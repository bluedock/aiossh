#!/usr/bin/env python3
"""
Example 2: High-Speed Parallel File Transfer with Progress (v1.1.0)

Demonstrates ParallelSCP for very fast uploads/downloads of large files.
"""

import asyncio
from pathlib import Path
from aiossh import AIOSSH, ParallelSCP


async def main():
    

    async with AIOSSH() as client:
        session = await client.connect(
            host="192.0.2.10",
            username="admin",
            password="your-password",
        )

        # Create ParallelSCP instance
        scp = ParallelSCP(
            session,
            chunk_size=16 * 1024 * 1024,  # 16 MB chunks
            max_parallel=6,               # 6 parallel connections
        )

        # Progress callback
        def show_progress(p):
            percent = (p.transferred / p.total_bytes) * 100 if p.total_bytes > 0 else 0
            print(f"  {percent:6.1f}% | {p.speed_mbps:6.1f} MB/s | ETA {p.eta_seconds:5.1f}s")

        scp.on_progress(show_progress)

        # === Upload Example ===
        local_file = "/tmp/large-test-file.bin"
        remote_file = "/tmp/large-test-file.bin"

        # Create a test file if it doesn't exist (100MB)
        if not Path(local_file).exists():
            print("Creating 100MB test file...")
            with open(local_file, "wb") as f:
                f.write(b"0" * (100 * 1024 * 1024))

        print(f"\nUploading {local_file} → {remote_file}")
        result = await scp.upload(local_file, remote_file, max_speed_mbps=0)  # 0 = unlimited

        print("\nUpload finished!")
        print(f"   Speed: {result['speed_mbps']:.2f} MB/s")
        print(f"   Time:  {result['transfer_time']:.2f} seconds")
        print(f"   Chunks: {result['chunks']}")

        # === Download Example ===
        print(f"\nDownloading back...")
        download_result = await scp.download(remote_file, "/tmp/downloaded-back.bin")

        print("\nDownload finished!")
        print(f"   Speed: {download_result['speed_mbps']:.2f} MB/s")


if __name__ == "__main__":
    asyncio.run(main())
