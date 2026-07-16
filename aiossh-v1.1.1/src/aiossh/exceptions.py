"""
AIOSSH Exceptions - v1.1.0

Comprehensive, specific exception hierarchy for precise error handling.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional


class AIOSSHException(Exception):
    """Base exception for all AIOSSH errors."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "GENERIC_ERROR",
        details: Optional[dict[str, Any]] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}
        self.cause = cause
        self.timestamp = datetime.now(timezone.utc).isoformat()

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


class AIOSSHConnectionError(AIOSSHException):
    """Base for all connection-related errors."""


class AIOSSHConnectionTimeoutError(AIOSSHConnectionError):
    pass


class AIOSSHConnectionRefusedError(AIOSSHConnectionError):
    pass


class AIOSSHHostKeyVerificationError(AIOSSHConnectionError):
    pass


class AIOSSHAuthenticationError(AIOSSHException):
    pass


class AIOSSHInvalidCredentialsError(AIOSSHAuthenticationError):
    pass


class AIOSSHSessionError(AIOSSHException):
    pass


class AIOSSHSessionExpiredError(AIOSSHSessionError):
    pass


class AIOSSHSessionNotFoundError(AIOSSHSessionError):
    pass


class AIOSSHCommandError(AIOSSHException):
    """Raised when an SSH command fails or times out.

    Accepts an optional ``command`` keyword that is stored in ``details``
    for easier debugging / logging.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str = "CMD_ERROR",
        details: Optional[dict[str, Any]] = None,
        cause: Optional[BaseException] = None,
        command: Optional[str] = None,
    ) -> None:
        details = dict(details or {})
        if command is not None:
            details.setdefault("command", command)
        super().__init__(message, code=code, details=details, cause=cause)
        self.command = command


class AIOSSHCommandTimeoutError(AIOSSHCommandError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "CMD_TIMEOUT",
        details: Optional[dict[str, Any]] = None,
        cause: Optional[BaseException] = None,
        command: Optional[str] = None,
    ) -> None:
        super().__init__(
            message, code=code, details=details, cause=cause, command=command
        )


class AIOSSHFileTransferError(AIOSSHException):
    pass


class AIOSSHFileTransferNotFoundError(AIOSSHFileTransferError):
    pass


class AIOSSHFileUploadError(AIOSSHFileTransferError):
    pass


class AIOSSHFileDownloadError(AIOSSHFileTransferError):
    pass


class AIOSSHFileDiskFullError(AIOSSHFileTransferError):
    pass


class AIOSSHSecurityError(AIOSSHException):
    pass


class AIOSSHIntegrityError(AIOSSHSecurityError):
    pass


class AIOSSHRateLimitError(AIOSSHException):
    pass


class AIOSSHConfigurationError(AIOSSHException):
    pass


class AIOSSHValidationError(AIOSSHException):
    pass


class AIOSSHInvalidParameterError(AIOSSHValidationError):
    pass


class AIOSSHPoolExhaustedError(AIOSSHException):
    pass


class AIOSSHProxyError(AIOSSHException):
    pass


class AIOSSHPluginError(AIOSSHException):
    pass


class AIOSSHEncryptionError(AIOSSHSecurityError):
    """Raised when encryption or decryption of sensitive data fails."""


class AIOSSHSessionCorruptedError(AIOSSHSessionError):
    """Raised when a stored session file is corrupted or invalid."""
