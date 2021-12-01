import os
import time
import math
import uuid
import OpenGL.GL as gl
import functools

import dbs
import config
import loghelper
from image import Image, ImgLib
from draw import FlatQuad, TexturedQuad

log = loghelper.get_logger('Tile', loghelper.Color.Cyan)



# FIXME: UGH
shadow_blursize = 32
shadow_expand = 4
shadow_img = None
shadow_texture = None

def get_shadow():
	global shadow_img, shadow_texture
	if shadow_texture is not None:
		return shadow_texture

	import PIL.Image, PIL.ImageFilter
	w, h = config.tile.width + shadow_blursize * 2, config.tile.thumb_height + shadow_blursize * 2

	shadow_img = PIL.Image.new('RGBA', (w, h), (255, 255, 255, 0))
	shadow_img.paste((255, 255, 255, 255), (shadow_blursize - shadow_expand, shadow_blursize - shadow_expand, w - shadow_blursize + shadow_expand, h - shadow_blursize + shadow_expand))
	shadow_img = shadow_img.filter(PIL.ImageFilter.GaussianBlur((shadow_blursize - shadow_expand) // 2))
	#shadow_img.paste((255, 255, 255, 255), (shadow_blursize, shadow_blursize, w - shadow_blursize, h - shadow_blursize))
	#shadow_img = shadow_img.filter(PIL.ImageFilter.GaussianBlur(shadow_blursize // 3))

	shadow_texture = gl.glGenTextures(1)
	gl.glBindTexture(gl.GL_TEXTURE_2D, shadow_texture)
	gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
	gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR)
	gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGBA, w, h, 0, gl.GL_RGBA, gl.GL_UNSIGNED_BYTE, shadow_img.tobytes())
	gl.glBindTexture(gl.GL_TEXTURE_2D, 0)
	return shadow_texture

# FIXME: UGH
hl_blursize = 19
hl_expand = 10
hl_img = None
hl_texture = None

def get_hl():
	global hl_img, hl_texture
	if hl_texture is not None:
		return hl_texture

	import PIL.Image, PIL.ImageFilter
	w, h = config.tile.width + hl_blursize * 2, config.tile.thumb_height + hl_blursize * 2

	hl_img = PIL.Image.new('RGBA', (w, h), (255, 255, 255, 0))
	hl_img.paste((255, 255, 255, 255), (hl_blursize - hl_expand, hl_blursize - hl_expand, w - hl_blursize + hl_expand, h - hl_blursize + hl_expand))
	hl_img = hl_img.filter(PIL.ImageFilter.GaussianBlur((hl_blursize - hl_expand) // 2))
	#hl_img.paste((255, 255, 255, 255), (hl_blursize, hl_blursize, w - hl_blursize, h - hl_blursize))
	#hl_img = hl_img.filter(PIL.ImageFilter.GaussianBlur(hl_blursize // 3))

	hl_texture = gl.glGenTextures(1)
	gl.glBindTexture(gl.GL_TEXTURE_2D, hl_texture)
	gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
	gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR)
	gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGBA, w, h, 0, gl.GL_RGBA, gl.GL_UNSIGNED_BYTE, hl_img.tobytes())
	gl.glBindTexture(gl.GL_TEXTURE_2D, 0)
	return hl_texture



