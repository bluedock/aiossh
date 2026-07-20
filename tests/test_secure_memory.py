"""
Regression tests for secure in-memory wiping of secrets.

Guards against the bug where SessionFileManager called
SecureMemory.secure_clear(bytearray(key)) on a *copy* of the derived key,
leaving the real key (and plaintext credentials) un-wiped in memory.
"""

import tempfile
import unittest

from aiossh.security.file_manager import SessionFileManager
from aiossh.security import SecureMemory


class SecureMemoryTest(unittest.TestCase):
    def test_secure_clear_zeroes_and_randomizes(self):
        buf = bytearray(b"\xAA" * 32)
        original = bytes(buf)
        SecureMemory.secure_clear(buf)
        # The same buffer object must have been mutated in place.
        self.assertNotEqual(bytes(buf), original)

    def test_secure_clear_ignores_immutable_bytes(self):
        # bytes are immutable; secure_clear must not raise on wrong type.
        SecureMemory.secure_clear(b"immutable")  # type: ignore[arg-type]

    def test_derive_key_is_mutable_bytearray(self):
        m = SessionFileManager(tempfile.mkdtemp())
        key = m._derive_key("master-password-123", b"s" * 32)
        # Must be a mutable bytearray so it can actually be wiped in place.
        self.assertIsInstance(key, bytearray)
        # And clearing it must change the real object.
        snapshot = bytes(key)
        SecureMemory.secure_clear(key)
        self.assertNotEqual(bytes(key), snapshot)

    def test_roundtrip_still_works_after_fix(self):
        m = SessionFileManager(tempfile.mkdtemp())
        mp = "another-strong-master-pw"
        creds = {"host": "example.com", "username": "root",
                 "password": "p@ssw0rd", "port": 2222}
        m.create_session_file("sess1", creds, mp)
        self.assertEqual(m.load_session_file("sess1", mp), creds)

    def test_wrong_master_password_fails_integrity(self):
        m = SessionFileManager(tempfile.mkdtemp())
        creds = {"host": "h", "username": "u", "password": "p", "port": 22}
        m.create_session_file("sess2", creds, "correct-master-pw-1")
        with self.assertRaises(Exception):
            m.load_session_file("sess2", "wrong-master-pw-99")


if __name__ == "__main__":
    unittest.main()
