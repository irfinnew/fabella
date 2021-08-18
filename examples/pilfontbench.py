#! /usr/bin/env python3

import os
import sys
import time
from PIL import Image, ImageDraw, ImageFont

# Takes about 20ms
text = 'Comparative Wickedness of Civilized and Unenlightened Peoples'
size = 30
stroke = 3

font = ImageFont.truetype('DejaVuSans', size)

#w, h = font.getsize(text)
image = Image.new('RGBA', (8, 8), (0, 164, 201))
w, h = ImageDraw.Draw(image).textsize(text, font, stroke_width=stroke)

image = Image.new('RGBA', (w + 64, h + 64), (0, 164, 201, 0))
draw = ImageDraw.Draw(image)

start = time.time()
for i in range(1000):
	draw.text((32, 32), text, font=font, align='center', fill=(255, 255, 255), stroke_width=stroke, stroke_fill=(0, 0, 0))
print(time.time() - start)

image.save('sample.png')
