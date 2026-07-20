"""
Offline test suite for aiossh 1.1.3 (patched).

No real network / real asyncssh available in this sandbox, so a minimal
fake asyncssh module (tests/fakes.py + mocks/asyncssh) stands in for the
real SSH transport. `cryptography` is the real library (installed), so
file_manager.py's encryption path is exercised for real.
"""
import asyncio
import os
import shlex
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))                       # fakes.py
sys.path.insert(0, str(HERE / "_fake_asyncssh"))     # fake `asyncssh` package
sys.path.insert(0, str(HERE.parent / "src"))         # real aiossh package

import asyncssh  # the fake
from fakes import FakeConnection, FakeSFTP

from aiossh.security.validators import InputValidator
from aiossh.exceptions import (
    AIOSSHInvalidParameterError, AIOSSHSecurityError, AIOSSHPoolExhaustedError,
    AIOSSHCommandTimeoutError, AIOSSHFileDiskFullError, AIOSSHFileDownloadError,
)
from aiossh.core.session import FastSSHSession, SSHConfig
from aiossh.core.pool import ConnectionPool, PoolConfig
from aiossh.security import RateLimiter, SecurityConfig
from aiossh.security.file_manager import SessionFileManager
from aiossh.integrations.docker import DockerExecSession
from aiossh.transfer.scp import ParallelSCP
from aiossh.core import AIOSSH


def make_session(conn: FakeConnection) -> FastSSHSession:
    cfg = SSHConfig(host="test.example.com", username="tester", password="hunter2pass",
                     security=SecurityConfig())
    session = FastSSHSession(cfg)
    session._connection = conn
    return session


# ───────────────────────── InputValidator ─────────────────────────

class TestValidators(unittest.TestCase):
    def test_valid_hostname_and_ip(self):
        self.assertEqual(InputValidator.validate_host("example.com"), "example.com")
        self.assertEqual(InputValidator.validate_host("8.8.8.8"), "8.8.8.8")

    def test_private_ip_blocked_by_default(self):
        with self.assertRaises(AIOSSHInvalidParameterError):
            InputValidator.validate_host("192.168.1.1")
        with self.assertRaises(AIOSSHInvalidParameterError):
            InputValidator.validate_host("127.0.0.1")

    def test_private_ip_allowed_when_opted_in(self):
        self.assertEqual(InputValidator.validate_host("192.168.1.1", allow_private=True), "192.168.1.1")

    def test_null_byte_host_rejected(self):
        with self.assertRaises(AIOSSHInvalidParameterError):
            InputValidator.validate_host("evil\x00.com")

    def test_port_range(self):
        self.assertEqual(InputValidator.validate_port(22), 22)
        with self.assertRaises(AIOSSHInvalidParameterError):
            InputValidator.validate_port(0)
        with self.assertRaises(AIOSSHInvalidParameterError):
            InputValidator.validate_port(70000)

    def test_dangerous_command_blocked(self):
        with self.assertRaises(AIOSSHSecurityError):
            InputValidator.validate_command("rm -rf /")
        with self.assertRaises(AIOSSHSecurityError):
            InputValidator.validate_command("echo $(whoami)")

    def test_safe_command_allowed(self):
        self.assertEqual(InputValidator.validate_command("uptime"), "uptime")

    def test_path_traversal_blocked(self):
        with self.assertRaises(AIOSSHSecurityError):
            InputValidator.validate_path("../../etc/passwd")

    def test_session_name_rejects_separators(self):
        with self.assertRaises(AIOSSHInvalidParameterError):
            InputValidator.validate_session_name("../../etc/cron.d/evil")


# ───────────────────────── RateLimiter ─────────────────────────

class TestRateLimiter(unittest.IsolatedAsyncioTestCase):
    async def test_limits_bursts(self):
        rl = RateLimiter(max_requests=3, window_seconds=60)
        results = [await rl.acquire() for _ in range(5)]
        self.assertEqual(results, [True, True, True, False, False])


# ───────────────────────── FastSSHSession ─────────────────────────

