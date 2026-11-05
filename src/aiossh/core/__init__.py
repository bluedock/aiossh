"""Core SSH client, session, and connection-pool primitives."""

from .client import AIOSSH
from .pool import ConnectionPool, PoolConfig
from .session import FastSSHSession, SSHConfig

__all__ = [
    "AIOSSH",
    "ConnectionPool",
    "FastSSHSession",
    "PoolConfig",
    "SSHConfig",
]
