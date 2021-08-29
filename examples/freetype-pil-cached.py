#! /usr/bin/env python

import sys
import time
import freetype
import functools
import PIL.Image

font_name = sys.argv[1]
font_size = int(sys.argv[2])
stroke_width = int(sys.argv[3])
border = 8

@functools.lru_cache(None)
def get_bitmap(face, char, height, above, stroke_width):
	face.load_char(char, freetype.FT_LOAD_DEFAULT | freetype.FT_LOAD_NO_BITMAP)
	slot = face.glyph
	advance = slot.advance.x >> 6

	glyph = slot.get_glyph()
	stroker = freetype.Stroker()
	stroker.set(int(stroke_width * 64), freetype.FT_STROKER_LINECAP_ROUND, freetype.FT_STROKER_LINEJOIN_ROUND, 0 )
	glyph.stroke( stroker , True )
	blyph = glyph.to_bitmap(freetype.FT_RENDER_MODE_NORMAL, freetype.Vector(0,0), True )
	bitmap = blyph.bitmap

	if bitmap.width:
		stroke_img = PIL.Image.new('RGBA', (bitmap.width, height), (0, 0, 0, 0))
		char_img = PIL.Image.frombytes('L', (bitmap.width, bitmap.rows), bytes(bitmap.buffer))
		stroke_img.paste((255, 255, 255, 255), (0, above - blyph.top), char_img)
		stroke_left = blyph.left

		face.load_char(char)
		slot = face.glyph
		bitmap = slot.bitmap
		fill_img = PIL.Image.new('RGBA', (bitmap.width, height), (0, 0, 0, 0))
		char_img = PIL.Image.frombytes('L', (bitmap.width, bitmap.rows), bytes(bitmap.buffer))
		fill_img.paste((255, 255, 255, 255), (0, above - slot.bitmap_top), char_img)
		fill_left = slot.bitmap_left

		return (advance, stroke_left, stroke_img, fill_left, fill_img)
	else:
		return (advance, 0, None, 0, None)


@functools.lru_cache(None)
def get_kerning(face, prev, char):
	return face.get_kerning(prev, char).x >> 6


def draw_text(face, stroke_width, text, border, height, above):
	height += border * 2
	above += border

	offset = border
	previous = 0
	glyphs = []
	for c in text:
		kerning = get_kerning(face, previous, c)
		advance, stroke_left, stroke_img, fill_left, fill_img = get_bitmap(face, c, height, above, stroke_width)

		offset += kerning

		glyphs.append((offset + stroke_left, stroke_img, offset + fill_left, fill_img))

		offset += advance
		previous = c
	offset += border
	width = offset

	# Determine width
	img = PIL.Image.new('RGBA', (width, height), (0, 0, 0, 0))
	for stroke_offset, stroke_img, fill_offset, fill_img in glyphs:
		if fill_img:
			img.paste((0, 0, 0, 255), (stroke_offset, 0, stroke_offset + stroke_img.width, height), stroke_img)
			img.paste((255, 255, 255, 255), (fill_offset, 0, fill_offset + fill_img.width, height), fill_img)
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
