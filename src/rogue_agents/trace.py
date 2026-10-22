"""Structured logging: every run is a stream of JSON events.

The same stream drives the live terminal view, the JSONL trace on disk, and
replays, so what you see on stage is exactly what was recorded.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable

Listener = Callable[[dict], None]


class Tracer:
    def __init__(self, path: str | Path | None = None, listeners: list[Listener] | None = None):
        self.t0 = time.monotonic()
        self.events: list[dict] = []
        self.listeners = list(listeners or [])
        self.file = None
        if path:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            self.file = open(path, "w", encoding="utf-8")

    def emit(self, type: str, **data) -> dict:
        event = {"t": round(time.monotonic() - self.t0, 3), "type": type, **data}
        self.events.append(event)
        if self.file:
            self.file.write(json.dumps(event, ensure_ascii=False) + "\n")
            self.file.flush()
        for listener in self.listeners:
            listener(event)
        return event

    def close(self) -> None:
        if self.file:
            self.file.close()
            self.file = None


def load(path: str | Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
