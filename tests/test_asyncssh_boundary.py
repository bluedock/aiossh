"""
asyncssh boundary regression tests.

These scenarios lock down the layer between aiossh and the underlying
``asyncssh`` library.  Historically a class of bugs existed where aiossh
handed requests to ``asyncssh`` *directly* -- either forwarding keyword
arguments that a modern asyncssh (>= 2.14) does not accept, or letting an
unvalidated command/host reach asyncssh before aiossh's own validation ran.
Those bugs surfaced as opaque ``TypeError`` / "'bool' object is not
iterable" style failures on every request.

The generic test double in ``tests/fakes.py`` accepts ``**kwargs`` and is
therefore too permissive to catch these regressions.  The fake here mirrors
the *strict* keyword-only signature of ``asyncssh.connect`` for exactly the
parameters aiossh is allowed to use, so any stray/renamed/removed argument
raises ``TypeError`` and fails the test.
"""
from __future__ import annotations

import unittest

import asyncssh

from aiossh.core import AIOSSH
from aiossh.core.session import FastSSHSession, SSHConfig
from aiossh.exceptions import (
    AIOSSHInvalidParameterError,
    AIOSSHSecurityError,
    AIOSSHValidationError,
)

from fakes import FakeConnection


class _StrictConnect:
    """Callable mirroring the exact asyncssh.connect kwargs aiossh may use.

    Keyword-only with NO ``**kwargs`` catch-all: if aiossh passes anything
    outside this whitelist (e.g. the old ``compression=`` bool, a
    ``connect_timeout=``, or a bare ``proxy=`` string) Python raises
    ``TypeError`` and the calling test fails -- reproducing the historical
    "passed straight to asyncssh" bug as a hard failure.
    """

    def __init__(self, connection=None):
        self._connection = connection
        self.calls: list[dict] = []

    async def __call__(
        self,
        *,
        host,
        port,
        username,
        password=None,
        client_keys=None,
        compression_algs=None,
        known_hosts="<<unset>>",
        keepalive_interval=None,
        encryption_algs=None,
        kex_algs=None,
        mac_algs=None,
        tunnel=None,
    ):
        self.calls.append(
            {
                "host": host,
                "port": port,
                "username": username,
                "password": password,
                "client_keys": client_keys,
                "compression_algs": compression_algs,
                "known_hosts": known_hosts,
                "keepalive_interval": keepalive_interval,
                "encryption_algs": encryption_algs,
                "kex_algs": kex_algs,
                "mac_algs": mac_algs,
                "tunnel": tunnel,
            }
        )
        return self._connection if self._connection is not None else FakeConnection()


