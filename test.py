#! /usr/bin/env python3

# Requires pyGLFW, PyOpenGL, python-mpv, pillow >= 6.2.0

import math
import sys
import glfw
import time
import OpenGL.GL as gl
import random

import loghelper
from window import Window
import draw
import PIL.Image
import config
import font



loghelper.set_up_logging(15, 0, 'test.log')
log = loghelper.get_logger('Test', loghelper.Color.Red)
log.info('Starting Graphics Test.')



window = Window(2, "Test")

fnt = font.Font('Ubuntu Medium', 36)
text = fnt.text(100, 1100, 2, 'hoi', anchor='tl', lines=1)
quad = draw.FlatQuad(0, 0, window.width, window.height, 0, config.menu.background_color)

textures = [draw.Texture(image=PIL.Image.open(f'img/{fn}.png')) for fn in ['unseen', 'watching', 'tagged']]

import random
quads = [
	#draw.FlatQuad(random.randint(0, window.width - 50), random.randint(0, window.height - 50), 50, 50, 1, (random.random(), random.random(), random.random(), 1))
	draw.TexturedQuad(random.randint(0, window.width - 50), random.randint(0, window.height - 50), 50, 50, 1, texture=random.choice(textures))
	for i in range(500)
]

def sw(s = None):
	if s is None:
		sw.start = time.time()
	else:
		t = int((time.time() - sw.start) * 1000000)
		print(f'{t:>6} us: {s}')

#### Main loop
frame_time = time.time()
frame_count = 0
log.info('Starting main loop')
while not window.closed():
	window.wait()

	for key, scancode, action, modifiers in window.get_events():
		if action == glfw.PRESS:
			log.info(f'Parsing key {key}')
			if key == glfw.KEY_ESCAPE:
				log.info('Quitting.')
				window.terminate()
				exit()
			if key == glfw.KEY_SPACE:
				text.text += random.choice('qwertyuiopasdfghjklzxcvbnm  ')

	## MPV seems to reset some of this stuff, so re-init
	gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
	gl.glEnable(gl.GL_BLEND)
	gl.glEnable(gl.GL_TEXTURE_2D)

	xoff = int(math.sin(time.time() * 1) * 1920) + 1920
	gl.glViewport(0, 0, window.width, window.height)
	gl.glClearColor(0.0, 0.0, 0.0, 1)
	gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)
	gl.glMatrixMode(gl.GL_PROJECTION)
	gl.glLoadIdentity()
	gl.glOrtho(0.0, window.width, 0.0, window.height, 0.0, 1.0)
	gl.glMatrixMode (gl.GL_MODELVIEW)
	gl.glViewport(xoff, 0, window.width, window.height)

	sw()
	for q in quads:
		q.x += random.randint(-1, 1)
		q.y += random.randint(-1, 1)
	sw('move')

	sw()
	draw.render()
	sw('render')
	sw()
	window.swap_buffers()
	sw('swap')

	frame_count += 1
	if time.time() - frame_time > 1:
		print(f'{frame_count} FPS')
		frame_count = 0
		frame_time += 1
