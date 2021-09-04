#! /usr/bin/env python

import sys
import cairo
import gi
gi.require_version('Pango', '1.0')
from gi.repository import Pango
gi.require_version('PangoCairo', '1.0')
from gi.repository import PangoCairo

font_name = './Vera.ttf'
font_size = 30
stroke_width = 4
border = 8

width = 256
height = 256

def draw_text(face, stroke_width, text, border, layout, max_width=None, lines=1):
	layout.set_text(text, -1)

	# Wrapping
	if max_width:
		layout.set_width((max_width - border * 2) * Pango.SCALE)
	layout.set_height(-lines)
	layout.set_wrap(Pango.WrapMode.WORD)
	layout.set_ellipsize(Pango.EllipsizeMode.END)

	# Create actual surface
	width, height = layout.get_size()
	height = height // Pango.SCALE + border * 2
	if max_width:
		width = max_width
	else:
		width = width // Pango.SCALE + border * 2
	print(width, height)
	
	surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
	context = cairo.Context(surface)

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


face = Pango.font_description_from_string(f'{font_name} {font_size}')
ghost_surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 64, 64)
ghost_context = cairo.Context(ghost_surface)
layout = PangoCairo.create_layout(ghost_context)
layout.set_font_description(face)

text = 'Why on Earth Is No One Talking About the Mouthfeel?'
surface = draw_text(face, stroke_width, text, border, layout, max_width=256, lines=2)
surface.write_to_png(f'output.png')
