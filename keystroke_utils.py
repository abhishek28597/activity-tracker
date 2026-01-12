"""
Keystroke reconstruction utilities for Activity Tracker.

Provides functions to reconstruct text from keystroke logs and format
grouped keystrokes for display or export.
"""

from typing import List, Dict, Tuple
from datetime import datetime
from config import IGNORE_KEYS
from date_utils import format_timestamp_display


def reconstruct_text(keystrokes: List[str]) -> str:
    """
    Reconstruct readable text from a list of keystroke strings.

    Args:
        keystrokes: List of key strings (e.g., ['h', 'e', 'l', 'l', 'o'])

    Returns:
        Reconstructed text string
    """
    result = []
    for key in keystrokes:
        key_lower = key.lower()

        # Skip ignored keys
        if key_lower in IGNORE_KEYS:
            continue

        # Handle special keys
        if key_lower == 'backspace':
            if result:
                result.pop()
        elif key_lower == 'space':
            result.append(' ')
        elif key_lower in ('enter', 'return'):
            result.append('\n')
        elif len(key) == 1:
            # Regular character
            result.append(key)

    return ''.join(result)


def group_keystrokes_by_app(
    keystrokes: List[Dict]
) -> List[Tuple[str, str, List[str]]]:
    """
    Group keystrokes by application changes.

    Args:
        keystrokes: List of dicts with 'timestamp', 'key_pressed', 'app_name' keys

    Returns:
        List of tuples: (timestamp, app_name, [keys])

    Example:
        >>> keystrokes = [
        ...     {'timestamp': '2026-01-08 10:00:00', 'key_pressed': 'h', 'app_name': 'Terminal'},
        ...     {'timestamp': '2026-01-08 10:00:01', 'key_pressed': 'i', 'app_name': 'Terminal'},
        ... ]
        >>> group_keystrokes_by_app(keystrokes)
        [('2026-01-08 10:00:00', 'Terminal', ['h', 'i'])]
    """
    if not keystrokes:
        return []

    groups = []
    current_app = None
    current_keys = []
    current_timestamp = None

    for ks in keystrokes:
        # When app changes, save previous group
        if current_app is not None and ks['app_name'] != current_app:
            if current_timestamp:
                groups.append((current_timestamp, current_app, current_keys))
            current_keys = []

        # Update current app and add key
        if current_app != ks['app_name']:
            current_app = ks['app_name']
            current_timestamp = ks['timestamp']

        current_keys.append(ks['key_pressed'])

    # Add last group
    if current_app is not None and current_timestamp:
        groups.append((current_timestamp, current_app, current_keys))

    return groups


def format_keystroke_groups(
    groups: List[Tuple[str, str, List[str]]]
) -> str:
    """
    Format grouped keystrokes into readable text output.

    Args:
        groups: List of tuples from group_keystrokes_by_app()

    Returns:
        Formatted text with timestamps, app names, and reconstructed text
    """
    output_lines = []

    for timestamp, app_name, keys in groups:
        reconstructed = reconstruct_text(keys)
        has_text = reconstructed.strip()

        formatted_time = format_timestamp_display(timestamp)
        output_lines.append(formatted_time)
        output_lines.append(f"[{app_name}]")

        if has_text:
            output_lines.append(reconstructed)
        else:
            output_lines.append("(App switch activity)")
        output_lines.append("")  # Empty line between groups

    return '\n'.join(output_lines)
