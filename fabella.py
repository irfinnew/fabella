#!/usr/bin/env python

import sys
import ctypes
import pyglet
import pyglet.gl as gl
from mpv import MPV, MpvRenderContext, OpenGlCbGetProcAddrFn


# FIXME: texture is a fixed 1920x1080



#### Pyglet setup

window = pyglet.window.Window(resizable=True)
#batch = pyglet.graphics.Batch()



# Generate FBO
fboIDs = (gl.GLuint * 1) ()
gl.glGenFramebuffers(1, fboIDs)
vfboid = fboIDs[0]
gl.glBindFramebuffer(gl.GL_FRAMEBUFFER, vfboid)

# Generate Texture, bind to FBO
textureIDs = (gl.GLuint * 1) ()
gl.glGenTextures(1, textureIDs)
vtid = textureIDs[0]
gl.glBindTexture(gl.GL_TEXTURE_2D, vtid)
gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR)
gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGB, 1920, 1080, 0, gl.GL_RGB, gl.GL_UNSIGNED_BYTE, None)
gl.glFramebufferTexture2D(gl.GL_FRAMEBUFFER, gl.GL_COLOR_ATTACHMENT0, gl.GL_TEXTURE_2D, vtid, 0)
assert gl.glCheckFramebufferStatus(gl.GL_FRAMEBUFFER) == gl.GL_FRAMEBUFFER_COMPLETE



#### MPV setup

def get_process_address(_, name):
	cname = ctypes.cast(ctypes.c_char_p(name), ctypes.POINTER(ctypes.c_ubyte))
	address = gl.glx.glXGetProcAddress(cname)
	return ctypes.cast(address, ctypes.c_void_p).value

mpv = MPV()
mpv['hwdec'] = 'vaapi-copy'
mpv_ctx = MpvRenderContext(mpv, 'opengl', opengl_init_params={'get_proc_address': OpenGlCbGetProcAddrFn(get_process_address)})

video_coords = [0, 0, 1, 1]


timepos = 0
@mpv.property_observer('percent-pos')
def time_observer(_name, value):
	global timepos
	if value is not None:
		timepos = value / 100

@window.event
def on_draw(foo=None):
	gl.glClearColor(0, 0, 0, 1)
	window.clear()

	if mpv_ctx.update():
		mpv_ctx.render(flip_y=True, opengl_fbo={'w': 1920, 'h': 1080, 'fbo': vfboid})

	# MPV seems to reset some of this stuff, so re-init
	gl.glViewport(0, 0, window.width, window.height)
	gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
	gl.glEnable(gl.GL_BLEND)
	gl.glEnable(gl.GL_TEXTURE_2D)

	x1 = window.width * video_coords[0]
	x2 = window.width * video_coords[2]
	y1 = window.height * video_coords[1]
	y2 = window.height * video_coords[3]
	gl.glColor4f(1, 1, 1, 1)
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

	global timepos

	x1, y1, x2, y2 = 0, 0, window.width, 3
	gl.glBegin(gl.GL_QUADS)
	gl.glColor4f(0, 0, 0, 0.75)
	gl.glVertex2f(x1, y1)
	gl.glVertex2f(x2, y1)
	gl.glColor4f(0, 0, 0, 0.75)
	gl.glVertex2f(x2, y2)
	gl.glVertex2f(x1, y2)
	gl.glEnd()

	x1, y1, x2, y2 = 0, 0, timepos * window.width, 1
	gl.glColor4f(0.5, 0.5, 1, 1)
	gl.glBegin(gl.GL_QUADS); gl.glVertex2f(x1, y1); gl.glVertex2f(x2, y1); gl.glVertex2f(x2, y2); gl.glVertex2f(x1, y2); gl.glEnd()


@window.event
def on_mouse_drag(x, y, dx, dy, buttons, modifiers):
	x /= window.width
	dx /= window.width
	y /= window.height
	dy /= window.height

	# Drag
	if buttons == 1 and video_coords[0] < x < video_coords[2] and video_coords[1] < y < video_coords[3]:
		video_coords[0] += dx
		video_coords[2] += dx
		video_coords[1] += dy
		video_coords[3] += dy

		if video_coords[0] < 0:
			video_coords[2] -= video_coords[0]
			video_coords[0] = 0

		if video_coords[2] > 1:
			video_coords[0] -= video_coords[2] - 1
			video_coords[2] = 1

		if video_coords[1] < 0:
			video_coords[3] -= video_coords[1]
			video_coords[1] = 0

		if video_coords[3] > 1:
			video_coords[1] -= video_coords[3] - 1
			video_coords[3] = 1

	# Resize 
	if buttons == 4 and video_coords[0] < x < video_coords[2] and video_coords[1] < y < video_coords[3]:
		video_coords[2] += dx
		video_coords[1] += dy

		if video_coords[2] < video_coords[0] + 0.05:
			video_coords[2] = video_coords[0] + 0.05

		if video_coords[2] > 1:
			video_coords[2] = 1

		if video_coords[1] < 0:
			video_coords[1] = 0

		if video_coords[1] > video_coords[3] - 0.05:
			video_coords[1] = video_coords[3] - 0.05

@window.event
def on_key_press(symbol, modifiers):
	key = pyglet.window.key

	if symbol == key.Q: exit()
	if symbol == key.O: mpv['osd-level'] = 3 - mpv['osd-level']
	if symbol == key.SPACE: mpv.cycle('pause')
	if symbol == key.RIGHT: mpv.seek(5)
	if symbol == key.LEFT: mpv.seek(-5)
	if symbol == key.UP: mpv.seek(60)
	if symbol == key.DOWN: mpv.seek(-60)

# Set up a 1ms NOP callback. Somehow pyglet limits the updates to the framerate of the video. How?
# How does it even know? Something vsync related?
#mpv_ctx.update_cb = None
def nop(foo=None):
	print(pyglet.clock.get_fps())
	pass
pyglet.clock.schedule_interval(nop, 1/1000)

mpv.play(sys.argv[1])
pyglet.app.run()
