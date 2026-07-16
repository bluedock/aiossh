# AIOSSH v1.0.0

AIOSSH is a professional asynchronous SSH client library for Python.

This is the complete and stable v1.0.0 release with connection pooling, encrypted session storage, strict validation, tunneling, parallel file transfers, and more.

## Features
- Async SSH using asyncssh
- Connection pooling
- Encrypted credential storage (AES-256-GCM)
- SOCKS5 proxy + port forwarding
- High-speed parallel file transfers
- Session recording & replay
- Docker & Kubernetes support
- Webhook notifications
- Plugin system
- Full type hints

## Installation
```bash
pip install aiossh==1.0.0
import asyncio
from aiossh import AIOSSH

async def main():
    async with AIOSSH() as client:
        session = await client.connect("host", "user", password="pass")
        result = await client.execute_command(session, "uptime")
        print(result["stdout"])

asyncio.run(main())
cd \~/storage/shared/aiossh
git checkout restructure
cat > README.md << 'EOF'
# AIOSSH

این ریپازیتوری شامل نسخه‌های مختلف کتابخونه AIOSSH است.

## نسخه‌ها

- [aiossh-1.1.0](./aiossh-1.1.0) — نسخه پایدار
- [aiossh-1.0.0](./aiossh-1.0.0) — نسخه قبلی

برای استفاده از هر نسخه، به پوشه مربوطه مراجعه کنید.
