#!/usr/bin/env python
import os
import sys

current_dir = os.path.abspath(os.path.dirname(__file__))
parent_dir = os.path.abspath(current_dir+'../../../../')
sys.path.append(parent_dir)
common_library_dir = os.path.abspath(os.path.join(current_dir, '../common_library'))
sys.path.append(common_library_dir)