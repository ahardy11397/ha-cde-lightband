"""Exceptions for CDE Lightband integration."""

class CdeError(Exception):
    """Base exception for CDE Lightband errors."""

class CdeAuthError(CdeError):
    """Exception raised when authentication fails."""

class CdeConnectionError(CdeError):
    """Exception raised when network or connection fails."""

class CdeDataError(CdeError):
    """Exception raised when response data format is invalid."""
