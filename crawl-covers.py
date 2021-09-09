#! /usr/bin/env python

# ffmpeg -ss '05:00' -i 01.\ A\ Princess\ an\ Elf\ and\ a\ Demon\ Walk\ Into\ a\ Bar.mkv -vf  "thumbnail,scale=640:360" -frames:v 1 thumb.png 
# https://stackoverflow.com/questions/41610167/specify-percentage-instead-of-time-to-ffmpeg

COVER_WIDTH = 320
COVER_HEIGHT = 200
COVERS_DB_NAME = '.fabella/covers.zip'
THUMB_SEEK = '07:00'

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
	if path.endswith('.mkv'):
		with open(path, 'rb') as fd:
			mkv = enzyme.MKV(fd)
			for a in mkv.attachments:
				# FIXME: just uses first jpg attachment it sees; check filename!
				if a.mimetype == 'image/jpeg':
					log.debug(f'Found embedded cover in {path}')
					return scaled_cover(a.data)

	# If we got here, no embedded cover was found, generate thumbnail
	if path.endswith(('.mkv', '.mp4')):
		log.debug(f'Generating thumbnail for {path}')
		sp = subprocess.run(['ffmpeg', '-ss', THUMB_SEEK, '-i', path, '-vf', 'thumbnail', '-frames:v', '1', '-f', 'apng', '-'], capture_output=True, check=True)
		return scaled_cover(io.BytesIO(sp.stdout))

	return None


def find_folder_cover(path):
	cover_file = os.path.join(path, 'cover.jpg')
	if not os.path.isfile(cover_file):
		return None

	with open(cover_file, 'rb') as fd:
		log.debug(f'Found cover {cover_file}')
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
