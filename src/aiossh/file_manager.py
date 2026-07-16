"""
Session File Manager - v2.0

Manages encrypted session credential files with:
- AES-256-GCM encryption
- PBKDF2-HMAC-SHA512 key derivation (600,000 iterations)
- Random salt per file (32 bytes)
- HMAC-SHA512 integrity verification
- Atomic file writes
- Path traversal prevention
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import struct
from pathlib import Path
from typing import Any

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from .exceptions import (
    AIOSSHEncryptionError,
    AIOSSHIntegrityError,
    AIOSSHSecurityError,
    AIOSSHSessionCorruptedError,
)
from .security import SecureMemory
from .validators import InputValidator

# JSON serialization with orjson fallback
try:
    import orjson

    def _json_dumps(data: object) -> bytes:
        return orjson.dumps(data)

    def _json_loads(data: bytes) -> object:
        return orjson.loads(data)
except ImportError:
    import json

    def _json_dumps(data: object) -> bytes:
        return json.dumps(data, separators=(",", ":")).encode("utf-8")

    def _json_loads(data: bytes) -> object:
        return json.loads(data.decode("utf-8"))


class SessionFileManager:
    """Manages encrypted session credential files.

    File format:
        [salt: 32 bytes][nonce: 12 bytes][hmac: 64 bytes][ciphertext: variable]

    Encryption: AES-256-GCM with random nonce
    Key: Derived via PBKDF2-HMAC-SHA512 (600,000 iterations) with unique salt
    Integrity: HMAC-SHA512 over (salt + nonce + ciphertext)
    """

    _SALT_SIZE = 32
    _NONCE_SIZE = 12
    _HMAC_SIZE = 64
    _KEY_SIZE = 32
    _PBKDF2_ITERATIONS = 600_000
    _HEADER_SIZE = _SALT_SIZE + _NONCE_SIZE + _HMAC_SIZE

    def __init__(self, session_dir: str = "~/.aiossh/sessions") -> None:
        """Initialize session file manager.

        Args:
            session_dir: Directory for storing session files.
        """
        self._dir = Path(session_dir).expanduser()
        self._dir.mkdir(mode=0o700, parents=True, exist_ok=True)

    def _derive_key(self, master_password: str, salt: bytes) -> bytes:
        """Derive encryption key using PBKDF2-HMAC-SHA512.

        Args:
            master_password: User's master password.
            salt: Cryptographic salt (32 bytes).

        Returns:
            32-byte AES-256 key.
        """
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA512(),
            length=self._KEY_SIZE,
            salt=salt,
            iterations=self._PBKDF2_ITERATIONS,
            backend=default_backend(),
        )
        return kdf.derive(master_password.encode("utf-8"))

    def _resolve_path(self, filename: str) -> Path:
        """Resolve and validate the target file path.

        Args:
            filename: Base filename (with or without .seshn extension).

        Returns:
            Resolved absolute path.

        Raises:
            AIOSSHSecurityError: If path traversal is detected.
        """
        if not filename.endswith(".seshn"):
            filename = f"{filename}.seshn"

        target = (self._dir / filename).resolve()
        base_dir = self._dir.resolve()

        if not str(target).startswith(str(base_dir)):
            raise AIOSSHSecurityError(
                "Path traversal attempt detected",
                code="PATH_TRAVERSAL",
                details={"filename": filename},
            )

        return target

    def create_session_file(
        self,
        filename: str,
        credentials: dict[str, Any],
        master_password: str,
    ) -> Path:
        """Create an encrypted session file.

        Args:
            filename: Base filename (without extension).
            credentials: Dictionary of credentials to encrypt.
            master_password: Password to derive encryption key.

        Returns:
            Path to the created file.

        Raises:
            AIOSSHSecurityError: If path traversal is detected.
            AIOSSHEncryptionError: If encryption fails.
        """
        filename = InputValidator.validate_session_name(filename)
        target = self._resolve_path(filename)

        # Generate cryptographic materials
        salt = secrets.token_bytes(self._SALT_SIZE)
        nonce = secrets.token_bytes(self._NONCE_SIZE)
        key = self._derive_key(master_password, salt)

        try:
            # Encrypt credentials
            plaintext = _json_dumps(credentials)
            aesgcm = AESGCM(key)
            ciphertext = aesgcm.encrypt(nonce, plaintext, None)

            # Compute integrity HMAC
            signed_data = salt + nonce + ciphertext
            file_hmac = hmac.new(
                key, signed_data, hashlib.sha512
            ).digest()

            # Write atomically via temp file
            temp_path = target.with_suffix(".tmp")
            try:
                with open(temp_path, "wb") as f:
                    f.write(salt + nonce + file_hmac + ciphertext)
                os.chmod(temp_path, 0o600)
                os.replace(temp_path, target)
            except Exception:
                if temp_path.exists():
                    temp_path.unlink()
                raise

        except Exception as e:
            raise AIOSSHEncryptionError(
                "Failed to encrypt session file",
                code="ENCRYPTION_FAILED",
                cause=e,
            )
        finally:
            # Securely clear sensitive material
            SecureMemory.secure_clear(bytearray(key))
            SecureMemory.secure_clear(bytearray(plaintext))

        return target

    def load_session_file(
        self,
        filename: str,
        master_password: str,
    ) -> dict[str, Any]:
        """Load and decrypt a session file.

        Args:
            filename: Session filename.
            master_password: Password to derive decryption key.

        Returns:
            Decrypted credentials dictionary.

        Raises:
            AIOSSHSessionCorruptedError: If file is corrupted.
            AIOSSHIntegrityError: If HMAC verification fails.
            AIOSSHEncryptionError: If decryption fails.
        """
        filename = InputValidator.validate_session_name(filename)
        target = self._resolve_path(filename)

        if not target.exists():
            raise AIOSSHSessionCorruptedError(
                f"Session file not found: {filename}",
                code="FILE_NOT_FOUND",
            )

        # Read file
        try:
            with open(target, "rb") as f:
                data = f.read()
        except OSError as e:
            raise AIOSSHSessionCorruptedError(
                f"Cannot read session file: {e}",
                code="READ_ERROR",
                cause=e,
            )

        if len(data) < self._HEADER_SIZE + 1:
            raise AIOSSHSessionCorruptedError(
                "Session file is too small - possibly corrupted",
                code="FILE_TOO_SMALL",
                details={"size": len(data), "min_expected": self._HEADER_SIZE + 1},
            )

        # Parse file structure
        pos = 0
        salt = data[pos: pos + self._SALT_SIZE]
        pos += self._SALT_SIZE

        nonce = data[pos: pos + self._NONCE_SIZE]
        pos += self._NONCE_SIZE

        file_hmac = data[pos: pos + self._HMAC_SIZE]
        pos += self._HMAC_SIZE

        ciphertext = data[pos:]

        # Derive key and verify integrity
        key = self._derive_key(master_password, salt)

        try:
            signed_data = salt + nonce + ciphertext
            expected_hmac = hmac.new(
                key, signed_data, hashlib.sha512
            ).digest()

            if not SecureMemory.secure_compare(file_hmac, expected_hmac):
                raise AIOSSHIntegrityError(
                    "Session file integrity check failed - "
                    "wrong password or corrupted file",
                    code="HMAC_MISMATCH",
                )

            # Decrypt
            try:
                aesgcm = AESGCM(key)
                plaintext = aesgcm.decrypt(nonce, ciphertext, None)
            except Exception as e:
                raise AIOSSHEncryptionError(
                    "Failed to decrypt session file",
                    code="DECRYPTION_FAILED",
                    cause=e,
                )

            # Parse credentials
            try:
                credentials = _json_loads(plaintext)
            except Exception as e:
                raise AIOSSHSessionCorruptedError(
                    "Failed to parse session data",
                    code="PARSE_ERROR",
                    cause=e,
                )

            if not isinstance(credentials, dict):
                raise AIOSSHSessionCorruptedError(
                    "Invalid session data format - expected dictionary",
                    code="INVALID_FORMAT",
                    details={"type": type(credentials).__name__},
                )

            return credentials

        finally:
            SecureMemory.secure_clear(bytearray(key))

    def list_sessions(self) -> list[str]:
        """List all stored session names.

        Returns:
            Sorted list of session names (without .seshn extension).
        """
        sessions = []
        for f in self._dir.glob("*.seshn"):
            if f.is_file():
                sessions.append(f.stem)
        return sorted(sessions)

    def delete_session(self, filename: str) -> bool:
        """Delete a session file.

        Args:
            filename: Session filename to delete.

        Returns:
            True if deleted, False if file didn't exist.

        Raises:
            AIOSSHSecurityError: If path traversal is detected.
        """
        filename = InputValidator.validate_session_name(filename)
        target = self._resolve_path(filename)

        if target.exists():
            target.unlink()
            return True
        return False