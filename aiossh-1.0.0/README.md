# AIOSSH

Async SSH client library for Python.

AIOSSH provides a high-level asynchronous interface for managing SSH connections,
executing commands, transferring files, and creating secure tunnels. It is built
on top of the asyncssh library and adds connection pooling, encrypted session
storage, strict input validation, rate limiting, audit logging, and support for
advanced features such as SOCKS5 proxies, port forwarding, plugins, and more.

This library is intended for developers and system administrators who need
reliable, secure, and efficient remote management capabilities in Python
applications and automation scripts.

## Features

- Asynchronous SSH connections and command execution using asyncssh
- Connection pooling with configurable limits, idle connection cleanup, and
  automatic health management
- Encrypted storage of session credentials using AES-256-GCM with HMAC-SHA512
  integrity checks and PBKDF2 key derivation (600,000 iterations)
- Rate limiting for connections and commands using sliding window algorithm
  with exponential backoff for repeat violations
- Comprehensive input validation (hosts, ports, usernames, commands, paths)
  with protection against SSRF, command injection, and path traversal
- Support for tunneling: SOCKS5 proxy, local port forwarding (-L), and remote
  port forwarding (-R)
- Plugin system for intercepting and modifying connection, command, and file
  transfer events
- Priority-based command queue with support for batch execution
- Webhook notifications for events (Discord, Telegram, and custom HTTP endpoints)
- Telnet session support for legacy systems
- Execution of commands inside Docker containers and Kubernetes pods via SSH
  or API
- High-speed parallel chunked file transfers (SCP/SFTP) with progress reporting
  and optional speed throttling
- Session recording and replay for auditing and debugging
- Structured logging to local files and external systems (Elasticsearch, Loki,
  Datadog, Syslog)
- Full static type hints and compatibility with strict type checkers
- Context manager support for automatic resource cleanup
- More than 40 specific exception classes for precise error handling
- Retry and timing decorators for resilience and observability

## Requirements

- Python 3.12 or newer
- asyncssh >= 2.14.0 and < 3.0.0
- cryptography >= 42.0.0
- aiofiles >= 23.0.0
- orjson >= 3.9.0 (orjson is recommended for performance; the library falls
  back to the standard library json module if orjson is not available)

Optional dependencies for additional features:
- aiohttp: required for Kubernetes exec support and webhook delivery

## Installation

Install from PyPI:

```bash
pip install aiossh
```

For development and testing:

```bash
pip install aiossh[dev]
```

To enable Kubernetes exec and webhook functionality:

```bash
pip install aiossh aiohttp
```

## Quick Start

The following example demonstrates basic usage with an async context manager.

```python
import asyncio
from aiossh import AIOSSH

async def main() -> None:
    async with AIOSSH() as client:
        session = await client.connect(
            host="192.0.2.10",
            username="admin",
            password="your-password",  # Prefer SSH keys in production
            port=22,
        )

        result = await client.execute_command(session, "uptime")
        print(result["stdout"])

        await client.close_session(session)

if __name__ == "__main__":
    asyncio.run(main())
```

For tunneling examples and advanced usage, refer to the documentation in the
source code or the project wiki.

## Core Components

### AIOSSH Client

The AIOSSH class is the primary entry point. It manages a connection pool,
rate limiters, audit logging, and optional encrypted session storage.

Key methods:
- connect(): Establish a new SSH session (uses pool by default)
- execute_command(): Execute a command on a session with rate limiting
- execute_on_all() / execute_on_multiple(): Run commands across sessions
- temporary_session(): Context manager for short-lived connections
- save_session_to_file() / load_session_from_file(): Encrypted credential storage
- close_session() / close_all(): Resource cleanup

### Sessions

FastSSHSession provides direct control over a single SSH connection. It supports
command execution, file upload/download, streaming output, and exposes the
underlying asyncssh connection for advanced tunneling use cases.

### Connection Pool

ConnectionPool implements strict limits on concurrent connections, reuses idle
connections, and performs periodic cleanup of stale entries. Configuration is
done via PoolConfig.

### Tunneling and Proxy

ProxyConfig and create_tunnel (async context manager) allow creation of:
- SOCKS5 proxy (dynamic port forwarding)
- Local port forwards (-L semantics)
- Remote port forwards (-R semantics)

These features enable secure access to internal services through an SSH
bastion host.

### Security

- All user-supplied input passes through whitelist-based validators
- Private and reserved IP ranges are blocked by default (SSRF protection)
- Dangerous command patterns are rejected unless explicitly allowed
- Session files are encrypted at rest with authenticated encryption
- Audit log entries are individually signed with HMAC-SHA512
- Sensitive material is wiped from memory after use where possible
- Rate limiters protect against brute-force and resource exhaustion

### Plugins

The plugin system allows registration of hooks that run before and after
connection establishment, command execution, and file transfers. Plugins can
cancel operations or modify context objects.

Built-in plugins include command logging and basic validation. Custom plugins
are created by subclassing BasePlugin.

### Error Handling

All errors raised by the library are subclasses of AIOSSHException. Each
exception carries a machine-readable code, optional structured details, and
a UTC timestamp. Specific subclasses exist for connection failures,
authentication problems, command errors, file transfer issues, security
violations, and resource exhaustion.

## Development

The source layout follows the src/ package layout recommended for modern
Python projects.

To run static analysis and tests (after installing dev dependencies):

```bash
ruff check .
mypy src/aiossh
pytest
```

The library targets Python 3.12+ and uses modern async features including
asyncio.TaskGroup.

No test suite is included in this release. Comprehensive tests are planned
for subsequent versions.

## License

This project is licensed under the MIT License. See the LICENSE file for
details.

## Acknowledgments

This library is built on the excellent asyncssh package. Cryptographic
primitives are provided by the cryptography library.

Contributions and feedback are welcome via the project issue tracker.