class TestFastSSHSession(unittest.IsolatedAsyncioTestCase):
    async def test_execute_happy_path(self):
        conn = FakeConnection(command_handler=lambda c: asyncssh.SSHCompletedProcess("hello\n", "", 0))
        session = make_session(conn)
        result = await session.execute("echo hello")
        self.assertTrue(result["success"])
        self.assertEqual(result["exit_code"], 0)
        self.assertIn("echo hello", conn.executed_commands)

    async def test_execute_rejects_dangerous_command(self):
        conn = FakeConnection()
        session = make_session(conn)
        with self.assertRaises(AIOSSHSecurityError):
            await session.execute("rm -rf /")
        self.assertEqual(conn.executed_commands, [])  # never reached the transport

    async def test_execute_sudo_prefixes_command(self):
        conn = FakeConnection()
        session = make_session(conn)
        await session.execute("systemctl restart nginx", sudo=True)
        self.assertEqual(conn.executed_commands, ["sudo -n systemctl restart nginx"])

    async def test_execute_timeout_raises_specific_error(self):
        conn = FakeConnection(hang_forever=True)
        session = make_session(conn)
        with self.assertRaises(AIOSSHCommandTimeoutError):
            await session.execute("sleep 999", timeout=0.05)

    async def test_upload_blocked_on_insufficient_disk_space(self):
        sftp = FakeSFTP(free_bytes=10)  # far smaller than the file we upload
        conn = FakeConnection(sftp=sftp)
        session = make_session(conn)
        local = Path("/tmp/aiossh_test_upload.bin")
        local.write_bytes(os.urandom(1000))
        with self.assertRaises(AIOSSHFileDiskFullError):
            await session.upload_file(str(local), "/remote/file.bin")

    async def test_upload_download_roundtrip(self):
        sftp = FakeSFTP()
        conn = FakeConnection(sftp=sftp)
        session = make_session(conn)
        local = Path("/tmp/aiossh_test_roundtrip.bin")
        payload = os.urandom(4096)
        local.write_bytes(payload)

        up = await session.upload_file(str(local), "/remote/roundtrip.bin")
        self.assertTrue(up["success"])

        dest = Path("/tmp/aiossh_test_roundtrip_out.bin")
        down = await session.download_file("/remote/roundtrip.bin", str(dest))
        self.assertTrue(down["success"])
        self.assertEqual(dest.read_bytes(), payload)

    async def test_stream_command_yields_lines(self):
        conn = FakeConnection(stream_lines=["a\n", "b\n", "c\n"])
        session = make_session(conn)
        lines = [line async for line in session.stream_command("tail -f x")]
        self.assertEqual(lines, ["a", "b", "c"])


# ───────────────────────── ConnectionPool ─────────────────────────

class TestConnectionPool(unittest.IsolatedAsyncioTestCase):
    async def test_max_connections_enforced_and_propagated(self):
        pool = ConnectionPool(PoolConfig(max_connections=1, min_connections=0))
        cfg = SSHConfig(host="pool-a.example.com", username="a", password="hunter2pass")

        fake_conn = FakeConnection()
        with patch("asyncssh.connect", new=AsyncMock(return_value=fake_conn)):
            s1 = await pool.get_connection(cfg)  # fills the pool (max=1)
            with self.assertRaises(AIOSSHPoolExhaustedError):
                await pool.get_connection(cfg)  # regression check: must NOT silently open a new one

    async def test_returned_connection_is_reused(self):
        pool = ConnectionPool(PoolConfig(max_connections=2, min_connections=0))
        cfg = SSHConfig(host="pool-b.example.com", username="a", password="hunter2pass")
        fake_conn = FakeConnection()
        with patch("asyncssh.connect", new=AsyncMock(return_value=fake_conn)):
            s1 = await pool.get_connection(cfg)
            await pool.return_connection(cfg, s1)
            s2 = await pool.get_connection(cfg)
        self.assertIs(s1, s2)  # reused, not a brand-new session
        self.assertEqual(pool.stats["total_connections"], 1)


# ───────────────────────── AIOSSH core (pool-exhaustion regression) ─────────

class TestAIOSSHCore(unittest.IsolatedAsyncioTestCase):
    async def test_pool_exhaustion_is_not_silently_bypassed(self):
        pool_cfg = PoolConfig(max_connections=1, min_connections=0)
        client = AIOSSH(pool_config=pool_cfg, enable_audit=False)
        fake_conn = FakeConnection()
        with patch("asyncssh.connect", new=AsyncMock(return_value=fake_conn)):
            async with client:
                await client.connect("pool-c.example.com", "root", password="hunter2pass")
                with self.assertRaises(AIOSSHPoolExhaustedError):
                    await client.connect("pool-c.example.com", "root", password="hunter2pass")


# ───────────────────────── SessionFileManager (real crypto) ─────────────

