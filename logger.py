import datetime

class Logger:
	Black = '\x1b[30m'
	Red = '\x1b[31m'
	Green = '\x1b[32m'
	Yellow = '\x1b[33m'
	Blue = '\x1b[34m'
	Magenta = '\x1b[35m'
	Cyan = '\x1b[36m'
	Gray = '\x1b[37m'
	Bright = '\x1b[1m'
	Reset = '\x1b[0m'

	LevelColors = {
		'critical': Bright + Magenta,
		'error':    Bright + Red,
		'warning':  Bright + Yellow,
		'info':     Bright + Green,
		'debug':    Bright + Cyan,
	}

	def __init__(self, *, module, color):
		self.module = module
		self.color = color

	def log(self, level, msg, *, module=None, color=None):
		#if level == 'debug':
		#	return

		level_color = self.LevelColors[level]
		module = module or self.module
		color = color or self.color

		timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
		level = ' ' * (8 - len(level)) + '<' + level_color + level + self.Reset + '>'
		module = ' ' * (8 - len(module)) + '[' + color + module + self.Reset + ']'
		print(f'{timestamp} {level} {module} {msg}')

	def critical(self, msg, **kwargs):
		self.log('critical', msg, **kwargs)

	def error(self, msg, **kwargs):
		self.log('error', msg, **kwargs)

	def warning(self, msg, **kwargs):
		self.log('warning', msg, **kwargs)

	def info(self, msg, **kwargs):
		self.log('info', msg, **kwargs)

	def debug(self, msg, **kwargs):
		self.log('debug', msg, **kwargs)
