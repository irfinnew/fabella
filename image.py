import io
import OpenGL.GL as gl
import PIL.Image, PIL.ImageOps

from logger import Logger


class Image:
	log = Logger(module='Image', color=Logger.Black + Logger.Bright)

	def __init__(self, source, width, height, name='None', pool=None):
		self._source = None
		self.pixels = None
		self.rendered = False
		self._texture = None

		self.width = width
		self.height = height
		self.name = name
		self.pool = pool
		self.source = source

	def __del__(self):
		if self._texture:
			# FIXME: is this called from the right GL context? Does this work?
			#print(f'>>>> Deleting textures {[self._texture]}')
			gl.glDeleteTextures([self._texture])
			self._texture = None

	@property
	def source(self):
		return self._source
	@source.setter
	def source(self, source):
		if source != self._source:
			self._source = source
			self.rendered = False
			self.update_texture = False
			self.pool.schedule(self.render)

	def render(self):
		self.log.info(f'Rendering image: {self.name}')

		if self.rendered:
			self.log.info('Already rendered, skipping')
			return

		with PIL.Image.open(io.BytesIO(self._source)) as image:
			if image.mode != 'RGB':
				image = image.convert('RGB')
			if image.width != self.width or image.height != self.height:
				image = PIL.ImageOps.fit(image, (self.width, self.height))
			pixels = image.tobytes()

		self.pixels = pixels
		self.rendered = True

	@property
	def texture(self):
		if not self.pixels:
			return self._texture

		if self._texture is None:
			self._texture = gl.glGenTextures(1)

		gl.glBindTexture(gl.GL_TEXTURE_2D, self._texture)
		gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
		gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR)
		gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGB, self.width, self.height, 0, gl.GL_RGB, gl.GL_UNSIGNED_BYTE, self.pixels)
		gl.glBindTexture(gl.GL_TEXTURE_2D, 0)

		self.pixels = None
		return self._texture