class TestSessionFileManager(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = "/tmp/aiossh_test_sessions"
        self.mgr = SessionFileManager(self.tmp_dir)

    def test_roundtrip(self):
        creds = {"host": "example.com", "username": "bob", "password": "s3cr3t!", "port": 22}
        self.mgr.create_session_file("mybox", creds, "correct horse battery staple")
        loaded = self.mgr.load_session_file("mybox", "correct horse battery staple")
        self.assertEqual(loaded, creds)

    def test_wrong_password_rejected(self):
        creds = {"host": "example.com", "username": "bob", "password": "s3cr3t!"}
        self.mgr.create_session_file("mybox2", creds, "correct horse battery staple")
        with self.assertRaises(Exception):
            self.mgr.load_session_file("mybox2", "totally wrong password!!")

    def test_tampered_file_detected(self):
        creds = {"host": "example.com", "username": "bob", "password": "s3cr3t!"}
        path = self.mgr.create_session_file("mybox3", creds, "correct horse battery staple")
        data = bytearray(path.read_bytes())
        data[-1] ^= 0xFF  # flip a bit in the ciphertext
        path.write_bytes(bytes(data))
        with self.assertRaises(Exception):
            self.mgr.load_session_file("mybox3", "correct horse battery staple")

    def test_path_traversal_in_filename_blocked(self):
        with self.assertRaises(Exception):
            self.mgr.create_session_file("../../etc/cron.d/evil", {"host": "x", "username": "y"}, "correct horse battery staple")


# ───────────────────────── DockerExecSession (the fixed bug) ─────────────

class TestDockerExecInjectionFix(unittest.IsolatedAsyncioTestCase):
    async def test_compound_command_runs_only_inside_container_via_sh_c(self):
        recorded = {}

        async def fake_execute(cmd, timeout=30, **kw):
            recorded["cmd"] = cmd
            return {"stdout": "", "stderr": "", "success": True, "exit_code": 0}

        ssh = unittest.mock.MagicMock()
        ssh.execute = AsyncMock(side_effect=fake_execute)

        docker = DockerExecSession(ssh_session=ssh, container_name="nginx-prod")
        await docker.execute("nginx -t && nginx -s reload")

        cmd = recorded["cmd"]
        # The whole compound command must appear as a single shlex-quoted
        # argument to `sh -c`, so the outer (remote-host) shell never sees
        # the unescaped "&&".
        expected_inner = shlex.quote("nginx -t && nginx -s reload")
        self.assertIn(f"sh -c {expected_inner}", cmd)
        self.assertTrue(cmd.startswith("docker exec"))

    async def test_malicious_semicolon_command_cannot_escape_container(self):
        recorded = {}

        async def fake_execute(cmd, timeout=30, **kw):
            recorded["cmd"] = cmd
            return {"stdout": "", "stderr": "", "success": True, "exit_code": 0}

        ssh = unittest.mock.MagicMock()
        ssh.execute = AsyncMock(side_effect=fake_execute)

        docker = DockerExecSession(ssh_session=ssh, container_name="nginx-prod")
        malicious = "echo hi; touch /tmp/PWNED_ON_HOST"
        await docker.execute(malicious)

        cmd = recorded["cmd"]
        # Old (buggy) behaviour would have placed a *bare*, unescaped
        # ";" in the outer command string — meaning it would run on the
        # remote host shell directly. The fixed version must keep it
        # entirely inside a single quoted sh -c argument.
        self.assertNotIn("; touch /tmp/PWNED_ON_HOST", cmd.split("sh -c", 1)[0])
        self.assertIn(shlex.quote(malicious), cmd)

    async def test_connect_exact_name_match_not_substring(self):
        # nginx-prod-2 exists; we're looking for nginx-prod. A naive
        # substring check ("nginx-prod" in stdout) would incorrectly
        # succeed here. The fix must require an exact line match.
        ssh = unittest.mock.MagicMock()
        ssh.execute = AsyncMock(return_value={"stdout": "nginx-prod-2\nother-box\n"})
        docker = DockerExecSession(ssh_session=ssh, container_name="nginx-prod")
        with self.assertRaises(ConnectionError):
            await docker.connect()

    async def test_connect_succeeds_on_exact_match(self):
        ssh = unittest.mock.MagicMock()
        ssh.execute = AsyncMock(return_value={"stdout": "nginx-prod-2\nnginx-prod\n"})
        docker = DockerExecSession(ssh_session=ssh, container_name="nginx-prod")
        await docker.connect()  # should not raise


# ───────────────────────── ParallelSCP quoting ─────────────────────────

class TestParallelSCPQuoting(unittest.IsolatedAsyncioTestCase):
    async def test_download_size_check_shell_quotes_hostile_path(self):
        recorded_cmds = []

        class FakeSession:
            async def execute(self, cmd, **kw):
                recorded_cmds.append(cmd)
                if "getsize" in cmd:
                    return {"stdout": "123\n"}
                return {"stdout": "has-split\n"}

            async def download_file(self, remote, local, **kw):
                Path(local).write_bytes(b"x" * 123)
                return {"success": True, "file_size": 123}

        scp = ParallelSCP(FakeSession(), chunk_size=1_000_000)
        hostile_path = "foo' ; touch /tmp/PWNED_VIA_SCP #"
        await scp.download(hostile_path, "/tmp/aiossh_test_scp_out.bin")

        for cmd in recorded_cmds:
            self.assertIn(shlex.quote(hostile_path), cmd)
            # The raw, unescaped hostile path must never appear bare
            # (i.e. without its surrounding quotes) in any shell command.
            self.assertNotIn("; touch /tmp/PWNED_VIA_SCP", cmd.replace(shlex.quote(hostile_path), ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
