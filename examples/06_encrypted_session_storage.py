#!/usr/bin/env python3
"""
Example 6: Encrypted Session Storage (v1.1.0)

Save and load SSH credentials securely using AES-256-GCM + HMAC.
Never store passwords in plain text again.
"""

import asyncio
from aiossh import AIOSSH


async def main():
    

    MASTER_PASSWORD = "SuperStrongMasterPassword123!@#"

    client = AIOSSH(master_password=MASTER_PASSWORD)
    await client.__aenter__()

    try:
        # === SAVE SESSION ===
        print("Saving encrypted session...")
        await client.save_session_to_file(
            session_name="prod-db-server",
            host="db.internal.example.com",
            username="deploy",
            password="very-secret-password",
            port=22,
        )
        print("Session saved securely (encrypted with AES-256-GCM)")

        # === LOAD AND USE ===
        print("\nLoading saved session...")
        session = await client.load_session_from_file("prod-db-server")

        print(f"Connected to {session.host} using saved credentials")

        result = await client.execute_command(session, "hostname")
        print(f"Hostname: {result['stdout'].strip()}")

        # List all saved sessions
        saved = client.list_saved_sessions()
        print(f"\n📁 All saved sessions: {saved}")

    finally:
        await client.close_all()


if __name__ == "__main__":
    asyncio.run(main())
