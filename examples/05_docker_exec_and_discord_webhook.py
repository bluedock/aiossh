#!/usr/bin/env python3
"""
Example 5: Docker Exec + Discord/Telegram Notifications (v1.1.0)

Execute commands inside Docker containers and notify your team via webhooks.
"""

import asyncio
from aiossh import AIOSSH, DockerExecSession, DiscordWebhook, TelegramWebhook


async def main():
    

    # Setup webhooks (replace with your real URLs/tokens)
    discord = DiscordWebhook("https://discord.com/api/webhooks/YOUR_WEBHOOK_URL")
    telegram = TelegramWebhook(bot_token="YOUR_BOT_TOKEN", chat_id="YOUR_CHAT_ID")

    async with AIOSSH() as client:
        # Connect to Docker host
        docker_host = await client.connect(
            host="docker-host.example.com",
            username="root",
            password="your-password",
        )

        # Create Docker session
        docker = DockerExecSession(
            ssh_session=docker_host,
            container_name="nginx-prod",
            sudo=False
        )

        await docker.connect()
        print("Connected to nginx-prod container")

        # Run command inside container
        result = await docker.execute("nginx -t && nginx -s reload", timeout=15)

        if result["success"]:
            msg = "Nginx configuration reloaded successfully on production"
            print(msg)
            await discord.send(msg)
            await telegram.send(msg)
        else:
            msg = f"❌ Nginx reload failed!\n\n{result.get('stderr', '')}"
            print(msg)
            await discord.send(msg)


if __name__ == "__main__":
    asyncio.run(main())
