import functools



@functools.lru_cache
def duration_format(duration, seconds=False):
	with_seconds = seconds
	duration = int(duration)
	hours = duration // 3600
	minutes = (duration % 3600) // 60
	seconds = duration % 60
	return f'{hours}:{minutes:>02}' + (f':{seconds:>02}' if with_seconds else '')
