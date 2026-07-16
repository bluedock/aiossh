"""
Session Module - v2.1 (v1.1.0)

Provides FastSSHSession with comprehensive error handling, concurrent command
execution, file transfer with space checks, streaming support with timeout,
and better resource management.
"""

from __future__ import annotations

import asyncio
import os
import socket
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator, Callable, Optional, Self, Union

import asyncssh
from asyncssh import SSHClientConnection, SSHCompletedProcess

from .exceptions import (
    AIOSSHAuthenticationError,
    AIOSSHCommandError,
    AIOSSHCommandTimeoutError,
    AIOSSHConnectionError,
    AIOSSHConnectionRefusedError,
    AIOSSHConnectionTimeoutError,
    AIOSSHFileDiskFullError,
    AIOSSHFileDownloadError,
    AIOSSHFileTransferNotFoundError,
    AIOSSHFileUploadError,
    AIOSSHHostKeyVerificationError,
    AIOSSHInvalidCredentialsError,
    AIOSSHInvalidParameterError,
    AIOSSHSessionError,
    AIOSSHSessionExpiredError,
)
from .security import AuditLogger, SecurityConfig
from .validators import InputValidator


@dataclass(frozen=True)
class SSHConfig:
    """Immutable SSH connection configuration."""

    host: str
    username: str
    port: int = 22
    password: Optional[str] = None
    private_key_path: Optional[str] = None
    timeout: int = 30
    keepalive_interval: int = 30
    security: SecurityConfig = field(default_factory=SecurityConfig)
    compression: bool = True
    host_key_callback: Optional[Callable[[str, int, object], bool]] = None
    proxy: Optional[str] = None  # ProxyCommand or jump host string for asyncssh

    def validate(self) -> None:
        InputValidator.validate_host(self.host)
        InputValidator.validate_port(self.port)
        InputValidator.validate_username(self.username)
        if self.password is not None:
            InputValidator.validate_password(self.password)
        if self.private_key_path is not None:
            InputValidator.validate_path(self.private_key_path)


