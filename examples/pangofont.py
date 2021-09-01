#! /usr/bin/env python

import time
import sys
import cairo
import gi
gi.require_version('Pango', '1.0')
from gi.repository import Pango
gi.require_version('PangoCairo', '1.0')
from gi.repository import PangoCairo

font_name = sys.argv[1]
font_size = int(sys.argv[2])
stroke_width = int(sys.argv[3])
border = 8

def draw_text(face, stroke_width, text, border, layout):
	layout.set_text(text, -1)
	layout.set_font_description(face)
	width, height = layout.get_size()
	width //= 1024
	height //= 1024

	surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width + border * 2, height + border * 2)
	context = cairo.Context(surface)
	#context.rectangle(0,0,320,120)
	#context.set_source_rgb(1, 1, 1)
	#context.fill()

	# Outline
	context.set_source_rgb(0, 0, 0)
	context.move_to(border, border)
	PangoCairo.layout_path(context, layout)
	context.set_line_width(stroke_width * 2)
	context.set_line_join(cairo.LINE_JOIN_ROUND)
	context.set_line_cap(cairo.LINE_CAP_ROUND)
	context.stroke()

	# Fill
	context.set_source_rgb(1, 1, 1)
	context.move_to(border, border)
	PangoCairo.show_layout(context, layout)

	return surface

#face = Pango.font_description_from_string('./Vera.ttf 30')
face = Pango.font_description_from_string(f'{font_name} {font_size}')
# Hurgh, needed to determine size
surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 20, 20)
context = cairo.Context(surface)
layout = PangoCairo.create_layout(context)

characters = 0
duration = 0
for i, line in enumerate(sys.stdin):
	line = line.strip()
	if line:
		characters += len(line)
		duration -= time.time()
		surface = draw_text(face, stroke_width, line, border, layout)
		duration += time.time()
		surface.write_to_png(f'output-{i:04}.png')

print(f'Rendered {characters} characters in {duration} seconds; {int(characters/duration)} chars/sec.')
