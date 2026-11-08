"""Tests for `backend/api/sse.py` (spec 008 Testing)."""

from __future__ import annotations

import pytest

from backend.api.sse import sse_event


def test_frame_format() -> None:
    assert (
        sse_event("status", {"step": "router"})
        == b'event: status\ndata: {"step":"router"}\n\n'
    )


def test_newlines_in_data_are_escaped() -> None:
    frame = sse_event("reply", {"text": "a\n\nb"})
    lines = frame.decode("utf-8").split("\n")

    data_lines = [line for line in lines if line.startswith("data:")]
    assert len(data_lines) == 1
    assert "a\\n\\nb" in data_lines[0]


def test_non_ascii_preserved() -> None:
    frame = sse_event("reply", {"text": "\u2019"})

    assert "\u2019".encode() in frame
    assert b"\\u2019" not in frame


def test_invalid_event_name_rejected() -> None:
    with pytest.raises(ValueError, match="event"):
        sse_event("bad name", {})
