"""
Standalone background worker for Sooppiy.

Run this separately from the FastAPI process so HTTP requests are not competing
with price refreshes, profit-history compaction, and market-intel snapshots.
"""

import asyncio
import fcntl
import logging
import os
import signal
import sys
from contextlib import suppress

from database import init_database, get_database_status
from tasks import (
    DEFAULT_BACKGROUND_TASKS,
    WORKER_ROLES,
    _prune_profit_history,
    get_worker_lock_key,
    start_background_tasks,
    tasks_for_role,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def _renew_redis_lock(lock, timeout_seconds: int) -> None:
    interval = max(5, timeout_seconds // 3)
    while True:
        await asyncio.sleep(interval)
        try:
            lock.reacquire()
        except Exception as exc:
            logger.error("Lost worker singleton Redis lock: %s", exc)
            os._exit(1)


def _acquire_file_lock(role: str = "all"):
    # Per-role file lock so role-segmented workers don't fight over the same path.
    default_path = (
        "/tmp/sooppiy-worker.lock"
        if role == "all"
        else f"/tmp/sooppiy-worker-{role}.lock"
    )
    lock_path = os.getenv("SOOPPIY_WORKER_LOCK_FILE", default_path)
    handle = open(lock_path, "w", encoding="utf-8")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        logger.warning("Another Sooppiy %s worker is already running; lock_file=%s", role, lock_path)
        return None
    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()))
    handle.flush()
    return handle


def _release_file_lock(handle) -> None:
    if handle is None:
        return
    with suppress(Exception):
        fcntl.flock(handle, fcntl.LOCK_UN)
    with suppress(Exception):
        handle.close()


async def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(line_buffering=True)
        except Exception:
            pass
    try:
        os.nice(int(os.getenv("SOOPPIY_WORKER_NICE", "10")))
    except Exception:
        pass

    redis_lock = None
    file_lock_handle = None
    lock_renew_task = None
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signame in ("SIGINT", "SIGTERM"):
        with suppress(Exception):
            loop.add_signal_handler(getattr(signal, signame), stop_event.set)
    tasks: list[asyncio.Task] = []
    try:
        lock_timeout_seconds = max(30, int(os.getenv("SOOPPIY_WORKER_LOCK_TIMEOUT_SECONDS", "120")))
    except Exception:
        lock_timeout_seconds = 120

    # Phase 4.6: role-segmented workers. SOOPPIY_WORKER_ROLE picks which
    # task subset this process runs; each role uses a distinct lock key so
    # role-specialised workers can run side-by-side.
    role = (os.getenv("SOOPPIY_WORKER_ROLE", "all").strip() or "all").lower()
    if role not in WORKER_ROLES:
        logger.error(
            "Invalid SOOPPIY_WORKER_ROLE=%r; expected one of %s",
            role, WORKER_ROLES,
        )
        return
    lock_key = get_worker_lock_key(role)
    logger.info(
        "Starting Sooppiy worker role=%s tasks=%s",
        role, tasks_for_role(role),
    )

    try:
        from cache import acquire_lock

        redis_lock = acquire_lock(
            lock_key,
            timeout_seconds=lock_timeout_seconds,
            blocking=False,
        )
        if redis_lock is not None:
            acquired = bool(redis_lock.acquire(blocking=False))
            if not acquired:
                logger.warning("Another Sooppiy %s worker is already running; Redis singleton lock %s is held.", role, lock_key)
                return
            lock_renew_task = asyncio.create_task(
                _renew_redis_lock(redis_lock, lock_timeout_seconds),
                name=f"sooppiy:{role}_worker_lock_renew",
            )
            logger.info("Acquired %s worker singleton lock via Redis (%s)", role, lock_key)
        else:
            file_lock_handle = _acquire_file_lock(role)
            if file_lock_handle is None:
                return
            logger.info("Acquired %s worker singleton lock via file", role)
    except Exception:
        if redis_lock is not None:
            with suppress(Exception):
                redis_lock.release()
        logger.exception("Failed to acquire %s worker singleton lock", role)
        return

    try:
        init_database()
        logger.info("Worker database ready: %s", get_database_status())

        if os.getenv("SOOPPIY_BACKGROUND_TASKS") is None:
            os.environ["SOOPPIY_BACKGROUND_TASKS"] = DEFAULT_BACKGROUND_TASKS

        tasks = start_background_tasks(logger)
        if not tasks:
            logger.warning("No background tasks enabled; set SOOPPIY_BACKGROUND_TASKS to a comma-separated task list.")
            return

        if os.getenv("PROFIT_HISTORY_PRUNE_ON_WORKER_START", "false").strip().lower() in {"1", "true", "yes", "on"}:
            logger.info("Scheduling startup profit history prune")
            tasks.append(asyncio.create_task(asyncio.to_thread(_prune_profit_history), name="sooppiy:startup_profit_history_prune"))

        await stop_event.wait()
        logger.info("Worker shutdown requested")
    finally:
        for task in tasks:
            task.cancel()
        if tasks:
            with suppress(Exception):
                await asyncio.gather(*tasks, return_exceptions=True)
        if lock_renew_task is not None:
            lock_renew_task.cancel()
            with suppress(asyncio.CancelledError):
                await lock_renew_task
        if redis_lock is not None:
            with suppress(Exception):
                redis_lock.release()
        _release_file_lock(file_lock_handle)


if __name__ == "__main__":
    asyncio.run(main())
