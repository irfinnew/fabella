#! /usr/bin/env python3

# Requires pyGLFW, PyOpenGL, python-mpv
# https://github.com/mpv-player/mpv/blob/master/libmpv/render_gl.h#L91

import sys
import glfw
import time
import ctypes
import mpv
import OpenGL.GL as gl


#### GLFW setup
if not glfw.init():
	exit(1)
window = glfw.create_window(640, 480, "Hello World", None, None)
if not window:
	glfw.terminate()
	exit(1)
glfw.make_context_current(window)


#### Generate FBO
fboIDs = (gl.GLuint * 1) ()
gl.glGenFramebuffers(1, fboIDs)
vfboid = fboIDs[0]
gl.glBindFramebuffer(gl.GL_FRAMEBUFFER, vfboid)


#### Generate Texture, bind to FBO
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
def get_proc_address(_, name):
	return glfw.get_proc_address(name.decode('utf8'))

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
while not glfw.window_should_close(window):
	mpv_ctx.render(flip_y=True, opengl_fbo={'w': 1920, 'h': 1080, 'fbo': vfboid})

	gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
	gl.glEnable(gl.GL_BLEND)
	gl.glEnable(gl.GL_TEXTURE_2D)

	gl.glViewport(0, 0, 500, 500)
	gl.glClearColor(1, 1, 1, 1)
	gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)
	gl.glMatrixMode(gl.GL_PROJECTION)
	gl.glLoadIdentity()
	gl.glOrtho(0.0, 500, 0.0, 500, 0.0, 1.0)
	gl.glMatrixMode (gl.GL_MODELVIEW)

	gl.glBindTexture(gl.GL_TEXTURE_2D, vtid)
	gl.glBegin(gl.GL_QUADS)
	gl.glTexCoord2f(0.0, 0.0)
	gl.glVertex2f(100, 100)
	gl.glTexCoord2f(1.0, 0.0)
	gl.glVertex2f(300, 100)
	gl.glTexCoord2f(1.0, 1.0)
	gl.glVertex2f(300, 200)
	gl.glTexCoord2f(0.0, 1.0)
	gl.glVertex2f(100, 200)
	gl.glEnd()
	gl.glBindTexture(gl.GL_TEXTURE_2D, 0)

	glfw.swap_buffers(window)
	glfw.poll_events()

glfw.terminate()
