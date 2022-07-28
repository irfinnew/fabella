import operator
import OpenGL.GL as gl
import PIL.Image  # Hmm, just for SuperTexture.dump() ?
import math

import loghelper

log = loghelper.get_logger('Draw', loghelper.Color.BrightBlack)



# XXX: Not yet thread safe, only call stuff from main thread
def initialize(width, height):
	log.info(f'Initialize for {width}x{height}')

	# Init OpenGL
	gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
	gl.glEnable(gl.GL_BLEND)
	gl.glEnable(gl.GL_TEXTURE_2D)
	gl.glMatrixMode(gl.GL_PROJECTION)
	gl.glLoadIdentity()
	gl.glOrtho(0, width, 0, height, 0, 1)
	gl.glMatrixMode(gl.GL_MODELVIEW)

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



def render():
	# MPV seems to mess this up, so we have to re-enable it.
	gl.glEnable(gl.GL_BLEND)

	# FIXME: maybe make sorting invariant for efficiency?
	SuperTexture.bind()
	gl.glBegin(gl.GL_QUADS)
	for quad in sorted({q for q in Quad.all if not q.hidden}, key = operator.attrgetter('z')):
		quad.render()
	gl.glEnd()
	gl.glBindTexture(gl.GL_TEXTURE_2D, 0)



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

	# Bind texture for rendering... FIXME: is this needed?
	@classmethod
	def bind(cls):
		gl.glBindTexture(gl.GL_TEXTURE_2D, cls.tid)

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
		self.x = x
		self.y = y
		self.w = w
		self.h = h
		self.z = z
		self.xpos, self.ypos = pos
		self.scale = scale
		self.hidden = False
		self.texture = Texture(image=image, persistent=False) if texture is None else texture
		self.w = w or self.texture.width or 0
		self.h = h or self.texture.height or 0
		self.color = (1, 1, 1, 1) if color is None else color
		self.all.add(self)

	@property
	def pos(self):
		return (self.xpos, self.ypos)
	@pos.setter
	def pos(self, newpos):
		self.xpos, self.ypos = newpos

	@property
	def opacity(self):
		return self.color[3]
	@opacity.setter
	def opacity(self, newopa):
		#self.color[3] = newopa
		self.color = self.color[:3] + (newopa,)

	def update_image(self, image):
		self.texture.update_image(image)

	def destroy(self):
		self.all.remove(self)
		self.texture.destroy()
		del self.x # trigger AttributeError if we're used after this
		del self.texture  # trigger AttributeError if we're used after this

	def render(self):
		if not self.texture.concrete:
			return
		uv = self.texture.uv
		gl.glColor4f(*self.color)
		gl.glTexCoord2f(uv[0], uv[3])
		gl.glVertex2f(self.xpos + self.x * self.scale, self.ypos + self.y * self.scale)
		gl.glTexCoord2f(uv[2], uv[3])
		gl.glVertex2f(self.xpos + (self.x + self.w) * self.scale, self.ypos + self.y * self.scale)
		gl.glTexCoord2f(uv[2], uv[1])
		gl.glVertex2f(self.xpos + (self.x + self.w) * self.scale, self.ypos + (self.y + self.h) * self.scale)
		gl.glTexCoord2f(uv[0], uv[1])
		gl.glVertex2f(self.xpos + self.x * self.scale, self.ypos + (self.y + self.h) * self.scale)

	def __str__(self):
		return f'<{type(self).__name__} @{self.x},{self.y} #{self.z} x{self.scale} ({self.xd} {self.yd} {self.w} {self.h}>'

	def __repr__(self):
		return str(self)



class FlatQuad(Quad):
	def __init__(self, **kwargs):
		super().__init__(texture=Texture.flat, **kwargs)
