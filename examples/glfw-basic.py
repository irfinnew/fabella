#! /usr/bin/env python3

import glfw
import time
import OpenGL.GL as gl

# Initialize the library
if not glfw.init():
	exit(1)
# Create a windowed mode window and its OpenGL context
window = glfw.create_window(640, 480, "Hello World", None, None)
if not window:
	glfw.terminate()
	exit()

# Make the window's context current
glfw.make_context_current(window)

frame_count = 0
last = time.time()

print(dir(glfw))
print(glfw.get_wayland_display())

# Loop until the user closes the window
while not glfw.window_should_close(window):
	# Render here, e.g. using pyOpenGL
	gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
	gl.glEnable(gl.GL_BLEND)
	#gl.glEnable(gl.GL_TEXTURE_2D)

	gl.glViewport(0, 0, 640, 480)
	gl.glClearColor(1, 1, 1, 1)
	gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)
	gl.glMatrixMode(gl.GL_PROJECTION)
	gl.glLoadIdentity()
	gl.glOrtho(0.0, 640, 0.0, 480, 0.0, 1.0)
	gl.glMatrixMode (gl.GL_MODELVIEW)

	#gl.glBindTexture(gl.GL_TEXTURE_2D, vtid)
	gl.glBegin(gl.GL_QUADS)
	gl.glColor3f(0, 0, 0)
	#gl.glTexCoord2f(0.0, 0.0)
	gl.glVertex2f(100, 100)
	#gl.glTexCoord2f(1.0, 0.0)
	gl.glVertex2f(300, 100)
	#gl.glTexCoord2f(1.0, 1.0)
	gl.glVertex2f(300, 200)
	#gl.glTexCoord2f(0.0, 1.0)
	gl.glVertex2f(100, 200)
	gl.glEnd()
	#gl.glBindTexture(gl.GL_TEXTURE_2D, 0)

	# Swap front and back buffers
	glfw.swap_buffers(window)

	# Poll for and process events
	glfw.poll_events()

	frame_count += 1
	new = time.time()
	if int(new) > int(last):
		last = int(new)
		print(f'{frame_count} fps')
		frame_count = 0

glfw.terminate()
