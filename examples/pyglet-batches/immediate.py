#!/usr/bin/env python

import time
import random
import pyglet
import pyglet.gl as gl
pyglet.options['vsync'] = False

# immediate: 2600

BOUNCIES = 2600
MARGIN = 10

window = pyglet.window.Window(resizable=True)
#batch = pyglet.graphics.Batch()

class Bouncy:
	def __init__(self, width, height):
		self.sx = random.randint(10, 40)
		self.sy = random.randint(10, 40)
		self.x = random.randint(MARGIN, width - MARGIN - self.sx)
		self.y = random.randint(MARGIN, width - MARGIN - self.sy)
		self.dx = random.uniform(-3, 3)
		self.dy = random.uniform(-3, 3)
		self.color = (random.random(), random.random(), random.random())

	def advance(self, width, height):
		if self.x + self.dx < MARGIN:
			self.dx = abs(self.dx)
		if self.x + self.dx + self.sx > width - MARGIN:
			self.dx = -abs(self.dx)
		if self.y + self.dy < MARGIN:
			self.dy = abs(self.dy)
		if self.y + self.dy + self.sy > height - MARGIN:
			self.dy = -abs(self.dy)

		self.x += self.dx
		self.y += self.dy

		if self.x + self.sx > width - MARGIN:
			self.x = width - MARGIN - self.sx
		if self.y + self.sy > height - MARGIN:
			self.y = height - MARGIN - self.sy

	def draw(self):
		x1 = self.x
		y1 = self.y
		x2 = x1 + self.sx
		y2 = y1 + self.sy
		gl.glColor3f(*self.color)
		gl.glVertex2f(x1, y1)
		gl.glVertex2f(x2, y1)
		gl.glVertex2f(x2, y2)
		gl.glVertex2f(x1, y2)

bouncies = [Bouncy(window.width, window.height) for _ in range(BOUNCIES)]

last_time = 0
@window.event
def on_draw():
	global last_time, window
	t = time.time()
	frame_time = t - last_time
	fps = 1 / frame_time
	last_time = t
	frame_time = int(frame_time * 1000)
	print(f'on_draw @ {fps:.1f} fps, elapsed = {frame_time} ms')

	gl.glViewport(0, 0, window.width, window.height)

	gl.glClearColor(0, 0, 0, 1)
	window.clear()

	gl.glBegin(gl.GL_QUADS)
	for b in bouncies:
		b.advance(window.width, window.height)
		b.draw()
	gl.glEnd()


pyglet.clock.schedule_interval(lambda x: None, 1/50)
pyglet.app.run()
