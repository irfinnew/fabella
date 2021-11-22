#! /usr/bin/env python3

INDEX_DB_NAME = '.fabella/index.json.gz'
PARTIAL_SUFFIX = '.part'
INDEX_META_VERSION = 1

COVER_DB_NAME = '.fabella/covers.zip'
COVER_META_TAG = '.meta'
COVER_WIDTH = 320
COVER_HEIGHT = 200

STATE_DB_NAME = '.fabella/state.json.gz'
QUEUE_DIR_NAME = '.fabella/queue'

THUMB_VIDEO_POSITION = 0.25
VIDEO_FILETYPES = ['mkv', 'mp4', 'webm', 'avi', 'wmv']
VIDEO_EXTENSIONS = tuple('.' + ext for ext in VIDEO_FILETYPES)
FOLDER_COVER_FILE = '.cover.jpg'
MKV_COVER_FILE = 'cover.jpg'
EVENT_COOLDOWN_SECONDS = 1

WATCHED_STEPS = 10
WATCHED_MAX = (2 ** WATCHED_STEPS - 1)
STATE_UPDATE_SCHEMA = {
	'name': str,
	'position?': (int, float),
	'state?': int,
}
INDEX_DB_SCHEMA = {
	'meta': { 'version': int },
	'files': [
		{
			'name': str,
			'isdir': bool,
			'src_size': int,
			'src_mtime': int,
			'tile_color': str,
			'duration': int,
		}
	],
}

import sys
import os
import io
import ast
import stat
import gzip
import zlib
import json
import time
import uuid
import zipfile
import enzyme
import hashlib
import subprocess
import PIL.Image
import PIL.ImageOps

import colorpicker
from logger import Logger
from watch import Watcher
from worker import Pool

log = Logger(module='clerk', color=Logger.Magenta)



class JsonValidateError(Exception):
	pass

