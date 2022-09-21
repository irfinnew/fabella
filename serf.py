#! /usr/bin/env python3
# Fabella - Simple, elegant video library and player.
#
# Copyright 2020-2022 Marcel Moreaux.
# Licensed under GPL v2.0, or (at your option) any later version.
# (SPDX GPL-2.0-or-later) See LICENSE file for details.

import os
import sys

import dbs

if len(sys.argv) < 2 or sys.argv[1] != 'find-tagged':
	print(f'Usage: {sys.argv[0]} find-tagged')
	print(f'  Recursively lists all tagged files')
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

process('')
