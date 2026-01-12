"""
Configuration module for Activity Tracker.

Centralizes all constants, configurations, and magic strings.
"""

import os
from pathlib import Path

# Application paths
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
DATABASE_PATH = PROJECT_ROOT / "activity.db"

# Database configuration
DB_TABLE_ACTIVITY_LOG = "activity_log"
DB_TABLE_KEYSTROKE_LOG = "keystroke_log"

# Date and time formats
DATE_FORMAT_ISO = "%Y-%m-%d"
DATE_FORMAT_DISPLAY = "%-d %b %Y at %-I:%M %p"
DATE_FORMAT_FILENAME = "%Y-%m-%d"

# File naming patterns
FILENAME_REFINED_TEXT = "{date}_refined.txt"
FILENAME_ACTIVITY_TREE = "{date}_refined_tree.json"
FILENAME_KEYSTROKE_EXPORT = "{date}_key_stroke.txt"
FILENAME_REFINED_EXPORT = "{date}_refined_key_stroke.txt"

# LLM configuration
LLM_MODEL_NAME = "llama-3.3-70b-versatile"
LLM_TEMPERATURE_REFINEMENT = 0.3
LLM_TEMPERATURE_CONCEPT_EXTRACTION = 0.5
LLM_TEMPERATURE_DAY_ACTIVITY = 0.7
LLM_MAX_TOKENS_REFINEMENT = 4096
LLM_MAX_TOKENS_CONCEPT = 256
LLM_MAX_TOKENS_AGGREGATE = 512
LLM_MAX_TOKENS_DAY = 64

# Keystroke reconstruction
IGNORE_KEYS = {
    'shift', 'shift_r', 'ctrl', 'ctrl_r', 'alt', 'alt_r', 'alt_gr',
    'cmd', 'cmd_r', 'caps_lock', 'up', 'down', 'left', 'right',
    'home', 'end', 'page_up', 'page_down', 'delete', 'escape',
    'f1', 'f2', 'f3', 'f4', 'f5', 'f6', 'f7', 'f8', 'f9', 'f10', 'f11', 'f12',
    'tab', 'print_screen', 'scroll_lock', 'pause', 'insert', 'num_lock',
    'menu'
}

# Activity tracking
ACTIVITY_SAVE_INTERVAL_SECONDS = 60
KEYSTROKE_LIMIT_DASHBOARD = 500

# Flask configuration
FLASK_HOST = "127.0.0.1"
FLASK_PORT = 5000
FLASK_DEBUG = True
