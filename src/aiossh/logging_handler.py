"""
Advanced Logging Handler - AIOSSH

Supports structured logging to multiple backends:
- Local file (JSON lines format)
- ELK Stack (Elasticsearch)
- Loki (Grafana)
- Datadog
- Syslog
"""

from __future__ import annotations

import asyncio
import json
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Optional

try:
    import aiofiles
except ImportError:
    aiofiles = None

try:
    import aiohttp
except ImportError:
    aiohttp = None

try:
    import orjson
    json_dumps = orjson.dumps
except ImportError:
    json_dumps = lambda x: json.dumps(x, default=str).encode("utf-8")


class BaseLogHandler(ABC):
    """Abstract base for log handlers."""

    @abstractmethod
    async def emit(self, level: str, message: str, extra: Optional[dict[str, Any]] = None) -> None:
        """Emit a log record."""
        pass

    async def flush(self) -> None:
        """Flush buffered records."""
        pass

    async def close(self) -> None:
        """Close the handler."""
        pass


class FileLogHandler(BaseLogHandler):
    """Log to a local JSON lines file."""

    def __init__(self, filepath: str, max_size_mb: int = 100, backup_count: int = 5) -> None:
        self.filepath = filepath
        self.max_size = max_size_mb * 1024 * 1024
        self.backup_count = backup_count
        self._buffer: list[bytes] = []
        self._lock = asyncio.Lock()
        self._last_flush = time.monotonic()

    async def emit(self, level: str, message: str, extra: Optional[dict[str, Any]] = None) -> None:
        """Emit a log record to file."""
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "message": message,
            "extra": extra or {},
        }

        line = json_dumps(record) + b"\n"

        async with self._lock:
            self._buffer.append(line)

            if len(self._buffer) >= 100 or time.monotonic() - self._last_flush > 30:
                await self._flush()

    async def _flush(self) -> None:
        """Write buffer to file."""
        if not self._buffer:
            return

        try:
            if aiofiles:
                async with aiofiles.open(self.filepath, "ab") as f:
                    await f.write(b"".join(self._buffer))
        except Exception:
            pass
        finally:
            self._buffer.clear()
            self._last_flush = time.monotonic()


class ElasticsearchHandler(BaseLogHandler):
    """Log to Elasticsearch."""

    def __init__(self, host: str, index: str = "aiossh-logs", port: int = 9200) -> None:
        self.host = host
        self.port = port
        self.index = index
        self._url = f"http://{host}:{port}/{index}/_doc"
        self._buffer: list[dict[str, Any]] = []
        self._lock = asyncio.Lock()

    async def emit(self, level: str, message: str, extra: Optional[dict[str, Any]] = None) -> None:
        """Send log to Elasticsearch."""
        record = {
            "@timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "message": message,
            "extra": extra or {},
        }

        async with self._lock:
            self._buffer.append(record)
            if len(self._buffer) >= 50:
                await self._flush()

    async def _flush(self) -> None:
        """Send buffer to Elasticsearch."""
        if not self._buffer:
            return

        try:
            if aiohttp:
                async with aiohttp.ClientSession() as session:
                    for record in self._buffer:
                        await session.post(self._url, json=record, timeout=aiohttp.ClientTimeout(total=5))
        except Exception:
            pass
        finally:
            self._buffer.clear()


class LokiHandler(BaseLogHandler):
    """Log to Grafana Loki."""

    def __init__(self, url: str, labels: dict[str, str] = None) -> None:
        self.url = f"{url}/loki/api/v1/push"
        self.labels = labels or {"source": "aiossh"}
        self._buffer: list[dict[str, Any]] = []
        self._lock = asyncio.Lock()

    async def emit(self, level: str, message: str, extra: Optional[dict[str, Any]] = None) -> None:
        """Send log to Loki."""
        record = {
            "ts": str(int(time.time() * 1_000_000_000)),
            "line": f"[{level}] {message}",
        }

        async with self._lock:
            self._buffer.append(record)
            if len(self._buffer) >= 100:
                await self._flush()

    async def _flush(self) -> None:
        """Send buffer to Loki."""
        if not self._buffer:
            return

        payload = {
            "streams": [{
                "stream": self.labels,
                "values": [[r["ts"], r["line"]] for r in self._buffer],
            }]
        }

        try:
            if aiohttp:
                async with aiohttp.ClientSession() as session:
                    await session.post(
                        self.url,
                        json=payload,
                        headers={"Content-Type": "application/json"},
                        timeout=aiohttp.ClientTimeout(total=5),
                    )
        except Exception:
            pass
        finally:
            self._buffer.clear()


