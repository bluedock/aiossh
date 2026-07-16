# AIOSSH v1.1.0

AIOSSH is an asynchronous SSH client library for Python built on `asyncssh`.

It includes connection pooling, encrypted session storage, input validation, tunneling support, parallel file transfers, session recording, Docker exec, and webhook notifications.

Changes in v1.1.0:
- Added Windows compatibility for privileged port validation
- Implemented minimum idle connection support in the pool
- Added timeout protection for streaming commands
- Improved portability of parallel file transfers
- Expanded module coverage for better import compatibility
- Updated documentation and examples

---

## 📁 Project Structure

```
aiossh-1.1.0/
├── src/aiossh/                 # Main package source
│   ├── __init__.py
│   ├── core.py                 # High-level AIOSSH client
│   ├── session.py              # FastSSHSession + SSHConfig
│   ├── pool.py                 # ConnectionPool with min/max support
│   ├── validators.py           # Strict input validation + SSRF protection
│   ├── scp_speed.py            # ParallelSCP (high-speed transfers)
│   ├── exceptions.py           # 20+ specific exception types
│   └── py.typed
│
├── examples/                   # Ready-to-run practical examples
│   ├── 01_basic_connect_and_execute.py
│   ├── 02_high_speed_parallel_transfer.py
│   ├── 03_ssh_tunneling_socks5_and_port_forward.py
│   ├── 04_session_recording_and_replay.py
│   ├── 05_docker_exec_and_discord_webhook.py
│   └── 06_encrypted_session_storage.py
│
├── README.md
├── CHANGELOG.md
├── LICENSE
└── pyproject.toml
```

---

## Features

- Asynchronous connection management and command execution
- Connection pooling with configurable limits and idle connection reuse
- Encrypted storage of session credentials using AES-256-GCM
- Input validation for hosts, ports, usernames, commands, and paths
- Support for SOCKS5 proxies and local/remote port forwarding
- Parallel file transfers with chunking and progress reporting
- Session recording and replay functionality
- Docker container command execution
- Webhook notifications (Discord and Telegram helpers)
- Custom exception hierarchy for different error types
- Compatible with Python 3.11+ on Windows and Linux

---

## Installation

```bash
pip install aiossh

# With webhook + extra features
pip install "aiossh[web]"
```

**Requirements:** Python ≥ 3.11

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

See `examples/01_basic_connect_and_execute.py` for a complete version.

---

## Practical Examples

All examples are located in the `examples/` folder and are ready to run.

| # | Example | Description | Run Command |
|---|---------|-------------|-------------|
| 1 | `01_basic_connect_and_execute.py` | Connect + run commands + sudo + execute on all | `python examples/01_basic_connect_and_execute.py` |
| 2 | `02_high_speed_parallel_transfer.py` | Upload/download large files at maximum speed with live progress | `python examples/02_high_speed_parallel_transfer.py` |
| 3 | `03_ssh_tunneling_socks5_and_port_forward.py` | Create SOCKS5 proxy + local port forwards (VPN-like) | `python examples/03_ssh_tunneling_socks5_and_port_forward.py` |
| 4 | `04_session_recording_and_replay.py` | Record SSH session for audit/training and replay it | `python examples/04_session_recording_and_replay.py` |
| 5 | `05_docker_exec_and_discord_webhook.py` | Run commands inside Docker containers + send notifications | `python examples/05_docker_exec_and_discord_webhook.py` |
| 6 | `06_encrypted_session_storage.py` | Securely save/load credentials (never store passwords in plain text) | `python examples/06_encrypted_session_storage.py` |

---

## Security Considerations

- Use context managers for automatic resource cleanup.
- Prefer SSH private keys over password authentication when possible.
- When using encrypted session storage, provide a master password of at least 12 characters.
- In production environments, implement proper host key verification instead of accepting all keys.
- Private and reserved IP addresses are blocked by default in host validation. Use `allow_private=True` when connecting to internal networks.
- Certain dangerous command patterns are rejected by default.

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

## 📜 Changelog Highlights (v1.1.0)

- Fixed Windows compatibility (`os.geteuid` crash)
- Implemented `min_connections` warm pool in `ConnectionPool`
- Added timeout protection to `stream_command`
- Made `ParallelSCP` portable (auto-fallback when `split` unavailable)
- Greatly improved documentation and added 6 practical examples
- Hardened input validation and path traversal checks
- All known logical bugs and race conditions resolved

See `CHANGELOG.md` for full details.

---

## License

MIT License © 2026 PyHPDev

---


