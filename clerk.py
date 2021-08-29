#! /usr/bin/env python3

import os
import sys
import tarfile
import PIL.Image, PIL.ImageOps

from logger import Logger
import config

cover_size = (320, 200)

log = Logger(module='Main', color=Logger.Red)

def scan_dir(path):
	log.info(f'Processing {path}')
	dirs = []
	files = []
	for f in os.listdir(path):
		if f.startswith('.') or f in config.tile.thumb_dirs + config.tile.thumb_files:
			continue
		if os.path.isdir(os.path.join(path, f)):
			dirs.append(f)
		else:
			files.append(f)

	fabella_dir = os.path.join(path, '.fabella')
	if not isdir(fabella_dir):
		log.debug(f'Creating {fabella_dir}')
		os.mkdir(fabella_dir)

	tarfile.open(

	for d in dirs:
		for c in config.tile.thumb_files:
			cover_file = os.path.join(path, d, c)
			if os.path.isfile(cover_file):
				log.debug(f'Found {cover_file}')
				cover_full = PIL.Image.open(cover_file).convert('RGB')
				cover = PIL.ImageOps.fit(cover_full, cover_size)
				cover.save(..., 'JPEG', quality=90)

	for f in files:
		...

	for d in dirs:
		scan_dir(os.path.join(path, d))

scan_dir(sys.argv[1])
