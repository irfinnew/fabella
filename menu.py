import os  # FIXME
import OpenGL.GL as gl

from logger import Logger
from tile import Tile
from font import Font

class Menu:
	log = Logger(module='Menu', color=Logger.Cyan)
	enabled = False
	path = None
	tiles = []
	current_idx = 0
	current_offset = 0
	font = None

	tile_width = 256
	tile_hspace = 64
	tile_height = 144
	tile_vspace = 64
	text_margin = 8
	text_width = 256
	text_height = 48

	def __init__(self, path='/', enabled=False):
		self.log.info(f'Created instance, path={path}, enabled={enabled}')
		self.font = Font('DejaVuSans', 19, stroke_width=2)
		self.load(path)
		self.enabled = enabled

	def open(self):
		self.log.info('Opening Menu')
		self.enabled = True

	def close(self):
		self.log.info('Closing Menu')
		self.enabled = False

	def load(self, path):
		self.forget()
		self.log.info(f'Loading {path}')

		self.path = path
		self.tiles = []
		for f in sorted(os.listdir(self.path)):
			if not f.startswith('.'):
				self.tiles.append(Tile(f, path, self.font))
		self.current_idx = 0
		self.current_offset = 0
		for i, tile in enumerate(self.tiles):
			if tile.last_pos < 0.999:
				self.current_idx = i
				break

	def forget(self):
		self.log.info('Forgetting tiles')
		for tile in self.tiles:
			tile.destroy()
		self.tiles = []
		self.current_idx = None

	@property
	def current(self):
		return self.tiles[self.current_idx]

	def up(self):
		self.log.info('Select above')
		if self.current_idx >= self.htiles:
			self.current_idx -= self.htiles

	def down(self):
		self.log.info('Select below')
		if self.current_idx < len(self.tiles) - self.htiles:
			self.current_idx += self.htiles

	def left(self):
		self.log.info('Select left')
		if self.current_idx > 0:
			self.current_idx -= 1
		#else:
		#	self.current_idx = len(self.tiles) - 1

	def right(self):
		self.log.info('Select right')
		if self.current_idx < len(self.tiles) - 1:
			self.current_idx += 1
		#else:
		#	self.current_idx = 0

	def enter(self, video):
		self.log.info('Enter')
		tile = self.current
		if tile.isdir:
			self.load(tile.path)
		else:
			self.play(tile, video)

	def play(self, tile, video):
		self.log.info(f'Play; (currently {video.tile})')
		if tile is not video.tile:
			# Not already playing this
			self.log.info(f'Starting new video: {tile}')
			video.start(tile.path, menu=self, tile=tile)
		else:
			self.log.info('Already playing this video, NOP')
		self.close()

	def back(self):
		self.log.info('Back')
		new = os.path.dirname(self.path)
		if not new:
			return
		previous = os.path.basename(self.path)
		self.load(new)
		for i, tile in enumerate(self.tiles):
			if tile.name == previous:
				self.current_idx = i
				break

	def draw(self, width, height):
		# Background
		x1, y1, x2, y2 = 0, 0, width, height
		gl.glColor4f(0, 0, 0, 0.66)
		gl.glBegin(gl.GL_QUADS); gl.glVertex2f(x1, y1); gl.glVertex2f(x2, y1); gl.glVertex2f(x2, y2); gl.glVertex2f(x1, y2); gl.glEnd()

		# Render at most one tile per frame
		for tile in self.tiles:
			if tile.rendered is None:
				tile.render(self.text_width, self.text_height)
				break

		# draw tiles
		htiles = width // (self.tile_width + self.tile_hspace)
		self.htiles = htiles  # FIXME: ughhh
		hoffset = (width - htiles * (self.tile_width + self.tile_hspace) + self.tile_hspace) // 2
		vtiles = height // (self.tile_height + self.tile_vspace + self.text_height + self.text_margin)
		voffset = (height - vtiles * (self.tile_height + self.text_height + self.tile_vspace + self.text_margin) + self.tile_vspace) // 2

		# Fix offset
		while self.current_idx // htiles < self.current_offset:
			self.current_offset -= 1

		while self.current_idx // htiles >= (self.current_offset + vtiles):
			self.current_offset += 1

		if self.current_offset > (len(self.tiles) - 1) // htiles + 1 - vtiles:
			self.current_offset = (len(self.tiles) - 1) // htiles + 1 - vtiles

		if self.current_offset < 0:
			self.current_offset = 0

		for y in range(vtiles):
			for x in range(htiles):
				idx = y * htiles + x + self.current_offset * htiles
				try:
					tile = self.tiles[idx]
				except IndexError:
					break
				if tile.rendered:
					xpos = hoffset + (self.tile_width + self.tile_hspace) * x
					ypos = height - (voffset + (self.tile_height + self.text_height + self.text_margin + self.tile_vspace) * y) - self.text_height - self.text_margin - self.tile_height
					# FIXME
					x1, y1, x2, y2 = xpos, ypos + self.text_height + self.text_margin, xpos + self.tile_width, ypos + self.text_height + self.tile_height
					gl.glColor4f(0.5, 0, 0, 1)
					gl.glBegin(gl.GL_QUADS); gl.glVertex2f(x1, y1); gl.glVertex2f(x2, y1); gl.glVertex2f(x2, y2); gl.glVertex2f(x1, y2); gl.glEnd()
					tile.draw(xpos, ypos, selected=idx == self.current_idx)
