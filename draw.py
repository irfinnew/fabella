import operator
import OpenGL, OpenGL.GL.shaders, OpenGL.GL as gl
import PIL.Image  # Hmm, just for SuperTexture.dump() ?
import math
import ctypes
import array
import time

import loghelper
import window

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
	def initialize(cls, width, height):
		log.info(f'PyOpenGL version {OpenGL.version.__version__}')
		log.info(f'Initialize for {width}x{height}')
		cls.width = width
		cls.height = height

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
		gl.glEnableVertexAttribArray(0)
		gl.glVertexAttribPointer(0, 2, gl.GL_FLOAT, False, 60, ctypes.c_void_p(0))
		gl.glEnableVertexAttribArray(1)
		gl.glVertexAttribPointer(1, 4, gl.GL_FLOAT, False, 60, ctypes.c_void_p(8))
		gl.glEnableVertexAttribArray(2)
		gl.glVertexAttribPointer(2, 4, gl.GL_FLOAT, False, 60, ctypes.c_void_p(24))
		gl.glEnableVertexAttribArray(3)
		gl.glVertexAttribPointer(3, 4, gl.GL_FLOAT, False, 60, ctypes.c_void_p(40))
		gl.glEnableVertexAttribArray(4)
		gl.glVertexAttribPointer(4, 1, gl.GL_FLOAT, False, 60, ctypes.c_void_p(56))

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
		Texture.video.update_raw(width, height, 'RGBA', None)

		# Allocate single white-pixel texture for rendering flats
		Texture.flat = Texture()
		Texture.flat.update_raw(1, 1, 'RGBA', b'\xff' * 4)
		# Hack to avoid texture edge bleeding
		d = 1 / (size * 2)
		uv = Texture.flat.uv
		Texture.flat.uv = (uv[0] + d, uv[1] + d, uv[2] - d, uv[3] - d)


	@classmethod
	def render(cls):
		if cls.rebuild_buffer:
			log.debug('Rebuilding OpenGL data buffer')
			cls.buffer = array.array('f', [])
			for i, quad in enumerate(sorted({q for q in Quad.all if not q.hidden}, key = operator.attrgetter('z'))):
				cls.buffer.extend(quad.array())
				quad.buffer_index = i
			cls.rebuild_buffer = False
			cls.dirty_quads.clear()
			cls.redraw_needed = True

		if cls.dirty_quads:
			log.debug('Updating OpenGL data buffer')
			for quad in cls.dirty_quads:
				idx = quad.buffer_index * 15
				cls.buffer[idx:idx+15] = quad.array()
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
		gl.glDrawArrays(gl.GL_POINTS, 0, len(Quad.all))

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

	def force_redraw(self):
		State.redraw_needed = True

	def destroy(self, force=False):
		if self.persistent and not force:
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

	def __init__(self, x=0, y=0, w=None, h=None, z=0, pos=(0, 0), scale=1.0, texture=None, image=None, color=None):
		self.destroyed = False
		self.x = x
		self.y = y
		self.w = w
		self.h = h
		self.z = z
		self.pos = pos
		self.scale = scale
		self.hidden = False
		self.texture = Texture(image=image, persistent=False) if texture is None else texture
		self.w = w or self.texture.width or 0
		self.h = h or self.texture.height or 0
		self.color = (1, 1, 1, 1) if color is None else color
		self.all.add(self)
		State.rebuild_buffer = True

	# FIXME: yuck
	def __setattr__(self, k, v):
		super().__setattr__(k, v)
		if self.destroyed:
			return
		if k in {'z', 'hidden'}:
			State.rebuild_buffer = True
		else:
			State.dirty_quads.add(self)

	@property
	def opacity(self):
		return self.color[3]
	@opacity.setter
	def opacity(self, newopa):
		#self.color[3] = newopa
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

	def destroy(self):
		self.all.remove(self)
		self.texture.destroy()
		del self.x # trigger AttributeError if we're used after this
		del self.texture  # trigger AttributeError if we're used after this
		State.rebuild_buffer = True
		self.destroyed = True

	def array(self):
		if not self.texture.concrete:
			return array.array('f', [])

		return array.array('f', [
			*self.pos,
			self.x, self.y, self.x + self.w, self.y + self.h,
			*self.texture.uv,
			*self.color,
			self.scale
		])

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

	def add(self, *quads):
		self._quads |= set(q for q in quads if q)

	def remove(self, *quads):
		self._quads -= set(quads)

	def destroy(self):
		for quad in set(self._quads):
			if quad.destroyed:
				self.remove(quad)
			else:
				quad.destroy()

	def __setattr__(self, k, v):
		if k[0] == '_':
			super().__setattr__(k, v)
		else:
			for quad in set(self._quads):
				if quad.destroyed:
					self.remove(quad)
				else:
					setattr(quad, k, v)



class Animation:
	all = set()

	def __init__(self, quad=None, duration=1.0, after=None, **kwargs):
		self.quad = quad
		self.duration = duration
		self.start = time.time()
		self.params = kwargs
		self.after = after
		Animation.all.add(self)

	def animate(self, t):
		x = min((t - self.start) / self.duration, 1)
		for k, (s, e) in self.params.items():
			v = s * (1 - x) + e * x
			setattr(self.quad, k, v)
		if x == 1:
			Animation.all.remove(self)
			if self.after:
				self.after()

	@classmethod
	def animate_all(cls):
		if cls.all:
			t = time.time()
			for a in set(cls.all):
				a.animate(t)
			window.wakeup()



VERTEX_SHADER = """#version 330 core
uniform vec2 resolution;
layout (location = 0) in vec2 position;
layout (location = 1) in vec4 XY;
layout (location = 2) in vec4 UV;
layout (location = 3) in vec4 color;
layout (location = 4) in float scale;

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
