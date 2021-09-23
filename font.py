import OpenGL.GL as gl
import cairo
import gi
gi.require_version('Pango', '1.0')
from gi.repository import Pango
gi.require_version('PangoCairo', '1.0')
from gi.repository import PangoCairo

from logger import Logger


class Text:
	log = Logger(module='Font', color=Logger.Black + Logger.Bright)

	def __init__(self, font, text, max_width=None, lines=1, pool=None):
		self._text = None
		self.width = 0
		self.height = 0
		self.update = None
		self.rendered = False
		self._texture = None

		self.font = font
		self.max_width = max_width
		self.lines = lines
		self.pool = pool
		self.text = text

	def __del__(self):
		if self._texture:
			self.log.error(f'{self}.__del__(): lingering texture!')

	@property
	def text(self):
		return self._text
	@text.setter
	def text(self, text):
		if text != self._text:
			self._text = text
			self.rendered = False
			self.pool.schedule(self.render)

	def render(self):
		self.log.debug(f'Rendering text: "{self._text}"')

		if self.rendered:
			self.log.warning('Already rendered, skipping')
			return

		border = self.font.stroke_width
		layout = PangoCairo.create_layout(self.font.context)
		layout.set_font_description(self.font.face)
		layout.set_wrap(Pango.WrapMode.WORD)
		layout.set_ellipsize(Pango.EllipsizeMode.END)
		layout.set_text(self._text, -1)

		# Wrapping
		if self.max_width:
			layout.set_width((self.max_width - border * 2) * Pango.SCALE)
		layout.set_height(-self.lines)

		# Create actual surface
		width, height = layout.get_size()
		height = height // Pango.SCALE + border * 2
		if self.max_width:
			width = self.max_width
		else:
			width = width // Pango.SCALE + border * 2

		surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
		context = cairo.Context(surface)

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

		self.update = (surface.get_data(), width, height)
		self.rendered = True

	@property
	def texture(self):
		if not self.update:
			return self._texture

		data, self.width, self.height = self.update
		self.update = None

		if self._texture is None:
			self._texture = gl.glGenTextures(1)

		gl.glBindTexture(gl.GL_TEXTURE_2D, self._texture)
		gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
		gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR)
		gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGBA, self.width, self.height, 0, gl.GL_BGRA, gl.GL_UNSIGNED_BYTE, data)
		gl.glBindTexture(gl.GL_TEXTURE_2D, 0)

		return self._texture

	def __str__(self):
		return f'Text({self.font.name} {self.font.size}, {repr(self._text)})'

	def __repr__(self):
		return self.__str__()


class Font:
	log = Logger(module='Font', color=Logger.Black + Logger.Bright)
	face = None
	name = None
	size = None
	stroke_width = 0

	def __init__(self, fontname, size, stroke_width):
		self.log.info(f'Creating instance for {fontname} {size}')
		self.name = fontname
		self.size = size
		self.stroke_width = stroke_width
		self.face = Pango.font_description_from_string(f'{fontname} {size}')

		# Surface and context will be re-used for every Text instance to create
		# a Pango layout from, just to lay out the text.
		self.surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 64, 64)
		self.context = cairo.Context(self.surface)

	def text(self, text, max_width=None, lines=1, pool=None):
		return Text(self, text, max_width, lines, pool=pool)

	def __str__(self):
		return f'Font({self.name} {self.size}, {self.stroke_width})'

	def __repr__(self):
		return self.__str__()
