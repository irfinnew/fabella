#! /usr/bin/env python

# ffmpeg -ss '05:00' -i 01.\ A\ Princess\ an\ Elf\ and\ a\ Demon\ Walk\ Into\ a\ Bar.mkv -vf  "thumbnail,scale=640:360" -frames:v 1 thumb.png 
# https://superuser.com/questions/538112/meaningful-thumbnails-for-a-video-using-ffmpeg
# https://stackoverflow.com/questions/41610167/specify-percentage-instead-of-time-to-ffmpeg

COVER_WIDTH = 320
COVER_HEIGHT = 200
COVERS_DB_NAME = '.fabella/covers.zip'
THUMB_OFFSET = 0.25
VIDEO_EXTENSIONS = ['mkv', 'mp4', 'webm', 'avi', 'wmv']

import sys
import os
import io
import zipfile
import enzyme
import subprocess
from PIL import Image, ImageOps

from logger import Logger

log = Logger(module='crawl', color=Logger.Magenta)


# Takes file-like object, reads image from it, scales, encodes to JPEG, returns bytes
def scaled_cover(fd):
	with Image.open(fd) as cover:
		cover = cover.convert('RGB')
		cover = ImageOps.fit(cover, (COVER_WIDTH, COVER_HEIGHT))

	buffer = io.BytesIO()
	cover.save(buffer, format='JPEG', quality=90, optimize=True)
	return buffer.getvalue()


def find_file_cover(path):
	# FIXME: maybe don't
	if path.endswith(('.jpg', '.jpeg', '.png')):
		log.info(f'Thumbnailing image file {path}')
		with open(path, 'rb') as fd:
			return scaled_cover(fd)

	if path.endswith('.mkv'):
		with open(path, 'rb') as fd:
			mkv = enzyme.MKV(fd)
			for a in mkv.attachments:
				# FIXME: just uses first jpg attachment it sees; check filename!
				if a.mimetype == 'image/jpeg':
					log.info(f'Found embedded cover in {path}')
					return scaled_cover(a.data)

	# If we got here, no embedded cover was found, generate thumbnail
	if path.endswith(tuple('.' + e for e in VIDEO_EXTENSIONS)):
		log.info(f'Generating thumbnail for {path}')
		sp = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=duration', '-of', 'default=nokey=1:noprint_wrappers=1', path], capture_output=True)
		if sp.returncode:
			print(sp.stderr.decode('utf-8'))
			exit(1)

		duration = float(sp.stdout)
		duration = str(int(duration * THUMB_OFFSET))

		sp = subprocess.run(['ffmpeg', '-ss', duration, '-i', path, '-vf', 'thumbnail', '-frames:v', '1', '-f', 'apng', '-'], capture_output=True)
		if sp.returncode:
			print(sp.stderr.decode('utf-8'))
			exit(1)
		return scaled_cover(io.BytesIO(sp.stdout))

	return None


def find_folder_cover(path):
	cover_file = os.path.join(path, 'cover.jpg')
	if not os.path.isfile(cover_file):
		return None

	with open(cover_file, 'rb') as fd:
		log.info(f'Found cover {cover_file}')
		return scaled_cover(fd)


def scan(path):
	log.info(f'Processing {path}')
	covers_db_name = (os.path.join(path, COVERS_DB_NAME))
	os.makedirs(os.path.dirname(covers_db_name), exist_ok=True)
	covers_db = zipfile.ZipFile(covers_db_name, 'w')

	dirs = []
	for isfile, name in sorted((not de.is_dir(), de.name) for de in os.scandir(path)):
		if name.startswith('.'):
			continue
		# FIXME: muh
		if name == 'cover.jpg':
			continue

		if isfile:
			cover = find_file_cover(os.path.join(path, name))
		else:
			cover = find_folder_cover(os.path.join(path, name))
			dirs.append(name)

		if cover:
			covers_db.writestr(name, cover)

	covers_db.close()

	for d in dirs:
		scan(os.path.join(path, d))

scan(sys.argv[1])
