#! /usr/bin/env python3

# Requires pyGLFW, PyOpenGL, python-mpv, pillow >= 6.2.0
# https://github.com/mpv-player/mpv/blob/master/libmpv/render_gl.h#L91

import os
import sys
import glfw
import time
import math
import ctypes
import mpv
import PIL.Image, PIL.ImageDraw, PIL.ImageFont
import OpenGL.GL as gl
import datetime
import inspect


class Logger:
	Red = '\x1b[31m'
	Green = '\x1b[32m'
	Yellow = '\x1b[33m'
	Blue = '\x1b[34m'
	Magenta = '\x1b[35m'
	Cyan = '\x1b[36m'
	Gray = '\x1b[37m'
	Bright = '\x1b[1m'
	Reset = '\x1b[0m'

	LevelColors = {
		'critical': Bright + Magenta,
		'error':    Bright + Red,
		'warning':  Bright + Yellow,
		'info':     Bright + Green,
		'debug':    Bright + Cyan,
	}

	def __init__(self, *, module, color):
		self.module = module
		self.color = color

	def log(self, level, msg, *, module=None, color=None):
		if level == 'debug':
			return

		level_color = self.LevelColors[level]
		module = module or self.module
		color = color or self.color

		timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
		level = ' ' * (8 - len(level)) + '<' + level_color + level + self.Reset + '>'
		module = ' ' * (8 - len(module)) + '[' + color + module + self.Reset + ']'
		print(f'{timestamp} {level} {module} {msg}')

	def critical(self, msg, **kwargs):
		self.log('critical', msg, **kwargs)

	def error(self, msg, **kwargs):
		self.log('error', msg, **kwargs)

	def warning(self, msg, **kwargs):
		self.log('warning', msg, **kwargs)

	def info(self, msg, **kwargs):
		self.log('info', msg, **kwargs)

	def debug(self, msg, **kwargs):
		self.log('debug', msg, **kwargs)


