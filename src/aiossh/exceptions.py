"""
AIOSSH Exception Hierarchy - v2.0

All exceptions are prefixed with 'AIOSSH' to prevent shadowing of Python builtins.
Every exception supports structured details, error codes, and serialization.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional


class AIOSSHException(Exception):
    """Base exception for all AIOSSH errors.

    Attributes:
        message: Human-readable error description.
        code: Machine-readable error code (UPPER_SNAKE_CASE).
        details: Additional structured information about the error.
        timestamp: UTC timestamp when the exception was created.
    """

    def __init__(
        self,
        message: str,
        *,
        code: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or type(self).__name__.upper()
        self.details = details if details is not None else {}
        self.timestamp = datetime.now(timezone.utc)
        if cause is not None:
            self.__cause__ = cause

    def to_dict(self) -> dict[str, Any]:
        """Serialize exception to a JSON-safe dictionary."""
        result: dict[str, Any] = {
            "error": self.message,
            "code": self.code,
            "type": type(self).__name__,
            "timestamp": self.timestamp.isoformat(),
            "details": self.details,
        }
        if self.__cause__ is not None:
            result["cause"] = str(self.__cause__)
        return result

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


# ── Connection Errors ────────────────────────────────────────────────────────

class AIOSSHConnectionError(AIOSSHException):
    """Base class for connection-related errors."""


class AIOSSHConnectionTimeoutError(AIOSSHConnectionError):
    """Connection attempt timed out."""


class AIOSSHConnectionRefusedError(AIOSSHConnectionError):
    """Server actively refused the connection."""


class AIOSSHConnectionResetError(AIOSSHConnectionError):
    """Connection was reset by peer."""


class AIOSSHHostKeyVerificationError(AIOSSHConnectionError):
    """Host key verification failed."""


class AIOSSHProxyError(AIOSSHConnectionError):
    """Proxy connection failed."""


class AIOSSHUnsupportedProtocolError(AIOSSHConnectionError):
    """SSH protocol version not supported."""


# ── Authentication Errors ────────────────────────────────────────────────────

class AIOSSHAuthenticationError(AIOSSHException):
    """Base class for authentication errors."""


class AIOSSHInvalidCredentialsError(AIOSSHAuthenticationError):
    """Invalid username or password provided."""


class AIOSSHKeyAuthenticationError(AIOSSHAuthenticationError):
    """SSH key pair authentication failed."""


class AIOSSHAuthenticationTimeoutError(AIOSSHAuthenticationError):
    """Authentication process timed out."""


class AIOSSHAccountLockedError(AIOSSHAuthenticationError):
    """Account locked due to too many failed attempts."""


# ── Session Errors ───────────────────────────────────────────────────────────

class AIOSSHSessionError(AIOSSHException):
    """Base class for session management errors."""


class AIOSSHSessionExpiredError(AIOSSHSessionError):
    """Session has expired and requires reconnection."""


class AIOSSHSessionNotFoundError(AIOSSHSessionError):
    """Requested session name was not found in registry."""


class AIOSSHSessionLimitExceededError(AIOSSHSessionError):
    """Maximum number of sessions reached."""


class AIOSSHSessionCorruptedError(AIOSSHSessionError):
    """Session data file is corrupted or tampered with."""


# ── Command Execution Errors ─────────────────────────────────────────────────

class AIOSSHCommandError(AIOSSHException):
    """Base class for command execution errors.

    Attributes:
        command: The command that was being executed.
        exit_code: Exit code from the remote process, if available.
    """

    def __init__(
        self,
        message: str,
        *,
        command: str = "",
        exit_code: Optional[int] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.command = command
        self.exit_code = exit_code

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        base["command"] = self.command[:500]
        base["exit_code"] = self.exit_code
        return base


class AIOSSHCommandTimeoutError(AIOSSHCommandError):
    """Command execution timed out."""


class AIOSSHCommandNotFoundError(AIOSSHCommandError):
    """Command not found on the remote system."""


class AIOSSHCommandPermissionError(AIOSSHCommandError):
    """Permission denied while executing command."""


# ── File Transfer Errors ─────────────────────────────────────────────────────

class AIOSSHFileTransferError(AIOSSHException):
    """Base class for file transfer errors."""


class AIOSSHFileTransferNotFoundError(AIOSSHFileTransferError):
    """File not found during transfer operation."""


class AIOSSHFileUploadError(AIOSSHFileTransferError):
    """File upload operation failed."""


class AIOSSHFileDownloadError(AIOSSHFileTransferError):
    """File download operation failed."""


class AIOSSHFilePermissionError(AIOSSHFileTransferError):
    """Permission denied for file operation."""


class AIOSSHFileDiskFullError(AIOSSHFileTransferError):
    """Insufficient disk space for file operation."""


class AIOSSHTransferInterruptedError(AIOSSHFileTransferError):
    """File transfer was interrupted."""


# ── Security Errors ──────────────────────────────────────────────────────────

class AIOSSHSecurityError(AIOSSHException):
    """Base class for security-related errors."""


class AIOSSHIntegrityError(AIOSSHSecurityError):
    """Data integrity verification failed."""


class AIOSSHRateLimitError(AIOSSHSecurityError):
    """Rate limit has been exceeded."""


class AIOSSHEncryptionError(AIOSSHSecurityError):
    """Encryption or decryption operation failed."""


class AIOSSHCertificateError(AIOSSHSecurityError):
    """SSL/TLS certificate validation failed."""


# ── Configuration Errors ─────────────────────────────────────────────────────

class AIOSSHConfigurationError(AIOSSHException):
    """Base class for configuration errors."""


class AIOSSHValidationError(AIOSSHConfigurationError):
    """Configuration validation failed."""


class AIOSSHInvalidParameterError(AIOSSHConfigurationError):
    """An invalid parameter value was provided."""


class AIOSSHMissingParameterError(AIOSSHConfigurationError):
    """A required parameter is missing."""


# ── Resource Errors ──────────────────────────────────────────────────────────

class AIOSSHResourceError(AIOSSHException):
    """Base class for resource management errors."""


class AIOSSHPoolExhaustedError(AIOSSHResourceError):
    """Connection pool has no available connections."""


class AIOSSHChannelExhaustedError(AIOSSHResourceError):
    """SSH channel limit has been reached."""


class AIOSSHMemoryError(AIOSSHResourceError):
    """Memory allocation failed."""


# ── Protocol Errors ──────────────────────────────────────────────────────────

class AIOSSHProtocolError(AIOSSHException):
    """SSH protocol violation or error."""


class AIOSSHNegotiationError(AIOSSHProtocolError):
    """SSH algorithm negotiation failed."""