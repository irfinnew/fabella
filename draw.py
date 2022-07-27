import operator
import OpenGL.GL as gl

# Not yet thread safe, only call stuff from main thread

quads = set()

flat_texture = None
def initialize():
	global flat_texture
	flat_texture = Texture()
	flat_texture.update_raw(1, 1, 'RGBA', b'\xff' * 4)


def render():
	# FIXME: maybe make sorting invariant for efficiency?
	for quad in sorted({q for q in quads if not q.hidden}, key = operator.attrgetter('z')):
		quad.render()



class Texture:
	def __init__(self, image=None, persistent=True):
		self.persistent = persistent
		self.concrete = False
		self.width = None
		self.height = None
		self.tid = gl.glGenTextures(1)
		gl.glBindTexture(gl.GL_TEXTURE_2D, self.tid)
		gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
		gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR)
		gl.glBindTexture(gl.GL_TEXTURE_2D, 0)
		if image is not None:
			self.update_image(image)

	def update_raw(self, width, height, mode, pixels):
		glformat = {'RGB': gl.GL_RGB, 'RGBA': gl.GL_RGBA, 'BGRA': gl.GL_BGRA}[mode]
		glinternal = {'RGB': gl.GL_RGB, 'RGBA': gl.GL_RGBA, 'BGRA': gl.GL_RGBA}[mode]

		gl.glBindTexture(gl.GL_TEXTURE_2D, self.tid)
		gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, glinternal, width, height, 0, glformat, gl.GL_UNSIGNED_BYTE, pixels)
		gl.glBindTexture(gl.GL_TEXTURE_2D, 0)

		self.width = width
		self.height = height
		self.concrete = True

	def update_image(self, img):
		if img is None:
			return
		self.update_raw(img.width, img.height, img.mode, img.tobytes())

	def destroy(self, force=False):
		if self.persistent and not force:
			return
		self.concrete = False
		gl.glDeleteTextures([self.tid])
		del self.tid
		del self.concrete
		del self.persistent

	def __str__(self):
		return f'<Texture ({self.tid}) {self.width}x{self.height}{" concrete" if self.concrete else ""}{" persistent" if self.persistent else ""}>'

	def __repr__(self):
		return str(self)


class ExternalTexture:
	def __init__(self, tid):
		self.concrete = True
		self.tid = tid

	def destroy(self, force=False):
		if not force:
			return
		self.concrete = False
		gl.glDeleteTextures([self.tid])
		del self.tid
		del self.concrete

	def __str__(self):
		return f'<Texture ({self.tid}) external>>'

	def __repr__(self):
		return str(self)


class Quad:
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
		quads.add(self)

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
		self.color[3] = newopa

	def update_image(self, image):
		self.texture.update_image(image)

	def destroy(self):
		quads.remove(self)
		self.texture.destroy()
		del self.x # trigger AttributeError if we're used still
		del self.texture  # trigger AttributeError if we're used still

	def render(self):
		if not self.texture.concrete:
			return
		gl.glColor4f(*self.color)
		gl.glBindTexture(gl.GL_TEXTURE_2D, self.texture.tid)
		gl.glBegin(gl.GL_QUADS)
		gl.glTexCoord2f(0.0, 1.0)
		gl.glVertex2f(self.xpos + self.x * self.scale, self.ypos + self.y * self.scale)
		gl.glTexCoord2f(1.0, 1.0)
		gl.glVertex2f(self.xpos + (self.x + self.w) * self.scale, self.ypos + self.y * self.scale)
		gl.glTexCoord2f(1.0, 0.0)
		gl.glVertex2f(self.xpos + (self.x + self.w) * self.scale, self.ypos + (self.y + self.h) * self.scale)
		gl.glTexCoord2f(0.0, 0.0)
		gl.glVertex2f(self.xpos + self.x * self.scale, self.ypos + (self.y + self.h) * self.scale)
		gl.glEnd()
		gl.glBindTexture(gl.GL_TEXTURE_2D, 0)

	def __str__(self):
		return f'<{type(self).__name__} @{self.x},{self.y} #{self.z} x{self.scale} ({self.xd} {self.yd} {self.w} {self.h}>'

	def __repr__(self):
		return str(self)



class FlatQuad(Quad):
	def __init__(self, **kwargs):
		super().__init__(texture=flat_texture, **kwargs)
