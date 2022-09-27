# Fabella - Simple, elegant video library and player.
#
# Copyright 2020-2022 Marcel Moreaux.
# Licensed under GPL v2.0, or (at your option) any later version.
# (SPDX GPL-2.0-or-later) See LICENSE file for details.

import os
import io
import time
import uuid
import PIL.Image, PIL.ImageFilter, PIL.features, PIL.ImageDraw

import dbs
import config
import loghelper
import draw
import util

log = loghelper.get_logger('Tile', loghelper.Color.Cyan)



class Tile:
	xoff = None
	yoff = None

	@classmethod
	def initialize(cls):
		# FIXME: wrong place for this I think
		log.info(f'PIL / Pillow version {PIL.__version__}')
		if PIL.features.check_feature("libjpeg_turbo"):
			log.info('Pillow is using libjpeg-turbo')
		else:
			log.info('Pillow is NOT using libjpeg-turbo; loading cover images may be slower')

		cfg = config.tile

		# Positions etc
		cls.xoff = -cfg.width // 2
		cls.yoff = -cfg.cover_height // 2

		# Shadow
		w, h = cfg.width + cfg.shadow_blursize * 2, cfg.cover_height + cfg.shadow_blursize * 2

		shadow_img = PIL.Image.new('RGBA', (w, h), (255, 255, 255, 0))
		shadow_img.paste((255, 255, 255, 255), (
			cfg.shadow_blursize - cfg.shadow_expand, cfg.shadow_blursize - cfg.shadow_expand,
			w - cfg.shadow_blursize + cfg.shadow_expand, h - cfg.shadow_blursize + cfg.shadow_expand
		))
		shadow_img = shadow_img.filter(PIL.ImageFilter.GaussianBlur((cfg.shadow_blursize - cfg.shadow_expand) // 2))

		cls.tx_shadow = draw.Texture(shadow_img)

		# Highlight
		aa = 4
		outl = cfg.outline_size
		outs = cfg.highlight_outset
		w, h = cfg.width + (outl + outs) * 2, cfg.cover_height + (outl + outs) * 2

		hl_img = PIL.Image.new('RGBA', (w * aa, h * aa), (0, 0, 0, 0))
		imgdraw = PIL.ImageDraw.Draw(hl_img)
		imgdraw.rounded_rectangle((0, 0, w * aa - 1, h * aa - 1), fill=(255, 255, 255, 255), radius=cfg.highlight_outset * aa)
		hl_img = hl_img.resize((w, h))

		cls.tx_highlight = draw.Texture(hl_img)

		# Emblems
		size = round((config.tile.width * config.tile.cover_height) ** 0.5 * config.tile.emblem_scale)
		log.info(f'Emblems are {size}x{size} pixels')
		for emblem in ['unseen', 'watching', 'tagged']:
			with PIL.Image.open(f'img/{emblem}.png') as img:
				width, height = (size, size)
				image = PIL.ImageOps.fit(img, (width, height))

				# Shadow
				outset, blur_radius, blur_count = (1, 1, 8)
				border = outset * 2 + blur_radius * 2 + blur_count // 2 + 1 # Yeah maybe maybe not

				# Stencil
				new = PIL.Image.new('RGBA', (width + border * 2, height + border * 2))

				for i in range(blur_count):
					new.paste((0, 0, 0), (border - outset, border - outset), mask=image)
					new.paste((0, 0, 0), (border + outset, border - outset), mask=image)
					new.paste((0, 0, 0), (border + outset, border + outset), mask=image)
					new.paste((0, 0, 0), (border - outset, border + outset), mask=image)
					new = new.filter(PIL.ImageFilter.GaussianBlur(blur_radius))
				new.paste(image, (border, border), mask=image)

				setattr(cls, f'tx_{emblem}', draw.Texture(new))


	def __init__(self, menu, meta, covers_zip=None):
		self.menu = menu
		self.path = menu.path
		self.font = menu.tile_font # FIXME Yuck

		self.filename = meta['name']
		self.isdir = meta['isdir']
		self.full_path = os.path.join(self.path, self.filename)
		self.name = self.filename if self.isdir else os.path.splitext(self.filename)[0]
		# Filenames can't contain slashes, so backslashes may have been substituted
		# Backslashes don't make much sense in video titles, so convert them to slashes
		self.name = self.name.replace('\\', '/')

		log.debug(f'Created {self}')

		# State
		self.pos = (None, None)
		self.selected = False
		self.used = True
		self.state_last_update = 0

		# Metadata, will be populated later
		self.tile_color = (0, 0, 0, 1)
		self.duration = None
		self.position = 0
		self.tagged = False

		# Renderables
		self.quads = draw.Group()
		self.cover = None
		self.title = self.font.text(z=204, group=self.quads, text=self.name, color=config.tile.text_color,
			x=self.xoff, y=self.yoff - config.tile.text_vspace, anchor='tl',
			max_width=config.tile.width, lines=config.tile.text_lines,
		)
		self.info = None
		self.shadow = draw.Quad(z=200, group=self.quads,
			x=self.xoff - (self.tx_shadow.width - config.tile.width) // 2 + config.tile.shadow_offset,
			y=self.yoff - (self.tx_shadow.height - config.tile.cover_height) // 2 - config.tile.shadow_offset,
			texture=self.tx_shadow, color=config.tile.shadow_color
		)
		self.outline = draw.FlatQuad(z=202, group=self.quads,
			x=self.xoff - config.tile.outline_size,
			y=self.yoff - config.tile.outline_size,
			w=config.tile.width + config.tile.outline_size * 2,
			h=config.tile.cover_height + config.tile.outline_size * 2,
			color=config.tile.outline_color
		)
		self.highlight = None
		self.quad_unseen = None
		self.quad_watching = None
		self.quad_tagged = None
		self.quad_posbar = None
		self.quad_posback = None

		self.update_meta(meta)
		self.update_cover(covers_zip)


	def update_meta(self, meta):
		log.debug(f'Update metadata for {self}')

		if meta['name'] != self.filename:
			raise ValueError('{self}.update_meta({meta})')
		if meta['isdir'] != self.isdir:
			raise ValueError('{self}.update_meta({meta})')

		# Tile color
		if 'tile_color' in meta:
			tile_color = meta.get('tile_color', None)
			if tile_color is not None:
				tile_color = tile_color.strip('#')
				# FIXME: error checking
				self.tile_color = tuple(int(tile_color[i:i+2], 16) / 255 for i in range(0, 6, 2)) + (1,)
			else:
				self.tile_color = (0.3, 0.3, 0.3, 1)

		# Duration
		if 'duration' in meta:
			self.duration = meta.get('duration', None)
			if not self.info:
				self.info = self.font.text(z=204, group=self.quads, color=config.tile.text_color,
					x=self.xoff + config.tile.width - 4, y=self.yoff, anchor='br')
			if self.duration is None:
				self.info.text = '?:??'
			else:
				self.info.text = util.duration_format(int(self.duration), seconds=False)

		if 'position' in meta:
			self.position = meta['position']

		if 'tagged' in meta:
			self.tagged = meta['tagged']


	def update_cover(self, covers_zip):
		try:
			with covers_zip.open(self.filename) as fd:
				cover_data = fd.read()
		except KeyError:
			cover_data = None
			log.warning(f'Loading thumbnail for {self.filename}: Not found in zip')

		# FIXME: reuse instead of recreate
		if self.cover:
			self.cover.destroy()
		if cover_data:
			img = PIL.Image.open(io.BytesIO(cover_data))
			# Always convert to RGBA; 4-byte pixels avoid alignment problems
			img = img.convert('RGBA')
			if (img.width, img.height) != (config.tile.width, config.tile.cover_height):
				#img = PIL.ImageOps.fit(img, (config.tile.width, config.tile.cover_height))
				img = util.img_crop_ratio(img, (config.tile.width, config.tile.cover_height))
			self.cover = draw.Quad(z=203, group=self.quads,
				x=self.xoff, y=self.yoff, w=config.tile.width, h=config.tile.cover_height,
				image=img
			)
		else:
			self.cover = draw.FlatQuad(z=203, group=self.quads,
				x=self.xoff, y=self.yoff, w=config.tile.width, h=config.tile.cover_height,
				color=self.tile_color
			)


	def show(self, pos, selected):
		if (pos, selected) != (self.pos, self.selected):
			self.pos = pos
			self.selected = selected
			self.render()

		if selected:
			draw.Animation(self.quads, duration=0.2, scale=(1.1, 1))
			self.title.lines = config.tile.text_lines_selected
		else:
			self.title.lines = config.tile.text_lines


	def destroy(self):
		self.pos = None
		self.selected = False
		self.quads.destroy()


	def maybe(self, cls, name, active, **kwargs):
		quad = getattr(self, name)

		if not active:
			if quad:
				quad.destroy()
				self.quads.remove(quad)
				setattr(self, name, None)
			return

		if quad:
			for k, v in kwargs.items():
				setattr(quad, k, v)
		else:
			quad = cls(**kwargs, group=self.quads)
			setattr(self, name, quad)


	def render(self):
		self.maybe(draw.Quad, 'highlight', self.selected, z=201,
			x=self.xoff - config.tile.outline_size - config.tile.highlight_outset,
			y=self.yoff - config.tile.outline_size - config.tile.highlight_outset,
			texture=self.tx_highlight, color=config.tile.highlight_color,
		)
		self.maybe(draw.Quad, 'quad_unseen', self.unseen, z=204,
			x=self.xoff + config.tile.width - self.tx_unseen.width // 2,
			y=self.yoff + config.tile.cover_height - self.tx_unseen.height // 2,
			texture=self.tx_unseen,
		)
		self.maybe(draw.Quad, 'quad_watching', self.watching, z=204,
			x=self.xoff + config.tile.width - self.tx_watching.width // 2,
			y=self.yoff + config.tile.cover_height - self.tx_watching.height // 2,
			texture=self.tx_watching,
		)
		offset = self.unseen * self.tx_unseen.width or self.watching * self.tx_watching.width or 0
		self.maybe(draw.Quad, 'quad_tagged', self.tagged, z=204,
			x=self.xoff + config.tile.width - self.tx_tagged.width // 2 - offset,
			y=self.yoff + config.tile.cover_height - self.tx_tagged.height // 2,
			texture=self.tx_tagged,
		)

		active = (0 < self.position < 1) and not self.isdir
		w, h = int(config.tile.width * self.position), config.tile.pos_bar_height
		self.maybe(draw.FlatQuad, 'quad_posback', active, z=204,
			x=self.xoff - 1, y=self.yoff - 1, w=w + 2, h=h + 2,
			color=config.tile.shadow_color,
		)
		self.maybe(draw.FlatQuad, 'quad_posbar', active, z=205,
			x=self.xoff, y=self.yoff, w=w, h=h,
			color=config.tile.pos_bar_color,
		)

		self.title.quad.color = config.tile.text_hl_color if self.selected else config.tile.text_color
		if self.info:
			self.info.quad.color = config.tile.text_hl_color if self.selected else config.tile.text_color

		self.quads.pos = self.pos


	def update_pos(self, position, force=False):
		log.debug(f'{self} update_pos({position}, {force})')
		old_pos = self.position
		self.position = position

		now = time.time()
		if now - self.state_last_update > 10 or abs(old_pos - position) > 0.01 or force:
			self.state_last_update = now
			self.write_state_update()


	def write_state_update(self, state=None):
		if state is None:
			state = {'position': self.position}
		log.info(f'Writing state for {self.filename}: {state}')
		update_name = os.path.join(self.path, dbs.QUEUE_DIR_NAME, str(uuid.uuid4()))
		dbs.json_write(update_name, {self.filename: state})


	@property
	def unseen(self):
		return self.position == 0


	@property
	def watching(self):
		return 0 < self.position < 1


	def toggle_seen(self, seen=None):
		if self.isdir:
			return

		if seen is None:
			self.position = 1 if self.position < 1 else 0
		else:
			self.position = 1 if seen else 0

		self.write_state_update()
		self.render()


	def toggle_tagged(self):
		if self.isdir:
			return

		self.tagged = not self.tagged
		self.write_state_update({'tagged': self.tagged})
		self.render()


	def __str__(self):
		return f'<Tile path={self.path}, name={self.name}, isdir={self.isdir}>'


	def __repr__(self):
		return str(self)
