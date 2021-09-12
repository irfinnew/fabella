#! /usr/bin/env python

COVER_WIDTH = 320
COVER_HEIGHT = 200
COVERS_DB_NAME = '.fabella/covers.zip'
COVERS_DB_SUFFIX = '.part'
THUMB_VIDEO_POSITION = 0.25
VIDEO_EXTENSIONS = ['mkv', 'mp4', 'webm', 'avi', 'wmv']
FOLDER_COVER_FILE = 'cover.jpg'
EXIF_MAKERNOTE_TAG = 37500
FABELLA_EXIF_TAG = 'FABELLA_CACHE_TAGS: '
TAG_VERSION = 1

import sys
import os
import io
import ast
import stat
import zipfile
import enzyme
import subprocess
import PIL.Image
import PIL.ImageOps
import PIL.ExifTags

from logger import Logger

log = Logger(module='crawl', color=Logger.Magenta)



def run_command(command):
	try:
		return subprocess.run(command, capture_output=True, check=True)
	except subprocess.CalledProcessError as e:
		log.error(f'Command returned {e.returncode}: {command}')
		for line in e.stderr.decode('utf-8').splitlines():
			log.error(line)
		raise



class CoverError(Exception):
	pass



class Cover:
	def __init__(self, name, parent_path, *, scaled_cover_image=None):
		self.name = name
		self.path = os.path.join(parent_path, name)
		self.scaled_cover_image = scaled_cover_image

		if scaled_cover_image:
			self.tag_version, self.isdir, self.size, self.mtime, self.dimensions = self.parse_exiftag_from_image(self.scaled_cover_image)
		else:
			self.isdir, self.size, self.mtime = self.get_attrs()
			self.tag_version = TAG_VERSION
			self.dimensions = f'{COVER_WIDTH}x{COVER_HEIGHT}'


	def get_attrs(self):
		"""Returns (isdir, size, mtime) file attrs used to determine cover staleness."""
		stat_data = os.stat(self.path)

		if stat.S_ISDIR(stat_data.st_mode):
			# Folder, check cover file in it instead
			try:
				stat_data = os.stat(os.path.join(self.path, FOLDER_COVER_FILE))
				return (True, stat_data.st_size, stat_data.st_mtime_ns)
			except FileNotFoundError:
				return (True, None, None)
		else:
			return (False, stat_data.st_size, stat_data.st_mtime_ns)


	@property
	def fabella_tag(self):
		"""Return the EXIF tag *content* that will determine dirtyness."""
		tags = {'version': self.tag_version, 'isdir': self.isdir, 'size': self.size, 'mtime': self.mtime, 'dimensions': self.dimensions}
		return FABELLA_EXIF_TAG + repr(tags)


	@property
	def exiftag(self):
		"""Return the full EXIF tag that will determine dirtyness."""
		exif = PIL.Image.Exif()
		exif[EXIF_MAKERNOTE_TAG] = self.fabella_tag
		return exif


	def parse_exiftag(self, exif):
		empty_tags = (None, None, None, None, None)
		"""Take EXIF tag, parse it, return attrs or tuple of Nones."""
		if exif is None:
			return empty_tags

		try:
			tag = exif[EXIF_MAKERNOTE_TAG]
		except KeyError:
			log.warning(f'EXIF tag not found in cover image for {self.name}')
			return empty_tags

		if not tag.startswith(FABELLA_EXIF_TAG):
			log.warning(f'EXIF tag doesn\'t start with {FABELLA_EXIF_TAG} in cover image for {self.name}')
			return empty_tags
		tag = tag[len(FABELLA_EXIF_TAG):]

		try:
			tag = ast.literal_eval(tag)
			# FIXME: perhaps use .get() to allow for missing tags?
			return (int(tag['version']), bool(tag['isdir']), int(tag['size']), int(tag['mtime']), tag['dimensions'])
		except (KeyError, ValueError) as e:
			log.warning(f'Error parsing EXIF tag in cover image for {self.name}: {e}')
			return empty_tags


	def parse_exiftag_from_image(self, image):
		"""Take EXIF tag from jpeg bytestr, parse it, return attrs or tuple of Nones."""
		try:
			with PIL.Image.open(io.BytesIO(image)) as img:
				return self.parse_exiftag(img.getexif())
		except PIL.UnidentifiedImageError:
			return self.parse_exiftag(None)


	def scale_encode(self, fd):
		"""Takes file-like object, reads image from it, scales, encodes to JPEG, returns bytes."""
		try:
			with PIL.Image.open(fd) as cover:
				cover = cover.convert('RGB')
				cover = PIL.ImageOps.fit(cover, (COVER_WIDTH, COVER_HEIGHT))
		except PIL.UnidentifiedImageError as e:
			raise CoverError(f'Loading image for {self.path}: {str(e)}')

		buffer = io.BytesIO()
		cover.save(buffer, format='JPEG', quality=90, optimize=True, exif=self.exiftag)
		return buffer.getvalue()


	def get_folder_cover(self):
		"""Find cover image for folder, scale, return bytes."""
		cover_file = os.path.join(self.path, FOLDER_COVER_FILE)
		if not os.path.isfile(cover_file):
			raise CoverError(f'Cover image {cover_file} not found')

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
			except enzyme.exceptions.Error as e:
				raise CoverError(f'Processing {self.path}: {str(e)}')

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
				raise CoverError(f'Processing {self.path}: Command returned error')

		raise CoverError(f'Processing {self.path}: unknown filetype to generate cover image from')


	def get_scaled_cover_image(self):
		"""Return cached cover image bytes. If not cached, find, scale, return bytes. None if unsuccessful."""
		if not self.scaled_cover_image:
			if self.isdir:
				self.scaled_cover_image = self.get_folder_cover()
			else:
				self.scaled_cover_image = self.get_file_cover()

		return self.scaled_cover_image


	def __eq__(self, other):
		if other is None:
			return False
		# Size/mtime might be missing for both; does not mean they're equal!
		if None in (self.tag_version, self.isdir, self.size, self.mtime, self.dimensions):
			return False
		return (self.tag_version, self.name, self.isdir, self.size, self.mtime, self.dimensions) == \
			(other.tag_version, other.name, other.isdir, other.size, other.mtime, other.dimensions)


	def __lt__(self, other):
		return self.name < other.name


	def __str__(self):
		return f'Cover({self.name}, version={self.tag_version}, isdir={self.isdir}, size={self.size}, mtime={self.mtime}, dimensions={self.dimensions})'


	def __repr__(self):
		return self.__str__()



