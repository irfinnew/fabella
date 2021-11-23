import io
import OpenGL.GL as gl
import PIL.Image, PIL.ImageOps, PIL.ImageFilter

from logger import Logger


class ImgLib:
	@classmethod
	def add(cls, name, filename, width, height, pool, shadow=None):
		with open(filename, 'rb') as fd:
			data = fd.read()
		img = Image(data, width, height, name=name, pool=pool, mode='RGBA', shadow=shadow)
		setattr(cls, name, img)



class Image:
	log = Logger(module='Image', color=Logger.Black + Logger.Bright)

	def __init__(self, source, width, height, name='None', pool=None, mode='RGB', shadow=None):
		self._source = None
		self.pixels = None
		self.rendered = False
		self._texture = None

		self.width = width
		self.height = height
		self.mode = mode
		self.shadow = shadow
		self.name = name
		self.pool = pool
		self.source = source

	def __del__(self):
		if self._texture:
			self.log.error(f'{self}.__del__(): lingering texture!')

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
		self.log.debug(f'Rendering image: {self.name}')

		if self.rendered:
			self.log.warning('Already rendered, skipping')
			return

		with PIL.Image.open(io.BytesIO(self._source)) as image:
			if image.mode != self.mode:
				image = image.convert(self.mode)
			if image.width != self.width or image.height != self.height:
				image = PIL.ImageOps.fit(image, (self.width, self.height))

			if self.shadow:
				blur_radius, blur_count = self.shadow
				outset = blur_radius + blur_count // 2 + 1

				# Stencil
				new = PIL.Image.new('RGBA', (self.width + outset * 2, self.height + outset * 2))

				for i in range(blur_count):
					new.paste((0, 0, 0), (outset - 1, outset - 1), mask=image)
					new.paste((0, 0, 0), (outset + 1, outset - 1), mask=image)
					new.paste((0, 0, 0), (outset + 1, outset + 1), mask=image)
					new.paste((0, 0, 0), (outset - 1, outset + 1), mask=image)
					new = new.filter(PIL.ImageFilter.GaussianBlur(blur_radius))
				new.paste(image, (outset, outset), mask=image)

				image = new.convert(self.mode)
				self.width = new.width
				self.height = new.height

			pixels = image.tobytes()

		self.pixels = pixels
		self.rendered = True

	@property
	def texture(self):
		if not self.pixels:
			return self._texture

		if self._texture is None:
			self._texture = gl.glGenTextures(1)

		glmode = {'RGB': gl.GL_RGB, 'RGBA': gl.GL_RGBA}[self.mode]
		gl.glBindTexture(gl.GL_TEXTURE_2D, self._texture)
		gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
		gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR)
		gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, glmode, self.width, self.height, 0, glmode, gl.GL_UNSIGNED_BYTE, self.pixels)
		gl.glBindTexture(gl.GL_TEXTURE_2D, 0)

		self.pixels = None
		return self._texture

	def __str__(self):
		return f'Image({self.name}, {self.width}, {self.height})'

	def __repr__(self):
		return self.__str__()
