"""
Date parsing and formatting utilities for Activity Tracker.

Centralizes date/time handling logic to eliminate duplication.
"""

from datetime import datetime, date
from typing import Optional, Union
from config import DATE_FORMAT_ISO, DATE_FORMAT_DISPLAY, DATE_FORMAT_FILENAME


def parse_date_param(
    date_str: Optional[str],
    default_to_today: bool = True
) -> Optional[date]:
    """
    Parse date parameter from query string or request.

    Args:
        date_str: Date string in YYYY-MM-DD format (or None)
        default_to_today: If True and date_str is None, return today

    Returns:
        date object, or None if parsing fails and default_to_today is False

    Example:
        selected_date = parse_date_param(request.args.get('date'))
    """
    if date_str:
        try:
            return datetime.strptime(date_str, DATE_FORMAT_ISO).date()
        except ValueError:
            if default_to_today:
                return date.today()
            return None
    else:
        if default_to_today:
            return date.today()
        return None


def format_timestamp_display(timestamp: Union[datetime, str]) -> str:
    """
    Format timestamp for display (e.g., "8 Jan 2026 at 1:00 AM").

    Args:
        timestamp: datetime object or ISO format string

    Returns:
        Formatted timestamp string
    """
    if isinstance(timestamp, str):
        timestamp = datetime.fromisoformat(timestamp)
    return timestamp.strftime(DATE_FORMAT_DISPLAY)


def format_date_filename(date_obj: date) -> str:
    """
    Format date for use in filenames (YYYY-MM-DD).

    Args:
        date_obj: date object

    Returns:
        Date string in YYYY-MM-DD format
    """
    return date_obj.strftime(DATE_FORMAT_FILENAME)
