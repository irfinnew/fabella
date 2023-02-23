# Fabella - Simple, elegant video library and player.
#
# Copyright 2020-2023 Marcel Moreaux.
# Licensed under GPL v2.0, or (at your option) any later version.
# (SPDX GPL-2.0-or-later) See LICENSE file for details.

import operator
import OpenGL, OpenGL.GL.shaders, OpenGL.GL as gl
import PIL.Image, PIL.ImageDraw
from collections import namedtuple
import math
import queue
import ctypes
import array
import time
import io
import os

import loghelper
import window
import util

log = loghelper.get_logger('Draw', loghelper.Color.BrightBlack)
# XXX: Not yet thread safe, only call stuff from main thread



class State:
	width = None
	height = None
	shader = None
	vao = None
	vbo = None
	buffer = None
	rebuild_buffer = False
	dirty_quads = set()
	redraw_needed = False

	def __init__(self):
		raise NotImplementedError('Instantiation not allowed.')

	@classmethod
	def initialize(cls, width, height, threads=None):
		log.info(f'PyOpenGL version {OpenGL.version.__version__}')
		log.info(f'Initialize for {width}x{height}')
		cls.width = width
		cls.height = height

		# Init OpenGL
		gl.glEnable(gl.GL_BLEND)
		gl.glBlendFuncSeparate(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA, gl.GL_ONE, gl.GL_ONE)

		# Shaders
		geometry_shader = gl.shaders.compileShader(GEOMETRY_SHADER, gl.GL_GEOMETRY_SHADER)
		vertex_shader = gl.shaders.compileShader(VERTEX_SHADER, gl.GL_VERTEX_SHADER)
		fragment_shader = gl.shaders.compileShader(FRAGMENT_SHADER, gl.GL_FRAGMENT_SHADER)
		cls.shader = gl.shaders.compileProgram(vertex_shader, fragment_shader)
		gl.shaders.glAttachShader(cls.shader, geometry_shader)
		gl.glLinkProgram(cls.shader)

		# Arrays / buffers
		cls.vao = gl.glGenVertexArrays(1)
		gl.glBindVertexArray(cls.vao)

		cls.vbo = gl.glGenBuffers(1)
		gl.glBindBuffer(gl.GL_ARRAY_BUFFER, cls.vbo)
		stride = 16 * 4  # 16 floats
		gl.glEnableVertexAttribArray(0)  # position
		gl.glVertexAttribPointer(0, 2, gl.GL_FLOAT, False, stride, ctypes.c_void_p(0))
		gl.glEnableVertexAttribArray(1)  # XY
		gl.glVertexAttribPointer(1, 4, gl.GL_FLOAT, False, stride, ctypes.c_void_p(8))
		gl.glEnableVertexAttribArray(2)  # UV
		gl.glVertexAttribPointer(2, 4, gl.GL_FLOAT, False, stride, ctypes.c_void_p(24))
		gl.glEnableVertexAttribArray(3)  # color
		gl.glVertexAttribPointer(3, 4, gl.GL_FLOAT, False, stride, ctypes.c_void_p(40))
		gl.glEnableVertexAttribArray(4)  # scale
		gl.glVertexAttribPointer(4, 1, gl.GL_FLOAT, False, stride, ctypes.c_void_p(56))
		gl.glEnableVertexAttribArray(5)  # hidden
		gl.glVertexAttribPointer(5, 1, gl.GL_FLOAT, False, stride, ctypes.c_void_p(60))

		gl.glBindBuffer(gl.GL_ARRAY_BUFFER, 0)
		gl.glBindVertexArray(0)

		# Set uniforms
		uTexture = gl.glGetUniformLocation(cls.shader, 'texture')
		uResolution = gl.glGetUniformLocation(cls.shader, 'resolution')
		gl.glUseProgram(cls.shader)
		gl.glUniform1i(uTexture, 0)
		gl.glUniform2f(uResolution, cls.width / 2, cls.height / 2)

		# Allocate TextureAtlas
		# FIXME: have TextureAtlas expand when it's full, and choose smaller size here
		max_size = gl.glGetInteger(gl.GL_MAX_TEXTURE_SIZE)
		log.info(f'GL_MAX_TEXTURE_SIZE = {max_size}')
		size = max(width, height)
		size = 2 ** math.ceil(math.log2(size))
		size *= 2
		if size > max_size:
			log.error(f'Desired texture size {size}x{size} unsupported, using {max_size}x{max_size}!')
			size = max_size
		TextureAtlas.initialize(size, size)

		# Allocate video texture.
		# This NEEDS to be done first, because it has to go in the top left corner.
		# MPV doesn't support rendering to any other position.
		Texture.video = Texture()
		Texture.video.update_raw(width, height, 'RGBA', b'\x00\x00\x00\xff' * width * height)

		# Allocate single white-pixel texture for rendering flats
		Texture.flat = Texture()
		Texture.flat.update_raw(1, 1, 'RGBA', b'\xff' * 4)
		Texture.flat.inset_halftexel()


	@classmethod
	def render(cls, win):
		if cls.rebuild_buffer:
			log.debug('Rebuilding OpenGL data buffer')
			cls.buffer = array.array('f', [])
			for i, quad in enumerate(sorted(Quad.all, key=operator.attrgetter('z'))):
				cls.buffer.extend(quad.buffer())
				quad.buffer_index = i
			cls.rebuild_buffer = False
			cls.dirty_quads.clear()
			cls.redraw_needed = True

		if cls.dirty_quads:
			log.debug('Updating OpenGL data buffer')
			for quad in cls.dirty_quads:
				qb = array.array('f', quad.buffer())
				qbl = len(qb)
				idx = quad.buffer_index * qbl
				cls.buffer[idx:idx+qbl] = qb
			cls.dirty_quads.clear()
			cls.redraw_needed = True

		if not cls.redraw_needed:
			return

		# MPV seems to mess this up, so we have to re-enable it.
		gl.glEnable(gl.GL_BLEND)

		gl.glUseProgram(cls.shader)
		gl.glActiveTexture(gl.GL_TEXTURE0)
		gl.glBindTexture(gl.GL_TEXTURE_2D, TextureAtlas.tid)

		gl.glBindVertexArray(cls.vao)
		gl.glBindBuffer(gl.GL_ARRAY_BUFFER, cls.vbo)
		buffer = cls.buffer.tobytes()
		gl.glBufferData(gl.GL_ARRAY_BUFFER, len(buffer), buffer, gl.GL_STATIC_DRAW)
		gl.glDrawArrays(gl.GL_POINTS, 0, len(cls.buffer) // 15)

		# Seems like unbinding this stuff isn't necessary, so save the CPU cycles
		#gl.glUseProgram(0)
		#gl.glBindBuffer(gl.GL_ARRAY_BUFFER, 0)
		#gl.glBindVertexArray(0)

		cls.redraw_needed = False
		win.swap_buffers()



class TextureShelf:
	Hole = namedtuple('Hole', 'x w')
	# Minimum height for shelves, and tolerance for lower items on the shelf.
	# Higher value means fewer shelves, so searching the shelves is faster.
	# Higher value means more eligible items, so fuller shelves, which may improve packing.
	# Higher value means more vertical space is wasted on shelves, worsening packing.
	# This is a trade-off. 64 seems to work pretty well for my settings.
	# Optimum seems to be at the height of the largest Tile title.
	alignment = 64

	def __init__(self, ypos, height, width):
		if height < self.alignment:
			height = self.alignment
		self.ypos = ypos
		self.height = height
		self.width = width
		self.holes = {self.Hole(0, width)}

	def add(self, width, height):
		if height > self.height or height < self.height - self.alignment:
			raise ValueError('height not suitable for this shelf')

		best = None
		for hole in self.holes:
			if hole.w > width:
				if best is None or hole.w < hole.w:
					best = hole

		if best:
			self.holes.remove(best)
			self.holes.add(self.Hole(best.x + width, best.w - width))
			return (best.x, self.ypos)

		raise ValueError('no horizontal space in this shelf')

	def remove(self, xpos, width):
		left, right = None, None
		for hole in self.holes:
			if hole.x + hole.w == xpos:
				left = hole
			if xpos + width == hole.x:
				right = hole

		if left and right:
			self.holes.remove(left)
			self.holes.remove(right)
			self.holes.add(self.Hole(left.x, left.w + width + right.w))
		elif left:
			self.holes.remove(left)
			self.holes.add(self.Hole(left.x, left.w + width))
		elif right:
			self.holes.remove(right)
			self.holes.add(self.Hole(xpos, right.w + width))
		else:
			self.holes.add(self.Hole(xpos, width))

	def __str__(self):
		pct = int(sum(h.w for h in self.holes) / self.width * 100)
		return f'<TextureShelf h{self.height} @{self.ypos}, {pct}% free>'

	def __repr__(self):
		return str(self)



class TextureAtlas:
	def __init__(self, size):
		raise NotImplementedError('Instantiation not allowed.')

	@classmethod
	def initialize(cls, width, height):
		cls.width = width
		cls.height = height
		cls.used = 0
		cls.shelves = []
		cls.textures = {}
		cls.tid = gl.glGenTextures(1)
		gl.glBindTexture(gl.GL_TEXTURE_2D, cls.tid)
		gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
		gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR)
		gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGBA, width, height, 0, gl.GL_RGBA, gl.GL_UNSIGNED_BYTE, None)
		gl.glBindTexture(gl.GL_TEXTURE_2D, 0)
		log.info(f'Initialized TextureAtlas of size {width}x{height}')

	@classmethod
	def add_to_shelf(cls, shelf, txt):
		xoff, yoff = shelf.add(txt.width, txt.height)
		cls.textures[txt] = (shelf, xoff, yoff, txt.width, txt.height)
		return (xoff / cls.width, yoff / cls.height, (xoff + txt.width) / cls.width, (yoff + txt.height) / cls.height)

	@classmethod
	def add(cls, texture):
		# Find a shelf to put this on.
		for shelf in cls.shelves:
			try:
				return cls.add_to_shelf(shelf, texture)
			except ValueError:
				pass

		# No available shelf; create a new shelf.
		if cls.height - cls.used > texture.height:
			shelf = TextureShelf(cls.used, texture.height, cls.width)
			cls.shelves.append(shelf)
			# Sort shelves by height, so that we'll find the tightest match that has room
			cls.shelves = sorted(cls.shelves, key=lambda s: s.height)
			cls.used += shelf.height
			try:
				return cls.add_to_shelf(shelf, texture)
			except ValueError:
				cls.dump()
				raise

		cls.dump()
		raise ValueError(f"Couldn't allocate {width}x{height} area in TextureAtlas!")

	@classmethod
	def remove(cls, texture):
		shelf, xpos, ypos, width, height = cls.textures.pop(texture)
		shelf.remove(xpos, width)

	@classmethod
	def update(cls, texture, format, pixels):
		shelf, *coords = cls.textures[texture]
		gl.glBindTexture(gl.GL_TEXTURE_2D, cls.tid)
		gl.glTexSubImage2D(gl.GL_TEXTURE_2D, 0, *coords, format, gl.GL_UNSIGNED_BYTE, pixels)

	@classmethod
	def dump(cls):
		log.warning(f'{int(cls.used / cls.height * 100)}% of TextureAtlas used, in {len(cls.shelves)} shelves:')
		for shelf in cls.shelves:
			log.warning(str(shelf))
		log.warning(f'Dumping TextureAtlas contents')
		gl.glBindTexture(gl.GL_TEXTURE_2D, cls.tid)
		pixels = gl.glGetTexImage(gl.GL_TEXTURE_2D, 0, gl.GL_RGBA, gl.GL_UNSIGNED_BYTE)
		image = PIL.Image.frombytes('RGBA', (cls.width, cls.height), pixels)
		overlay = PIL.Image.new('RGBA', (cls.width, cls.height))
		draw = PIL.ImageDraw.Draw(overlay)
		for sh, fx, fy, fw, fh in cls.textures.values():
			draw.rectangle((fx, fy, fx + fw - 1, fy + fh - 1), fill=(150, 30, 30, 128), outline=(255, 160, 160), width=3)
		for shelf in cls.shelves:
			for hole in shelf.holes:
				fx, fy, fw, fh = hole.x, shelf.ypos, hole.w, shelf.height
				draw.rectangle((fx, fy, fx + fw - 1, fy + fh - 1), fill=(40, 40, 160), outline=(160, 160, 255), width=3)
		image = PIL.Image.alpha_composite(image, overlay)
		image.save('texture_atlas.png')



