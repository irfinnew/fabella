#! /usr/bin/env python3
# Fabella - Simple, elegant video library and player.
#
# Copyright 2020-2023 Marcel Moreaux.
# Licensed under GPL v2.0, or (at your option) any later version.
# (SPDX GPL-2.0-or-later) See LICENSE file for details.

COVER_META_TAG = '.meta'
COVER_WIDTH = 320
COVER_HEIGHT = 200

THUMB_VIDEO_POSITION = 0.25
FOLDER_COVER_FILE = '.cover.jpg'
MKV_COVER_FILE = 'cover.jpg'
EVENT_COOLDOWN_SECONDS = 1



import sys
import os
import io
import ast
import stat
import json
import time
import zipfile
import enzyme
import hashlib
import logging
import argparse
import subprocess
import collections
import multiprocessing
import PIL.Image
import PIL.ImageOps

import loghelper
import colorpicker
from watch import Watcher
from worker import Pool
import dbs

loghelper.set_up_logging(console_level=loghelper.VERBOSE, file_level=loghelper.NOTSET, filename='clerk.log')
log = loghelper.get_logger('Clerk', loghelper.Color.Red)
# Enzyme spams the logs with stuff we don't care about
logging.getLogger('enzyme').setLevel(logging.CRITICAL)
log.info('Starting Clerk.')


# Parse command line arguments
parser = argparse.ArgumentParser(description='Fabella Clerk. Watches video library for changes, updates indices and state.')
parser.add_argument('--once', '-o', action='store_true', help="Don't watch the library; just update everything and quit.")
parser.add_argument('--skip-initial', '-s', action='store_true', help="Skip the initial consistency scan of the library; just watch it for changes.")
parser.add_argument('path', type=str, help='Path to video library')
args = parser.parse_args()


try:
	import setproctitle
	setproctitle.setproctitle(' '.join(['clerk'] + sys.argv[1:]))
except ModuleNotFoundError:
	log.warning("Couldn't load setproctitle module; not changing process name")


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


def scale_cover(fd, path):
	"""Takes file-like object, reads image from it, scales, encodes to JPEG.
	Also determines representative color. Returns (color, jpeg bytes)."""
	try:
		with PIL.Image.open(fd) as cover:
			cover = cover.convert('RGB')
			cover = PIL.ImageOps.fit(cover, (COVER_WIDTH, COVER_HEIGHT))
	except PIL.UnidentifiedImageError as e:
		raise TileError(f'Loading image for {path}: {str(e)}')

	# Choose a representative color from the cover image
	color = '#' + ''.join(f'{c:02x}' for c in colorpicker.pick(cover))

	buffer = io.BytesIO()
	cover.save(buffer, format='JPEG', quality=90, subsampling=0, optimize=True)
	return color, buffer.getvalue()


