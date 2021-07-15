#!/usr/bin/env python

import math
import time
import sys
import ctypes
import pyglet
import pyglet.gl as gl
from mpv import MPV, MpvRenderContext, OpenGlCbGetProcAddrFn
pyglet.options['vsync'] = False


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
mpv['video-timing-offset'] = 0
mpv_ctx = MpvRenderContext(mpv, 'opengl', opengl_init_params={'get_proc_address': OpenGlCbGetProcAddrFn(get_process_address)})

video_coords = [0, 0, 1, 1]


overlay_target = 0
overlay_current = 0
timepos = 0
@mpv.property_observer('percent-pos')
def time_observer(_name, value):
	global timepos
	if value is not None:
		timepos = value / 100

last_time = 0
@window.event
def on_draw(foo=None):
	global last_time
	t = time.time()
	frame_time = t - last_time
	fps = 1 / frame_time
	last_time = t

	print(f'on_draw @ {fps:.1f} fps, elapsed = {int(frame_time * 1000)} ms')

	# MPV seems to reset some of this stuff, so re-init
	gl.glViewport(0, 0, window.width, window.height)
	gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
	gl.glEnable(gl.GL_BLEND)
	gl.glEnable(gl.GL_TEXTURE_2D)

	gl.glClearColor(0, 0, 0, 1)
	window.clear()

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

	x1, y1, x2, y2 = 0, 0, window.width, 4
	gl.glBegin(gl.GL_QUADS)
	gl.glColor4f(0, 0, 0, 1)
	gl.glVertex2f(x1, y1)
	gl.glVertex2f(x2, y1)
	gl.glColor4f(0, 0, 0, 1)
	gl.glVertex2f(x2, y2)
	gl.glVertex2f(x1, y2)
	gl.glEnd()

	x1, y1, x2, y2 = 0, 0, timepos * window.width, 1
	gl.glColor4f(0.4, 0.4, 1, 1)
	gl.glBegin(gl.GL_QUADS); gl.glVertex2f(x1, y1); gl.glVertex2f(x2, y1); gl.glVertex2f(x2, y2); gl.glVertex2f(x1, y2); gl.glEnd()

	global overlay_current
	shade = math.sqrt(overlay_current)
	shade = math.sin(overlay_current * math.pi / 2)
	shade = math.sin((overlay_current - 0.5) * math.pi) / 2 + 0.5

	x1, y1, x2, y2 = 0, 0, window.width, window.height
	gl.glColor4f(0, 0, 0, shade * 0.75)
	gl.glBegin(gl.GL_QUADS); gl.glVertex2f(x1, y1); gl.glVertex2f(x2, y1); gl.glVertex2f(x2, y2); gl.glVertex2f(x1, y2); gl.glEnd()

	x1, y1, x2, y2 = 0, 0, shade * 0.4 * window.width, window.height
	gl.glColor4f(1, 1, 1, 0.5)
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
	global overlay_target
	key = pyglet.window.key

	if symbol == key.Q: exit()
	if symbol == key.O: mpv['osd-level'] ^= 2
	if symbol == key.SPACE: mpv.cycle('pause')
	if symbol == key.RIGHT: mpv.seek(5)
	if symbol == key.LEFT: mpv.seek(-5)
	if symbol == key.UP: mpv.seek(60)
	if symbol == key.DOWN: mpv.seek(-60)
	if symbol == key.LSHIFT: overlay_target = 1; animate()

@window.event
def on_key_release(symbol, modifiers):
	global overlay_target
	key = pyglet.window.key

	if symbol == key.LSHIFT: overlay_target = 0; animate()


#### MPV render new frame when available
def mpv_render(tdelta):
	print('mpv_render')
	mpv_ctx.render(flip_y=True, opengl_fbo={'w': 1920, 'h': 1080, 'fbo': vfboid})


def mpv_update():
	print('mpv_update')
	pyglet.clock.schedule_once(mpv_render, 0)
	pyglet.app.platform_event_loop.notify()

mpv_ctx.update_cb = mpv_update


def animate(foo=None):

	global overlay_current, overlay_target
	delta = 0.04

	if overlay_current < overlay_target:
		overlay_current = min(overlay_current + delta, 1)
	if overlay_current > overlay_target:
		overlay_current = max(overlay_current - delta, 0)

	pyglet.clock.unschedule(animate)
	if overlay_current != overlay_target:
		pyglet.clock.schedule_once(animate, 1/50)

#def nop(foo=None):
#	pass
#pyglet.clock.schedule_interval(nop, 1/30)



mpv.play(sys.argv[1])
pyglet.app.run()
