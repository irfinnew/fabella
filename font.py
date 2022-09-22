# Fabella - Simple, elegant video library and player.
#
# Copyright 2020-2022 Marcel Moreaux.
# Licensed under GPL v2.0, or (at your option) any later version.
# (SPDX GPL-2.0-or-later) See LICENSE file for details.

import cairo
import gi
gi.require_version('Pango', '1.0')
from gi.repository import Pango
gi.require_version('PangoCairo', '1.0')
from gi.repository import PangoCairo

import loghelper
import draw

log = loghelper.get_logger('Font', loghelper.Color.BrightBlack)



class Text:
	def __init__(self, font, text='', x=0, y=0, z=0, pos=(0, 0), anchor='bl', max_width=None, color=None, lines=1, group=None):
		self._text = None
		self._max_width = None
		self.width = 0
		self.height = 0
		self.update = None
		self.rendered = False
		self.anchor = anchor
		self.quad = draw.FlatQuad(x=x, y=y, z=z, pos=pos, color=color, group=group)

		self.font = font
		self._lines = lines
		self._max_width = max_width
		self.text = text

	@property
	def text(self):
		return self._text
	@text.setter
	def text(self, text):
		if text != self._text:
			self._text = text
			draw.UpdateText(self.quad, self)

	@property
	def max_width(self):
		return self._max_width
	@max_width.setter
	def max_width(self, max_width):
		if max_width != self._max_width:
			self._max_width = max_width
			draw.UpdateText(self.quad, self)

	@property
	def lines(self):
		return self._lines
	@lines.setter
	def lines(self, lines):
		if lines != self._lines:
			self._lines = lines
			draw.UpdateText(self.quad, self)

	def render(self):
		if self._text is None:
			return

		log.debug(f'Rendering text: "{self._text}"')

		# We need to pad the surface a bit to account for the stroke width
		border = self.font.stroke_width
		layout = PangoCairo.create_layout(self.font.context)
		layout.set_font_description(self.font.font_desc)
		layout.set_wrap(Pango.WrapMode.WORD_CHAR)
		layout.set_ellipsize(Pango.EllipsizeMode.END)
		layout.set_text(self._text, -1)

		# Wrapping
		if self._max_width:
			layout.set_width((self._max_width - border * 2) * Pango.SCALE)
		layout.set_height(-self._lines)

		# Create actual surface
		width, height = layout.get_size()
		height = height // Pango.SCALE + border * 2
		if self._max_width:
			width = self._max_width
		else:
			width = width // Pango.SCALE + border * 2

		# Surface
		surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
		context = cairo.Context(surface)

		# Useful for debugging
		#context.set_source_rgb(1, 0, 0)
		#context.rectangle(0, 0, width, height)
		#context.fill()

		# Outline
		context.set_source_rgb(0, 0, 0)
		context.move_to(border, border)
		PangoCairo.layout_path(context, layout)
		context.set_line_width(self.font.stroke_width * 2)
		context.set_line_join(cairo.LINE_JOIN_ROUND)
		context.set_line_cap(cairo.LINE_CAP_ROUND)
		context.stroke()

		# Fill
		context.set_source_rgb(1, 1, 1)
		context.move_to(border, border)
		PangoCairo.show_layout(context, layout)

		surface.flush()
		return (width, height, 'BGRA', bytes(surface.get_data()))

	def destroy(self):
		self.quad.destroy()

	def __str__(self):
		return f'<Text {self.font.desc}, {repr(self._text)}>'

	def __repr__(self):
		return self.__str__()


class Font:
	def __init__(self, fontname, size, stroke_width=None):
		self.name = fontname
		self.size = size
		self.desc = f'{fontname} {size}'

		log.info(f'{self.desc}: Initializing Font renderer')
		log.info(f'{self.desc}: Pycairo version {cairo.version}')
		if stroke_width is None:
			self.stroke_width = 1 + round(size / 9)
		else:
			self.stroke_width = stroke_width
		log.info(f'{self.desc}: Stroke width: {self.stroke_width}')

		font_desc = Pango.font_description_from_string(f'{fontname} {size}')
		fontmap = PangoCairo.font_map_get_default()
		self.font = fontmap.load_font(fontmap.create_context(), font_desc)
		self.font_desc = self.font.describe()
		log.info(f'{self.desc}: Loaded font: {self.font_desc.to_string()}')

		self.line_height = self.font.get_metrics().height / Pango.SCALE
		log.info(f'{self.desc}: Font height: {self.height}px')

		# Surface and context will be re-used for every Text instance to create
		# a Pango layout from, just to lay out the text.
		self.surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 64, 64)
		self.context = cairo.Context(self.surface)

	def height(self, lines=1):
		return round(self.line_height * lines) + self.stroke_width

	def text(self, **kwargs):
		return Text(self, **kwargs)

	def __str__(self):
		return f'<Font {self.desc}, {self.stroke_width}>'

	def __repr__(self):
		return str(self)
