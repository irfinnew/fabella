#! /bin/sh

/bin/rm output-*; sync
echo
echo pilfont.py
cat *.py | ./pilfont.py Vera.ttf 40 4

/bin/rm output-*; sync
echo
echo freetype-pil.py
cat *.py | ./freetype-pil.py Vera.ttf 40 4

/bin/rm output-*; sync
echo
echo freetype-pil-cached.py
cat *.py | ./freetype-pil-cached.py Vera.ttf 40 4
