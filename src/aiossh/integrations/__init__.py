"""Optional integrations: proxy/tunnel, webhooks, Docker, and session replay."""

from .docker import DockerExecSession
from .proxy import ProxyConfig, SSHTunnelManager, create_tunnel
from .replay import SessionRecorder, SessionReplayer
from .webhook import DiscordWebhook, TelegramWebhook, WebhookManager

__all__ = [
    "DiscordWebhook",
    "DockerExecSession",
    "ProxyConfig",
    "SSHTunnelManager",
    "SessionRecorder",
    "SessionReplayer",
    "TelegramWebhook",
    "WebhookManager",
    "create_tunnel",
]