def extract_duration(path):
	try:
		sp = run_command(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=nokey=1:noprint_wrappers=1', path])
		return float(sp.stdout)
	except (subprocess.CalledProcessError, ValueError) as e:
		log.error(f'Getting video duration for {path}: {e}')
		return None


def generate_thumbnail(path, duration=None):
	if path.endswith(dbs.VIDEO_EXTENSIONS):
		log.info(f'Generating thumbnail for {path}')
		try:
			if duration is None:
				duration = extract_duration(path)

			duration = str(duration * THUMB_VIDEO_POSITION)
			sp = run_command(['ffmpeg', '-ss', duration, '-threads', '1', '-i', path,
				'-vf', 'scale=1280:720,thumbnail', '-frames:v', '1', '-f', 'apng', '-'])
			color, jpeg = scale_cover(sp.stdout, path)
			return duration, jpeg, color
		except subprocess.CalledProcessError:
			raise TileError(f'Processing {path}: Command returned error')


def get_info_image(path):
	if not os.path.isfile(path):
		raise TileError(f'Cover image {path} not found')

	with open(path, 'rb') as fd:
		log.info(f'Found cover {path}')
		color, jpeg = scale_cover(fd, path)
		return 0, jpeg, color


def get_info_matroska(path):
	try:
		with open(path, 'rb') as fd:
			mkv = enzyme.MKV(fd)
			duration = mkv.info.duration
			duration = round(duration.seconds + duration.microseconds / 1000000)
			for a in mkv.attachments:
				if a.mimetype == 'image/jpeg' and a.filename == MKV_COVER_FILE:
					log.info(f'Found embedded cover in {path}')
					color, jpeg = scale_cover(a.data, path)
					return duration, jpeg, color
	except (OSError, enzyme.exceptions.Error) as e:
		raise TileError(f'Processing {path}: {e}')

	# If we got here, no embedded cover was found, generate thumbnail
	return generate_thumbnail(path, duration=duration)


# returns (duration, jpeg cover image, tile color)
def get_video_info(path):
	_, ext = os.path.splitext(path)
	ext = ext.lower()

	if ext in ['.jpg', '.jpeg', '.png']:
		return get_info_image(path)
	if ext == '.mkv':
		return get_info_matroska(path)
	
	log.warning(f'Getting video info: unsupported filetype: {path}')
	return (0, None, None)


class BaseTile:
	def to_json(self):
		"""Return the attributes as json."""
		data = {
			'name': self.name,
			'isdir': self.isdir,
			'fingerprint': self.fingerprint,
			'tile_color': self.tile_color,
		}
		if not self.isdir:
			data['duration'] = self.duration

		return data


	def __eq__(self, other):
		if other is None:
			return False
		return (self.name, self.isdir, self.fingerprint) == \
			(other.name, other.isdir, other.fingerprint)


	def __lt__(self, other):
		return self.sortkey < other.sortkey


	def analyze(self):
		duration, image, color = get_video_info(self.cover_source_path())
		self.duration = duration
		self.cover_image = image
		self.tile_color = color


	def cover_source_path(self):
		if self.isdir:
			return os.path.join(self.full_path, FOLDER_COVER_FILE)
		else:
			return self.full_path


	@property
	def sortkey(self):
		simplename = os.path.splitext(self.name)[0].strip().casefold()
		for a in ['a ', 'an ', 'the ', 'de ', 'een ']:
			if simplename.startswith(a):
				simplename = simplename[len(a):].strip()
				break
		# Sort on case-insensitive simplified name, then raw name (for deterministic ordering).
		return (simplename, self.name)


	def __str__(self):
		return f'{self.__class__.__name__}({self.name}, isdir={self.isdir}, fingerprint={self.fingerprint})'


	def __repr__(self):
		return self.__str__()



class IndexedTile(BaseTile):
	def __init__(self, path, data):
		self.name = data['name']
		self.isdir = data['isdir']
		self.fingerprint = data['fingerprint']
		self.tile_color = data['tile_color']
		self.duration = None if self.isdir else data['duration']

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
			st = os.stat(self.full_path)
		except OSError as e:
			# Can't stat the file we were just created for? Fatal.
			raise ValueError(repr(e))

		if stat.S_ISDIR(st.st_mode):
			self.isdir = True
			# Folder, check cover image in it instead
			try:
				st = os.stat(os.path.join(self.full_path, FOLDER_COVER_FILE))
				self.fingerprint = f'inode={st.st_ino}:size={st.st_size}:mtime={st.st_mtime_ns}'
			except FileNotFoundError:
				self.fingerprint = None
		else:
			self.isdir = False
			self.fingerprint = f'inode={st.st_ino}:size={st.st_size}:mtime={st.st_mtime_ns}'

	def valid(self):
		"""True if the tile is "valid". Meaning the name/filetype/etc checks out."""
		if self.name.startswith('.'):
			return False

		if self.isdir:
			return True

		# File
		return self.name.endswith(dbs.VIDEO_EXTENSIONS)



class Meta:
	def __init__(self, *, version):
		self.version = version

	@classmethod
	def from_json(cls, data):
		return cls(version=data['meta']['version'])

	@classmethod
	def from_tiles(cls, tiles):
		return cls(version=dbs.INDEX_META_VERSION)

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
		tiles = [[t.name, t.isdir, t.fingerprint] for t in tiles]
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

	from util import stopwatch
	stopwatch()

	index_db_name = os.path.join(path, dbs.INDEX_DB_NAME)
	orig_index = dbs.json_read(index_db_name, dbs.INDEX_DB_SCHEMA)

	#### Check meta version, extract file info index
	indexes = []
	indexed_meta = None
	if orig_index:
		try:
			indexed_meta = Meta.from_json(orig_index)
			if indexed_meta.version == dbs.INDEX_META_VERSION:
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
	cover_db_name = os.path.join(path, dbs.COVER_DB_NAME)
	cover_db_fingerprint = None
	try:
		with zipfile.ZipFile(cover_db_name, 'r') as fd:
			log.debug(f'Found existing covers DB {cover_db_name}')
			cover_meta = json.loads(fd.read(COVER_META_TAG))
			if cover_meta['version'] != dbs.INDEX_META_VERSION:
				log.info(f'Existing {cover_db_name} outdated version, discarding')
			elif cover_meta['dimensions'] != f'{COVER_WIDTH}x{COVER_HEIGHT}':
				log.info(f'Existing {cover_db_name} has wrong cover dimensions, discarding')
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
	update_tiles = [tile for tile in real_tiles if tile.cover_needs_update]
	paths = [tile.cover_source_path() for tile in update_tiles]
	with multiprocessing.Pool() as pool:
		new_info = pool.map(get_video_info, paths)
	for tile, (duration, image, color) in zip(update_tiles, new_info):
		tile.duration = duration
		tile.cover_image = image
		tile.tile_color = color

	#### Write index
	if index_needs_update:
		dbs.json_write(index_db_name, Meta.full_json(real_tiles))

	#### Write covers
	# FIXME: error checking
	real_fingerprint = Meta.fingerprint(real_tiles)
	if cover_db_fingerprint == real_fingerprint:
		log.info(f'Existing cover DB {cover_db_name} is up to date, skipping')
	else:
		if real_tiles:
			log.info(f'Writing new cover DB {cover_db_name}')
			with zipfile.ZipFile(cover_db_name + dbs.NEW_SUFFIX, 'w') as fd:
				meta = {
					'version': dbs.INDEX_META_VERSION,
					'dimensions': f'{COVER_WIDTH}x{COVER_HEIGHT}',
					'fingerprint': real_fingerprint,
				}
				fd.writestr(COVER_META_TAG, json.dumps(meta, indent='\t'))

				# Write cover images
				for tile in real_tiles:
					fd.writestr(tile.name, tile.cover_image or b'')
			os.rename(cover_db_name + dbs.NEW_SUFFIX, cover_db_name)
		else:
			if os.path.isfile(cover_db_name):
				log.info(f'No files here, removing {cover_db_name}')
				os.remove(cover_db_name)
			else:
				log.debug(f'No files here, not writing {cover_db_name}')
	stopwatch('updating covers')



def process_state_queue(path, roots):
	if not os.path.isdir(path):
		log.debug(f'{path} is gone, nothing to do')
		return

	log.info(f'Processing state events for {path}')

	queue_dir_name = os.path.join(path, dbs.QUEUE_DIR_NAME)
	state_db_name = os.path.join(path, dbs.STATE_DB_NAME)

	new = not os.path.isdir(queue_dir_name)

	# Ensure queue dir exists
	os.makedirs(queue_dir_name, exist_ok=True)
	os.chmod(queue_dir_name, 0o775)

	#### Load original state
	previous_state = dbs.json_read(state_db_name, dbs.STATE_DB_SCHEMA)
	# Deep copy for later
	orig_state = {n: dict(s) for n, s in previous_state.items()}

	if new:
		# This is a new directory. Setting orig_state = None will force a propagation
		# of state to the parent (notably, for position: 1).
		orig_state = None

	# Load filenames from index
	index = dbs.json_read([path, dbs.INDEX_DB_NAME], dbs.INDEX_DB_SCHEMA, default={'files': []})['files']
	new_state = {}

	# Match index to previous state on name AND fingerprint
	remaining = []
	for idx in index:
		name = idx['name']
		state = previous_state.get(name, {})
		fp = state.get('fingerprint', None)
		if fp is not None and fp == idx['fingerprint']:
			new_state[name] = state
			previous_state.pop(name)
			log.debug(f'Found name+fingerprint match in previous state for "{name}"')
		else:
			remaining.append(idx)

	# Match index to previous state on just fingerprint; these were probably renamed
	index = remaining
	remaining = []
	duplicate_fps = {None} \
		| {fp for fp, c in collections.Counter([i.get('fingerprint') for i in index]).items() if c > 1} \
		| {fp for fp, c in collections.Counter([s.get('fingerprint') for s in previous_state.values()]).items() if c > 1}
	if duplicate_fps != {None}:
		log.warning(f'Duplicate fingerprints will be ignored: {duplicate_fps}')
	previous_state_by_fp = {s['fingerprint']: (n, s) for n, s in previous_state.items() if s.get('fingerprint') not in duplicate_fps}
	for idx in index:
		name = idx['name']
		fp = idx.get('fingerprint')
		if fp in duplicate_fps:
			remaining.append(idx)
			continue
		try:
			oldname, state = previous_state_by_fp[fp]
		except KeyError:
			remaining.append(idx)
			continue
		else:
			new_state[name] = state
			previous_state.pop(oldname)
			log.info(f'Found fingerprint match in previous state for "{name}"; renamed from "{oldname}"')

	# Match index to previous state on just name; these were probably updated
	index = remaining
	remaining = []
	for idx in index:
		name = idx['name']
		fp = idx.get('fingerprint')
		try:
			state = previous_state[name]
		except KeyError:
			new_state[name] = {} if fp is None else {'fingerprint': fp}
			log.info(f'New file "{name}" has no match in previous state')
		else:
			#log.info(f'Found name match in previous state for "{name}" fingerprint changed from {state.get("fingerprint")} to {fp}')
			if fp is None:
				state.pop('fingerprint', None)
			else:
				state['fingerprint'] = fp
			new_state[name] = state
			previous_state.pop(name)

	# Remaining entries from previous state are unmatched; they were probably removed
	for n, s in previous_state.items():
		log.info(f'"{n}" in previous state was not matched to any current file; ignored')

	#### Collect any state update files
	state_queue = {}
	try:
		for f in os.scandir(queue_dir_name):
			try:
				if not f.is_file() or f.path.endswith(dbs.NEW_SUFFIX):
					continue
				updates = dbs.json_read(f.path, dbs.STATE_UPDATE_SCHEMA, default={})
				state_queue[f.stat().st_mtime, f.path] = updates
			except OSError as e:
				log.error(f'Reading {f.path}: {str(e)}')
	except OSError as e:
		log.error(f'Reading {queue_dir_name}: {str(e)}')
		state_queue = {}

	#### Apply the requested state updates
	for meta, updates in sorted(state_queue.items()):
		for name, update in updates.items():
			log.debug(f'State update for {name}: {update}')

			if name not in new_state:
				new_state[name] = {}
			this_state = new_state[name]

			if 'position' in update:
				if update['position'] > 0:
					this_state['position'] = update['position']
				else:
					this_state.pop('position', None)

			if 'tagged' in update:
				if update['tagged']:
					this_state['tagged'] = True
				else:
					this_state.pop('tagged', None)

	#### Write new state
	if new_state == orig_state:
		log.debug('State unchanged, not updating.')
	else:
		if new_state:
			dbs.json_write(state_db_name, new_state)
		else:
			log.debug(f'Empty state; removing {state_db_name}')
			try:
				os.unlink(state_db_name)
			except FileNotFoundError:
				pass
			except OSError as e:
				log.error(f'Removing {state_db_name}: {str(e)}')

		# Propagate state upwards (but not outside root dir)
		if path not in roots:
			flat = {'tagged': any(s.get('tagged', False) for s in new_state.values())}

			if any(0 < s.get('position', 0) < 1 for s in new_state.values()):
				flat['position'] = 0.5
			elif any(s.get('position', 0) == 0 for s in new_state.values()):
				flat['position'] = 0
			else:
				flat['position'] = 1

			dbs.json_write([os.path.dirname(path), dbs.QUEUE_DIR_NAME, ...], {os.path.basename(path): flat})

	for update_mtime, update_name in state_queue.keys():
		try:
			log.debug(f'Removing {update_name}')
			os.unlink(update_name)
		except OSError as e:
			log.error(f'Removing {update_name}: {str(e)}')



#roots = [os.path.abspath(root) for root in sys.argv[1:]]
roots = [os.path.abspath(args.path)]
if not roots:
	print('Must specify at least one root')
	exit(1)
watcher = Watcher(roots)

if not args.skip_initial:
	for root in roots:
		watcher.push(root, recursive=True)

analyze_pool = Pool('analyze', threads=1)
scan_dirty = {}
state_dirty = {}
for event in watcher.events(timeout=EVENT_COOLDOWN_SECONDS):
	if event:
		log.debug(f'Got event: {event}')

	now = time.time()

	if event:
		if event.isdir and not event.hidden():
			# Case: path/ itself
			if event.evtype in {'modified', 'created'}:
				scan_dirty[event.path] = now

			# Case: path/foo/
			if event.evtype in {'created', 'deleted'}:
				watcher.push(os.path.dirname(event.path))

		if not event.isdir:
			# Case: path/.fabella/queue/foo
			if os.path.dirname(event.path).endswith('/' + dbs.QUEUE_DIR_NAME):
				if not event.path.endswith(dbs.NEW_SUFFIX):
					state_dirty[os.path.dirname(os.path.dirname(os.path.dirname(event.path)))] = now

			# Case: path/.fabella/state.json.gz
			elif event.path.endswith('/' + dbs.STATE_DB_NAME):
				state_dirty[os.path.dirname(os.path.dirname(event.path))] = now

			# Case: path/.fabella/index.json.gz
			elif event.path.endswith('/' + dbs.INDEX_DB_NAME):
				watcher.push(os.path.dirname(os.path.dirname(event.path)))

			# Case: path/.fabella/covers.zip
			elif event.path.endswith('/' + dbs.COVER_DB_NAME):
				watcher.push(os.path.dirname(os.path.dirname(event.path)))

			# Case: path/.cover.jpg
			elif event.path.endswith('/' + FOLDER_COVER_FILE):
				watcher.push(os.path.dirname(os.path.dirname(event.path)))

			# Case: path/foo.bar
			else:
				# Only do something for file extensions we care about
				if event.path.endswith(dbs.VIDEO_EXTENSIONS):
					watcher.push(os.path.dirname(event.path))

	# Items needing a full scan (index/cover update)
	for path, age in list(scan_dirty.items()):
		# Only process index events after a little while. In case a file is being
		# written, this postpones scanning until the file is completely done.
		if now - age > EVENT_COOLDOWN_SECONDS:
			del scan_dirty[path]
			scan(path, pool=analyze_pool)
			state_dirty[path] = now

	# Items needing a state update
	for path, age in list(state_dirty.items()):
		# Don't think we need a cooldown for state updates.
		#if now - age > EVENT_COOLDOWN_SECONDS:
		del state_dirty[path]
		process_state_queue(path, roots)

	if args.once and not scan_dirty and not state_dirty:
		break
