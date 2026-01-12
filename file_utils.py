"""
File and directory utilities for Activity Tracker.

Provides functions for safe file operations, path management,
and directory creation.
"""

import os
import json
from pathlib import Path
from typing import Optional
from datetime import date
from config import (
    DATA_DIR,
    FILENAME_REFINED_TEXT,
    FILENAME_ACTIVITY_TREE,
    FILENAME_KEYSTROKE_EXPORT,
    FILENAME_REFINED_EXPORT
)
from date_utils import format_date_filename


def ensure_data_directory() -> Path:
    """
    Ensure the data directory exists. Create if needed.

    Returns:
        Path object for data directory
    """
    DATA_DIR.mkdir(exist_ok=True)
    return DATA_DIR


def get_refined_text_path(date_obj: date) -> Path:
    """Get path for refined text file for a given date."""
    ensure_data_directory()
    filename = FILENAME_REFINED_TEXT.format(date=format_date_filename(date_obj))
    return DATA_DIR / filename


def get_activity_tree_path(date_obj: date) -> Path:
    """Get path for activity tree JSON file for a given date."""
    ensure_data_directory()
    filename = FILENAME_ACTIVITY_TREE.format(date=format_date_filename(date_obj))
    return DATA_DIR / filename


def get_keystroke_export_filename(date_obj: date, refined: bool = False) -> str:
    """Get filename for keystroke export."""
    if refined:
        return FILENAME_REFINED_EXPORT.format(date=format_date_filename(date_obj))
    else:
        return FILENAME_KEYSTROKE_EXPORT.format(date=format_date_filename(date_obj))


def read_text_file(file_path: Path) -> Optional[str]:
    """
    Safely read text file.

    Returns:
        File content or None if file doesn't exist or error occurs
    """
    try:
        if file_path.exists():
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
    except Exception as e:
        print(f"Error reading file {file_path}: {e}")
    return None


def write_text_file(file_path: Path, content: str) -> bool:
    """
    Safely write text file.

    Returns:
        True if successful, False otherwise
    """
    try:
        ensure_data_directory()
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    except Exception as e:
        print(f"Error writing file {file_path}: {e}")
        return False


def read_json_file(file_path: Path) -> Optional[dict]:
    """
    Safely read JSON file.

    Returns:
        Parsed JSON dict or None if error occurs
    """
    try:
        if file_path.exists():
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"Error reading JSON file {file_path}: {e}")
    return None


def write_json_file(file_path: Path, data: dict) -> bool:
    """
    Safely write JSON file.

    Returns:
        True if successful, False otherwise
    """
    try:
        ensure_data_directory()
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error writing JSON file {file_path}: {e}")
        return False
