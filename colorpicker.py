# Fabella - Simple, elegant video library and player.
#
# Copyright 2020-2022 Marcel Moreaux.
# Licensed under GPL v2.0, or (at your option) any later version.
# (SPDX GPL-2.0-or-later) See LICENSE file for details.

import math


def color_distance(c1, c2):
	"""Return a number indicating how dissimilar two color tuples are."""

	# Using the fourth root clusters colors together quite strongly.
	# This seems to give a good result overall.
	return sum(abs(a - b) ** (1/2) for a, b in zip(c1, c2))


def pick(img, colors=64):
	"""Pick a representative color for img. colors should be 1-256.
	A higher number of colors should give a better result, but will be slower.
	"""

	# Quantize the image into colors; this will effectively generate a histogram for us
	quantized = img.quantize(colors)

	# Get the palette as color-tuples
	palette = quantized.getpalette()
	palette = [tuple(palette[i*3:i*3+3]) for i in range(colors)]

	# [color-tuple: count] histogram
	histogram = {palette[color]: count for count, color in quantized.getcolors(colors)}

	best_color = None
	best_distance = math.inf
	# We consider all colors in the histogram as candidates for the "best color".
	# For every color, we calculate the cumulative distance to all colors in the
	# histogram, and we select the color with the lowest such cumulative distance.
	for color in histogram.keys():
		distance = 0
		for other, count in histogram.items():
			distance += color_distance(color, other) * count
		if distance < best_distance:
			best_color = color
			best_distance = distance

	return best_color