def validate_json(data, schema, keyname=None):
	if isinstance(schema, dict):
		if not isinstance(data, dict):
			raise JsonValidateError(f'Expected object, not {data}')
		mandatory = {k: v for k, v in schema.items() if not k.endswith('?')}
		optional = {k[:-1]: v for k, v in schema.items() if k.endswith('?')}
		for k, v in data.items():
			if k in mandatory:
				validate_json(v, mandatory[k], keyname=k)
				del mandatory[k]
			if k in optional:
				validate_json(v, optional[k], keyname=k)
		if mandatory:
			raise JsonValidateError(f'Missing keys {list(mandatory.keys())} in {data}')
	else:
		if not isinstance(data, schema):
			raise JsonValidateError(f'Key {keyname}={data} should be type {schema}')



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
		if not self.isdir:
			data['duration'] = self.duration

		return data


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
		cover_file = os.path.join(self.full_path, FOLDER_COVER_FILE)
		if not os.path.isfile(cover_file):
			raise TileError(f'Cover image {cover_file} not found')

		with open(cover_file, 'rb') as fd:
			log.info(f'Found cover {cover_file}')
			return self.scale_encode(fd)


	def get_file_cover(self):
		"""Find cover image for file, scale, return bytes."""
		# FIXME: Hmm. Not sure; image files are ignored earlier in the process anyway.
		if self.name.endswith(('.jpg', '.png')):
			log.info(f'Using image file as its own cover: {self.full_path}')
			with open(self.full_path, 'rb') as fd:
				return self.scale_encode(fd)

		if self.name.endswith('.mkv'):
			try:
				with open(self.full_path, 'rb') as fd:
					mkv = enzyme.MKV(fd)
					for a in mkv.attachments:
						if a.mimetype == 'image/jpeg' and a.filename == MKV_COVER_FILE:
							log.info(f'Found embedded cover in {self.full_path}')
							return self.scale_encode(a.data)
			except (OSError, enzyme.exceptions.Error) as e:
				raise TileError(f'Processing {self.full_path}: {e}')

		# If we got here, no embedded cover was found, generate thumbnail
		if self.name.endswith(VIDEO_EXTENSIONS):
			log.info(f'Generating thumbnail for {self.full_path}')
			try:
				duration = self.get_video_duration()
				# Bit dirty, but we need it later anyway.
				self.duration = round(duration)
				duration = str(duration * THUMB_VIDEO_POSITION)

				sp = run_command(['ffmpeg', '-ss', duration, '-threads', '1', '-i', self.full_path, '-vf', 'thumbnail', '-frames:v', '1', '-f', 'apng', '-'])
				return self.scale_encode(io.BytesIO(sp.stdout))
			except subprocess.CalledProcessError:
				raise TileError(f'Processing {self.full_path}: Command returned error')

		raise TileError(f'Processing {self.full_path}: unknown filetype to generate cover image from')


	def get_video_duration(self):
		if self.name.endswith('.mkv'):
			try:
				with open(self.full_path, 'rb') as fd:
					mkv = enzyme.MKV(fd)
					duration = mkv.info.duration
					return duration.seconds + duration.microseconds / 1000000
			except (OSError, enzyme.exceptions.Error) as e:
				log.error(f'Processing {self.full_path}: {e}')
				return None
		else:
			try:
				sp = run_command(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=nokey=1:noprint_wrappers=1', self.full_path])
				return float(sp.stdout)
			except (subprocess.CalledProcessError, ValueError) as e:
				log.error(f'Getting video duration for {self.name}: {e}')
				return none


	def analyze(self):
		if self.cover_needs_update:
			try:
				if self.isdir:
					self.cover_image = self.get_folder_cover()
				else:
					self.cover_image = self.get_file_cover()
			except TileError as e:
				log.error(str(e))
				self.cover_image = None
			self.cover_needs_update = False

		# Maybe duration was set from getting the cover, maybe not.
		if self.duration is None and not self.isdir and self.name.endswith(VIDEO_EXTENSIONS):
			try:
				self.duration = self.get_video_duration()
				self.duration = round(self.duration) if self.duration is not None else None
			except subprocess.CalledProcessError as e:
				log.error(f'Couldn\'t determine video duration: {e}')


	def __eq__(self, other):
		if other is None:
			return False
		# Size/mtime might be missing for both; does not mean they're equal!
		# Actually, it does; missing in archive and missing in real = equal.
		#if None in (self.isdir, self.size, self.mtime):
		#	return False
		return (self.name, self.isdir, self.src_size, self.src_mtime) == \
			(other.name, other.isdir, other.src_size, other.src_mtime)


	def __lt__(self, other):
		return self.sortkey < other.sortkey


	@property
	def sortkey(self):
		casename = self.name.strip().casefold()
		simplename = casename
		for a in ['a ', 'an ', 'the ']:
			if simplename.startswith(a):
				simplename = simplename[len(a):].strip()
				break
		# Sort folders first, then files.
		# Next, sort on case-insensitive simplified name.
		# Finally, just the raw name for deterministic ordering.
		return (not self.isdir, simplename, self.name)


	def __str__(self):
		return f'{self.__class__.__name__}({self.name}, isdir={self.isdir}, src_size={self.src_size}, mtime={self.src_mtime})'


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
			self.duration = None if self.isdir else json_get(data, 'duration', int, none=True)
		except (KeyError, TypeError, ValueError) as e:
			# Give caller a single exception to worry about
			raise ValueError(repr(e))

		self.path = path
		self.full_path = os.path.join(path, self.name)
		self.cover_image = None
		self.cover_needs_update = True



class RealTile(BaseTile):
	def __init__(self, parent_path, name):
		self.name = name
		self.path = path
		self.full_path = os.path.join(path, name)

		# Not yet determined
		self.duration = None
		self.tile_color = None
		self.cover_image = None
		self.cover_needs_update = True

		# Get file attrs
		try:
			stat_data = os.stat(self.full_path)
		except OSError as e:
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

	def valid(self):
		"""True if the tile is "valid". Meaning the name/filetype/etc checks out."""
		if self.name.startswith('.'):
			return False

		if self.isdir:
			return True

		# File
		return self.name.endswith(VIDEO_EXTENSIONS)



class Meta:
	def __init__(self, *, version):
		self.version = version

	@classmethod
	def from_json(cls, data):
		meta = json_get(data, 'meta', dict)
		version = json_get(meta, 'version', int)
		return cls(version=version)

	@classmethod
	def from_tiles(cls, tiles):
		return cls(version=INDEX_META_VERSION)

	def to_json(self):
		return {
			'version': self.version,
		}

	@classmethod
	def full_json(cls, tiles):
		return {
			'meta': Meta.from_tiles(tiles).to_json(),
			'files': [tile.to_json() for tile in sorted(tiles)],
		}

	@classmethod
	def fingerprint(cls, tiles):
		tiles = [[t.name, t.isdir, t.src_size, t.src_mtime] for t in tiles]
		return hashlib.sha256(json.dumps(tiles).encode('utf8')).hexdigest()

	def __eq__(self, other):
		if other is None:
			return False
		return self.version == other.version

	def __str__(self):
		return f'Meta(version={self.version})'

	def __repr__(self):
		return self.__str__()



def scan(path, pool):
	log.debug(f'Scanning {path}')
	if not os.path.isdir(path):
		log.info(f'{path} is gone, nothing to do')
		return

	# Ensure state queue is processed
	process_state_queue(path)

	index_db_name = os.path.join(path, INDEX_DB_NAME)

	#### Read index file
	orig_index = {}
	try:
		with gzip.open(index_db_name) as fd:
			log.debug(f'Found existing index DB {index_db_name}')
			orig_index = json.load(fd)
	except FileNotFoundError:
		log.info(f'Index DB {index_db_name} missing')
	except (OSError, EOFError, zlib.error, json.JSONDecodeError) as e:
		log.error(f'Parsing {index_db_name}: {str(e)}')


	#### Check meta version, extract file info index
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


	#### Convert index to tiles
	indexed_tiles = []
	for data in indexes:
		try:
			tile = IndexedTile(path, data)
			indexed_tiles.append(tile)
		except ValueError as e:
			log.error(f'Error parsing json for tile in {index_db_name}: {e}')
	del indexes


	#### Covers DB
	cover_db_name = os.path.join(path, COVER_DB_NAME)
	cover_db_fingerprint = None
	try:
		with zipfile.ZipFile(cover_db_name, 'r') as fd:
			log.debug(f'Found existing covers DB {cover_db_name}')
			cover_meta = json.loads(fd.read(COVER_META_TAG))
			if cover_meta['version'] != INDEX_META_VERSION:
				log.info(f'Existing {covers.db_name} outdated version, discarding')
			elif cover_meta['dimensions'] != f'{COVER_WIDTH}x{COVER_HEIGHT}':
				log.info(f'Existing {covers.db_name} has wrong cover dimensions, discarding')
			elif cover_meta['fingerprint'] != Meta.fingerprint(indexed_tiles):
				log.warning(f'Existing {cover_db_name} fingerprint doesn\'t match {index_db_name}, discarding')
			else:
				for tile in indexed_tiles:
					tile.cover_image = fd.read(tile.name)
					if tile.cover_image == b'':
						tile.cover_image = None
					tile.cover_needs_update = False
				cover_db_fingerprint = cover_meta['fingerprint']
	except FileNotFoundError:
		log.info(f'Cover DB {cover_db_name} missing')
	except (OSError, zipfile.BadZipFile, json.JSONDecodeError, KeyError, TypeError) as e:
		log.error(f'Parsing {cover_db_name}: {e}')


	#### List actual files, convert into tiles
	real_tiles = []
	try:
		names = os.listdir(path)
	except FileNotFoundError:
		log.warning(f'Directory disappeared while we were working on it: {path}')
		return

	for name in names:
		try:
			tile = RealTile(path, name)
			real_tiles.append(tile)
		except ValueError as e:
			log.error(f'Error inspecting {path} {name}: {repr(e)}')

	# Filter and sort
	real_tiles = [tile for tile in real_tiles if tile.valid()]
	real_tiles = sorted(real_tiles)


	#### If the index matches reality, we're done.
	index_needs_update = True
	if indexed_tiles == real_tiles and indexed_meta == Meta.from_tiles(real_tiles):
		log.info(f'Existing index DB {index_db_name} is up to date, skipping')
		index_needs_update = False


	#### Determine what we can reuse
	# Abuses real_tiles as the end-result
	indexed_tiles = {t.name: t for t in indexed_tiles}
	for i in range(len(real_tiles)):
		name = real_tiles[i].name
		if real_tiles[i] == indexed_tiles.get(name):
			log.debug(f'Tile for {name} is up to date, reusing')
			real_tiles[i] = indexed_tiles[name]
		else:
			log.debug(f'Tile for {name} is stale, re-inspecting')

	#### Update covers/tile_color/duration etc; this is the expensive part
	for tile in real_tiles:
		pool.schedule(tile.analyze)
	pool.join()

	#### Write index
	if index_needs_update:
		log.info(f'Writing new index DB {index_db_name}')
		os.makedirs(os.path.dirname(index_db_name), exist_ok=True)
		with gzip.open(index_db_name + PARTIAL_SUFFIX, 'wt') as fd:
			json.dump(Meta.full_json(real_tiles), fd, indent=4)
			os.fdatasync(fd)
		os.rename(index_db_name + PARTIAL_SUFFIX, index_db_name)

	#### Write covers
	# FIXME: error checking
	real_fingerprint = Meta.fingerprint(real_tiles)
	if cover_db_fingerprint == real_fingerprint:
		log.info(f'Existing cover DB {cover_db_name} is up to date, skipping')
	else:
		if real_tiles:
			log.info(f'Writing new cover DB {cover_db_name}')
			with zipfile.ZipFile(cover_db_name + PARTIAL_SUFFIX, 'w') as fd:
				meta = {
					'version': INDEX_META_VERSION,
					'dimensions': f'{COVER_WIDTH}x{COVER_HEIGHT}',
					'fingerprint': real_fingerprint,
				}
				fd.writestr(COVER_META_TAG, json.dumps(meta, indent=4))

				# Write cover images
				for tile in real_tiles:
					fd.writestr(tile.name, tile.cover_image or b'')
			with open(cover_db_name + PARTIAL_SUFFIX) as fd:
				os.fdatasync(fd)
			os.rename(cover_db_name + PARTIAL_SUFFIX, cover_db_name)
		else:
			if os.path.isfile(cover_db_name):
				log.info(f'No files here, removing {cover_db_name}')
				os.remove(cover_db_name)
			else:
				log.debug(f'No files here, not writing {cover_db_name}')



def process_state_queue(path):
	log.debug(f'Processing state events for {path}')

	queue_dir_name = os.path.join(path, QUEUE_DIR_NAME)
	state_db_name = os.path.join(path, STATE_DB_NAME)

	# Ensure queue dir exists
	os.makedirs(queue_dir_name, exist_ok=True)
	os.chmod(queue_dir_name, 0o775)

	#### Load original state
	try:
		with gzip.open(state_db_name) as fd:
			orig_state = json.load(fd)
	except FileNotFoundError:
		log.debug(f'No state DB {state_db_name}; using empty state')
		orig_state = {}
	except (OSError, EOFError, zlib.error, json.JSONDecodeError) as e:
		log.error(f'Parsing {state_db_name}: {str(e)}')
	# FIXME: validate state

	# FIXME: duplicate code
	# BLABLAH
	index_db_name = os.path.join(path, INDEX_DB_NAME)
	try:
		with gzip.open(index_db_name) as fd:
			log.debug(f'Adding names from {index_db_name}')
			# FIXME: validate
			index = [idx['name'] for idx in json.load(fd)['files']]
	except FileNotFoundError:
		log.debug(f'Index DB {index_db_name} missing')
		index = []
	except (OSError, EOFError, zlib.error, json.JSONDecodeError) as e:
		log.error(f'Parsing {index_db_name}: {str(e)}')
		index = []

	# Make deep copy of actual present files
	state = {name: dict(orig_state.get(name, {})) for name in index}

	state_queue = [f for f in os.scandir(queue_dir_name) if f.is_file()]
	state_queue = sorted(state_queue, key=lambda f: f.stat().st_mtime)
	state_queue = [f.path for f in state_queue]

	print('before', state)

	for update_name in state_queue:
		log.debug(f'Processing {update_name}')
		try:
			with open(update_name) as fd:
				update = json.load(fd)
		except (OSError, EOFError, zlib.error, json.JSONDecodeError) as e:
			log.error(f'Parsing {update_name}: {str(e)}')
			continue

		print(update)
		try:
			validate_json(update, STATE_UPDATE_SCHEMA)
		except JsonValidateError as e:
			log.error(f'Parsing {update_name}: {str(e)}')
			continue

		name = update['name']
		if name not in state:
			state[name] = {}
		this_state = state[name]

		if 'position' in update:
			if update['position'] > 0:
				this_state['position'] = update['position']
				this_state['position_date'] = time.time()
			else:
				this_state.pop('position', None)
				this_state.pop('position_date', None)

		if 'state' in update:
			if update['state'] == 0:
				this_state.pop('state', None)
				this_state.pop('position', None)
				this_state.pop('position_date', None)
			elif update['state'] == WATCHED_MAX:
				this_state['state'] = WATCHED_MAX
				this_state.pop('position', None)
				this_state.pop('position_date', None)
			else:
				this_state['state'] = update['state']

		if 'trashed' in update:
			this_state['trashed'] = update['trashed']

	# Filter out empty states
	#state = {k: v for k, v in state.items() if v}
	print('after', state)

	#### Write new state
	if state != orig_state:
		# FIXME: error checking
		if state:
			log.info(f'Writing new state DB {state_db_name}')
			os.makedirs(os.path.dirname(state_db_name), exist_ok=True)
			with gzip.open(state_db_name + PARTIAL_SUFFIX, 'wt') as fd:
				json.dump(state, fd, indent=4)
				os.fdatasync(fd)
			os.rename(state_db_name + PARTIAL_SUFFIX, state_db_name)
		else:
			log.info(f'Empty state; removing {state_db_name}')
			os.unlink(state_db_name)

		def flatten_state(state):
			# Flatten multiple states to one folder state
			if any(0 < s.get('state', 0) < WATCHED_MAX for s in state.values()):
				return 2 ** (WATCHED_STEPS // 2) - 1
			if any(s.get('state', 0) == 0 for s in state.values()):
				return 0
			return WATCHED_MAX

		# Propagate state upwards
		flat = flatten_state(state)
		if flat != flatten_state(orig_state):
			up_state_name = os.path.join(os.path.dirname(path), QUEUE_DIR_NAME, str(uuid.uuid4()))
			log.debug(f'Propagating new state upwards as {up_state_name}')
			os.makedirs(os.path.dirname(up_state_name), exist_ok=True)
			# FIXME: Error checking
			with open(up_state_name, 'w') as fd:
				json.dump({"name": os.path.basename(path), "state": flat}, fd, indent=4)
				os.fdatasync(fd)

	for update_name in state_queue:
		try:
			log.debug(f'Removing {update_name}')
			os.unlink(update_name)
		except OSError as e:
			log.error(f'Removing {update_name}: {str(e)}')


roots = [os.path.abspath(root) for root in sys.argv[1:]]
if not roots:
	print('Must specify at least one root')
	exit(1)
watcher = Watcher(roots)
for root in roots:
	watcher.push(root, recursive=True)

analyze_pool = Pool('analyze', threads=4)
scan_dirty = {}
for event in watcher.events(timeout=1):
	if event:
		log.debug(f'Got event: {event}')

	do_state_queue = []
	now = time.time()

	if event:
		if event.isdir and not event.hidden():
			# Case: path/ itself
			if event.evtype in {'modified'}:
				scan_dirty[event.path] = now

			# Case: path/foo/
			if event.evtype in {'created', 'deleted'}:
				watcher.push(os.path.dirname(event.path))

		if not event.isdir:
			# Case: path/.fabella/queue/foo
			if os.path.dirname(event.path).endswith('/' + QUEUE_DIR_NAME):
				if event.evtype in {'closed'}:
					do_state_queue.append(os.path.dirname(os.path.dirname(os.path.dirname(event.path))))

			# Case: path/.fabella/state.json.gz
			elif event.path.endswith('/' + STATE_DB_NAME):
				do_state_queue.append(os.path.dirname(os.path.dirname(event.path)))

			# Case: path/.fabella/index.json.gz
			elif event.path.endswith('/' + INDEX_DB_NAME):
				watcher.push(os.path.dirname(os.path.dirname(event.path)))

			# Case: path/.fabella/covers.zip
			elif event.path.endswith('/' + COVER_DB_NAME):
				watcher.push(os.path.dirname(os.path.dirname(event.path)))

			# Case: path/.cover.jpg
			elif event.path.endswith('/' + FOLDER_COVER_FILE):
				watcher.push(os.path.dirname(os.path.dirname(event.path)))

			# Case: path/foo.bar
			else:
				# Only do something for file extensions we care about
				if event.path.endswith(VIDEO_EXTENSIONS):
					watcher.push(os.path.dirname(event.path))

	scan_now = []
	for path, age in list(scan_dirty.items()):
		if now - age > EVENT_COOLDOWN_SECONDS:
			del scan_dirty[path]
			scan_now.append(path)

	for path in scan_now:
		scan(path, pool=analyze_pool)

	for path in do_state_queue:
		process_state_queue(path)

	#if not dirty:
	#	break
