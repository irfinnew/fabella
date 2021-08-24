import os  # FIXME
import OpenGL.GL as gl

import config
from logger import Logger
from tile import Tile
from font import Font

class Menu:
	log = Logger(module='Menu', color=Logger.Cyan)
	enabled = False
	path = None
	tiles = []
	tiles_per_row = 1
	current_idx = 0
	current_offset = 0
	font = None

	def __init__(self, path='/', enabled=False):
		self.log.info(f'Created instance, path={path}, enabled={enabled}')
		self.font = Font('DejaVuSans', 20, stroke_width=2)
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
			if f.startswith('.'):
				continue
			if f in config.tile.thumb_dirs:
				continue
			if f in config.tile.thumb_files:
				continue
			self.tiles.append(Tile(f, path, self.font))
		self.current_idx = 0
		self.current_offset = 0
		for i, tile in enumerate(self.tiles):
			if not tile.watched:
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
		if self.current_idx >= self.tiles_per_row:
			self.current_idx -= self.tiles_per_row

	def down(self):
		self.log.info('Select below')
		if self.current_idx // self.tiles_per_row < (len(self.tiles) - 1) // self.tiles_per_row:
			self.current_idx = min(
				len(self.tiles) - 1,
				self.current_idx + self.tiles_per_row
			)

	def left(self):
		self.log.info('Select left')
		if self.current_idx > 0:
			self.current_idx -= 1

	def right(self):
		self.log.info('Select right')
		if self.current_idx < len(self.tiles) - 1:
			self.current_idx += 1

	def enter(self, video):
		self.log.info('Enter')
		tile = self.current
		if tile.isdir:
			self.load(tile.full_path)
		else:
			self.play(tile, video)

	def play(self, tile, video):
		self.log.info(f'Play; (currently {video.tile})')
		if tile is not video.tile:
			self.log.info(f'Starting new video: {tile}')
			video.start(tile.full_path, menu=self, tile=tile)
		else:
			self.log.info('Already playing this video, just maybe unpause')
			video.pause(False)
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
			if tile.rendered_title is None:
				tile.render()
				break

		tile_width = config.tile.width
		tile_hspace = config.tile.min_hspace
		tile_htotal = tile_width + tile_hspace

		tile_height = config.tile.thumb_height + config.tile.text_vspace + config.tile.text_height
		tile_vspace = config.tile.min_vspace
		tile_vtotal = tile_height + tile_vspace

		tiles_per_row = max(width // tile_htotal, 1)
		tile_hoffset = (width - tiles_per_row * tile_htotal + tile_hspace) // 2
		# Hmm, this is kinda dirty. But I need this in other places.
		self.tiles_per_row = tiles_per_row

		tile_rows = max(height // tile_vtotal, 1)
		tile_voffset = (height - tile_rows * tile_vtotal + tile_vspace) // 2

		# Fix offset
		while self.current_idx // tiles_per_row < self.current_offset:
			self.current_offset -= 1

		while self.current_idx // tiles_per_row >= (self.current_offset + tile_rows):
			self.current_offset += 1

		if self.current_offset > (len(self.tiles) - 1) // tiles_per_row + 1 - tile_rows:
			self.current_offset = (len(self.tiles) - 1) // tiles_per_row + 1 - tile_rows

		if self.current_offset < 0:
			self.current_offset = 0

		for y in range(tile_rows):
			for x in range(tiles_per_row):
				idx = y * tiles_per_row + x + self.current_offset * tiles_per_row
				try:
					tile = self.tiles[idx]
				except IndexError:
					break
				tile.draw(tile_hoffset + x * tile_htotal, height - tile_voffset - y * tile_vtotal, idx == self.current_idx)
