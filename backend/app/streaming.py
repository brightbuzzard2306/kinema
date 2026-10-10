"""Server-Sent Events for a chat turn.

The turn runs in a worker thread and reports REAL milestones through ``emit`` (step / cards). This module turns them into an
SSE stream so the browser can show the picks as soon as they are ranked, while the reply is still being written.

Event order: step(interpret) -> step(rank) -> cards -> step(write) -> done   (simple replies skip rank/cards).
On failure a single ``error`` event is sent instead of ``done``. A comment heartbeat keeps proxies from closing idle connections.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
from collections.abc import Callable, Iterator

from .schemas import ChatResponse

log = logging.getLogger("rs.stream")

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "X-Accel-Buffering": "no",  # tell nginx-style proxies not to buffer the stream
    "Connection": "keep-alive",
}
_DONE = object()


def sse(name: str, data: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def event_stream(run: Callable[[Callable[[dict], None]], ChatResponse], heartbeat: float = 10.0) -> Iterator[str]:
    """Run ``run(emit)`` in a thread and yield its events as SSE text."""
    events: queue.Queue = queue.Queue()

    def worker() -> None:
        try:
            result = run(events.put)
            events.put({"event": "done", "response": result.model_dump(mode="json")})
        except KeyError:
            events.put({"event": "error", "status": 404, "code": "not_found", "message": "That movie does not exist in the catalogue."})
        except Exception:  # noqa: BLE001 - never leak internals to the client
            log.exception("stream turn failed")
            events.put({"event": "error", "status": 500, "code": "internal_error", "message": "Something went wrong on our side. Please try again."})
        finally:
            events.put(_DONE)

    threading.Thread(target=worker, daemon=True).start()
    while True:
        try:
            item = events.get(timeout=heartbeat)
        except queue.Empty:
            yield ": ping\n\n"
            continue
        if item is _DONE:
            return
        payload = dict(item)
        yield sse(payload.pop("event"), payload)
