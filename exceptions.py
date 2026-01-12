"""
Custom exception classes for Activity Tracker.

Provides specific exception types for better error handling and debugging.
"""


class ActivityTrackerException(Exception):
    """Base exception for activity tracker."""
    pass


class DatabaseException(ActivityTrackerException):
    """Database operation failed."""
    pass


class LLMException(ActivityTrackerException):
    """LLM call or parsing failed."""
    pass


class FileOperationException(ActivityTrackerException):
    """File read/write operation failed."""
    pass


class DateParseException(ActivityTrackerException):
    """Date parsing failed."""
    pass
