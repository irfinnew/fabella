#! /usr/bin/env python3

import os
# ^&!@%#^%^$@!#&^$!
# Somehow, despite running under Wayland/EGL, PyOpenGL ends up using GLX?
# Forcing EGL makes the program work.
# https://stackoverflow.com/questions/42185728/why-is-glgenvertexarrays-undefined-in-pyopengl-when-using-gtkglarea
os.environ['PYOPENGL_PLATFORM'] = 'egl'

import glfw
import OpenGL.GL as gl
import OpenGL.GL.shaders
import time
import math
import random
import PIL.Image
import ctypes
import array



VERTEX_SHADER = """#version 330 core
layout (location = 0) in vec2 position;
layout (location = 1) in vec4 XY;
layout (location = 2) in vec4 UV;
layout (location = 3) in vec4 color;
layout (location = 4) in float scale;

out VDATA {
	vec4 XY;
	vec4 UV;
	vec4 color;
	float scale;
} vdata;

void main()
{
	vdata.XY = XY;
	vdata.UV = UV;
	vdata.color = color;
	vdata.scale = scale;
	gl_Position = vec4(position, 0.0, 1.0);
}
"""

GEOMETRY_SHADER = """#version 330 core
layout (points) in;
layout (triangle_strip, max_vertices = 4) out;

in VDATA {
	vec4 XY;
	vec4 UV;
	vec4 color;
	float scale;
} vdata[];

out vec2 UV;
out vec4 color;

void main() {
	vec4 position = gl_in[0].gl_Position;

	color = vdata[0].color;

	// Bottom-left
	gl_Position = position + vec4(vdata[0].XY[0], vdata[0].XY[1], 0.0, 0.0) * vdata[0].scale;
	UV = vec2(vdata[0].UV[0], vdata[0].UV[3]);
	EmitVertex();

	// Bottom-right
	gl_Position = position + vec4(vdata[0].XY[2], vdata[0].XY[1], 0.0, 0.0) * vdata[0].scale;
	UV = vec2(vdata[0].UV[2], vdata[0].UV[3]);
	EmitVertex();

	// Top-left
	gl_Position = position + vec4(vdata[0].XY[0], vdata[0].XY[3], 0.0, 0.0) * vdata[0].scale;
	UV = vec2(vdata[0].UV[0], vdata[0].UV[1]);
	EmitVertex();

	// Top-right
	gl_Position = position + vec4(vdata[0].XY[2], vdata[0].XY[3], 0.0, 0.0) * vdata[0].scale;
	UV = vec2(vdata[0].UV[2], vdata[0].UV[1]);
	EmitVertex();

	EndPrimitive();
}
"""

FRAGMENT_SHADER = """#version 330 core
uniform sampler2D texture;
in vec2 UV;
in vec4 color;

out vec4 FragColor;

void main()
{
	FragColor = texture2D(texture, UV) * color;
}
"""



# Window init
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

# Shaders
geometry_shader = gl.shaders.compileShader(GEOMETRY_SHADER, gl.GL_GEOMETRY_SHADER)
vertex_shader = gl.shaders.compileShader(VERTEX_SHADER, gl.GL_VERTEX_SHADER)
fragment_shader = gl.shaders.compileShader(FRAGMENT_SHADER, gl.GL_FRAGMENT_SHADER)
shader_program = gl.shaders.compileProgram(vertex_shader, fragment_shader)
gl.shaders.glAttachShader(shader_program, geometry_shader)
gl.glLinkProgram(shader_program)

# Arrays / buffers
vao = gl.glGenVertexArrays(1)
gl.glBindVertexArray(vao)

vbo = gl.glGenBuffers(1)
gl.glBindBuffer(gl.GL_ARRAY_BUFFER, vbo)
gl.glEnableVertexAttribArray(0)
gl.glVertexAttribPointer(0, 2, gl.GL_FLOAT, False, 60, ctypes.c_void_p(0))
gl.glEnableVertexAttribArray(1)
gl.glVertexAttribPointer(1, 4, gl.GL_FLOAT, False, 60, ctypes.c_void_p(8))
gl.glEnableVertexAttribArray(2)
gl.glVertexAttribPointer(2, 4, gl.GL_FLOAT, False, 60, ctypes.c_void_p(24))
gl.glEnableVertexAttribArray(3)
gl.glVertexAttribPointer(3, 4, gl.GL_FLOAT, False, 60, ctypes.c_void_p(40))
gl.glEnableVertexAttribArray(4)
gl.glVertexAttribPointer(4, 1, gl.GL_FLOAT, False, 60, ctypes.c_void_p(56))

