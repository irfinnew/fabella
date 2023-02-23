#! /usr/bin/env python3
# Fabella - Simple, elegant video library and player.
#
# Copyright 2020-2023 Marcel Moreaux.
# Licensed under GPL v2.0, or (at your option) any later version.
# (SPDX GPL-2.0-or-later) See LICENSE file for details.

import os
import sys
import subprocess

import dbs

if len(sys.argv) < 2 or sys.argv[1] not in {'find-tagged', 'mark-seen', 'do-tagged'}:
	print(f'Usage:')
	print(f'  {sys.argv[0]} find-tagged          Recursively lists all tagged files.')
	print(f'  {sys.argv[0]} do-tagged <cmd> <args> \'*\' <args>')
	print(f'  {sys.argv[0]} mark-seen <file(s)>  Mark files as seen.')
	exit(1)


def escape(path):
	return '"' + path.replace('\\', '\\\\').replace('"', '\\"') + '"'


def find_tagged(path):
	index = dbs.json_read([path, dbs.INDEX_DB_NAME], dbs.INDEX_DB_SCHEMA)
	state = dbs.json_read([path, dbs.STATE_DB_NAME], dbs.STATE_DB_SCHEMA)

	files = []
	for item in index['files']:
		if state[item['name']].get('tagged', False):
			if item['isdir']:
				files += find_tagged(os.path.join(path, item['name']))
			else:
				files.append(os.path.join(path, item['name']))
	return files


if sys.argv[1] == 'find-tagged':
	for fn in find_tagged(''):
		print(fn)

if sys.argv[1] == 'do-tagged':
	pre_args, post_args = [], []
	current = pre_args
	mode = []
	for arg in sys.argv[2:]:
		if arg in {'*', '?'}:
			mode.append(arg)
			current = post_args
		else:
			current.append(arg)

	if len(mode) != 1:
		print('Exactly one argument should be "*" or "?"')
		exit(1)
	mode = mode[0]

	if len(pre_args) < 1:
		print(f'Need a command before {mode}')
		exit(1)

	files = find_tagged('')
	if not files:
		print('No tagged files.')
		exit(1)

	if mode == '?':
		for fn in files:
			subprocess.run(pre_args + [fn] + post_args)
	if mode == '*':
		subprocess.run(pre_args + files + post_args)

if sys.argv[1] == 'mark-seen':
	count = 0
	for f in sys.argv[2:]:
		path, file = os.path.split(f)
		dbs.json_write([path, dbs.QUEUE_DIR_NAME, ...], {file: {'position': 1}})
		count += 1
	print(f'Marked {count} files as seen.')
