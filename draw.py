# Fabella - Simple, elegant video library and player.
#
# Copyright 2020-2021 Marcel Moreaux.
# Licensed under GPL v2.0, or (at your option) any later version.
# (SPDX GPL-2.0-or-later) See LICENSE file for details.

import operator
import OpenGL, OpenGL.GL.shaders, OpenGL.GL as gl
import PIL.Image  # Hmm, just for SuperTexture.dump() ?
import math
import queue
import ctypes
import array
import time
import io
import os

import loghelper
import window
import worker
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
	swap_needed = False

	def __init__(self):
		raise NotImplementedError('Instantiation not allowed.')

	@classmethod
	def initialize(cls, width, height, threads=None):
		log.info(f'PyOpenGL version {OpenGL.version.__version__}')
		log.info(f'Initialize for {width}x{height}')
		cls.width = width
		cls.height = height

		cls.render_pool = worker.Pool('Render', threads=util.render_thread_count() if threads is None else threads)

		# Init OpenGL
		gl.glEnable(gl.GL_BLEND)
		gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)

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

		# Allocate SuperTexture
		max_size = gl.glGetInteger(gl.GL_MAX_TEXTURE_SIZE)
		log.info(f'GL_MAX_TEXTURE_SIZE = {max_size}')
		size = max(width, height)
		size = 2 ** math.ceil(math.log2(size))
		size *= 2
		if size > max_size:
			log.error(f'Desired texture size {size}x{size} unsupported, using {max_size}x{max_size}!')
			size = max_size
		SuperTexture.initialize(size)

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
	def render(cls):
		Update.finalize_all()

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
			cls.swap_needed = False
			return

		# MPV seems to mess this up, so we have to re-enable it.
		gl.glEnable(gl.GL_BLEND)

		gl.glUseProgram(cls.shader)
		gl.glActiveTexture(gl.GL_TEXTURE0)
		gl.glBindTexture(gl.GL_TEXTURE_2D, SuperTexture.tid)

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
		cls.swap_needed = True



class SuperTexture:
	# Small alignment increases fragmentation, large alignment increases waste.
	# This seems to be a reasonable trade-off.
	alignment = 32
	tid = None
	size = None
	freelist = None
	coords = {}

	def __init__(self, size):
		raise NotImplementedError('Instantiation not allowed.')

	@classmethod
	def initialize(cls, size):
		assert cls.tid is None
		cls.size = size
		cls.tid = gl.glGenTextures(1)
		cls.freelist = {(size, size, 0, 0)}
		gl.glBindTexture(gl.GL_TEXTURE_2D, cls.tid)
		gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
		gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR)
		gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGBA, size, size, 0, gl.GL_RGBA, gl.GL_UNSIGNED_BYTE, None)
		gl.glBindTexture(gl.GL_TEXTURE_2D, 0)
		log.info(f'Initialized SuperTexture of size {size}x{size}')

	@classmethod
	def allocate_area(cls, width, height):
		width = (width + cls.alignment - 1) // cls.alignment * cls.alignment
		height = (height + cls.alignment - 1) // cls.alignment * cls.alignment
		for (fh, fw, fx, fy) in sorted(cls.freelist):
			if fw >= width and fh >= height:
				cls.freelist.remove((fh, fw, fx, fy))
				if fh > height:
					cls.freelist.add((fh - height, fw, fx, fy + height))
				if fw > width:
					cls.freelist.add((height, fw - width, fx + width, fy))
				return (fx, fy)

		cls.dump()
		raise ValueError(f"Couldn't allocate {width}x{height} area in SuperTexture!")

	@classmethod
	def add(cls, texture):
		size = cls.size
		width, height = texture.width, texture.height
		xoff, yoff = cls.allocate_area(width, height)
		cls.coords[texture] = (xoff, yoff, width, height)
		return (xoff / size, yoff / size, (xoff + width) / size, (yoff + height) / size)

	@classmethod
	def remove(cls, texture):
		(xoff, yoff, width, height) = cls.coords[texture]
		width = (width + cls.alignment - 1) // cls.alignment * cls.alignment
		height = (height + cls.alignment - 1) // cls.alignment * cls.alignment
		cls.freelist.add((height, width, xoff, yoff))
		cls.coords.pop(texture)

	@classmethod
	def update(cls, texture, format, pixels):
		coords = cls.coords[texture]
		gl.glBindTexture(gl.GL_TEXTURE_2D, cls.tid)
		gl.glTexSubImage2D(gl.GL_TEXTURE_2D, 0, *coords, format, gl.GL_UNSIGNED_BYTE, pixels)

	@classmethod
	def dump(cls):
		items = len(cls.freelist)
		pixels = sum(h * w for (h, w, x, y) in cls.freelist)
		log.warning(f'Dumping SuperTexture ({items} items, {pixels} pixels on freelist)')
		gl.glBindTexture(gl.GL_TEXTURE_2D, cls.tid)
		pixels = gl.glGetTexImage(gl.GL_TEXTURE_2D, 0, gl.GL_RGBA, gl.GL_UNSIGNED_BYTE)
		image = PIL.Image.frombytes('RGBA', (cls.size, cls.size), pixels)
		image.save('supertexture.png')



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
				SuperTexture.remove(self)
			self.width = width
			self.height = height
			self.concrete = True
			self.uv = SuperTexture.add(self)

		glformat = {'RGB': gl.GL_RGB, 'RGBA': gl.GL_RGBA, 'BGRA': gl.GL_BGRA}[mode]
		SuperTexture.update(self, glformat, pixels)

	def update_image(self, img):
		if img is not None:
			self.update_raw(img.width, img.height, img.mode, img.tobytes())

	# Hack to avoid texture edge bleeding on very small textures
	def inset_halftexel(self):
		d = 1 / (SuperTexture.size * 2)
		self.uv = (self.uv[0] + d, self.uv[1] + d, self.uv[2] - d, self.uv[3] - d)

	def force_redraw(self):
		State.redraw_needed = True

	def use(self):
		self.ref_count += 1

	def destroy(self, force=False):
		self.ref_count -= 1
		if not force and (self.persistent or self.ref_count > 0):
			return
		if self.concrete:
			SuperTexture.remove(self)
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
		self.texture.update_image(image)
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
		self.destroyed = True
		self.all.remove(self)
		self.texture.destroy()
		del self.x # trigger AttributeError if we're used after this
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




