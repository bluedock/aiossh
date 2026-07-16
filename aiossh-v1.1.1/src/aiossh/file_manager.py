"""
Session File Manager - v1.1.0 (Professional)

Manages encrypted session credential files with AES-256-GCM + HMAC-SHA512.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
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

try:
    import orjson as json_module
    def _json_dumps(data): return json_module.dumps(data)
    def _json_loads(data): return json_module.loads(data)
except ImportError:
    import json as json_module
    def _json_dumps(data): return json_module.dumps(data, separators=(",", ":")).encode()
    def _json_loads(data): return json_module.loads(data.decode())


class SessionFileManager:
    """Encrypted session storage (AES-256-GCM + HMAC-SHA512 + PBKDF2)."""

    _SALT_SIZE = 32
    _NONCE_SIZE = 12
    _HMAC_SIZE = 64
    _KEY_SIZE = 32
    _PBKDF2_ITERATIONS = 600_000
    _HEADER_SIZE = _SALT_SIZE + _NONCE_SIZE + _HMAC_SIZE

    def __init__(self, session_dir: str = "~/.aiossh/sessions") -> None:
        self._dir = Path(session_dir).expanduser()
        self._dir.mkdir(mode=0o700, parents=True, exist_ok=True)

    def _derive_key(self, master_password: str, salt: bytes) -> bytes:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA512(),
            length=self._KEY_SIZE,
            salt=salt,
            iterations=self._PBKDF2_ITERATIONS,
            backend=default_backend(),
        )
        return kdf.derive(master_password.encode("utf-8"))

    def _resolve_path(self, filename: str) -> Path:
        if not filename.endswith(".seshn"):
            filename = f"{filename}.seshn"
        target = (self._dir / filename).resolve()
        if not str(target).startswith(str(self._dir.resolve())):
            raise AIOSSHSecurityError("Path traversal detected", code="PATH_TRAVERSAL")
        return target

    def create_session_file(self, filename: str, credentials: dict[str, Any], master_password: str) -> Path:
        filename = InputValidator.validate_session_name(filename)
        target = self._resolve_path(filename)

        salt = secrets.token_bytes(self._SALT_SIZE)
        nonce = secrets.token_bytes(self._NONCE_SIZE)
        key = self._derive_key(master_password, salt)

        try:
            plaintext = _json_dumps(credentials)
            aesgcm = AESGCM(key)
            ciphertext = aesgcm.encrypt(nonce, plaintext, None)

            signed_data = salt + nonce + ciphertext
            file_hmac = hmac.new(key, signed_data, hashlib.sha512).digest()

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
            raise AIOSSHEncryptionError("Failed to encrypt session file", code="ENCRYPTION_FAILED", cause=e) from e
        finally:
            SecureMemory.secure_clear(bytearray(key))
            if 'plaintext' in locals():
                SecureMemory.secure_clear(bytearray(plaintext))

        return target

    def load_session_file(self, filename: str, master_password: str) -> dict[str, Any]:
        filename = InputValidator.validate_session_name(filename)
        target = self._resolve_path(filename)

        if not target.exists():
            raise AIOSSHSessionCorruptedError(f"Session file not found: {filename}", code="FILE_NOT_FOUND")

        with open(target, "rb") as f:
            data = f.read()

        if len(data) < self._HEADER_SIZE + 1:
            raise AIOSSHSessionCorruptedError("Session file too small", code="FILE_TOO_SMALL")

        pos = 0
        salt = data[pos : pos + self._SALT_SIZE]; pos += self._SALT_SIZE
        nonce = data[pos : pos + self._NONCE_SIZE]; pos += self._NONCE_SIZE
        file_hmac = data[pos : pos + self._HMAC_SIZE]; pos += self._HMAC_SIZE
        ciphertext = data[pos:]

        key = self._derive_key(master_password, salt)

        try:
            signed_data = salt + nonce + ciphertext
            expected_hmac = hmac.new(key, signed_data, hashlib.sha512).digest()

            if not SecureMemory.secure_compare(file_hmac, expected_hmac):
                raise AIOSSHIntegrityError("Session file integrity check failed", code="HMAC_MISMATCH")

            aesgcm = AESGCM(key)
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
            credentials = _json_loads(plaintext)

            if not isinstance(credentials, dict):
                raise AIOSSHSessionCorruptedError("Invalid session data format", code="INVALID_FORMAT")

            return credentials
        finally:
            SecureMemory.secure_clear(bytearray(key))

    def list_sessions(self) -> list[str]:
        return sorted([f.stem for f in self._dir.glob("*.seshn") if f.is_file()])

    def delete_session(self, filename: str) -> bool:
        filename = InputValidator.validate_session_name(filename)
        target = self._resolve_path(filename)
        if target.exists():
            target.unlink()
            return True
        return False
