import os  # FIXME
import OpenGL.GL as gl
import datetime
import time
import uuid
import zipfile

import loghelper
import config
import dbs
from tile import Tile
from font import Font
from worker import Pool
from image import ImgLib



log = loghelper.get_logger('Menu', loghelper.Color.Cyan)



class Menu:
	enabled = False
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
		log.info(f'Created instance, path={path}, enabled={enabled}')

		# FIXME: number of threads
		self.render_pool = Pool('render', threads=3)
		self.tile_pool = Pool('tile', threads=1)
		self.tile_font = Font('Ubuntu Medium', config.tile.text_size, stroke_width=3)
		self.menu_font = Font('Ubuntu Medium', config.menu.text_size, stroke_width=4)
		self.load(path)
		self.enabled = enabled

		ImgLib.add('Unseen', 'img/unseen.png', 48, 48, self.render_pool, shadow=(2, 12))
		ImgLib.add('Trash', 'img/error.png', 48, 48, self.render_pool, shadow=(2, 12))
		for i in range(13):
			ImgLib.add(f'Watching{i}', f'img/watching-{i}.png', 48, 48, self.render_pool, shadow=(2, 12))

		self.bread_text = self.menu_font.text(None, pool=self.render_pool)
		self.clock_text = self.menu_font.text(None, pool=self.render_pool)

	def open(self):
		log.info('Opening Menu')
		self.enabled = True

	def close(self):
		log.info('Closing Menu')
		self.enabled = False

	def load(self, path):
		self.forget()
		log.info(f'Loading {path}')
		# BENCHMARK
		self.bench = time.time()

		state_db_name = os.path.join(path, dbs.STATE_DB_NAME)
		state = dbs.json_read(state_db_name, dbs.STATE_DB_SCHEMA)

		start = time.time()
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
		start = int((time.time() - start) * 1000); log.warning(f'Reading index: {start}ms')

		self.path = path
		self.tiles = []
		start = time.time()
		for entry in index:
			name = entry['name']
			isdir = entry['isdir']
			self.tiles.append(Tile(path, name, isdir, self, self.tile_font, self.render_pool))
		start = int((time.time() - start) * 1000); log.warning(f'Creating tiles: {start}ms')

		start = time.time()
		for tile, entry in zip(self.tiles, index):
			meta = {**entry, **state.get(tile.name, {})}
			tile.update_meta(meta)
		start = int((time.time() - start) * 1000); log.warning(f'Updating meta: {start}ms')

		self.tile_pool.schedule(self.load_covers)

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

	def load_covers(self):
		start = time.time()
		cover_db_name = os.path.join(self.path, '.fabella', 'covers.zip')
		try:
			with zipfile.ZipFile(cover_db_name, 'r') as fd:
				for tile in self.tiles:
					tile.update_cover(fd)
		except OSError as e:
			log.error(f'Parsing cover DB {cover_db_name}: {e}')
		start = int((time.time() - start) * 1000); log.warning(f'Updating covers: {start}ms')

	def forget(self):
		log.info('Forgetting tiles')
		self.tile_pool.flush()
		self.render_pool.flush()
		Tile.release_all_textures(self.tiles)
		self.tiles = []
		self.current_idx = None

	@property
	def current(self):
		return self.tiles[self.current_idx]

	def previous_row(self):
		log.info('Select previous row')
		if self.current_idx >= self.tiles_per_row:
			self.current_idx -= self.tiles_per_row

	def next_row(self):
		log.info('Select next row')
		if self.current_idx // self.tiles_per_row < (len(self.tiles) - 1) // self.tiles_per_row:
			self.current_idx = min(
				len(self.tiles) - 1,
				self.current_idx + self.tiles_per_row
			)

	def previous(self):
		log.info('Select previous')
		if self.current_idx > 0:
			self.current_idx -= 1

	def next(self):
		log.info('Select next')
		if self.current_idx < len(self.tiles) - 1:
			self.current_idx += 1

	def toggle_seen(self):
		self.current.toggle_seen()

	def toggle_seen_all(self):
		watched = dbs.WATCHED_MAX if any(t.unseen and not t.isdir for t in self.tiles) else 0
		state = {}
		for tile in self.tiles:
			if not tile.isdir:
				tile.watched = watched
				tile.position = 0
				state[tile.name] = {'watched': watched, 'position': 0}

		update_name = os.path.join(self.path, dbs.QUEUE_DIR_NAME, str(uuid.uuid4()))
		dbs.json_write(update_name, state)

	def toggle_trash(self):
		self.current.toggle_trash()

	def enter(self, video):
		log.info('Enter')
		tile = self.current
		if tile.isdir:
			self.breadcrumbs.append(tile.name)
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

	def draw(self, width, height, transparent=False):
		# FIXME: really not the place for this
		if int(time.time() * 1000) % 97 == 0:
			self.tile_pool.schedule(self.load_covers)

		# Background
		x1, y1, x2, y2 = 0, 0, width, height
		if transparent:
			gl.glColor4f(0, 0, 0, 0.66)
		else:
			gl.glColor4f(*config.menu.background_color)
		gl.glBegin(gl.GL_QUADS); gl.glVertex2f(x1, y1); gl.glVertex2f(x2, y1); gl.glVertex2f(x2, y2); gl.glVertex2f(x1, y2); gl.glEnd()

		# Breadcrumbs
		self.bread_text.text = '  ›  '.join(self.breadcrumbs)

		if self.bread_text.texture:
			x1, y1 = config.menu.header_hspace, height - config.menu.header_vspace - self.bread_text.height
			x2, y2 = x1 + self.bread_text.width, y1 + self.bread_text.height
			gl.glColor4f(1, 1, 1, 1)
			gl.glBindTexture(gl.GL_TEXTURE_2D, self.bread_text.texture)
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
		self.clock_text.text = datetime.datetime.now().strftime('%H:%M:%S')

		if self.clock_text.texture:
			x1, y1 = width - config.menu.header_hspace - self.clock_text.width, height - config.menu.header_vspace - self.clock_text.height
			x2, y2 = x1 + self.clock_text.width, y1 + self.clock_text.height
			gl.glColor4f(1, 1, 1, 1)
			gl.glBindTexture(gl.GL_TEXTURE_2D, self.clock_text.texture)
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

		if self.bench and self.tiles:
			t = self.tiles[-1]
			if t.title and t.title.rendered:
				log.warning(f'Rendering: {int((time.time() - self.bench) * 1000)}ms')
				self.bench = None

		tile_width = config.tile.width
		tile_hspace = config.tile.min_hspace
		tile_htotal = tile_width + tile_hspace

		tile_height = config.tile.thumb_height + config.tile.text_vspace + int(config.tile.text_size * 1.65) * config.tile.text_lines
		tile_vspace = config.tile.min_vspace
		tile_vtotal = tile_height + tile_vspace

		tiles_per_row = max(width // tile_htotal, 1)
		tile_hoffset = (width - tiles_per_row * tile_htotal + tile_hspace) // 2
		# Hmm, this is kinda dirty. But I need this in other places.
		self.tiles_per_row = tiles_per_row

		# FIXME: yuck
		height -= int(config.menu.header_vspace + config.menu.text_size * 1.65)
		tile_rows = max(height // tile_vtotal, 1)
		tile_voffset = (height - tile_rows * tile_vtotal) // 2 + tile_vspace

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