class Texture:
	flat = None
	video = None

	def __init__(self, image=None, persistent=True):
		self.ref_count = 0
		self.persistent = persistent
		self.concrete = False
		self.width = None
		self.height = None
		self.uv = None
		if image is not None:
			self.update_image(image)

	def update_raw(self, width, height, mode, pixels):
		if (self.width, self.height) != (width, height):
			if self.concrete:
				TextureAtlas.remove(self)
			self.width = width
			self.height = height
			self.concrete = True
			self.uv = TextureAtlas.add(self)

		glformat = {'RGB': gl.GL_RGB, 'RGBA': gl.GL_RGBA, 'BGRA': gl.GL_BGRA}[mode]
		TextureAtlas.update(self, glformat, pixels)

	def update_image(self, img):
		if img is not None:
			self.update_raw(img.width, img.height, img.mode, img.tobytes())

	# Hack to avoid texture edge bleeding on very small textures
	def inset_halftexel(self):
		dx = 1 / (TextureAtlas.width * 2)
		dy = 1 / (TextureAtlas.height * 2)
		self.uv = (self.uv[0] + dx, self.uv[1] + dy, self.uv[2] - dx, self.uv[3] - dy)

	def force_redraw(self):
		State.redraw_needed = True

	def use(self):
		self.ref_count += 1

	def destroy(self, force=False):
		self.ref_count -= 1
		if not force and (self.persistent or self.ref_count > 0):
			return
		if self.concrete:
			TextureAtlas.remove(self)
		self.concrete = False
		del self.concrete  # Trigger AttributeError if used again

	def __str__(self):
		return f'<Texture {self.width}x{self.height}{" concrete" if self.concrete else ""}{" persistent" if self.persistent else ""}>'

	def __repr__(self):
		return str(self)



