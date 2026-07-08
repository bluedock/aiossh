"""
AIOSSH - Async SSH Client Library for Python

A comprehensive asynchronous SSH client built on asyncssh, providing connection
pooling, secure credential management, input validation, rate limiting, audit
logging, tunneling (SOCKS5, local/remote port forwarding), plugin system,
command queuing, webhooks, Telnet support, Docker and Kubernetes exec,
parallel file transfers, and session recording/replay.

Version: 1.0.0
"""

from __future__ import annotations

from .core import AIOSSH
from .session import FastSSHSession, SSHConfig
from .pool import ConnectionPool, PoolConfig
from .security import AuditLogger, RateLimiter, SecureChannel, SecureMemory, SecurityConfig
from .validators import InputValidator
from .file_manager import SessionFileManager
from .plugin import PluginManager, BasePlugin, CommandContext, ConnectionContext
from .proxy import ProxyConfig, SSHTunnelManager, create_tunnel
from .queue_manager import CommandQueue, QueuedCommand
from .webhook import WebhookManager, DiscordWebhook, TelegramWebhook
from .telnet import TelnetSession
from .kubernetes_exec import KubeExecSession, KubeExecManager
from .docker_exec import DockerExecSession
from .logging_handler import (
    LogManager,
    FileLogHandler,
    ElasticsearchHandler,
    LokiHandler,
    DatadogHandler,
    SyslogHandler,
)
from .session_replay import SessionRecorder, SessionReplayer
from .scp_speed import ParallelSCP, TransferProgress

from .exceptions import (
    AIOSSHException,
    AIOSSHConnectionError,
    AIOSSHConnectionTimeoutError,
    AIOSSHConnectionRefusedError,
    AIOSSHHostKeyVerificationError,
    AIOSSHAuthenticationError,
    AIOSSHInvalidCredentialsError,
    AIOSSHSessionError,
    AIOSSHSessionExpiredError,
    AIOSSHSessionNotFoundError,
    AIOSSHCommandError,
    AIOSSHCommandTimeoutError,
    AIOSSHFileTransferError,
    AIOSSHFileTransferNotFoundError,
    AIOSSHFileUploadError,
    AIOSSHFileDownloadError,
    AIOSSHSecurityError,
    AIOSSHIntegrityError,
    AIOSSHRateLimitError,
    AIOSSHConfigurationError,
    AIOSSHValidationError,
    AIOSSHInvalidParameterError,
    AIOSSHPoolExhaustedError,
)

__version__ = "1.0.0"

__all__ = [
    # Core
    "AIOSSH",
    "FastSSHSession",
    "SSHConfig",
    # Pool
    "ConnectionPool",
    "PoolConfig",
    # Security
    "SecurityConfig",
    "RateLimiter",
    "SecureChannel",
    "SecureMemory",
    "AuditLogger",
    # Utilities
    "InputValidator",
    "SessionFileManager",
    # Plugin
    "PluginManager",
    "BasePlugin",
    "CommandContext",
    "ConnectionContext",
    # Proxy & Tunneling (VPN over SSH, SOCKS, Port Forwarding)
    "ProxyConfig",
    "SSHTunnelManager",
    "create_tunnel",
    # Queue
    "CommandQueue",
    "QueuedCommand",
    # Webhook
    "WebhookManager",
    "DiscordWebhook",
    "TelegramWebhook",
    # Telnet
    "TelnetSession",
    # Kubernetes
    "KubeExecSession",
    "KubeExecManager",
    # Docker
    "DockerExecSession",
    # Logging
    "LogManager",
    "FileLogHandler",
    "ElasticsearchHandler",
    "LokiHandler",
    "DatadogHandler",
    "SyslogHandler",
    # Session Replay
    "SessionRecorder",
    "SessionReplayer",
    # SCP
    "ParallelSCP",
    "TransferProgress",
    # Exceptions
    "AIOSSHException",
    "AIOSSHConnectionError",
    "AIOSSHConnectionTimeoutError",
    "AIOSSHConnectionRefusedError",
    "AIOSSHHostKeyVerificationError",
    "AIOSSHAuthenticationError",
    "AIOSSHInvalidCredentialsError",
    "AIOSSHSessionError",
    "AIOSSHSessionExpiredError",
    "AIOSSHSessionNotFoundError",
    "AIOSSHCommandError",
    "AIOSSHCommandTimeoutError",
    "AIOSSHFileTransferError",
    "AIOSSHFileTransferNotFoundError",
    "AIOSSHFileUploadError",
    "AIOSSHFileDownloadError",
    "AIOSSHSecurityError",
    "AIOSSHIntegrityError",
    "AIOSSHRateLimitError",
    "AIOSSHConfigurationError",
    "AIOSSHValidationError",
    "AIOSSHInvalidParameterError",
    "AIOSSHPoolExhaustedError",
]