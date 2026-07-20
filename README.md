# AIOSSH

**English** · [فارسی (Persian)](README.fa.md) · [العربية (Arabic)](README.ar.md)

AIOSSH is an asynchronous SSH client library for Python, built on top of
[`asyncssh`](https://asyncssh.readthedocs.io/). It provides a high-level
client with connection pooling, input validation, encrypted credential
storage, SSH tunneling, high-speed parallel file transfer, session
recording/replay, Docker command execution, and webhook notification
helpers.

Current version: **1.1.3**. See [`CHANGELOG.md`](CHANGELOG.md) for a
detailed history of changes.

---

## Table of Contents

- [Requirements](#requirements)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Project Structure](#project-structure)
- [Features](#features)
- [API Reference](#api-reference)
- [Examples](#examples)
- [Security Considerations](#security-considerations)
- [Testing](#testing)
- [Development](#development)
- [License](#license)

---

## Requirements

- Python 3.11 or later
- Cross-platform: Linux, macOS, and Windows

Runtime dependencies (installed automatically):

| Package | Used for |
|---|---|
| `asyncssh` | SSH/SFTP connections, tunneling |
| `cryptography` | AES-256-GCM / PBKDF2 encrypted session storage |
| `orjson` | Faster JSON serialization where available (optional at runtime: `security/file_manager.py` and `integrations/replay.py` fall back to the standard-library `json` module if `orjson` is not importable) |

`aiohttp` is required only for webhook delivery and is installed via the
optional `web` extra:

```bash
pip install "aiossh[web]"
```

Without `aiohttp` installed, `DiscordWebhook.send()`, `TelegramWebhook.send()`,
and `WebhookManager`'s HTTP delivery return `False` / are skipped rather than
raising an exception.

---

## Installation

```bash
pip install aiossh

# With webhook support (Discord/Telegram/generic HTTP webhooks)
pip install "aiossh[web]"

# Development install (linting, type checking, tests)
pip install -e ".[dev]"
```

---

## Quick Start

```python
import asyncio
from aiossh import AIOSSH

async def main():
    async with AIOSSH() as client:
        session = await client.connect("server.example.com", "admin", password="secret")
        result = await client.execute_command(session, "uptime")
        print(result["stdout"])

asyncio.run(main())
```

See [`examples/01_basic_connect_and_execute.py`](examples/01_basic_connect_and_execute.py)
for a complete version, including `sudo` execution and running a command
against every active session at once.

---

## Project Structure

```
aiossh-1.1.3/
├── src/aiossh/
│   ├── __init__.py             # Public API surface (lazy-loaded exports)
│   ├── core/                   # Core client, session, and pooling
│   │   ├── __init__.py
│   │   ├── client.py           # AIOSSH: high-level client facade
│   │   ├── session.py          # FastSSHSession, SSHConfig
│   │   └── pool.py             # ConnectionPool, PoolConfig
│   ├── security/               # Validation, policy, and encrypted storage
│   │   ├── __init__.py
│   │   ├── config.py           # SecurityConfig, RateLimiter, AuditLogger, SecureMemory, SecureChannel
│   │   ├── validators.py       # InputValidator (whitelist validation, SSRF/path/command checks)
│   │   └── file_manager.py     # SessionFileManager (AES-256-GCM encrypted session storage)
│   ├── transfer/               # High-speed file transfer
│   │   ├── __init__.py
│   │   └── scp.py              # ParallelSCP, TransferProgress
│   ├── integrations/           # Optional integrations
│   │   ├── __init__.py
│   │   ├── proxy.py            # ProxyConfig, SSHTunnelManager, create_tunnel
│   │   ├── webhook.py          # WebhookManager, DiscordWebhook, TelegramWebhook
│   │   ├── docker.py           # DockerExecSession
│   │   └── replay.py           # SessionRecorder, SessionReplayer
│   ├── utils/                  # Internal utilities
│   │   ├── __init__.py
│   │   └── decorators.py       # retry, timing (not part of the public __all__ export)
│   ├── exceptions.py           # Exception hierarchy
│   └── py.typed
│
├── examples/                # Six runnable usage examples (see below)
├── tests/                   # Offline unittest suite (228 tests, no network required)
├── README.md
├── CHANGELOG.md
├── LICENSE
└── pyproject.toml
```

---

## Features

- Asynchronous SSH connection management and command execution, including
  `sudo` execution, batch execution (parallel or sequential), and
  line-by-line output streaming with timeout protection.
- Connection pooling with configurable minimum/maximum connection limits,
  idle-connection reuse, periodic cleanup of stale or expired connections,
  and per-pool connection-rate limiting.
- Whitelist-based input validation for hosts, ports, usernames, passwords,
  commands, and paths — including SSRF protection (private/reserved IP
  ranges are blocked by default) and path-traversal detection.
- Encrypted session credential storage using AES-256-GCM with
  PBKDF2-HMAC-SHA512 key derivation (600,000 iterations) and an
  independent HMAC-SHA512 integrity check over the stored file.
- SFTP file upload and download, with optional resume support and a
  best-effort remote disk-space check before uploading.
- High-speed file transfer via chunked, parallel upload/download
  (`ParallelSCP`), with progress callbacks and optional bandwidth
  throttling.
- SOCKS5 proxying and local TCP port forwarding over an established SSH
  connection.
- Session recording and replay, with optional gzip compression of the
  recorded event stream.
- Command execution inside Docker containers over an existing SSH
  connection, with the command shell-escaped and executed inside the
  container via `sh -c`.
- Webhook notification helpers for Discord and Telegram, plus a
  general-purpose callback/webhook event-dispatch registry.
- A hierarchy of more than 25 specific exception types for precise error
  handling, each carrying a machine-readable `code` and optional
  structured `details`.
- Cross-platform support (Linux, macOS, Windows) on Python 3.11+.

---

## API Reference

All public classes and functions are re-exported from the top-level
`aiossh` package (e.g. `from aiossh import AIOSSH, ParallelSCP`). They are
loaded lazily on first access.

### Core Client — `AIOSSH`

The main high-level entry point. Wraps session creation, connection
pooling, rate limiting, and encrypted-session-file helpers.

```python
AIOSSH(
    *,
    master_password: str | None = None,   # required to use save/load_session_*_file
    security_config: SecurityConfig | None = None,
    pool_config: PoolConfig | None = None,
    session_dir: str = "~/.aiossh/sessions",
    enable_audit: bool = True,
)
```

| Method | Description |
|---|---|
| `async connect(host, username, *, password=None, port=22, private_key_path=None, session_name=None, use_pool=True, timeout=30) -> FastSSHSession` | Validates and opens (or reuses, via the pool) an SSH session. If `session_name` is given, the session is tracked under that name for later lookup. |
| `async execute_command(session_id, command, *, timeout=30, sudo=False, **kwargs) -> dict` | Runs a command on a session referenced by name or by the `FastSSHSession` object itself. Subject to a global command-rate limit (50 commands/second by default). |
| `async execute_on_all(command, **kwargs) -> dict[str, dict]` | Runs a command on every named active session; per-session failures are captured in the result rather than raised. |
| `async close_session(session_id)` | Closes (or returns to the pool) a single named session. |
| `async close_all()` | Closes/releases every tracked session and shuts down the connection pool. Called automatically on `async with` exit. |
| `async save_session_to_file(session_name, host, username, password, port=22)` | Persists credentials to an encrypted session file. Requires `master_password` at construction. |
| `async load_session_from_file(session_name) -> FastSSHSession` | Decrypts a saved session file and connects using its credentials. |
| `list_saved_sessions() -> list[str]` | Lists session names available on disk. |
| `list_active_sessions() -> list[dict]` | Lists in-memory active sessions with host and connection status. |

`AIOSSH` also applies two internal `RateLimiter` instances: connection
attempts are limited to 30 per 60 seconds, and command executions to 50
per second, raising `AIOSSHRateLimitError` when exceeded.

### Session — `FastSSHSession`, `SSHConfig`

`SSHConfig` is an immutable (`frozen=True`) dataclass describing a single
connection:

```python
SSHConfig(
    host, username, port=22, password=None, private_key_path=None,
    timeout=30, keepalive_interval=30,
    security=SecurityConfig(), compression=True,
    host_key_callback=None, proxy=None,
)
```

`FastSSHSession` wraps a live connection created from an `SSHConfig`:

| Method / Property | Description |
|---|---|
| `async connect()` | Opens the underlying `asyncssh` connection. |
| `is_connected` (property) | `True` if a live, unclosed connection exists. |
| `connection` (property) | The underlying `asyncssh.SSHClientConnection`, for advanced use (e.g. manual tunneling). |
| `stats` (property) | Dict of commands executed, bytes transferred, errors, reconnects, uptime, host, and username. |
| `async execute(command, *, timeout=30, sudo=False, allow_dangerous=False) -> dict` | Runs a single command; returns `stdout`, `stderr`, `exit_code`, `success`, `execution_time`, and `truncated`. |
| `async execute_batch(commands, *, parallel=True, max_concurrent=5, **kwargs) -> list[dict]` | Runs multiple commands, in parallel (bounded by `max_concurrent`) or sequentially; per-command failures are captured in the returned list rather than raised. |
| `async upload_file(local_path, remote_path, *, check_disk_space=True) -> dict` | SFTP upload with an optional pre-flight remote disk-space check. |
| `async download_file(remote_path, local_path, *, resume=False) -> dict` | SFTP download; with `resume=True`, continues an interrupted download by seeking past the bytes already present locally. |
| `async stream_command(command, timeout=300) -> AsyncIterator[str]` | Yields stdout line by line as the command runs, under a timeout. |
| `async close()` | Closes the connection, with a forced abort if graceful close does not complete within 5 seconds. |

The default host-key handler accepts all host keys. See
[Security Considerations](#security-considerations) before using this in
production.

### Connection Pool — `ConnectionPool`, `PoolConfig`

```python
PoolConfig(
    max_connections: int = 10,
    min_connections: int = 2,
    max_idle_time: int = 300,     # seconds
    cleanup_interval: int = 60,   # seconds
    max_lifetime: int = 3600,     # seconds
)
```

| Method | Description |
|---|---|
| `async start()` | Starts the background cleanup task. |
| `async ensure_min_connections(sample_config=None)` | Best-effort warm-up to `min_connections` idle connections for the given configuration. |
| `async get_connection(config) -> FastSSHSession` | Returns an idle connection if one is available and healthy, otherwise opens a new one (subject to `max_connections`). Raises `AIOSSHPoolExhaustedError` if the pool is full. |
| `async return_connection(config, connection)` | Returns a connection to the idle pool, or closes it if it is no longer healthy. |
| `async close()` | Stops the cleanup task and closes every pooled connection. |
| `stats` (property) | Dict of total/idle/in-use connection counts, configured limits, and current connection rate. |

Connections are pooled per `username@host:port`. Idle connections beyond
`max_idle_time`, or any connection beyond `max_lifetime`, are closed by
the periodic cleanup task.

### Input Validation — `InputValidator`

Static/class methods; all raise `AIOSSHInvalidParameterError` or
`AIOSSHSecurityError` on invalid input rather than silently sanitizing.

| Method | Description |
|---|---|
| `validate_host(host, *, allow_private=False) -> str` | Validates a hostname or IP; rejects private/reserved IPv4 and IPv6 ranges unless `allow_private=True`. |
| `validate_port(port) -> int` | Validates that the port is an integer in the 1–65535 range and returns it as an `int`. |
| `validate_username(username) -> str` | Validates against a POSIX-style username pattern. |
| `validate_password(password) -> str` | Rejects empty passwords, passwords over 128 characters, and null bytes. |
| `validate_command(command, *, allow_dangerous=False) -> str` | Rejects commands over 8192 characters, null bytes, a fixed set of destructive shell patterns (e.g. `rm -rf /`, fork bombs), and common injection indicators (`` $( `` , `` ` `` , `/dev/tcp`, etc.) unless `allow_dangerous=True`. |
| `validate_path(path) -> str` | Rejects paths over 4096 characters, null bytes, and any literal `..` path segment. Expands `~` but does not resolve the path against the local filesystem (paths may be remote). |
| `validate_session_name(name) -> str` | Restricts session names to `[a-zA-Z0-9_-]`, 1–64 characters, with no path separators. |
| `sanitize_string(value, max_length=256) -> str` | Strips null bytes and whitespace, truncates to `max_length`. |
| `shell_escape(argument) -> str` | `shlex.quote()` wrapper for constructing shell-safe arguments. |

### Encrypted Session Storage — `SessionFileManager`

```python
SessionFileManager(session_dir: str = "~/.aiossh/sessions")
```

Stores credentials as `<name>.seshn` files (mode `0600`, directory mode
`0700`) encrypted with AES-256-GCM. The encryption key is derived from the
master password with PBKDF2-HMAC-SHA512 (600,000 iterations, 32-byte
random salt), and an independent HMAC-SHA512 over `salt + nonce +
ciphertext` is verified before decryption is attempted.

| Method | Description |
|---|---|
| `create_session_file(filename, credentials, master_password) -> Path` | Encrypts and writes `credentials` (a dict) to disk atomically (write to a temp file, then rename). |
| `load_session_file(filename, master_password) -> dict` | Verifies the HMAC, then decrypts and returns the stored credentials. Raises `AIOSSHIntegrityError` on tampering and `AIOSSHSessionCorruptedError` on a malformed file. |
| `list_sessions() -> list[str]` | Lists stored session names. |
| `delete_session(filename) -> bool` | Deletes a stored session file if it exists. |

### Security Utilities

- **`SecurityConfig`** — dataclass listing the allowed SSH ciphers, key
  exchange algorithms, and MACs used when opening a connection. Defaults
  to a modern, AEAD-preferring set (e.g. `aes256-gcm@openssh.com`,
  `curve25519-sha256`, `hmac-sha2-256-etm@openssh.com`).
- **`RateLimiter(max_requests, window_seconds)`** — async sliding-window
  rate limiter with `await acquire() -> bool` and a `current_rate`
  property. Used internally by `AIOSSH` and `ConnectionPool`; can also be
  used directly.
- **`AuditLogger`** — exposes `async log(event, data=None)`. The default
  implementation is a no-op; it is used internally by `FastSSHSession` and
  `AIOSSH` to mark `session_connect` / `session_close` events, and is
  intended to be subclassed or replaced to integrate with an external
  logging or audit system.
- **`SecureMemory`** — `secure_clear(buffer: bytearray)` overwrites a
  buffer with random bytes rather than leaving zeroed/plaintext data in
  memory; `secure_compare(a, b)` performs a constant-time byte comparison
  via `hmac.compare_digest`.
- **`SecureChannel`** — reserved for future secure-channel functionality.
  It is present in the public API for forward compatibility but currently
  has no behavior.

### SSH Tunneling — `ProxyConfig`, `SSHTunnelManager`, `create_tunnel`

```python
ProxyConfig(
    socks_port: int = 1080,
    local_forwards: list[tuple[int, str, int]] = [],  # (local_port, remote_host, remote_port)
    remote_forwards: list[tuple[int, str, int]] = [],
    enable_socks: bool = True,
)
```

| Method | Description |
|---|---|
| `SSHTunnelManager(connection).start_socks_proxy(port=1080, host="127.0.0.1")` | Starts a local SOCKS5 proxy tunneled through the SSH connection. |
| `SSHTunnelManager(connection).add_local_forward(local_port, remote_host, remote_port)` | Forwards a local TCP port to a host/port reachable from the remote server. |
| `SSHTunnelManager(connection).close_all()` | Closes every listener opened through the manager. |
| `create_tunnel(connection, config=None)` | Async context manager that starts the SOCKS proxy (if `enable_socks`) and every entry in `local_forwards` from a single `ProxyConfig`, and tears them down on exit. |

`ProxyConfig.remote_forwards` is present for forward compatibility but is
not yet consumed by `create_tunnel()` or `SSHTunnelManager` in this
release — only SOCKS5 proxying and local port forwarding are currently
implemented.

### Webhook Notifications — `WebhookManager`, `DiscordWebhook`, `TelegramWebhook`

`DiscordWebhook(webhook_url)` and `TelegramWebhook(bot_token, chat_id)`
each expose `async send(message, ...) -> bool` and can be used directly,
independently of the rest of the library, as shown in
[`examples/05_docker_exec_and_discord_webhook.py`](examples/05_docker_exec_and_discord_webhook.py).

`WebhookManager` is a general-purpose event registry with four named
events: `on_connect`, `on_disconnect`, `on_command_complete`, `on_error`.

| Method | Description |
|---|---|
| `on(event, callback)` | Registers a local (sync or async) callback for an event. |
| `add_webhook(event, url)` | Registers an HTTP endpoint to receive a JSON POST when the event fires. |
| `async trigger(event, data)` | Invokes all registered callbacks and posts to all registered webhook URLs for `event`. Requires `aiohttp` (the `web` extra) for HTTP delivery; local callbacks run regardless. |

`WebhookManager.trigger()` is not called automatically by `AIOSSH` or
`FastSSHSession`; the application is responsible for calling it at the
appropriate point (e.g. after a successful `connect()` or a failed
command).

### Docker Exec — `DockerExecSession`

```python
DockerExecSession(ssh_session: FastSSHSession, container_name: str, sudo: bool = False)
```

| Method | Description |
|---|---|
| `async connect()` | Verifies the target container is running (exact name match against `docker ps` output) before allowing command execution. |
| `async execute(command, timeout=30, workdir="/") -> dict` | Shell-escapes `command` and runs it inside the container via `docker exec ... sh -c '<command>'`, so compound commands (`&&`, `;`, `|`) are interpreted once, by the container's shell. |
| `is_connected` (property) | Delegates to the underlying SSH session. |
| `async close()` | No-op; the underlying SSH session owns the connection lifecycle. |

### Session Recording & Replay — `SessionRecorder`, `SessionReplayer`

`SessionRecorder(session_id, storage_dir="~/.aiossh/recordings")` records
a timestamped event stream (`session_start`, `command`, `result`,
`session_end`) to a `.iossh` file (`.iossh.gz` if compressed).

| Method | Description |
|---|---|
| `start()` | Begins recording. |
| `record_command(command)` | Records a command event. |
| `record_result(result)` | Records a result event. |
| `stop()` | Ends recording. |
| `async save(compress=True) -> str` | Writes the recording to disk (gzip-compressed by default) and returns the file path. |

`SessionReplayer(filepath)` loads a recording and replays it with the
original relative timing.

| Method | Description |
|---|---|
| `async load()` | Reads and decompresses (if applicable) the recording. |
| `async replay(speed=1.0, callback=None)` | Replays events, sleeping between them according to their original timestamps divided by `speed`; invokes `callback(event_type, data)` for each event. |
| `get_summary() -> dict` | Returns total event count, command count, and the list of executed commands. |

### High-Speed Parallel Transfer — `ParallelSCP`, `TransferProgress`

```python
ParallelSCP(session: FastSSHSession, chunk_size: int = 8 * 1024 * 1024, max_parallel: int = 4)
```

| Method | Description |
|---|---|
| `on_progress(callback)` | Registers a callback invoked with a `TransferProgress` instance as the transfer proceeds. |
| `async upload(local_path, remote_path, *, max_speed_mbps=0) -> dict` | Splits the local file into chunks, uploads them concurrently (bounded by `max_parallel`), and reassembles them remotely with `cat`. Falls back to a single `upload_file()` call for files smaller than `chunk_size`. `max_speed_mbps=0` means unthrottled. |
| `async download(remote_path, local_path, *, max_speed_mbps=0) -> dict` | Splits the remote file with the remote `split` utility (probed for availability first; falls back to a plain download if unavailable) and downloads chunks concurrently. Verifies the reassembled file's size before cleaning up remote chunk files; raises `AIOSSHFileDownloadError` if any chunk fails or the final size does not match. |

`TransferProgress` is a dataclass with `total_bytes`, `transferred`,
`speed_mbps`, `eta_seconds`, and `complete`.

### Exceptions

All exceptions derive from `AIOSSHException`, which carries `message`,
`code` (a machine-readable string), `details` (a dict), `cause` (the
original exception, if any), and `timestamp`.

| Category | Exceptions |
|---|---|
| Connection | `AIOSSHConnectionError`, `AIOSSHConnectionTimeoutError`, `AIOSSHConnectionRefusedError`, `AIOSSHHostKeyVerificationError` |
| Authentication | `AIOSSHAuthenticationError`, `AIOSSHInvalidCredentialsError` |
| Session | `AIOSSHSessionError`, `AIOSSHSessionExpiredError`, `AIOSSHSessionNotFoundError`, `AIOSSHSessionCorruptedError` |
| Command execution | `AIOSSHCommandError`, `AIOSSHCommandTimeoutError` (both accept a `command` keyword argument) |
| File transfer | `AIOSSHFileTransferError`, `AIOSSHFileTransferNotFoundError`, `AIOSSHFileUploadError`, `AIOSSHFileDownloadError`, `AIOSSHFileDiskFullError` |
| Security / validation | `AIOSSHSecurityError`, `AIOSSHIntegrityError`, `AIOSSHEncryptionError`, `AIOSSHValidationError`, `AIOSSHInvalidParameterError` |
| Resource limits | `AIOSSHRateLimitError`, `AIOSSHPoolExhaustedError` |
| Configuration / other | `AIOSSHConfigurationError`, `AIOSSHProxyError`, `AIOSSHPluginError` (reserved; not currently raised by the library) |

### Utility Decorators — `aiossh.decorators`

Not part of the top-level `aiossh` public API; import explicitly from the
submodule:

```python
from aiossh.decorators import retry, timing
```

| Decorator | Description |
|---|---|
| `retry(max_retries=3, exceptions=(Exception,))` | Wraps an async function; retries on the given exception types with a linearly increasing delay (`0.5s * attempt`), re-raising the last exception after `max_retries` attempts. |
| `timing` | Wraps an async function; prints its execution time to stdout after each call. |

---

## Examples

All examples are in [`examples/`](examples/) and are ready to run against
a real host after editing the connection details at the top of each file.

| # | File | Demonstrates |
|---|---|---|
| 1 | [`01_basic_connect_and_execute.py`](examples/01_basic_connect_and_execute.py) | Connecting, running commands, `sudo` execution, and `execute_on_all` |
| 2 | [`02_high_speed_parallel_transfer.py`](examples/02_high_speed_parallel_transfer.py) | `ParallelSCP` upload/download with live progress reporting |
| 3 | [`03_ssh_tunneling_socks5_and_port_forward.py`](examples/03_ssh_tunneling_socks5_and_port_forward.py) | SOCKS5 proxy and local port forwarding through a bastion host |
| 4 | [`04_session_recording_and_replay.py`](examples/04_session_recording_and_replay.py) | Recording a session and replaying it |
| 5 | [`05_docker_exec_and_discord_webhook.py`](examples/05_docker_exec_and_discord_webhook.py) | Running commands in a Docker container and sending Discord/Telegram notifications |
| 6 | [`06_encrypted_session_storage.py`](examples/06_encrypted_session_storage.py) | Saving and loading credentials with `SessionFileManager` |

```bash
python examples/01_basic_connect_and_execute.py
```

---

## Security Considerations

- The default host-key handler (`FastSSHSession._default_host_key_handler`)
  accepts all host keys and does not protect against MITM attacks. Supply
  a `host_key_callback` in `SSHConfig`, or otherwise configure `asyncssh`
  known-hosts verification, before using this library against untrusted
  networks in production.
- Prefer SSH private keys over password authentication where possible.
- Private and reserved IP ranges are blocked by `InputValidator.validate_host()`
  by default (SSRF protection); pass `allow_private=True` explicitly when
  connecting to internal networks.
- A fixed set of destructive command patterns and common injection
  indicators are rejected by `InputValidator.validate_command()` unless
  `allow_dangerous=True` is passed explicitly; this is a defense-in-depth
  measure, not a substitute for trusting the source of the commands you
  execute.
- When using encrypted session storage, use a master password of at least
  12 characters (enforced by `AIOSSH.__init__`); the derived key never
  touches disk and is cleared from memory after use.
- Use `async with` / context managers so sessions, pools, and tunnels are
  always cleaned up, even on error.

---

## Testing

`tests/` contains a self-contained `unittest` suite (228 tests) covering
`InputValidator`, `RateLimiter`, `ConnectionPool`, `FastSSHSession`,
`SessionFileManager` (using the real `cryptography` package for AES-256-GCM
/ PBKDF2), and regression tests for the `DockerExecSession` command-injection
fix and the `ParallelSCP` / `ConnectionPool` fixes described in
[`CHANGELOG.md`](CHANGELOG.md). No real network access or the real
`asyncssh` package is required — a minimal fake `asyncssh`
(`tests/_fake_asyncssh/`) provides just the exception types and connection
surface the library depends on. The suite is split across `tests/test_all.py`
(core behaviour), `tests/test_deep_audit.py` (edge cases, concurrency,
security, and platform-specific behaviour), and
`tests/test_asyncssh_boundary.py` (regression scenarios that assert only
validated requests and asyncssh-compatible keyword arguments ever cross
the boundary into the underlying `asyncssh` library).

```bash
pip install cryptography
PYTHONPATH="src:tests/_fake_asyncssh:tests" python -m unittest tests.test_all tests.test_deep_audit tests.test_asyncssh_boundary tests.test_secure_memory -v
```

---

## Development

```bash
git clone https://github.com/bluedock/aiossh.git
cd aiossh
pip install -e ".[dev]"
ruff check .
mypy src/aiossh
```

---

## License

MIT License © 2026 bluedock. See [`LICENSE`](LICENSE) for the full text.

---

## Credits

AIOSSH is created and maintained by [**bluedock**](https://github.com/bluedock).
