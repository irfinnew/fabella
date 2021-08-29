#! /usr/bin/env python

import sys
import time
import freetype
import PIL.Image

font_name = sys.argv[1]
font_size = int(sys.argv[2])
stroke_width = int(sys.argv[3])
border = 8


def draw_text(face, stroke_width, text, border, height, above):
	height += border * 2
	above += border

	# Determine width
	offset = border
	previous = 0
	for c in text:
		face.load_char(c, freetype.FT_LOAD_DEFAULT | freetype.FT_LOAD_NO_BITMAP)
		slot = face.glyph
		offset += face.get_kerning(previous, c).x >> 6
		offset += slot.advance.x >> 6
		previous = c
	offset += border
	width = offset

	stroker = freetype.Stroker()
	stroker.set(int(stroke_width * 64), freetype.FT_STROKER_LINECAP_ROUND, freetype.FT_STROKER_LINEJOIN_ROUND, 0 )

	img = PIL.Image.new('RGBA', (width, height), (0, 0, 0, 0))
	offset = border
	previous = 0
	for c in text:
		face.load_char(c, freetype.FT_LOAD_DEFAULT | freetype.FT_LOAD_NO_BITMAP)
		slot = face.glyph

		glyph = slot.get_glyph()
		glyph.stroke( stroker , True )
		blyph = glyph.to_bitmap(freetype.FT_RENDER_MODE_NORMAL, freetype.Vector(0,0), True )
		bitmap = blyph.bitmap

		offset += face.get_kerning(previous, c).x >> 6
		if bitmap.width:
			char_img = PIL.Image.frombytes('L', (bitmap.width, bitmap.rows), bytes(bitmap.buffer))
			img.paste((0, 0, 0), (offset + blyph.left, above - blyph.top), char_img)

			face.load_char(c)
			slot = face.glyph
			bitmap = slot.bitmap
			char_img = PIL.Image.frombytes('L', (bitmap.width, bitmap.rows), bytes(bitmap.buffer))
			img.paste((255, 255, 255), (offset + slot.bitmap_left, above - slot.bitmap_top), char_img)

		offset += slot.advance.x >> 6
		previous = c

	offset += border
	return img


face = freetype.Face(font_name)
face.set_char_size(height=font_size << 6)
height = face.size.height >> 6
above = face.size.ascender >> 6

characters = 0
duration = 0
for i, line in enumerate(sys.stdin):
	line = line.strip()
	if line:
		characters += len(line)
		duration -= time.time()
		image = draw_text(face, stroke_width, line, border, height, above)
		duration += time.time()
		image.save(f'output-{i:04}.png')

print(f'Rendered {characters} characters in {duration} seconds; {int(characters/duration)} chars/sec.')
