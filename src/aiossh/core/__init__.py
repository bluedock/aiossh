"""Core SSH client, session, and connection-pool primitives."""

from .client import AIOSSH
from .session import FastSSHSession, SSHConfig
from .pool import ConnectionPool, PoolConfig

__all__ = [
    "AIOSSH",
    "FastSSHSession",
    "SSHConfig",
    "ConnectionPool",
    "PoolConfig",
]
