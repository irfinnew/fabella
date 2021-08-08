#!/usr/bin/env python

import time
import random
import pyglet
import pyglet.gl as gl
pyglet.options['vsync'] = False

# immediate: 2600
# batched: 8000+

BOUNCIES = 8000
MARGIN = 150

window = pyglet.window.Window(resizable=True)
batch = pyglet.graphics.Batch()

class Bouncy:
	def __init__(self, width, height, batch):
		self.sx = random.randint(10, 40)
		self.sy = random.randint(10, 40)
		self.x = random.randint(MARGIN, width - MARGIN - self.sx)
		self.y = random.randint(MARGIN, height- MARGIN - self.sy)
		self.dx = random.uniform(-3, 3)
		self.dy = random.uniform(-3, 3)
		self.color = (random.random(), random.random(), random.random())

		x1 = self.x
		y1 = self.y
		x2 = x1 + self.sx
		y2 = y1 + self.sy
		self.vertex_list = batch.add(4, gl.GL_QUADS, None, ('v2f', (x1, y1, x2, y1, x2, y2, x1, y2)), ('c3f', self.color * 4))

	def advance(self, width, height):
		self.x += self.dx
		self.y += self.dy

		if self.x < MARGIN:
			#self.dx = abs(self.dx)
			self.dx += 0.1
		if self.x + self.sx > width - MARGIN:
			#self.dx = -abs(self.dx)
			self.dx -= 0.1
		if self.y < MARGIN:
			#self.dy = abs(self.dy)
			self.dy += 0.1
		if self.y + self.sy > height - MARGIN:
			#self.dy = -abs(self.dy)
			self.dy -= 0.1

		x1 = self.x
		y1 = self.y
		x2 = x1 + self.sx
		y2 = y1 + self.sy
		self.vertex_list.vertices = (x1, y1, x2, y1, x2, y2, x1, y2)

bouncies = [Bouncy(window.width, window.height, batch) for _ in range(BOUNCIES)]

last_time = 0
@window.event
def on_draw():
	global last_time, window, batch
	t = time.time()
	frame_time = t - last_time
	fps = 1 / frame_time
	last_time = t
	frame_time = int(frame_time * 1000)
	print(f'on_draw @ {fps:.1f} fps, elapsed = {frame_time} ms')

	gl.glViewport(0, 0, window.width, window.height)

	gl.glClearColor(0, 0, 0, 1)
	window.clear()

	for b in bouncies:
		b.advance(window.width, window.height)
	batch.draw()


pyglet.clock.schedule_interval(lambda x: None, 1/50)
pyglet.app.run()
