#!/usr/bin/env python3
"""
Example 4: Session Recording & Replay for Auditing / Training (v1.1.0)

Record everything that happens in an SSH session and replay it later.
Useful for compliance, debugging, and training new engineers.
"""

import asyncio
from aiossh import AIOSSH, SessionRecorder, SessionReplayer


async def main():
    

    async with AIOSSH() as client:
        session = await client.connect(
            host="192.0.2.10",
            username="admin",
            password="your-password",
        )

        # === RECORDING ===
        recorder = SessionRecorder(
            session_id="deploy-prod-2026-07-16",
            storage_dir="~/.aiossh/recordings"
        )
        recorder.start()

        print("Recording started...")

        # Run some commands
        result1 = await session.execute("uname -a")
        recorder.record_command("uname -a")
        recorder.record_result(result1)

        result2 = await session.execute("df -h | head -5")
        recorder.record_command("df -h | head -5")
        recorder.record_result(result2)

        recorder.stop()
        filepath = await recorder.save(compress=True)

        print(f"Recording saved to: {filepath}")

        # === REPLAY ===
        print("\n Replaying recorded session at 3x speed...\n")

        replayer = SessionReplayer(filepath)
        await replayer.load()

        summary = replayer.get_summary()
        print(f"Summary: {summary['commands_executed']} commands recorded\n")

        def replay_callback(event_type, data):
            if event_type == "command":
                print(f"  $ {data['command']}")
            elif event_type == "result":
                if data.get("stdout"):
                    print(f"     → {data['stdout'][:80]}...")

        await replayer.replay(speed=3.0, callback=replay_callback)

        print("\nReplay finished!")


if __name__ == "__main__":
    asyncio.run(main())
