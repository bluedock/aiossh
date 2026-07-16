"""
Command Queue Manager - AIOSSH

Schedule and batch command execution with priority support.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass(order=True)
class QueuedCommand:
    """A command in the execution queue."""
    priority: int
    command_id: str = field(compare=False)
    command: str = field(compare=False)
    session: Any = field(compare=False)
    timeout: int = field(compare=False, default=30)
    scheduled_at: float = field(compare=False, default_factory=time.monotonic)
    callback: Optional[Callable] = field(compare=False, default=None)
    metadata: dict[str, Any] = field(compare=False, default_factory=dict)
    status: str = field(compare=False, default="pending")


class CommandQueue:
    """Priority-based command execution queue."""

    def __init__(self, max_concurrent: int = 5) -> None:
        self._queue: list[QueuedCommand] = []
        self._max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._lock = asyncio.Lock()
        self._processing = False
        self._results: dict[str, Any] = {}
        self._counter = 0

    async def enqueue(
        self,
        command: str,
        session: Any,
        *,
        priority: int = 100,
        timeout: int = 30,
        callback: Optional[Callable] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> str:
        """Add a command to the queue."""
        self._counter += 1
        command_id = f"cmd_{self._counter}"

        queued = QueuedCommand(
            priority=priority,
            command_id=command_id,
            command=command,
            session=session,
            timeout=timeout,
            callback=callback,
            metadata=metadata or {},
        )

        async with self._lock:
            self._queue.append(queued)
            self._queue.sort(key=lambda x: x.priority)

        return command_id

    async def enqueue_batch(
        self,
        commands: list[dict[str, Any]],
        session: Any,
        *,
        parallel: bool = True,
    ) -> list[str]:
        """Enqueue multiple commands at once."""
        ids = []
        for cmd_info in commands:
            cmd_id = await self.enqueue(
                command=cmd_info["command"],
                session=session,
                priority=cmd_info.get("priority", 100),
                timeout=cmd_info.get("timeout", 30),
            )
            ids.append(cmd_id)
        return ids

    async def process(self) -> dict[str, Any]:
        """Process all queued commands."""
        self._processing = True
        tasks = []

        async with self._lock:
            pending = [cmd for cmd in self._queue if cmd.status == "pending"]
            self._queue = [cmd for cmd in self._queue if cmd.status != "pending"]

        for cmd in pending:
            cmd.status = "running"
            task = asyncio.create_task(self._execute_one(cmd))
            tasks.append(task)

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        self._processing = False
        return self._results

    async def _execute_one(self, cmd: QueuedCommand) -> None:
        """Execute a single queued command."""
        async with self._semaphore:
            try:
                result = await cmd.session.execute(
                    cmd.command,
                    timeout=cmd.timeout,
                )
                cmd.status = "completed"
                self._results[cmd.command_id] = result

                if cmd.callback:
                    if asyncio.iscoroutinefunction(cmd.callback):
                        await cmd.callback(cmd.command_id, result)
                    else:
                        cmd.callback(cmd.command_id, result)

            except Exception as e:
                cmd.status = "failed"
                self._results[cmd.command_id] = {
                    "error": str(e),
                    "success": False,
                }

    def get_status(self, command_id: str) -> Optional[str]:
        """Get status of a queued command."""
        for cmd in self._queue:
            if cmd.command_id == command_id:
                return cmd.status
        if command_id in self._results:
            return "completed"
        return None

    def get_result(self, command_id: str) -> Optional[dict[str, Any]]:
        """Get result of a completed command."""
        return self._results.get(command_id)

    def clear(self) -> None:
        """Clear the queue and results."""
        self._queue.clear()
        self._results.clear()

    @property
    def pending_count(self) -> int:
        """Number of pending commands."""
        return len([c for c in self._queue if c.status == "pending"])

    @property
    def completed_count(self) -> int:
        """Number of completed commands."""
        return len(self._results)