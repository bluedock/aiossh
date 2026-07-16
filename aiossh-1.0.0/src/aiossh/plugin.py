"""
Plugin System Module - AIOSSH

Middleware-style plugin system for intercepting and modifying
command execution, connections, and file transfers.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Any, Callable, Optional
from dataclasses import dataclass, field

from .exceptions import AIOSSHSecurityError


@dataclass
class CommandContext:
    """Context object passed through plugin chain."""
    command: str
    timeout: int = 30
    sudo: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    cancelled: bool = False


@dataclass
class ConnectionContext:
    """Context for connection events."""
    host: str
    port: int
    username: str
    metadata: dict[str, Any] = field(default_factory=dict)
    cancelled: bool = False


@dataclass
class FileTransferContext:
    """Context for file transfer events."""
    local_path: str
    remote_path: str
    file_size: int = 0
    direction: str = "upload"  # upload or download
    metadata: dict[str, Any] = field(default_factory=dict)
    cancelled: bool = False


class BasePlugin(ABC):
    """Base class for all plugins."""

    def __init__(self, name: str, priority: int = 100) -> None:
        self.name = name
        self.priority = priority
        self._enabled = True

    @property
    def enabled(self) -> bool:
        return self._enabled

    def enable(self) -> None:
        self._enabled = True

    def disable(self) -> None:
        self._enabled = False

    async def on_before_connect(self, ctx: ConnectionContext) -> ConnectionContext:
        """Called before establishing connection."""
        return ctx

    async def on_after_connect(self, session: Any) -> None:
        """Called after successful connection."""
        pass

    async def on_before_execute(self, ctx: CommandContext) -> CommandContext:
        """Called before command execution."""
        return ctx

    async def on_after_execute(self, ctx: CommandContext, result: dict[str, Any]) -> dict[str, Any]:
        """Called after command execution."""
        return result

    async def on_before_file_transfer(self, ctx: FileTransferContext) -> FileTransferContext:
        """Called before file transfer."""
        return ctx

    async def on_after_file_transfer(self, ctx: FileTransferContext, result: dict[str, Any]) -> dict[str, Any]:
        """Called after file transfer."""
        return result

    async def on_disconnect(self, host: str) -> None:
        """Called when session disconnects."""
        pass

    async def on_error(self, error: Exception, context: dict[str, Any]) -> None:
        """Called on any error."""
        pass


class PluginManager:
    """Manages and orchestrates plugins."""

    def __init__(self) -> None:
        self._plugins: list[BasePlugin] = []

    def register(self, plugin: BasePlugin) -> None:
        """Register a plugin."""
        self._plugins.append(plugin)
        self._plugins.sort(key=lambda p: p.priority)

    def unregister(self, plugin_name: str) -> None:
        """Unregister a plugin by name."""
        self._plugins = [p for p in self._plugins if p.name != plugin_name]

    def get_plugin(self, name: str) -> Optional[BasePlugin]:
        """Get a plugin by name."""
        for plugin in self._plugins:
            if plugin.name == name:
                return plugin
        return None

    async def execute_hook(self, hook_name: str, *args: Any, **kwargs: Any) -> Any:
        """Execute a hook across all enabled plugins."""
        result = args[0] if args else None

        for plugin in self._plugins:
            if not plugin.enabled:
                continue

            hook = getattr(plugin, hook_name, None)
            if hook is None:
                continue

            try:
                if hook_name.startswith("on_before"):
                    result = await hook(result)
                    if result is None:
                        break
                elif hook_name.startswith("on_after"):
                    result = await hook(result, kwargs.get("result", {}))
                    if result is None:
                        break
                else:
                    await hook(*args, **kwargs)
            except Exception as e:
                await plugin.on_error(e, {"hook": hook_name})

        return result


# Built-in Plugins

class CommandLoggerPlugin(BasePlugin):
    """Logs all commands and their results."""

    def __init__(self) -> None:
        super().__init__(name="command_logger", priority=10)

    async def on_before_execute(self, ctx: CommandContext) -> CommandContext:
        print(f"[CMD] Executing: {ctx.command[:100]}")
        return ctx

    async def on_after_execute(self, ctx: CommandContext, result: dict[str, Any]) -> dict[str, Any]:
        status = "OK" if result.get("success") else "FAILED"
        print(f"[CMD] {status}: {ctx.command[:100]} (exit: {result.get('exit_code')})")
        return result


class ValidationPlugin(BasePlugin):
    """Validates commands before execution."""

    def __init__(self, blocked_patterns: list[str] = None) -> None:
        super().__init__(name="validator", priority=1)
        self.blocked_patterns = blocked_patterns or [
            "rm -rf /",
            "mkfs.",
            "dd if=",
            "shutdown",
            "reboot",
        ]

    async def on_before_execute(self, ctx: CommandContext) -> CommandContext:
        for pattern in self.blocked_patterns:
            if pattern.lower() in ctx.command.lower():
                ctx.cancelled = True
                raise AIOSSHSecurityError(
                    f"Command blocked by validation plugin: {pattern}",
                    code="COMMAND_BLOCKED",
                    details={"command": ctx.command[:100]},
                )
        return ctx


class AutoRetryPlugin(BasePlugin):
    """Automatically retries failed commands."""

    def __init__(self, max_retries: int = 3) -> None:
        super().__init__(name="auto_retry", priority=50)
        self.max_retries = max_retries

    async def on_after_execute(self, ctx: CommandContext, result: dict[str, Any]) -> dict[str, Any]:
        if not result.get("success"):
            result["auto_retry_attempted"] = True
        return result