import loghelper
import functools
import time
import os


log = loghelper.get_logger('Util', loghelper.Color.BrightYellow)


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


def img_crop_ratio(image, size):
	input_ratio = image.width / image.height
	output_ratio = size[0] / size[1]

	# If the image is close enough, don't bother
	if 0.99 < input_ratio / output_ratio < 1.01:
		return image

	# Determine what dimension to crop
	if input_ratio >= output_ratio:
		crop_width = output_ratio * image.height
		crop_height = image.height
	else:
		crop_width = image.width
		crop_height = image.width / output_ratio
	crop_left = (image.width - crop_width) / 2
	crop_top = (image.height - crop_height) / 2

	# Actually crop
	return image.crop((crop_left, crop_top, crop_left + crop_width, crop_top + crop_height))


def stopwatch(msg=None):
	now = time.perf_counter()
	if msg:
		ms = (now - stopwatch.start) * 1000
		log.warning(f'{ms:.1f}ms: {msg}')

	stopwatch.start = now
