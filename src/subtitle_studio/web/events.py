"""Event fan-out for the browser: one bus, many server-sent-event listeners.

Stages report progress through the same `(message, fraction)` callback the CLI
and TUI use; the bus turns those calls into events every open page receives.
A short history is kept so a page that connects mid-stage (or reloads) still
sees what already happened instead of a blank log.
"""

from __future__ import annotations

import itertools
import queue
import threading
import time

HISTORY_LIMIT = 400
QUEUE_LIMIT = 1000


class EventBus:
    def __init__(self, history_limit: int = HISTORY_LIMIT) -> None:
        self._lock = threading.Lock()
        self._subscribers: set[queue.Queue] = set()
        self._history: list[dict] = []
        self._history_limit = history_limit
        self._seq = itertools.count(1)

    def publish(self, event: dict) -> dict:
        """Stamp an event, remember it, hand it to every open page."""
        with self._lock:
            stamped = {"seq": next(self._seq), "ts": round(time.time(), 3), **event}
            self._history.append(stamped)
            if len(self._history) > self._history_limit:
                del self._history[: len(self._history) - self._history_limit]
            listeners = list(self._subscribers)
        for listener in listeners:
            try:
                listener.put_nowait(stamped)
            except queue.Full:  # a page that stopped reading must not block a stage
                pass
        return stamped

    def subscribe(self) -> queue.Queue:
        listener: queue.Queue = queue.Queue(maxsize=QUEUE_LIMIT)
        with self._lock:
            self._subscribers.add(listener)
        return listener

    def unsubscribe(self, listener: queue.Queue) -> None:
        with self._lock:
            self._subscribers.discard(listener)

    def history(self, after_seq: int = 0) -> list[dict]:
        with self._lock:
            return [event for event in self._history if event["seq"] > after_seq]
