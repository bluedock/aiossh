"""
Webhook & Callback System - AIOSSH

Notify external services about connection status, command execution,
and file transfer events.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any, Callable, Optional, Union

try:
    import aiohttp
except ImportError:
    aiohttp = None

try:
    import orjson

    def _json_serializer(obj: Any) -> str:
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Type not serializable: {type(obj)}")

    def json_dumps(data: dict[str, Any]) -> bytes:
        return orjson.dumps(data, default=_json_serializer)
except ImportError:

    class DateTimeEncoder(json.JSONEncoder):
        def default(self, obj: Any) -> Any:
            if isinstance(obj, datetime):
                return obj.isoformat()
            return super().default(obj)

    def json_dumps(data: dict[str, Any]) -> bytes:
        return json.dumps(data, cls=DateTimeEncoder).encode("utf-8")


class WebhookManager:
    """Manage webhooks and callbacks for SSH events."""

    def __init__(self) -> None:
        self._callbacks: dict[str, list[Callable]] = {
            "on_connect": [],
            "on_disconnect": [],
            "on_command_start": [],
            "on_command_complete": [],
            "on_command_error": [],
            "on_file_upload": [],
            "on_file_download": [],
            "on_error": [],
        }
        self._webhooks: dict[str, list[str]] = {
            "on_connect": [],
            "on_disconnect": [],
            "on_command_complete": [],
            "on_error": [],
        }

    def on(self, event: str, callback: Callable) -> None:
        """Register a callback for an event."""
        if event in self._callbacks:
            self._callbacks[event].append(callback)

    def add_webhook(self, event: str, url: str) -> None:
        """Add a webhook URL for an event."""
        if event in self._webhooks:
            self._webhooks[event].append(url)

    async def trigger(self, event: str, data: dict[str, Any]) -> None:
        """Trigger an event (callbacks + webhooks)."""
        # Execute callbacks
        for callback in self._callbacks.get(event, []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(data)
                else:
                    callback(data)
            except Exception as e:
                print(f"[WEBHOOK] Callback error for {event}: {e}")

        # Send webhooks
        if aiohttp and event in self._webhooks:
            payload = json_dumps(data)
            for url in self._webhooks[event]:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.post(
                            url,
                            data=payload,
                            headers={"Content-Type": "application/json"},
                            timeout=aiohttp.ClientTimeout(total=5),
                        ) as resp:
                            if resp.status >= 400:
                                print(f"[WEBHOOK] Failed {url}: {resp.status}")
                except Exception as e:
                    print(f"[WEBHOOK] Error sending to {url}: {e}")


class DiscordWebhook:
    """Helper for Discord webhooks."""

    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = webhook_url

    async def send(self, message: str, embed: Optional[dict[str, Any]] = None) -> bool:
        """Send a message to Discord webhook."""
        if not aiohttp:
            return False

        payload: dict[str, Any] = {"content": message}
        if embed:
            payload["embeds"] = [embed]

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    return resp.status == 204
        except Exception:
            return False


class TelegramWebhook:
    """Helper for Telegram bot notifications."""

    def __init__(self, bot_token: str, chat_id: str) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{bot_token}"

    async def send(self, message: str) -> bool:
        """Send a message to Telegram."""
        if not aiohttp:
            return False

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/sendMessage",
                    json={
                        "chat_id": self.chat_id,
                        "text": message,
                        "parse_mode": "Markdown",
                    },
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    return resp.status == 200
        except Exception:
            return False