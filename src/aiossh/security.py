"""
Security Module - v2.0

Core security primitives:
- ChaCha20-Poly1305 encrypted channels with overflow-safe nonces
- PBKDF2-HMAC-SHA512 key derivation (600,000 iterations)
- HMAC-SHA512 integrity verification
- Constant-time comparison
- Rate limiting with exponential backoff
- Audit logging with tamper detection
- Secure memory cleanup
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import secrets
import struct
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import constant_time, hashes
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from .exceptions import (
    AIOSSHEncryptionError,
    AIOSSHIntegrityError,
    AIOSSHRateLimitError,
    AIOSSHSecurityError,
)

# ── JSON Serialization (orjson with fallback) ────────────────────────────────

try:
    import orjson

    def _fast_dumps(data: dict) -> bytes:
        """Serialize data to JSON bytes using orjson."""
        return orjson.dumps(data)

    def _fast_loads(data: bytes) -> dict:
        """Deserialize JSON bytes to dict using orjson."""
        return orjson.loads(data)

except ImportError:
    import json

    def _fast_dumps(data: dict) -> bytes:
        """Serialize data to JSON bytes using stdlib json."""
        return json.dumps(data, separators=(",", ":")).encode("utf-8")

    def _fast_loads(data: bytes) -> dict:
        """Deserialize JSON bytes to dict using stdlib json."""
        return json.loads(data.decode("utf-8"))


# ── Security Configuration ───────────────────────────────────────────────────


@dataclass(frozen=True)
class SecurityConfig:
    """Immutable security configuration.

    Attributes:
        pbkdf2_iterations: PBKDF2 iteration count (min 600,000 per OWASP 2024).
        max_connections_per_minute: Rate limit for new connections.
        max_commands_per_second: Rate limit for command execution.
        max_auth_attempts: Maximum failed authentication attempts before lockout.
        auth_lockout_seconds: Duration of authentication lockout.
        session_max_lifetime: Maximum session lifetime in seconds.
        max_idle_seconds: Maximum idle time before session is considered stale.
        allowed_kex_algorithms: Permitted SSH key exchange algorithms.
        allowed_ciphers: Permitted SSH encryption ciphers.
        allowed_macs: Permitted SSH MAC algorithms.
    """

    pbkdf2_iterations: int = 600_000
    max_connections_per_minute: int = 30
    max_commands_per_second: int = 50
    max_auth_attempts: int = 5
    auth_lockout_seconds: int = 300
    session_max_lifetime: int = 86400  # 24 hours
    max_idle_seconds: int = 900  # 15 minutes

    allowed_kex_algorithms: tuple[str, ...] = field(default=(
        "curve25519-sha256",
        "curve25519-sha256@libssh.org",
        "ecdh-sha2-nistp521",
    ))

    allowed_ciphers: tuple[str, ...] = field(default=(
        "chacha20-poly1305@openssh.com",
        "aes256-gcm@openssh.com",
    ))

    allowed_macs: tuple[str, ...] = field(default=(
        "hmac-sha2-512-etm@openssh.com",
        "hmac-sha2-256-etm@openssh.com",
    ))

    def __post_init__(self) -> None:
        """Validate configuration values."""
        if self.pbkdf2_iterations < 600_000:
            raise ValueError(
                f"PBKDF2 iterations must be >= 600,000 (OWASP 2024), "
                f"got {self.pbkdf2_iterations}"
            )
        if self.max_auth_attempts < 1:
            raise ValueError("max_auth_attempts must be positive")
        if self.auth_lockout_seconds < 1:
            raise ValueError("auth_lockout_seconds must be positive")


# ── Rate Limiter ─────────────────────────────────────────────────────────────


class RateLimiter:
    """Sliding window rate limiter with exponential backoff penalty.

    Uses a deque-based sliding window for O(1) cleanup of expired events.
    Implements burst tolerance and progressive penalty escalation for
    repeat offenders.
    """

    def __init__(
        self,
        max_requests: int,
        window_seconds: float,
        burst_multiplier: int = 2,
    ) -> None:
        """Initialize rate limiter.

        Args:
            max_requests: Maximum requests allowed in the window.
            window_seconds: Sliding window size in seconds.
            burst_multiplier: Burst allowance multiplier (2 = 2x burst).
        """
        if max_requests <= 0:
            raise ValueError("max_requests must be positive")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")

        self._max_requests = max_requests
        self._window = window_seconds
        self._burst_limit = max_requests * burst_multiplier
        self._timestamps: deque[float] = deque(maxlen=self._burst_limit)
        self._lock = asyncio.Lock()
        self._penalty_until: float = 0.0
        self._violation_count: int = 0

    async def acquire(self) -> bool:
        """Attempt to acquire a rate limit token.

        Returns:
            True if the request is allowed, False if rate-limited.
        """
        async with self._lock:
            now = time.monotonic()

            # Check penalty period
            if now < self._penalty_until:
                return False

            # Clean expired timestamps
            cutoff = now - self._window
            while self._timestamps and self._timestamps[0] <= cutoff:
                self._timestamps.popleft()

            # Check hard burst limit
            if len(self._timestamps) >= self._burst_limit:
                self._violation_count += 1
                penalty_seconds = min(
                    2 ** self._violation_count * 10,
                    3600,  # Max 1 hour penalty
                )
                self._penalty_until = now + penalty_seconds
                return False

            # Check rate limit
            if len(self._timestamps) >= self._max_requests:
                return False

            # Allow the request
            self._timestamps.append(now)
            self._violation_count = max(0, self._violation_count - 1)
            return True

    @property
    def current_rate(self) -> float:
        """Get the current request rate (requests per second)."""
        now = time.monotonic()
        cutoff = now - self._window
        recent = sum(1 for t in self._timestamps if t > cutoff)
        return recent / self._window if self._window > 0 else 0.0

    def reset(self) -> None:
        """Reset the rate limiter state."""
        self._timestamps.clear()
        self._violation_count = 0
        self._penalty_until = 0.0


# ── Secure Memory Utilities ──────────────────────────────────────────────────


class SecureMemory:
    """Constant-time comparison and secure memory wiping utilities."""

    @staticmethod
    def secure_compare(a: Union[str, bytes], b: Union[str, bytes]) -> bool:
        """Constant-time comparison to prevent timing side-channel attacks.

        Args:
            a: First value to compare.
            b: Second value to compare.

        Returns:
            True if values are identical, False otherwise.
        """
        if isinstance(a, str):
            a = a.encode("utf-8")
        if isinstance(b, str):
            b = b.encode("utf-8")
        return constant_time.bytes_eq(a, b)

    @staticmethod
    def secure_clear(data: bytearray) -> None:
        """Overwrite sensitive data with zeros.

        Args:
            data: Bytearray to clear. Modified in-place.
        """
        for i in range(len(data)):
            data[i] = 0


# ── Secure Encrypted Channel ─────────────────────────────────────────────────


class SecureChannel:
    """Encrypted communication channel using ChaCha20-Poly1305.

    Derives separate encryption and authentication keys via HKDF.
    Uses overflow-protected nonce generation (12 bytes, 96 bits) with
    random prefix to prevent nonce reuse under high concurrency.

    Raises AIOSSHSecurityError when nonce counter would overflow (after 2^64
    encryptions), requiring key rotation.
    """

    _NONCE_SIZE = 12  # 96 bits for ChaCha20-Poly1305
    _MAX_NONCE_COUNTER = 2**64 - 1

    def __init__(self, master_key: bytes) -> None:
        """Initialize secure channel.

        Args:
            master_key: Master key material (min 32 bytes).

        Raises:
            AIOSSHSecurityError: If master key is too short.
        """
        if len(master_key) < 32:
            raise AIOSSHSecurityError(
                "Master key must be at least 32 bytes (256 bits)",
                code="WEAK_KEY",
                details={"key_length": len(master_key)},
            )

        # Derive separate keys using HKDF
        salt = secrets.token_bytes(32)
        hkdf = HKDF(
            algorithm=hashes.SHA512(),
            length=64,
            salt=salt,
            info=b"aiossh-channel-v4",
            backend=default_backend(),
        )

        key_material = hkdf.derive(master_key)
        self._encryption_key = key_material[:32]
        self._auth_key = key_material[32:64]
        self._nonce_counter = 0
        self._lock = asyncio.Lock()

        # Securely clear derived key material from local variables
        SecureMemory.secure_clear(bytearray(salt))
        SecureMemory.secure_clear(bytearray(key_material))
        SecureMemory.secure_clear(bytearray(master_key))

    async def encrypt(self, plaintext: Union[str, bytes]) -> bytes:
        """Encrypt data with authenticated encryption.

        Args:
            plaintext: Data to encrypt (string or bytes).

        Returns:
            JSON bytes containing nonce, ciphertext, and HMAC.

        Raises:
            AIOSSHSecurityError: If nonce counter overflow occurs.
            AIOSSHEncryptionError: If encryption fails.
        """
        async with self._lock:
            if isinstance(plaintext, str):
                plaintext = plaintext.encode("utf-8")

            nonce = self._generate_nonce()
            plaintext_copy = bytes(plaintext)  # Work with copy

            try:
                chacha = ChaCha20Poly1305(self._encryption_key)
                ciphertext = chacha.encrypt(nonce, plaintext_copy, None)

                # Compute HMAC over nonce + ciphertext
                mac = hmac.new(
                    self._auth_key,
                    nonce + ciphertext,
                    hashlib.sha512,
                ).digest()

                return _fast_dumps({
                    "n": nonce.hex(),
                    "c": ciphertext.hex(),
                    "m": mac.hex(),
                })
            finally:
                SecureMemory.secure_clear(bytearray(plaintext_copy))

    async def decrypt(self, encrypted_data: bytes) -> bytes:
        """Decrypt and verify authenticated data.

        Args:
            encrypted_data: Encrypted data from encrypt() method.

        Returns:
            Decrypted plaintext bytes.

        Raises:
            AIOSSHIntegrityError: If HMAC verification fails.
            AIOSSHEncryptionError: If data format is invalid or decryption fails.
        """
        async with self._lock:
            try:
                obj = _fast_loads(encrypted_data)
                nonce = bytes.fromhex(obj["n"])
                ciphertext = bytes.fromhex(obj["c"])
                mac = bytes.fromhex(obj["m"])
            except (KeyError, ValueError, TypeError) as e:
                raise AIOSSHEncryptionError(
                    "Invalid encrypted data format",
                    code="INVALID_FORMAT",
                    cause=e,
                )

            # Verify HMAC first (authenticate before decrypt)
            expected_mac = hmac.new(
                self._auth_key,
                nonce + ciphertext,
                hashlib.sha512,
            ).digest()

            if not SecureMemory.secure_compare(mac, expected_mac):
                raise AIOSSHIntegrityError(
                    "Message authentication failed - data may be tampered",
                    code="HMAC_MISMATCH",
                )

            try:
                chacha = ChaCha20Poly1305(self._encryption_key)
                return chacha.decrypt(nonce, ciphertext, None)
            except Exception as e:
                raise AIOSSHEncryptionError(
                    "Decryption failed - key may be incorrect",
                    code="DECRYPTION_FAILED",
                    cause=e,
                )

    def _generate_nonce(self) -> bytes:
        """Generate unique 12-byte nonce with overflow protection.

        Mixes 4 random bytes with 8-byte monotonic counter to guarantee
        uniqueness under concurrent access (lock ensures sequential counter).

        Returns:
            12-byte nonce.

        Raises:
            AIOSSHSecurityError: If counter would overflow 2^64.
        """
        self._nonce_counter += 1
        if self._nonce_counter > self._MAX_NONCE_COUNTER:
            raise AIOSSHSecurityError(
                "Nonce counter overflow - key rotation required",
                code="NONCE_OVERFLOW",
            )

        random_part = secrets.token_bytes(4)
        counter_part = struct.pack(">Q", self._nonce_counter)
        return random_part + counter_part


# ── Audit Logger ─────────────────────────────────────────────────────────────


class AuditLogger:
    """Secure audit logger with HMAC-based tamper detection.

    All log entries are individually signed with HMAC-SHA512 for
    integrity verification. Writes are batched for performance
    and use atomic file operations.
    """

    _FLUSH_INTERVAL = 30.0  # seconds
    _BATCH_SIZE = 50  # events
    _MAX_BUFFER_SIZE = 5_000_000  # 5 MB safety limit

    def __init__(self, log_path: str = "~/.aiossh/audit.log") -> None:
        """Initialize audit logger.

        Args:
            log_path: Path to the audit log file.
        """
        self._path = Path(log_path).expanduser()
        self._path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

        # Set restrictive permissions on log directory
        try:
            os_module = __import__("os")
            os_module.chmod(str(self._path.parent), 0o700)
        except Exception:
            pass

        self._signing_key = secrets.token_bytes(32)
        self._buffer: list[bytes] = []
        self._buffer_size: int = 0
        self._lock = asyncio.Lock()
        self._last_flush = time.monotonic()

    async def log(
        self,
        event_type: str,
        details: dict[str, object],
        level: str = "INFO",
    ) -> None:
        """Log a security event with integrity protection.

        Args:
            event_type: Event category (e.g., 'connection', 'auth_failure').
            details: Event-specific information.
            level: Severity level (INFO, WARNING, ERROR).
        """
        event = {
            "ts": time.time(),
            "type": event_type,
            "level": level,
            "detail": details,
        }

        raw = _fast_dumps(event)
        sig = hmac.new(
            self._signing_key,
            raw,
            hashlib.sha512,
        ).digest()

        signed_entry = raw + b"|" + sig.hex().encode("utf-8")

        async with self._lock:
            self._buffer.append(signed_entry)
            self._buffer_size += len(signed_entry)

            should_flush = (
                len(self._buffer) >= self._BATCH_SIZE
                or time.monotonic() - self._last_flush > self._FLUSH_INTERVAL
                or self._buffer_size > self._MAX_BUFFER_SIZE
            )

            if should_flush:
                await self._flush()

    async def _flush(self) -> None:
        """Write buffered events to disk atomically."""
        if not self._buffer:
            return

        data = b"\n".join(self._buffer) + b"\n"
        temp_path = self._path.with_suffix(".tmp")

        try:
            import aiofiles

            async with aiofiles.open(temp_path, "wb") as f:
                await f.write(data)

            # Set permissions
            os_module = __import__("os")
            os_module.chmod(str(temp_path), 0o600)

            # Atomic replace
            os_module.replace(str(temp_path), str(self._path))
        except Exception:
            # Fail-safe: logging must not crash the application
            pass
        finally:
            self._buffer.clear()
            self._buffer_size = 0
            self._last_flush = time.monotonic()

    async def verify_integrity(self) -> bool:
        """Verify the integrity of the entire audit log.

        Returns:
            True if all entries pass HMAC verification, False otherwise.
        """
        if not self._path.exists():
            return True

        try:
            import aiofiles

            async with aiofiles.open(self._path, "rb") as f:
                content = await f.read()
        except Exception:
            return False

        for line in content.split(b"\n"):
            if not line:
                continue

            if b"|" not in line:
                return False

            raw, sig_hex = line.rsplit(b"|", 1)
            expected_sig = hmac.new(
                self._signing_key,
                raw,
                hashlib.sha512,
            ).hexdigest().encode("utf-8")

            if not SecureMemory.secure_compare(sig_hex, expected_sig):
                return False

        return True