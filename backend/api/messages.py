"""Fixed, server-authored copy for `backend/api/` (spec 008 User-Facing Copy:
Backend). ASCII apostrophes only, per the spec's exact-text requirement.
"""

from __future__ import annotations

from typing import Final

from backend.api.settings import MAX_MESSAGE_CHARS

UNSUPPORTED_MEDIA_TYPE_TEXT: Final = "The request must be sent as JSON."

REQUEST_TOO_LARGE_TEXT: Final = (
    "The request was too large. Please send a shorter message."
)

INVALID_REQUEST_TEXT: Final = (
    "The request was not valid. Please reload the page and try again."
)

MESSAGE_TOO_LONG_TEXT: Final = (
    f"Your message is too long. Please keep it to {MAX_MESSAGE_CHARS} characters "
    "or fewer."
)

BUDGET_EXHAUSTED_TEXT: Final = (
    "The demo budget is used up for today. Please come back tomorrow. The rules "
    "pages still work in the meantime."
)

RATE_LIMIT_MINUTE_TEXT: Final = (
    "You're sending messages too quickly. Please wait a minute and try again."
)

RATE_LIMIT_DAY_TEXT: Final = (
    "You've reached today's message limit for this demo. Please come back tomorrow."
)

TIMEOUT_TEXT: Final = "The assistant took too long to answer. Please try again."
