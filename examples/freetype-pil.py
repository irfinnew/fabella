#! /usr/bin/env python

import freetype
import PIL.Image

text = 'Helloy - World!'
face = freetype.Face('Vera.ttf')
face.set_char_size(height=40 << 6)

# Pixels above and below baseline
above = (face.bbox.yMax + 63) >> 6
below = (-face.bbox.yMin + 63) >> 6
height = above + below

# TODO: outlines
img = PIL.Image.new('L', (1024, height), (63,))
offset = 0
previous = 0
for c in text:
	face.load_char(c)
	glyph = face.glyph
	bitmap = glyph.bitmap

	offset += face.get_kerning(previous, c).x >> 6
	if bitmap.width:
		char_img = PIL.Image.frombytes('L', (bitmap.width, bitmap.rows), bytes(bitmap.buffer))
		img.paste(char_img, (offset, above - glyph.bitmap_top))

	offset += glyph.advance.x >> 6
	previous = c

# Ensure the right side of the image is cropped closely
offset -= glyph.advance.x >> 6
offset += bitmap.width

img.crop((0, 0, offset, height)).save('output.png')
