# Fabella - Simple, elegant video library and player.
#
# Copyright 2020-2022 Marcel Moreaux.
# Licensed under GPL v2.0, or (at your option) any later version.
# (SPDX GPL-2.0-or-later) See LICENSE file for details.



class tile:
	width = 320
	cover_height = 200
	min_hspace = 48
	min_vspace = 32
	text_vspace = 8
	text_font = 'Ubuntu Medium'
	text_size = 18
	text_lines = 3
	text_lines_selected = 3

	pos_bar_height = 2
	#pos_bar_color = (0.4, 0.4, 1, 1)
	pos_bar_color = (0.8, 0.1, 0.1, 1)
	emblem_scale = 0.2

	thumb_dirs = ['covers']
	thumb_files = ['cover.jpg']

	shadow_blursize = 32
	shadow_expand = 4
	shadow_offset = 8
	shadow_color = (0, 0, 0, 1)

	outline_size = 2
	outline_color = (0, 0, 0, 1)

	highlight_outset = 6
	highlight_color = (0.55, 0.7, 1, 1)

	text_color = (0.6, 0.6, 0.6, 1)
	text_hl_color = (1, 1, 1, 1)

class menu:
	background_image = None
	#background_color = (0.2, 0.2, 0.25, 1)
	background_color = (0.16, 0.16, 0.2, 1)
	text_font = 'Ubuntu Medium'
	text_size = 36
	header_hspace = 64
	header_vspace = 32

class video:
	position_bar_height = 2
	position_shadow_height = 2
	position_bar_color = (0.4, 0.4, 1, 1)  # Blueish
	#position_bar_color = (0.8, 0.1, 0.1, 1)  # Reddish
	position_shadow_color = (0, 0, 0, 1)
	position_bar_active_scale = 6
	position_bar_active_duration = 3

class ui:
	dark_mode_brightness = 0.45

class performance:
	text_cache_items = 512
	text_low_quality_outline = False
