# Fabella - Simple, elegant video library and player.
#
# Copyright 2020-2022 Marcel Moreaux.
# Licensed under GPL v2.0, or (at your option) any later version.
# (SPDX GPL-2.0-or-later) See LICENSE file for details.

import glfw
import time

import loghelper

log = loghelper.get_logger('Window', loghelper.Color.Blue)



def get_wayland_display():
	return glfw.get_wayland_display()

def get_proc_address(name):
	return glfw.get_proc_address(name)

def wakeup():
	glfw.post_empty_event()



class Display:
	def __init__(self, monitor):
		self.monitor = monitor
		self.primary = False
		self.selected = False

	@property
	def name(self):
		return glfw.get_monitor_name(self.monitor).decode()[:24]

	@property
	def size(self):
		return glfw.get_video_mode(self.monitor).size

	@property
	def pos(self):
		return glfw.get_monitor_pos(self.monitor)

	def __str__(self):
		desc = f'{self.name} {self.size.width}x{self.size.height} +{self.pos[0]}+{self.pos[1]}'
		if self.primary:
			desc += ' primary'
		if self.selected:
			desc += ' selected'
		return desc

	def __repr__(self):
		return str(self)

	@classmethod
	def all(cls):
		displays = [cls(m) for m in glfw.get_monitors()]
		displays[0].primary = True
		return sorted(displays, key=lambda m: m.pos)



class Window:
	def __init__(self, display_num, title):
		log.info(f'pyglfw version {glfw.__version__}, using GLFW version {glfw.VERSION_MAJOR}.{glfw.VERSION_MINOR}.{glfw.VERSION_REVISION}')
		if not glfw.init():
			log.critical('glfw.init() failed')
			raise 'glfw.init()'

		glfw.window_hint(glfw.DECORATED, False)
		glfw.window_hint(glfw.AUTO_ICONIFY, False)
		glfw.window_hint(glfw.FOCUSED, True)
		glfw.window_hint(glfw.RESIZABLE, False)

		glfw.window_hint(glfw.OPENGL_FORWARD_COMPAT, True)
		glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
		glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
		glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)

		displays = Display.all()
		try:
			display = displays[display_num]
		except IndexError:
			display = displays[0]
		display.selected = True

		log.info(f'Displays:')
		for d in displays:
			log.info(f'  - {d}')

		self.width, self.height = display.size
		self.monitor = display.monitor
		self.window = glfw.create_window(self.width, self.height, title, self.monitor, None)
		if not self.window:
			log.critical('glfw.create_window() failed')
			glfw.terminate()
			raise 'glfw.create_window()'
		log.info(f'Created instance of {self.width}x{self.height}: "{title}"')

		glfw.make_context_current(self.window)
		glfw.swap_interval(1)
		glfw.set_key_callback(self.window, self.on_keypress)

		log.debug('Hiding mouse cursor')
		glfw.set_input_mode(self.window, glfw.CURSOR, glfw.CURSOR_HIDDEN)

		self.fullscreen = True
		self.events = []
		self.had_event = True

	def terminate(self):
		log.info('Terminating')
		glfw.destroy_window(self.window)
		glfw.terminate()

	def set_fullscreen(self, fullscreen=None):
		if fullscreen is None:
			self.fullscreen = not self.fullscreen
		else:
			self.fullscreen = bool(fullscreen)

		if self.fullscreen:
			log.info('Entering fullscreen')
			glfw.set_window_monitor(self.window, self.monitor, 0, 0, self.width, self.height, glfw.DONT_CARE)
		else:
			log.info('Leaving fullscreen')
			glfw.set_window_monitor(self.window, None, 0, 0, self.width, self.height, glfw.DONT_CARE)

	def on_keypress(self, window, key, scancode, action, modifiers):
		log.info(f'Keypress key={key}, scancode={scancode}, action={action}, modifiers={modifiers}')
		self.events.append((key, scancode, action, modifiers))

	def closed(self):
		return glfw.window_should_close(self.window)

	def wait(self):
		#log.debug('glfw.wait_events()')
		# FIXME: doesn't seem to wait if swap_buffers is called every iteration
		# https://github.com/glfw/glfw/issues/1911
		# Wait until next second transition
		if self.had_event:
			glfw.poll_events()
		else:
			glfw.wait_events_timeout(1 - (time.time() % 1))

	def swap_buffers(self):
		#log.debug('glfw.swap_buffers()')
		glfw.swap_buffers(self.window)

	def get_events(self):
		try:
			yield self.events.pop(0)
			self.had_event = True
		except IndexError:
			self.had_event = False
			return
