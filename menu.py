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
		self.tiles = []
		self.shown_tiles = set()
		self.background = draw.FlatQuad(0, 0, 1, 1, 0, (0, 0, 0, 0.66))
		self.breadcrumbs = []
		self.bread_text = self.menu_font.text(config.menu.header_hspace, height - config.menu.header_vspace, 101, 'breadcrumbs', anchor='tl')
		self.clock_text = self.menu_font.text(width - config.menu.header_hspace, height - config.menu.header_vspace, 101, 'clock', anchor='tr')

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


	def close(self):
		self.enabled = False
		for t in tiles:
			t.hide()


	def open(self, enabled=True):
		if not enabled:
			return self.close()

		self.enabled = True
		self.draw_tiles()


	def forget(self):
		for t in self.tiles:
			t.hide()
		self.tiles = []


	def load(self, path):
		self.forget()
		log.info(f'Loading {path}')

		state_db_name = os.path.join(path, dbs.STATE_DB_NAME)
		state = dbs.json_read(state_db_name, dbs.STATE_DB_SCHEMA)

		index_db_name = os.path.join(path, dbs.INDEX_DB_NAME)
		index = dbs.json_read(index_db_name, dbs.INDEX_DB_SCHEMA, default=None)
		if index is None:
			log.warning(f'falling back to scandir()')
			index = []
			for isfile, name in sorted((not de.is_dir(), de.name) for de in os.scandir(path)):
				if not name.startswith('.') and name.endswith(dbs.VIDEO_EXTENSIONS):
					index.append({'name': name, 'isdir': not isfile})
		else:
			index = index['files']

		self.path = path
		for entry in index:
			name = entry['name']
			isdir = entry['isdir']
			self.tiles.append(Tile(path, name, isdir, self, self.tile_font))

		for tile, entry in zip(self.tiles, index):
			meta = {**entry, **state.get(tile.name, {})}
			tile.update_meta(meta)

		self.load_covers()

		self.current_idx = 0
		self.current_offset = 0

		# Find first "watching" video
		for i, tile in enumerate(self.tiles):
			if tile.watching:
				self.current_idx = i
				break
		else:
			# Otherwise, find first "unseen" video
			for i, tile in enumerate(self.tiles):
				if tile.unseen:
					self.current_idx = i
					break

		self.draw_tiles()


	def load_covers(self):
		start = time.time()
		cover_db_name = os.path.join(self.path, '.fabella', 'covers.zip')
		try:
			with zipfile.ZipFile(cover_db_name, 'r') as fd:
				for tile in self.tiles:
					tile.update_cover(fd)
		except OSError as e:
			log.error(f'Parsing cover DB {cover_db_name}: {e}')


	@property
	def current(self):
		return self.tiles[self.current_idx]


	def previous_row(self):
		log.info('Select previous row')
		if self.current_idx >= self.tile_columns:
			self.current_idx -= self.tile_columns
		self.draw_tiles()


	def next_row(self):
		log.info('Select next row')
		if self.current_idx // self.tile_columns < (len(self.tiles) - 1) // self.tile_columns:
			self.current_idx = min(
				len(self.tiles) - 1,
				self.current_idx + self.tile_columns
			)
		self.draw_tiles()


	def previous(self):
		log.info('Select previous')
		if self.current_idx > 0:
			self.current_idx -= 1
		self.draw_tiles()


	def next(self):
		log.info('Select next')
		if self.current_idx < len(self.tiles) - 1:
			self.current_idx += 1
		self.draw_tiles()


	def toggle_seen(self):
		self.current.toggle_seen()


	def toggle_seen_all(self):
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
		self.close()


	def back(self):
		log.info('Back')
		try:
			self.breadcrumbs.pop()
			self.bread_text.text = '  ›  '.join(self.breadcrumbs)
		except IndexError:
			log.info("Hit root, not going up.")
			return

		new = os.path.dirname(self.path)
		if not new:
			return
		previous = os.path.basename(self.path)
		self.load(new)
		for i, tile in enumerate(self.tiles):
			if tile.name == previous:
				self.current_idx = i
				break


	def draw_tiles(self):
		# Fix offset
		while self.current_idx // self.tile_columns < self.current_offset:
			self.current_offset -= 1

		while self.current_idx // self.tile_columns >= (self.current_offset + self.tile_rows):
			self.current_offset += 1

		if self.current_offset > (len(self.tiles) - 1) // self.tile_columns + 1 - self.tile_rows:
			self.current_offset = (len(self.tiles) - 1) // self.tile_columns + 1 - self.tile_rows

		if self.current_offset < 0:
			self.current_offset = 0

		new_tiles = set()
		for y in range(self.tile_rows):
			for x in range(self.tile_columns):
				idx = (y + self.current_offset) * self.tile_columns + x
				try:
					tile = self.tiles[idx]
				except IndexError:
					break
				tile.show(
					self.tile_hstart + x * self.tile_hoffset,
					self.height - self.tile_vstart - y * self.tile_voffset,
					idx == self.current_idx
				)
				new_tiles.add(tile)

		for tile in self.shown_tiles - new_tiles:
			tile.hide()

		self.shown_tiles = new_tiles

		# FIXME: put somewhere else
		self.clock_text.text = datetime.datetime.now().strftime('%a %H:%M:%S')