class Quad:
	all = set()

	def __init__(self, x=0, y=0, w=None, h=None, z=0, pos=(0, 0), scale=1.0, texture=None, image=None, color=None, hidden=False, group=None):
		self.destroyed = False
		self.x = x
		self.y = y
		self.z = z
		self.pos = pos
		self.scale = scale
		self.hidden = hidden
		self.texture = Texture(image=image, persistent=False) if texture is None else texture
		self.texture.use()
		self.w = w or self.texture.width or 0
		self.h = h or self.texture.height or 0
		self.color = (1, 1, 1, 1) if color is None else color
		self.all.add(self)
		State.rebuild_buffer = True
		if group:
			group.add(self)

	# FIXME: yuck; maybe make property protocol?
	def __setattr__(self, k, v):
		super().__setattr__(k, v)
		if self.destroyed:
			return
		if k in {'z', 'hidden'}:
			# FIXME: this rebuilds the buffer even if property is written with same value...
			State.rebuild_buffer = True
		else:
			State.dirty_quads.add(self)

	@property
	def opacity(self):
		return self.color[3]
	@opacity.setter
	def opacity(self, newopa):
		self.color = self.color[:3] + (newopa,)

	@property
	def xpos(self):
		return self.pos[0]
	@xpos.setter
	def xpos(self, new):
		self.pos = (new,) + self.pos[1:]

	@property
	def ypos(self):
		return self.pos[1]
	@ypos.setter
	def ypos(self, new):
		self.pos = self.pos[:1] + (new,)

	def update_raw(self, width, height, mode, pixels):
		if self.texture is Texture.flat:
			self.texture.destroy()
			self.texture = Texture(None, persistent=False)
			self.texture.use()
		uv = self.texture.uv
		self.texture.update_raw(width, height, mode, pixels)
		if uv != self.texture.uv:
			State.dirty_quads.add(self)
		else:
			State.redraw_needed = True

	def update_image(self, image):
		uv = self.texture.update_image(image)
		if uv != self.texture.uv:
			State.dirty_quads.add(self)
		else:
			State.redraw_needed = True

	# Return an independent copy of this quad. All attributes are copied, except group.
	# The texture is shared. Provided attributes override copied ones.
	def copy(self, **kwargs):
		attrs = {k: getattr(self, k) for k in ['x', 'y', 'w', 'h', 'z', 'pos', 'scale', 'texture', 'color', 'hidden']}
		attrs.update(kwargs)
		return Quad(**attrs)

	def destroy(self):
		if self.destroyed:
			return
		self.destroyed = True
		self.all.remove(self)
		self.texture.destroy()
		del self.texture  # trigger AttributeError if we're used after this
		State.rebuild_buffer = True

	def buffer(self):
		return [
			*self.pos,
			self.x, self.y, self.x + self.w, self.y + self.h,
			*self.texture.uv,
			*self.color,
			self.scale,
			float(self.hidden),
		]

	def __str__(self):
		return f'<{type(self).__name__} @{self.pos[0]},{self.pos[1]} #{self.z} x{self.scale} ({self.x} {self.y} {self.w} {self.h})>'

	def __repr__(self):
		return str(self)



