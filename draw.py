# Fabella - Simple, elegant video library and player.
#
# Copyright 2020-2021 Marcel Moreaux.
# Licensed under GPL v2.0, or (at your option) any later version.
# (SPDX GPL-2.0-or-later) See LICENSE file for details.

import operator
import OpenGL.GL as gl



class Quad:
	quads = set()

	def __init__(self, coords, z):
		self.z = z
		self.hidden = False

		if len(coords) == 2:
			self.x1, self.y1 = 0, 0
			self.x2, self.y2 = coords
		else:
			self.x1, self.y1, self.x2, self.y2 = coords

		assert self.x1 <= self.x2
		assert self.y1 <= self.y2

		self.quads.add(self)

	def delete(self):
		self.quads.remove(self)

	def lowerleft_to(self, x, y):
		width, height = self.x2 - self.x1, self.y2 - self.y1
		self.x1, self.y1, self.x2, self.y2 = x, y, x + width, y + height

	def upperleft_to(self, x, y):
		width, height = self.x2 - self.x1, self.y2 - self.y1
		self.x1, self.y1, self.x2, self.y2 = x, y - height, x + width, y

	def lowerright_to(self, x, y):
		width, height = self.x2 - self.x1, self.y2 - self.y1
		self.x1, self.y1, self.x2, self.y2 = x - width, y, x, y + height

	def upperright_to(self, x, y):
		width, height = self.x2 - self.x1, self.y2 - self.y1
		self.x1, self.y1, self.x2, self.y2 = x - width, y - height, x, y

	@classmethod
	def draw_all(cls):
		for quad in sorted({q for q in cls.quads if not q.hidden}, key = operator.attrgetter('z')):
			quad.draw()

		# FIXME: remove
		# For now, we discard everything after drawing. Reuse later.
		cls.quads = set()



class FlatQuad(Quad):
	def __init__(self, coords, z, color):
		self.color = color
		super().__init__(coords, z)

	def draw(self):
		gl.glColor4f(*self.color)
		gl.glBegin(gl.GL_QUADS)
		gl.glVertex2f(self.x1, self.y1)
		gl.glVertex2f(self.x2, self.y1)
		gl.glVertex2f(self.x2, self.y2)
		gl.glVertex2f(self.x1, self.y2)
		gl.glEnd()



class ShadedQuad(Quad):
	def __init__(self, coords, z, colors):
		self.colors = colors
		super().__init__(coords, z)

	def draw(self):
		gl.glBegin(gl.GL_QUADS)
		gl.glColor4f(*self.colors[0])
		gl.glVertex2f(self.x1, self.y1)
		gl.glColor4f(*self.colors[1])
		gl.glVertex2f(self.x2, self.y1)
		gl.glColor4f(*self.colors[2])
		gl.glVertex2f(self.x2, self.y2)
		gl.glColor4f(*self.colors[3])
		gl.glVertex2f(self.x1, self.y2)
		gl.glEnd()



class TexturedQuad(Quad):
	def __init__(self, coords, z, texture, color=None):
		self.texture = texture
		self.color = (1, 1, 1, 1) if color is None else color
		super().__init__(coords, z)

	def draw(self):
		if not self.texture:
			return
		gl.glColor4f(*self.color)
		gl.glBindTexture(gl.GL_TEXTURE_2D, self.texture)
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