class Video:
	log = Logger(module='Video', color=Logger.Yellow)
	mpv = None
	context = None
	current_file = None
	fbo = None
	texture = None
	video_size = (640, 360)
	video_size_old = (None, None)
	position = 0
	position_immune_until = 0
	rendered = False
	tile = None

	def __init__(self):
		self.log.debug('Created instance')
		def mpv_log(loglevel, component, message):
			loglevel = {'fatal': 'critical', 'warn': 'warning', 'v': 'info', 'trace': 'debug'}.get(loglevel, loglevel)
			self.log.log(loglevel, component + ': ' + message, module='libmpv', color=Logger.Green)

		self.mpv = mpv.MPV(log_handler=mpv_log, loglevel='debug')
		self.log.warning('FIXME: setting MPV options')
		#self.mpv['hwdec'] = 'auto'
		self.mpv['osd-duration'] = 1000
		self.mpv['osd-level'] = 1
		self.mpv['video-timing-offset'] = 0
		self.mpv['af'] = 'lavfi=[dynaudnorm=p=1]'

		self.context = mpv.MpvRenderContext(
			self.mpv,
			'opengl',
			wl_display=ctypes.c_void_p(glfw.get_wayland_display()),
			opengl_init_params={'get_proc_address': mpv.OpenGlCbGetProcAddrFn(lambda _, name: glfw.get_proc_address(name.decode('utf8')))},
		)
		self.mpv.observe_property('width', self.size_changed)
		self.mpv.observe_property('height', self.size_changed)
		self.mpv.observe_property('percent-pos', self.position_changed)
		self.mpv.register_event_callback(self.mpv_event)

		# FIXME
		self.fbo = gl.glGenFramebuffers(1)
		gl.glBindFramebuffer(gl.GL_FRAMEBUFFER, self.fbo)

		self.texture = gl.glGenTextures(1)
		gl.glBindTexture(gl.GL_TEXTURE_2D, self.texture)
		gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
		gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR)
		gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGB, *self.video_size, 0, gl.GL_RGB, gl.GL_UNSIGNED_BYTE, None)
		gl.glFramebufferTexture2D(gl.GL_FRAMEBUFFER, gl.GL_COLOR_ATTACHMENT0, gl.GL_TEXTURE_2D, self.texture, 0)
		assert gl.glCheckFramebufferStatus(gl.GL_FRAMEBUFFER) == gl.GL_FRAMEBUFFER_COMPLETE

		gl.glBindFramebuffer(gl.GL_FRAMEBUFFER, 0)
		gl.glBindTexture(gl.GL_TEXTURE_2D, 0)

	def mpv_event(self, event):
		if event['event'] == {'prefix': 'cplayer', 'level': 'v', 'text': 'video EOF reached'}:
			self.eof_reached()

	def eof_reached(self):
		self.log.info('Reached video EOF')
		self.position = 1.0
		self.stop()
		if self.menu:
			self.menu.open()

	def size_changed(self, prop, value):
		self.log.info(f'Video {prop} changed to {value}')
		assert prop in ['width', 'height']

		if value is None:
			return
		if prop == 'width':
			self.video_size = (value, self.video_size[1])
		elif prop == 'height':
			self.video_size = (self.video_size[0], value)

	def position_changed(self, prop, value):
		self.log.debug(f'Video percent-pos changed to {value}')
		assert prop == 'percent-pos'

		if self.position_immune_until > time.time():
			self.log.debug(f'Video percent-pos is immune, ignoring')
			return
		if value is None:
			return
		self.position = value / 100

		if self.tile:
			self.tile.update_pos(self.position)

	def start(self, filename, menu=None, tile=None):
		if self.current_file:
			self.stop()
		self.log.info(f'Starting playback for {filename}')

		self.current_file = filename
		self.rendered = False
		self.position = 0
		self.tile = tile
		self.menu = menu

		self.position_immune_until = time.time() + 1
		self.mpv.play(filename)
		if self.tile and self.tile.last_pos > 0.001 and self.tile.last_pos < 0.999:
			last_pos = self.tile.last_pos
			self.log.info(f'Starting playback at position {last_pos}')
			while not self.context.update():
				time.sleep(0.01)
			self.mpv.percent_pos = last_pos * 100

	def stop(self):
		self.log.info(f'Stopping playback for {self.current_file}')
		self.mpv.stop()

		if self.tile:
			self.tile.update_pos(self.position, force=True)

		self.current_file = None
		self.rendered = False
		self.tile = None

	def seek(self, amount, whence='relative'):
		self.log.info(f'Seeking {whence} {amount}')
		try:
			self.mpv.seek(amount, whence)
		except SystemError as e:
			# FIXME
			self.log.warning('SEEK ERROR')
			print(e)

	def render(self):
		width, height = self.video_size
		if self.video_size != self.video_size_old:
			self.log.info(f'Resizing video texture from {self.video_size_old} to {self.video_size}')
			gl.glBindTexture(gl.GL_TEXTURE_2D, self.texture)
			gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGB, width, height, 0, gl.GL_RGB, gl.GL_UNSIGNED_BYTE, None)
			gl.glBindTexture(gl.GL_TEXTURE_2D, 0)
			self.video_size_old = self.video_size
			self.rendered = False

		if self.context.update():
			self.log.debug('Rendering frame')
			ret = self.context.render(flip_y=True, opengl_fbo={'w': width, 'h': height, 'fbo': self.fbo})
			self.rendered = True

	def draw(self, window_width, window_height):
		if not self.rendered:
			#self.log.debug('Drawing frame skipped because not rendered')
			return

		#self.log.debug('Drawing frame')
		video_width, video_height = self.video_size

		# Fit video to screen, preserving aspect
		x1 = max((window_width - video_width / video_height * height) / 2, 0)
		y1 = max((window_height - video_height / video_width * width) / 2, 0)

		x2 = window_width - x1
		y2 = window_height - y1

		x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)

		gl.glColor4f(1, 1, 1, 1)
		gl.glBindTexture(gl.GL_TEXTURE_2D, video.texture)
		gl.glBegin(gl.GL_QUADS)
		gl.glTexCoord2f(0.0, 0.0)
		gl.glVertex2i(x1, y1)
		gl.glTexCoord2f(1.0, 0.0)
		gl.glVertex2i(x2, y1)
		gl.glTexCoord2f(1.0, 1.0)
		gl.glVertex2i(x2, y2)
		gl.glTexCoord2f(0.0, 1.0)
		gl.glVertex2i(x1, y2)
		gl.glEnd()
		gl.glBindTexture(gl.GL_TEXTURE_2D, 0)

		# Draw position bar + shadow
		position_bar_height = 3
		position_shadow_height = 4
		position_shadow_top_color = (0, 0, 0, 0.25)
		position_shadow_bottom_color = (0, 0, 0, 1)
		position_bar_color = (0.4, 0.4, 1, 1)  # Blueish
		#position_bar_color = (0.8, 0.1, 0.1, 1)  # Red

		gl.glBegin(gl.GL_QUADS)
		gl.glColor4f(*position_shadow_bottom_color)
		gl.glVertex2f(0, position_bar_height)
		gl.glVertex2f(window_width, position_bar_height)
		gl.glColor4f(*position_shadow_top_color)
		gl.glVertex2f(window_width, position_bar_height + position_shadow_height)
		gl.glVertex2f(0, position_bar_height + position_shadow_height)
		gl.glEnd()

		x1, y1, x2, y2 = self.position * window_width, 0, window_width, position_bar_height
		gl.glColor4f(*position_shadow_bottom_color)
		gl.glBegin(gl.GL_QUADS); gl.glVertex2f(x1, y1); gl.glVertex2f(x2, y1); gl.glVertex2f(x2, y2); gl.glVertex2f(x1, y2); gl.glEnd()

		x1, y1, x2, y2 = 0, 0, self.position * window_width, position_bar_height
		gl.glColor4f(*position_bar_color)
		gl.glBegin(gl.GL_QUADS); gl.glVertex2f(x1, y1); gl.glVertex2f(x2, y1); gl.glVertex2f(x2, y2); gl.glVertex2f(x1, y2); gl.glEnd()




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