class FlatQuad(Quad):
	def __init__(self, **kwargs):
		super().__init__(texture=Texture.flat, **kwargs)



class Group:
	def __init__(self, *quads):
		self._quads = set(q for q in quads if q)
		self._destroyed = False

	def __iter__(self):
		return iter(self._quads)

	@property
	def destroyed(self):
		return self._destroyed

	def add(self, *quads):
		self._quads |= set(q for q in quads if q)

	def remove(self, *quads):
		self._quads -= set(quads)

	def contains(self, quad):
		for q in self._quads:
			if q == quad:
				return True
			elif isinstance(q, Group):
				if q.contains(quad):
					return True

	def remove_destroyed(self):
		for quad in {q for q in self._quads if q.destroyed}:
			self.remove(quad)

	def destroy(self):
		self._destroyed = True
		self.remove_destroyed()
		for quad in set(self._quads):
			quad.destroy()

	def __setattr__(self, k, v):
		if k[0] == '_':
			super().__setattr__(k, v)
		else:
			self.remove_destroyed()
			for quad in set(self._quads):
				setattr(quad, k, v)



class Animation:
	all = {}
	EASES = {  # Cubic easement functions
		'in': lambda x: x ** 3,
		'out': lambda x: 1 - (1 - x) ** 3,
		'both': lambda x: 4 * x ** 3 if x < 0.5 else 1 - 4 * (1 - x) ** 3,
	}

	def __init__(self, quad=None, ease='both', duration=1.0, delay=0.0, after=None, hide=False, **kwargs):
		self.quad = quad
		self.ease = self.EASES[ease]
		self.duration = duration
		self.start = time.time() + delay
		self.params = kwargs
		# Set None start value to current value.
		# FIXME: this breaks if quad is a group.
		for p, (b, a) in self.params.items():
			if b is None:
				b = getattr(self.quad, p)
				self.params[p] = (b, a)
		self.after = after
		self.hide = hide
		self.started = False
		Animation.all[self] = None
		self.quad.hidden = False

	def animate(self, t):
		t = (t - self.start) / self.duration
		t = max(t, 0)
		t = min(t, 1)
		x = self.ease(t)
		for k, (s, e) in self.params.items():
			v = s * (1 - x) + e * x
			setattr(self.quad, k, v)

		if x >= 1:
			Animation.all.pop(self)
			if self.hide:
				self.quad.hidden = True
			if self.after:
				self.after()

	def contains(self, quad):
		if isinstance(self.quad, Group):
			return self.quad.contains(quad)
		else:
			return self.quad == quad

	def abort(self):
		Animation.all.pop(self, None)

	@classmethod
	def animate_all(cls):
		t = time.time()
		for a in list(cls.all.keys()):
			a.animate(t)
		# Doing this makes glfw wait events not work properly, dropping rendering to ~30fps and stuttering ???
		#window.wakeup()

	@classmethod
	def cancel(cls, *quads):
		for a in list(cls.all.keys()):
			for q in quads:
				if a.contains(q):
					a.abort()



