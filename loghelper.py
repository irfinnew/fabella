# Fabella - Simple, elegant video library and player.
#
# Copyright 2020-2023 Marcel Moreaux.
# Licensed under GPL v2.0, or (at your option) any later version.
# (SPDX GPL-2.0-or-later) See LICENSE file for details.

import logging
import logging.handlers


NOTSET = 0
DEBUG = 10
VERBOSE = 15
INFO = 20
WARNING = 30
ERROR = 40
CRITICAL = 50

class Color:
	Reset = '\x1b[0m'

	Black   = '\x1b[30m'
	Red     = '\x1b[31m'
	Green   = '\x1b[32m'
	Yellow  = '\x1b[33m'
	Blue    = '\x1b[34m'
	Magenta = '\x1b[35m'
	Cyan    = '\x1b[36m'
	White   = '\x1b[37m'

	BrightBlack   = '\x1b[30;1m'
	BrightRed     = '\x1b[31;1m'
	BrightGreen   = '\x1b[32;1m'
	BrightYellow  = '\x1b[33;1m'
	BrightBlue    = '\x1b[34;1m'
	BrightMagenta = '\x1b[35;1m'
	BrightCyan    = '\x1b[36;1m'
	BrightWhite   = '\x1b[37;1m'



Levels = {
	50 : Color.BrightMagenta,
	40 : Color.BrightRed,
	30 : Color.BrightYellow,
	20 : Color.BrightGreen,
	15 : Color.Cyan,
	-1000 : Color.BrightCyan,
}

Names = {}



class ColoredFormatter(logging.Formatter):
	def format(self, record):
		level_color = ''
		for l, c in Levels.items():
			if record.levelno >= l:
				level_color = c
				break

		name_color = Names.get(record.name, '')

		format = '%(asctime)s %(levelcolor)s%(levelname)8s%(reset)s: %(namecolor)s%(name)20s.%(funcName)-20s%(reset)s -> %(message)s'
		format = format.replace('%(levelcolor)s', level_color).replace('%(namecolor)s', name_color).replace('%(reset)s', Color.Reset)
		formatter = logging.Formatter(format)
		formatted = formatter.format(record)
		if 'FIXME' in formatted:
			formatted = formatted.replace('FIXME', f'{Color.BrightRed}FIXME{Color.Reset}')
		return formatted



def set_up_logging(console_level=20, file_level=10, filename=None):
	logging.addLevelName(10, 'debug')
	logging.addLevelName(15, 'verbose')
	logging.addLevelName(20, 'info')
	logging.addLevelName(30, 'warning')
	logging.addLevelName(40, 'error')
	logging.addLevelName(50, 'critical')

	logger = logging.getLogger()
	logger.setLevel(logging.NOTSET)

	if filename:
		handler = logging.handlers.WatchedFileHandler(filename)
		handler.setLevel(file_level)
		format = '%(asctime)s %(levelname)8s: %(name)20s.%(funcName)-20s -> %(message)s'
		handler.setFormatter(logging.Formatter(format))
		logger.addHandler(handler)

	handler = logging.StreamHandler()
	handler.setLevel(console_level)
	handler.setFormatter(ColoredFormatter())
	logger.addHandler(handler)



def get_logger(name, color):
	set_color(name, color)
	return logging.getLogger(name)



def set_color(name, color):
	Names[name] = color