class DatadogHandler(BaseLogHandler):
    """Log to Datadog."""

    def __init__(self, api_key: str, source: str = "aiossh", tags: str = None) -> None:
        self.api_key = api_key
        self.source = source
        self.tags = tags or "service:aiossh"
        self._url = "https://http-intake.logs.datadoghq.com/api/v2/logs"
        self._buffer: list[dict[str, Any]] = []
        self._lock = asyncio.Lock()

    async def emit(self, level: str, message: str, extra: Optional[dict[str, Any]] = None) -> None:
        """Send log to Datadog."""
        record = {
            "ddsource": self.source,
            "ddtags": self.tags,
            "hostname": "aiossh",
            "message": f"[{level}] {message}",
            "status": level.lower(),
        }

        async with self._lock:
            self._buffer.append(record)
            if len(self._buffer) >= 50:
                await self._flush()

    async def _flush(self) -> None:
        """Send buffer to Datadog."""
        if not self._buffer:
            return

        try:
            if aiohttp:
                async with aiohttp.ClientSession() as session:
                    await session.post(
                        self._url,
                        json=self._buffer,
                        headers={
                            "DD-API-KEY": self.api_key,
                            "Content-Type": "application/json",
                        },
                        timeout=aiohttp.ClientTimeout(total=5),
                    )
        except Exception:
            pass
        finally:
            self._buffer.clear()


class SyslogHandler(BaseLogHandler):
    """Log to local syslog."""

    def __init__(self, facility: int = None, address: str = "/dev/log") -> None:
        """Initialize syslog handler.

        Args:
            facility: Syslog facility (e.g., syslog.LOG_LOCAL0). Imported on init.
            address: Syslog socket address.
        """
        self.facility = facility
        self.address = address
        try:
            import syslog
            self._syslog = syslog
            if facility is None:
                self.facility = syslog.LOG_LOCAL0
        except ImportError:
            self._syslog = None

    async def emit(self, level: str, message: str, extra: Optional[dict[str, Any]] = None) -> None:
        """Send log to syslog."""
        if not self._syslog:
            return

        try:
            level_map = {
                "DEBUG": self._syslog.LOG_DEBUG,
                "INFO": self._syslog.LOG_INFO,
                "WARNING": self._syslog.LOG_WARNING,
                "ERROR": self._syslog.LOG_ERR,
                "CRITICAL": self._syslog.LOG_CRIT,
            }
            priority = level_map.get(level, self._syslog.LOG_INFO) | self.facility

            self._syslog.openlog(ident="aiossh")
            self._syslog.syslog(priority, message)
        except Exception:
            pass


class LogManager:
    """Central log manager supporting multiple handlers."""

    def __init__(self) -> None:
        self._handlers: list[BaseLogHandler] = []

    def add_handler(self, handler: BaseLogHandler) -> None:
        """Add a log handler."""
        self._handlers.append(handler)

    async def log(self, level: str, message: str, extra: Optional[dict[str, Any]] = None) -> None:
        """Emit to all handlers."""
        for handler in self._handlers:
            try:
                await handler.emit(level, message, extra)
            except Exception:
                pass

    async def debug(self, message: str, **kwargs: Any) -> None:
        await self.log("DEBUG", message, kwargs)

    async def info(self, message: str, **kwargs: Any) -> None:
        await self.log("INFO", message, kwargs)

    async def warning(self, message: str, **kwargs: Any) -> None:
        await self.log("WARNING", message, kwargs)

    async def error(self, message: str, **kwargs: Any) -> None:
        await self.log("ERROR", message, kwargs)

    async def flush_all(self) -> None:
        """Flush all handlers."""
        for handler in self._handlers:
            await handler.flush()

    async def close_all(self) -> None:
        """Close all handlers."""
        for handler in self._handlers:
            await handler.close()
        self._handlers.clear()