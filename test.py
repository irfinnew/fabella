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
quads = []
for x in range(5):
	for y in range(3, -1, -1):
		q = draw.TexturedQuad(x * 384 + 384 // 2 - 64, y * 300 + 300 // 2 - 64, 128, 128, 1, texture=random.choice(textures))
		q.orig_x = q.x
		q.orig_y = q.y
		quads.append(q)

def ease_out(x):
	return 1 - (1 - x) ** 3

def ease_in(x):
	return x ** 3

#### Main loop
frame_time = time.time()
frame_count = 0
anim_start = time.time()
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

	gl.glViewport(0, 0, window.width, window.height)
	gl.glClearColor(0.0, 0.0, 0.0, 1)
	gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)
	gl.glMatrixMode(gl.GL_PROJECTION)
	gl.glLoadIdentity()
	gl.glOrtho(0.0, window.width, 0.0, window.height, 0.0, 1.0)
	gl.glMatrixMode (gl.GL_MODELVIEW)

	dt = time.time() - anim_start
	if dt < 1:
		for q in quads:
			dq = dt - q.orig_x / (1920*8) + (q.orig_y - 1200) / (1200*16)
			dq *= 5
			dq = min(dq, 1)
			dq = ease_out(dq)
			q.x = q.orig_x + 1920 - dq * 1920

	if dt > 1:
		for q in quads:
			dq = (dt - 1) - q.orig_x / (1920*8) + (q.orig_y - 1200) / (1200*16)
			dq *= 5
			dq = max(dq, 0)
			dq = ease_in(dq)
			q.x = q.orig_x - dq * 1920

	if dt > 2:
		anim_start = time.time()

	draw.render()
	window.swap_buffers()

	frame_count += 1
	if time.time() - frame_time > 1:
		print(f'{frame_count} FPS')
		frame_count = 0
		frame_time += 1
