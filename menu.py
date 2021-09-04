import os  # FIXME
import OpenGL.GL as gl
import datetime
import json

import config
from logger import Logger
from tile import Tile
from font import Font

class Menu:
	log = Logger(module='Menu', color=Logger.Cyan)
	enabled = False
	state_file = None
	state = None
	path = None
	tiles = []
	tiles_per_row = 1
	current_idx = 0
	current_offset = 0
	menu_font = None
	tile_font = None
	breadcrumbs = []
	bread_text = None
	clock_text = None

	def __init__(self, path='/', enabled=False):
		self.log.info(f'Created instance, path={path}, enabled={enabled}')
		self.tile_font = Font('DejaVuSans', config.tile.text_size, stroke_width=3)
		self.menu_font = Font('DejaVuSans', config.menu.text_size, stroke_width=4)
		self.load(path)
		self.enabled = enabled

		self.bread_text = self.menu_font.text(None)
		self.clock_text = self.menu_font.text(None)

	def open(self):
		self.log.info('Opening Menu')
		self.enabled = True

	def close(self):
		self.log.info('Closing Menu')
		self.enabled = False

	def load(self, path):
		self.forget()
		self.log.info(f'Loading {path}')
		# BENCHMARK
		import time
		self.bench = time.time()

		self.state_file = os.path.join(path, '.fabella', 'state.json')
		os.makedirs(os.path.dirname(self.state_file), exist_ok=True)

		try:
			with open(self.state_file) as fd:
				self.state = json.load(fd)
		except FileNotFoundError:
			self.state = {}

		self.path = path
		self.tiles = []
		for f in sorted(os.listdir(self.path)):
			if f.startswith('.'):
				continue
			if f in config.tile.thumb_dirs:
				continue
			if f in config.tile.thumb_files:
				continue
			self.tiles.append(Tile(f, path, self, self.tile_font, self.state.get(f)))
		self.current_idx = 0
		self.current_offset = 0

		# Find first "watching" video
		for i, tile in enumerate(self.tiles):
			if tile.watching:
				self.current_idx = i
				return

		# Otherwise, find first "unseen" video
		for i, tile in enumerate(self.tiles):
			if tile.unseen:
				self.current_idx = i
				return

	def write_state(self, name, new_state):
		self.log.info(f'Writing {self.state_file}')
		self.state[name] = new_state
		with open(self.state_file, 'w') as fd:
			json.dump(self.state, fd, indent=4)

	def forget(self):
		self.log.info('Forgetting tiles')
		for tile in self.tiles:
			tile.destroy()
		self.tiles = []
		self.current_idx = None

	@property
	def current(self):
		return self.tiles[self.current_idx]

	def previous_row(self):
		self.log.info('Select previous row')
		if self.current_idx >= self.tiles_per_row:
			self.current_idx -= self.tiles_per_row

	def next_row(self):
		self.log.info('Select next row')
		if self.current_idx // self.tiles_per_row < (len(self.tiles) - 1) // self.tiles_per_row:
			self.current_idx = min(
				len(self.tiles) - 1,
				self.current_idx + self.tiles_per_row
			)

	def previous(self):
		self.log.info('Select previous')
		if self.current_idx > 0:
			self.current_idx -= 1

	def next(self):
		self.log.info('Select next')
		if self.current_idx < len(self.tiles) - 1:
			self.current_idx += 1

	def toggle_seen(self):
		self.current.toggle_seen()

	def enter(self, video):
		self.log.info('Enter')
		tile = self.current
		if tile.isdir:
			self.breadcrumbs.append(tile.name)
			self.load(tile.full_path)
		else:
			self.play(tile, video)

	def play(self, tile, video):
		self.log.info(f'Play; (currently {video.tile})')
		if tile is not video.tile:
			self.log.info(f'Starting new video: {tile}')
			video.start(tile.full_path, position=tile.position, menu=self, tile=tile)
		else:
			self.log.info('Already playing this video, just maybe unpause')
			video.pause(False)
		self.close()

	def back(self):
		self.log.info('Back')
		self.breadcrumbs.pop()
		new = os.path.dirname(self.path)
		if not new:
			return
		previous = os.path.basename(self.path)
		self.load(new)
		for i, tile in enumerate(self.tiles):
			if tile.name == previous:
				self.current_idx = i
				break

	def draw(self, width, height, transparent=False):
		# Background
		x1, y1, x2, y2 = 0, 0, width, height
		if transparent:
			gl.glColor4f(0, 0, 0, 0.66)
		else:
			gl.glColor4f(*config.menu.background_color)
		gl.glBegin(gl.GL_QUADS); gl.glVertex2f(x1, y1); gl.glVertex2f(x2, y1); gl.glVertex2f(x2, y2); gl.glVertex2f(x1, y2); gl.glEnd()

		# Breadcrumbs
		breadcrumbs = ' › '.join(['Home'] + self.breadcrumbs)
		self.bread_text.set_text(breadcrumbs)

		if self.bread_text.texture():
			x1, y1 = config.menu.header_hspace, height - config.menu.header_vspace - self.bread_text.height
			x2, y2 = x1 + self.bread_text.width, y1 + self.bread_text.height
			gl.glColor4f(1, 1, 1, 1)
			gl.glBindTexture(gl.GL_TEXTURE_2D, self.bread_text.texture())
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

		# Clock
		self.clock_text.set_text(datetime.datetime.now().strftime('%H:%M:%S'))

		if self.clock_text.texture():
			x1, y1 = width - config.menu.header_hspace - self.clock_text.width, height - config.menu.header_vspace - self.clock_text.height
			x2, y2 = x1 + self.clock_text.width, y1 + self.clock_text.height
			gl.glColor4f(1, 1, 1, 1)
			gl.glBindTexture(gl.GL_TEXTURE_2D, self.clock_text.texture())
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

		# Render at most X tiles per frame
		count = 0
		for tile in self.tiles:
			if not tile.rendered:
				tile.render()
				count += 1
				if count > 9:
					break
		else:
			# BENCHMARK
			if self.bench:
				import time
				self.log.warning(f'Finished rendering in {time.time() - self.bench} seconds')
				self.bench = None

		tile_width = config.tile.width
		tile_hspace = config.tile.min_hspace
		tile_htotal = tile_width + tile_hspace

		tile_height = config.tile.thumb_height + config.tile.text_vspace + config.tile.text_size * config.tile.text_lines
		tile_vspace = config.tile.min_vspace
		tile_vtotal = tile_height + tile_vspace

		tiles_per_row = max(width // tile_htotal, 1)
		tile_hoffset = (width - tiles_per_row * tile_htotal + tile_hspace) // 2
		# Hmm, this is kinda dirty. But I need this in other places.
		self.tiles_per_row = tiles_per_row

		# FIXME: yuck
		height -= int(config.menu.header_vspace + config.menu.text_size)
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