def scan(path, errors):
	log.info(f'Processing {path}')
	covers_db_name = (os.path.join(path, COVERS_DB_NAME))
	os.makedirs(os.path.dirname(covers_db_name), exist_ok=True)

	try:
		with zipfile.ZipFile(covers_db_name, 'r') as covers_db:
			log.info(f'Found existing covers DB {covers_db_name}')
			existing_covers = {}
			for cover_name in covers_db.namelist():
				existing_covers[cover_name] = Cover(cover_name, path, scaled_cover_image=covers_db.read(cover_name))
	except FileNotFoundError:
		existing_covers = {}
	except zipfile.BadZipFile as e:
		log.error(f'Existing covers DB {covers_db_name} is broken: {str(e)}')
		existing_covers = {}

	current_covers = {}
	for name in sorted(os.listdir(path)):
		if name.startswith('.'):
			continue
		if name == FOLDER_COVER_FILE:
			continue

		current_covers[name] = Cover(name, path)

	if existing_covers == current_covers:
		log.info(f'Existing covers DB {covers_db_name} is up to date, skipping')
		new_covers = sorted(current_covers.values())
	else:
		new_covers = []
		for name, cover in current_covers.items():
			if existing_covers.get(name) == cover:
				log.info(f'Cover for {name} is up to date, reusing')
				new_covers.append(existing_covers[name])
			else:
				new_covers.append(cover)
		new_covers = sorted(new_covers)

		# Write new covers file
		covers_db = zipfile.ZipFile(covers_db_name + COVERS_DB_SUFFIX, 'w')
		for cover in new_covers:
			try:
				covers_db.writestr(cover.name, cover.get_scaled_cover_image())
			except CoverError as e:
				log.error(str(e))
				errors.append(cover.path)
		covers_db.close()
		os.rename(covers_db_name + COVERS_DB_SUFFIX, covers_db_name)

	for cover in new_covers:
		if cover.isdir:
			scan(cover.path, errors)



errors = []
scan(sys.argv[1], errors)

if errors:
	print()
	print('Errors processing the following files:')
	for e in errors:
		print(' ', e)