class Animatable:
	def __init__(self, quad, duration=0.3, initial=False, ease='single', **kwargs):
		self.quad = quad
		self.duration = duration
		self.ease = ease
		self.params_on = {}
		self.params_off = {}
		self.update_params(**kwargs)

		self.state = initial
		for k, v in self.params_on.items():
			setattr(quad, k, v[self.state])

	def update_params(self, **kwargs):
		for k, (u, v) in kwargs.items():
			self.params_on[k] = (u, v)
			self.params_off[k] = (v, u)

	def show(self, state):
		if state == self.state:
			return

		self.state = state
		params = self.params_on if self.state else self.params_off
		ease = 'both' if self.ease == 'both' else ['in', 'out'][self.state]
		Animation(self.quad, duration=self.duration, ease=ease, **params)



VERTEX_SHADER = """#version 330 core
uniform vec2 resolution;
layout (location = 0) in vec2 position;
layout (location = 1) in vec4 XY;
layout (location = 2) in vec4 UV;
layout (location = 3) in vec4 color;
layout (location = 4) in float scale;
layout (location = 5) in float hidden;

out VDATA {
	vec4 XY;
	vec4 UV;
	vec4 color;
} vdata;

void main()
{
	vdata.XY = vec4(
		XY[0] / resolution[0] * scale - 1,
		XY[1] / resolution[1] * scale - 1,
		XY[2] / resolution[0] * scale - 1,
		XY[3] / resolution[1] * scale - 1
	);
	vdata.UV = UV;
	vdata.color = color;

	if (hidden > 0.5)
		vdata.color.a = 0.0;

	gl_Position = vec4(position[0] / resolution[0], position[1] / resolution[1], 0.0, 1.0);
}
"""



