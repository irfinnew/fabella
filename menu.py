#! /usr/bin/env python3

import os  # FIXME
import PIL.Image, PIL.ImageDraw, PIL.ImageFont  # FIXME
import OpenGL.GL as gl

from logger import Logger
from tile import Tile

class Menu:
	log = Logger(module='Menu', color=Logger.Cyan)
	enabled = False
	path = None
	tiles = []
	current_idx = 0
	font = None

	def __init__(self, path='/', enabled=False):
		self.log.info(f'Created instance, path={path}, enabled={enabled}')
		self.font = PIL.ImageFont.truetype('DejaVuSans', 35)
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
		if self.current_idx > 0:
			self.current_idx -= 1
		else:
			self.current_idx = len(self.tiles) - 1

	def down(self):
		self.log.info('Select below')
		if self.current_idx < len(self.tiles) - 1:
			self.current_idx += 1
		else:
			self.current_idx = 0

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
		x1, y1, x2, y2 = 0, 0, width, height
		gl.glColor4f(0, 0, 0, 0.66)
		gl.glBegin(gl.GL_QUADS); gl.glVertex2f(x1, y1); gl.glVertex2f(x2, y1); gl.glVertex2f(x2, y2); gl.glVertex2f(x1, y2); gl.glEnd()

		line_height = 50
		num_lines = height // line_height + 2
		if num_lines % 2 == 0:
			num_lines -= 1
		cx = width // 2
		cy = height // 2

		# Render at most one tile per frame
		for tile in self.tiles:
			if tile.texture is None:
				tile.render()
				break

		for i in range(-(num_lines // 2), num_lines // 2 + 1):
			idx = self.current_idx + i
			if idx < 0 or idx >= len(self.tiles):
				continue

			tile = self.tiles[idx]
			ypos = cy - i * line_height - tile.height // 2

			tile.draw(cx - tile.width // 2, ypos, selected=i == 0)
