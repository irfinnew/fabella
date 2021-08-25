import os
import time
import OpenGL.GL as gl

import config
from logger import Logger

# FIXME: UGH
blursize = 32
shadow_img = None
shadow_texture = None

def get_shadow():
	global shadow_img, shadow_texture
	if shadow_texture is not None:
		return shadow_texture

	import PIL.Image, PIL.ImageFilter
	w, h = config.tile.width + blursize * 2, config.tile.thumb_height + blursize * 2

	shadow_img = PIL.Image.new('RGBA', (w, h), (255, 255, 255, 0))
	shadow_img.paste((255, 255, 255, 255), (blursize, blursize, w - blursize, h - blursize))
	shadow_img = shadow_img.filter(PIL.ImageFilter.GaussianBlur(blursize // 3))
	shadow_img.paste((255, 255, 255, 255), (blursize, blursize, w - blursize, h - blursize))
	shadow_img = shadow_img.filter(PIL.ImageFilter.GaussianBlur(blursize // 3))

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
	font = None
	rendered_title = None
	thumb_file = ''
	thumb_texture = None
	path = ''
	full_path = ''
	isdir = False
	state_file = None
	state_last_update = 0
	last_pos = 0


	def __init__(self, name, path, font):
		self.log.info(f'Created Tile path={path}, name={name}')
		self.name = name
		self.path = path
		self.full_path = os.path.join(path, name)
		self.isdir = os.path.isdir(self.full_path)
		self.font = font

		if not self.isdir:
			self.state_file = os.path.join(self.path, '.fabella', 'state', name)
			self.read_state()

	def update_pos(self, position, force=False):
		self.log.debug(f'Tile {self.name} update_pos({position}, {force})')
		if self.last_pos == position:
			return

		now = time.time()
		if now - self.state_last_update > 5 or abs(self.last_pos - position) > 0.01 or force:
			self.state_last_update = now
			self.last_pos = position
			self.write_state()

	def read_state(self):
		self.log.info(f'Reading state for {self.name}')
		try:
			with open(self.state_file) as fd:
				self.last_pos = float(fd.read())
		except FileNotFoundError:
			pass

	def write_state(self):
		self.log.info(f'Writing state for {self.name}')
		os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
		with open(self.state_file, 'w') as fd:
			fd.write(str(self.last_pos) + '\n')

	@property
	def watched(self):
		return self.last_pos >= 0.99

	def find_folder_cover(self, path=None):
		if not path:
			path = self.full_path
		for thumb_file in config.tile.thumb_files:
			thumb_file = os.path.join(path, thumb_file)
			if os.path.isfile(thumb_file):
				return thumb_file
		return None

	def find_file_cover(self):
		for thumb_dir in config.tile.thumb_dirs:
			thumb_file = os.path.join(self.path, thumb_dir, os.path.splitext(self.name)[0] + '.jpg')
			if os.path.isfile(thumb_file):
				return thumb_file
		return None

	def render(self):
		self.log.info(f'Rendering for {self.name}')
		assert self.rendered_title is None
		assert self.thumb_texture is None

		# Title
		if self.isdir:
			name = self.name + '/'
			self.thumb_file = self.find_folder_cover()
		else:
			name = os.path.splitext(self.name)[0]
			self.thumb_file = self.find_file_cover()

		if not self.thumb_file:
			path = self.full_path
			while len(path) > 2 and not self.thumb_file:
				print(path)
				path = os.path.dirname(path)
				self.thumb_file = self.find_folder_cover(path)

		if self.thumb_file:
			self.thumb_texture = self.load_thumbnail(self.thumb_file)

		self.rendered_title = self.font.multiline(name, config.tile.width, config.tile.text_height, None)

	def load_thumbnail(self, thumb_file):
		if thumb_file is None:
			return None

		self.log.info(f'Loading thumbnail from {thumb_file}')
		from PIL import Image, ImageOps
		thumb_full = Image.open(thumb_file)
		thumb = ImageOps.fit(thumb_full, (config.tile.width, config.tile.thumb_height))
		del thumb_full

		# FIXME: properly detect image format (RGB8 etc)
		texture = gl.glGenTextures(1)
		gl.glBindTexture(gl.GL_TEXTURE_2D, texture)
		gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
		gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR)
		gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGB, config.tile.width, config.tile.thumb_height, 0, gl.GL_RGB, gl.GL_UNSIGNED_BYTE, thumb.tobytes())
		gl.glBindTexture(gl.GL_TEXTURE_2D, 0)
		del thumb

		return texture

	def draw(self, x, y, selected=False):
		# Drop shadow
		x1, y1, x2, y2 = x - blursize, y - config.tile.thumb_height - blursize, x + config.tile.width + blursize, y + blursize
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
		# outline
		x1, y1, x2, y2 = x - 2, y - config.tile.thumb_height - 2, x + config.tile.width + 2, y + 2
		gl.glColor4f(*config.tile.shadow_color)
		gl.glBegin(gl.GL_QUADS); gl.glVertex2f(x1, y1); gl.glVertex2f(x2, y1); gl.glVertex2f(x2, y2); gl.glVertex2f(x1, y2); gl.glEnd()

		# Thumbnail
		x1, y1, x2, y2 = x, y - config.tile.thumb_height, x + config.tile.width, y
		if self.thumb_texture is not None:
			gl.glColor4f(1, 1, 1, 1)
			gl.glBindTexture(gl.GL_TEXTURE_2D, self.thumb_texture)
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
			#gl.glColor4f(color, 0, 0, 1)
			#gl.glBegin(gl.GL_QUADS); gl.glVertex2f(x1, y1); gl.glVertex2f(x2, y1); gl.glVertex2f(x2, y2); gl.glVertex2f(x1, y2); gl.glEnd()
			pass

		# Position bar
		x1, y1 = x, y - config.tile.thumb_height - 1 - config.tile.pos_bar_height
		x2, y2 = x1 + config.tile.width * self.last_pos, y1 + config.tile.pos_bar_height
		gl.glColor4f(*config.tile.pos_bar_color)
		gl.glBegin(gl.GL_QUADS); gl.glVertex2f(x1, y1); gl.glVertex2f(x2, y1); gl.glVertex2f(x2, y2); gl.glVertex2f(x1, y2); gl.glEnd()

		# Title
		if self.rendered_title is not None:
			x1, y1 = x, y - config.tile.thumb_height - config.tile.text_vspace - self.rendered_title.height
			x2, y2 = x1 + self.rendered_title.width, y1 + self.rendered_title.height
			if selected:
				gl.glColor4f(*config.tile.text_hl_color)
			else:
				gl.glColor4f(*config.tile.text_color)
			gl.glBindTexture(gl.GL_TEXTURE_2D, self.rendered_title.texture)
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
		if self.rendered_title is not None:
			gl.glDeleteTextures([self.rendered_title.texture])
		if self.thumb_texture is not None:
			gl.glDeleteTextures([self.thumb_texture])

	def __str__(self):
		return f'Tile(name={self.name}, isdir={self.isdir}, last_pos={self.last_pos}, rendered={self.rendered_title})'
