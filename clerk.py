#! /usr/bin/env python

COVER_WIDTH = 320
COVER_HEIGHT = 200
INDEX_DB_NAME = '.fabella/index.zip'
INDEX_DB_INDEX = '.index.json'
INDEX_DB_SUFFIX = '.part'
THUMB_VIDEO_POSITION = 0.25
VIDEO_EXTENSIONS = ['mkv', 'mp4', 'webm', 'avi', 'wmv']
FOLDER_COVER_FILE = '.cover.jpg'
INDEX_META_VERSION = 1

INDEX_META_TAG = {
	'version': INDEX_META_VERSION,
	'dimensions': f'{COVER_WIDTH}x{COVER_HEIGHT}',
}


import sys
import os
import io
import ast
import stat
import json
import time
import zipfile
import enzyme
import subprocess
import PIL.Image
import PIL.ImageOps

import colorpicker
from logger import Logger
from watch import Watcher

log = Logger(module='clerk', color=Logger.Magenta)



def run_command(command):
	try:
		return subprocess.run(command, capture_output=True, check=True)
	except subprocess.CalledProcessError as e:
		log.error(f'Command returned {e.returncode}: {command}')
		for line in e.stderr.decode('utf-8').splitlines():
			log.error(line)
		raise



class TileError(Exception):
	pass