class AsyncSSHBoundaryTest(unittest.IsolatedAsyncioTestCase):
    def _patch_connect(self, connection=None) -> _StrictConnect:
        strict = _StrictConnect(connection)
        original = asyncssh.connect
        asyncssh.connect = strict
        self.addCleanup(lambda: setattr(asyncssh, "connect", original))
        return strict

    # ── Only valid asyncssh kwargs cross the boundary ────────────────────

    async def test_connect_uses_only_whitelisted_kwargs(self):
        strict = self._patch_connect()
        session = FastSSHSession(
            SSHConfig(host="server.example.com", username="admin", password="secret")
        )
        # If aiossh forwarded any unknown/renamed kwarg, _StrictConnect would
        # have raised TypeError here.
        await session.connect()
        self.assertEqual(len(strict.calls), 1)
        call = strict.calls[0]
        self.assertEqual(call["host"], "server.example.com")
        self.assertEqual(call["port"], 22)
        self.assertEqual(call["username"], "admin")
        self.assertEqual(call["password"], "secret")

    async def test_compression_is_sent_as_algs_list_not_bool(self):
        strict = self._patch_connect()
        session = FastSSHSession(
            SSHConfig(host="h.example.com", username="u", compression=True)
        )
        await session.connect()
        algs = strict.calls[0]["compression_algs"]
        # Must be an algorithm list (asyncssh >= 2.14), never a bare bool.
        self.assertIsInstance(algs, list)
        self.assertNotIsInstance(algs, bool)

    async def test_known_hosts_default_is_none_not_bool_or_callable(self):
        strict = self._patch_connect()
        session = FastSSHSession(SSHConfig(host="h.example.com", username="u"))
        await session.connect()
        kh = strict.calls[0]["known_hosts"]
        # A plain bool / callable would trigger asyncssh's
        # "'bool' object is not iterable"; None disables verification safely.
        self.assertIsNone(kh)
        self.assertNotIsInstance(kh, bool)
        self.assertFalse(callable(kh))

    async def test_proxy_string_is_not_forwarded_as_tunnel(self):
        strict = self._patch_connect()
        session = FastSSHSession(
            SSHConfig(host="h.example.com", username="u", proxy="jump-host:22")
        )
        await session.connect()
        # asyncssh has no ``proxy`` param; a legacy string must be ignored,
        # not smuggled through as ``tunnel``.
        self.assertIsNone(strict.calls[0]["tunnel"])

    async def test_proxy_connection_is_forwarded_as_tunnel(self):
        jump = asyncssh.SSHClientConnection()
        strict = self._patch_connect()
        session = FastSSHSession(
            SSHConfig(host="h.example.com", username="u", proxy=jump)
        )
        await session.connect()
        self.assertIs(strict.calls[0]["tunnel"], jump)

    async def test_security_algorithms_are_passed_as_lists(self):
        strict = self._patch_connect()
        session = FastSSHSession(SSHConfig(host="h.example.com", username="u"))
        await session.connect()
        call = strict.calls[0]
        for key in ("encryption_algs", "kex_algs", "mac_algs"):
            self.assertIsInstance(call[key], list, key)
            self.assertTrue(call[key], key)

    # ── Validation happens BEFORE anything reaches asyncssh ──────────────

    async def test_invalid_username_never_reaches_asyncssh(self):
        strict = self._patch_connect()
        async with AIOSSH() as client:
            with self.assertRaises(AIOSSHValidationError):
                await client.connect("server.example.com", "bad user!")
        # The offending request must be rejected locally, never dialed out.
        self.assertEqual(strict.calls, [])

    async def test_invalid_host_never_reaches_asyncssh(self):
        strict = self._patch_connect()
        async with AIOSSH() as client:
            with self.assertRaises(AIOSSHValidationError):
                await client.connect("not a host!!", "admin")
        self.assertEqual(strict.calls, [])

    async def test_invalid_port_rejected_before_session_constructed(self):
        strict = self._patch_connect()
        with self.assertRaises(AIOSSHInvalidParameterError):
            FastSSHSession(SSHConfig(host="h.example.com", username="u", port=70000))
        self.assertEqual(strict.calls, [])

    # ── Commands are validated before being run over asyncssh ────────────

    async def test_dangerous_command_not_run_on_connection(self):
        conn = FakeConnection()
        self._patch_connect(conn)
        session = FastSSHSession(SSHConfig(host="h.example.com", username="u"))
        await session.connect()
        with self.assertRaises(AIOSSHSecurityError):
            await session.execute("rm -rf /")
        # Nothing dangerous should ever have been handed to connection.run().
        self.assertEqual(conn.executed_commands, [])

    async def test_injection_indicator_not_run_on_connection(self):
        conn = FakeConnection()
        self._patch_connect(conn)
        session = FastSSHSession(SSHConfig(host="h.example.com", username="u"))
        await session.connect()
        with self.assertRaises(AIOSSHSecurityError):
            await session.execute("echo $(cat /etc/passwd)")
        self.assertEqual(conn.executed_commands, [])

    async def test_valid_command_reaches_connection_once(self):
        conn = FakeConnection()
        self._patch_connect(conn)
        session = FastSSHSession(SSHConfig(host="h.example.com", username="u"))
        await session.connect()
        result = await session.execute("echo hi")
        self.assertEqual(conn.executed_commands, ["echo hi"])
        self.assertTrue(result["success"])

    async def test_sudo_prefix_applied_before_reaching_connection(self):
        conn = FakeConnection()
        self._patch_connect(conn)
        session = FastSSHSession(SSHConfig(host="h.example.com", username="u"))
        await session.connect()
        await session.execute("whoami", sudo=True)
        self.assertEqual(conn.executed_commands, ["sudo -n whoami"])

    async def test_execute_on_disconnected_session_does_not_touch_asyncssh(self):
        conn = FakeConnection()
        self._patch_connect(conn)
        session = FastSSHSession(SSHConfig(host="h.example.com", username="u"))
        # Never connected -> must raise, never call run().
        from aiossh.exceptions import AIOSSHSessionExpiredError

        with self.assertRaises(AIOSSHSessionExpiredError):
            await session.execute("echo hi")
        self.assertEqual(conn.executed_commands, [])


if __name__ == "__main__":
    unittest.main()
