#! /usr/bin/env python3
# Fabella - Simple, elegant video library and player.
#
# Copyright 2020-2023 Marcel Moreaux.
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



loghelper.set_up_logging(console_level=loghelper.VERBOSE, file_level=loghelper.NOTSET, filename='fabella.log')
log = loghelper.get_logger('Fabella', loghelper.Color.Red)
log.info('Starting Fabella.')


#### Process name
try:
	import setproctitle
	setproctitle.setproctitle(' '.join(['fabella'] + sys.argv[1:]))
except ModuleNotFoundError:
	log.warning("Couldn't load setproctitle module; not changing process name")


#### Configuration
try:
	import local
except ModuleNotFoundError:
	log.info("Couldn't import local.py for configuration overrides.")
else:
	import config
	for cname in [a for a in dir(local) if not a.startswith('__')]:
		config_cls = getattr(config, cname)
		local_cls = getattr(local, cname)
		for aname in [a for a in dir(local_cls) if not a.startswith('__')]:
			value = getattr(local_cls, aname)
			log.info(f'Overriding config.{cname}.{aname} = {value}')
			setattr(config_cls, aname, value)


#### Initialization
# FIXME: hardcoded monitor
window = Window(2, "Fabella")
draw.State.initialize(window.width, window.height)
Tile.initialize()
menu = Menu(sys.argv[1], window.width, window.height, enabled=True)
video = Video(window.width, window.height, menu)


#### Main loop
last_time = 0
frame_count = 0
log.info('Starting main loop')
while not window.closed():
	window.wait()

	for key, scancode, action, modifiers, char in window.get_events():
		# FIXME
		if menu.enabled and menu.searching and char:
			if chr(char) == '/':
				pass
			elif chr(char) == ' ':
				menu.search_next(with_current=False)
			else:
				menu.search_char(char)

		if action in [glfw.PRESS, glfw.REPEAT]:
			log.info(f'Parsing key {key}/{scancode} in {"menu" if menu.enabled else "video"} mode')

			if menu.enabled and menu.searching:
				if key in [glfw.KEY_SLASH, glfw.KEY_ESCAPE]:
					menu.search_end()
				elif key == glfw.KEY_ENTER:
					menu.search_end()
					menu.enter(video)
				if key == glfw.KEY_BACKSPACE:
					menu.search_char(-1)
			elif menu.enabled:
				# Global keys
				if key == glfw.KEY_Q and modifiers == glfw.MOD_CONTROL:
					log.info('Quitting.')
					menu.forget()
					video.stop()
					window.terminate()
					exit()
				if key == glfw.KEY_F:
					window.set_fullscreen()
				if key == glfw.KEY_T and modifiers == glfw.MOD_CONTROL | glfw.MOD_ALT:
					draw.TextureAtlas.dump()
				if key == glfw.KEY_D:
					log.info('Cycling dark mode')
					menu.show_dark_mode(not menu.dark_mode)

				# Menu keys
				if key == glfw.KEY_INSERT:
					menu.toggle_seen()
				if key == glfw.KEY_TAB or scancode == 164:  # Media play/pause
					if modifiers == 0:
						menu.find_next_new()
					if modifiers == glfw.MOD_SHIFT:
						menu.find_next_new(backwards=True)
				if key in [glfw.KEY_ENTER, glfw.KEY_SPACE]:
					menu.enter(video)
				if key in [glfw.KEY_BACKSPACE, glfw.KEY_ESCAPE] or scancode == 158:  # XF86Back
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
				if key == glfw.KEY_SLASH:
					menu.search_start()
			else:
				# Global keys
				if key == glfw.KEY_Q and modifiers == glfw.MOD_CONTROL:
					log.info('Quitting.')
					menu.forget()
					video.stop()
					window.terminate()
					exit()
				if key == glfw.KEY_F:
					window.set_fullscreen()
				if key == glfw.KEY_T and modifiers == glfw.MOD_CONTROL | glfw.MOD_ALT:
					draw.TextureAtlas.dump()
				if key == glfw.KEY_D:
					log.info('Cycling dark mode')
					menu.show_dark_mode(not menu.dark_mode)

				# Video keys
				if key in [glfw.KEY_ESCAPE, glfw.KEY_ENTER] or scancode == 158:  # XF86Back
					video.stop()
					menu.open()
				if key == glfw.KEY_O:
					log.info('Cycling OSD')
					if not video.paused:
						menu.show_osd(not menu.osd)
				if key == glfw.KEY_SPACE or scancode == 164:  # Media play/pause
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
				if key == glfw.KEY_PERIOD:
					video.seek(1, 'frame')
					# FIXME: kinda ugly that I need to do this?
					menu.show_osd(force=video.paused)
				if key == glfw.KEY_COMMA:
					video.seek(-1, 'frame')
					# FIXME: kinda ugly that I need to do this?
					menu.show_osd(force=video.paused)

				if key in [glfw.KEY_J, glfw.KEY_K] or scancode in [163, 165]:  # Media prev/next
					log.warning('Cycling Subtitles (FIXME: move code)')
					if key == glfw.KEY_J or scancode == 163:
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
	draw.State.render(window)

	frame_count += 1
	new = time.time()
	if int(new) > last_time:
		last_time = int(new)
		log.info(f'Rendering at {frame_count} fps')
		frame_count = 0

log.info('End of program.')
window.terminate()
