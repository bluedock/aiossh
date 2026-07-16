"""
Telnet Support Module - AIOSSH

Provides telnet connectivity as an alternative to SSH.
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Optional


class TelnetSession:
    """Async telnet session with expect/send support."""

    def __init__(
        self,
        host: str,
        port: int = 23,
        timeout: int = 30,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.username = username
        self.password = password
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        """Establish telnet connection."""
        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port),
            timeout=self.timeout,
        )
        self._connected = True

        # Auto-login if credentials provided
        if self.username:
            await self.expect(["login:", "Username:", "user:"])
            await self.send(self.username + "\r\n")

        if self.password:
            await self.expect(["Password:", "password:"])
            await self.send(self.password + "\r\n")

            # Wait for prompt
            await asyncio.sleep(0.5)

    async def send(self, data: str) -> None:
        """Send data to the telnet server."""
        if not self._writer:
            raise ConnectionError("Not connected")
        self._writer.write(data.encode("utf-8"))
        await self._writer.drain()

    async def read_until(self, expected: str, timeout: int = 10) -> str:
        """Read until expected string is found."""
        if not self._reader:
            raise ConnectionError("Not connected")

        buffer = b""
        expected_bytes = expected.encode("utf-8")
        start_time = time.monotonic()

        while time.monotonic() - start_time < timeout:
            try:
                chunk = await asyncio.wait_for(
                    self._reader.read(4096),
                    timeout=min(1.0, timeout - (time.monotonic() - start_time)),
                )
                if not chunk:
                    break

                buffer += chunk
                if expected_bytes in buffer:
                    break
            except asyncio.TimeoutError:
                break

        return buffer.decode("utf-8", errors="replace")

    async def expect(self, patterns: list[str], timeout: int = 10) -> tuple[int, str]:
        """Wait for any of the patterns and return match index + buffer."""
        if not self._reader:
            raise ConnectionError("Not connected")

        compiled = [re.compile(p.encode("utf-8")) for p in patterns]
        buffer = b""
        start_time = time.monotonic()

        while time.monotonic() - start_time < timeout:
            try:
                chunk = await asyncio.wait_for(
                    self._reader.read(4096),
                    timeout=min(1.0, timeout - (time.monotonic() - start_time)),
                )
                if chunk:
                    buffer += chunk

                    for i, pattern in enumerate(compiled):
                        if pattern.search(buffer):
                            return i, buffer.decode("utf-8", errors="replace")
                else:
                    break
            except asyncio.TimeoutError:
                continue

        return -1, buffer.decode("utf-8", errors="replace")

    async def execute(self, command: str, timeout: int = 10) -> dict[str, object]:
        """Execute a command and return output."""
        if not self._writer or not self._reader:
            raise ConnectionError("Not connected")

        await self.send(command + "\r\n")
        await asyncio.sleep(0.3)

        output = await self.read_until("\n", timeout=timeout)

        return {
            "command": command,
            "stdout": output.strip(),
            "success": True,
        }

    async def close(self) -> None:
        """Close telnet connection."""
        self._connected = False
        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()
        self._reader = None
        self._writer = None