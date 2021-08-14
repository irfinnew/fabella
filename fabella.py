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



class Video:
	mpv = None
	context = None
	current_file = None
	fbo = None
	texture = None
	video_size = (640, 360)
	video_size_old = (None, None)
	position = 0
	rendered = False

	def __init__(self):
		def my_log(loglevel, component, message):
			#print('\x1b[32m[{}] {}: {}\x1b[0m'.format(loglevel, component, message))
			pass

		self.mpv = mpv.MPV(log_handler=my_log, loglevel='debug')
		#self.mpv['hwdec'] = 'auto'
		self.mpv['osd-duration'] = 1000
		self.mpv['osd-level'] = 1
		self.mpv['video-timing-offset'] = 0
		self.context = mpv.MpvRenderContext(
			self.mpv,
			'opengl',
			wl_display=ctypes.c_void_p(glfw.get_wayland_display()),
			opengl_init_params={'get_proc_address': mpv.OpenGlCbGetProcAddrFn(lambda _, name: glfw.get_proc_address(name.decode('utf8')))},
		)
		self.mpv.observe_property('width', self.size_changed)
		self.mpv.observe_property('height', self.size_changed)
		self.mpv.observe_property('percent-pos', self.position_changed)

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

	def size_changed(self, prop, value):
		print('SIZE CHANGED', prop, value)
		if value is None:
			return

		if prop == 'width':
			self.video_size = (value, self.video_size[1])
		elif prop == 'height':
			self.video_size = (self.video_size[0], value)
		else:
			raise 5

	def position_changed(self, prop, value):
		assert prop == 'percent-pos'
		if value is None:
			# FIXME: close file? Return to menu?
			value = 100
		self.position = value / 100

	def start(self, filename):
		self.current_file = filename
		self.rendered = False
		percent_pos = 0
		self.mpv.play(filename)

	def stop(self):
		self.current_file = None
		self.rendered = False
		percent_pos = 0
		self.mpv.stop()

	def seek(self, amount):
		try:
			self.mpv.seek(amount)
		except SystemError:
			pass

	def render(self, force_render=False):
		width, height = self.video_size
		if self.video_size != self.video_size_old:
			print(f'Resizing video texture from {self.video_size_old} to {self.video_size}')
			gl.glBindTexture(gl.GL_TEXTURE_2D, self.texture)
			gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGB, width, height, 0, gl.GL_RGB, gl.GL_UNSIGNED_BYTE, None)
			gl.glBindTexture(gl.GL_TEXTURE_2D, 0)
			self.video_size_old = self.video_size
			force_render = True
			self.rendered = False

		if self.context.update():
			ret = self.context.render(flip_y=True, opengl_fbo={'w': width, 'h': height, 'fbo': self.fbo})
			self.rendered = True

	def draw(self, window_width, window_height):
		if not self.rendered:
			return

		video_width, video_height = self.video_size

		# Fit video to screen, preserving aspect
		x1 = max((window_width - video_width / video_height * height) / 2, 0)
		y1 = max((window_height - video_height / video_width * width) / 2, 0)
		x2 = window_width - x1
		y2 = window_height - y1

		gl.glColor4f(1, 1, 1, 1)
		gl.glBindTexture(gl.GL_TEXTURE_2D, video.texture)
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

		# Draw position bar + shadow
		position_bar_height = 3
		position_shadow_height = 4
		position_shadow_top_color = (0, 0, 0, 0.25)
		position_shadow_bottom_color = (0, 0, 0, 1)
		#position_bar_color = (0.4, 0.4, 1, 1)
		position_bar_color = (0.8, 0.1, 0.1, 1)

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
	window = None
	fullscreen = False
	events = []

	def __init__(self, width, height, title):
		if not glfw.init():
			raise 'glfw.init()'
		self.window = glfw.create_window(width, height, title, None, None)
		if not self.window:
			glfw.terminate()
			raise 'glfw.create_window()'
		glfw.make_context_current(self.window)
		glfw.set_key_callback(self.window, self.on_keypress)
		#glfw.set_window_user_pointer(window, 5)
		#print(glfw.get_window_user_pointer(window))

	def terminate(self):
		#glfw.destroy_window(self.window)
		glfw.terminate()

	def set_fullscreen(self, fullscreen=None):
		print(f'set_fullscreen({fullscreen})')
		if fullscreen is None:
			self.fullscreen = not self.fullscreen
		else:
			self.fullscreen = bool(fullscreen)
			
		if self.fullscreen:
			glfw.set_window_monitor(self.window, glfw.get_primary_monitor(), 0, 0, 640, 360, glfw.DONT_CARE)
		monitor = glfw.get_primary_monitor() if self.fullscreen else None
		glfw.set_window_monitor(self.window, monitor, 0, 0, *self.size(), glfw.DONT_CARE)

	def on_keypress(self, window, key, scancode, action, modifiers):
		self.events.append((key, scancode, action, modifiers))

	def closed(self):
		return glfw.window_should_close(self.window)

	def size(self):
		return glfw.get_window_size(self.window)

	def wait(self):
		glfw.wait_events()

	def swap_buffers(self):
		glfw.swap_buffers(self.window)

	def get_events(self):
		while True:
			try:
				yield self.events.pop(0)
			except IndexError:
				return


