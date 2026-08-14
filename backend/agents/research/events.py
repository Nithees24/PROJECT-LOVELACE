"""Progress-event plumbing for the streaming deep-research pipeline.

The research pipeline is synchronous and long-running, so it executes in a
worker thread and reports progress by calling `emitter.emit(...)` at each step.
The streaming HTTP endpoint drains those events with `get()` and writes them to
the client as NDJSON (one JSON object per line). This is the contract the
frontend (Phase 2) consumes to render the plan (left pane) and the live
activity feed (right pane).

Event envelope (every event): {"seq": int, "ts": iso8601, "type": str, ...}

Types (payload keys in parentheses):
  run_started   (run_id, query)
  plan          (plan)                       ← left pane
  activity      (stage, title, status, section_id, detail)  ← right pane feed
  source        (source)                     ← right pane sources
  section_done  (section_id, synthesis)
  report        (markdown, sources)          ← final answer
  run_finished  (stats)
  error         (message)

activity.stage ∈ {planning, search, fetch, read, extract, reflect, write}
activity.status ∈ {started, ok, failed}
"""
import queue
import threading
from datetime import datetime, timezone

_SENTINEL = object()


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


class EventEmitter:
    """Thread-safe sink for research progress events.

    Producers (possibly several worker threads doing parallel scraping) call the
    typed helpers below; a single consumer drains via `get()` until it returns
    None (stream closed). `seq` is monotonic so the client can order/de-dupe.
    """

    def __init__(self):
        self._q = queue.Queue()
        self._seq = 0
        self._lock = threading.Lock()
        self._closed = False

    # -- core --
    def emit(self, type_, **payload):
        with self._lock:
            if self._closed:
                return None
            self._seq += 1
            event = {"seq": self._seq, "ts": _now_iso(), "type": type_}
        event.update(payload)
        self._q.put(event)
        return event

    def get(self, timeout=None):
        """Block for the next event; return None once the stream is closed."""
        item = self._q.get(timeout=timeout)
        return None if item is _SENTINEL else item

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._q.put(_SENTINEL)

    # -- typed helpers (the event contract) --
    def run_started(self, run_id, query):
        return self.emit("run_started", run_id=run_id, query=query)

    def plan(self, plan):
        return self.emit("plan", plan=plan)

    def activity(self, stage, title, status="started", section_id=None, detail=None):
        return self.emit(
            "activity", stage=stage, title=title, status=status,
            section_id=section_id, detail=detail,
        )

    def source(self, source):
        return self.emit("source", source=source)

    def section_done(self, section_id, synthesis):
        return self.emit("section_done", section_id=section_id, synthesis=synthesis)

    def report(self, markdown, sources):
        return self.emit("report", markdown=markdown, sources=sources)

    def run_finished(self, stats):
        return self.emit("run_finished", stats=stats)

    def error(self, message):
        return self.emit("error", message=message)


class NullEmitter(EventEmitter):
    """Discards all events — lets the non-streaming `run()` reuse the exact same
    streaming code path with zero overhead and no queue buildup."""

    def emit(self, type_, **payload):
        return None

    def get(self, timeout=None):
        return None

    def close(self):
        pass
