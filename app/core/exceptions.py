"""Custom exception classes for the ETF Research Platform.

All platform-specific exceptions inherit from ETFPlatformException.
"""


class ETFPlatformException(Exception):
    """Base exception for all platform-specific errors."""

    def __init__(self, message: str = "An unexpected platform error occurred") -> None:
        self.message = message
        super().__init__(self.message)


class DataProviderError(ETFPlatformException):
    """Raised when an external data provider fails or returns invalid data."""

    def __init__(self, message: str = "Data provider error") -> None:
        super().__init__(message)


class ValidationError(ETFPlatformException):
    """Raised when input validation fails."""

    def __init__(self, message: str = "Validation error") -> None:
        super().__init__(message)


class ETLError(ETFPlatformException):
    """Raised when an ETL (Extract, Transform, Load) operation fails."""

    def __init__(self, message: str = "ETL error") -> None:
        super().__init__(message)
