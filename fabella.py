#! /usr/bin/env python3

# Requires pyGLFW, PyOpenGL, python-mpv, pillow >= 6.2.0

import sys
import glfw
import time
import OpenGL.GL as gl
from logger import Logger
from window import Window
from menu import Menu
from video import Video

window = Window(1280, 720, "libmpv wayland/egl/opengl example")
menu = Menu(sys.argv[1], enabled=True)
video = Video()
log = Logger(module='Main', color=Logger.Red)

#### Main loop
last_time = 0
frame_count = 0
log.info('Starting main loop')
while not window.closed():
	window.wait()

	if not menu.enabled:
		for key, scancode, action, modifiers  in window.get_events():
			if action == glfw.PRESS:
				log.info(f'Parsing key {key} in video mode')
				if key == glfw.KEY_Q:
					log.info('Quitting.')
					video.stop()
					window.terminate()
					exit()
				if key == glfw.KEY_ESCAPE:
					#video.pause(True)  # Dunno
					menu.open()
				if key == glfw.KEY_ENTER:
					video.seek(-0.01, 'absolute')
					#menu.open()
				if key == glfw.KEY_F:
					window.set_fullscreen()
				if key == glfw.KEY_O:
					log.info('Cycling OSD')
					video.mpv['osd-level'] ^= 2
				if key == glfw.KEY_SPACE:
					video.pause()
				if key == glfw.KEY_RIGHT:
					video.seek(5)
				if key == glfw.KEY_LEFT:
					video.seek(-5)
				if key == glfw.KEY_UP:
					video.seek(60)
				if key == glfw.KEY_DOWN:
					video.seek(-60)

				if key in [glfw.KEY_J, glfw.KEY_K]:
					log.warning('Cycling Subtitles (FIXME: move code)')
					if key == glfw.KEY_J:
						video.mpv.cycle('sub')
					else:
						video.mpv.cycle('sub', 'down')
					subid = video.mpv.sub

					if subid is False:
						video.mpv.show_text('Subtitles off')
					else:
						sublang = 'unknown'
						subtitle = ''
						sub_count = 0
						for track in video.mpv.track_list:
							if track['type'] == 'sub':
								sub_count += 1
								if track['id'] == subid:
									sublang = track.get('lang', sublang)
									subtitle = track.get('title', subtitle)

						video.mpv.show_text(f'Subtitles {subid}/{sub_count}: {sublang.upper()}\n{subtitle}')

	if menu.enabled:
		for key, scancode, action, modifiers  in window.get_events():
			if action == glfw.PRESS:
				log.info(f'Parsing key {key} in menu mode')
				if key == glfw.KEY_Q:
					log.info('Quitting.')
					video.stop()
					window.terminate()
					exit()
				if key == glfw.KEY_F:
					window.set_fullscreen()
				if key == glfw.KEY_ESCAPE:
					menu.close()
					#video.pause(False)
				if key in [glfw.KEY_ENTER, glfw.KEY_SPACE]:
					menu.enter(video)
				if key == glfw.KEY_BACKSPACE:
					menu.back()
				if key == glfw.KEY_UP:
					menu.previous_row()
				if key == glfw.KEY_DOWN:
					menu.next_row()
				if key == glfw.KEY_RIGHT:
					menu.next()
				if key == glfw.KEY_LEFT:
					menu.previous()

	width, height = window.size()
	log.debug(f'Window size {width}x{height}')

	video.render()

	# MPV seems to reset some of this stuff, so re-init
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

	video.draw(width, height)

	if menu.enabled:
		menu.draw(width, height)

	window.swap_buffers()

	frame_count += 1
	new = time.time()
	if int(new) > last_time:
		last_time = int(new)
		#print(f'{frame_count} fps')
		log.info(f'Rendering at {frame_count} fps')
		frame_count = 0

log.info('End of program.')
window.terminate()
