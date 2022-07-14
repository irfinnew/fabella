import operator
import OpenGL.GL as gl



class Quad:
	quads = set()

	def __init__(self, x, y, w, h, z):
		assert w > 0
		assert h > 0

		self.x = x
		self.y = y
		self.z = z
		self.w = w
		self.h = h
		self.hidden = False
		self.quads.add(self)

	def destroy(self):
		self.quads.remove(self)

	def move_to(self, x, y):
		self.x = x
		self.y = y

	def resize(self, w, h):
		self.w = w
		self.h = h

	def show(self):
		self.hidden = False

	def hide(self):
		self.hidden = True

	# Only call from main thread
	@classmethod
	def render_all(cls):
		# FIXME: maybe make sorting invariant for efficiency?
		for quad in sorted({q for q in cls.quads if not q.hidden}, key = operator.attrgetter('z')):
			quad.render()



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
	def __init__(self):
		self.concrete = False
		self.tid = gl.glGenTextures(1)
		gl.glBindTexture(gl.GL_TEXTURE_2D, self.tid)
		gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
		gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR)
		gl.glBindTexture(gl.GL_TEXTURE_2D, 0)

	def update(self, img):
		glmode = {'RGB': gl.GL_RGB, 'RGBA': gl.GL_RGBA}[img.mode]
		pixels = img.tobytes()

		gl.glBindTexture(gl.GL_TEXTURE_2D, self.tid)
		gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, glmode, img.width, img.height, 0, glmode, gl.GL_UNSIGNED_BYTE, pixels)
		gl.glBindTexture(gl.GL_TEXTURE_2D, 0)

		self.concrete = True

	def destroy(self):
		self.concrete = False
		gl.glDeleteTexturs([self.tid])
		self.tid = None



class TexturedQuad(Quad):
	# Only call from main thread
	def __init__(self, x, y, w, h, z, color=None):
		self.texture = Texture()
		self.color = (1, 1, 1, 1) if color is None else color
		super().__init__(x, y, w, h, z)

	# Only call from main thread
	def update_texture(self, image):
		# FIXME: this should use a work queue so this can be called from any context
		self.texture.update(image)

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
		gl.glVertex2f(self.x, self.y)
		gl.glTexCoord2f(1.0, 1.0)
		gl.glVertex2f(self.x + self.w, self.y)
		gl.glTexCoord2f(1.0, 0.0)
		gl.glVertex2f(self.x + self.w, self.y + self.h)
		gl.glTexCoord2f(0.0, 0.0)
		gl.glVertex2f(self.x, self.y + self.h)
		gl.glEnd()
		gl.glBindTexture(gl.GL_TEXTURE_2D, 0)
