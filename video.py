# https://github.com/mpv-player/mpv/blob/master/libmpv/render_gl.h#L91

import glfw  # FIXME: abstract out
import ctypes
import time
import mpv
import OpenGL.GL as gl

from logger import Logger

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
		self.mpv['hwdec'] = 'auto'
		self.mpv['osd-duration'] = 1000
		self.mpv['osd-level'] = 1
		self.mpv['video-timing-offset'] = 0
		self.mpv['af'] = 'lavfi=[dynaudnorm=p=1]'
		self.mpv['replaygain'] = 'track'
		self.mpv['replaygain-clip'] = 'yes'
		self.mpv['osd-font'] = 'Ubuntu Medium'
		self.mpv['osd-font-size'] = 45
		self.mpv['sub-font'] = 'Ubuntu Medium'
		self.mpv['sub-font-size'] = 45

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
		self.position = 0.0
		self.stop()
		# FIXME: tight coupling
		if self.menu:
			time.sleep(0.5)
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

	def pause(self, pause=None):
		if pause is None:
			pause = not self.mpv.pause

		if pause != self.mpv.pause:
			self.log.info('Pausing video' if pause else 'Unpausing video')
			self.mpv.pause = pause

	def start(self, filename, position=0, menu=None, tile=None):
		if self.current_file:
			self.stop()
		self.log.info(f'Starting playback for {filename}')

		self.current_file = filename
		self.rendered = False
		self.position = position
		self.tile = tile
		self.menu = menu

		self.position_immune_until = time.time() + 1
		self.mpv.play(filename)
		self.pause(False)
		if position > 0:
			self.log.info(f'Starting playback at position {position}')
			# Updating the position only works after libmpv has had
			# a chance to initialize the video; so we spin here until
			# libmpv is ready.
			while not self.context.update():
				time.sleep(0.01)
			self.mpv.percent_pos = position * 100

	def stop(self):
		self.log.info(f'Stopping playback for {self.current_file}')
		# Not sure why this'd be necessary
		#self.pause(False)
		self.mpv.stop()

		if self.tile:
			self.tile.update_pos(self.position, force=True)

		self.current_file = None
		# Hmm, maybe not do this? Is the memory valid after stop though?
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
		x1 = max((window_width - video_width / video_height * window_height) / 2, 0)
		y1 = max((window_height - video_height / video_width * window_width) / 2, 0)

		x2 = window_width - x1
		y2 = window_height - y1

		x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)

		gl.glColor4f(1, 1, 1, 1)
		gl.glBindTexture(gl.GL_TEXTURE_2D, self.texture)
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
