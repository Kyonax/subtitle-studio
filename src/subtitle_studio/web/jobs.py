"""One stage at a time, in a background thread, reported to every open page.

The pipeline loads big models onto the GPU one at a time (the VRAM law in
`gpu.py`), so the browser gets the same discipline: a single job slot. A second
request while a stage runs is refused with a clear message instead of queuing
two model loads onto the same card.
"""

from __future__ import annotations

import threading
import time
import traceback
import uuid
from dataclasses import asdict, dataclass, field
from typing import Callable

from subtitle_studio.web.events import EventBus

ProgressFn = Callable[[str, float], None]
StageFn = Callable[[ProgressFn], object]


class Busy(RuntimeError):
    """Raised when a stage is asked for while another one is still running."""


@dataclass
class Job:
    id: str
    stage: str
    label: str
    status: str = "running"  # running | done | error
    message: str = ""
    fraction: float = 0.0
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    result: str | None = None
    error: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


class JobRunner:
    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._lock = threading.Lock()
        self._current: Job | None = None
        self._recent: list[Job] = []

    @property
    def current(self) -> Job | None:
        with self._lock:
            return self._current

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "current": self._current.as_dict() if self._current else None,
                "recent": [job.as_dict() for job in self._recent[-10:]],
            }

    def submit(self, stage: str, label: str, fn: StageFn) -> Job:
        with self._lock:
            if self._current is not None:
                raise Busy(f"{self._current.label} is still running — wait for it to finish")
            job = Job(id=uuid.uuid4().hex[:12], stage=stage, label=label)
            self._current = job
        self._bus.publish({"type": "job", "event": "start", "job": job.as_dict()})
        self.log(f"{label} started", level="info")
        threading.Thread(target=self._work, args=(job, fn), daemon=True, name=f"stage-{stage}").start()
        return job

    def log(self, message: str, level: str = "info") -> None:
        self._bus.publish({"type": "log", "level": level, "message": message})

    def _work(self, job: Job, fn: StageFn) -> None:
        def progress(message: str, fraction: float) -> None:
            job.message = message
            job.fraction = max(0.0, min(float(fraction or 0.0), 1.0))
            self._bus.publish(
                {
                    "type": "progress",
                    "stage": job.stage,
                    "job": job.id,
                    "message": message,
                    "fraction": job.fraction,
                }
            )
            self.log(f"  {message}")

        try:
            result = fn(progress)
            job.status = "done"
            job.fraction = 1.0
            job.result = str(result) if result is not None else None
            self.log(f"{job.label} done{f' -> {job.result}' if job.result else ''}", level="ok")
        except Exception as exc:  # every stage failure belongs on the page, not in a terminal
            job.status = "error"
            job.error = f"{type(exc).__name__}: {exc}"
            self.log(job.error, level="error")
            self._bus.publish({"type": "trace", "text": traceback.format_exc()})
        finally:
            job.finished_at = time.time()
            with self._lock:
                self._current = None
                self._recent.append(job)
                del self._recent[:-10]
            self._bus.publish({"type": "job", "event": "end", "job": job.as_dict()})
            self._bus.publish({"type": "invalidate"})  # pages refetch their state


class BusConsole:
    """A file-like object so `models pull` (which writes to a rich Console) can
    report into the page instead of a terminal."""

    def __init__(self, runner: JobRunner) -> None:
        self._runner = runner
        self._buffer = ""

    def write(self, text: str) -> int:
        self._buffer += text
        while "\n" in self._buffer:
            line, _, self._buffer = self._buffer.partition("\n")
            if line.strip():
                self._runner.log(line.rstrip())
        return len(text)

    def flush(self) -> None:
        if self._buffer.strip():
            self._runner.log(self._buffer.rstrip())
        self._buffer = ""

    def isatty(self) -> bool:
        return False
