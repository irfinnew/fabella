import operator
import OpenGL.GL as gl

quads = set()

# Only call from main thread
def render():
	# FIXME: maybe make sorting invariant for efficiency?
	for quad in sorted({q for q in quads if not q.hidden}, key = operator.attrgetter('z')):
		quad.render()



class Quad:
	def __init__(self, x, y, w, h, z):
		self.x = x
		self.y = y
		self.z = z
		self.w = w
		self.h = h
		self.hidden = False
		quads.add(self)

	# FIXME: hack alert
	def __setattr__(self, name, value):
		super().__setattr__(name, value)
		try:
			if name in 'xywh':
				self.x1, self.x2 = sorted([self.x, self.x + self.w])
				self.y1, self.y2 = sorted([self.y, self.y + self.h])
		except AttributeError:
			pass

	def destroy(self):
		quads.remove(self)
		del self.x
		del self.y
		del self.w
		del self.h
		del self.z
		del self.hidden

	def __str__(self):
		return f'<{type(self).__name__} {self.x}x{self.y} +{self.w}+{self.h} @{self.z}>'

	def __repr__(self):
		return str(self)



class FlatQuad(Quad):
	def __init__(self, x, y, w, h, z, color):
		self.color = color
		super().__init__(x, y, w, h, z)

	# Only call from main thread
	def render(self):
		gl.glColor4f(*self.color)
		gl.glBegin(gl.GL_QUADS)
		gl.glVertex2f(self.x, self.y)
		gl.glVertex2f(self.x + self.w, self.y)
		gl.glVertex2f(self.x + self.w, self.y + self.h)
		gl.glVertex2f(self.x, self.y + self.h)
		gl.glEnd()



class ShadedQuad(Quad):
	def __init__(self, x, y, w, h, z, colors):
		self.colors = colors
		super().__init__(x, y, w, h, z)

	# Only call from main thread
	def render(self):
		gl.glBegin(gl.GL_QUADS)
		gl.glColor4f(*self.colors[0])
		gl.glVertex2f(self.x, self.y)
		gl.glColor4f(*self.colors[1])
		gl.glVertex2f(self.x + self.w, self.y)
		gl.glColor4f(*self.colors[2])
		gl.glVertex2f(self.x + self.w, self.y + self.h)
		gl.glColor4f(*self.colors[3])
		gl.glVertex2f(self.x, self.y + self.h)
		gl.glEnd()



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
		self.update_raw(img.width, img.height, img.mode, img.tobytes())

	def destroy(self, force=False):
		if not force and not self.persistent:
			return
		self.concrete = False
		gl.glDeleteTexturs([self.tid])
		#self.tid = None
		del self.tid
		del self.concrete
		del self.persistent

	def __str__(self):
		return f'<Texture ({self.tid}) {self.width}x{self.height}{" concrete" if self.concrete else ""}{" persistent" if self.persistent else ""}>'

	def __repr__(self):
		return str(self)



class TexturedQuad(Quad):
	# Only call from main thread
	def __init__(self, x, y, w, h, z, texture=None, image=None, color=None):
		self.texture = Texture(image=image, persistent=False) if texture is None else texture
		self.color = (1, 1, 1, 1) if color is None else color
		super().__init__(x, y, w, h, z)

	# Only call from main thread
	def update_image(self, image):
		self.texture.update_image(image)

	# Only call from main thread
	def destroy(self):
		self.texture.destroy()
		self.texture = None
		super().destroy()

	# Only call from main thread
	def render(self):
		if not self.texture.concrete:
			return
		gl.glColor4f(*self.color)
		gl.glBindTexture(gl.GL_TEXTURE_2D, self.texture.tid)
		gl.glBegin(gl.GL_QUADS)
		gl.glTexCoord2f(0.0, 1.0)
		gl.glVertex2f(self.x1, self.y1)
		gl.glTexCoord2f(1.0, 1.0)
		gl.glVertex2f(self.x2, self.y1)
		gl.glTexCoord2f(1.0, 0.0)
		gl.glVertex2f(self.x2, self.y2)
		gl.glTexCoord2f(0.0, 0.0)
		gl.glVertex2f(self.x1, self.y2)
		gl.glEnd()
		gl.glBindTexture(gl.GL_TEXTURE_2D, 0)
