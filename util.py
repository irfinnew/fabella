import functools
import os



@functools.lru_cache
def duration_format(duration, seconds=False):
	with_seconds = seconds
	duration = int(duration)
	hours = duration // 3600
	minutes = (duration % 3600) // 60
	seconds = duration % 60
	return f'{hours}:{minutes:>02}' + (f':{seconds:>02}' if with_seconds else '')


def render_thread_count(minimum=1):
	cpus = len(os.sched_getaffinity(0))
	threads = cpus - 1
	if threads < 2:
		threads = 2
	if threads > cpus:
		threads = cpus
	return threads
