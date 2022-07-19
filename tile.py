import os
import io
import time
import math
import uuid
import OpenGL.GL as gl
import functools

import dbs
import config
import loghelper
import draw
import PIL.Image

log = loghelper.get_logger('Tile', loghelper.Color.Cyan)



class Tile:
	def __init__(self, path, name, isdir, menu, font):
		self.name = name
		self.path = path
		self.full_path = os.path.join(path, name)
		self.isdir = isdir
		self.menu = menu
		self.font = font

		log.debug(f'Created {self}')

		# Internal state
		self.x = None
		self.y = None
		self.selected = False
		self.quad = None

		# Metadata, will be populated later
		self.tile_color = (0, 0, 0, 1)
		self.duration = None
		self.position = 0
		self.tagged = False

		self.cover_data = None
		self.img_cover = None
		# Renderables
		#self.title = self.font.text(None, max_width=config.tile.width, lines=config.tile.text_lines, pool=self.render_pool)
		#self.title.text = self.name if self.isdir else os.path.splitext(self.name)[0]
		self.info = None


	def update_meta(self, meta):
		log.debug(f'Update metadata for {self}')

		if meta['name'] != self.name:
			raise ValueError('{self}.update_meta({meta})')
		if meta['isdir'] != self.isdir:
			raise ValueError('{self}.update_meta({meta})')

		# Tile color
		if 'tile_color' in meta:
			tile_color = meta.get('tile_color', None)
			if tile_color is not None:
				tile_color = tile_color.strip('#')
				# FIXME: error checking
				self.tile_color = tuple(int(tile_color[i:i+2], 16) / 255 for i in range(0, 6, 2)) + (1,)
			else:
				self.tile_color = (0.3, 0.3, 0.3, 1)

		# Duration
		if 'duration' in meta:
			self.duration = meta.get('duration', None)
			if not self.info:
				self.info = self.font.text(0, 0, 1, None, max_width=None, lines=1)
			if self.duration is None:
				self.info.text = '?:??'
			else:
				duration = int(self.duration)
				hours = duration // 3600
				minutes = (duration % 3600) // 60
				self.info.text = f'{hours}:{minutes:>02}'

		if 'position' in meta:
			self.position = meta['position']

		if 'tagged' in meta:
			self.tagged = meta['tagged']


	def update_cover(self, covers_zip):
		try:
			with covers_zip.open(self.name) as fd:
				self.cover_data = fd.read()
				self.img_cover = None
		except KeyError:
			self.cover_data = None
			log.warning(f'Loading thumbnail for {self.name}: Not found in zip')


	def show(self, x, y, selected):
		if (x, y, selected, bool(self.quad)) != (self.x, self.y, self.selected, True):
			# FIXME: If just x and y change, just update quad coords
			self.x = x
			self.y = y
			self.selected = selected
			self.draw()


	def hide(self):
		self.x = None
		self.y = None
		self.selected = False

		if self.quad is not None:
			self.quad.destroy()
			self.quad = None


	def draw(self):
		if self.cover_data and not self.img_cover:
			self.img_cover = PIL.Image.open(io.BytesIO(self.cover_data))

		if self.quad is not None:
			self.quad.destroy()

		self.quad = draw.TexturedQuad(self.x, self.y, config.tile.width, -config.tile.thumb_height, 200, image=self.img_cover, color=(1, 1, 1, 1 if self.selected else 0.5))


	def update_pos(self, position, force=False):
		log.debug(f'{self} update_pos({position}, {force})')
		old_pos = self.position
		self.position = position

		now = time.time()
		if now - self.state_last_update > 10 or abs(old_pos - position) > 0.01 or force:
			self.state_last_update = now
			self.write_state_update()


	def write_state_update(self, state=None):
		if state is None:
			state = {'position': self.position}
		log.info(f'Writing state for {self.name}: {state}')
		update_name = os.path.join(self.path, dbs.QUEUE_DIR_NAME, str(uuid.uuid4()))
		dbs.json_write(update_name, {self.name: state})


	@property
	def unseen(self):
		return self.position == 0


	@property
	def watching(self):
		return 0 < self.position < 1


	def toggle_seen(self, seen=None):
		if self.isdir:
			return

		if seen is None:
			self.position = 1 if self.position < 1 else 0
		else:
			self.position = 1 if seen else 0

		self.write_state_update()


	def toggle_tagged(self):
		if self.isdir:
			return

		self.tagged = not self.tagged
		self.write_state_update({'tagged': self.tagged})


	def __str__(self):
		return f'<Tile path={self.path}, name={self.name}, isdir={self.isdir}>'


	def __repr__(self):
		return str(self)
