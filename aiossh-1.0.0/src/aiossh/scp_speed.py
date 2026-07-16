"""
High-Speed SCP Module - AIOSSH

Parallel file transfer with chunking for maximum throughput.
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Callable


@dataclass
class TransferProgress:
    """File transfer progress."""
    total_bytes: int
    transferred: int
    speed_mbps: float
    eta_seconds: float
    complete: bool = False


class ParallelSCP:
    """High-speed file transfer using parallel chunks."""

    def __init__(
        self,
        session: object,
        chunk_size: int = 10 * 1024 * 1024,  # 10 MB chunks
        max_parallel: int = 4,
    ) -> None:
        self.session = session
        self.chunk_size = chunk_size
        self.max_parallel = max_parallel
        self._progress_callback: Optional[Callable[[TransferProgress], None]] = None

    def on_progress(self, callback: Callable[[TransferProgress], None]) -> None:
        """Set progress callback function."""
        self._progress_callback = callback

    async def upload(
        self,
        local_path: str,
        remote_path: str,
        *,
        max_speed_mbps: float = 0,
    ) -> dict[str, object]:
        """Upload a file using parallel chunks."""
        local_file = Path(local_path).expanduser()
        file_size = local_file.stat().st_size

        if file_size <= self.chunk_size:
            # Small file, use normal upload
            return await self.session.upload_file(str(local_file), remote_path)

        # Split into chunks
        num_chunks = (file_size + self.chunk_size - 1) // self.chunk_size
        chunk_files: list[str] = []

        try:
            # Create chunk files
            with open(local_file, "rb") as f:
                for i in range(num_chunks):
                    chunk_path = f"{local_file}.part{i:04d}"
                    with open(chunk_path, "wb") as cf:
                        data = f.read(self.chunk_size)
                        cf.write(data)
                    chunk_files.append(chunk_path)

            # Upload chunks in parallel
            semaphore = asyncio.Semaphore(self.max_parallel)
            transferred = 0
            start_time = time.monotonic()
            transfer_lock = asyncio.Lock()

            async def upload_chunk(i: int, chunk_path: str) -> None:
                nonlocal transferred
                async with semaphore:
                    # Speed throttling
                    if max_speed_mbps > 0:
                        current_time = time.monotonic()
                        async with transfer_lock:
                            if elapsed := current_time - start_time > 0:
                                current_speed = (transferred / 1_000_000) / elapsed
                                if current_speed > max_speed_mbps:
                                    sleep_time = (transferred / 1_000_000) / max_speed_mbps - elapsed
                                    if sleep_time > 0:
                                        await asyncio.sleep(sleep_time)

                    remote_chunk = f"{remote_path}.part{i:04d}"
                    await self.session.upload_file(chunk_path, remote_chunk)

                    chunk_size_bytes = Path(chunk_path).stat().st_size
                    async with transfer_lock:
                        transferred += chunk_size_bytes

                    if self._progress_callback:
                        elapsed = time.monotonic() - start_time
                        speed = (transferred / 1_000_000) / elapsed if elapsed > 0 else 0
                        eta = (file_size - transferred) / (speed * 1_000_000) if speed > 0 else 0
                        self._progress_callback(TransferProgress(
                            total_bytes=file_size,
                            transferred=transferred,
                            speed_mbps=round(speed, 2),
                            eta_seconds=round(eta, 1),
                        ))

            async with asyncio.TaskGroup() as tg:
                tasks = [
                    tg.create_task(upload_chunk(i, chunk_path))
                    for i, chunk_path in enumerate(chunk_files)
                ]

            # Combine chunks on remote (safer, with cleanup even on partial failure)
            parts = " ".join(f"{remote_path}.part{i:04d}" for i in range(num_chunks))
            combine_cmd = f"cat {parts} > {remote_path} || true; rm -f {parts}"
            combine_result = await self.session.execute(combine_cmd)
            if not combine_result.get("success"):
                # Still try to clean parts
                await self.session.execute(f"rm -f {parts}")

            elapsed = time.monotonic() - start_time

            return {
                "success": True,
                "file_size": file_size,
                "chunks": num_chunks,
                "transfer_time": round(elapsed, 2),
                "speed_mbps": round((file_size / 1_000_000) / elapsed, 2) if elapsed > 0 else 0,
            }

        finally:
            # Clean up chunk files
            for chunk_path in chunk_files:
                try:
                    os.remove(chunk_path)
                except Exception:
                    pass

    async def download(
        self,
        remote_path: str,
        local_path: str,
        *,
        max_speed_mbps: float = 0,
    ) -> dict[str, object]:
        """Download a file using parallel chunks."""
        local_file = Path(local_path).expanduser()
        local_file.parent.mkdir(parents=True, exist_ok=True)

        # Get remote file size (portable)
        stat_result = await self.session.execute(
            f"python3 -c \"import os; print(os.path.getsize('{remote_path}'))\""
        )
        file_size = int(stat_result["stdout"].strip())

        if file_size <= self.chunk_size:
            return await self.session.download_file(remote_path, str(local_file))

        num_chunks = (file_size + self.chunk_size - 1) // self.chunk_size

        # Split and download
        split_cmd = f"split -b {self.chunk_size} -d {remote_path} {remote_path}.part"
        await self.session.execute(split_cmd)

        semaphore = asyncio.Semaphore(self.max_parallel)
        transferred = 0
        start_time = time.monotonic()
        transfer_lock = asyncio.Lock()

        async def download_chunk(i: int) -> None:
            nonlocal transferred
            async with semaphore:
                # Speed throttling
                if max_speed_mbps > 0:
                    current_time = time.monotonic()
                    async with transfer_lock:
                        if elapsed := current_time - start_time > 0:
                            current_speed = (transferred / 1_000_000) / elapsed
                            if current_speed > max_speed_mbps:
                                sleep_time = (transferred / 1_000_000) / max_speed_mbps - elapsed
                                if sleep_time > 0:
                                    await asyncio.sleep(sleep_time)

                remote_chunk = f"{remote_path}.part{i:04d}"
                local_chunk = f"{local_file}.part{i:04d}"
                result = await self.session.download_file(remote_chunk, local_chunk)
                chunk_size_bytes = result.get("file_size", 0)
                async with transfer_lock:
                    transferred += chunk_size_bytes

                if self._progress_callback:
                    elapsed = time.monotonic() - start_time
                    speed = (transferred / 1_000_000) / elapsed if elapsed > 0 else 0
                    eta = (file_size - transferred) / (speed * 1_000_000) if speed > 0 else 0
                    self._progress_callback(TransferProgress(
                        total_bytes=file_size,
                        transferred=transferred,
                        speed_mbps=round(speed, 2),
                        eta_seconds=round(eta, 1),
                    ))

        async with asyncio.TaskGroup() as tg:
            tasks = [tg.create_task(download_chunk(i)) for i in range(num_chunks)]

        # Combine locally
        with open(local_file, "wb") as outfile:
            for i in range(num_chunks):
                chunk_path = f"{local_file}.part{i:04d}"
                with open(chunk_path, "rb") as infile:
                    outfile.write(infile.read())
                os.remove(chunk_path)

        # Clean up remote chunks
        await self.session.execute(f"rm {remote_path}.part*")

        elapsed = time.monotonic() - start_time

        return {
            "success": True,
            "file_size": file_size,
            "chunks": num_chunks,
            "transfer_time": round(elapsed, 2),
            "speed_mbps": round((file_size / 1_000_000) / elapsed, 2) if elapsed > 0 else 0,
        }