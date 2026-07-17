"""
AIOSSH

Asynchronous SSH client library for Python.
"""

from __future__ import annotations

__version__ = "1.1.2"

_lazy_imports = {
    "AIOSSH": (".core", "AIOSSH"),
    "FastSSHSession": (".session", "FastSSHSession"),
    "SSHConfig": (".session", "SSHConfig"),
    "ConnectionPool": (".pool", "ConnectionPool"),
    "PoolConfig": (".pool", "PoolConfig"),
    "SecurityConfig": (".security", "SecurityConfig"),
    "RateLimiter": (".security", "RateLimiter"),
    "SecureChannel": (".security", "SecureChannel"),
    "SecureMemory": (".security", "SecureMemory"),
    "AuditLogger": (".security", "AuditLogger"),
    "InputValidator": (".validators", "InputValidator"),
    "SessionFileManager": (".file_manager", "SessionFileManager"),
    "ProxyConfig": (".proxy", "ProxyConfig"),
    "SSHTunnelManager": (".proxy", "SSHTunnelManager"),
    "create_tunnel": (".proxy", "create_tunnel"),
    "WebhookManager": (".webhook", "WebhookManager"),
    "DiscordWebhook": (".webhook", "DiscordWebhook"),
    "TelegramWebhook": (".webhook", "TelegramWebhook"),
    "DockerExecSession": (".docker_exec", "DockerExecSession"),
    "SessionRecorder": (".session_replay", "SessionRecorder"),
    "SessionReplayer": (".session_replay", "SessionReplayer"),
    "ParallelSCP": (".scp_speed", "ParallelSCP"),
    "TransferProgress": (".scp_speed", "TransferProgress"),
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
    AIOSSHProxyError,
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
    "AIOSSHProxyError",
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
