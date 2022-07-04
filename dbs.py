# Fabella - Simple, elegant video library and player.
#
# Copyright 2020-2021 Marcel Moreaux.
# Licensed under GPL v2.0, or (at your option) any later version.
# (SPDX GPL-2.0-or-later) See LICENSE file for details.



INDEX_DB_NAME = '.fabella/index.json.gz'
INDEX_META_VERSION = 1

COVER_DB_NAME = '.fabella/covers.zip'

STATE_DB_NAME = '.fabella/state.json.gz'
QUEUE_DIR_NAME = '.fabella/queue'
NEW_SUFFIX = '.new'

VIDEO_FILETYPES = ['mkv', 'mp4', 'webm', 'avi', 'wmv']
VIDEO_EXTENSIONS = tuple('.' + ext for ext in VIDEO_FILETYPES)

STATE_DB_SCHEMA = {
	'*': {
		'position?': float,
		'tagged?': int,
	}
}
STATE_UPDATE_SCHEMA = STATE_DB_SCHEMA
INDEX_DB_SCHEMA = {
	'meta': { 'version': int },
	'files': [
		{
			'name': str,
			'isdir': bool,
			'src_size': (int,),
			'src_mtime': (int,),
			'tile_color?': (str,),
			'duration?': (int,),
		}
	],
}



import os
import gzip
import zlib
import json

import loghelper

log = loghelper.get_logger('DBs', loghelper.Color.Magenta)



class JsonValidationError(Exception):
	pass



def json_validate(data, schema, keyname=None):
	if isinstance(schema, dict):
		if not isinstance(data, dict):
			raise JsonValidationError(f'Expected object for {keyname}, not {data}')
		mandatory, optional, wildcard = {}, {}, None
		for k, v in schema.items():
			if k == '*':
				wildcard = v
			elif k.endswith('?'):
				optional[k[:-1]] = v
			else:
				mandatory[k] = v

		unknown = []
		for k, v in data.items():
			if k in mandatory:
				json_validate(v, mandatory[k], keyname=k)
				del mandatory[k]
			elif k in optional:
				json_validate(v, optional[k], keyname=k)
			elif wildcard is not None:
				json_validate(v, wildcard, keyname=k)
			else:
				unknown.append(k)

		if unknown:
			raise JsonValidationError(f'Extra keys {unknown} in {data}')
		if mandatory:
			raise JsonValidationError(f'Missing keys {list(mandatory.keys())} in {data}')

	elif isinstance(schema, list):
		if len(schema) != 1:
			raise ValueError(f'Schema list must have length one: {schema}')
		schema = schema[0]
		for idx, item in enumerate(data):
			json_validate(item, schema, keyname=str(idx))

	# Optional hack
	elif isinstance(schema, tuple):
		if len(schema) != 1:
			raise ValueError(f'Schema tuple must have length one: {schema}')
		schema = schema[0]
		if data is not None:
			json_validate(data, schema, keyname=keyname)

	elif schema in {str, bool, int, float}:
		if schema is float:
			schema = (int, float)
		if not isinstance(data, schema):
			raise JsonValidationError(f'Key {keyname}={data} should be type {schema}')
	else:
		raise KeyError(f'Unsupported schema type: {schema}')



def json_read(filename, schema, default=...):
	openfunc = gzip.open if filename.endswith('.gz') else open
	if default is ...:
		default = {}

	try:
		with openfunc(filename) as fd:
			log.debug(f'Reading DB {filename}')
			data = json.load(fd)
			json_validate(data, schema)

	except FileNotFoundError:
		log.info(f'Missing DB {filename}, using default')
		data = default

	except (OSError, EOFError, zlib.error, json.JSONDecodeError, JsonValidationError) as e:
		log.error(f'Reading {filename}: {str(e)}')
		data = default

	return data



def json_write(filename, data):
	openfunc = gzip.open if filename.endswith('.gz') else open
	new_filename = filename + NEW_SUFFIX

	log.info(f'Writing DB {filename}')
	try:
		os.makedirs(os.path.dirname(filename), exist_ok=True)
		with openfunc(new_filename, 'wt') as fd:
			json.dump(data, fd, indent=4)
			os.fdatasync(fd)

		if filename.endswith('.gz'):
			# UGHHHHHHHH.
			# sshfs messes up when a file is replaced, frequently causing clients to short-read
			# files, which then (rightly) trips up gzip. So we try padding the compressed stream
			# so the short-read still returns enough data for gzip.
			with open(new_filename, 'ab') as fd:
				fd.write(bytes(4096))

		# Atomic file replacement
		os.rename(new_filename, filename)
	except OSError as e:
		log.error(f'Writing {filename}: {str(e)}')
