#! /usr/bin/env python3

# Requires pyGLFW, PyOpenGL, python-mpv, pillow >= 6.2.0

import sys
import glfw
import time
import OpenGL.GL as gl

import loghelper
from window import Window
from menu import Menu
from video import Video



loghelper.set_up_logging(15, 0, 'fabella.log')
log = loghelper.get_logger('Fabella', loghelper.Color.Red)



window = Window(1920, 1080, "Fabella")
menu = Menu(sys.argv[1], enabled=True)
video = Video()

#### Main loop
last_time = 0
frame_count = 0
log.info('Starting main loop')
while not window.closed():
	window.wait()

	if not menu.enabled:
		for key, scancode, action, modifiers in window.get_events():
			if action == glfw.PRESS:
				log.info(f'Parsing key {key} in video mode')
				if key == glfw.KEY_Q and modifiers == glfw.MOD_CONTROL:
					log.info('Quitting.')
					menu.forget()
					video.stop()
					window.terminate()
					exit()
				if key == glfw.KEY_ESCAPE:
					#video.pause(True)  # Dunno
					menu.open()
				if key == glfw.KEY_ENTER:
					#video.seek(-0.01, 'absolute')
					video.stop()
					menu.open()
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
				if key == glfw.KEY_PAGE_UP:
					video.seek(600)
				if key == glfw.KEY_PAGE_DOWN:
					video.seek(-600)

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
		for key, scancode, action, modifiers in window.get_events():
			if action == glfw.PRESS:
				log.info(f'Parsing key {key} in menu mode')
				if key == glfw.KEY_Q and modifiers == glfw.MOD_CONTROL:
					log.info('Quitting.')
					menu.forget()
					video.stop()
					window.terminate()
					exit()
				if key == glfw.KEY_F:
					window.set_fullscreen()
				if key == glfw.KEY_ESCAPE:
					# FIXME Hmm; the idea is right, but the variable definitely needs a better name.
					if video.should_render:
						menu.close()
					else:
						log.info('No video open; refusing to close menu.')
					#video.pause(False)
				if key == glfw.KEY_TAB and modifiers == 0:
					menu.toggle_seen()
				if key == glfw.KEY_TAB and modifiers == glfw.MOD_SHIFT:
					menu.toggle_seen_all()
				if key in [glfw.KEY_ENTER, glfw.KEY_SPACE]:
					menu.enter(video)
				if key == glfw.KEY_BACKSPACE:
					menu.back()
				if key in [glfw.KEY_UP, glfw.KEY_K]:
					menu.previous_row()
				if key in [glfw.KEY_DOWN, glfw.KEY_J]:
					menu.next_row()
				if key in [glfw.KEY_RIGHT, glfw.KEY_L]:
					menu.next()
				if key in [glfw.KEY_LEFT, glfw.KEY_H]:
					menu.previous()
				if key == glfw.KEY_DELETE:
					menu.toggle_trash()

	width, height = window.size()
	#log.debug(f'Window size {width}x{height}')

	video.render(width, height)

	# MPV seems to reset some of this stuff, so re-init
	gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
	gl.glEnable(gl.GL_BLEND)
	gl.glEnable(gl.GL_TEXTURE_2D)

	gl.glViewport(0, 0, width, height)
	gl.glClearColor(0.0, 0.0, 0.0, 1)
	gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)
	gl.glMatrixMode(gl.GL_PROJECTION)
	gl.glLoadIdentity()
	gl.glOrtho(0.0, width, 0.0, height, 0.0, 1.0)
	gl.glMatrixMode (gl.GL_MODELVIEW)

	video.draw(width, height)

	if menu.enabled:
		menu.draw(width, height, transparent=video.rendered)

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
