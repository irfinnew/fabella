import os
import io
import time
import math
import uuid
import OpenGL.GL as gl
import functools
import PIL.Image, PIL.ImageFilter

import dbs
import config
import loghelper
import draw

log = loghelper.get_logger('Tile', loghelper.Color.Cyan)



class Tile:
	xoff = -config.tile.width // 2
	yoff = -config.tile.thumb_height // 2

	@classmethod
	def initialize(cls):
		# FIXME: wrong place I think
		log.info(f'PIL / Pillow version {PIL.__version__}')
		cfg = config.tile

		# Shadow
		w, h = cfg.width + cfg.shadow_blursize * 2, cfg.thumb_height + cfg.shadow_blursize * 2

		shadow_img = PIL.Image.new('RGBA', (w, h), (255, 255, 255, 0))
		shadow_img.paste((255, 255, 255, 255), (
			cfg.shadow_blursize - cfg.shadow_expand, cfg.shadow_blursize - cfg.shadow_expand,
			w - cfg.shadow_blursize + cfg.shadow_expand, h - cfg.shadow_blursize + cfg.shadow_expand
		))
		shadow_img = shadow_img.filter(PIL.ImageFilter.GaussianBlur((cfg.shadow_blursize - cfg.shadow_expand) // 2))

		cls.tx_shadow = draw.Texture(shadow_img)

		# Highlight
		w, h = cfg.width + cfg.highlight_blursize * 2, cfg.thumb_height + cfg.highlight_blursize * 2

		hl_img = PIL.Image.new('RGBA', (w, h), (255, 255, 255, 0))
		hl_img.paste((255, 255, 255, 255), (
			cfg.highlight_blursize - cfg.highlight_expand, cfg.highlight_blursize - cfg.highlight_expand,
			w - cfg.highlight_blursize + cfg.highlight_expand, h - cfg.highlight_blursize + cfg.highlight_expand))
		hl_img = hl_img.filter(PIL.ImageFilter.GaussianBlur((cfg.highlight_blursize - cfg.highlight_expand) // 2))

		cls.tx_highlight = draw.Texture(hl_img)

		# Emblems
		for emblem in ['unseen', 'watching', 'tagged']:
			with PIL.Image.open(f'img/{emblem}.png') as img:
				# FIXME: hardcoded size
				width, height = (48, 48)
				image = PIL.ImageOps.fit(img, (width, height))

				# Shadow
				blur_radius, blur_count = (2, 12)
				outset = blur_radius + blur_count // 2 + 1

				# Stencil
				new = PIL.Image.new('RGBA', (width + outset * 2, height + outset * 2))

				for i in range(blur_count):
					new.paste((0, 0, 0), (outset - 1, outset - 1), mask=image)
					new.paste((0, 0, 0), (outset + 1, outset - 1), mask=image)
					new.paste((0, 0, 0), (outset + 1, outset + 1), mask=image)
					new.paste((0, 0, 0), (outset - 1, outset + 1), mask=image)
					new = new.filter(PIL.ImageFilter.GaussianBlur(blur_radius))
				new.paste(image, (outset, outset), mask=image)

				setattr(cls, f'tx_{emblem}', draw.Texture(new))


	def __init__(self, menu, meta, covers_zip=None):
		self.menu = menu
		self.path = menu.path
		self.font = menu.tile_font # FIXME Yuck

		self.name = meta['name']
		self.isdir = meta['isdir']
		self.full_path = os.path.join(self.path, self.name)

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
		self.cover = None
		self.title = self.font.text(z=204, text=self.name,
			x=self.xoff, y=self.yoff - config.tile.text_vspace, anchor='tl',
			max_width=config.tile.width, lines=config.tile.text_lines,
		)
		self.info = None
		self.shadow = draw.Quad(z=200,
			x=self.xoff - (self.tx_shadow.width - config.tile.width) // 2 + config.tile.shadow_offset,
			y=self.yoff - (self.tx_shadow.height - config.tile.thumb_height) // 2 - config.tile.shadow_offset,
			texture=self.tx_shadow, color=config.tile.shadow_color
		)
		self.outline = draw.FlatQuad(z=202,
			x=self.xoff - config.tile.outline_size,
			y=self.yoff - config.tile.outline_size,
			w=config.tile.width + config.tile.outline_size * 2,
			h=config.tile.thumb_height + config.tile.outline_size * 2,
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

		if meta['name'] != self.name:
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
				self.info = self.font.text(z=204, x=self.xoff + config.tile.width - 4, y=self.yoff, anchor='br')
			if self.duration is None:
				self.info.text = '?:??'
			else:
				duration = int(self.duration)
				hours = duration // 3600
				minutes = (duration % 3600) // 60
				self.info.text = f'{hours}:{minutes:>02}'

		if 'position' in meta:
			self.position = meta['position']

		if 'tagged' in meta:
			self.tagged = meta['tagged']


	def update_cover(self, covers_zip):
		try:
			with covers_zip.open(self.name) as fd:
				cover_data = fd.read()
		except KeyError:
			cover_data = None
			log.warning(f'Loading thumbnail for {self.name}: Not found in zip')

		# FIXME: reuse instead of recreate
		if self.cover:
			self.cover.destroy()
		if cover_data:
			cover_img = PIL.Image.open(io.BytesIO(cover_data))
			self.cover = draw.Quad(z=203, x=self.xoff, y=self.yoff, image=cover_img)
		else:
			self.cover = draw.FlatQuad(z=203,
				x=self.xoff, y=self.yoff, w=config.tile.width, h=config.tile.thumb_height,
				color=self.tile_color
			)


	def show(self, pos, selected):
		if (pos, selected) != (self.pos, self.selected):
			self.pos = pos
			self.selected = selected
			self.selected_time = time.time() # FIXME
			self.render()

		if selected:
			quads = draw.Group(self.shadow, self.highlight, self.outline, self.cover, self.title.quad)
			quads.add(self.quad_unseen, self.quad_watching, self.quad_tagged)
			if self.info:
				quads.add(self.info.quad)
			draw.Animation(quads, duration=0.3, opacity=(0.4, 1), scale=(1.2, 1))

	def animate_blowup(self, xpos, ypos):
		quads = draw.Group(self.shadow, self.highlight, self.outline, self.cover, self.title.quad)
		quads.add(self.quad_unseen, self.quad_watching, self.quad_tagged, self.quad_posback, self.quad_posbar)
		if self.info:
			quads.add(self.info.quad)
		draw.Animation(quads, duration=0.5, opacity=(1, 0), scale=(1, 6), xpos=(self.pos[0], xpos), ypos=(self.pos[1], ypos), after=self.destroy)

	def destroy(self):
		self.pos = None
		self.selected = False

		self.cover.destroy()
		self.title.destroy()
		self.shadow.destroy()
		self.outline.destroy()
		if self.info:
			self.info.destroy()
		if self.highlight:
			self.highlight.destroy()
		if self.quad_unseen:
			self.quad_unseen.destroy()
		if self.quad_watching:
			self.quad_watching.destroy()
		if self.quad_tagged:
			self.quad_tagged.destroy()
		if self.quad_posbar:
			self.quad_posbar.destroy()
		if self.quad_posback:
			self.quad_posback.destroy()


	def maybe(self, cls, name, active, **kwargs):
		quad = getattr(self, name)

		if not active:
			if quad:
				quad.destroy()
				setattr(self, name, None)
			return

		if quad:
			for k, v in kwargs.items():
				setattr(quad, k, v)
		else:
			quad = cls(**kwargs)
			setattr(self, name, quad)


	def render(self):
		self.shadow.pos = self.pos
		self.outline.pos = self.pos
		self.cover.pos = self.pos
		self.title.quad.pos = self.pos
		if self.info:
			self.info.quad.pos = self.pos

		self.maybe(draw.Quad, 'highlight', self.selected, z=201,
			x=self.xoff - config.tile.highlight_blursize,
			y=self.yoff - config.tile.highlight_blursize,
			texture=self.tx_highlight, color=config.tile.highlight_color,
			pos=self.pos,
		)
		self.maybe(draw.Quad, 'quad_unseen', self.unseen, z=204,
			x=self.xoff + config.tile.width - self.tx_unseen.width // 2,
			y=self.yoff + config.tile.thumb_height - self.tx_unseen.height // 2,
			texture=self.tx_unseen,
			pos=self.pos,
		)
		self.maybe(draw.Quad, 'quad_watching', self.watching, z=204,
			x=self.xoff + config.tile.width - self.tx_watching.width // 2,
			y=self.yoff + config.tile.thumb_height - self.tx_watching.height // 2,
			texture=self.tx_watching,
			pos=self.pos,
		)
		offset = self.unseen * self.tx_unseen.width or self.watching * self.tx_watching.width or 0
		self.maybe(draw.Quad, 'quad_tagged', self.tagged, z=204,
			x=self.xoff + config.tile.width - self.tx_tagged.width // 2 - offset,
			y=self.yoff + config.tile.thumb_height - self.tx_tagged.height // 2,
			texture=self.tx_tagged,
			pos=self.pos,
		)

		active = (0 < self.position < 1) and not self.isdir
		w, h = int(config.tile.width * self.position), config.tile.pos_bar_height
		self.maybe(draw.FlatQuad, 'quad_posback', active, z=204,
			x=self.xoff - 1, y=self.yoff - 1, w=w + 2, h=h + 2, pos=self.pos,
			color=config.tile.shadow_color,
		)
		self.maybe(draw.FlatQuad, 'quad_posbar', active, z=205,
			x=self.xoff, y=self.yoff, w=w, h=h, pos=self.pos,
			color=config.tile.pos_bar_color,
		)


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
		log.info(f'Writing state for {self.name}: {state}')
		update_name = os.path.join(self.path, dbs.QUEUE_DIR_NAME, str(uuid.uuid4()))
		dbs.json_write(update_name, {self.name: state})


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