class Tile:
	log = Logger(module='Tile', color=Logger.Magenta)
	name = ''
	texture = None
	font = None
	width = 0
	height = 0
	path = ''
	isdir = False
	state_file = None
	state_last_update = 0
	last_pos = 0
	rendered_last_pos = 0

	def __init__(self, name, path, font):
		self.log.info(f'Created Tile path={path}, name={name}')
		self.name = name
		self.path = os.path.join(path, name)
		self.isdir = os.path.isdir(self.path)
		self.font = font

		if not self.isdir:
			self.state_file = os.path.join(path, '.fabella', 'state', name)
			self.read_state()

	def update_pos(self, position, force=False):
		self.log.debug(f'Tile {self.name} update_pos({position}, {force})')
		if self.last_pos == position:
			return

		now = time.time()
		if now - self.state_last_update > 5 or abs(self.last_pos - position) > 0.01 or force:
			self.state_last_update = now
			self.last_pos = position
			self.write_state()

	def read_state(self):
		self.log.info(f'Reading state for {self.name}')
		try:
			with open(self.state_file) as fd:
				self.last_pos = float(fd.read())
		except FileNotFoundError:
			pass

	def write_state(self):
		self.log.info(f'Writing state for {self.name}')
		os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
		with open(self.state_file, 'w') as fd:
			fd.write(str(self.last_pos) + '\n')

	def render(self):
		self.log.info(f'Rendering for {self.name}')
		stroke_width = 2
		name = self.name
		if self.isdir:
			name = name + '/'

		if self.last_pos > 0.01:
			name = name + f' [{round(self.last_pos * 100)}%]'
		self.rendered_last_pos = self.last_pos

		# Get text size
		image = PIL.Image.new('RGBA', (8, 8), (0, 164, 201))
		w, h = PIL.ImageDraw.Draw(image).textsize(name, self.font, stroke_width=stroke_width)

		# Draw text
		image = PIL.Image.new('RGBA', (w, h), (0, 164, 201, 0))
		PIL.ImageDraw.Draw(image).text((0, 0), name, font=self.font, align='center', fill=(255, 255, 255), stroke_width=stroke_width, stroke_fill=(0, 0, 0))

		self.width = w
		self.height = h
		if self.texture is None:
			self.texture = gl.glGenTextures(1)
		gl.glBindTexture(gl.GL_TEXTURE_2D, self.texture)
		gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
		gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR)
		gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGBA, w, h, 0, gl.GL_RGBA, gl.GL_UNSIGNED_BYTE, image.tobytes())
		gl.glBindTexture(gl.GL_TEXTURE_2D, 0)

	def draw(self, x, y, selected=False):
		if self.texture is None:
			return

		if abs(self.last_pos - self.rendered_last_pos) > 0.01:
			self.render()

		new = 0.5 if self.last_pos == 1 else 1.0
		x1, y1, x2, y2 = x, y, x + self.width, y + self.height
		gl.glBindTexture(gl.GL_TEXTURE_2D, self.texture)
		if selected:
			gl.glColor4f(new, 0, 0, 1)
		else:
			gl.glColor4f(new, new, new, 1)
		gl.glBegin(gl.GL_QUADS)
		gl.glTexCoord2f(0.0, 1.0)
		gl.glVertex2f(x1, y1)
		gl.glTexCoord2f(1.0, 1.0)
		gl.glVertex2f(x2, y1)
		gl.glTexCoord2f(1.0, 0.0)
		gl.glVertex2f(x2, y2)
		gl.glTexCoord2f(0.0, 0.0)
		gl.glVertex2f(x1, y2)
		gl.glEnd()
		gl.glBindTexture(gl.GL_TEXTURE_2D, 0)

	def destroy(self):
		self.log.info(f'Destroying {self.name}')
		if self.texture is not None:
			gl.glDeleteTextures([self.texture])

	def __str__(self):
		return f'Tile(name={self.name}, isdir={self.isdir}, last_pos={self.last_pos}, texture={self.texture})'


