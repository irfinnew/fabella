#! /usr/bin/env python3
# Fabella - Simple, elegant video library and player.
#
# Copyright 2020-2021 Marcel Moreaux.
# Licensed under GPL v2.0, or (at your option) any later version.
# (SPDX GPL-2.0-or-later) See LICENSE file for details.

# Ugh. Somehow, despite running under Wayland/EGL, PyOpenGL ends up using GLX?
# Forcing EGL makes the program work.
# https://stackoverflow.com/questions/42185728/why-is-glgenvertexarrays-undefined-in-pyopengl-when-using-gtkglarea
import os
os.environ['PYOPENGL_PLATFORM'] = 'egl'

import sys
import glfw
import time

import loghelper
from window import Window
from tile import Tile
from menu import Menu
from video import Video
import draw



loghelper.set_up_logging(15, 0, 'fabella.log')
log = loghelper.get_logger('Fabella', loghelper.Color.Red)
log.info('Starting Fabella.')



#### Initialization
# FIXME: hardcoded monitor
window = Window(2, "Fabella")
draw.State.initialize(window.width, window.height)
Tile.initialize()
menu = Menu(sys.argv[1], window.width, window.height, enabled=True)
video = Video(window.width, window.height)



#### Main loop
last_time = 0
frame_count = 0
log.info('Starting main loop')
while not window.closed():
	window.wait()

	for key, scancode, action, modifiers in window.get_events():
		if action in [glfw.PRESS, glfw.REPEAT]:
			log.info(f'Parsing key {key} in {"menu" if menu.enabled else "video"} mode')

			# Global keys
			if key == glfw.KEY_Q and modifiers == glfw.MOD_CONTROL:
				log.info('Quitting.')
				menu.forget()
				video.stop()
				window.terminate()
				exit()
			if key == glfw.KEY_F:
				window.set_fullscreen()
			if key == glfw.KEY_T:
				draw.SuperTexture.dump()
			if key == glfw.KEY_D:
				log.info('Cycling dark mode')
				menu.show_dark_mode(not menu.dark_mode)

			# Menu keys
			if menu.enabled:
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
			else:
				# Video keys
				if key in [glfw.KEY_ESCAPE, glfw.KEY_ENTER]:
					video.stop()
					menu.open()
				if key == glfw.KEY_O:
					log.info('Cycling OSD')
					#video.mpv['osd-level'] ^= 2
					menu.show_osd(not menu.osd)
				if key == glfw.KEY_SPACE:
					video.pause()
					menu.show_osd(force=video.paused)
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

	video.render()
	menu.tick(video)
	draw.Animation.animate_all()
	draw.State.render()
	if draw.State.swap_needed:
		window.swap_buffers()

	frame_count += 1
	new = time.time()
	if int(new) > last_time:
		last_time = int(new)
		log.info(f'Rendering at {frame_count} fps')
		frame_count = 0

log.info('End of program.')
window.terminate()
