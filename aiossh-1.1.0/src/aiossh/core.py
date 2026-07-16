"""
Core AIOSSH Client - v1.1.0 (simplified high-level facade)

For full implementation see the complete modules. This provides the main
AIOSSH class with connection pooling, rate limiting, and session management.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Optional, Self, Union

from .pool import ConnectionPool, PoolConfig
from .security import AuditLogger, RateLimiter, SecurityConfig
from .session import FastSSHSession, SSHConfig
from .validators import InputValidator
from .file_manager import SessionFileManager  # type: ignore
from .exceptions import (
    AIOSSHConfigurationError,
    AIOSSHInvalidParameterError,
    AIOSSHRateLimitError,
    AIOSSHSessionError,
)


class AIOSSH:
    """Main high-level async SSH client (v1.1.0)."""

    def __init__(
        self,
        *,
        master_password: Optional[str] = None,
        security_config: Optional[SecurityConfig] = None,
        pool_config: Optional[PoolConfig] = None,
        session_dir: str = "~/.aiossh/sessions",
        enable_audit: bool = True,
    ) -> None:
        if master_password is not None and len(master_password) < 12:
            raise AIOSSHInvalidParameterError(
                "Master password must be at least 12 characters",
                code="WEAK_MASTER_PASSWORD",
            )
        self._security_config = security_config or SecurityConfig()
        self._pool_config = pool_config or PoolConfig()
        self._session_manager = SessionFileManager(session_dir) if master_password else None
        self._master_password = master_password
        self._audit = AuditLogger() if enable_audit else None
        self._pool = ConnectionPool(self._pool_config)
        self._conn_rate_limiter = RateLimiter(max_requests=30, window_seconds=60)
        self._cmd_rate_limiter = RateLimiter(max_requests=50, window_seconds=1)
        self._active_sessions: dict[str, FastSSHSession] = {}
        self._lock = asyncio.Lock()
        self._closed = False

    async def __aenter__(self) -> Self:
        await self._pool.start()
        return self

    async def __aexit__(self, *args) -> None:
        await self.close_all()

    async def connect(
        self,
        host: str,
        username: str,
        *,
        password: Optional[str] = None,
        port: int = 22,
        private_key_path: Optional[str] = None,
        session_name: Optional[str] = None,
        use_pool: bool = True,
        timeout: int = 30,
    ) -> FastSSHSession:
        if self._closed:
            raise AIOSSHSessionError("Client closed", code="CLIENT_CLOSED")
        if not await self._conn_rate_limiter.acquire():
            raise AIOSSHRateLimitError("Connection rate limit exceeded", code="RATE_LIMIT")

        host = InputValidator.validate_host(host)
        port = InputValidator.validate_port(port)
        username = InputValidator.validate_username(username)
        if password:
            password = InputValidator.validate_password(password)

        config = SSHConfig(
            host=host, port=port, username=username, password=password,
            private_key_path=private_key_path, timeout=timeout,
            security=self._security_config
        )

        if use_pool:
            try:
                session = await self._pool.get_connection(config)
            except Exception:
                session = FastSSHSession(config)
                await session.connect()
        else:
            session = FastSSHSession(config)
            await session.connect()

        if session_name:
            async with self._lock:
                self._active_sessions[session_name] = session
        return session

    async def execute_command(
        self,
        session_id: Union[str, FastSSHSession],
        command: str,
        *,
        timeout: int = 30,
        sudo: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if not await self._cmd_rate_limiter.acquire():
            raise AIOSSHRateLimitError("Command rate limit exceeded", code="CMD_RATE_LIMIT")
        session = await self._resolve_session(session_id)
        return await session.execute(command, timeout=timeout, sudo=sudo, **kwargs)

    async def execute_on_all(self, command: str, **kwargs: Any) -> dict[str, dict[str, Any]]:
        async with self._lock:
            names = list(self._active_sessions.keys())
        results: dict[str, dict[str, Any]] = {}
        for name in names:
            try:
                results[name] = await self.execute_command(name, command, **kwargs)
            except Exception as e:
                results[name] = {"error": str(e), "success": False}
        return results

    async def close_session(self, session_id: Union[str, FastSSHSession]) -> None:
        async with self._lock:
            if isinstance(session_id, str):
                session = self._active_sessions.pop(session_id, None)
            else:
                session = session_id
                for k, v in list(self._active_sessions.items()):
                    if v is session:
                        del self._active_sessions[k]
                        break
        if session:
            await session.close()

    async def close_all(self) -> None:
        if self._closed:
            return
        self._closed = True
        async with self._lock:
            sessions = list(self._active_sessions.values())
            self._active_sessions.clear()
        for s in sessions:
            try:
                await s.close()
            except Exception:
                pass
        await self._pool.close()

    async def _resolve_session(self, sid: Union[str, FastSSHSession]) -> FastSSHSession:
        if isinstance(sid, FastSSHSession):
            return sid
        async with self._lock:
            if sid in self._active_sessions:
                return self._active_sessions[sid]
        raise AIOSSHSessionError(f"Session '{sid}' not found", code="SESSION_NOT_FOUND")

    # Session file helpers (require master_password)
    async def save_session_to_file(self, session_name: str, host: str, username: str, password: str, port: int = 22) -> None:
        if self._session_manager is None:
            raise AIOSSHConfigurationError("No master_password provided at init", code="NO_SESSION_MANAGER")
        self._session_manager.create_session_file(
            session_name, {"host": host, "username": username, "password": password, "port": port}, self._master_password  # type: ignore
        )

    async def load_session_from_file(self, session_name: str) -> FastSSHSession:
        if self._session_manager is None:
            raise AIOSSHConfigurationError("No master_password provided at init", code="NO_SESSION_MANAGER")
        creds = self._session_manager.load_session_file(session_name, self._master_password)  # type: ignore
        return await self.connect(creds["host"], creds["username"], password=creds.get("password"), port=creds.get("port", 22), session_name=session_name)

    def list_saved_sessions(self) -> list[str]:
        if self._session_manager is None:
            return []
        return self._session_manager.list_sessions()

    def list_active_sessions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": name,
                "host": session.host,
                "connected": session.is_connected,
            }
            for name, session in self._active_sessions.items()
        ]
