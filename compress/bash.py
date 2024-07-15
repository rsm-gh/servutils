#!/usr/bin/python3

#
#  Copyright (C) 2015-2023 Rafael Senties Martinelli. All Rights Reserved. 
#

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
sys.path.insert(1, "/home/cadweb/cadweb/core/django/")

from cadweb.settings import MIN_RESOURCES, MINIFY_SCRIPTS, REDUCE_SCRIPTS, DEBUG
from compress.compress import compress_directory

if MIN_RESOURCES:
    compress_directory(MINIFY_SCRIPTS, REDUCE_SCRIPTS, DEBUG)