class Tile:
	def __init__(self, name, parent_path, *, json_data=None, scaled_cover_image=None):
		self.name = name
		self.path = os.path.join(parent_path, name)
		self.scaled_cover_image = scaled_cover_image

		if json_data:
			self.isdir, self.size, self.mtime, self.duration, self.tile_color = self.parse_json(json_data)
		else:
			self.isdir, self.size, self.mtime = self.get_attrs()
			self.duration = None
			self.tile_color = None


	def get_attrs(self):
		"""Returns (isdir, size, mtime) file attrs used to determine cover staleness."""
		try:
			stat_data = os.stat(self.path)
		except FileNotFoundError:
			return (True, None, None)

		if stat.S_ISDIR(stat_data.st_mode):
			# Folder, check cover file in it instead
			try:
				stat_data = os.stat(os.path.join(self.path, FOLDER_COVER_FILE))
				return (True, stat_data.st_size, stat_data.st_mtime_ns)
			except FileNotFoundError:
				return (True, None, None)
		else:
			return (False, stat_data.st_size, stat_data.st_mtime_ns)


	def to_json(self):
		"""Return the attributes as json."""
		return {
			'name': self.name,
			'isdir': self.isdir,
			'src_size': self.size,
			'src_mtime': self.mtime,
			'duration': self.get_duration(),
			'tile_color': self.tile_color,
		}


	def parse_json(self, data):
		try:
			return (
				bool(data['isdir']),
				int(data['src_size']) if data['src_size'] is not None else None,
				int(data['src_mtime']) if data['src_mtime'] is not None else None,
				int(data['duration']) if data['duration'] is not None else None,
				str(data['tile_color']) if data['tile_color'] is not None else None,
			)
		except (json.decoder.JSONDecodeError, TypeError, KeyError) as e:
			log.warning(f'Error JSON data for {self.name}: {repr(e)}')
			return (None, None, None, None)


	def scale_encode(self, fd):
		"""Takes file-like object, reads image from it, scales, encodes to JPEG, returns bytes."""
		try:
			with PIL.Image.open(fd) as cover:
				cover = cover.convert('RGB')
				cover = PIL.ImageOps.fit(cover, (COVER_WIDTH, COVER_HEIGHT))
		except PIL.UnidentifiedImageError as e:
			raise TileError(f'Loading image for {self.path}: {str(e)}')

		# Choose a representative color from the cover image
		self.tile_color = '#' + ''.join(f'{c:02x}' for c in colorpicker.pick(cover))

		buffer = io.BytesIO()
		cover.save(buffer, format='JPEG', quality=90, optimize=True)
		return buffer.getvalue()


	def get_folder_cover(self):
		"""Find cover image for folder, scale, return bytes."""
		cover_file = os.path.join(self.path, FOLDER_COVER_FILE)
		if not os.path.isfile(cover_file):
			raise TileError(f'Cover image {cover_file} not found')

		with open(cover_file, 'rb') as fd:
			log.info(f'Found cover {cover_file}')
			return self.scale_encode(fd)


	def get_file_cover(self):
		"""Find cover image for file, scale, return bytes."""
		# FIXME: Hmm. Not sure.
		if self.path.endswith(('.jpg', '.png')):
			log.info(f'Using image file as its own cover: {self.path}')
			with open(self.path, 'rb') as fd:
				return self.scale_encode(fd)

		if self.path.endswith('.mkv'):
			try:
				with open(self.path, 'rb') as fd:
					mkv = enzyme.MKV(fd)
					for a in mkv.attachments:
						# FIXME: just uses first jpg attachment it sees; check filename!
						if a.mimetype == 'image/jpeg':
							log.info(f'Found embedded cover in {self.path}')
							return self.scale_encode(a.data)
			except (FileNotFoundError, enzyme.exceptions.Error) as e:
				raise TileError(f'Processing {self.path}: {str(e)}')

		# If we got here, no embedded cover was found, generate thumbnail
		if self.path.endswith(tuple('.' + e for e in VIDEO_EXTENSIONS)):
			log.info(f'Generating thumbnail for {self.path}')
			try:
				sp = run_command(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=nokey=1:noprint_wrappers=1', self.path])
				duration = float(sp.stdout)
				duration = str(int(duration * THUMB_VIDEO_POSITION))

				sp = run_command(['ffmpeg', '-ss', duration, '-i', self.path, '-vf', 'thumbnail', '-frames:v', '1', '-f', 'apng', '-'])
				return self.scale_encode(io.BytesIO(sp.stdout))
			except subprocess.CalledProcessError:
				raise TileError(f'Processing {self.path}: Command returned error')

		raise TileError(f'Processing {self.path}: unknown filetype to generate cover image from')


	def get_scaled_cover_image(self):
		"""Return cached cover image bytes. If not cached, find, scale, return bytes. None if unsuccessful."""
		if not self.scaled_cover_image:
			if self.isdir:
				self.scaled_cover_image = self.get_folder_cover()
			else:
				self.scaled_cover_image = self.get_file_cover()

		return self.scaled_cover_image


	def get_duration(self):
		"""Return cached duration. If not cached, probe and return. None if unsuccessful."""
		if not self.duration:
			if not self.isdir and self.path.endswith(tuple('.' + e for e in VIDEO_EXTENSIONS)):
				sp = run_command(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=nokey=1:noprint_wrappers=1', self.path])
				self.duration = round(float(sp.stdout))

		return self.duration


	def __eq__(self, other):
		if other is None:
			return False
		# Size/mtime might be missing for both; does not mean they're equal!
		#if None in (self.isdir, self.size, self.mtime):
		#	return False
		return (self.name, self.isdir, self.size, self.mtime) == \
			(other.name, other.isdir, other.size, other.mtime)


	def __lt__(self, other):
		return self.name < other.name


	def __str__(self):
		return f'Tile({self.name}, isdir={self.isdir}, size={self.size}, mtime={self.mtime})'


	def __repr__(self):
		return self.__str__()



def scan(path):
	log.info(f'Processing {path}')
	index_db_name = (os.path.join(path, INDEX_DB_NAME))

	try:
		with zipfile.ZipFile(index_db_name, 'r') as index_db:
			log.info(f'Found existing index DB {index_db_name}')
			try:
				index = json.loads(index_db.read(INDEX_DB_INDEX))
			except KeyError:
				log.error(f'Missing index {INDEX_DB_INDEX} in existing index DB {index_db_name}')
				raise FileNotFoundError() # FIXME: ewww. But we must get out of here

			try:
				if index['meta'] != INDEX_META_TAG:
					log.info(f'Outdated {INDEX_DB_INDEX} in existing tiles DB {index_db_name}; ignoring index')
					raise FileNotFoundError() # FIXME: ewww. But we must get out of here
			except KeyError:
				log.error(f'Missing metadata in existing index DB {index_db_name}')
				raise FileNotFoundError() # FIXME: ewww. But we must get out of here

			existing_tiles = {}
			for entry in index['files']:
				# FIXME: check errors
				name = entry['name']

				# It's semi-valid for a file to exist in the index but not have a cover image
				try:
					scaled_cover_image = index_db.read(name)
				except KeyError:
					scaled_cover_image = None

				existing_tiles[name] = Tile(name, path, json_data=entry, scaled_cover_image=scaled_cover_image)

	except FileNotFoundError:
		existing_tiles = {}
	except zipfile.BadZipFile as e:
		log.error(f'Existing tiles DB {index_db_name} is broken: {str(e)}')
		existing_tiles = {}

	current_tiles = {}
	try:
		names = os.listdir(path)
	except FileNotFoundError:
		log.warning(f'Directory disappeared while we were working on it: {path}')
		return

	for name in names:
		if name.startswith('.'):
			continue
		if name == FOLDER_COVER_FILE:
			continue
		# FIXME: check for valid filetype

		current_tiles[name] = Tile(name, path)

	if existing_tiles == current_tiles:
		log.info(f'Existing tiles DB {index_db_name} is up to date, skipping')
		return

	new_tiles = {}
	for name, tile in current_tiles.items():
		if existing_tiles.get(name) == tile:
			log.info(f'Tile for {name} is up to date, reusing')
			new_tiles[name] = existing_tiles[name]
		else:
			new_tiles[name] = tile
			try:
				tile.get_scaled_cover_image()
			except TileError as e:
				log.error(str(e))

	# Recheck after maybe some new tiles errored out
	if existing_tiles == new_tiles:
		log.info(f'Existing index DB {index_db_name} is up to date, skipping')
		return


	# Write new tiles file
	new_tiles = sorted(new_tiles.values())
	os.makedirs(os.path.dirname(index_db_name), exist_ok=True)
	index_db = zipfile.ZipFile(index_db_name + INDEX_DB_SUFFIX, 'w')
	log.info(f'Writing new index DB {index_db_name}')

	# Write index
	index = {
		'meta': INDEX_META_TAG,
		'files': [tile.to_json() for tile in new_tiles],
	}
	index_db.writestr(INDEX_DB_INDEX, json.dumps(index, indent=4), compresslevel=zipfile.ZIP_DEFLATED)

	# Write cover images
	for tile in new_tiles:
		if tile.scaled_cover_image:
			index_db.writestr(tile.name, tile.scaled_cover_image)

	index_db.close()
	os.rename(index_db_name + INDEX_DB_SUFFIX, index_db_name)



path = sys.argv[1]
watcher = Watcher(path)
watcher.push(path, recursive=True)
dirty = {}
for event in watcher.events(timeout=1):
	now = time.time()

	if event:
		if event.isdir and event.evtype in {'modified'} and not event.hidden():
			dirty[event.path] = now

		if event.isdir and event.evtype in {'created', 'deleted'}:
			watcher.push(os.path.dirname(event.path))

		if not event.isdir:
			if event.path.endswith('/' + INDEX_DB_NAME):
				watcher.push(os.path.dirname(os.path.dirname(event.path)))
			elif event.path.endswith('/' + FOLDER_COVER_FILE):
				watcher.push(os.path.dirname(os.path.dirname(event.path)))
			else:
				watcher.push(os.path.dirname(event.path))

	act_now = []
	for path, age in list(dirty.items()):
		if now - age > 1:
			del dirty[path]
			act_now.append(path)

	for path in act_now:
		scan(path)
