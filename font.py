import OpenGL.GL as gl
import cairo
import gi
gi.require_version('Pango', '1.0')
from gi.repository import Pango
gi.require_version('PangoCairo', '1.0')
from gi.repository import PangoCairo

from logger import Logger



# FIXME: WIP
import time
import threading
def do_renders():
	while True:
		#print(f'Font render thread: {len(do_renders.scheduled)}')
		while do_renders.scheduled:
			text = do_renders.scheduled.pop(0)
			text.render()
		time.sleep(0.01)
do_renders.scheduled = []
threading.Thread(target=do_renders, daemon=True).start()



class Text:
	log = Logger(module='Font', color=Logger.Black + Logger.Bright)
	font = None
	text = None
	max_width = None
	lines = 1
	width = 0
	height = 0
	surface = None
	update = False
	_texture = None

	def __init__(self, font, text, max_width=None, lines=1):
		self.font = font
		self.max_width = max_width
		self.lines = lines

		self.set_text(text)

	def set_text(self, text):
		if text != self.text:
			self.text = text
			#self.render()
			do_renders.scheduled.append(self)

	# Warning; not thread-safe!
	def render(self):
		self.log.info(f'Rendering text: "{self.text}"')

		# Reuses font-global layout; not thread-safe
		layout = self.font.layout
		border = self.font.stroke_width

		layout.set_text(self.text, -1)

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

		self.surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.width, self.height)
		context = cairo.Context(self.surface)

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

		self.update = True


	def texture(self):
		if not self.update:
			return self._texture

		if self._texture is None:
			self._texture = gl.glGenTextures(1)

		gl.glBindTexture(gl.GL_TEXTURE_2D, self._texture)
		gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
		gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR)
		gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGBA, self.width, self.height, 0, gl.GL_RGBA, gl.GL_UNSIGNED_BYTE, bytes(self.surface.get_data()))
		gl.glBindTexture(gl.GL_TEXTURE_2D, 0)

		# FIXME: is this valid?
		#del self.surface
		#self.surface = None

		self.update = False
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
		self.surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 64, 64)
		self.context = cairo.Context(self.surface)
		self.layout = PangoCairo.create_layout(self.context)
		self.layout.set_font_description(self.face)
		self.layout.set_wrap(Pango.WrapMode.WORD)
		self.layout.set_ellipsize(Pango.EllipsizeMode.END)

	def text(self, text, max_width=None, lines=1):
		t = Text(self, text, max_width, lines)
		return t
