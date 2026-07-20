"""
Minimal fake `asyncssh` used ONLY for exercising aiossh's logic in this
sandbox (no real network / no real asyncssh package available offline).

Provides just enough surface area (exception types + a monkeypatchable
`connect`) for aiossh.core.session / aiossh.transfer.scp / aiossh.core.pool to run
against fully in-memory fake connections.
"""
from __future__ import annotations
import asyncio


class DisconnectError(Exception):
    pass


class PermissionDenied(Exception):
    pass


class HostKeyNotVerifiable(Exception):
    pass


class SFTPError(Exception):
    pass


class SSHCompletedProcess:
    def __init__(self, stdout="", stderr="", exit_status=0):
        self.stdout = stdout
        self.stderr = stderr
        self.exit_status = exit_status
        self.stdout_was_truncated = False
        self.stderr_was_truncated = False


class SSHClientConnection:
    """Overridden per-test via FakeConnection subclasses."""
    pass


class SSHListener:
    def close(self):
        pass

    async def wait_closed(self):
        pass


async def connect(**kwargs):
    raise NotImplementedError("tests must monkeypatch asyncssh.connect")
