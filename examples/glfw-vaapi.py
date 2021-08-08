#! /usr/bin/env python3

# Requires pyGLFW, PyOpenGL, python-mpv
# https://github.com/mpv-player/mpv/blob/master/libmpv/render_gl.h#L91

import sys
import glfw
import time
import math
import ctypes
import mpv
import OpenGL.GL as gl


#### GLFW setup
if not glfw.init():
	exit(1)
window = glfw.create_window(640, 480, "libmpv wayland/egl/opengl example", None, None)
if not window:
	glfw.terminate()
	exit(1)
glfw.make_context_current(window)
def on_keypress(window, key, scancode, action, modifiers):
	if key == glfw.KEY_ESCAPE:
		glfw.terminate()
		exit()
glfw.set_key_callback(window, on_keypress)


#### Generate FBO + Texture for mpv
fboIDs = (gl.GLuint * 1) ()
gl.glGenFramebuffers(1, fboIDs)
vfboid = fboIDs[0]
gl.glBindFramebuffer(gl.GL_FRAMEBUFFER, vfboid)

textureIDs = (gl.GLuint * 1) ()
gl.glGenTextures(1, textureIDs)
vtid = textureIDs[0]
gl.glBindTexture(gl.GL_TEXTURE_2D, vtid)
gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR)
gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGB, 1920, 1080, 0, gl.GL_RGB, gl.GL_UNSIGNED_BYTE, None)
gl.glFramebufferTexture2D(gl.GL_FRAMEBUFFER, gl.GL_COLOR_ATTACHMENT0, gl.GL_TEXTURE_2D, vtid, 0)
assert gl.glCheckFramebufferStatus(gl.GL_FRAMEBUFFER) == gl.GL_FRAMEBUFFER_COMPLETE

gl.glBindFramebuffer(gl.GL_FRAMEBUFFER, 0)
gl.glBindTexture(gl.GL_TEXTURE_2D, 0)


#### MPV setup
def my_log(loglevel, component, message):
	print('\x1b[32m[{}] {}: {}\x1b[0m'.format(loglevel, component, message))

player = mpv.MPV(log_handler=my_log, loglevel='debug')
player['hwdec'] = 'auto'
#mpv['video-timing-offset'] = 0
mpv_ctx = mpv.MpvRenderContext(
	player,
	'opengl',
	wl_display=ctypes.c_void_p(glfw.get_wayland_display()),
	opengl_init_params={'get_proc_address': mpv.OpenGlCbGetProcAddrFn(lambda _, name: glfw.get_proc_address(name.decode('utf8')))},
)

player.play(sys.argv[1])


#### Main loop
last_time = 0
frame_count = 0
while not glfw.window_should_close(window):
	width, height = glfw.get_window_size(window)
	mpv_ctx.render(flip_y=True, opengl_fbo={'w': 1920, 'h': 1080, 'fbo': vfboid})

	gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
	gl.glEnable(gl.GL_BLEND)
	gl.glEnable(gl.GL_TEXTURE_2D)

	gl.glViewport(0, 0, width, height)
	gl.glClearColor(0.2, 0.2, 0.2, 1)
	gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)
	gl.glMatrixMode(gl.GL_PROJECTION)
	gl.glLoadIdentity()
	gl.glOrtho(0.0, width, 0.0, height, 0.0, 1.0)
	gl.glMatrixMode (gl.GL_MODELVIEW)

	inset = math.sin(time.time()) * 100
	x1 = inset
	y1 = inset
	x2 = width - inset
	y2 = height - inset

	gl.glBindTexture(gl.GL_TEXTURE_2D, vtid)
	gl.glBegin(gl.GL_QUADS)
	gl.glTexCoord2f(0.0, 0.0)
	gl.glVertex2f(x1, y1)
	gl.glTexCoord2f(1.0, 0.0)
	gl.glVertex2f(x2, y1)
	gl.glTexCoord2f(1.0, 1.0)
	gl.glVertex2f(x2, y2)
	gl.glTexCoord2f(0.0, 1.0)
	gl.glVertex2f(x1, y2)
	gl.glEnd()
	gl.glBindTexture(gl.GL_TEXTURE_2D, 0)

	glfw.swap_buffers(window)
	glfw.poll_events()

	frame_count += 1
	new = time.time()
	if int(new) > last_time:
		last_time = int(new)
		print(f'{frame_count} fps')
		frame_count = 0

glfw.terminate()
