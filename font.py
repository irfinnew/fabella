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
		self.surface = None
		self.rendered = False
		self._texture = None

		self.font = font
		self.max_width = max_width
		self.lines = lines
		self.pool = pool
		self.text = text

	def __del__(self):
		if self._texture:
			# FIXME: is this called from the right GL context? Does this work?
			#print(f'>>>> Deleting textures {[self._texture]}')
			gl.glDeleteTextures([self._texture])
			self._texture = None

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
		self.height = height // Pango.SCALE + border * 2
		if self.max_width:
			self.width = self.max_width
		else:
			self.width = width // Pango.SCALE + border * 2

		surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.width, self.height)
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

		self.surface = surface
		self.rendered = True

	@property
	def texture(self):
		if not self.surface:
			return self._texture

		if self._texture is None:
			self._texture = gl.glGenTextures(1)

		gl.glBindTexture(gl.GL_TEXTURE_2D, self._texture)
		gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
		gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR)
		gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGBA, self.width, self.height, 0, gl.GL_BGRA, gl.GL_UNSIGNED_BYTE, self.surface.get_data())
		gl.glBindTexture(gl.GL_TEXTURE_2D, 0)

		self.surface = None
		return self._texture


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
