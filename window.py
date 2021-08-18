import glfw

from logger import Logger

class Window:
	log = Logger(module='Window', color=Logger.Blue)
	window = None
	fullscreen = False
	events = []

	def __init__(self, width, height, title):
		self.log.info(f'Created instance of {width}x{height}: "{title}"')
		if not glfw.init():
			self.log.critical('glfw.init() failed')
			raise 'glfw.init()'
		self.window = glfw.create_window(width, height, title, None, None)
		if not self.window:
			self.log.critical('glfw.create_window() failed')
			glfw.terminate()
			raise 'glfw.create_window()'
		glfw.make_context_current(self.window)
		glfw.set_key_callback(self.window, self.on_keypress)
		#glfw.set_window_user_pointer(window, 5)
		#print(glfw.get_window_user_pointer(window))
		self.log.debug('Hiding mouse cursor')
		glfw.set_input_mode(self.window, glfw.CURSOR, glfw.CURSOR_HIDDEN)

	def terminate(self):
		self.log.info('Terminating')
		glfw.destroy_window(self.window)
		glfw.terminate()

	def set_fullscreen(self, fullscreen=None):
		if fullscreen is None:
			self.fullscreen = not self.fullscreen
		else:
			self.fullscreen = bool(fullscreen)
			
		if self.fullscreen:
			self.log.info('Entering fullscreen')
			glfw.set_window_monitor(self.window, glfw.get_primary_monitor(), 0, 0, *self.size(), glfw.DONT_CARE)
		else:
			self.log.info('Leaving fullscreen')
			glfw.set_window_monitor(self.window, None, 0, 0, *self.size(), glfw.DONT_CARE)

	def on_keypress(self, window, key, scancode, action, modifiers):
		self.log.info(f'Keypress key={key}, scancode={scancode}, action={action}, modifiers={modifiers}')
		self.events.append((key, scancode, action, modifiers))

	def closed(self):
		return glfw.window_should_close(self.window)

	def size(self):
		return glfw.get_window_size(self.window)

	def wait(self):
		self.log.debug('glfw.wait_events()')
		glfw.wait_events()

	def swap_buffers(self):
		self.log.debug('glfw.swap_buffers()')
		glfw.swap_buffers(self.window)

	def get_events(self):
		while True:
			try:
				yield self.events.pop(0)
			except IndexError:
				return
