#! /usr/bin/env python3

import os
import sys
from PIL import Image, ImageDraw, ImageFont

text = sys.argv[1]

font = ImageFont.truetype('DejaVuSans', 64)

#w, h = font.getsize(text)
image = Image.new('RGBA', (8, 8), (0, 164, 201))
w, h = ImageDraw.Draw(image).textsize(text, font, stroke_width=5)

image = Image.new('RGBA', (w + 64, h + 64), (0, 164, 201, 0))
draw = ImageDraw.Draw(image)

draw.text((32, 32), text, font=font, align='center', fill=(255, 255, 255), stroke_width=5, stroke_fill=(0, 0, 0))

image.save('sample.png')
