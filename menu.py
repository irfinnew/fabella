# Fabella - Simple, elegant video library and player.
#
# Copyright 2020-2022 Marcel Moreaux.
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

		# Dark mode stuff
		self.dark_mode_quad = draw.FlatQuad(z=1000, w=width, h=height, color=(0, 0, 0, 1 - config.ui.dark_mode_brightness), hidden=True)
		self.dark_mode_text = self.menu_font.text(z=999, text='🌒', anchor='tr',
			x=width - config.menu.header_hspace, y=height - config.menu.header_vspace,
		)
		self.dark_mode_bg_thing = draw.Animatable(self.dark_mode_quad, opacity=(0, 1 - config.ui.dark_mode_brightness))
		self.dark_mode_icon_thing = draw.Animatable(self.dark_mode_text.quad, opacity=(0, 1))

		# OSD stuff
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
		self.osd_background_quad = draw.Quad(z=101, w=width, h=-20, pos=(0, height), color=(0, 0, 0, 1), hidden=True)
		self.osd_background_quad.update_raw(2, 2, 'RGBA', b'\xff\xff\xff\x00' * 2 + b'\xff\xff\xff\xff' * 2)
		self.osd_background_quad.texture.inset_halftexel() # Ugh

		self.osd_bread_thing = draw.Animatable(self.bread_text.quad, xpos=(-self.width, 0))
		self.osd_clock_thing = draw.Animatable(self.clock_text.quad, xpos=(self.width, 0))
		self.osd_name_thing = draw.Animatable(self.osd_name_text.quad, xpos=(-self.width, 0))
		self.osd_duration_thing = draw.Animatable(self.osd_duration_text.quad, xpos=(self.width, 0))
		self.osd_background_thing = draw.Animatable(self.osd_background_quad, ypos=(int(self.height * 1.5), self.height))

		# FIXME: this entire section is yuck
		tile_width = config.tile.width
		tile_hspace = config.tile.min_hspace
		tile_htotal = tile_width + tile_hspace

		tile_height = config.tile.cover_height + config.tile.text_vspace + self.tile_font.height(config.tile.text_lines)
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
		# FIXME: hurgh.
		meh = datetime.datetime.now().strftime('%a %H:%M:%S')
		if self.dark_mode:
			meh += '        '
		self.clock_text.text = meh

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

		draw.Animation(draw.Group(*(t.quads for t in self.tiles.values())), duration=0.5, opacity=(1, 0))
		draw.Animation(self.background, duration=1.0, delay=0.25, opacity=(1, 0))
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

		draw.Animation.cancel(self.background)
		draw.Animation(self.background, duration=0.5, opacity=(None, 1))

		self.show_osd()


	def forget(self, animate=None):
		for t in self.tiles.values():
			if animate:
				offset = {'left': -self.width, 'right': self.width}[animate]
				draw.Animation(t.quads, ease='in', duration=0.3, xpos=(t.pos[0], t.pos[0] + offset), after=t.destroy)
			else:
				t.destroy()
		self.tiles = {}
		self.index = []
		self.current_idx = 0
		self.current_offset = 0
		self.covers_zip = None


	def load(self, path, previous=None):
		if len(path) > len(self.path or ''):
			animate_direction = 'left'
		else:
			animate_direction = 'right'

		self.forget(animate=animate_direction)
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

		index = None
		if index is None and previous is not None:
			# Find the tile that was used to enter the previous path
			for idx, meta in enumerate(self.index):
				if meta['name'] == previous:
					index = idx
					break

		if index is None:
			# Find first "watching" video
			for i, tile in enumerate(self.index):
				if 0.0 < tile.get('position', 0.0) < 1.0:
					index = i
					break

		if index is None:
			# Find the first "unseen" video
			for i, tile in enumerate(self.index):
				if tile.get('position', 0.0) == 0.0:
					index = i
					break

		if index is None:
			index = 0

		timer = int((time.time() - timer) * 1000)
		log.info(f'Loaded tiles in {timer}ms')

		# This will also draw
		self.jump_tile(index, animate=animate_direction)


	@property
	def current(self):
		return self.tiles[self.current_idx]


	def jump_tile(self, idx, animate=None):
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

		self.draw_tiles(animate=animate)


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

		# Copy the current cover image, perform zoom animation
		quad = self.current.cover.copy(z=250)
		scale = max(self.width / quad.w, self.height / quad.h) * 1.25
		draw.Animation(quad, ease='in', duration=0.5, opacity=(1, 0), scale=(quad.scale, scale),
			xpos=(quad.pos[0], self.width // 2), ypos=(quad.pos[1], self.height // 2),
			hide=True, after=quad.destroy,
		)
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
		self.load(os.path.dirname(self.path), previous=previous)


	def draw_tiles(self, animate=None):
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
					self.height - self.tile_vstart - y * self.tile_voffset - config.tile.cover_height - Tile.yoff),
					idx == self.current_idx
				)
				self.tiles[idx] = tile
				tile.used = True

				if animate:
					offset = {'left': self.width, 'right': -self.width}[animate]
					draw.Animation(tile.quads, ease='out', delay=0.1, duration=0.3, xpos=(tile.pos[0] + offset, tile.pos[0]))
					# Ew.
					for q in tile.quads:
						q.xpos = tile.pos[0] + offset

		for idx, tile in dict(self.tiles).items():
			if not tile.used:
				tile.destroy()
				del self.tiles[idx]

		timer = int((time.time() - timer) * 1000)
		log.info(f'Drew tiles in {timer}ms')


	def show_osd(self, enabled=None, force=False):
		if enabled is not None:
			self.osd = enabled

		show_basic_osd = (self.osd or self.enabled) or force
		show_extended_osd = (self.osd and not self.enabled) or force

		self.osd_background_quad.h = -int((config.menu.header_vspace * 3 + self.bread_text.quad.h + self.osd_name_text.quad.h) * 1.1)
		self.osd_background_thing.update_params(ypos=(self.height - self.osd_background_quad.h, self.height))

		self.osd_bread_thing.show(show_basic_osd)
		self.osd_clock_thing.show(show_basic_osd)
		self.osd_name_thing.show(show_extended_osd)
		self.osd_duration_thing.show(show_extended_osd)
		self.osd_background_thing.show(show_extended_osd)


	def show_dark_mode(self, enabled=None):
		# FIXME: dark mode icon obscures clock...
		if enabled is not None:
			self.dark_mode = enabled

		self.dark_mode_bg_thing.show(self.dark_mode)
		self.dark_mode_icon_thing.show(self.dark_mode)
