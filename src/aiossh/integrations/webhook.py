"""
Webhook Module - v1.1.0
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

try:
    import aiohttp
except ImportError:
    aiohttp = None  # type: ignore[assignment]

try:
    import orjson as _orjson
    def _json_dumps(data): return _orjson.dumps(data)
    def _json_loads(data): return _orjson.loads(data)
except ImportError:
    import json as _json
    def _json_dumps(data): return _json.dumps(data).encode()
    def _json_loads(data): return _json.loads(data.decode())


class WebhookManager:
    def __init__(self):
        self._callbacks: dict[str, list[Callable]] = {k: [] for k in ["on_connect", "on_disconnect", "on_command_complete", "on_error"]}
        self._webhooks: dict[str, list[str]] = {k: [] for k in ["on_connect", "on_disconnect", "on_command_complete", "on_error"]}

    def on(self, event: str, callback: Callable):
        if event in self._callbacks:
            self._callbacks[event].append(callback)

    def add_webhook(self, event: str, url: str):
        if event in self._webhooks:
            self._webhooks[event].append(url)

    async def trigger(self, event: str, data: dict[str, Any]):
        for cb in self._callbacks.get(event, []):
            try:
                if inspect.iscoroutinefunction(cb):
                    await cb(data)
                else:
                    cb(data)
            except Exception:
                pass

        if aiohttp and event in self._webhooks:
            payload = _json_dumps(data)
            for url in self._webhooks[event]:
                try:
                    async with aiohttp.ClientSession() as session:
                        await session.post(url, data=payload, headers={"Content-Type": "application/json"}, timeout=aiohttp.ClientTimeout(total=5))
                except Exception:
                    pass


class DiscordWebhook:
    def __init__(self, webhook_url: str):
        self.url = webhook_url

    async def send(self, message: str, embed: dict | None = None) -> bool:
        if not aiohttp:
            return False
        payload: dict[str, Any] = {"content": message}
        if embed:
            payload["embeds"] = [embed]
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.url, json=payload, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    return resp.status == 204
        except Exception:
            return False


class TelegramWebhook:
    def __init__(self, bot_token: str, chat_id: str):
        self.api = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        self.chat_id = chat_id

    async def send(self, message: str) -> bool:
        if not aiohttp:
            return False
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.api, json={"chat_id": self.chat_id, "text": message}, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    return resp.status == 200
        except Exception:
            return False
