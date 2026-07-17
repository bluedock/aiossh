"""
High-Speed SCP Module - AIOSSH v1.1.0

Parallel file transfer with chunking for maximum throughput.
Improved portability for remote split (falls back gracefully if GNU split not available).
"""

from __future__ import annotations

import asyncio
import os
import shlex
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Callable, Any

from .exceptions import AIOSSHFileDownloadError
from .validators import InputValidator


@dataclass
class TransferProgress:
    """File transfer progress."""
    total_bytes: int
    transferred: int
    speed_mbps: float
    eta_seconds: float
    complete: bool = False


class ParallelSCP:
    """High-speed file transfer using parallel chunks. v1.1.0 improvements."""

    def __init__(
        self,
        session: Any,
        chunk_size: int = 8 * 1024 * 1024,  # 8 MB default for better compatibility
        max_parallel: int = 4,
    ) -> None:
        self.session = session
        self.chunk_size = chunk_size
        self.max_parallel = max_parallel
        self._progress_callback: Optional[Callable[[TransferProgress], None]] = None

    def on_progress(self, callback: Callable[[TransferProgress], None]) -> None:
        self._progress_callback = callback

    async def upload(
        self,
        local_path: str,
        remote_path: str,
        *,
        max_speed_mbps: float = 0,
    ) -> dict[str, object]:
        """Upload using parallel chunks + remote reassembly."""
        local_file = Path(local_path).expanduser()
        if not local_file.exists():
            raise FileNotFoundError(f"Local file not found: {local_path}")
        file_size = local_file.stat().st_size

        if file_size <= self.chunk_size:
            return await self.session.upload_file(str(local_file), remote_path)

        num_chunks = (file_size + self.chunk_size - 1) // self.chunk_size
        chunk_files: list[str] = []

        try:
            with open(local_file, "rb") as f:
                for i in range(num_chunks):
                    chunk_path = f"{local_file}.part{i:04d}"
                    with open(chunk_path, "wb") as cf:
                        data = f.read(self.chunk_size)
                        cf.write(data)
                    chunk_files.append(chunk_path)

            semaphore = asyncio.Semaphore(self.max_parallel)
            transferred = 0
            start_time = time.monotonic()
            transfer_lock = asyncio.Lock()

            async def upload_chunk(i: int, chunk_path: str) -> None:
                nonlocal transferred
                async with semaphore:
                    if max_speed_mbps > 0:
                        async with transfer_lock:
                            elapsed = time.monotonic() - start_time
                            if elapsed > 0:
                                current_speed = (transferred / 1_000_000) / elapsed
                                if current_speed > max_speed_mbps:
                                    sleep_time = max(0, (transferred / 1_000_000 / max_speed_mbps) - elapsed)
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
                            total_bytes=file_size, transferred=transferred,
                            speed_mbps=round(speed, 2), eta_seconds=round(eta, 1)
                        ))

            async with asyncio.TaskGroup() as tg:
                for i, chunk_path in enumerate(chunk_files):
                    tg.create_task(upload_chunk(i, chunk_path))

            # Reassemble on remote (robust) - quoted for safety
            parts = " ".join(shlex.quote(f"{remote_path}.part{i:04d}") for i in range(num_chunks))
            rp_quoted = shlex.quote(remote_path)
            combine_cmd = (
                f"cat {parts} > {rp_quoted} 2>/dev/null || true; "
                f"rm -f {parts} 2>/dev/null || true"
            )
            await self.session.execute(combine_cmd)

            elapsed = time.monotonic() - start_time
            return {
                "success": True, "file_size": file_size, "chunks": num_chunks,
                "transfer_time": round(elapsed, 2),
                "speed_mbps": round((file_size / 1_000_000) / elapsed, 2) if elapsed > 0 else 0,
            }
        finally:
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
        """Download using parallel chunks. Falls back to single download if remote split unavailable."""
        # Validate + shell-quote remote_path up front. Previously this value was
        # interpolated directly into shell commands below (size check, cleanup)
        # without escaping, which meant a remote_path containing a single quote
        # (e.g. "foo' ; rm -rf ~ #") would break out of the quoting and inject
        # arbitrary shell commands on the remote host. shlex.quote() closes
        # that hole; validate_path() also rejects null bytes / traversal.
        remote_path = InputValidator.validate_path(remote_path)
        rp_quoted = shlex.quote(remote_path)

        local_file = Path(local_path).expanduser()
        local_file.parent.mkdir(parents=True, exist_ok=True)

        # Get size. The path is passed as argv[1] to the python3 fallback (not
        # embedded in the python source string) and shell-quoted for stat/wc,
        # so it can't be used to break out of the command.
        try:
            stat_result = await self.session.execute(
                f"python3 -c \"import os,sys; print(os.path.getsize(sys.argv[1]))\" "
                f"-- {rp_quoted} 2>/dev/null || "
                f"stat -c%s {rp_quoted} 2>/dev/null || wc -c < {rp_quoted}"
            )
            file_size = int(stat_result.get("stdout", "0").strip().splitlines()[-1] or 0)
        except Exception:
            file_size = 0

        if file_size <= self.chunk_size or file_size == 0:
            return await self.session.download_file(remote_path, str(local_file))

        # Try to use remote split (portable attempt)
        use_split = True
        try:
            # Test if split works. We only require that `split` exists and
            # is runnable (GNU coreutils vs. BusyBox/BSD variants both
            # support the -b/-d flags we use below), not a specific vendor.
            test_cmd = "which split >/dev/null 2>&1 && echo has-split || echo no-split"
            test_res = await self.session.execute(test_cmd)
            if "has-split" not in test_res.get("stdout", ""):
                use_split = False
        except Exception:
            use_split = False

        if not use_split:
            # Fallback to normal download for compatibility
            return await self.session.download_file(remote_path, str(local_file))

        num_chunks = (file_size + self.chunk_size - 1) // self.chunk_size

        # Split on remote with 4-digit suffix to match our :04d naming
        split_cmd = f"split -b {self.chunk_size} -d -a 4 {rp_quoted} {rp_quoted}.part 2>/dev/null || echo split-failed"
        split_res = await self.session.execute(split_cmd)
        if "split-failed" in split_res.get("stdout", ""):
            # Fallback
            return await self.session.download_file(remote_path, str(local_file))

        semaphore = asyncio.Semaphore(self.max_parallel)
        transferred = 0
        start_time = time.monotonic()
        transfer_lock = asyncio.Lock()
        # Track which chunks failed so we don't silently assemble a
        # corrupted/truncated file out of whatever happened to succeed.
        failed_chunks: list[tuple[int, str]] = []

        async def download_chunk(i: int) -> None:
            nonlocal transferred
            async with semaphore:
                if max_speed_mbps > 0:
                    async with transfer_lock:
                        elapsed = time.monotonic() - start_time
                        if elapsed > 0:
                            current_speed = (transferred / 1_000_000) / elapsed
                            if current_speed > max_speed_mbps:
                                sleep_time = max(0, (transferred / 1_000_000 / max_speed_mbps) - elapsed)
                                if sleep_time > 0:
                                    await asyncio.sleep(sleep_time)

                remote_chunk = f"{remote_path}.part{i:04d}"
                local_chunk = f"{local_file}.part{i:04d}"
                try:
                    result = await self.session.download_file(remote_chunk, local_chunk)
                    if os.path.exists(local_chunk):
                        chunk_size_bytes = result.get("file_size", 0) or os.path.getsize(local_chunk)
                    else:
                        chunk_size_bytes = 0
                    async with transfer_lock:
                        transferred += chunk_size_bytes
                except Exception as e:
                    # Previously this was silently swallowed, which let the
                    # reassembly step below build a corrupted/truncated file
                    # (a missing chunk just left a gap) without ever raising
                    # an error. Record the failure instead so it aborts.
                    async with transfer_lock:
                        failed_chunks.append((i, str(e)))

                if self._progress_callback:
                    elapsed = time.monotonic() - start_time
                    speed = (transferred / 1_000_000) / elapsed if elapsed > 0 else 0
                    eta = (file_size - transferred) / (speed * 1_000_000) if speed > 0 else 0
                    self._progress_callback(TransferProgress(
                        total_bytes=file_size, transferred=transferred,
                        speed_mbps=round(speed, 2), eta_seconds=round(eta, 1)
                    ))

        async with asyncio.TaskGroup() as tg:
            for i in range(num_chunks):
                tg.create_task(download_chunk(i))

        if failed_chunks:
            # Clean up whatever partial chunk files did land locally, then
            # bail out loudly instead of writing a corrupted file to disk.
            for i in range(num_chunks):
                chunk_path = f"{local_file}.part{i:04d}"
                if os.path.exists(chunk_path):
                    try:
                        os.remove(chunk_path)
                    except Exception:
                        pass
            details = ", ".join(f"part{i:04d}: {err}" for i, err in failed_chunks[:5])
            raise AIOSSHFileDownloadError(
                f"{len(failed_chunks)}/{num_chunks} chunk(s) failed to download: {details}",
                code="CHUNK_DOWNLOAD_FAILED",
                details={"remote_path": remote_path, "failed_chunks": len(failed_chunks)},
            )

        # Reassemble locally
        with open(local_file, "wb") as outfile:
            for i in range(num_chunks):
                chunk_path = f"{local_file}.part{i:04d}"
                with open(chunk_path, "rb") as infile:
                    outfile.write(infile.read())
                try:
                    os.remove(chunk_path)
                except Exception:
                    pass

        # Verify the reassembled file actually matches the expected size
        # before declaring success and deleting the remote parts.
        assembled_size = local_file.stat().st_size
        if assembled_size != file_size:
            raise AIOSSHFileDownloadError(
                f"Reassembled file size mismatch: expected {file_size} bytes, got {assembled_size}",
                code="SIZE_MISMATCH",
                details={"remote_path": remote_path, "expected": file_size, "actual": assembled_size},
            )

        # Cleanup remote parts (base path safely quoted; .part* left
        # unquoted so the shell still glob-expands it).
        await self.session.execute(f"rm -f {rp_quoted}.part* 2>/dev/null || true")

        elapsed = time.monotonic() - start_time
        return {
            "success": True, "file_size": file_size, "chunks": num_chunks,
            "transfer_time": round(elapsed, 2),
            "speed_mbps": round((file_size / 1_000_000) / elapsed, 2) if elapsed > 0 else 0,
        }
