"""
AIOSSH

Asynchronous SSH client library for Python.
"""

from __future__ import annotations

__version__ = "1.1.3"

_lazy_imports = {
    "AIOSSH": (".core", "AIOSSH"),
    "FastSSHSession": (".core", "FastSSHSession"),
    "SSHConfig": (".core", "SSHConfig"),
    "ConnectionPool": (".core", "ConnectionPool"),
    "PoolConfig": (".core", "PoolConfig"),
    "SecurityConfig": (".security", "SecurityConfig"),
    "RateLimiter": (".security", "RateLimiter"),
    "SecureChannel": (".security", "SecureChannel"),
    "SecureMemory": (".security", "SecureMemory"),
    "AuditLogger": (".security", "AuditLogger"),
    "InputValidator": (".security", "InputValidator"),
    "SessionFileManager": (".security", "SessionFileManager"),
    "ProxyConfig": (".integrations", "ProxyConfig"),
    "SSHTunnelManager": (".integrations", "SSHTunnelManager"),
    "create_tunnel": (".integrations", "create_tunnel"),
    "WebhookManager": (".integrations", "WebhookManager"),
    "DiscordWebhook": (".integrations", "DiscordWebhook"),
    "TelegramWebhook": (".integrations", "TelegramWebhook"),
    "DockerExecSession": (".integrations", "DockerExecSession"),
    "SessionRecorder": (".integrations", "SessionRecorder"),
    "SessionReplayer": (".integrations", "SessionReplayer"),
    "ParallelSCP": (".transfer", "ParallelSCP"),
    "TransferProgress": (".transfer", "TransferProgress"),
}

from .exceptions import (
    AIOSSHException, AIOSSHConnectionError, AIOSSHConnectionTimeoutError,
    AIOSSHConnectionRefusedError, AIOSSHHostKeyVerificationError,
    AIOSSHAuthenticationError, AIOSSHInvalidCredentialsError,
    AIOSSHSessionError, AIOSSHSessionExpiredError, AIOSSHSessionNotFoundError,
    AIOSSHCommandError, AIOSSHCommandTimeoutError,
    AIOSSHFileTransferError, AIOSSHFileTransferNotFoundError,
    AIOSSHFileUploadError, AIOSSHFileDownloadError,
    AIOSSHSecurityError, AIOSSHIntegrityError, AIOSSHRateLimitError,
    AIOSSHConfigurationError, AIOSSHValidationError, AIOSSHInvalidParameterError,
    AIOSSHPoolExhaustedError, AIOSSHEncryptionError, AIOSSHSessionCorruptedError,
    AIOSSHProxyError, AIOSSHFileDiskFullError, AIOSSHPluginError,
)

__all__ = [
    "__version__", "AIOSSH", "FastSSHSession", "SSHConfig",
    "ConnectionPool", "PoolConfig",
    "SecurityConfig", "RateLimiter", "SecureChannel", "SecureMemory", "AuditLogger",
    "InputValidator", "SessionFileManager",
    "ProxyConfig", "SSHTunnelManager", "create_tunnel",
    "WebhookManager", "DiscordWebhook", "TelegramWebhook",
    "DockerExecSession", "SessionRecorder", "SessionReplayer",
    "ParallelSCP", "TransferProgress",
    "AIOSSHException", "AIOSSHConnectionError", "AIOSSHConnectionTimeoutError",
    "AIOSSHConnectionRefusedError", "AIOSSHHostKeyVerificationError",
    "AIOSSHAuthenticationError", "AIOSSHInvalidCredentialsError",
    "AIOSSHSessionError", "AIOSSHSessionExpiredError", "AIOSSHSessionNotFoundError",
    "AIOSSHCommandError", "AIOSSHCommandTimeoutError",
    "AIOSSHFileTransferError", "AIOSSHFileTransferNotFoundError",
    "AIOSSHFileUploadError", "AIOSSHFileDownloadError",
    "AIOSSHSecurityError", "AIOSSHIntegrityError", "AIOSSHRateLimitError",
    "AIOSSHConfigurationError", "AIOSSHValidationError", "AIOSSHInvalidParameterError",
    "AIOSSHPoolExhaustedError", "AIOSSHEncryptionError", "AIOSSHSessionCorruptedError",
    "AIOSSHProxyError", "AIOSSHFileDiskFullError", "AIOSSHPluginError",
]


def __getattr__(name: str):
    if name in _lazy_imports:
        module_path, attr_name = _lazy_imports[name]
        import importlib
        module = importlib.import_module(module_path, package=__name__)
        value = getattr(module, attr_name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(set(globals()) | set(__all__))
