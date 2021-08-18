#! /usr/bin/env python3

import PIL.Image, PIL.ImageDraw, PIL.ImageFont
import OpenGL.GL as gl
from dataclasses import dataclass

from logger import Logger

@dataclass
class RenderedText:
	texture: int
	width: int
	height: int

class Font:
	log = Logger(module='Font', color=Logger.Black + Logger.Bright)
	font = None
	stroke_width = 0

	def __init__(self, fontname, size, stroke_width):
		self.log.info(f'Creating instance for {fontname} {size}')
		self.font = PIL.ImageFont.truetype(fontname, size)
		self.stroke_width = stroke_width

	def render(self, text, texture=None):
		self.log.info(f'Rendering into {"existing" if texture else "new"} texture: "{text}"')

		# Get text size
		image = PIL.Image.new('RGBA', (8, 8), (0, 164, 201))
		w, h = PIL.ImageDraw.Draw(image).textsize(text, self.font, stroke_width=self.stroke_width)

		# Draw text
		image = PIL.Image.new('RGBA', (w, h), (0, 164, 201, 0))
		PIL.ImageDraw.Draw(image).text((0, 0), text, font=self.font, align='center', fill=(255, 255, 255), stroke_width=self.stroke_width, stroke_fill=(0, 0, 0))

		if texture is None:
			texture = gl.glGenTextures(1)

		gl.glBindTexture(gl.GL_TEXTURE_2D, texture)
		gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
		gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR)
		gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGBA, w, h, 0, gl.GL_RGBA, gl.GL_UNSIGNED_BYTE, image.tobytes())
		gl.glBindTexture(gl.GL_TEXTURE_2D, 0)

		del image

		return RenderedText(texture=texture, width=w, height=h)
