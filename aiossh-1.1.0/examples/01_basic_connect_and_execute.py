#!/usr/bin/env python3
"""
Example 1: Basic Connection and Command Execution (v1.1.0)

This is the simplest way to connect to a server and run commands.
"""

import asyncio
from aiossh import AIOSSH


async def main():
    

    # Using context manager is the recommended way (auto cleanup)
    async with AIOSSH() as client:
        # Connect to server
        import os
        session = await client.connect(
            host=os.getenv("AIOSSH_HOST", "192.0.2.10"),
            username=os.getenv("AIOSSH_USER", "admin"),
            password=os.getenv("AIOSSH_PASSWORD"),
            port=int(os.getenv("AIOSSH_PORT", "22")),
            session_name="web-server-01",
            timeout=30,
        )

        print(f"Connected to {session.host}")

        # Execute simple command
        result = await client.execute_command(session, "uptime")
        print("\n[uptime]")
        print(result["stdout"])

        # Execute with sudo
        result2 = await client.execute_command(session, "df -h", sudo=True)
        print("\n[df -h with sudo]")
        print(result2["stdout"])

        # Run on all active sessions (in this case just one)
        all_results = await client.execute_on_all("whoami")
        print("\n[whoami on all sessions]")
        for name, res in all_results.items():
            print(f"  {name}: {res.get('stdout', '').strip()}")

        # Close specific session
        await client.close_session(session)
        print("\nSession closed gracefully")


if __name__ == "__main__":
    asyncio.run(main())
