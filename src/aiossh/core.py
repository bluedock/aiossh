"""
Core Client Module - v2.0

Main AIOSSH client providing the primary API for:
- Creating and managing SSH sessions
- Executing commands across multiple servers
- Managing encrypted session storage
- Rate limiting and audit logging
"""

from __future__ import annotations

import asyncio
import signal
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional, Self, Union

from .decorators import retry, timing
from .exceptions import (
    AIOSSHConfigurationError,
    AIOSSHConnectionError,
    AIOSSHInvalidParameterError,
    AIOSSHPoolExhaustedError,
    AIOSSHRateLimitError,
    AIOSSHSessionError,
    AIOSSHSessionExpiredError,
    AIOSSHSessionNotFoundError,
)
from .file_manager import SessionFileManager
from .pool import ConnectionPool, PoolConfig
from .security import AuditLogger, RateLimiter, SecurityConfig
from .session import FastSSHSession, SSHConfig
from .validators import InputValidator


class AIOSSH:
    """Production-ready async SSH client.

    Provides secure connection management, encrypted session storage,
    rate limiting, and comprehensive error handling.

    Example:
        async with AIOSSH(master_password="strong-password") as client:
            session = await client.connect(
                "server.example.com", "admin", password="secret"
            )
            result = await client.execute_command(session, "uptime")
            print(result["stdout"])
    """

    def __init__(
        self,
        *,
        master_password: Optional[str] = None,
        security_config: Optional[SecurityConfig] = None,
        pool_config: Optional[PoolConfig] = None,
        session_dir: str = "~/.aiossh/sessions",
        enable_audit: bool = True,
    ) -> None:
        """Initialize the AIOSSH client.

        Args:
            master_password: Password for encrypting session files (optional).
            security_config: Security configuration.
            pool_config: Connection pool configuration.
            session_dir: Directory for storing session files.
            enable_audit: Enable audit logging.

        Raises:
            AIOSSHInvalidParameterError: If master_password is too short.
        """
        if master_password is not None and len(master_password) < 12:
            raise AIOSSHInvalidParameterError(
                "Master password must be at least 12 characters for security",
                code="WEAK_MASTER_PASSWORD",
            )

        self._security_config = security_config or SecurityConfig()
        self._pool_config = pool_config or PoolConfig()

        self._session_manager: Optional[SessionFileManager] = None
        if master_password is not None:
            self._session_manager = SessionFileManager(session_dir)

        self._master_password = master_password
        self._audit = AuditLogger() if enable_audit else None

        # Core components
        self._pool = ConnectionPool(self._pool_config)
        self._connection_rate_limiter = RateLimiter(
            max_requests=self._security_config.max_connections_per_minute,
            window_seconds=60.0,
            burst_multiplier=2,
        )
        self._command_rate_limiter = RateLimiter(
            max_requests=self._security_config.max_commands_per_second,
            window_seconds=1.0,
            burst_multiplier=2,
        )

        # Session registry
        self._active_sessions: dict[str, FastSSHSession] = {}
        self._lock = asyncio.Lock()
        self._closed = False

        # Register signal handlers
        self._register_signal_handlers()

    def _register_signal_handlers(self) -> None:
        """Register graceful shutdown on SIGINT/SIGTERM."""
        try:
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(
                    sig,
                    lambda s=sig: asyncio.ensure_future(self._handle_signal(s)),
                )
        except (NotImplementedError, RuntimeError):
            pass  # Windows or no event loop

    async def _handle_signal(self, sig: signal.Signals) -> None:
        """Handle shutdown signal."""
        await self.close_all()

    async def __aenter__(self) -> Self:
        await self._pool.start()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[object],
    ) -> None:
        await self.close_all()

    @timing
    @retry(max_retries=3, exceptions=(AIOSSHConnectionError,))
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
        """Connect to a remote server.

        Args:
            host: Remote hostname or IP address.
            username: SSH username.
            password: SSH password.
            port: SSH port (default 22).
            private_key_path: Path to private key file.
            session_name: Name for this session (for later reference).
            use_pool: Use connection pooling if True.
            timeout: Connection timeout in seconds.

        Returns:
            A connected FastSSHSession.

        Raises:
            AIOSSHRateLimitError: If connection rate limit exceeded.
            AIOSSHSessionError: If client is closed.
        """
        if self._closed:
            raise AIOSSHSessionError(
                "Client has been closed",
                code="CLIENT_CLOSED",
            )

        # Rate limiting
        if not await self._connection_rate_limiter.acquire():
            raise AIOSSHRateLimitError(
                "Connection rate limit exceeded",
                code="RATE_LIMIT",
            )

        # Validate inputs
        host = InputValidator.validate_host(host)
        port = InputValidator.validate_port(port)
        username = InputValidator.validate_username(username)
        if password is not None:
            password = InputValidator.validate_password(password)
        if session_name is not None:
            session_name = InputValidator.validate_session_name(session_name)

        # Create config
        config = SSHConfig(
            host=host,
            port=port,
            username=username,
            password=password,
            private_key_path=private_key_path,
            timeout=timeout,
            security=self._security_config,
        )

        # Get or create session
        if use_pool:
            try:
                session = await self._pool.get_connection(config)
            except AIOSSHPoolExhaustedError:
                # Fall back to direct connection
                session = FastSSHSession(config)
                await session.connect()
        else:
            session = FastSSHSession(config)
            await session.connect()

        # Register session
        if session_name is not None:
            async with self._lock:
                self._active_sessions[session_name] = session

        if self._audit is not None:
            await self._audit.log(
                "connection_created",
                {
                    "host": host,
                    "username": username,
                    "session_name": session_name,
                    "use_pool": use_pool,
                },
            )

        return session

    async def execute_command(
        self,
        session_id: Union[str, FastSSHSession],
        command: str,
        *,
        timeout: int = 30,
        sudo: bool = False,
        **kwargs: object,
    ) -> dict[str, object]:
        """Execute a command on a session with rate limiting.

        Args:
            session_id: Session name or FastSSHSession object.
            command: Command to execute.
            timeout: Command timeout in seconds.
            sudo: Prefix with sudo if True.
            **kwargs: Additional arguments passed to session.execute().

        Returns:
            Command result dictionary.

        Raises:
            AIOSSHRateLimitError: If command rate limit exceeded.
        """
        if not await self._command_rate_limiter.acquire():
            raise AIOSSHRateLimitError(
                "Command rate limit exceeded",
                code="CMD_RATE_LIMIT",
            )

        session = await self._resolve_session(session_id)
        return await session.execute(
            command,
            timeout=timeout,
            sudo=sudo,
            **kwargs,  # type: ignore[arg-type]
        )

    async def execute_on_multiple(
        self,
        commands: Union[str, list[str]],
        sessions: Optional[list[Union[str, FastSSHSession]]] = None,
        *,
        parallel: bool = True,
        **kwargs: object,
    ) -> dict[str, dict[str, object]]:
        """Execute commands on multiple sessions.

        Args:
            commands: Single command or list of commands.
            sessions: List of sessions to execute on (default: all active).
            parallel: Execute in parallel if True.
            **kwargs: Additional arguments for execute().

        Returns:
            Dictionary mapping session names to results.
        """
        if sessions is None:
            async with self._lock:
                sessions = list(self._active_sessions.keys())  # type: ignore[assignment]

        if isinstance(commands, str):
            commands = [commands] * len(sessions)

        if len(commands) != len(sessions):
            raise AIOSSHInvalidParameterError(
                f"Commands count ({len(commands)}) must match "
                f"sessions count ({len(sessions)})",
                code="COUNT_MISMATCH",
            )

        results: dict[str, dict[str, object]] = {}

        if parallel:
            async def _execute_one(
                sid: Union[str, FastSSHSession],
                cmd: str,
            ) -> tuple[str, dict[str, object]]:
                try:
                    result = await self.execute_command(
                        sid, cmd, **kwargs  # type: ignore[arg-type]
                    )
                    return str(sid), result
                except Exception as e:
                    return str(sid), {"error": str(e), "success": False}

            async with asyncio.TaskGroup() as tg:
                tasks = [
                    tg.create_task(_execute_one(sid, cmd))
                    for sid, cmd in zip(sessions, commands)
                ]

            for task in tasks:
                sid, result = task.result()
                results[sid] = result
        else:
            for sid, cmd in zip(sessions, commands):
                try:
                    results[str(sid)] = await self.execute_command(
                        sid, cmd, **kwargs  # type: ignore[arg-type]
                    )
                except Exception as e:
                    results[str(sid)] = {"error": str(e), "success": False}

        return results

    async def execute_on_all(
        self,
        command: str,
        **kwargs: object,
    ) -> dict[str, dict[str, object]]:
        """Execute a command on all active sessions.

        Args:
            command: Command to execute.
            **kwargs: Additional arguments for execute().

        Returns:
            Dictionary mapping session names to results.
        """
        async with self._lock:
            session_names = list(self._active_sessions.keys())

        return await self.execute_on_multiple(
            commands=command,
            sessions=session_names,  # type: ignore[arg-type]
            **kwargs,
        )

    @asynccontextmanager
    async def temporary_session(
        self,
        host: str,
        username: str,
        *,
        password: Optional[str] = None,
        port: int = 22,
        **kwargs: object,
    ) -> AsyncIterator[FastSSHSession]:
        """Context manager for temporary connections with guaranteed cleanup.

        Args:
            host: Remote hostname or IP.
            username: SSH username.
            password: SSH password.
            port: SSH port.
            **kwargs: Additional arguments for connect().

        Yields:
            A connected FastSSHSession.
        """
        session = None
        try:
            session = await self.connect(
                host=host,
                username=username,
                password=password,
                port=port,
                use_pool=False,
                **kwargs,  # type: ignore[arg-type]
            )
            yield session
        finally:
            if session is not None:
                try:
                    await session.close()
                except Exception:
                    pass

    async def save_session_to_file(
        self,
        session_name: str,
        host: str,
        username: str,
        password: str,
        *,
        port: int = 22,
    ) -> None:
        """Save encrypted session credentials to a file.

        Args:
            session_name: Name for the saved session.
            host: Remote host.
            username: SSH username.
            password: SSH password.
            port: SSH port.

        Raises:
            AIOSSHConfigurationError: If session manager not available.
        """
        if self._session_manager is None:
            raise AIOSSHConfigurationError(
                "Session file manager not available. "
                "Provide master_password when creating AIOSSH.",
                code="NO_SESSION_MANAGER",
            )

        session_name = InputValidator.validate_session_name(session_name)

        self._session_manager.create_session_file(
            filename=session_name,
            credentials={
                "host": host,
                "username": username,
                "password": password,
                "port": port,
                "version": "2.0",
            },
            master_password=self._master_password,  # type: ignore[arg-type]
        )

    async def load_session_from_file(
        self,
        session_name: str,
    ) -> FastSSHSession:
        """Load and connect using saved session credentials.

        Args:
            session_name: Name of the saved session.

        Returns:
            A connected FastSSHSession.

        Raises:
            AIOSSHConfigurationError: If session manager not available.
        """
        if self._session_manager is None:
            raise AIOSSHConfigurationError(
                "Session file manager not available. "
                "Provide master_password when creating AIOSSH.",
                code="NO_SESSION_MANAGER",
            )

        session_name = InputValidator.validate_session_name(session_name)

        creds = self._session_manager.load_session_file(
            filename=session_name,
            master_password=self._master_password,  # type: ignore[arg-type]
        )

        return await self.connect(
            host=creds["host"],
            username=creds["username"],
            password=creds.get("password", ""),
            port=creds.get("port", 22),
            session_name=session_name,
        )

    def list_saved_sessions(self) -> list[str]:
        """List all saved session names.

        Returns:
            List of session names.
        """
        if self._session_manager is None:
            return []
        return self._session_manager.list_sessions()

    def list_active_sessions(self) -> list[dict[str, object]]:
        """List all active sessions with their status.

        Returns:
            List of session information dictionaries.
        """
        return [
            {
                "name": name,
                "host": session.host,
                "connected": session.is_connected,
                "stats": session.stats,
            }
            for name, session in self._active_sessions.items()
        ]

    async def close_session(
        self,
        session_id: Union[str, FastSSHSession],
    ) -> None:
        """Close a specific session.

        Args:
            session_id: Session name or session object.
        """
        async with self._lock:
            if isinstance(session_id, str):
                session = self._active_sessions.pop(session_id, None)
            else:
                session = session_id
                for name, s in list(self._active_sessions.items()):
                    if s is session:
                        del self._active_sessions[name]
                        break

        if session is not None:
            try:
                await session.close()
            except Exception:
                pass

    async def close_all(self) -> None:
        """Close all sessions and release all resources."""
        if self._closed:
            return

        self._closed = True

        # Close all active sessions
        async with self._lock:
            sessions = list(self._active_sessions.values())
            self._active_sessions.clear()

        for session in sessions:
            try:
                await session.close()
            except Exception:
                pass

        # Close connection pool
        try:
            await self._pool.close()
        except Exception:
            pass

        if self._audit is not None:
            await self._audit.log(
                "client_shutdown",
                {"sessions_closed": len(sessions)},
            )

    async def _resolve_session(
        self,
        session_id: Union[str, FastSSHSession],
    ) -> FastSSHSession:
        """Resolve a session identifier to a session object.

        Args:
            session_id: Session name or session object.

        Returns:
            The resolved FastSSHSession.

        Raises:
            AIOSSHSessionNotFoundError: If session name not found.
            AIOSSHSessionExpiredError: If session is not connected.
        """
        if isinstance(session_id, FastSSHSession):
            if not session_id.is_connected:
                raise AIOSSHSessionExpiredError(
                    "Session is not connected",
                    code="SESSION_NOT_CONNECTED",
                )
            return session_id

        async with self._lock:
            if session_id not in self._active_sessions:
                raise AIOSSHSessionNotFoundError(
                    f"Session '{session_id}' not found",
                    code="SESSION_NOT_FOUND",
                )

            session = self._active_sessions[session_id]
            if not session.is_connected:
                raise AIOSSHSessionExpiredError(
                    f"Session '{session_id}' is not connected",
                    code="SESSION_NOT_CONNECTED",
                )

            return session

    @property
    def is_closed(self) -> bool:
        """Check if the client has been closed."""
        return self._closed

    @property
    def pool_stats(self) -> dict[str, object]:
        """Get connection pool statistics."""
        return self._pool.stats