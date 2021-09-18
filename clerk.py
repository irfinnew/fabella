#! /usr/bin/env python3

INDEX_DB_NAME = '.fabella/index.json.gz'
PARTIAL_SUFFIX = '.part'
INDEX_META_VERSION = 1

COVER_DB_NAME = '.fabella/covers.zip'
COVER_TAG_NAME = 'FIXME'
COVER_WIDTH = 320
COVER_HEIGHT = 200

THUMB_VIDEO_POSITION = 0.25
VIDEO_FILETYPES = ['mkv', 'mp4', 'webm', 'avi', 'wmv']
VIDEO_EXTENSIONS = tuple('.' + ext for ext in VIDEO_FILETYPES)
FOLDER_COVER_FILE = '.cover.jpg'



import sys
import os
import io
import ast
import stat
import gzip
import zlib
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



def json_get(data, key, typ, none=False):
	value = data[key]

	if none and value is None:
		return None

	if not isinstance(value, typ):
		raise TypeError(f'Expected {key} to be {typ}: {value}')
	return value



class TileError(Exception):
	pass



class BaseTile:
	def to_json(self):
		"""Return the attributes as json."""
		data = {
			'name': self.name,
			'isdir': self.isdir,
			'src_size': self.src_size,
			'src_mtime': self.src_mtime,
			'tile_color': self.tile_color,
		}
		if self.isdir:
			data['count'] = self.count
		else:
			data['duration'] = self.duration

		return data


	def __eq__(self, other):
		if other is None:
			return False
		# Size/mtime might be missing for both; does not mean they're equal!
		# Actually, it does; missing in archive and missing in real = equal.
		#if None in (self.isdir, self.size, self.mtime):
		#	return False
		return (self.name, self.isdir, self.src_size, self.src_mtime, self.count) == \
			(other.name, other.isdir, other.src_size, other.src_mtime, other.count)


	def __lt__(self, other):
		# FIXME: better sorting
		return self.name < other.name


	def __str__(self):
		return f'{self.__class__.__name__}({self.name}, isdir={self.isdir}, src_size={self.src_size}, mtime={self.src_mtime}, count={self.count})'


	def __repr__(self):
		return self.__str__()



class IndexedTile(BaseTile):
	def __init__(self, path, data):
		try:
			self.name = json_get(data, 'name', str)
			self.isdir = json_get(data, 'isdir', bool)
			self.src_size = json_get(data, 'src_size', int, none=True)
			self.src_mtime = json_get(data, 'src_mtime', int, none=True)
			self.tile_color = json_get(data, 'tile_color', str, none=True)
			if self.isdir:
				self.count = json_get(data, 'count', int, none=True)
				self.duration = None
			else:
				self.count = 1
				self.duration = json_get(data, 'duration', int, none=True)
		except (KeyError, TypeError, ValueError) as e:
			# Give caller a single exception to worry about
			raise ValueError(repr(e))

		self.path = path
		self.full_path = os.path.join(path, self.name)
		self.cover_image = None