class Tile:
	name = ''
	texture = None
	font = None
	width = 0
	height = 0
	path = ''
	isdir = False

	def __init__(self, name, path, font):
		self.name = name
		self.path = os.path.join(path, name)
		self.isdir = os.path.isdir(self.path)
		self.font = font

	def render(self):
		if self.texture is not None:
			raise 5

		stroke_width = 2
		name = self.name
		if self.isdir:
			name = name + '/'

		# Get text size
		image = PIL.Image.new('RGBA', (8, 8), (0, 164, 201))
		w, h = PIL.ImageDraw.Draw(image).textsize(name, self.font, stroke_width=stroke_width)

		# Draw text
		image = PIL.Image.new('RGBA', (w, h), (0, 164, 201, 0))
		PIL.ImageDraw.Draw(image).text((0, 0), name, font=self.font, align='center', fill=(255, 255, 255), stroke_width=stroke_width, stroke_fill=(0, 0, 0))

		self.width = w
		self.height = h
		self.texture = gl.glGenTextures(1)
		gl.glBindTexture(gl.GL_TEXTURE_2D, self.texture)
		gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
		gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR)
		gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGBA, w, h, 0, gl.GL_RGBA, gl.GL_UNSIGNED_BYTE, image.tobytes())
		gl.glBindTexture(gl.GL_TEXTURE_2D, 0)

	def draw(self, x, y, selected=False):
		if self.texture is None:
			return

		x1, y1, x2, y2 = x, y, x + self.width, y + self.height
		gl.glBindTexture(gl.GL_TEXTURE_2D, self.texture)
		if selected:
			gl.glColor4f(1, 0, 0, 1)
		else:
			gl.glColor4f(1, 1, 1, 1)
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
		if self.texture is not None:
			gl.glDeleteTextures([self.texture])


class Menu:
	enabled = False
	path = None
	tiles = []
	current_idx = 0
	font = None

	def __init__(self, path='/', enabled=False):
		self.font = PIL.ImageFont.truetype('DejaVuSans', 35)
		self.load(path)
		self.enabled = enabled

	def load(self, path):
		self.forget()

		self.path = path
		self.tiles = [Tile(f, path, self.font) for f in sorted(os.listdir(self.path))]
		self.current_idx = 0

	def forget(self):
		for tile in self.tiles:
			tile.destroy()
		self.tiles = []
		self.current_idx = None

	@property
	def current(self):
		return self.tiles[self.current_idx]

	def up(self):
		if self.current_idx > 0:
			self.current_idx -= 1

	def down(self):
		if self.current_idx < len(self.tiles) - 1:
			self.current_idx += 1

	def enter(self, video):
		tile = self.current
		if tile.isdir:
			self.load(tile.path)
		else:
			video.start(tile.path)
			self.enabled = False

	def back(self):
		previous = os.path.basename(self.path)
		self.load(os.path.dirname(self.path))
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

			tile.draw(cx - tile.width // 2, ypos, i == 0)


window = Window(1280, 720, "libmpv wayland/egl/opengl example")
menu = Menu(sys.argv[1], enabled=True)
video = Video()

#### Main loop
last_time = 0
frame_count = 0
while not window.closed():
	window.wait()

	if not menu.enabled:
		for key, scancode, action, modifiers  in window.get_events():
			if action == glfw.PRESS:
				if key in [glfw.KEY_ESCAPE, glfw.KEY_Q]:
					window.terminate()
					exit()
				if key == glfw.KEY_BACKSPACE:
					menu.enabled = True
				if key == glfw.KEY_F:
					window.set_fullscreen()
				if key == glfw.KEY_O:
					video.mpv['osd-level'] ^= 2
				if key == glfw.KEY_SPACE:
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
				if key in [glfw.KEY_ESCAPE, glfw.KEY_Q]:
					window.terminate()
					exit()
				if key == glfw.KEY_F:
					window.set_fullscreen()
				if key == glfw.KEY_BACKSPACE:
					menu.enabled = False
				if key in [glfw.KEY_ENTER, glfw.KEY_RIGHT]:
					menu.enter(video)
				if key == glfw.KEY_LEFT:
					menu.back()
				if key == glfw.KEY_UP:
					menu.up()
				if key == glfw.KEY_DOWN:
					menu.down()

	width, height = window.size()

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
		print(f'{frame_count} fps')
		frame_count = 0

window.terminate()