class FastSSHSession:
    """High-performance async SSH session with improved streaming and safety."""

    def __init__(self, config: SSHConfig) -> None:
        config.validate()
        self.config = config
        self._connection: Optional[SSHClientConnection] = None
        self._created_at: Optional[datetime] = None
        self._last_used: Optional[datetime] = None
        self._closed: bool = False
        self._command_semaphore = asyncio.Semaphore(10)
        self._audit = AuditLogger()
        self._lock = asyncio.Lock()

        self._stats: dict[str, int] = {
            "commands_executed": 0,
            "bytes_transferred": 0,
            "errors": 0,
            "reconnects": 0,
        }

    @property
    def is_connected(self) -> bool:
        if self._closed:
            return False
        if self._connection is None:
            return False
        return not self._connection.is_closed()

    @property
    def connection(self) -> Optional["SSHClientConnection"]:
        """Underlying asyncssh connection (for advanced tunneling use)."""
        return self._connection

    @property
    def host(self) -> str:
        return self.config.host

    @property
    def stats(self) -> dict[str, object]:
        uptime = 0.0
        if self._created_at is not None:
            uptime = (datetime.now(timezone.utc) - self._created_at).total_seconds()
        return {
            **self._stats,
            "connected": self.is_connected,
            "uptime_seconds": round(uptime, 1),
            "host": self.config.host,
            "username": self.config.username,
        }

    async def __aenter__(self) -> Self:
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    async def connect(self) -> None:
        async with self._lock:
            if self.is_connected:
                return
            if self._closed:
                raise AIOSSHSessionExpiredError(
                    "Session has been permanently closed", code="SESSION_CLOSED"
                )

            try:
                connect_kwargs: dict[str, object] = {
                    "host": self.config.host,
                    "port": self.config.port,
                    "username": self.config.username,
                    "password": self.config.password,
                    "client_keys": [self.config.private_key_path] if self.config.private_key_path else None,
                    "known_hosts": self.config.host_key_callback or self._default_host_key_handler,
                    "keepalive_interval": self.config.keepalive_interval,
                    "connect_timeout": self.config.timeout,
                    "compression": self.config.compression,
                    "encryption_algs": list(self.config.security.allowed_ciphers),
                    "kex_algs": list(self.config.security.allowed_kex_algorithms),
                    "mac_algs": list(self.config.security.allowed_macs),
                    "proxy": self.config.proxy,
                }

                self._connection = await asyncio.wait_for(
                    asyncssh.connect(**connect_kwargs),  # type: ignore[arg-type]
                    timeout=self.config.timeout,
                )
                self._created_at = datetime.now(timezone.utc)
                self._last_used = datetime.now(timezone.utc)

                await self._audit.log(
                    "session_connect",
                    {"host": self.config.host, "username": self.config.username, "port": self.config.port},
                )
            except asyncio.TimeoutError as e:
                raise AIOSSHConnectionTimeoutError(
                    f"Connection timed out after {self.config.timeout}s",
                    code="TIMEOUT", details={"host": self.config.host}, cause=e
                ) from e
            except asyncssh.DisconnectError as e:
                raise AIOSSHConnectionRefusedError(
                    f"Server refused connection: {e}", code="DISCONNECTED",
                    details={"host": self.config.host}, cause=e
                ) from e
            except asyncssh.PermissionDenied as e:
                raise AIOSSHInvalidCredentialsError(
                    f"Authentication failed: {e}", code="AUTH_FAILED",
                    details={"host": self.config.host}, cause=e
                ) from e
            except asyncssh.HostKeyNotVerifiable as e:
                raise AIOSSHHostKeyVerificationError(
                    f"Host key not verifiable: {e}", code="HOST_KEY",
                    details={"host": self.config.host}, cause=e
                ) from e
            except socket.gaierror as e:
                raise AIOSSHConnectionError(
                    f"DNS resolution failed: {e}", code="DNS_ERROR",
                    details={"host": self.config.host}, cause=e
                ) from e
            except Exception as e:
                if isinstance(e, AIOSSHConnectionError):
                    raise
                raise AIOSSHConnectionError(
                    f"Connection failed: {e}", code="CONNECTION_ERROR",
                    details={"host": self.config.host}, cause=e
                ) from e

    @staticmethod
    def _default_host_key_handler(host: str, port: int, key: object) -> bool:
        """Default host key handler - accepts all (INSECURE for production).
        
        Override with strict verification in production environments to prevent MITM.
        """
        # In production, you should implement proper known_hosts or callback that verifies fingerprint
        return True

    async def execute(
        self,
        command: str,
        *,
        timeout: int = 30,
        sudo: bool = False,
        allow_dangerous: bool = False,
    ) -> dict[str, object]:
        if not self.is_connected:
            raise AIOSSHSessionExpiredError(
                "Cannot execute command: session not connected", code="SESSION_NOT_CONNECTED"
            )

        InputValidator.validate_command(command, allow_dangerous=allow_dangerous)

        if sudo:
            command = f"sudo -n {command}"

        async with self._command_semaphore:
            try:
                start_time = time.monotonic()
                result: SSHCompletedProcess = await asyncio.wait_for(
                    self._connection.run(command, check=False), timeout=timeout  # type: ignore[union-attr]
                )
                execution_time = time.monotonic() - start_time
                self._last_used = datetime.now(timezone.utc)
                self._stats["commands_executed"] += 1

                exit_code: Optional[int] = None
                try:
                    if result.exit_status is not None:
                        exit_code = int(result.exit_status)
                    elif hasattr(result, "returncode") and result.returncode is not None:
                        exit_code = int(result.returncode)
                except (TypeError, ValueError):
                    exit_code = None

                return {
                    "command": command,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "exit_code": exit_code,
                    "success": exit_code == 0 if exit_code is not None else False,
                    "execution_time": round(execution_time, 6),
                    "truncated": getattr(result, "stdout_was_truncated", False) or getattr(result, "stderr_was_truncated", False),
                }
            except asyncio.TimeoutError as e:
                self._stats["errors"] += 1
                raise AIOSSHCommandTimeoutError(
                    f"Command timed out after {timeout}s", code="CMD_TIMEOUT",
                    command=command[:200], cause=e
                ) from e
            except Exception as e:
                self._stats["errors"] += 1
                if isinstance(e, AIOSSHCommandError):
                    raise
                raise AIOSSHCommandError(
                    f"Command execution failed: {e}", code="CMD_ERROR",
                    command=command[:200], cause=e
                ) from e

    async def execute_batch(
        self, commands: list[str], *, parallel: bool = True, max_concurrent: int = 5, **kwargs
    ) -> list[dict[str, object]]:
        if not commands:
            return []
        if parallel:
            semaphore = asyncio.Semaphore(max_concurrent)
            async def _bounded_execute(cmd: str) -> dict[str, object]:
                async with semaphore:
                    try:
                        return await self.execute(cmd, **kwargs)
                    except Exception as e:
                        return {"command": cmd, "error": str(e), "success": False, "exit_code": -1}
            async with asyncio.TaskGroup() as tg:
                tasks = [tg.create_task(_bounded_execute(cmd)) for cmd in commands]
            return [t.result() for t in tasks]
        else:
            results = []
            for cmd in commands:
                try:
                    results.append(await self.execute(cmd, **kwargs))
                except Exception as e:
                    results.append({"command": cmd, "error": str(e), "success": False, "exit_code": -1})
            return results

    async def upload_file(
        self, local_path: str, remote_path: str, *, check_disk_space: bool = True
    ) -> dict[str, object]:
        if not self.is_connected:
            raise AIOSSHSessionExpiredError("Cannot upload: session not connected", code="SESSION_NOT_CONNECTED")

        local_path = InputValidator.validate_path(local_path)
        remote_path = InputValidator.validate_path(remote_path)

        local_file = Path(local_path).expanduser()
        if not local_file.exists() or not local_file.is_file():
            raise AIOSSHFileTransferNotFoundError(f"Local file not found or not regular: {local_path}", code="LOCAL_NOT_FOUND")

        file_size = local_file.stat().st_size
        start_time = time.monotonic()

        try:
            async with self._connection.start_sftp_client() as sftp:  # type: ignore[union-attr]
                if check_disk_space:
                    try:
                        remote_dir = str(Path(remote_path).parent)
                        vfs = await sftp.statvfs(remote_dir)
                        available = vfs.f_bfree * vfs.f_frsize
                        if available < file_size:
                            raise AIOSSHFileDiskFullError(
                                f"Insufficient remote disk space", code="DISK_FULL",
                                details={"needed": file_size, "available": available}
                            )
                    except AIOSSHFileDiskFullError:
                        raise
                    except Exception:
                        pass  # proceed if check fails
                await sftp.put(str(local_file), remote_path)
        except asyncssh.SFTPError as e:
            raise AIOSSHFileUploadError(f"SFTP upload failed: {e}", code="SFTP_ERROR", cause=e) from e
        except Exception as e:
            if isinstance(e, AIOSSHFileUploadError):
                raise
            raise AIOSSHFileUploadError(f"Upload failed: {e}", code="UPLOAD_ERROR", cause=e) from e

        elapsed = time.monotonic() - start_time
        self._stats["bytes_transferred"] += file_size
        return {
            "success": True, "local_path": str(local_file), "remote_path": remote_path,
            "file_size": file_size, "transfer_time": round(elapsed, 3),
            "speed_mbps": round((file_size / 1_000_000) / elapsed, 3) if elapsed > 0 else 0.0,
        }

    async def download_file(
        self, remote_path: str, local_path: str, *, resume: bool = False
    ) -> dict[str, object]:
        if not self.is_connected:
            raise AIOSSHSessionExpiredError("Cannot download: session not connected", code="SESSION_NOT_CONNECTED")

        remote_path = InputValidator.validate_path(remote_path)
        local_path = InputValidator.validate_path(local_path)

        local_file = Path(local_path).expanduser()
        local_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            async with self._connection.start_sftp_client() as sftp:  # type: ignore[union-attr]
                try:
                    stat = await sftp.stat(remote_path)
                    remote_size = stat.size or 0
                except asyncssh.SFTPError as e:
                    raise AIOSSHFileTransferNotFoundError(f"Remote file not found: {remote_path}", code="REMOTE_NOT_FOUND", cause=e) from e

                offset = 0
                if resume and local_file.exists():
                    offset = local_file.stat().st_size
                    if offset >= remote_size:
                        return {"success": True, "message": "File already fully downloaded", "file_size": remote_size}

                start_time = time.monotonic()
                await sftp.get(remote_path, str(local_file), resume_offset=offset)
                elapsed = time.monotonic() - start_time
                self._stats["bytes_transferred"] += remote_size
                return {
                    "success": True, "remote_path": remote_path, "local_path": str(local_file),
                    "file_size": remote_size, "transfer_time": round(elapsed, 3),
                    "speed_mbps": round((remote_size / 1_000_000) / elapsed, 3) if elapsed > 0 else 0.0,
                    "resumed": offset > 0,
                }
        except AIOSSHFileTransferNotFoundError:
            raise
        except asyncssh.SFTPError as e:
            raise AIOSSHFileDownloadError(f"SFTP download failed: {e}", code="SFTP_ERROR", cause=e) from e
        except Exception as e:
            raise AIOSSHFileDownloadError(f"Download failed: {e}", code="DOWNLOAD_ERROR", cause=e) from e

    async def stream_command(self, command: str, timeout: int = 300) -> AsyncIterator[str]:
        """Execute a command and stream stdout line by line with timeout protection."""
        if not self.is_connected:
            raise AIOSSHSessionExpiredError("Cannot stream: session not connected", code="SESSION_NOT_CONNECTED")

        InputValidator.validate_command(command)

        try:
            async with asyncio.timeout(timeout):  # Python 3.11+ timeout context
                async with self._connection.create_process(command) as process:  # type: ignore[union-attr]
                    async for line in process.stdout:
                        yield line.rstrip("\n")
        except asyncio.TimeoutError as e:
            raise AIOSSHCommandTimeoutError(
                f"Stream command timed out after {timeout}s", code="STREAM_TIMEOUT",
                command=command[:200], cause=e
            ) from e
        except Exception as e:
            raise AIOSSHCommandError(f"Command streaming failed: {e}", code="STREAM_ERROR", command=command[:200], cause=e) from e

    async def close(self) -> None:
        async with self._lock:
            if self._closed:
                return
            self._closed = True
            if self._connection is not None and not self._connection.is_closed():
                try:
                    self._connection.close()
                    await asyncio.wait_for(self._connection.wait_closed(), timeout=5.0)
                except asyncio.TimeoutError:
                    try:
                        self._connection.abort()
                    except Exception:
                        pass
                except Exception:
                    pass
                finally:
                    self._connection = None
            await self._audit.log("session_close", {"host": self.config.host, "stats": self._stats})