class Update:
	done = queue.Queue()

	def finalize(self):
		if self.quad.destroyed:
			return
		self.quad.update_raw(self.width, self.height, self.mode, self.pixels)
		if self.color is not None:
			self.quad.color = self.color

	@classmethod
	def finalize_all(cls):
		try:
			while True:
				cls.done.get_nowait().finalize()
		except queue.Empty:
			pass



class UpdateImg(Update):
	def __init__(self, quad, data, fit=None, color=None):
		self.quad = quad
		self.data = data
		self.fit = fit
		self.color = color
		State.render_pool.schedule(self.do)

	def do(self):
		img = PIL.Image.open(io.BytesIO(self.data))
		if self.fit:
			if (img.width, img.height) != self.fit:
				img = PIL.ImageOps.fit(img, self.fit)
		self.width = img.width
		self.height = img.height
		self.mode = img.mode
		self.pixels = img.tobytes()

		self.done.put(self)
		window.wakeup()



class UpdateText(Update):
	def __init__(self, quad, text):
		self.quad = quad
		self.text = text
		self.color = None
		State.render_pool.schedule(self.do)

	def do(self):
		width, height, mode, pixels = self.text.render()
		self.width = width
		self.height = height
		self.mode = mode
		self.pixels = pixels

		if (self.quad.w, self.quad.h) != (width, height):
			if self.text.anchor[1] == 'r':
				self.quad.x = self.quad.x + self.quad.w - width
			if self.text.anchor[0] == 't':
				self.quad.y = self.quad.y + self.quad.h - height
			self.quad.w = width
			self.quad.h = height

		self.done.put(self)
		window.wakeup()



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
		self.after = after
		self.hide = hide
		self.started = False
		Animation.all[self] = None

	def animate(self, t):
		if t < self.start:
			return

		if not self.started:
			self.quad.hidden = False

		x = self.ease(min((t - self.start) / self.duration, 1))
		for k, (s, e) in self.params.items():
			v = s * (1 - x) + e * x
			setattr(self.quad, k, v)

		if x == 1:
			Animation.all.pop(self)
			if self.hide:
				self.quad.hidden = True
			if self.after:
				self.after()

	@classmethod
	def animate_all(cls):
		t = time.time()
		for a in list(cls.all.keys()):
			a.animate(t)
		# Doing this makes glfw wait events not work properly, dropping rendering to ~30fps and stuttering ???
		#window.wakeup()



class Animatable:
	def __init__(self, quad, duration=0.3, initial=False, ease='single', **kwargs):
		self.quad = quad
		self.duration = duration
		self.ease = ease
		self.params_on = kwargs
		self.params_off = {k: (u, v) for k, (v, u) in kwargs.items()}

		self.state = initial
		for k, v in self.params_on.items():
			setattr(quad, k, v[self.state])

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
