from __future__ import annotations

import queue
import threading
import time
from datetime import datetime, timezone

from .database import JobStore


def parse_scheduled_at(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("scheduled_at must be an ISO-8601 datetime") from exc

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed.replace(microsecond=0)


def get_time_bucket(value: datetime) -> str:
    bucket_time = value.replace(minute=0, second=0, microsecond=0)
    return bucket_time.strftime("%Y%m%d%H")


class Scheduler:
    def __init__(
        self,
        store: JobStore,
        scan_interval_seconds: float = 1.0,
        worker_delay_seconds: float = 1.0,
    ) -> None:
        self.store = store
        self.scan_interval_seconds = scan_interval_seconds
        self.worker_delay_seconds = worker_delay_seconds
        self._queue: queue.Queue[int] = queue.Queue()
        self._started = False
        self._stop_event = threading.Event()
        self._threads: list[threading.Thread] = []
        self._start_lock = threading.Lock()

    def start(self) -> None:
        with self._start_lock:
            if self._started:
                return
            self._started = True
            self._threads = [
                threading.Thread(target=self._watcher_loop, name="task-watcher", daemon=True),
                threading.Thread(target=self._worker_loop, name="task-worker", daemon=True),
            ]
            for thread in self._threads:
                thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def _watcher_loop(self) -> None:
        while not self._stop_event.is_set():
            now = datetime.utcnow().replace(microsecond=0)
            bucket = get_time_bucket(now)
            for job in self.store.claim_due_jobs(bucket, now):
                self._queue.put(job.id)
            self._stop_event.wait(self.scan_interval_seconds)

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                job_id = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                if not self.store.mark_running(job_id):
                    continue
                time.sleep(self.worker_delay_seconds)
                self.store.mark_completed(job_id)
            except Exception as exc:  # pragma: no cover - defensive background guard
                self.store.mark_failed(job_id, str(exc))
            finally:
                self._queue.task_done()