class RealTile(BaseTile):
	def __init__(self, parent_path, name):
		self.name = name
		self.path = path
		self.full_path = os.path.join(path, name)

		# Not yet determined
		self.duration = None
		self.tile_color = None
		self.cover_image = None

		# Get file attrs
		try:
			stat_data = os.stat(self.full_path)
		except FileNotFoundError as e:
			# Can't stat the file we were just created for? Fatal.
			raise ValueError(repr(e))

		if stat.S_ISDIR(stat_data.st_mode):
			self.isdir = True
			# Folder, check cover image in it instead
			try:
				stat_data = os.stat(os.path.join(self.full_path, FOLDER_COVER_FILE))
				self.src_size, self.src_mtime = stat_data.st_size, stat_data.st_mtime_ns
			except FileNotFoundError:
				# Cover image not found? Not fatal; None for attrs.
				self.src_size, self.src_mtime = None, None
		else:
			self.isdir = False
			self.src_size, self.src_mtime = stat_data.st_size, stat_data.st_mtime_ns

		# Get children counts
		self.count = self.get_count()


	def get_count(self):
		if not self.isdir:
			return 1

		# FIXME: this should use the same code as the "official" parsing
		try:
			with gzip.open(os.path.join(self.full_path, INDEX_DB_NAME)) as fd:
				return int(json.load(fd)['meta']['count'])
		except Exception as e:
			# FIXME
			#log.error(f'MEH: {e}')
			return None


	def scale_encode(self, fd):
		"""Takes file-like object, reads image from it, scales, encodes to JPEG, returns bytes."""
		try:
			with PIL.Image.open(fd) as cover:
				cover = cover.convert('RGB')
				cover = PIL.ImageOps.fit(cover, (COVER_WIDTH, COVER_HEIGHT))
		except PIL.UnidentifiedImageError as e:
			raise TileError(f'Loading image for {self.path}: {str(e)}')

		# Choose a representative color from the cover image
		# Don't like setting this from here, but we need it later anyway.
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
		if self.path.endswith(VIDEO_EXTENSIONS):
			log.info(f'Generating thumbnail for {self.path}')
			try:
				sp = run_command(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=nokey=1:noprint_wrappers=1', self.path])
				duration = float(sp.stdout)
				# Bit dirty, but we need it later anyway.
				self.duration = round(duration)
				duration = str(int(duration * THUMB_VIDEO_POSITION))

				sp = run_command(['ffmpeg', '-ss', duration, '-i', self.path, '-vf', 'thumbnail', '-frames:v', '1', '-f', 'apng', '-'])
				return self.scale_encode(io.BytesIO(sp.stdout))
			except subprocess.CalledProcessError:
				raise TileError(f'Processing {self.path}: Command returned error')

		raise TileError(f'Processing {self.path}: unknown filetype to generate cover image from')


	def update_cover(self):
		if self.isdir:
			self._cover_image = self.get_folder_cover()
		else:
			self._cover_image = self.get_file_cover()

		# Maybe duration was set from getting the cover, maybe not.
		if self.duration is None and not self.isdir and self.path.endswith(VIDEO_EXTENSIONS):
			try:
				sp = run_command(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=nokey=1:noprint_wrappers=1', self.path])
				self.duration = round(float(sp.stdout))
			except subprocess.CalledProcessError:
				pass



class Meta:
	def __init__(self, *, version=INDEX_META_VERSION, count=0):
		self.version = version
		self.count = count

	@classmethod
	def from_json(cls, data):
		meta = json_get(data, 'meta', dict)
		version = json_get(meta, 'version', int)
		count = json_get(meta, 'count', int, none=True)
		return cls(version=version, count=count)

	@classmethod
	def from_tiles(cls, tiles):
		counts = [tile.count for tile in tiles]
		if None in counts:
			count = None
		else:
			count = sum(counts)
		return cls(count=count)

	def to_json(self):
		return {
			'version': self.version,
			'count': self.count,
		}

	@classmethod
	def full_json(cls, tiles):
		return {
			'meta': Meta.from_tiles(tiles).to_json(),
			'files': [tile.to_json() for tile in sorted(tiles)],
		}

	def __eq__(self, other):
		if other is None:
			return False
		return (self.version, self.count) == (other.version, other.count)

	def __str__(self):
		return f'Meta(version={self.version}, count={self.count})'

	def __repr__(self):
		return self.__str__()



def scan(path):
	log.debug(f'Processing {path}')
	index_db_name = os.path.join(path, INDEX_DB_NAME)

	# Read index file
	orig_index = {}
	try:
		with gzip.open(index_db_name) as fd:
			log.debug(f'Found existing index DB {index_db_name}')
			orig_index = json.load(fd)
	except FileNotFoundError:
		log.info(f'Index DB {index_db_name} missing')
	except (OSError, EOFError, zlib.error, json.JSONDecodeError) as e:
		log.error(f'Parsing {index_db_name}: {str(e)}')

	# Check meta version, extract file info index
	indexes = []
	indexed_meta = None
	if orig_index:
		try:
			indexed_meta = Meta.from_json(orig_index)
			if indexed_meta.version == INDEX_META_VERSION:
				indexes = list(orig_index['files'])
			else:
				log.warning(f'Skipping outdated index DB version: {index_db_name}')
		except (KeyError, TypeError) as e:
			log.error(f'Error parsing index DB version {index_db_name}: {str(e)}')

	# Covert index to tiles
	indexed_tiles = {}
	for data in indexes:
		try:
			tile = IndexedTile(path, data)
			indexed_tiles[tile.name] = tile
		except ValueError as e:
			log.error(f'Error parsing json for tile in {index_db_name}: {e}')
	del indexes
	#for tile in indexed_tiles.values(): print('   idx:', tile) # FIXME: remove

	real_tiles = {}
	try:
		names = os.listdir(path)
	except FileNotFoundError:
		log.warning(f'Directory disappeared while we were working on it: {path}')
		return

	# List actual files, convert into tiles
	for name in names:
		if name.startswith('.'):
			continue
		if name == FOLDER_COVER_FILE:
			continue
		# FIXME Ugh, need a way to allow dirs, but not files with unknown extension
		# FIXME: jpg hack
		if '.' in name and not name.endswith(VIDEO_EXTENSIONS + ('.jpg',)):
			continue

		try:
			tile = RealTile(path, name)
			real_tiles[tile.name] = tile
		except ValueError as e:
			log.error(f'Error inspecting {path} {name}: {repr(e)}')
	#for tile in real_tiles.values(): print('  real:', tile) # FIXME: remove

	# If the index matches reality, we're done.
	if indexed_tiles == real_tiles and indexed_meta == Meta.from_tiles(real_tiles.values()):
		log.info(f'Existing tiles DB {index_db_name} is up to date, skipping')
		return

	# Apparently something changed, let's see what we can reuse.
	for name in list(real_tiles.keys()):
		if real_tiles[name] == indexed_tiles.get(name):
			log.debug(f'Tile for {name} is up to date, reusing')
			real_tiles[name] = indexed_tiles[name]

	# Write index
	log.info(f'Writing new index DB {index_db_name}')
	os.makedirs(os.path.dirname(index_db_name), exist_ok=True)
	with gzip.open(index_db_name + PARTIAL_SUFFIX, 'wt') as fd:
		json.dump(Meta.full_json(real_tiles.values()), fd, indent=4)
		os.fdatasync(fd)
	os.rename(index_db_name + PARTIAL_SUFFIX, index_db_name)

	return
	exit()

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
			log.debug(f'Tile for {name} is up to date, reusing')
			new_tiles[name] = existing_tiles[name]
		else:
			new_tiles[name] = tile
			try:
				tile.get_scaled_cover_image()
			except TileError as e:
				log.error(str(e))

	# FIXME: I don't think this can be reached anymore
	# Recheck after maybe some new tiles errored out
	if existing_tiles == new_tiles:
		log.info(f'Existing index DB {index_db_name} is up to date, skipping')
		log.error('No, we shouldn\'t get here anymore.')
		exit(1)
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



path = os.path.abspath(sys.argv[1])
watcher = Watcher(path)
watcher.push(path, recursive=True)
dirty = {}
for event in watcher.events(timeout=1):
	if event:
		log.debug(f'Got event: {event}')

	now = time.time()

	if event:
		# Case: path/ itself
		if event.isdir and event.evtype in {'modified'} and not event.hidden():
			dirty[event.path] = now

		# Case: path/foo/
		if event.isdir and event.evtype in {'created', 'deleted'}:
			watcher.push(os.path.dirname(event.path))

		if not event.isdir:
			# Case: path/.fabella/index.json.gz
			if not event.isdir and event.path.endswith('/' + INDEX_DB_NAME):
				# Recheck containing dir
				watcher.push(os.path.dirname(os.path.dirname(event.path)))
				# And parent also; it might need to be updated
				watcher.push(os.path.dirname(os.path.dirname(os.path.dirname(event.path))))
			# Case: path/.cover.jpg
			elif event.path.endswith('/' + FOLDER_COVER_FILE):
				watcher.push(os.path.dirname(os.path.dirname(event.path)))
			# Case: path/foo.bar
			else:
				# FIXME: check for valid filetype
				watcher.push(os.path.dirname(event.path))

	act_now = []
	for path, age in list(dirty.items()):
		if now - age > 1:
			del dirty[path]
			act_now.append(path)

	for path in act_now:
		scan(path)
