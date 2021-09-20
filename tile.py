import os
import time
import OpenGL.GL as gl
import functools

import config
from logger import Logger
from image import Image

# FIXME: UGH
shadow_blursize = 32
shadow_expand = 14
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


def json_get(data, key, typ, none=False):
	value = data[key]

	if none and value is None:
		return None

	if not isinstance(value, typ):
		raise TypeError(f'Expected {key} to be {typ}: {value}')
	return value



class Tile:
	log = Logger(module='Tile', color=Logger.Magenta)


	def __init__(self, path, name, isdir, menu, font, render_pool):
		self.name = name
		self.path = path
		self.full_path = os.path.join(path, name)
		self.isdir = isdir
		self.menu = menu
		self.render_pool = render_pool
		self.font = font
		self.state_last_update = 0  # FIXME: is this still needed?

		self.log.debug(f'Created {self}')

		# Metadata, will be populated later
		self.tile_color = (0, 0, 0)
		self.duration = None
		self.position = 0
		self.parts_watched = [False] * 10

		# Renderables
		self.title = self.font.text(None, max_width=config.tile.width, lines=config.tile.text_lines, pool=self.render_pool)
		self.title.text = self.name if self.isdir else os.path.splitext(self.name)[0]
		self.cover = None
		self.info = None

	def update_meta(self, meta):
		self.log.debug(f'Update metadata for {self}')

		if json_get(meta, 'name', str) != self.name:
			raise ValueError('{self}.update_meta({meta})')
		if json_get(meta, 'isdir', bool) != self.isdir:
			raise ValueError('{self}.update_meta({meta})')

		# Tile color
		if 'tile_color' in meta:
			tile_color = json_get(meta, 'tile_color', str, none=True)
			if tile_color is not None:
				tile_color = tile_color.strip('#')
				# FIXME: error checking
				self.tile_color = tuple(int(tile_color[i:i+2], 16) / 255 for i in range(0, 6, 2))
			else:
				self.tile_color = (0.3, 0.3, 0.3)

		# Duration
		if 'duration' in meta:
			self.duration = json_get(meta, 'duration', int, none=True)
			if not self.info:
				self.info = self.font.text(None, max_width=None, lines=1, pool=self.render_pool)
			if self.duration is None:
				self.info.text = '?:??'
			else:
				duration = int(self.duration)
				hours = duration // 3600
				minutes = round((duration % 3600) / 60)
				self.info.text = f'{hours}:{minutes:>02}'

		# Position
		if 'position' in meta:
			self.position = json_get(meta, 'position', (float, int))

		# Parts_watched
		if 'parts_watched' in meta:
			self.parts_watched = [pw == '#' for pw in json_get(meta, 'parts_watched', str)]


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
			self.log.warning(f'Loading thumbnail for {self.name}: Not found in zip')


	@classmethod
	def release_all_textures(cls, tiles):
		tobjs = [t.title for t in tiles] + [t.cover for t in tiles] + [t.info for t in tiles]
		tobjs = [o for o in tobjs if o]

		textures = [o._texture for o in tobjs if o._texture]
		cls.log.info(f'Deleting {len(textures)} textures')
		gl.glDeleteTextures(textures)

		for o in tobjs:
			o._texture = None


	def update_pos(self, position, force=False):
		self.log.debug(f'{self} update_pos({position}, {force})')
		old_pos = self.position
		self.position = position
		# FIXME: detect if user was watching for a while before marking part as watched
		self.parts_watched[min(int(position * 10), 9)] = True

		now = time.time()
		if now - self.state_last_update > 10 or abs(old_pos - position) > 0.01 or force:
			self.state_last_update = now
			self.write_state()


	def write_state(self):
		self.log.info(f'Writing state for {self.name}')
		parts_watched = ''.join('#' if pw else '.' for pw in self.parts_watched)
		self.menu.write_state(self.name, {'position': self.position, 'parts_watched': parts_watched})


	@property
	def unseen(self):
		if self.isdir:
			return False
		return self.parts_watched == [False] * 10


	@property
	def watching(self):
		if self.isdir:
			return False
		return self.parts_watched != [False] * 10 and self.parts_watched != [True] * 10


	def toggle_seen(self):
		if self.parts_watched == [True] * 10:
			self.parts_watched = [False] * 10
		else:
			self.parts_watched = [True] * 10
		self.position = 0
		self.write_state()


	def draw(self, x, y, selected=False):
		outset_x = int(config.tile.width * config.tile.highlight_outset / 2)
		outset_y = int(config.tile.thumb_height * config.tile.highlight_outset / 2)

		# Drop shadow
		x1, y1, x2, y2 = x - shadow_blursize, y - config.tile.thumb_height - shadow_blursize, x + config.tile.width + shadow_blursize, y + shadow_blursize
		x1 += 8; x2 += 8; y1 -= 8; y2 -= 8
		#if selected: x1 += 4; x2 += 4; y1 -= 4; y2 -= 4
		#if selected: x1 -= outset_x; y1 -= outset_y; x2 += outset_x; y2 += outset_y
		if selected and False:
			gl.glColor4f(*config.tile.highlight_color)
		else:
			gl.glColor4f(*config.tile.shadow_color)
		gl.glBindTexture(gl.GL_TEXTURE_2D, get_shadow())
		gl.glBegin(gl.GL_QUADS)
		gl.glTexCoord2f(0.0, 1.0)
		gl.glVertex2f(x1, y1)
		gl.glTexCoord2f(1.0, 1.0)
		gl.glVertex2f(x2, y1)
		gl.glTexCoord2f(1.0, 0.0)
		gl.glVertex2f(x2, y2)
		gl.glTexCoord2f(0.0, 0.0)
		gl.glVertex2f(x1, y2)
		gl.glEnd()
		gl.glBindTexture(gl.GL_TEXTURE_2D, 0)

		# Select
		if selected:
			x1, y1, x2, y2 = x - hl_blursize, y - config.tile.thumb_height - hl_blursize, x + config.tile.width + hl_blursize, y + hl_blursize
			gl.glBindTexture(gl.GL_TEXTURE_2D, get_hl())
			gl.glColor4f(*config.tile.highlight_color)
			gl.glBegin(gl.GL_QUADS)
			gl.glTexCoord2f(0.0, 1.0)
			gl.glVertex2f(x1, y1)
			gl.glTexCoord2f(1.0, 1.0)
			gl.glVertex2f(x2, y1)
			gl.glTexCoord2f(1.0, 0.0)
			gl.glVertex2f(x2, y2)
			gl.glTexCoord2f(0.0, 0.0)
			gl.glVertex2f(x1, y2)
			gl.glEnd()
			gl.glBindTexture(gl.GL_TEXTURE_2D, 0)

		# Outline
		x1, y1, x2, y2 = x - 2, y - config.tile.thumb_height - 2, x + config.tile.width + 2, y + 2
		#if selected: x1 -= outset_x; y1 -= outset_y; x2 += outset_x; y2 += outset_y
		gl.glColor4f(*config.tile.shadow_color)
		gl.glBegin(gl.GL_QUADS); gl.glVertex2f(x1, y1); gl.glVertex2f(x2, y1); gl.glVertex2f(x2, y2); gl.glVertex2f(x1, y2); gl.glEnd()

		# Thumbnail
		x1, y1, x2, y2 = x, y - config.tile.thumb_height, x + config.tile.width, y
		#if selected: x1 -= 4; x2 -= 4; y1 += 4; y2 += 4
		if self.cover and self.cover.texture:
			if selected: x1 -= outset_x; y1 -= outset_y; x2 += outset_x; y2 += outset_y
			gl.glColor4f(1, 1, 1, 1)
			gl.glBindTexture(gl.GL_TEXTURE_2D, self.cover.texture)
			gl.glBegin(gl.GL_QUADS)
			gl.glTexCoord2f(0.0, 1.0)
			gl.glVertex2f(x1, y1)
			gl.glTexCoord2f(1.0, 1.0)
			gl.glVertex2f(x2, y1)
			gl.glTexCoord2f(1.0, 0.0)
			gl.glVertex2f(x2, y2)
			gl.glTexCoord2f(0.0, 0.0)
			gl.glVertex2f(x1, y2)
			gl.glEnd()
			gl.glBindTexture(gl.GL_TEXTURE_2D, 0)
		else:
			gl.glColor4f(*self.tile_color, 1)
			gl.glBegin(gl.GL_QUADS); gl.glVertex2f(x1, y1); gl.glVertex2f(x2, y1); gl.glVertex2f(x2, y2); gl.glVertex2f(x1, y2); gl.glEnd()

		# Info
		if self.info and self.info.texture:
			y1, x2 = y - config.tile.thumb_height, x + int(config.tile.width * 0.98)
			x1, y2 = x2 - self.info.width, y1 + self.info.height
			if selected:
				gl.glColor4f(*config.tile.text_hl_color)
			else:
				gl.glColor4f(*config.tile.text_color)
			gl.glBindTexture(gl.GL_TEXTURE_2D, self.info.texture)
			gl.glBegin(gl.GL_QUADS)
			gl.glTexCoord2f(0.0, 1.0)
			gl.glVertex2f(x1, y1)
			gl.glTexCoord2f(1.0, 1.0)
			gl.glVertex2f(x2, y1)
			gl.glTexCoord2f(1.0, 0.0)
			gl.glVertex2f(x2, y2)
			gl.glTexCoord2f(0.0, 0.0)
			gl.glVertex2f(x1, y2)
			gl.glEnd()
			gl.glBindTexture(gl.GL_TEXTURE_2D, 0)

		# Position bar
		x1, y1 = x, y - config.tile.thumb_height - 1 - config.tile.pos_bar_height
		x2, y2 = x1 + config.tile.width * self.position, y1 + config.tile.pos_bar_height
		gl.glColor4f(*config.tile.pos_bar_color)
		gl.glBegin(gl.GL_QUADS); gl.glVertex2f(x1, y1); gl.glVertex2f(x2, y1); gl.glVertex2f(x2, y2); gl.glVertex2f(x1, y2); gl.glEnd()

		# "Watching" emblem
		if self.watching:
			x1, y1 = x + config.tile.width - 62, y + 10
			x2, y2 = x1 + 72, y1 - 30
			gl.glColor4f(0, 0, 0, 1)
			gl.glBegin(gl.GL_QUADS); gl.glVertex2f(x1, y1); gl.glVertex2f(x2, y1); gl.glVertex2f(x2, y2); gl.glVertex2f(x1, y2); gl.glEnd()
			x1 += 2; y1 -= 2; x2 = x1 + 5; y2 += 2
			gl.glColor4f(1, 0, 0, 1)
			for i in range(10):
				if self.parts_watched[i]:
					gl.glBegin(gl.GL_QUADS); gl.glVertex2f(x1, y1); gl.glVertex2f(x2, y1); gl.glVertex2f(x2, y2); gl.glVertex2f(x1, y2); gl.glEnd()
				x1 += 7
				x2 += 7

		# "Unseen" emblem
		if self.unseen:
			x1, y1 = x + config.tile.width - 20, y + 10
			x2, y2 = x1 + 30, y1 - 30
			gl.glColor4f(0, 0, 0, 1)
			gl.glBegin(gl.GL_QUADS); gl.glVertex2f(x1, y1); gl.glVertex2f(x2, y1); gl.glVertex2f(x2, y2); gl.glVertex2f(x1, y2); gl.glEnd()
			x1 += 2; y1 -= 2; x2 -= 2; y2 += 2
			gl.glColor4f(1, 1, 0, 1)
			gl.glBegin(gl.GL_QUADS); gl.glVertex2f(x1, y1); gl.glVertex2f(x2, y1); gl.glVertex2f(x2, y2); gl.glVertex2f(x1, y2); gl.glEnd()

		# Title
		if self.title and self.title.texture:
			x1, y1 = x, y - config.tile.thumb_height - config.tile.text_vspace - self.title.height
			x2, y2 = x1 + self.title.width, y1 + self.title.height
			if selected: y1 -= outset_y; y2 -= outset_y
			if selected:
				gl.glColor4f(*config.tile.text_hl_color)
			else:
				gl.glColor4f(*config.tile.text_color)
			gl.glBindTexture(gl.GL_TEXTURE_2D, self.title.texture)
			gl.glBegin(gl.GL_QUADS)
			gl.glTexCoord2f(0.0, 1.0)
			gl.glVertex2f(x1, y1)
			gl.glTexCoord2f(1.0, 1.0)
			gl.glVertex2f(x2, y1)
			gl.glTexCoord2f(1.0, 0.0)
			gl.glVertex2f(x2, y2)
			gl.glTexCoord2f(0.0, 0.0)
			gl.glVertex2f(x1, y2)
			gl.glEnd()
			gl.glBindTexture(gl.GL_TEXTURE_2D, 0)


	def __str__(self):
		return f'Tile(path={self.path}, name={self.name}, isdir={self.isdir})'


	def __repr__(self):
		return self.__str__()
