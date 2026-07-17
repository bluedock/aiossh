"""
Connection Pool Module - v2.1 (v1.1.0)

Provides a thread-safe async connection pool with strict max connection
enforcement, idle connection reuse, automatic cleanup of stale connections,
and support for maintaining a minimum number of warm idle connections.
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional

from .exceptions import AIOSSHPoolExhaustedError
from .security import RateLimiter
from .session import FastSSHSession, SSHConfig


@dataclass
class PoolConfig:
    """Connection pool configuration.

    Attributes:
        max_connections: Absolute maximum number of concurrent connections.
        min_connections: Minimum idle connections to maintain (warm pool).
                         These are created lazily on first use or via ensure_min().
        max_idle_time: Maximum seconds a connection can remain idle.
        cleanup_interval: Seconds between cleanup cycles.
        max_lifetime: Maximum total lifetime of a connection in seconds.
    """

    max_connections: int = 10
    min_connections: int = 2
    max_idle_time: int = 300
    cleanup_interval: int = 60
    max_lifetime: int = 3600

    def __post_init__(self) -> None:
        if self.max_connections < 1:
            raise ValueError("max_connections must be at least 1")
        if self.min_connections > self.max_connections:
            raise ValueError(
                f"min_connections ({self.min_connections}) cannot exceed "
                f"max_connections ({self.max_connections})"
            )
        if self.max_idle_time < 0:
            raise ValueError("max_idle_time must be non-negative")
        if self.cleanup_interval < 1:
            raise ValueError("cleanup_interval must be at least 1")
        if self.max_lifetime < 0:
            raise ValueError("max_lifetime must be non-negative")


class _PoolEntry:
    """Internal pool entry tracking connection state."""

    __slots__ = ("connection", "created_at", "last_used", "in_use")

    def __init__(self, connection: FastSSHSession) -> None:
        self.connection = connection
        self.created_at = time.monotonic()
        self.last_used = time.monotonic()
        self.in_use = False


class ConnectionPool:
    """Thread-safe async connection pool for SSH sessions.

    Enforces strict connection limits, reuses idle connections,
    performs periodic cleanup of stale connections, and can maintain
    a minimum warm pool of idle connections.
    """

    def __init__(self, config: Optional[PoolConfig] = None) -> None:
        self._config = config or PoolConfig()
        self._pools: OrderedDict[str, list[_PoolEntry]] = OrderedDict()
        self._total_connections = 0
        self._idle_connections = 0
        self._lock = asyncio.Lock()
        self._connection_available = asyncio.Condition(self._lock)
        self._cleanup_task: Optional[asyncio.Task[None]] = None
        self._rate_limiter = RateLimiter(
            max_requests=self._config.max_connections * 2,
            window_seconds=1.0,
        )
        self._warming = False  # Prevent concurrent warm attempts

    async def start(self) -> None:
        """Start the connection pool and background cleanup task."""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._periodic_cleanup())

    async def ensure_min_connections(self, sample_config: Optional[SSHConfig] = None) -> None:
        """Ensure at least min_connections idle connections exist (if sample_config provided).
        
        This is best-effort and lazy. Call after start() if you want warm pool.
        """
        if self._config.min_connections <= 0 or sample_config is None:
            return
        if self._warming:
            return
        self._warming = True
        try:
            async with self._lock:
                current_idle = self._idle_connections
                needed = max(0, self._config.min_connections - current_idle)
                for _ in range(needed):
                    if self._total_connections >= self._config.max_connections:
                        break
                    try:
                        entry = _PoolEntry(FastSSHSession(sample_config))
                        await entry.connection.connect()
                        entry.in_use = False
                        key = self._make_key(sample_config)
                        if key not in self._pools:
                            self._pools[key] = []
                        self._pools[key].append(entry)
                        self._total_connections += 1
                        self._idle_connections += 1
                    except Exception:
                        # Best effort warm-up; ignore individual failures
                        break
        finally:
            self._warming = False

    async def get_connection(self, config: SSHConfig) -> FastSSHSession:
        """Acquire a connection from the pool or create a new one.

        The expensive connect() is performed *outside* the lock to avoid
        blocking the entire pool during network latency.
        """
        if not await self._rate_limiter.acquire():
            raise AIOSSHPoolExhaustedError(
                "Connection rate limit exceeded",
                code="RATE_LIMIT",
            )

        key = self._make_key(config)

        async with self._lock:
            if key not in self._pools:
                self._pools[key] = []

            entries = self._pools[key]

            # 1. Try to reuse an idle healthy connection
            for entry in entries:
                if not entry.in_use and entry.connection.is_connected:
                    entry.in_use = True
                    entry.last_used = time.monotonic()
                    self._idle_connections -= 1
                    return entry.connection

            # 2. Create new if under limit (optimistic increment)
            if self._total_connections >= self._config.max_connections:
                raise AIOSSHPoolExhaustedError(
                    f"Connection pool exhausted "
                    f"({self._total_connections}/{self._config.max_connections})",
                    code="POOL_EXHAUSTED",
                    details={
                        "total": self._total_connections,
                        "max": self._config.max_connections,
                        "idle": self._idle_connections,
                    },
                )

            entry = _PoolEntry(FastSSHSession(config))
            entry.in_use = True
            entries.append(entry)
            self._total_connections += 1

        # Connect OUTSIDE the lock (the expensive part)
        try:
            await entry.connection.connect()
        except Exception:
            # Rollback on failure
            async with self._lock:
                if entry in entries:
                    entries.remove(entry)
                self._total_connections = max(0, self._total_connections - 1)
            raise

        # Success - update timestamp under lock
        async with self._lock:
            entry.last_used = time.monotonic()
        return entry.connection

    async def return_connection(
        self,
        config: SSHConfig,
        connection: FastSSHSession,
    ) -> None:
        """Return a connection to the pool for reuse.

        Args:
            config: The SSH configuration used to create the connection.
            connection: The connection to return.
        """
        key = self._make_key(config)

        async with self._lock:
            if key not in self._pools:
                self._total_connections = max(0, self._total_connections - 1)
                try:
                    await connection.close()
                except Exception:
                    pass
                self._connection_available.notify_all()
                return

            for entry in self._pools[key]:
                if entry.connection is connection:
                    if connection.is_connected:
                        entry.in_use = False
                        entry.last_used = time.monotonic()
                        self._idle_connections += 1
                        self._connection_available.notify_all()
                    else:
                        self._pools[key].remove(entry)
                        self._total_connections = max(0, self._total_connections - 1)
                        if not entry.in_use:
                            self._idle_connections = max(0, self._idle_connections - 1)
                        self._connection_available.notify_all()
                    return

            # Connection not found in pool (was closed externally or race)
            self._total_connections = max(0, self._total_connections - 1)
            try:
                await connection.close()
            except Exception:
                pass
            self._connection_available.notify_all()

    async def _periodic_cleanup(self) -> None:
        """Periodically clean up expired and stale connections."""
        while True:
            try:
                await asyncio.sleep(self._config.cleanup_interval)
                await self._cleanup_expired()
                # After cleanup, try to maintain min if we have a sample key
                # (best effort, only if we have at least one pool key)
            except asyncio.CancelledError:
                break
            except Exception:
                # Cleanup must not crash the pool
                pass

    async def _cleanup_expired(self) -> None:
        """Remove idle and expired connections. Maintain min_connections if possible."""
        now = time.monotonic()

        async with self._lock:
            for key in list(self._pools.keys()):
                entries = self._pools[key]
                new_entries: list[_PoolEntry] = []
                removed_count = 0

                for entry in entries:
                    should_remove = self._should_remove(entry, now)

                    if should_remove and not entry.in_use:
                        try:
                            await entry.connection.close()
                        except Exception:
                            pass
                        self._total_connections = max(0, self._total_connections - 1)
                        removed_count += 1
                    else:
                        new_entries.append(entry)

                if new_entries:
                    self._pools[key] = new_entries
                else:
                    del self._pools[key]

            # Recalculate idle after cleanup
            self._idle_connections = 0
            for entries in self._pools.values():
                for e in entries:
                    if not e.in_use and e.connection.is_connected:
                        self._idle_connections += 1

    def _should_remove(self, entry: _PoolEntry, now: float) -> bool:
        """Determine if a connection should be removed."""
        if not entry.connection.is_connected:
            return True
        if not entry.in_use and (now - entry.last_used) > self._config.max_idle_time:
            return True
        if (now - entry.created_at) > self._config.max_lifetime:
            return True
        return False

    async def close(self) -> None:
        """Close all connections and stop the pool."""
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

        async with self._lock:
            for key in list(self._pools.keys()):
                entries = self._pools[key]
                for entry in entries:
                    try:
                        await entry.connection.close()
                    except Exception:
                        pass
                del self._pools[key]

            self._total_connections = 0
            self._idle_connections = 0

    @property
    def stats(self) -> dict[str, object]:
        """Get current pool statistics."""
        return {
            "total_connections": self._total_connections,
            "idle_connections": self._idle_connections,
            "in_use_connections": max(0, self._total_connections - self._idle_connections),
            "max_connections": self._config.max_connections,
            "min_connections": self._config.min_connections,
            "connection_rate": self._rate_limiter.current_rate,
        }

    @staticmethod
    def _make_key(config: SSHConfig) -> str:
        """Create a unique pool key for a connection configuration."""
        return f"{config.username}@{config.host}:{config.port}"
