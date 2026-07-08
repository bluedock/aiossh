"""
Proxy and Tunneling Module for AIOSSH

Provides high-level async support for:
- SOCKS5 proxy over SSH (dynamic port forwarding)
- Local port forwarding (-L)
- Remote port forwarding (-R)
- Jump host / ProxyJump support
- Easy VPN-like tunneling for applications
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Optional, AsyncIterator, Callable, Any

from asyncssh import SSHClientConnection, SSHListener

from .exceptions import AIOSSHProxyError, AIOSSHConfigurationError


@dataclass
class ProxyConfig:
    """Configuration for SSH proxy / tunneling."""
    socks_port: int = 1080
    local_forwards: list[tuple[int, str, int]] = field(default_factory=list)  # (local_port, remote_host, remote_port)
    remote_forwards: list[tuple[int, str, int]] = field(default_factory=list)  # (remote_port, local_host, local_port)
    jump_hosts: list[str] = field(default_factory=list)  # Note: Jump hosts are best configured at connect time via SSHConfig or asyncssh proxy param for ProxyJump chaining
    enable_socks: bool = True


class SSHTunnelManager:
    """
    High-level manager for SSH tunneling and proxy features.
    
    Supports creating SOCKS5 proxy, local/remote port forwards easily.
    Perfect for VPN-like usage, bypassing restrictions, or secure application access.
    """

    def __init__(self, connection: SSHClientConnection):
        self._conn = connection
        self._listeners: list[SSHListener] = []
        self._tasks: list[asyncio.Task] = []

    async def start_socks_proxy(
        self,
        port: int = 1080,
        host: str = "127.0.0.1",
        backlog: int = 100,
    ) -> None:
        """
        Start a SOCKS5 proxy server that forwards traffic through the SSH connection.
        
        This is the most common "VPN over SSH" use case.
        Applications can be configured to use 127.0.0.1:port as SOCKS5 proxy.
        """
        try:
            listener = await self._conn.forward_socks(
                listen_host=host,
                listen_port=port,
                backlog=backlog,
            )
            self._listeners.append(listener)
            print(f"[AIOSSH] SOCKS5 proxy started on {host}:{port}")
        except Exception as e:
            raise AIOSSHProxyError(f"Failed to start SOCKS5 proxy: {e}") from e

    async def add_local_forward(
        self,
        local_port: int,
        remote_host: str,
        remote_port: int,
        local_host: str = "127.0.0.1",
    ) -> None:
        """
        Local port forwarding (equivalent to ssh -L).
        Traffic to local_port is forwarded to remote_host:remote_port through SSH.
        """
        try:
            listener = await self._conn.forward_local_port(
                listen_host=local_host,
                listen_port=local_port,
                dest_host=remote_host,
                dest_port=remote_port,
            )
            self._listeners.append(listener)
            print(f"[AIOSSH] Local forward: {local_host}:{local_port} -> {remote_host}:{remote_port}")
        except Exception as e:
            raise AIOSSHProxyError(f"Failed to create local forward: {e}") from e

    async def add_remote_forward(
        self,
        remote_port: int,
        local_host: str = "127.0.0.1",
        local_port: int = 0,
    ) -> None:
        """
        Remote port forwarding (equivalent to ssh -R).
        A port on the remote server is forwarded back to local machine.
        """
        try:
            listener = await self._conn.forward_remote_port(
                listen_host="",
                listen_port=remote_port,
                dest_host=local_host,
                dest_port=local_port,
            )
            self._listeners.append(listener)
            print(f"[AIOSSH] Remote forward: *:{remote_port} -> {local_host}:{local_port}")
        except Exception as e:
            raise AIOSSHProxyError(f"Failed to create remote forward: {e}") from e

    async def close_all(self) -> None:
        """Close all active tunnels and listeners."""
        for listener in self._listeners:
            listener.close()
        self._listeners.clear()
        
        for task in self._tasks:
            if not task.done():
                task.cancel()
        self._tasks.clear()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close_all()


@asynccontextmanager
async def create_tunnel(
    connection: SSHClientConnection,
    config: Optional[ProxyConfig] = None,
) -> AsyncIterator[SSHTunnelManager]:
    """
    Async context manager for easy tunnel management.
    
    Example:
        async with create_tunnel(session.connection, config) as tunnel:
            await tunnel.start_socks_proxy(1080)
            # ... use the tunnel
    """
    tunnel = SSHTunnelManager(connection)
    config = config or ProxyConfig()
    
    try:
        if config.enable_socks:
            await tunnel.start_socks_proxy(config.socks_port)
        
        for local_port, remote_host, remote_port in config.local_forwards:
            await tunnel.add_local_forward(local_port, remote_host, remote_port)
            
        for remote_port, local_host, local_port in config.remote_forwards:
            await tunnel.add_remote_forward(remote_port, local_host, local_port)
            
        yield tunnel
    finally:
        await tunnel.close_all()
