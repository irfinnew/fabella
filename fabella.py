#! /usr/bin/env python3

# Requires pyGLFW, PyOpenGL, python-mpv, pillow >= 6.2.0

import sys
import glfw
import time
import OpenGL.GL as gl

import loghelper
from window import Window
from tile import Tile
from menu import Menu
from video import Video
import draw



loghelper.set_up_logging(15, 0, 'fabella.log')
log = loghelper.get_logger('Fabella', loghelper.Color.Red)
log.info('Starting Fabella.')



# FIXME: hardcoded monitor
window = Window(2, "Fabella")
draw.initialize()
Tile.initialize()
menu = Menu(sys.argv[1], window.width, window.height, enabled=True)
video = Video(window.width, window.height)

#### Main loop
last_time = 0
frame_count = 0
osd = False
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
					#video.mpv['osd-level'] ^= 2
					osd = not osd
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
				if key == glfw.KEY_HOME:
					video.seek(0, 'absolute')
				if key == glfw.KEY_END:
					video.seek(-15, 'absolute')

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
				if key == glfw.KEY_PAGE_UP:
					menu.page_up()
				if key == glfw.KEY_PAGE_DOWN:
					menu.page_down()
				if key == glfw.KEY_HOME:
					menu.first()
				if key == glfw.KEY_END:
					menu.last()
				if key == glfw.KEY_DELETE:
					menu.toggle_tagged()

	video.render(window.width, window.height)

	# MPV seems to reset some of this stuff, so re-init
	gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
	gl.glEnable(gl.GL_BLEND)
	gl.glEnable(gl.GL_TEXTURE_2D)

	gl.glViewport(0, 0, window.width, window.height)
	gl.glClearColor(0.0, 0.0, 0.0, 1)
	gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)
	gl.glMatrixMode(gl.GL_PROJECTION)
	gl.glLoadIdentity()
	gl.glOrtho(0.0, window.width, 0.0, window.height, 0.0, 1.0)
	gl.glMatrixMode (gl.GL_MODELVIEW)

	if video.rendered:
		video.draw(window.width, window.height)

		if osd or video.mpv.pause:
			pass
			# FIXME
			#menu.draw_osd(window.width, window.height, video)

	#if menu.enabled:
	#	menu.draw(window.width, window.height, transparent=video.rendered)

	menu.current.animate()
	draw.render()

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