GEOMETRY_SHADER = """#version 330 core
layout (points) in;
layout (triangle_strip, max_vertices = 4) out;

in VDATA {
	vec4 XY;
	vec4 UV;
	vec4 color;
} vdata[];

out vec2 UV;
out vec4 color;

void main() {
	vec4 position = gl_in[0].gl_Position;

	color = vdata[0].color;

	if (color.a == 0.0)
		return;

	// Bottom-left
	gl_Position = position + vec4(vdata[0].XY[0], vdata[0].XY[1], 0.0, 0.0);
	UV = vec2(vdata[0].UV[0], vdata[0].UV[3]);
	EmitVertex();

	// Bottom-right
	gl_Position = position + vec4(vdata[0].XY[2], vdata[0].XY[1], 0.0, 0.0);
	UV = vec2(vdata[0].UV[2], vdata[0].UV[3]);
	EmitVertex();

	// Top-left
	gl_Position = position + vec4(vdata[0].XY[0], vdata[0].XY[3], 0.0, 0.0);
	UV = vec2(vdata[0].UV[0], vdata[0].UV[1]);
	EmitVertex();

	// Top-right
	gl_Position = position + vec4(vdata[0].XY[2], vdata[0].XY[3], 0.0, 0.0);
	UV = vec2(vdata[0].UV[2], vdata[0].UV[1]);
	EmitVertex();

	EndPrimitive();
}
"""



FRAGMENT_SHADER = """#version 330 core
uniform sampler2D texture;
in vec2 UV;
in vec4 color;

out vec4 FragColor;

void main()
{
	FragColor = texture2D(texture, UV) * color;
}
"""