class Tile:
	def __init__(self, path, name, isdir, menu, font, render_pool):
		self.name = name
		self.path = path
		self.full_path = os.path.join(path, name)
		self.isdir = isdir
		self.menu = menu
		self.render_pool = render_pool
		self.font = font
		self.state_last_update = 0  # FIXME: is this still needed?

		log.debug(f'Created {self}')

		# Metadata, will be populated later
		self.tile_color = (0, 0, 0)
		self.duration = None
		self.position = 0
		self.tagged = False

		# Renderables
		self.title = self.font.text(None, max_width=config.tile.width, lines=config.tile.text_lines, pool=self.render_pool)
		self.title.text = self.name if self.isdir else os.path.splitext(self.name)[0]
		self.cover = None
		self.info = None

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
				self.tile_color = tuple(int(tile_color[i:i+2], 16) / 255 for i in range(0, 6, 2))
			else:
				self.tile_color = (0.3, 0.3, 0.3)

		# Duration
		if 'duration' in meta:
			self.duration = meta.get('duration', None)
			if not self.info:
				self.info = self.font.text(None, max_width=None, lines=1, pool=self.render_pool)
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
		if not self.cover:
			self.cover = Image(None, config.tile.width, config.tile.thumb_height, self.name, pool=self.render_pool)
		try:
			with covers_zip.open(self.name) as fd:
				image = fd.read()
				# The cover image can be empty (if no cover is known)
				if image:
					self.cover.source = image
		except KeyError:
			log.warning(f'Loading thumbnail for {self.name}: Not found in zip')


	@classmethod
	def release_all_textures(cls, tiles):
		tobjs = [t.title for t in tiles] + [t.cover for t in tiles] + [t.info for t in tiles]
		tobjs = [o for o in tobjs if o]

		textures = [o._texture for o in tobjs if o._texture]
		log.info(f'Deleting {len(textures)} textures')
		gl.glDeleteTextures(textures)

		for o in tobjs:
			o._texture = None


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


	def toggle_tagged(self):
		if self.isdir:
			return

		self.tagged = not self.tagged
		self.write_state_update({'tagged': self.tagged})


	def draw(self, x, y, selected=False):
		# Drop shadow
		x1, y1, x2, y2 = x - shadow_blursize, y - config.tile.thumb_height - shadow_blursize, x + config.tile.width + shadow_blursize, y + shadow_blursize
		x1 += 8; x2 += 8; y1 -= 8; y2 -= 8
		TexturedQuad((x1, y1, x2, y2), 200, get_shadow(), color=config.tile.shadow_color)

		# Select
		if selected:
			x1, y1, x2, y2 = x - hl_blursize, y - config.tile.thumb_height - hl_blursize, x + config.tile.width + hl_blursize, y + hl_blursize
			TexturedQuad((x1, y1, x2, y2), 201, get_hl(), color=config.tile.highlight_color)

		# Outline
		x1, y1, x2, y2 = x - 2, y - config.tile.thumb_height - 2, x + config.tile.width + 2, y + 2
		FlatQuad((x1, y1, x2, y2), 202, config.tile.shadow_color)

		# Thumbnail
		x1, y1, x2, y2 = x, y - config.tile.thumb_height, x + config.tile.width, y
		if self.cover:
			TexturedQuad((x1, y1, x2, y2), 203, self.cover.texture)

		# Info
		if self.info:
			self.info.as_quad(
				-(x + int(config.tile.width * 0.98)), y - config.tile.thumb_height,
				204,
				config.tile.text_hl_color if selected else config.tile.text_color
			)

		# Position bar
		if self.position < 1 and not self.isdir:
			x1, y1 = x, y - config.tile.thumb_height - 1
			x2, y2 = x1 + config.tile.width * self.position, y1 + config.tile.pos_bar_height
			FlatQuad((x1 - 1, y1 - 1, x2 + 1, y2 + 1), 204, config.tile.shadow_color)
			FlatQuad((x1, y1, x2, y2), 205, config.tile.pos_bar_color)

		# "Watching" emblem
		if self.watching:
			ImgLib.Watching.as_quad(x + config.tile.width - ImgLib.Watching.width // 2, y - ImgLib.Watching.height // 2, 204)

		# "Unseen" emblem
		if self.unseen:
			ImgLib.Unseen.as_quad(x + config.tile.width - ImgLib.Unseen.width // 2, y - ImgLib.Unseen.height // 2, 204)

		# "Tagged" emblem
		if self.tagged:
			ImgLib.Tagged.as_quad(x - ImgLib.Tagged.width // 2, y - ImgLib.Tagged.height // 2, 204)

		# Title
		if self.title:
			x1, y1 = x, y - config.tile.thumb_height - config.tile.text_vspace - self.title.height
			self.title.as_quad(x1, y1, 204, color=config.tile.text_hl_color if selected else config.tile.text_color)


	def __str__(self):
		return f'Tile(path={self.path}, name={self.name}, isdir={self.isdir})'


	def __repr__(self):
		return self.__str__()
