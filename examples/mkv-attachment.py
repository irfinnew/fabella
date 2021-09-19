#! /usr/bin/env python

import sys
import enzyme
import shutil
import logging

#logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

with open(sys.argv[1], 'rb') as fd:
	mkv = enzyme.MKV(fd)

print(mkv.info)

for a in mkv.attachments:
	print(a)
	with open('extracted_' + a.filename, 'wb') as fd:
		shutil.copyfileobj(a.data, fd)
