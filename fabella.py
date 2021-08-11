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
		position_shadow_height = 6
		position_shadow_top_color = (0, 0, 0, 0)
		position_shadow_bottom_color = (0, 0, 0, 1)
		position_bar_color = (0.4, 0.4, 1, 1)

		x1, y1, x2, y2 = 0, 0, window_width, 5
		gl.glBegin(gl.GL_QUADS)
		gl.glColor4f(*position_shadow_bottom_color)
		gl.glVertex2f(0, 0)
		gl.glVertex2f(window_width, 0)
		gl.glColor4f(*position_shadow_top_color)
		gl.glVertex2f(window_width, position_shadow_height)
		gl.glVertex2f(0, position_shadow_height)
		gl.glEnd()

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


window = Window(1280, 720, "libmpv wayland/egl/opengl example")
video = Video()


#### Menu stuffs ####
menu = False
current_path = sys.argv[1]
files = sorted(os.listdir(current_path))
current_file = 0

menu_font = PIL.ImageFont.truetype('DejaVuSans', 35) # 64
menu_image = PIL.Image.new('RGBA', (1920, 1080), (0, 164, 201, 0))
menu_drawer = PIL.ImageDraw.Draw(menu_image)
menu_texture = gl.glGenTextures(1)
gl.glBindTexture(gl.GL_TEXTURE_2D, menu_texture)
gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR)
# FIXME: fixed size
gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGBA, 1920, 1080, 0, gl.GL_RGBA, gl.GL_UNSIGNED_BYTE, menu_image.tobytes())
gl.glBindTexture(gl.GL_TEXTURE_2D, 0)


#### Main loop
last_time = 0
frame_count = 0
while not window.closed():
	window.wait()

	if not menu:
		for key, scancode, action, modifiers  in window.get_events():
			if action == glfw.PRESS:
				if key in [glfw.KEY_ESCAPE, glfw.KEY_Q]:
					window.terminate()
					exit()
				if key == glfw.KEY_BACKSPACE:
					menu = True
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

	if menu:
		for key, scancode, action, modifiers  in window.get_events():
			if action == glfw.PRESS:
				if key in [glfw.KEY_ESCAPE, glfw.KEY_Q]:
					window.terminate()
					exit()
				if key == glfw.KEY_F:
					window.set_fullscreen()
				if key == glfw.KEY_BACKSPACE:
					menu = False
				if key == glfw.KEY_ENTER:
					selected = os.path.join(current_path, files[current_file])
					if not os.path.isdir(selected):
						video.start(selected)
						menu = False
				if key == glfw.KEY_RIGHT:
					selected = os.path.join(current_path, files[current_file])
					if os.path.isdir(selected):
						current_path = selected
						files = sorted(os.listdir(current_path))
						current_file = 0
				if key == glfw.KEY_LEFT:
					selected = os.path.dirname(current_path)
					if selected != current_path:
						current_path = selected
						files = sorted(os.listdir(current_path))
						current_file = 0
				if key == glfw.KEY_UP:
					current_file = max(0, current_file - 1)
				if key == glfw.KEY_DOWN:
					current_file = min(len(files) - 1, current_file + 1)

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

	if menu:
		x1, y1, x2, y2 = 0, 0, width, height
		gl.glColor4f(0, 0, 0, 0.66)
		gl.glBegin(gl.GL_QUADS); gl.glVertex2f(x1, y1); gl.glVertex2f(x2, y1); gl.glVertex2f(x2, y2); gl.glVertex2f(x1, y2); gl.glEnd()

		menu_image.paste((0, 164, 201, 0), (0, 0, 1920, 1080))
		textheight = 80
		for p, i in enumerate(range(current_file - 6, current_file + 7)):
			if i >= 0 and i < len(files):
				fill = (255, 0, 0) if i == current_file else (255, 255, 255)
				menu_drawer.text((200, p * textheight + 20), files[i], font=menu_font, fill=fill, stroke_width=4, stroke_fill=(0, 0, 0))

		x1, y1, x2, y2 = 0, 0, width, height
		gl.glBindTexture(gl.GL_TEXTURE_2D, menu_texture)
		gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGBA, 1920, 1080, 0, gl.GL_RGBA, gl.GL_UNSIGNED_BYTE, menu_image.tobytes())
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



	window.swap_buffers()

	frame_count += 1
	new = time.time()
	if int(new) > last_time:
		last_time = int(new)
		print(f'{frame_count} fps')
		frame_count = 0

window.terminate()
