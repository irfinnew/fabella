#! /usr/bin/env python3

import os
import time
import PIL.Image, PIL.ImageDraw, PIL.ImageFont
import OpenGL.GL as gl

from logger import Logger

class Tile:
	log = Logger(module='Tile', color=Logger.Magenta)
	name = ''
	texture = None
	font = None
	width = 0
	height = 0
	path = ''
	isdir = False
	state_file = None
	state_last_update = 0
	last_pos = 0
	rendered_last_pos = 0

	def __init__(self, name, path, font):
		self.log.info(f'Created Tile path={path}, name={name}')
		self.name = name
		self.path = os.path.join(path, name)
		self.isdir = os.path.isdir(self.path)
		self.font = font

		if not self.isdir:
			self.state_file = os.path.join(path, '.fabella', 'state', name)
			self.read_state()

	def update_pos(self, position, force=False):
		self.log.debug(f'Tile {self.name} update_pos({position}, {force})')
		if self.last_pos == position:
			return

		now = time.time()
		if now - self.state_last_update > 5 or abs(self.last_pos - position) > 0.01 or force:
			self.state_last_update = now
			self.last_pos = position
			self.write_state()

	def read_state(self):
		self.log.info(f'Reading state for {self.name}')
		try:
			with open(self.state_file) as fd:
				self.last_pos = float(fd.read())
		except FileNotFoundError:
			pass

	def write_state(self):
		self.log.info(f'Writing state for {self.name}')
		os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
		with open(self.state_file, 'w') as fd:
			fd.write(str(self.last_pos) + '\n')

	def render(self):
		self.log.info(f'Rendering for {self.name}')
		stroke_width = 2
		name = self.name
		if self.isdir:
			name = name + '/'

		if self.last_pos > 0.01:
			name = name + f' [{round(self.last_pos * 100)}%]'
		self.rendered_last_pos = self.last_pos

		# Get text size
		image = PIL.Image.new('RGBA', (8, 8), (0, 164, 201))
		w, h = PIL.ImageDraw.Draw(image).textsize(name, self.font, stroke_width=stroke_width)

		# Draw text
		image = PIL.Image.new('RGBA', (w, h), (0, 164, 201, 0))
		PIL.ImageDraw.Draw(image).text((0, 0), name, font=self.font, align='center', fill=(255, 255, 255), stroke_width=stroke_width, stroke_fill=(0, 0, 0))

		self.width = w
		self.height = h
		if self.texture is None:
			self.texture = gl.glGenTextures(1)
		gl.glBindTexture(gl.GL_TEXTURE_2D, self.texture)
		gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
		gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR)
		gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGBA, w, h, 0, gl.GL_RGBA, gl.GL_UNSIGNED_BYTE, image.tobytes())
		gl.glBindTexture(gl.GL_TEXTURE_2D, 0)

	def draw(self, x, y, selected=False):
		if self.texture is None:
			return

		if abs(self.last_pos - self.rendered_last_pos) > 0.01:
			self.render()

		new = 0.5 if self.last_pos == 1 else 1.0
		x1, y1, x2, y2 = x, y, x + self.width, y + self.height
		gl.glBindTexture(gl.GL_TEXTURE_2D, self.texture)
		if selected:
			gl.glColor4f(new, 0, 0, 1)
		else:
			gl.glColor4f(new, new, new, 1)
		gl.glBegin(gl.GL_QUADS)
		gl.glTexCoord2f(0.0, 1.0)
		gl.glVertex2f(x1, y1)
		gl.glTexCoord2f(1.0, 1.0)
		gl.glVertex2f(x2, y1)
		gl.glTexCoord2f(1.0, 0.0)
		gl.glVertex2f(x2, y2)
		gl.glTexCoord2f(0.0, 0.0)
		gl.glVertex2f(x1, y2)
		gl.glEnd()
		gl.glBindTexture(gl.GL_TEXTURE_2D, 0)

	def destroy(self):
		self.log.info(f'Destroying {self.name}')
		if self.texture is not None:
			gl.glDeleteTextures([self.texture])

	def __str__(self):
		return f'Tile(name={self.name}, isdir={self.isdir}, last_pos={self.last_pos}, texture={self.texture})'
