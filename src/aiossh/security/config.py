"""
Security utilities for AIOSSH.

Provides rate limiting, audit logging, secure memory handling,
and cryptographic configuration defaults.
"""

from __future__ import annotations

import asyncio
import hmac
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class SecurityConfig:
    """Security-related configuration for SSH connections."""

    allowed_ciphers: tuple[str, ...] = (
        "aes256-gcm@openssh.com",
        "aes128-gcm@openssh.com",
        "chacha20-poly1305@openssh.com",
        "aes256-ctr",
        "aes192-ctr",
        "aes128-ctr",
    )
    allowed_kex_algorithms: tuple[str, ...] = (
        "curve25519-sha256",
        "curve25519-sha256@libssh.org",
        "ecdh-sha2-nistp256",
        "ecdh-sha2-nistp384",
        "ecdh-sha2-nistp521",
        "diffie-hellman-group-exchange-sha256",
    )
    allowed_macs: tuple[str, ...] = (
        "hmac-sha2-256-etm@openssh.com",
        "hmac-sha2-512-etm@openssh.com",
        "hmac-sha2-256",
        "hmac-sha2-512",
    )


class RateLimiter:
    """Simple async sliding-window rate limiter."""

    def __init__(self, max_requests: int, window_seconds: float) -> None:
        if max_requests < 1:
            raise ValueError("max_requests must be positive")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> bool:
        async with self._lock:
            now = time.monotonic()
            while self._requests and (now - self._requests[0]) > self.window_seconds:
                self._requests.popleft()
            if len(self._requests) >= self.max_requests:
                return False
            self._requests.append(now)
            return True

    @property
    def current_rate(self) -> float:
        """Return the approximate current request rate (requests/second).

        Note: This is a best-effort snapshot.  It does *not* acquire the
        internal lock (which is an ``asyncio.Lock`` and cannot be held from
        a synchronous property), so concurrent ``acquire()`` calls may
        slightly skew the result.  This is acceptable for monitoring and
        pool-statistics purposes.
        """
        now = time.monotonic()
        # Only prune clearly-expired entries (safe even without the lock:
        # popleft on a deque is a single atomic operation in CPython's GIL).
        while self._requests and (now - self._requests[0]) > self.window_seconds:
            try:
                self._requests.popleft()
            except IndexError:
                break
        if not self._requests:
            return 0.0
        elapsed = now - self._requests[0]
        return len(self._requests) / max(elapsed, 0.001)


class AuditLogger:
    """Simple audit logger (extendable, silent by default)."""

    async def log(self, event: str, data: Optional[dict[str, Any]] = None) -> None:
        pass


class SecureMemory:
    """Utilities for handling sensitive data."""

    @staticmethod
    def secure_clear(buffer: bytearray) -> None:
        if not isinstance(buffer, bytearray):
            return
        length = len(buffer)
        for i in range(length):
            buffer[i] = 0
        import os
        rnd = os.urandom(length)
        for i in range(length):
            buffer[i] = rnd[i]

    @staticmethod
    def secure_compare(a: bytes, b: bytes) -> bool:
        return hmac.compare_digest(a, b)


class SecureChannel:
    """Placeholder for future secure channel support."""
    pass