class Menu:
	log = Logger(module='Menu', color=Logger.Cyan)
	enabled = False
	path = None
	tiles = []
	current_idx = 0
	font = None

	def __init__(self, path='/', enabled=False):
		self.log.info(f'Created instance, path={path}, enabled={enabled}')
		self.font = PIL.ImageFont.truetype('DejaVuSans', 35)
		self.load(path)
		self.enabled = enabled

	def open(self):
		self.log.info('Opening Menu')
		self.enabled = True

	def close(self):
		self.log.info('Closing Menu')
		self.enabled = False

	def load(self, path):
		self.forget()
		self.log.info(f'Loading {path}')

		self.path = path
		self.tiles = []
		for f in sorted(os.listdir(self.path)):
			if not f.startswith('.'):
				self.tiles.append(Tile(f, path, self.font))
		self.current_idx = 0
		for i, tile in enumerate(self.tiles):
			if tile.last_pos < 0.999:
				self.current_idx = i
				break

	def forget(self):
		self.log.info('Forgetting tiles')
		for tile in self.tiles:
			tile.destroy()
		self.tiles = []
		self.current_idx = None

	@property
	def current(self):
		return self.tiles[self.current_idx]

	def up(self):
		self.log.info('Select above')
		if self.current_idx > 0:
			self.current_idx -= 1
		else:
			self.current_idx = len(self.tiles) - 1

	def down(self):
		self.log.info('Select below')
		if self.current_idx < len(self.tiles) - 1:
			self.current_idx += 1
		else:
			self.current_idx = 0

	def enter(self, video):
		self.log.info('Enter')
		tile = self.current
		if tile.isdir:
			self.load(tile.path)
		else:
			self.play(tile, video)

	def play(self, tile, video):
		self.log.info(f'Play; (currently {video.tile})')
		if tile is not video.tile:
			# Not already playing this
			self.log.info(f'Starting new video: {tile}')
			video.start(tile.path, menu=self, tile=tile)
		else:
			self.log.info('Already playing this video, NOP')
		self.close()

	def back(self):
		self.log.info('Back')
		new = os.path.dirname(self.path)
		if not new:
			return
		previous = os.path.basename(self.path)
		self.load(new)
		for i, tile in enumerate(self.tiles):
			if tile.name == previous:
				self.current_idx = i
				break

	def draw(self, width, height):
		x1, y1, x2, y2 = 0, 0, width, height
		gl.glColor4f(0, 0, 0, 0.66)
		gl.glBegin(gl.GL_QUADS); gl.glVertex2f(x1, y1); gl.glVertex2f(x2, y1); gl.glVertex2f(x2, y2); gl.glVertex2f(x1, y2); gl.glEnd()

		line_height = 50
		num_lines = height // line_height + 2
		if num_lines % 2 == 0:
			num_lines -= 1
		cx = width // 2
		cy = height // 2

		# Render at most one tile per frame
		for tile in self.tiles:
			if tile.texture is None:
				tile.render()
				break

		for i in range(-(num_lines // 2), num_lines // 2 + 1):
			idx = self.current_idx + i
			if idx < 0 or idx >= len(self.tiles):
				continue

			tile = self.tiles[idx]
			ypos = cy - i * line_height - tile.height // 2

			tile.draw(cx - tile.width // 2, ypos, selected=i == 0)


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
				if key in [glfw.KEY_ESCAPE, glfw.KEY_Q]:
					log.info('Quitting.')
					video.stop()
					window.terminate()
					exit()
				if key == glfw.KEY_BACKSPACE:
					menu.open()
				if key == glfw.KEY_ENTER:
					video.seek(-0.1, 'absolute')
					menu.open()
				if key == glfw.KEY_F:
					window.set_fullscreen()
				if key == glfw.KEY_O:
					log.info('Cycling OSD')
					video.mpv['osd-level'] ^= 2
				if key == glfw.KEY_SPACE:
					log.info('Cycling pause')
					video.mpv.cycle('pause')
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
				if key in [glfw.KEY_ESCAPE, glfw.KEY_Q]:
					log.info('Quitting.')
					video.stop()
					window.terminate()
					exit()
				if key == glfw.KEY_F:
					window.set_fullscreen()
				if key == glfw.KEY_BACKSPACE:
					menu.close()
				if key in [glfw.KEY_ENTER, glfw.KEY_RIGHT]:
					menu.enter(video)
				if key == glfw.KEY_LEFT:
					menu.back()
				if key == glfw.KEY_UP:
					menu.up()
				if key == glfw.KEY_DOWN:
					menu.down()

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
