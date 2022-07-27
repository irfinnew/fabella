#! /usr/bin/env python3

import os
# ^&!@%#^%^$@!#&^$!
# Somehow, despite running under Wayland/EGL, PyOpenGL ends up using GLX?
# Forcing EGL makes the program work.
os.environ['PYOPENGL_PLATFORM'] = 'egl'

import numpy as np
import glfw
import OpenGL.GL as gl
import OpenGL.GL.shaders



VERTEX_SHADER = """#version 330
in vec4 position;
void main() { gl_Position = position; }
"""

FRAGMENT_SHADER = """#version 330
void main() { gl_FragColor = vec4(1.0f, 0.0f,0.0f,1.0f); }
"""

triangles = [
	-0.5, -0.5, 0.0,
	0.5, -0.5, 0.0,
	0.0, 0.5, 0.0,
]



glfw.init()
glfw.window_hint(glfw.OPENGL_FORWARD_COMPAT, gl.GL_TRUE)
glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
window = glfw.create_window(1280, 720, 'test', None, None)
glfw.make_context_current(window)

vertex_shader = gl.shaders.compileShader(VERTEX_SHADER, gl.GL_VERTEX_SHADER)
fragment_shader = gl.shaders.compileShader(FRAGMENT_SHADER, gl.GL_FRAGMENT_SHADER)
shader_program = gl.shaders.compileProgram(vertex_shader, fragment_shader)

triangles = np.array(triangles, dtype=np.float32)

vao = gl.glGenVertexArrays(1)
gl.glBindVertexArray(vao)

vbo = gl.glGenBuffers(1)
gl.glBindBuffer(gl.GL_ARRAY_BUFFER, vbo)
gl.glBufferData(gl.GL_ARRAY_BUFFER, triangles.nbytes, triangles, gl.GL_STATIC_DRAW)

position = gl.glGetAttribLocation(shader_program, 'position')
gl.glVertexAttribPointer(position, 3, gl.GL_FLOAT, gl.GL_FALSE, 0, None)
gl.glEnableVertexAttribArray(position)

#gl.glBindBuffer(gl.GL_ARRAY_BUFFER, 0)
#gl.glBindVertexArray(0)


while not glfw.window_should_close(window):
	glfw.wait_events()

	gl.glClearColor(0.0, 0.0, 1.0, 1.0)
	gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)
	gl.glUseProgram(shader_program)
	gl.glDrawArrays(gl.GL_TRIANGLES, 0, 3)
	gl.glUseProgram(0)

	glfw.swap_buffers(window)
