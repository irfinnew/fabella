import os
import time
import OpenGL.GL as gl

import config
from logger import Logger
from image import Image

# FIXME: UGH
blursize = 32
expand = 10
shadow_img = None
shadow_texture = None

def get_shadow():
	global shadow_img, shadow_texture
	if shadow_texture is not None:
		return shadow_texture

	import PIL.Image, PIL.ImageFilter
	w, h = config.tile.width + blursize * 2, config.tile.thumb_height + blursize * 2

	shadow_img = PIL.Image.new('RGBA', (w, h), (255, 255, 255, 0))
	shadow_img.paste((255, 255, 255, 255), (blursize - expand, blursize - expand, w - blursize + expand, h - blursize + expand))
	shadow_img = shadow_img.filter(PIL.ImageFilter.GaussianBlur((blursize - expand) // 2))
	#shadow_img.paste((255, 255, 255, 255), (blursize, blursize, w - blursize, h - blursize))
	#shadow_img = shadow_img.filter(PIL.ImageFilter.GaussianBlur(blursize // 3))

	shadow_texture = gl.glGenTextures(1)
	gl.glBindTexture(gl.GL_TEXTURE_2D, shadow_texture)
	gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
	gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR)
	gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGBA, w, h, 0, gl.GL_RGBA, gl.GL_UNSIGNED_BYTE, shadow_img.tobytes())
	gl.glBindTexture(gl.GL_TEXTURE_2D, 0)
	return shadow_texture


class Tile:
	log = Logger(module='Tile', color=Logger.Magenta)
	name = ''
	menu = None
	font = None
	title = None
	path = ''
	full_path = ''
	isdir = False
	state_file = None
	state_last_update = 0
	position = 0
	parts_watched = None
	rendered = False

	def __init__(self, name, path, isdir, menu, font, extra, state, covers_zip):
		self.log.info(f'Created Tile path={path}, name={name}')
		self.name = name
		self.path = path
		self.menu = menu
		self.full_path = os.path.join(path, name)
		self.isdir = isdir
		self.font = font
		self.title = self.font.text(None, max_width=config.tile.width, lines=config.tile.text_lines)
		self.parts_watched = [False] * 10
		self.covers_zip = covers_zip

		self.cover = Image(None, config.tile.width, config.tile.thumb_height, self.name)

		self.duration = int(extra['duration']) if extra.get('duration') else None
		self.tile_color = str(extra['tile_color']) if extra.get('tile_color') else None

		# FIXME: error checking
		if self.tile_color is not None:
			self.tile_color = self.tile_color.strip('#')
			self.tile_color = tuple(int(self.tile_color[i:i+2], 16) / 255 for i in range(0, 6, 2))
		else:
			self.tile_color = (0, 0, 0)

		# FIXME: state
		if state:
			if 'position' in state:
				self.position = state['position']
			if 'parts_watched' in state:
				self.parts_watched = [pw == '#' for pw in state['parts_watched']]

		if not self.isdir:
			name = os.path.splitext(name)[0]
		# FIXME: don't do duration like this
		self.title.text = name + (f' ({self.duration}s)' if self.duration else '')
		self.render()

	def update_pos(self, position, force=False):
		self.log.debug(f'Tile {self.name} update_pos({position}, {force})')
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

	def render(self):
		self.log.info(f'Rendering for {self.name}')
		self.load_cover()
		self.rendered = True

	def load_cover(self):
		if self.covers_zip is None:
			self.log.error(f'Loading thumbnail for {self.name}: No zip')
			return None

		try:
			with self.covers_zip.open(self.name) as fd:
				self.log.info(f'Loading thumbnail for {self.name}')
				self.cover.source = fd.read()
		except KeyError:
			self.log.warning(f'Loading thumbnail for {self.name}: Not found in zip')
			pass

	def draw(self, x, y, selected=False):
		outset_x = int(config.tile.width * config.tile.highlight_outset / 2)
		outset_y = int(config.tile.thumb_height * config.tile.highlight_outset / 2)

		# Drop shadow
		x1, y1, x2, y2 = x - blursize, y - config.tile.thumb_height - blursize, x + config.tile.width + blursize, y + blursize
		if selected: x1 -= outset_x; y1 -= outset_y; x2 += outset_x; y2 += outset_y
		if selected:
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

		# Outline
		x1, y1, x2, y2 = x - 2, y - config.tile.thumb_height - 2, x + config.tile.width + 2, y + 2
		if selected: x1 -= outset_x; y1 -= outset_y; x2 += outset_x; y2 += outset_y
		gl.glColor4f(*config.tile.shadow_color)
		gl.glBegin(gl.GL_QUADS); gl.glVertex2f(x1, y1); gl.glVertex2f(x2, y1); gl.glVertex2f(x2, y2); gl.glVertex2f(x1, y2); gl.glEnd()

		# Thumbnail
		x1, y1, x2, y2 = x, y - config.tile.thumb_height, x + config.tile.width, y
		if selected: x1 -= outset_x; y1 -= outset_y; x2 += outset_x; y2 += outset_y
		if self.cover.texture:
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
		if self.title.texture is not None:
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

	def destroy(self):
		self.log.info(f'Destroying {self.name}')
		#FIXME: empty now

	def __str__(self):
		parts_watched = ''.join('#' if pw else '.' for pw in self.parts_watched)
		return f'Tile(name={self.name}, isdir={self.isdir}, position={self.position}, parts_watched={parts_watched})'
