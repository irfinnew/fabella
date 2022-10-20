# Fabella - Simple, elegant video library and player.
#
# Copyright 2020-2022 Marcel Moreaux.
# Licensed under GPL v2.0, or (at your option) any later version.
# (SPDX GPL-2.0-or-later) See LICENSE file for details.



# https://github.com/mpv-player/mpv/blob/master/libmpv/render_gl.h#L91

import ctypes
import time
import mpv
import OpenGL.GL as gl

import loghelper
import config
import draw
import window
import util

log = loghelper.get_logger('Video', loghelper.Color.Yellow)



class Video:
	def __init__(self, width, height, menu):
		# https://mpv.io/manual/master/
		try:
			log.info(f'libmpv version {mpv.MPV_VERSION[0]}.{mpv.MPV_VERSION[1]}')
		except AttributeError:
			log.warning('libmpv version unknown! Old python-mpv?')
		log.debug('Created instance')
		self.current_file = None
		self.duration = 0
		self.paused = False
		self.seeking = False
		self.position = 0
		self.position_immune_until = 0
		self.position_request = None
		self.tile = None
		self.width = width
		self.height = height

		# Seek UI
		self.seek_back_quad = draw.FlatQuad(z=1, color=config.video.position_shadow_color,
			w=width, h=config.video.position_bar_height + config.video.position_shadow_height)
		self.seek_bar_quad = draw.FlatQuad(z=2, color=config.video.position_bar_color,
			w=0, h=config.video.position_bar_height)
		pos_height = config.video.position_bar_height * config.video.position_bar_active_scale + config.video.position_shadow_height
		self.seek_text = menu.menu_font.text(z=3, text='duration', anchor='br',
			x=width - config.menu.header_hspace, y=pos_height + menu.menu_font.height() // 4,
			pos=(0, -(pos_height + int(menu.menu_font.height() * 1.25))),
		)

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

		self.menu = menu
		# FIXME: should come from configuration, at least partially
		log.warning('FIXME: setting MPV options')

		# time interpolation for smoother video. Needs research.
		# https://github.com/mpv-player/mpv/wiki/Interpolation
		#self.mpv['video-sync'] = 'display-resample'
		#self.mpv['interpolation'] = 'yes'
		#self.mpv['override-display-fps'] = 59

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
			wl_display=ctypes.c_void_p(window.get_wayland_display()),
			opengl_init_params={'get_proc_address': mpv.OpenGlCbGetProcAddrFn(lambda _, name: window.get_proc_address(name.decode('utf8')))},
		)
		self.context.update_cb = self.frame_ready
		self.mpv.observe_property('width', self.size_changed)
		self.mpv.observe_property('height', self.size_changed)
		self.mpv.observe_property('percent-pos', self.position_changed)
		self.mpv.observe_property('duration', self.duration_changed)
		self.mpv.observe_property('pause', self.pause_changed)
		self.mpv.observe_property('eof-reached', self.eof_reached)

		# Set up video texture / FBO / Quad
		self.texture = draw.Texture.video
		self.fbo = gl.glGenFramebuffers(1)
		gl.glBindFramebuffer(gl.GL_FRAMEBUFFER, self.fbo)
		gl.glFramebufferTexture2D(gl.GL_FRAMEBUFFER, gl.GL_COLOR_ATTACHMENT0, gl.GL_TEXTURE_2D, draw.TextureAtlas.tid, 0)
		assert gl.glCheckFramebufferStatus(gl.GL_FRAMEBUFFER) == gl.GL_FRAMEBUFFER_COMPLETE
		gl.glBindFramebuffer(gl.GL_FRAMEBUFFER, 0)
		self.quad = draw.Quad(z=0, w=width, h=height, texture=self.texture)


	def frame_ready(self):
		# Wake up main loop, so self.render() will get called
		window.wakeup()


	def eof_reached(self, prop, value):
		if value is False:
			return

		log.info(f'Reached EOF @pos={self.position}')
		# The video is likely to not reach pos=1 on EOF, so we round up.
		if self.position > 0.99:
			self.position = 1
		self.stop()
		# FIXME: tight coupling
		# Also, we hope this method is called in time, so the open() doesn't interfere
		# with whatever the user is doing.
		# FIXME: even worse, calling draw stuff from another thread has race conditions
		# with the render code. This might happen in more places...
		if self.menu:
			self.menu.open()


	def osd_update_position(self, position, duration, paused):
		log.debug(f'osd_update_position({position=}, {duration=}, {paused=})')

		if position is None or duration is None:
			osd_text = '?:??'
			seek_text = ''
		else:
			paused = '⏸️' if paused else '▶️'
			position = util.duration_format(int(position * duration), seconds=True)
			duration = util.duration_format(int(duration), seconds=True)

			osd_text = f'{paused}  {position}  /  {duration}'
			seek_text = f'{position}'

		self.seek_text.text = seek_text
		self.menu.osd_duration_text.text = osd_text
		# Ugh.
		self.menu.osd_name_text.max_width = self.menu.width - self.menu.osd_duration_text.quad.w - config.menu.header_hspace * 3


	def size_changed(self, prop, value):
		log.info(f'Video {prop} is {value}')


	def position_changed(self, prop, value):
		log.debug(f'Video percent-pos changed to {value}')
		assert prop == 'percent-pos'

		if value is None:
			return

		self.position = value / 100

		if self.position_immune_until > time.time():
			log.debug(f'Video percent-pos is immune, not updating tile')
		else:
			if self.tile:
				self.tile.update_pos(self.position)


	def pause_changed(self, prop, value):
		log.info(f'Video paused changed to {value}')
		assert prop == 'pause'

		self.paused = value


	def duration_changed(self, prop, value):
		log.info(f'Video duration changed to {value}')
		assert prop == 'duration'
		self.duration = value

		# Setting the video position only works after the video duration is known.
		# If there was a queued request for setting position, handle it now.
		if self.position_request is not None and self.position_request > 0:
			log.info(f'Performing delayed seek to position {self.position_request}')
			pos = self.position_request * self.duration
			pos = max(0, pos - 2) # Start a little earlier to have overlap with previous stop
			self.mpv.seek(pos, 'absolute')
			self.position_request = None


	def pause(self, pause=None):
		if pause is None:
			pause = not self.paused

		if pause != self.paused:
			log.info('Pausing video' if pause else 'Unpausing video')
			self.mpv.pause = pause
			self.paused = pause


	def start(self, filename, position=0, tile=None):
		assert self.current_file is None
		if self.current_file:
			self.stop()
		log.info(f'Starting playback for {filename} at pos={position}')

		self.current_file = filename
		self.position = 0 if position == 1 else position
		self.duration = None
		self.tile = tile

		# Don't update the position registration until a bit of time has passed.
		self.position_immune_until = time.time() + 2
		self.mpv.play(filename)
		self.pause(False)
		if self.position > 0:
			# Setting the video position only works after the video is sufficiently
			# initialized. Set a request that will be handled later.
			log.info(f'Requesting delayed seek to {position}')
			self.position_request = self.position


	def stop(self):
		log.info(f'Stopping playback for {self.current_file}')
		# Not sure why this'd be necessary
		#self.pause(False)
		self.mpv.stop()

		if self.tile:
			self.tile.update_pos(self.position, force=True)

		self.current_file = None
		# Hmm, maybe not do this? Is the memory valid after stop though?
		self.tile = None


	def seek(self, amount, whence='relative'):
		log.info(f'Seeking {whence} {amount}')
		if self.seeking:
			log.info('Already a seek in progress; ignoring')
			return

		self.seeking = True
		try:
			self.mpv.seek(amount, whence)
		except SystemError as e:
			# FIXME
			log.warning('Seek error')
			print(e)
		else:
			self.position_immune_until = 0

		orig_bar_h = config.video.position_bar_height
		orig_back_h = orig_bar_h + config.video.position_shadow_height
		new_bar_h = orig_bar_h * config.video.position_bar_active_scale
		new_back_h = new_bar_h + config.video.position_shadow_height

		draw.Animation(self.seek_back_quad, duration=1, delay=2, h=(new_back_h, orig_back_h))
		draw.Animation(self.seek_bar_quad, duration=1, delay=2, h=(new_bar_h, orig_bar_h))
		offset = new_back_h + int(self.seek_text.quad.h * 1.25)
		draw.Animation(self.seek_text.quad, duration=1, delay=2, ypos=(0, -offset), ease='in')

		draw.Animation(self.seek_back_quad, duration=0.3, h=(None, new_back_h))
		draw.Animation(self.seek_bar_quad, duration=0.3, h=(None, new_bar_h))
		draw.Animation(self.seek_text.quad, duration=0.3, ypos=(None, 0), ease='out')


	def render(self):
		self.osd_update_position(self.position, self.duration, self.paused)

		if self.context.update():
			log.debug('Rendering frame')
			# FIXME: apparently, we shouldn't call other mpv functions from the same
			# thread as render(). Find a way to fix that.
			ret = self.context.render(flip_y=False, opengl_fbo={'w': self.width, 'h': self.height, 'fbo': self.fbo})
			self.texture.force_redraw()

			# FIXME: not sure if this is the proper place for this...
			new_pos = int(self.width * self.position)
			if self.seek_bar_quad.w != new_pos:
				self.seek_bar_quad.w = new_pos

			self.seeking = False
