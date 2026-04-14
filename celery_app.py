# TaskForge — Celery Worker Configuration & Task Definitions
# Author: Dhaatrik Chowdhury <https://github.com/dhaatrik>
# Repository: https://github.com/dhaatrik/distributed-task-queue
# License: MIT

import os
import sqlite3
import time
import logging
from datetime import datetime

from celery import Celery
from celery.signals import task_failure, task_success

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (Externalize via environment variables)
# ---------------------------------------------------------------------------
CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND: str = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")
DATABASE_URL: str = os.getenv("DATABASE_URL", "tasks_and_users.db")

# ---------------------------------------------------------------------------
# Celery application
# ---------------------------------------------------------------------------
app = Celery("tasks", broker=CELERY_BROKER_URL, backend=CELERY_RESULT_BACKEND)

app.conf.task_serializer = "json"
app.conf.accept_content = ["json"]  # Ensure the worker only accepts JSON
app.conf.result_serializer = "json"

# Configure task queues for prioritization
app.conf.task_queues = {
    "default": {"exchange": "default", "routing_key": "default"},
    "high_priority": {"exchange": "high_priority", "routing_key": "high_priority"},
}

# Enable late acknowledgment for fault tolerance and set result expiration
app.conf.task_acks_late = True
app.conf.result_expires = 3600  # Results expire after 1 hour


# ---------------------------------------------------------------------------
# Custom base task with exponential-backoff retries
# ---------------------------------------------------------------------------
class BaseTaskWithRetry(app.Task):
    """
    Abstract base task that auto-retries on transient network/IO errors using
    an exponential backoff strategy (2^n seconds between attempts).

    Subclass tasks inherit this behaviour automatically without any extra
    boilerplate — just set `base=BaseTaskWithRetry` on the `@app.task` decorator.
    """

    abstract = True
    max_retries = 3
    # Only retry on transient infrastructure errors; let business-logic
    # exceptions (TypeError, ValueError, etc.) propagate as FAILURE immediately.
    _transient_exceptions = (ConnectionError, TimeoutError, OSError)

    def on_failure(self, exc, task_id, args, kwargs, einfo):  # type: ignore[override]
        if isinstance(exc, self._transient_exceptions):
            retries = self.request.retries
            if retries < self.max_retries:
                countdown = 2**retries  # 1 s → 2 s → 4 s
                logger.warning(
                    "Task %s hit transient error %r. Retrying in %ds (attempt %d/%d).",
                    task_id,
                    exc,
                    countdown,
                    retries + 1,
                    self.max_retries,
                )
                raise self.retry(exc=exc, countdown=countdown)
        logger.error("Task %s failed permanently: %r", task_id, exc)
        super().on_failure(exc, task_id, args, kwargs, einfo)


# ---------------------------------------------------------------------------
# Celery signals — write results to SQLite the moment a task finishes
#
# Celery workers run synchronously, so we use the standard `sqlite3` module
# here (not `aiosqlite`).  The FastAPI side continues to use `aiosqlite`.
# ---------------------------------------------------------------------------
def _update_task_db(task_id: str, status: str, result: str) -> None:
    """Persist the final task state to the shared SQLite database."""
    try:
        with sqlite3.connect(DATABASE_URL) as conn:
            conn.execute(
                "UPDATE tasks SET status = ?, result = ?, completed_at = ? WHERE task_id = ?",
                (status, result, datetime.utcnow().isoformat(), task_id),
            )
        logger.info("Task %s → %s written to database.", task_id, status)
    except Exception as exc:  # noqa: BLE001
        logger.error("DB update failed for task %s (%s): %r", task_id, status, exc)


@task_success.connect
def on_task_success(sender, result, **kwargs) -> None:  # type: ignore[misc]
    """Persist SUCCESS state to the database immediately after a worker finishes."""
    task_id = sender.request.id
    if task_id:
        _update_task_db(task_id, "SUCCESS", str(result))


@task_failure.connect
def on_task_failure(sender, task_id, exception, **kwargs) -> None:  # type: ignore[misc]
    """Persist FAILURE state to the database immediately after a worker errors."""
    if task_id:
        _update_task_db(task_id, "FAILURE", str(exception))


# ---------------------------------------------------------------------------
# Task definitions
# ---------------------------------------------------------------------------
@app.task(bind=True, max_retries=3, default_retry_delay=60, queue="default")
def process_task(self, data: str) -> str:
    """Generic long-running task; retries automatically on any exception."""
    try:
        time.sleep(5)  # Simulate heavy computation
        return f"Processed: {data}"
    except Exception as exc:
        raise self.retry(exc=exc)


@app.task(base=BaseTaskWithRetry, queue="default")
def add_numbers(numbers: list) -> float:
    """Return the sum of a list of numbers."""
    if not isinstance(numbers, list):
        raise TypeError("Input must be a list of numbers.")
    for num in numbers:
        if not isinstance(num, (int, float)):
            raise TypeError(f"List contains non-numeric element: {num}")
    return float(sum(numbers))


@app.task(base=BaseTaskWithRetry, queue="default")
def simulate_image_processing(image_id: str) -> str:
    """Simulate image processing with a short delay."""
    if not isinstance(image_id, str) or not image_id.strip():
        raise ValueError("image_id must be a non-empty string.")
    time.sleep(1)  # Simulate image processing time
    return f"Image {image_id} processed successfully."


# ---------------------------------------------------------------------------
# SECURITY BEST PRACTICES for Broker/Backend (Redis):
# 1. Include credentials in CELERY_BROKER_URL / CELERY_RESULT_BACKEND,
#    e.g. 'redis://:yourpassword@localhost:6379/0'.
# 2. Restrict network access to Redis using firewall rules or ACLs.
# 3. Enable Redis protected mode when binding to non-loopback interfaces.
# 4. Use SSL/TLS (rediss://) when communicating over untrusted networks.
# ---------------------------------------------------------------------------