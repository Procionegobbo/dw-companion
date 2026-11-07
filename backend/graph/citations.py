"""Deterministic citation validation (spec 006 D12).

`check_citations` keeps markers `[[section_id]]` whose id is in the retrieved set
verbatim, and removes any other marker together with the whitespace run that
precedes it. `valid_ids` / `invalid_ids` are the distinct ids involved, in
first-appearance order. Pure, no I/O: the LLM never decides which citations are
trustworthy, this code does.
"""

from __future__ import annotations

import re
from collections.abc import Collection
from dataclasses import dataclass

# Group 1: the whitespace run immediately before the marker (may be empty).
# Group 2: the section id itself (no brackets or whitespace).
_MARKER = re.compile(r"(\s*)\[\[([^\[\]\s]+)\]\]")


@dataclass(frozen=True, slots=True)
class CitationCheck:
    text: str
    valid_ids: tuple[str, ...]
    invalid_ids: tuple[str, ...]


def check_citations(answer: str, retrieved_ids: Collection[str]) -> CitationCheck:
    valid_ids: list[str] = []
    invalid_ids: list[str] = []
    seen_valid: set[str] = set()
    seen_invalid: set[str] = set()

    def replace(match: re.Match[str]) -> str:
        marker_id = match.group(2)
        if marker_id in retrieved_ids:
            if marker_id not in seen_valid:
                seen_valid.add(marker_id)
                valid_ids.append(marker_id)
            return match.group(0)
        if marker_id not in seen_invalid:
            seen_invalid.add(marker_id)
            invalid_ids.append(marker_id)
        return ""

    text = _MARKER.sub(replace, answer).strip()
    return CitationCheck(
        text=text, valid_ids=tuple(valid_ids), invalid_ids=tuple(invalid_ids)
    )
