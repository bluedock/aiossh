"""Fake asyncssh connection/sftp helpers shared across the test suite."""
from __future__ import annotations
import asyncio
import asyncssh


class FakeSFTPFile:
    def __init__(self, data: bytes):
        self._data = data
        self._pos = 0

    async def seek(self, offset):
        self._pos = offset

    async def read(self, size):
        chunk = self._data[self._pos:self._pos + size]
        self._pos += len(chunk)
        return chunk

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class FakeStatResult:
    def __init__(self, size):
        self.size = size


class FakeVFS:
    def __init__(self, bfree, frsize=1):
        self.bfree = bfree
        self.frsize = frsize


class FakeSFTP:
    """In-memory fake of asyncssh's SFTP client."""

    def __init__(self, remote_files=None, free_bytes=10**12):
        # remote_files: dict[str, bytes]
        self.remote_files = dict(remote_files or {})
        self.put_calls = []
        self.get_calls = []
        self.free_bytes = free_bytes

    async def statvfs(self, path):
        return FakeVFS(self.free_bytes)

    async def stat(self, path):
        if path not in self.remote_files:
            raise asyncssh.SFTPError(f"no such file: {path}")
        return FakeStatResult(len(self.remote_files[path]))

    async def put(self, local_path, remote_path):
        with open(local_path, "rb") as f:
            data = f.read()
        self.remote_files[remote_path] = data
        self.put_calls.append((local_path, remote_path))

    async def get(self, remote_path, local_path):
        if remote_path not in self.remote_files:
            raise asyncssh.SFTPError(f"no such file: {remote_path}")
        with open(local_path, "wb") as f:
            f.write(self.remote_files[remote_path])
        self.get_calls.append((remote_path, local_path))

    def open(self, path, mode="rb"):
        return FakeSFTPFile(self.remote_files.get(path, b""))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class FakeProcess:
    def __init__(self, lines):
        self._lines = lines

    @property
    def stdout(self):
        async def gen():
            for line in self._lines:
                yield line
        return gen()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class FakeConnection:
    """Drop-in fake for asyncssh.SSHClientConnection used by FastSSHSession."""

    def __init__(self, command_handler=None, sftp=None, stream_lines=None,
                 hang_forever=False):
        self._closed = False
        self.executed_commands = []
        self._command_handler = command_handler or (lambda cmd: asyncssh.SSHCompletedProcess("ok\n", "", 0))
        self._sftp = sftp or FakeSFTP()
        self._stream_lines = stream_lines or ["line1", "line2"]
        self._hang_forever = hang_forever

    def is_closed(self):
        return self._closed

    def close(self):
        self._closed = True

    async def wait_closed(self):
        return None

    def abort(self):
        self._closed = True

    async def run(self, command, check=False):
        self.executed_commands.append(command)
        if self._hang_forever:
            await asyncio.sleep(9999)
        return self._command_handler(command)

    def create_process(self, command):
        self.executed_commands.append(command)
        return FakeProcess(self._stream_lines)

    def start_sftp_client(self):
        return self._sftp