gl.glBindBuffer(gl.GL_ARRAY_BUFFER, 0)
gl.glBindVertexArray(0)

# Texture
texture = gl.glGenTextures(1)
gl.glBindTexture(gl.GL_TEXTURE_2D, texture)
gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR)
gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
with PIL.Image.open('natalie.jpg') as image:
	# FIXME: hardcoded texture size
	gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGB, 1024, 1024, 0, gl.GL_RGB, gl.GL_UNSIGNED_BYTE, image.tobytes())
gl.glBindTexture(gl.GL_TEXTURE_2D, 0)
texture_uniform = gl.glGetUniformLocation(shader_program, 'texture')

gl.glEnable(gl.GL_BLEND)
gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
gl.glClearColor(0.1, 0.1, 0.1, 1)

# Data

N = 43
TCHOPS = 4
objects = [
	0.0, 0.0,				# position
	-0.2, -0.2, 0.2, 0.2,	# XY
	0.0, 0.0, 1.0, 1.0,		# UV
	1.0, 1.0, 1.0, 1.0,		# color
	1.0,					# scale
] * N
objects = array.array('f', objects)
for i in range(N):
	idx = i * 15
	# Color
	objects[idx + 10] = random.random()
	objects[idx + 11] = random.random()
	objects[idx + 12] = random.random()

	# Texture coords
	tsize = 1 / TCHOPS
	xoff = random.randrange(TCHOPS) / TCHOPS
	yoff = random.randrange(TCHOPS) / TCHOPS
	objects[idx + 6] = xoff
	objects[idx + 7] = yoff
	objects[idx + 8] = xoff + tsize
	objects[idx + 9] = yoff + tsize

# Background
objects[0:15] = array.array('f', [
	0.0, 0.0,				# position
	-1.0, -1.0, 1.0, 1.0,	# XY
	0.0, 0.0, 1.0, 1.0,		# UV
	0.1, 0.1, 0.1, 1.0,		# color
	1.0,					# scale
])

# Main loop
d = 0.9
s = 0.2
frame_count = 0
frame_time = time.time()
vtime = 0
gtime = 0
window_size = glfw.get_window_size(window)
while not glfw.window_should_close(window):
	glfw.wait_events()

	vtime -= time.time()
	t = time.time() / 10
	for i in range(1, N):
		x = math.sin(t * 2) * d
		y = math.cos(t) * d
		idx = i * 15
		objects[idx] = x
		objects[idx + 1] = y

		foo = abs(y) * .75 + 0.25
		objects[idx + 13] = foo # opacity
		objects[idx + 14] = foo # scale
		t += math.pi * 2 / N
	vtime += time.time()

	newsize = glfw.get_window_size(window)

	gtime -= time.time()
	if newsize != window_size:
		window_size = newsize
		gl.glViewport(0, 0, *window_size)
	#gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)

	gl.glUseProgram(shader_program)
	gl.glUniform1i(texture_uniform, 0)
	gl.glActiveTexture(gl.GL_TEXTURE0)
	gl.glBindTexture(gl.GL_TEXTURE_2D, texture)

	gl.glBindVertexArray(vao)
	gl.glBindBuffer(gl.GL_ARRAY_BUFFER, vbo)
	blah = objects.tobytes()
	gl.glBufferData(gl.GL_ARRAY_BUFFER, len(blah), blah, gl.GL_STATIC_DRAW)
	#gl.glBufferData(gl.GL_ARRAY_BUFFER, objects.nbytes, objects, gl.GL_STATIC_DRAW)
	gl.glDrawArrays(gl.GL_POINTS, 0, N)

	gl.glUseProgram(0)
	gl.glBindBuffer(gl.GL_ARRAY_BUFFER, 0)
	gl.glBindVertexArray(0)
	gtime += time.time()

	glfw.swap_buffers(window)

	frame_count += 1
	if time.time() - frame_time > 1:
		print(f'{frame_count} FPS, vtime={int(vtime*1000)} ms, gtime={int(gtime*1000)} ms')
		frame_count = 0
		frame_time += 1
		vtime = 0
		gtime = 0
