#!/usr/bin/env python3
"""
Example 3: SSH Tunneling - SOCKS5 Proxy + Local Port Forwarding (v1.1.0)

This turns your SSH connection into a secure VPN-like tunnel.
Perfect for accessing internal services securely.
"""

import asyncio
from aiossh import AIOSSH, ProxyConfig, create_tunnel


async def main():
    

    async with AIOSSH() as client:
        # Connect to bastion/jump host
        bastion = await client.connect(
            host="bastion.example.com",
            username="admin",
            password="your-password",
        )

        print("Connected to bastion host")

        # Configure tunneling
        tunnel_config = ProxyConfig(
            socks_port=1080,                    # SOCKS5 proxy on localhost:1080
            local_forwards=[
                (8080, "internal-db.example.com", 5432),   # localhost:8080 → internal DB
                (9000, "internal-api.example.com", 8080),  # localhost:9000 → internal API
            ],
            enable_socks=True,
        )

        print("\nStarting secure tunnels...")
        print("   • SOCKS5 proxy     → 127.0.0.1:1080")
        print("   • PostgreSQL       → 127.0.0.1:8080  (forwarded to internal-db:5432)")
        print("   • Internal API     → 127.0.0.1:9000")

        # Use context manager for automatic cleanup
        async with create_tunnel(bastion.connection, tunnel_config) as tunnel:
            print("\nAll tunnels are active!")
            print("   You can now use:")
            print("   - curl --socks5 127.0.0.1:1080 https://internal-service")
            print("   - psql -h 127.0.0.1 -p 8080 -U user dbname")
            print("\n   Press Ctrl+C to stop tunnels...\n")

            try:
                # Keep tunnels alive
                await asyncio.sleep(3600)
            except KeyboardInterrupt:
                print("\n🛑 Shutting down tunnels...")


if __name__ == "__main__":
    asyncio.run(main())
