#! /usr/bin/env python3

import time
import math
import random
import pyglet

pyglet.resource.path = ['../../img']
pyglet.resource.reindex()

COUNT = 1000

screens = pyglet.canvas.get_display().get_screens()
window = pyglet.window.Window(fullscreen=True, screen=screens[1])

label = pyglet.text.Label('Hello, world', font_name='Ubuntu', font_size=36,
	x=window.width//2, y=window.height//2, anchor_x='center', anchor_y='center')

images = []
for fn in ['unseen', 'watching', 'tagged']:
	i = pyglet.resource.image(f'{fn}.png')
	i.anchor_x = i.width // 2
	i.anchor_y = i.height // 2
	images.append(i)

def make_sprites(N, batch, group=None):
	sprites = []
	for i in range(N):
		s = pyglet.sprite.Sprite(img=random.choice(images), batch=batch, group=group)
		s.scale = 0.1
		s.position = (random.randint(0, window.width), random.randint(0, window.height))
		sprites.append(s)
	return sprites

class SlideGroup(pyglet.graphics.OrderedGroup):
	def set_state(self):
		pyglet.gl.glPushMatrix()
		x = int(math.sin(time.time()) * 1920)
		pyglet.gl.glTranslatef(x, 0, 0.0)
		pyglet.gl.glColor4f(1, 1, 1, 0.5)

	def unset_state(self):
		pyglet.gl.glPopMatrix()

batch = pyglet.graphics.Batch()
sprites = make_sprites(COUNT, batch, group=pyglet.graphics.OrderedGroup(0)) + make_sprites(COUNT, batch, group=SlideGroup(1))

def update(dt):
	for s in sprites:
		s.position = (s.x + random.randint(-1, 1), s.y + random.randint(-1, 1))
		#s.x += random.randint(-1, 1)
		#s.y += random.randint(-1, 1)
		#s.rotation += 5
		pass

pyglet.clock.schedule_interval(update, 1 / 60)

@window.event
def on_draw():
	window.clear()
	#for s in sprites:
	#	s.draw()
	batch.draw()
	label.draw()

	on_draw.frame_count += 1
	if time.time() - on_draw.frame_time > 1:
		print(f'{on_draw.frame_count} FPS')
		on_draw.frame_time += 1
		on_draw.frame_count = 0
on_draw.frame_time = time.time()
on_draw.frame_count = 0

pyglet.app.run()
