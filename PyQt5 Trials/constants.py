"""
constants.py - Application constants
"""

import os

VERSION = "2.0.0"
ICON_PIXELS = 16
DEFAULT_CHARL = 85.0
DEFAULT_AREA = 62.5
MASTER_POLL_MS = 800

# Default base directory - modify as needed
BASEDIR = os.path.expanduser("~/Documents/TensileData")
if not os.path.exists(BASEDIR):
    BASEDIR = os.getcwd()