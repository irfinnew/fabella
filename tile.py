import os
import time
import OpenGL.GL as gl

from logger import Logger
from config import Config

class Tile:
	log = Logger(module='Tile', color=Logger.Magenta)
	name = ''
	font = None
	rendered = None
	path = ''
	isdir = False
	state_file = None
	state_last_update = 0
	last_pos = 0

	def __init__(self, name, path, font):
		self.log.info(f'Created Tile path={path}, name={name}')
		self.name = name
		self.path = os.path.join(path, name)
		self.isdir = os.path.isdir(self.path)
		self.font = font

		if not self.isdir:
			self.state_file = os.path.join(path, '.fabella', 'state', name)
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

	def render(self):
		self.log.info(f'Rendering for {self.name}')
		name = self.name
		if self.isdir:
			name = name + '/'

		texture = self.rendered.texture if self.rendered else None
		self.rendered = self.font.multiline(name, Config.tile_size[0], Config.tile_text_height, texture)

	def draw(self, x, y, selected=False):
		if self.rendered is None:
			return

		# FIXME
		color = 1.0 if selected else (0.4 if self.watched else 0.7)

		# Thumbnail
		x1, y1, x2, y2 = x, y - Config.tile_size[1], x + Config.tile_size[0], y
		gl.glColor4f(color, 0, 0, 1)
		gl.glBegin(gl.GL_QUADS); gl.glVertex2f(x1, y1); gl.glVertex2f(x2, y1); gl.glVertex2f(x2, y2); gl.glVertex2f(x1, y2); gl.glEnd()

		# Pos bar
		pos_bar_height = 2  # FIXME
		x1, y1 = x, y - Config.tile_size[1] - 1 - pos_bar_height
		x2, y2 = x1 + Config.tile_size[0] * self.last_pos, y1 + pos_bar_height
		gl.glColor4f(0.4, 0.4, 1, 1)
		gl.glBegin(gl.GL_QUADS); gl.glVertex2f(x1, y1); gl.glVertex2f(x2, y1); gl.glVertex2f(x2, y2); gl.glVertex2f(x1, y2); gl.glEnd()

		# Title
		x1, y1 = x, y - Config.tile_size[1] - Config.tile_margin[1] - self.rendered.height
		x2, y2 = x1 + self.rendered.width, y1 + self.rendered.height
		gl.glColor4f(color, color, color, 1)
		gl.glBindTexture(gl.GL_TEXTURE_2D, self.rendered.texture)
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
		if self.rendered is not None:
			gl.glDeleteTextures([self.rendered.texture])

	def __str__(self):
		return f'Tile(name={self.name}, isdir={self.isdir}, last_pos={self.last_pos}, rendered={self.rendered})'
