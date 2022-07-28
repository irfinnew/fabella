# https://github.com/mpv-player/mpv/blob/master/libmpv/render_gl.h#L91

import glfw  # FIXME: abstract out
import ctypes
import time
import mpv
import OpenGL.GL as gl

import loghelper
import draw

log = loghelper.get_logger('Video', loghelper.Color.Yellow)



class Video:
	def __init__(self, width, height):
		log.debug('Created instance')
		self.current_file = None
		self.duration = 0
		self.position = 0
		self.position_immune_until = 0
		self.rendered = False
		self.tile = None
		self.width = width
		self.height = height

		mpv_logger = loghelper.get_logger('libmpv', loghelper.Color.Green)
		mpv_levels = {
			'fatal': 50,
			'error': 40,
			'warn': 30,
			'info': 20,
			'status': 20,
			'v': 15,
			'debug': 10,
			'trace': 5
		}
		self.mpv = mpv.MPV(log_handler=lambda l, c, m: mpv_logger.log(mpv_levels[l], f'{c}: {m}'), loglevel='debug')

		self.should_render = False
		self.menu = None
		log.warning('FIXME: setting MPV options')
		self.mpv['hwdec'] = 'auto'
		self.mpv['osd-duration'] = 1000
		self.mpv['osd-level'] = 1
		self.mpv['video-timing-offset'] = 0
		#self.mpv['af'] = 'lavfi=[dynaudnorm=p=1]'
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
		self.mpv.observe_property('duration', self.duration_changed)
		self.mpv.observe_property('eof-reached', self.eof_reached)

		# FIXME
		self.texture = draw.Texture.video
		self.fbo = gl.glGenFramebuffers(1)
		gl.glBindFramebuffer(gl.GL_FRAMEBUFFER, self.fbo)
		#gl.glBindTexture(gl.GL_TEXTURE_2D, draw.SuperTexture.tid)
		gl.glFramebufferTexture2D(gl.GL_FRAMEBUFFER, gl.GL_COLOR_ATTACHMENT0, gl.GL_TEXTURE_2D, draw.SuperTexture.tid, 0)
		assert gl.glCheckFramebufferStatus(gl.GL_FRAMEBUFFER) == gl.GL_FRAMEBUFFER_COMPLETE
		gl.glBindFramebuffer(gl.GL_FRAMEBUFFER, 0)
		#gl.glBindTexture(gl.GL_TEXTURE_2D, 0)
		self.quad = draw.Quad(z=0, w=width, h=height, texture=self.texture)

		# FIXME: broken for now
		#self.texture = draw.ExternalTexture(self.tid)
		#self.video_quad = draw.Quad(0, 0, self.width, self.height, 0, texture=self.texture)

	def eof_reached(self, prop, value):
		if value is False:
			return

		log.info(f'Reached EOF @pos={self.position}')
		# The video is likely to not reach pos=1 on EOF, so we round up.
		if self.position > 0.99:
			self.position = 1
		self.stop()
		# FIXME: tight coupling
		if self.menu:
			# FIXME: this is really ugly; this method is called from another thread, so
			# this will call menu.open() asynchronously, which may interfere with what
			# the user is doing at this point.
			time.sleep(0.5)
			self.menu.open()

	def size_changed(self, prop, value):
		log.info(f'Video {prop} is {value}')

	def position_changed(self, prop, value):
		log.debug(f'Video percent-pos changed to {value}')
		assert prop == 'percent-pos'

		if self.position_immune_until > time.time():
			log.debug(f'Video percent-pos is immune, ignoring')
			return
		if value is None:
			return
		self.position = value / 100

		if self.tile:
			self.tile.update_pos(self.position)

	def duration_changed(self, prop, value):
		log.debug(f'Video duration changed to {value}')
		assert prop == 'duration'
		self.duration = value

	def pause(self, pause=None):
		if pause is None:
			pause = not self.mpv.pause

		if pause != self.mpv.pause:
			log.info('Pausing video' if pause else 'Unpausing video')
			self.mpv.pause = pause

	def start(self, filename, position=0, menu=None, tile=None):
		if self.current_file:
			self.stop()
		log.info(f'Starting playback for {filename} at pos={position}')

		self.current_file = filename
		self.should_render = True
		self.rendered = False
		self.position = 0 if position == 1 else position
		self.duration = None
		self.tile = tile
		self.menu = menu

		self.position_immune_until = time.time() + 1
		self.mpv.play(filename)
		self.pause(False)
		if self.position > 0:
			log.info(f'Seeking to position {position}')
			# FIXME
			# Updating the position only works after libmpv has had
			# a chance to initialize the video; so we spin here until
			# libmpv is ready.
			while not self.context.update():
				time.sleep(0.01)
			self.mpv.percent_pos = position * 100

	def stop(self):
		log.info(f'Stopping playback for {self.current_file}')
		# Not sure why this'd be necessary
		#self.pause(False)
		self.mpv.stop()

		if self.tile:
			self.tile.update_pos(self.position, force=True)

		self.current_file = None
		# Hmm, maybe not do this? Is the memory valid after stop though?
		self.should_render = False
		self.rendered = False
		self.tile = None

	def seek(self, amount, whence='relative'):
		log.info(f'Seeking {whence} {amount}')
		try:
			self.mpv.seek(amount, whence)
		except SystemError as e:
			# FIXME
			log.warning('Seek error')
			print(e)

	def render(self):
		if self.should_render and self.context.update():
			log.debug('Rendering frame')
			# FIXME: apparently, we shouldn't call other mpv functions from the same
			# thread as render(). Find a way to fix that.
			ret = self.context.render(flip_y=False, opengl_fbo={'w': self.width, 'h': self.height, 'fbo': self.fbo})
			self.rendered = True

	def draw(self, window_width, window_height):
		return
		if not self.rendered:
			#log.debug('Drawing frame skipped because not rendered')
			return

		return
		#log.debug('Drawing frame')
		video_width, video_height = self.video_size

		# Draw video
		draw.Quad((0, 0, window_width, window_height), 0, self.tid)

		# Draw position bar + shadow
		position_bar_height = 3
		position_shadow_height = 5
		position_shadow_top_color = (0, 0, 0, 0.25)
		position_shadow_bottom_color = (0, 0, 0, 1)
		position_bar_color = (0.4, 0.4, 1, 1)  # Blueish
		#position_bar_color = (0.8, 0.1, 0.1, 1)  # Red

		#ShadedQuad(
		#	(0, position_bar_height, window_width, position_bar_height + position_shadow_height),
		#	1,
		#	((0, 0, 0, 1), (0, 0, 0, 1), (0, 0, 0, 0), (0, 0, 0, 0))
		#)
		#FlatQuad((0, 0, window_width                , position_bar_height), 1, (0, 0, 0, 1))
		#FlatQuad((0, 0, window_width * self.position, position_bar_height), 2, position_bar_color)
