"""
Session Recording & Replay - v1.1.0
"""

from __future__ import annotations

import asyncio
import gzip
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

try:
    import orjson as json_module

    def _json_dumps(obj: Any) -> bytes:
        return json_module.dumps(obj)

    def _json_loads(data: bytes) -> Any:
        return json_module.loads(data)
except ImportError:
    import json as json_module

    def _json_dumps(obj: Any) -> bytes:
        return json_module.dumps(obj, separators=(",", ":")).encode("utf-8")

    def _json_loads(data: bytes) -> Any:
        return json_module.loads(data.decode("utf-8"))


class SessionRecorder:
    def __init__(self, session_id: str, storage_dir: str = "~/.aiossh/recordings"):
        self.session_id = session_id
        self.storage_dir = Path(storage_dir).expanduser()
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._events: list[dict] = []
        self._started_at: Optional[float] = None
        self._recording = False

    def start(self):
        self._started_at = time.time()
        self._recording = True
        self._record("session_start", {})

    def _record(self, event_type: str, data: dict):
        if not self._recording:
            return
        self._events.append({
            "ts": time.time() - (self._started_at or 0),
            "type": event_type,
            "data": data
        })

    def record_command(self, command: str):
        self._record("command", {"command": command})

    def record_result(self, result: dict):
        self._record("result", result)

    def stop(self):
        self._record("session_end", {"total_events": len(self._events)})
        self._recording = False

    async def save(self, compress: bool = True) -> str:
        filename = f"{self.session_id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.iossh"
        filepath = self.storage_dir / filename
        data = _json_dumps({
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
    def __init__(self, filepath: str):
        self.filepath = Path(filepath)
        self._events: list[dict] = []
        self._loaded = False

    async def load(self):
        if self.filepath.suffix == ".gz":
            with gzip.open(self.filepath, "rb") as f:
                data = f.read()
        else:
            with open(self.filepath, "rb") as f:
                data = f.read()
        recording = _json_loads(data)
        self._events = recording.get("events", [])
        self._loaded = True

    async def replay(self, speed: float = 1.0, callback: Optional[Callable] = None):
        if not self._loaded:
            await self.load()
        last_ts = 0.0
        for event in self._events:
            delay = max(0, event["ts"] - last_ts) / speed
            await asyncio.sleep(delay)
            if callback:
                callback(event["type"], event["data"])
            last_ts = event["ts"]

    def get_summary(self) -> dict:
        if not self._loaded:
            return {}
        commands = [e for e in self._events if e["type"] == "command"]
        return {
            "total_events": len(self._events),
            "commands_executed": len(commands),
            "command_list": [c["data"].get("command", "") for c in commands]
        }
