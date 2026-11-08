"""The one SSE frame formatter `backend/api/app.py` uses (spec 008 D1, D5).

Each frame is `event: <name>\\ndata: <single-line JSON>\\n\\n`, UTF-8 encoded, with
no `id`/`retry` fields and no keep-alive comments.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping

from backend.api.schemas import JsonValue

_EVENT_NAME = re.compile(r"^[a-z_]+$")


def sse_event(event: str, data: Mapping[str, JsonValue]) -> bytes:
    if not _EVENT_NAME.fullmatch(event):
        raise ValueError(f"invalid sse_event: event must match {_EVENT_NAME.pattern!r}")
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n".encode()
