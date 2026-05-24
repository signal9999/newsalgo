import asyncio
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from engine.orchestrator import Orchestrator
from config.settings import PAPER_TRADE


async def main():
    mode = "PAPER TRADE" if PAPER_TRADE else "LIVE TRADE"
    print(f"[NewsAlgo] Starting in {mode} mode")

    orchestrator = Orchestrator()

    loop = asyncio.get_running_loop()

    def _shutdown():
        print("\n[NewsAlgo] Shutting down...")
        asyncio.ensure_future(orchestrator.stop())
        for task in asyncio.all_tasks(loop):
            task.cancel()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _shutdown)

    await orchestrator.run()


if __name__ == "__main__":
    asyncio.run(main())
