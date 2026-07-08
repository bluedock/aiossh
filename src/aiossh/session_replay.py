"""
Session Recording & Replay Module - AIOSSH

Record complete SSH sessions (input + output) and replay them.
Useful for auditing, debugging, and training.
"""

from __future__ import annotations

import asyncio
import gzip
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

try:
    import orjson
    json_dumps = orjson.dumps
    json_loads = orjson.loads
except ImportError:
    import json
    json_dumps = lambda x: json.dumps(x, default=str).encode("utf-8")
    json_loads = lambda x: json.loads(x)


class SessionRecorder:
    """Records a complete SSH session."""

    def __init__(self, session_id: str, storage_dir: str = "~/.aiossh/recordings") -> None:
        self.session_id = session_id
        self.storage_dir = Path(storage_dir).expanduser()
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._events: list[dict[str, Any]] = []
        self._started_at: Optional[float] = None
        self._recording = False

    def start(self) -> None:
        """Start recording."""
        self._started_at = time.time()
        self._recording = True
        self._record("session_start", {})

    def _record(self, event_type: str, data: dict[str, Any]) -> None:
        """Record an event."""
        if not self._recording:
            return

        event = {
            "ts": time.time() - (self._started_at or 0),
            "type": event_type,
            "data": data,
        }
        self._events.append(event)

    def record_command(self, command: str) -> None:
        """Record a command execution."""
        self._record("command", {"command": command})

    def record_output(self, output: str, is_stderr: bool = False) -> None:
        """Record command output."""
        self._record("output", {
            "text": output,
            "stream": "stderr" if is_stderr else "stdout",
        })

    def record_result(self, result: dict[str, Any]) -> None:
        """Record command result."""
        self._record("result", {
            "exit_code": result.get("exit_code"),
            "success": result.get("success"),
            "execution_time": result.get("execution_time"),
        })

    def record_file_transfer(self, direction: str, local: str, remote: str, size: int) -> None:
        """Record a file transfer."""
        self._record("file_transfer", {
            "direction": direction,
            "local": local,
            "remote": remote,
            "size": size,
        })

    def record_error(self, error: Exception) -> None:
        """Record an error."""
        self._record("error", {
            "type": type(error).__name__,
            "message": str(error),
        })

    def stop(self) -> None:
        """Stop recording."""
        self._record("session_end", {
            "total_events": len(self._events),
        })
        self._recording = False

    async def save(self, compress: bool = True) -> str:
        """Save recording to disk."""
        filename = f"{self.session_id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.iossh"
        filepath = self.storage_dir / filename

        data = json_dumps({
            "session_id": self.session_id,
            "started_at": datetime.fromtimestamp(self._started_at or 0, tz=timezone.utc).isoformat(),
            "events": self._events,
        })

        if compress:
            filepath = filepath.with_suffix(".iossh.gz")
            with gzip.open(filepath, "wb") as f:
                f.write(data)
        else:
            with open(filepath, "wb") as f:
                f.write(data)

        return str(filepath)


class SessionReplayer:
    """Replay a recorded session."""

    def __init__(self, filepath: str) -> None:
        self.filepath = Path(filepath)
        self._events: list[dict[str, Any]] = []
        self._loaded = False

    async def load(self) -> None:
        """Load recording from disk."""
        if self.filepath.suffix == ".gz":
            with gzip.open(self.filepath, "rb") as f:
                data = f.read()
        else:
            with open(self.filepath, "rb") as f:
                data = f.read()

        recording = json_loads(data)
        self._events = recording.get("events", [])
        self._loaded = True

    async def replay(
        self,
        speed: float = 1.0,
        callback: Optional[Callable[[str, dict[str, Any]], Any]] = None,
    ) -> None:
        """Replay the session.

        Args:
            speed: Playback speed multiplier (1.0 = real time, 2.0 = double speed).
            callback: Function called for each event with (event_type, data).
        """
        if not self._loaded:
            await self.load()

        if not self._events:
            return

        last_ts = 0.0

        for event in self._events:
            delay = max(0, event["ts"] - last_ts) / speed
            await asyncio.sleep(delay)

            if callback:
                callback(event["type"], event["data"])

            last_ts = event["ts"]

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of the recording."""
        if not self._loaded:
            return {}

        commands = [e for e in self._events if e["type"] == "command"]
        errors = [e for e in self._events if e["type"] == "error"]
        transfers = [e for e in self._events if e["type"] == "file_transfer"]

        return {
            "total_events": len(self._events),
            "commands_executed": len(commands),
            "errors": len(errors),
            "file_transfers": len(transfers),
            "command_list": [c["data"].get("command", "") for c in commands],
        }