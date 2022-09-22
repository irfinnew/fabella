#! /usr/bin/env python3
# Fabella - Simple, elegant video library and player.
#
# Copyright 2020-2022 Marcel Moreaux.
# Licensed under GPL v2.0, or (at your option) any later version.
# (SPDX GPL-2.0-or-later) See LICENSE file for details.

import os
import sys
import uuid

import dbs

if len(sys.argv) < 2 or sys.argv[1] not in {'find-tagged', 'mark-seen'}:
	print(f'Usage:')
	print(f'  {sys.argv[0]} find-tagged          Recursively lists all tagged files.')
	print(f'  {sys.argv[0]} mark-seen <file(s)>  Mark files as seen.')
	exit(1)

def escape(path):
	return '"' + path.replace('\\', '\\\\').replace('"', '\\"') + '"'

def process(path):
	index_db_name = os.path.join(path, dbs.INDEX_DB_NAME)
	index = dbs.json_read(index_db_name, dbs.INDEX_DB_SCHEMA)

	state_db_name = os.path.join(path, dbs.STATE_DB_NAME)
	state = dbs.json_read(state_db_name, dbs.STATE_DB_SCHEMA)

	for item in index['files']:
		if state[item['name']].get('tagged', False):
			if item['isdir']:
				process(os.path.join(path, item['name']))
			else:
				print(escape(os.path.join(path, item['name'])))

if sys.argv[1] == 'find-tagged':
	process('')

if sys.argv[1] == 'mark-seen':
	count = 0
	for f in sys.argv[2:]:
		path, file = os.path.split(f)
		queue_dir_name = os.path.join(path, dbs.QUEUE_DIR_NAME)
		os.makedirs(queue_dir_name, exist_ok=True)
		os.chmod(queue_dir_name, 0o775)
		state_name = os.path.join(queue_dir_name, str(uuid.uuid4()))
		dbs.json_write(state_name, {file: {'position': 1}})
		count += 1
	print(f'Marked {count} files as seen.')
