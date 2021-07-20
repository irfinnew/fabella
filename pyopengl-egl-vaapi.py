#! /usr/bin/env python3

# Requires PyOpenGL, PyGame, python-mpv

import os
if not os.environ.get( 'PYOPENGL_PLATFORM' ):
	os.environ['PYOPENGL_PLATFORM'] = 'egl'
os.environ['LIBVA_DRIVER_NAME'] = 'radeonsi'

import sys
import ctypes
import pygame.display
import pygame
import OpenGL.GL as gl
import OpenGL.EGL as egl
from OpenGL import arrays
from mpv import MPV, MpvRenderContext, OpenGlCbGetProcAddrFn


DESIRED_ATTRIBUTES = [
	egl.EGL_BLUE_SIZE, 8,
	egl.EGL_RED_SIZE,8,
	egl.EGL_GREEN_SIZE,8,
	egl.EGL_DEPTH_SIZE,24,
	egl.EGL_COLOR_BUFFER_TYPE, egl.EGL_RGB_BUFFER,
	egl.EGL_CONFIG_CAVEAT, egl.EGL_NONE, # Don't allow slow/non-conformant
]
API_BITS = {
	'opengl': egl.EGL_OPENGL_BIT,
	'gl': egl.EGL_OPENGL_BIT,
	'gles2': egl.EGL_OPENGL_ES2_BIT,
	'gles1': egl.EGL_OPENGL_ES_BIT,
	'gles': egl.EGL_OPENGL_ES_BIT,
	'es2': egl.EGL_OPENGL_ES2_BIT,
	'es1': egl.EGL_OPENGL_ES_BIT,
	'es': egl.EGL_OPENGL_ES_BIT,
}
API_NAMES = dict([
	(k,{
		egl.EGL_OPENGL_BIT:egl.EGL_OPENGL_API,
		egl.EGL_OPENGL_ES2_BIT:egl.EGL_OPENGL_ES_API,
		egl.EGL_OPENGL_ES_BIT:egl.EGL_OPENGL_ES_API
	}[v])
	for k,v in API_BITS.items()
])

api = 'opengl'
attributes = DESIRED_ATTRIBUTES
size = (500, 500)

major,minor = ctypes.c_long(),ctypes.c_long()
display = egl.eglGetDisplay(egl.EGL_DEFAULT_DISPLAY)
egl.eglInitialize( display, major, minor)
num_configs = ctypes.c_long()
configs = (egl.EGLConfig*2)()
api_constant = API_NAMES[api]
local_attributes = attributes[:]
local_attributes.extend( [
	egl.EGL_CONFORMANT, API_BITS[api.lower()],
	egl.EGL_NONE,
])
print('local_attributes', local_attributes)
local_attributes= arrays.GLintArray.asArray( local_attributes )
egl.eglChooseConfig(display, local_attributes, configs, 2, num_configs)
print('API', api_constant)
egl.eglBindAPI(api_constant)

# now need to get a raw X window handle...
pygame.init()
pygame.display.set_mode( size )
window = pygame.display.get_wm_info()['window']
x11_display = pygame.display.get_wm_info()['display']
print(x11_display)
ctypes.pythonapi.PyCapsule_GetPointer.restype = ctypes.c_void_p
ctypes.pythonapi.PyCapsule_GetPointer.argtypes = [ctypes.py_object, ctypes.c_char_p]
foo = ctypes.pythonapi.PyCapsule_GetPointer(x11_display, ctypes.c_char_p(b'display'))
x11_display = ctypes.c_void_p(foo)
surface = egl.eglCreateWindowSurface(display, configs[0], window, None )

ctx = egl.eglCreateContext(display, configs[0], egl.EGL_NO_CONTEXT, None)
if ctx == egl.EGL_NO_CONTEXT:
	raise RuntimeError( 'Unable to create context' )

# Generate FBO
egl.eglMakeCurrent( display, surface, surface, ctx )
fboIDs = (gl.GLuint * 1) ()
gl.glGenFramebuffers(1, fboIDs)
vfboid = fboIDs[0]
gl.glBindFramebuffer(gl.GL_FRAMEBUFFER, vfboid)

# Generate Texture, bind to FBO
textureIDs = (gl.GLuint * 1) ()
gl.glGenTextures(1, textureIDs)
vtid = textureIDs[0]
gl.glBindTexture(gl.GL_TEXTURE_2D, vtid)
gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR)
gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGB, 1920, 1080, 0, gl.GL_RGB, gl.GL_UNSIGNED_BYTE, None)
#gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGBA16F, 1920, 1080, 0, gl.GL_RGBA, gl.GL_HALF_FLOAT, None)
gl.glFramebufferTexture2D(gl.GL_FRAMEBUFFER, gl.GL_COLOR_ATTACHMENT0, gl.GL_TEXTURE_2D, vtid, 0)
assert gl.glCheckFramebufferStatus(gl.GL_FRAMEBUFFER) == gl.GL_FRAMEBUFFER_COMPLETE

gl.glBindFramebuffer(gl.GL_FRAMEBUFFER, 0)
gl.glBindTexture(gl.GL_TEXTURE_2D, 0)

#### MPV setup
def get_process_address(_, name):
	print(f'\x1b[31mget_processaddress({name})\x1b[0m')
	cname = ctypes.cast(ctypes.c_char_p(name), ctypes.POINTER(ctypes.c_ubyte))
	address = egl.eglGetProcAddress(cname)
	return ctypes.cast(address, ctypes.c_void_p).value

def my_log(loglevel, component, message):
	print('\x1b[32m[{}] {}: {}\x1b[0m'.format(loglevel, component, message))

mpv = MPV(log_handler=my_log, loglevel='debug')
mpv['hwdec'] = 'auto'
#mpv['video-timing-offset'] = 0
#mpv_ctx = MpvRenderContext(mpv, 'opengl', opengl_init_params={'get_proc_address': OpenGlCbGetProcAddrFn(get_process_address)})
mpv_ctx = MpvRenderContext(mpv, 'opengl', x11_display=x11_display, opengl_init_params={'get_proc_address': OpenGlCbGetProcAddrFn(get_process_address)})

mpv.play(sys.argv[1])




while True:
	egl.eglMakeCurrent( display, surface, surface, ctx )

	mpv_ctx.render(flip_y=True, opengl_fbo={'w': 1920, 'h': 1080, 'fbo': vfboid})

	gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
	gl.glEnable(gl.GL_BLEND)
	gl.glEnable(gl.GL_TEXTURE_2D)

	gl.glViewport(0, 0, 500, 500)
	gl.glClearColor(1, 1, 1, 1)
	gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)
	gl.glMatrixMode(gl.GL_PROJECTION)
	gl.glLoadIdentity()
	gl.glOrtho(0.0, 500, 0.0, 500, 0.0, 1.0)
	gl.glMatrixMode (gl.GL_MODELVIEW)

	gl.glBindTexture(gl.GL_TEXTURE_2D, vtid)
	gl.glBegin(gl.GL_QUADS)
	gl.glTexCoord2f(0.0, 0.0)
	gl.glVertex2f(100, 100)
	gl.glTexCoord2f(1.0, 0.0)
	gl.glVertex2f(300, 100)
	gl.glTexCoord2f(1.0, 1.0)
	gl.glVertex2f(300, 200)
	gl.glTexCoord2f(0.0, 1.0)
	gl.glVertex2f(100, 200)
	gl.glEnd()
	gl.glBindTexture(gl.GL_TEXTURE_2D, 0)

	egl.eglSwapBuffers( display, surface )

pygame.display.quit()
pygame.quit()
