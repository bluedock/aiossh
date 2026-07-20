"""Optional integrations: proxy/tunnel, webhooks, Docker, and session replay."""

from .proxy import ProxyConfig, SSHTunnelManager, create_tunnel
from .webhook import WebhookManager, DiscordWebhook, TelegramWebhook
from .docker import DockerExecSession
from .replay import SessionRecorder, SessionReplayer

__all__ = [
    "ProxyConfig",
    "SSHTunnelManager",
    "create_tunnel",
    "WebhookManager",
    "DiscordWebhook",
    "TelegramWebhook",
    "DockerExecSession",
    "SessionRecorder",
    "SessionReplayer",
]
