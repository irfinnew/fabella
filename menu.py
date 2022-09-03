# Fabella - Simple, elegant video library and player.
#
# Copyright 2020-2021 Marcel Moreaux.
# Licensed under GPL v2.0, or (at your option) any later version.
# (SPDX GPL-2.0-or-later) See LICENSE file for details.

import os
import datetime
import time
import uuid
import zipfile

import loghelper
import config
import dbs
import draw
import util
from tile import Tile
from font import Font



log = loghelper.get_logger('Menu', loghelper.Color.Cyan)



class Menu:
	def __init__(self, path, width, height, enabled=False):
		log.info(f'Created instance, path={path}, enabled={enabled}')

		self.tile_font = Font(config.tile.text_font, config.tile.text_size)
		self.menu_font = Font(config.menu.text_font, config.menu.text_size)
		self.width = width
		self.height = height
		self.enabled = False
		self.osd = False
		self.dark_mode = False
		self.root = path
		self.path = None
		self.current_idx = 0
		self.current_offset = 0
		self.index = []
		self.tiles = {}
		self.covers_zip = None
		self.background = draw.FlatQuad(z=100, w=width, h=height, color=config.menu.background_color)
		self.osd_background_quad = draw.Quad(z=101, w=width, h=-200, pos=(0, height), color=(0, 0, 0, 0), hidden=True)
		self.osd_background_quad.update_raw(2, 2, 'RGBA', b'\xff\xff\xff\x00' * 2 + b'\xff\xff\xff\xff' * 2)
		self.osd_background_quad.texture.inset_halftexel() # Ugh
		self.dark_mode_quad = draw.FlatQuad(z=1000, w=width, h=height, color=(0, 0, 0, 1 - config.ui.dark_mode_brightness), hidden=True)
		self.dark_mode_text = self.menu_font.text(z=999, text='🌒', anchor='tr',
			x=width - config.menu.header_hspace, y=height - config.menu.header_vspace,
		)
		self.breadcrumbs = []
		self.bread_text = self.menu_font.text(z=102, text='', anchor='tl',
			x=config.menu.header_hspace, y=height - config.menu.header_vspace,
		)
		self.clock_text = self.menu_font.text(z=102, text='clock', anchor='tr',
			x=width - config.menu.header_hspace, y=height - config.menu.header_vspace,
		)
		self.osd_name_text = self.menu_font.text(z=102, text='LOSD', anchor='tl', lines=4,
			x=config.menu.header_hspace, y=height - config.menu.header_vspace * 2 - self.menu_font.height(1),
		)
		self.osd_duration_text = self.menu_font.text(z=102, text='ROSD', anchor='tr',
			x=width - config.menu.header_hspace, y=height - config.menu.header_vspace * 2 - self.menu_font.height(1),
		)

		# FIXME: this entire section is yuck
		tile_width = config.tile.width
		tile_hspace = config.tile.min_hspace
		tile_htotal = tile_width + tile_hspace

		tile_height = config.tile.thumb_height + config.tile.text_vspace + self.tile_font.height(config.tile.text_lines)
		tile_vspace = config.tile.min_vspace
		tile_vtotal = tile_height + tile_vspace

		tile_columns = max(width // tile_htotal, 1)
		tile_hoffset = (width - tile_columns * tile_htotal + tile_hspace) // 2
		self.tile_columns = tile_columns
		self.tile_hstart = tile_hoffset
		self.tile_hoffset = tile_htotal

		height -= config.menu.header_vspace + self.menu_font.height(1)
		tile_rows = max(height // tile_vtotal, 1)
		tile_voffset = (height - tile_rows * tile_vtotal) // 2 + tile_vspace

		self.tile_rows = tile_rows
		self.tile_vstart = tile_voffset
		self.tile_vstart = config.menu.header_vspace + self.menu_font.height(1) + (height - tile_rows * tile_vtotal) // 2 + tile_vspace
		self.tile_voffset = tile_vtotal
		# FIXME: end yuck

		self.load(path)
		self.open(enabled)
		self.show_dark_mode()


	def tick(self, video):
		self.clock_text.text = datetime.datetime.now().strftime('%a %H:%M:%S')

		# FIXME: Hmm, kinda gross we need the video object here
		duration_text = '⏸️  ' if video.paused else '▶️  '
		if video.position is None or video.duration is None:
			duration_text += '?:??'
		else:
			position = int(video.position * video.duration)
			position = util.duration_format(position, seconds=True)
			duration = int(video.duration)
			duration = util.duration_format(duration, seconds=True)
			duration_text += f'{position}  ∕  {duration}'
		self.osd_duration_text.text = duration_text
		# Ugh.
		self.osd_name_text.max_width = self.width - self.osd_duration_text.quad.w - config.menu.header_hspace * 3


	def close(self):
		if not self.enabled:
			return
		self.enabled = False

		draw.Animation(draw.Group(*(t.quads for t in self.tiles.values())), duration=0.5, opacity=(1, 0), hide=True)
		draw.Animation(self.background, duration=1.0, delay=0.25, opacity=(1, 0), hide=True)
		#draw.Animation(self.background, duration=1.0, delay=0.25, ypos=(0, -self.height), hide=True)
		self.show_osd()


	def open(self, enabled=True):
		if not enabled:
			return self.close()
		if self.enabled:
			return
		self.enabled = True

		if self.tiles:
			# FIXME: hack to force redraw on tile, so playing emblem / posbar is shown
			self.current.show((0, 0), False)
		self.draw_tiles()

		draw.Animation(draw.Group(*(t.quads for t in self.tiles.values())), duration=0.5, opacity=(0, 1))
		draw.Animation(self.background, duration=0.5, opacity=(0, 1))
		#draw.Animation(self.background, duration=1.0, ypos=(-self.height, 0))
		self.show_osd()


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
		self.osd_name_text.text = tile.name
		# FIXME: this seems to work, but why?
		# It should interfere with the close() animation, AND scale shouldn't get reset...
		cur = self.current
		draw.Animation(cur.quads, duration=0.5, opacity=(1, 0), scale=(1, 6), xpos=(cur.pos[0], self.width // 2), ypos=(cur.pos[1], self.height // 2), hide=True)
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


	def show_osd(self, enabled=None, force=False):
		if enabled is not None:
			self.osd = enabled

		if (self.osd or self.enabled) or force:
			# show basic OSD
			if self.bread_text.quad.hidden:
				draw.Animation(self.bread_text.quad, ease='out', duration=0.5, xpos=(-self.width, 0))
			if self.clock_text.quad.hidden:
				draw.Animation(self.clock_text.quad, ease='out', duration=0.5, xpos=(self.width, 0))
		else:
			# hide basic OSD
			if not self.bread_text.quad.hidden:
				draw.Animation(self.bread_text.quad, ease='in', duration=0.5, xpos=(0, -self.width), hide=True)
			if not self.clock_text.quad.hidden:
				draw.Animation(self.clock_text.quad, ease='in', duration=0.5, xpos=(0, self.width), hide=True)

		if (self.osd and not self.enabled) or force:
			# show extended OSD
			if self.osd_background_quad.hidden:
				# FIXME: figure out better height?
				self.osd_background_quad.h = -int((config.menu.header_vspace * 3 + self.bread_text.quad.h + self.osd_name_text.quad.h) * 1.5)
				# FIXME: hardcoded opacity
				draw.Animation(self.osd_background_quad, duration=0.5, opacity=(0, 0.7))
			if self.osd_name_text.quad.hidden:
				draw.Animation(self.osd_name_text.quad, ease='out', duration=0.5, xpos=(-self.width, 0))
			if self.osd_duration_text.quad.hidden:
				draw.Animation(self.osd_duration_text.quad, ease='out', duration=0.5, xpos=(self.width, 0))
		else:
			# hide extended OSD
			if not self.osd_background_quad.hidden:
				# FIXME: hardcoded opacity
				draw.Animation(self.osd_background_quad, duration=0.5, opacity=(0.7, 0), hide=True)
			if not self.osd_name_text.quad.hidden:
				draw.Animation(self.osd_name_text.quad, ease='in', duration=0.5, xpos=(0, -self.width), hide=True)
			if not self.osd_duration_text.quad.hidden:
				draw.Animation(self.osd_duration_text.quad, ease='in', duration=0.5, xpos=(0, self.width), hide=True)


	def show_dark_mode(self, enabled=None):
		# FIXME: dark mode icon obscures clock...
		if enabled is not None:
			self.dark_mode = enabled

		if self.dark_mode:
			if self.dark_mode_quad.hidden:
				draw.Animation(self.dark_mode_quad, duration=0.5, opacity=(0, 1 - config.ui.dark_mode_brightness))
			if self.dark_mode_text.quad.hidden:
				draw.Animation(self.dark_mode_text.quad, duration=0.5, opacity=(0, 1))
		else:
			if not self.dark_mode_quad.hidden:
				draw.Animation(self.dark_mode_quad, duration=0.5, opacity=(1 - config.ui.dark_mode_brightness, 0), hide=True)
			if not self.dark_mode_text.quad.hidden:
				draw.Animation(self.dark_mode_text.quad, duration=0.5, opacity=(1, 0), hide=True)
