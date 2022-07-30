import os  # FIXME
import datetime
import time
import uuid
import zipfile

import loghelper
import config
import dbs
import draw
from tile import Tile
from font import Font
from worker import Pool
from image import ImgLib



log = loghelper.get_logger('Menu', loghelper.Color.Cyan)



class Menu:
	def __init__(self, path, width, height, enabled=False):
		log.info(f'Created instance, path={path}, enabled={enabled}')

		self.tile_font = Font(config.tile.text_font, config.tile.text_size)
		self.menu_font = Font(config.menu.text_font, config.menu.text_size)
		self.width = width
		self.height = height
		self.enabled = False
		self.root = path
		self.path = None
		self.current_idx = 0
		self.current_offset = 0
		self.index = []
		self.tiles = {}
		self.covers_zip = None
		self.background = draw.FlatQuad(z=100, w=width, h=height, color=config.menu.background_color)
		self.breadcrumbs = []
		self.bread_text = self.menu_font.text(z=101, text='', anchor='tl',
			pos=(config.menu.header_hspace, height - config.menu.header_vspace),
		)
		self.clock_text = self.menu_font.text(z=101, text='clock', anchor='tr',
			pos=(width - config.menu.header_hspace, height - config.menu.header_vspace),
		)

		# FIXME: this entire section is yuck
		tile_width = config.tile.width
		tile_hspace = config.tile.min_hspace
		tile_htotal = tile_width + tile_hspace

		tile_height = config.tile.thumb_height + config.tile.text_vspace + int(config.tile.text_size * 1.65) * config.tile.text_lines
		tile_vspace = config.tile.min_vspace
		tile_vtotal = tile_height + tile_vspace

		tile_columns = max(width // tile_htotal, 1)
		tile_hoffset = (width - tile_columns * tile_htotal + tile_hspace) // 2
		self.tile_columns = tile_columns
		self.tile_hstart = tile_hoffset
		self.tile_hoffset = tile_htotal

		height -= int(config.menu.header_vspace + config.menu.text_size * 1.65)
		tile_rows = max(height // tile_vtotal, 1)
		tile_voffset = (height - tile_rows * tile_vtotal) // 2 + tile_vspace

		self.tile_rows = tile_rows
		self.tile_vstart = tile_voffset
		self.tile_vstart = int(config.menu.header_vspace + config.menu.text_size * 1.65) + (height - tile_rows * tile_vtotal) // 2 + tile_vspace
		self.tile_voffset = tile_vtotal
		# FIXME: end yuck

		self.load(path)
		self.open(enabled)


	def tick(self):
		self.clock_text.text = datetime.datetime.now().strftime('%a %H:%M:%S')


	def close(self):
		if not self.enabled:
			return

		self.enabled = False
		for t in self.tiles.values():
			t.destroy()
		self.tiles = {}
		#self.background.hidden = True
		draw.Animation(self.background, duration=1.0, delay=0.25, opacity=(1, 0))
		self.bread_text.quad.hidden = True
		self.clock_text.quad.hidden = True


	def open(self, enabled=True):
		if not enabled:
			return self.close()

		if self.enabled:
			return

		self.enabled = True
		#self.background.hidden = False
		draw.Animation(self.background, duration=1, opacity=(0, 1))
		self.bread_text.quad.hidden = False
		self.clock_text.quad.hidden = False
		self.draw_tiles()


	def forget(self):
		for t in self.tiles.values():
			t.destroy()
		self.tiles = {}
		self.index = []
		self.current_idx = 0
		self.current_offset = 0
		self.covers_zip = None


	def load(self, path):
		self.forget()
		log.info(f'Loading {path}')
		self.path = path
		timer = time.time()

		index_db_name = os.path.join(path, dbs.INDEX_DB_NAME)
		index = dbs.json_read(index_db_name, dbs.INDEX_DB_SCHEMA, default=None)

		if index is None:
			log.warning(f'falling back to scandir()')
			index = []
			for isfile, name in sorted((not de.is_dir(), de.name) for de in os.scandir(path)):
				if not name.startswith('.') and name.endswith(dbs.VIDEO_EXTENSIONS):
					index.append({'name': name, 'isdir': not isfile})
			self.index = index
			return

		state_db_name = os.path.join(path, dbs.STATE_DB_NAME)
		state = dbs.json_read(state_db_name, dbs.STATE_DB_SCHEMA)

		index = index['files']
		for entry in index:
			entry.update(state.get(entry['name'], {}))
		self.index = index

		# Open cover DB
		cover_db_name = os.path.join(self.path, '.fabella', 'covers.zip')
		try:
			self.covers_zip = zipfile.ZipFile(cover_db_name, 'r')
		except OSError as e:
			self.covers_zip = None
			log.error(f'Parsing cover DB {cover_db_name}: {e}')

		# Find first "watching" video
		index = 0
		for i, tile in enumerate(self.index):
			if 0.0 < tile.get('position', 0.0) < 1.0:
				index = i
				break
		else:
			# Otherwise find the first "unseen" video
			for i, tile in enumerate(self.index):
				if tile.get('position', 0.0) == 0.0:
					index = i
					break

		timer = int((time.time() - timer) * 1000)
		log.info(f'Loaded tiles in {timer}ms')

		# This will also draw
		self.jump_tile(index)


	# FIXME: are we using this?
	@property
	def current(self):
		return self.tiles[self.current_idx]


	def jump_tile(self, idx):
		log.debug(f'Jumping to tile {idx}')
		self.current_idx = min(max(idx, 0), len(self.index) - 1)

		# Fix offset
		while self.current_idx // self.tile_columns < self.current_offset:
			self.current_offset -= 1

		while self.current_idx // self.tile_columns >= (self.current_offset + self.tile_rows):
			self.current_offset += 1

		if self.current_offset > (len(self.index) - 1) // self.tile_columns + 1 - self.tile_rows:
			self.current_offset = (len(self.index) - 1) // self.tile_columns + 1 - self.tile_rows

		if self.current_offset < 0:
			self.current_offset = 0

		self.draw_tiles()


	def previous(self):
		log.info('Select previous')
		self.jump_tile(self.current_idx - 1)


	def next(self):
		log.info('Select next')
		self.jump_tile(self.current_idx + 1)


	def previous_row(self):
		log.info('Select previous row')
		if self.current_idx >= self.tile_columns:
			self.jump_tile(self.current_idx - self.tile_columns)


	def next_row(self):
		log.info('Select next row')
		if self.current_idx // self.tile_columns < (len(self.index) - 1) // self.tile_columns:
			self.jump_tile(self.current_idx + self.tile_columns)


	def page_up(self):
		log.info('Select page up')
		self.jump_tile(self.current_idx - self.tile_columns * self.tile_rows)


	def page_down(self):
		log.info('Select page down')
		self.jump_tile(self.current_idx + self.tile_columns * self.tile_rows)


	def first(self):
		log.info('Select first tile')
		self.jump_tile(0)


	def last(self):
		log.info('Select last tile')
		self.jump_tile(len(self.index))


	def toggle_seen(self):
		self.current.toggle_seen()


	def toggle_seen_all(self):
		# FIXME: this needs complete revamp prolly
		position = 1 if any(t.unseen and not t.isdir for t in self.tiles) else 0
		state = {}
		for tile in self.tiles:
			if not tile.isdir:
				tile.position = position
				state[tile.name] = {'position': position}

		update_name = os.path.join(self.path, dbs.QUEUE_DIR_NAME, str(uuid.uuid4()))
		dbs.json_write(update_name, state)


	def toggle_tagged(self):
		self.current.toggle_tagged()


	def enter(self, video):
		log.info('Enter')
		tile = self.current
		if tile.isdir:
			self.breadcrumbs.append(tile.name)
			self.bread_text.text = '  ›  '.join(self.breadcrumbs)
			self.load(tile.full_path)
		else:
			self.play(tile, video)


	def play(self, tile, video):
		log.info(f'Play; (currently {video.tile})')
		if tile is not video.tile:
			log.info(f'Starting new video: {tile}')
			video.start(tile.full_path, position=tile.position, menu=self, tile=tile)
		else:
			log.info('Already playing this video, just maybe unpause')
			video.pause(False)
		# FIXME: hack
		the_tile = self.tiles.pop(self.current_idx)
		the_tile.animate_blowup(self.width / 2, self.height / 2)
		self.close()


	def back(self):
		log.info('Back')
		try:
			self.breadcrumbs.pop()
			self.bread_text.text = '  ›  '.join(self.breadcrumbs)
		except IndexError:
			log.info("Hit root, not going up.")
			return

		previous = os.path.basename(self.path)
		self.load(os.path.dirname(self.path))

		# Find the tile that was used to enter the previous path
		for idx, meta in enumerate(self.index):
			if meta['name'] == previous:
				self.jump_tile(idx)
				break


	def draw_tiles(self):
		timer = time.time()

		for tile in self.tiles.values():
			tile.used = False

		for y in range(self.tile_rows):
			for x in range(self.tile_columns):
				idx = (y + self.current_offset) * self.tile_columns + x
				if idx >= len(self.index):
					break
				try:
					tile = self.tiles[idx]
				except KeyError:
					tile = Tile(self, self.index[idx], self.covers_zip)
				tile.show(
					(self.tile_hstart + x * self.tile_hoffset - Tile.xoff,
					self.height - self.tile_vstart - y * self.tile_voffset - config.tile.thumb_height - Tile.yoff),
					idx == self.current_idx
				)
				self.tiles[idx] = tile
				tile.used = True

		for idx, tile in dict(self.tiles).items():
			if not tile.used:
				tile.destroy()
				del self.tiles[idx]

		timer = int((time.time() - timer) * 1000)
		log.info(f'Drew tiles in {timer}ms')
