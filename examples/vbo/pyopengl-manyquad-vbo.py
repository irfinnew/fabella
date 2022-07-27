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
import OpenGL.GL.shaders
import time
import math
import random



VERTEX_SHADER = """#version 330
in vec2 position;
in vec4 color;

out vec4 v_color;

void main()
{
	v_color = color;
	gl_Position = vec4(position, 0.0, 1.0);
}
"""

FRAGMENT_SHADER = """#version 330
in vec4 v_color;

void main()
{
	gl_FragColor = v_color;
}
"""



glfw.init()
glfw.window_hint(glfw.DECORATED, False)
glfw.window_hint(glfw.AUTO_ICONIFY, False)
glfw.window_hint(glfw.FOCUSED, False)

glfw.window_hint(glfw.OPENGL_FORWARD_COMPAT, True)
glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
window = glfw.create_window(1280, 720, 'test', None, None)
glfw.make_context_current(window)

print('GL_MAX_TEXTURE_IMAGE_UNITS', gl.glGetInteger(gl.GL_MAX_TEXTURE_IMAGE_UNITS))
print('GL_MAX_COMBINED_TEXTURE_IMAGE_UNITS', gl.glGetInteger(gl.GL_MAX_COMBINED_TEXTURE_IMAGE_UNITS))
print('GL_MAX_TEXTURE_SIZE', gl.glGetInteger(gl.GL_MAX_TEXTURE_SIZE))
print('GL_MAX_ARRAY_TEXTURE_LAYERS', gl.glGetInteger(gl.GL_MAX_ARRAY_TEXTURE_LAYERS))

vertex_shader = gl.shaders.compileShader(VERTEX_SHADER, gl.GL_VERTEX_SHADER)
fragment_shader = gl.shaders.compileShader(FRAGMENT_SHADER, gl.GL_FRAGMENT_SHADER)
shader_program = gl.shaders.compileProgram(vertex_shader, fragment_shader)

vao = gl.glGenVertexArrays(1)
gl.glBindVertexArray(vao)

vbo = gl.glGenBuffers(1)
gl.glBindBuffer(gl.GL_ARRAY_BUFFER, vbo)
position = gl.glGetAttribLocation(shader_program, 'position')
gl.glVertexAttribPointer(position, 2, gl.GL_FLOAT, False, 0, None)
gl.glEnableVertexAttribArray(position)

cbo = gl.glGenBuffers(1)
gl.glBindBuffer(gl.GL_ARRAY_BUFFER, cbo)
color = gl.glGetAttribLocation(shader_program, 'color')
gl.glVertexAttribPointer(color, 4, gl.GL_FLOAT, True, 0, None)
gl.glEnableVertexAttribArray(color)

ibo = gl.glGenBuffers(1)
gl.glBindBuffer(gl.GL_ELEMENT_ARRAY_BUFFER, ibo)
N = 100
indices = []
for i in range(N):
	o = i * 4
	indices.extend([o + 0, o + 1, o + 2, o + 1, o + 2, o + 3])
indices = np.array(indices, dtype=np.uint16)
gl.glBufferData(gl.GL_ELEMENT_ARRAY_BUFFER, indices.nbytes, indices, gl.GL_STATIC_DRAW)



#gl.glBindBuffer(gl.GL_ELEMENT_ARRAY_BUFFER, 0)
#gl.glBindBuffer(gl.GL_ARRAY_BUFFER, 0)
gl.glBindVertexArray(0)

gl.glEnable(gl.GL_BLEND)
gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
gl.glClearColor(0, 0, 0, 1)

colors = [1] * N * 4 * 4
triangles = [0] * N * 4 * 2

for i in range(N):
	color = [random.random(), random.random(), random.random(), random.random() / 2 + 0.5]
	for a in range(4):
		idx = i * 16 + a * 4
		colors[idx:idx+4] = color

colors = np.array(colors, dtype=np.float32)
triangles = np.array(triangles, dtype=np.float32)
d = 0.9
s = 0.2
while not glfw.window_should_close(window):
	glfw.wait_events()

	t = time.time()

	for i in range(N):
		x = math.sin(t * 2) * d
		y = math.cos(t) * d
		idx = i * 8
		triangles[idx:idx+8] = x - s, y - s, x + s, y - s, x - s, y + s, x + s, y + s
		t += math.pi * 2 / N

	gl.glBindVertexArray(vao)
	gl.glBindBuffer(gl.GL_ARRAY_BUFFER, vbo)
	gl.glBufferData(gl.GL_ARRAY_BUFFER, triangles.nbytes, triangles, gl.GL_STATIC_DRAW)
	gl.glBindBuffer(gl.GL_ARRAY_BUFFER, cbo)
	gl.glBufferData(gl.GL_ARRAY_BUFFER, colors.nbytes, colors, gl.GL_STATIC_DRAW)
	#gl.glBindBuffer(gl.GL_ELEMENT_ARRAY_BUFFER, ibo)

	gl.glViewport(0, 0, *glfw.get_window_size(window))
	gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)
	gl.glUseProgram(shader_program)
	gl.glDrawElements(gl.GL_TRIANGLES, 6 * N, gl.GL_UNSIGNED_SHORT, None)

	gl.glUseProgram(0)
	#gl.glBindBuffer(gl.GL_ELEMENT_ARRAY_BUFFER, 0)
	#gl.glBindBuffer(gl.GL_ARRAY_BUFFER, 0)
	gl.glBindVertexArray(0)

	glfw.swap_buffers(window)
