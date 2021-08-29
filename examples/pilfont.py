#! /usr/bin/env python3

import os
import sys
import time
from PIL import Image, ImageDraw, ImageFont

font_name = sys.argv[1]
font_size = int(sys.argv[2])
font_stroke = int(sys.argv[3])
border = 8


def draw_text(font, font_stroke, text, border, size_img):
	w, h = ImageDraw.Draw(size_img).textsize(text, font, font_stroke)
	w += border * 2
	h += border * 2

	image = Image.new('RGBA', (w, h), (0,0,0,0))
	draw = ImageDraw.Draw(image)
	draw.text((border, border), text, font=font, fill=(255,255,255,255), stroke_width=font_stroke, stroke_fill=(0,0,0,255))

	return image

size_img = Image.new('RGBA', (8, 8), (0, 164, 201))
font = ImageFont.truetype(font_name, font_size)

characters = 0
duration = 0
for i, line in enumerate(sys.stdin):
	line = line.strip()
	if line:
		characters += len(line)
		duration -= time.time()
		image = draw_text(font, font_stroke, line, border, size_img)
		duration += time.time()
		image.save(f'output-{i:04}.png')

print(f'Rendered {characters} characters in {duration} seconds; {int(characters/duration)} chars/sec.')
