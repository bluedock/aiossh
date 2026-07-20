"""
Proxy and Tunneling Module - v1.1.0
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Optional, AsyncIterator

# SSHListener is part of asyncssh's public API but is not guaranteed to be
# exported at the top level in every build/version.  Import it defensively so
# that a missing export does not prevent the rest of the module from loading.
from asyncssh import SSHClientConnection

try:
    from asyncssh import SSHListener as _SSHListenerType
except ImportError:
    _SSHListenerType = object  # type: ignore[assignment,misc]

from ..exceptions import AIOSSHProxyError


@dataclass
class ProxyConfig:
    socks_port: int = 1080
    local_forwards: list[tuple[int, str, int]] = field(default_factory=list)
    remote_forwards: list[tuple[int, str, int]] = field(default_factory=list)
    enable_socks: bool = True


class SSHTunnelManager:
    def __init__(self, connection: SSHClientConnection):
        self._conn = connection
        self._listeners: list[_SSHListenerType] = []

    async def start_socks_proxy(self, port: int = 1080, host: str = "127.0.0.1"):
        try:
            listener = await self._conn.forward_socks(listen_host=host, listen_port=port)
            self._listeners.append(listener)
        except Exception as e:
            raise AIOSSHProxyError(f"Failed to start SOCKS5 proxy: {e}") from e

    async def add_local_forward(self, local_port: int, remote_host: str, remote_port: int):
        try:
            listener = await self._conn.forward_local_port(
                listen_host="127.0.0.1", listen_port=local_port,
                dest_host=remote_host, dest_port=remote_port
            )
            self._listeners.append(listener)
        except Exception as e:
            raise AIOSSHProxyError(f"Failed to create local forward: {e}") from e

    async def close_all(self):
        for listener in self._listeners:
            listener.close()
            if hasattr(listener, "wait_closed"):
                try:
                    await listener.wait_closed()
                except Exception:
                    pass
        self._listeners.clear()

    async def __aenter__(self): return self
    async def __aexit__(self, *args): await self.close_all()


@asynccontextmanager
async def create_tunnel(connection: SSHClientConnection, config: Optional[ProxyConfig] = None) -> AsyncIterator[SSHTunnelManager]:
    tunnel = SSHTunnelManager(connection)
    config = config or ProxyConfig()
    try:
        if config.enable_socks:
            await tunnel.start_socks_proxy(config.socks_port)
        for lp, rh, rp in config.local_forwards:
            await tunnel.add_local_forward(lp, rh, rp)
        yield tunnel
    finally:
        await tunnel.close_all()
