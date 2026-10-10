import asyncio
import contextlib
import logging

from backend.database import close_db, init_db, record_heartbeat, require_current_schema
from backend.logging_utils import configure_logging
from backend.services.jobs import worker_forever
from backend.settings import settings

logger = logging.getLogger("ragapp.worker")


async def _heartbeat_loop(stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        await record_heartbeat("worker")
        await asyncio.sleep(max(5, settings.worker_heartbeat_ttl_seconds // 3))


async def main() -> None:
    configure_logging(settings.log_level)
    await init_db()
    await require_current_schema()
    stop_event = asyncio.Event()
    heartbeat_task = asyncio.create_task(_heartbeat_loop(stop_event))
    try:
        logger.info("worker_started")
        await worker_forever(stop_event)
    finally:
        stop_event.set()
        heartbeat_task.cancel()
        # Wait for the cancellation to land so an in-flight heartbeat write
        # never races with the pool being closed underneath it.
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat_task
        await close_db()
        logger.info("worker_stopped")


if __name__ == "__main__":
    asyncio.run(main())
