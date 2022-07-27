#! /usr/bin/env python3

import os
# ^&!@%#^%^$@!#&^$!
# Somehow, despite running under Wayland/EGL, PyOpenGL ends up using GLX?
# Forcing EGL makes the program work.
# https://stackoverflow.com/questions/42185728/why-is-glgenvertexarrays-undefined-in-pyopengl-when-using-gtkglarea
os.environ['PYOPENGL_PLATFORM'] = 'egl'

import numpy as np
import glfw
import OpenGL.GL as gl
import time
import math
import random



glfw.init()
glfw.window_hint(glfw.DECORATED, False)
glfw.window_hint(glfw.AUTO_ICONIFY, False)
glfw.window_hint(glfw.FOCUSED, False)

window = glfw.create_window(1280, 720, 'test', None, None)
glfw.make_context_current(window)

print('GL_MAX_TEXTURE_IMAGE_UNITS', gl.glGetInteger(gl.GL_MAX_TEXTURE_IMAGE_UNITS))
print('GL_MAX_COMBINED_TEXTURE_IMAGE_UNITS', gl.glGetInteger(gl.GL_MAX_COMBINED_TEXTURE_IMAGE_UNITS))
print('GL_MAX_TEXTURE_SIZE', gl.glGetInteger(gl.GL_MAX_TEXTURE_SIZE))
print('GL_MAX_ARRAY_TEXTURE_LAYERS', gl.glGetInteger(gl.GL_MAX_ARRAY_TEXTURE_LAYERS))

gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
gl.glEnable(gl.GL_BLEND)
gl.glClearColor(0, 0, 0, 1)

N = 100
colors = []
for i in range(N):
	color = [random.random(), random.random(), random.random(), random.random() / 2 + 0.5]
	colors.append(color)

d = 0.9
s = 0.2
while not glfw.window_should_close(window):
	glfw.wait_events()

	t = time.time()

	triangles = []
	for i in range(N):
		x = math.sin(t * 2) * d
		y = math.cos(t) * d
		idx = i * 8
		ts = [(x - s, y - s), (x - s, y + s), (x + s, y + s), (x + s, y - s)]
		triangles.append(ts)
		t += math.pi * 2 / N

	gl.glViewport(0, 0, *glfw.get_window_size(window))
	gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)

	gl.glBegin(gl.GL_QUADS)
	for i in range(N):
		gl.glColor4f(*colors[i])
		gl.glVertex2f(*triangles[i][0])
		gl.glVertex2f(*triangles[i][1])
		gl.glVertex2f(*triangles[i][2])
		gl.glVertex2f(*triangles[i][3])
	gl.glEnd()

	glfw.swap_buffers(window)
