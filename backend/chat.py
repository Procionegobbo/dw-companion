"""Local chat CLI: run one assistant turn end to end (D20).

`uv run --env-file .env python -m backend.chat "<message>" [--roll] [--modifier N]`.
Verifies milestone 6 locally without the spec 008 FastAPI app.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections.abc import Mapping, Sequence
from uuid import uuid4

from backend.composition import ConfigError, Runtime, Settings, build_runtime
from backend.graph.state import Reply, TurnInput, TurnResult


def _print_reply(result: TurnResult, turn_input: TurnInput) -> None:
    reply: Reply = result.reply
    print(reply.text)

    if reply.citations:
        print()
        print("Citations:")
        for citation in reply.citations:
            print(f"- {citation.title}: {citation.url}")

    move = reply.move
    if move is not None and move.outcomes is not None:
        print()
        print(f"Move: {move.name} ({move.url})")
        print(f"10+: {move.outcomes.strong_hit}")
        print(f"7-9: {move.outcomes.weak_hit}")
        miss_text = move.outcomes.miss or "Not stated by this move."
        print(f"6-: {miss_text}")

    print()
    intent = result.intent or "-"
    print(
        f"kind={reply.kind} intent={intent} trace_id={turn_input.trace_id} "
        f"session_id={turn_input.session_id}"
    )


async def _run_and_close(runtime: Runtime, turn_input: TurnInput) -> TurnResult:
    try:
        return await runtime.assistant.run(turn_input)
    finally:
        await runtime.aclose()


def main(
    argv: Sequence[str] | None = None, environ: Mapping[str, str] | None = None
) -> int:
    env = environ if environ is not None else os.environ

    parser = argparse.ArgumentParser(prog="python -m backend.chat")
    parser.add_argument("message")
    parser.add_argument("--roll", action="store_true")
    parser.add_argument("--modifier", type=int, default=None)
    args = parser.parse_args(argv)

    try:
        settings = Settings.from_env(env)
        runtime = build_runtime(settings)
        turn_input = TurnInput(
            message=args.message,
            session_id=uuid4().hex,
            trace_id=uuid4().hex,
            roll_requested=args.roll,
            modifier=args.modifier,
        )
    except (ConfigError, ValueError, FileNotFoundError) as exc:
        print(f"chat: error: {exc}", file=sys.stderr)
        return 2

    result = asyncio.run(_run_and_close(runtime, turn_input))
    _print_reply(result, turn_input)
    return 1 if result.reply.kind == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
