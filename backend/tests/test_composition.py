"""Tests for the composition root and the chat CLI (spec 007 Testing)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from pathlib import Path
from uuid import uuid4

import httpx2
import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from backend import chat
from backend.adapters.retrieval.bm25 import tokenize
from backend.adapters.retrieval.chunking import build_chunks
from backend.adapters.retrieval.index import write_index
from backend.composition import (
    ENV_VARS,
    REPO_ROOT,
    ConfigError,
    LangfuseSettings,
    Runtime,
    Settings,
    build_runtime,
)
from backend.domain.rulebook import move_from_dict, section_from_dict
from backend.graph.state import TurnInput
from backend.ports.errors import PortError
from backend.tests.adapter_helpers import (
    SyncHandler,
    chat_completion_json,
    embeddings_json,
    mini_normalized,
    mock_http,
)
from backend.tests.domain_helpers import ScriptedRandom
from backend.tests.fakes.embedder import FakeEmbedder
from backend.tests.fakes.llm import FakeLLMClient
from backend.tests.fakes.retriever import FakeRetriever
from backend.tests.graph_helpers import chunk as fake_chunk
from backend.tests.graph_helpers import make_assistant, router_json

TRACE_A = "ab" * 16
TRACE_B = "cd" * 16


def _valid_env(**overrides: str) -> dict[str, str]:
    env = {
        "OPENROUTER_API_KEY": "key",
        "MODEL_ROUTER": "m-router",
        "MODEL_CLASSIFIER": "m-classifier",
        "MODEL_ANSWER": "m-answer",
        "MODEL_EMBEDDINGS": "fake-embed",
    }
    env.update(overrides)
    return env


def _write_index(
    tmp_path: Path, embedding_model: str = "fake-embed"
) -> tuple[Path, Path]:
    normalized_dir = mini_normalized(tmp_path)
    sections_raw = json.loads(
        (normalized_dir / "sections.json").read_text(encoding="utf-8")
    )
    moves_raw = json.loads((normalized_dir / "moves.json").read_text(encoding="utf-8"))
    sections = [section_from_dict(item) for item in sections_raw]
    moves = [move_from_dict(item) for item in moves_raw]
    chunks = build_chunks(sections, moves)
    embedder = FakeEmbedder(dim=64)
    vectors = asyncio.run(embedder.embed([c.index_text for c in chunks]))
    index_dir = tmp_path / "index"
    write_index(index_dir, chunks, vectors, embedding_model)
    return index_dir, normalized_dir


def _fake_vector(text: str, dim: int = 64) -> list[float]:
    """Mirrors `FakeEmbedder`'s hashed bag-of-words algorithm, so the mocked
    `/embeddings` endpoint returns vectors matching the `FakeEmbedder`-built index."""
    vector = [0.0] * dim
    for token in tokenize(text):
        index = int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16)
        vector[index % dim] += 1.0
    if all(value == 0.0 for value in vector):
        vector[0] = 1.0
    return vector


def _e2e_handler(
    chat_responses: dict[str, str],
) -> tuple[SyncHandler, list[dict[str, object]]]:
    """Routes chat completions by model and embeddings through `_fake_vector`'s
    deterministic hashing, so retrieval over the `FakeEmbedder`-built index works."""
    bodies: list[dict[str, object]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        if request.url.path.endswith("/embeddings"):
            vectors = [_fake_vector(text) for text in body["input"]]
            return httpx2.Response(
                200, json=embeddings_json(vectors, model=body["model"])
            )
        bodies.append(body)
        model = body["model"]
        content = chat_responses[model]
        return httpx2.Response(200, json=chat_completion_json(content, model=model))

    return handler, bodies


def test_settings_from_env_valid() -> None:
    env = {
        "OPENROUTER_API_KEY": "  key  ",
        "MODEL_ROUTER": " m-router ",
        "MODEL_CLASSIFIER": " m-classifier ",
        "MODEL_ANSWER": " m-answer ",
        "MODEL_EMBEDDINGS": " m-embed ",
        "LANGFUSE_PUBLIC_KEY": " pk ",
        "LANGFUSE_SECRET_KEY": " sk ",
    }

    settings = Settings.from_env(env)

    assert settings.openrouter_api_key == "key"
    assert settings.model_router == "m-router"
    assert settings.model_classifier == "m-classifier"
    assert settings.model_answer == "m-answer"
    assert settings.model_embeddings == "m-embed"
    assert settings.langfuse == LangfuseSettings(
        "pk", "sk", "https://cloud.langfuse.com"
    )


def test_settings_lists_all_missing() -> None:
    with pytest.raises(ConfigError) as exc_info:
        Settings.from_env({})

    message = str(exc_info.value)
    assert message.startswith("invalid configuration: ")
    for name in (
        "OPENROUTER_API_KEY",
        "MODEL_ROUTER",
        "MODEL_CLASSIFIER",
        "MODEL_ANSWER",
        "MODEL_EMBEDDINGS",
    ):
        assert name in message


def test_whitespace_counts_as_unset() -> None:
    env = dict.fromkeys(ENV_VARS, "   ")

    with pytest.raises(ConfigError) as exc_info:
        Settings.from_env(env)

    message = str(exc_info.value)
    for name in (
        "OPENROUTER_API_KEY",
        "MODEL_ROUTER",
        "MODEL_CLASSIFIER",
        "MODEL_ANSWER",
        "MODEL_EMBEDDINGS",
    ):
        assert name in message


def test_langfuse_half_configured_rejected() -> None:
    env = _valid_env(LANGFUSE_PUBLIC_KEY="pk")

    with pytest.raises(
        ConfigError,
        match="LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY must both be set or both "
        "be empty",
    ):
        Settings.from_env(env)


def test_langfuse_absent_gives_null_tracer_and_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    index_dir, normalized_dir = _write_index(tmp_path)
    settings = Settings.from_env(_valid_env())
    assert settings.langfuse is None

    with caplog.at_level(logging.WARNING, logger="backend.composition"):
        runtime = build_runtime(
            settings, index_dir=index_dir, normalized_dir=normalized_dir
        )

    assert any("tracing disabled" in record.getMessage() for record in caplog.records)
    asyncio.run(runtime.aclose())


def test_settings_repr_hides_secrets() -> None:
    env = _valid_env(
        OPENROUTER_API_KEY="or-super-secret",
        LANGFUSE_PUBLIC_KEY="lf-public-secret",
        LANGFUSE_SECRET_KEY="lf-secret-secret",
    )

    settings = Settings.from_env(env)
    text = repr(settings)

    assert "or-super-secret" not in text
    assert "lf-public-secret" not in text
    assert "lf-secret-secret" not in text


def test_env_example_declares_every_setting() -> None:
    env_example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    keys = {
        line.split("=", 1)[0]
        for line in env_example.splitlines()
        if line and not line.startswith("#") and "=" in line
    }

    for name in ENV_VARS:
        assert name in keys


def test_embedding_model_mismatch_rejected(tmp_path: Path) -> None:
    index_dir, normalized_dir = _write_index(tmp_path, embedding_model="fake-embed")
    settings = Settings.from_env(_valid_env(MODEL_EMBEDDINGS="other"))

    with pytest.raises(ConfigError) as exc_info:
        build_runtime(settings, index_dir=index_dir, normalized_dir=normalized_dir)

    message = str(exc_info.value)
    assert "fake-embed" in message
    assert "other" in message


def test_end_to_end_rules_turn_with_real_adapters(tmp_path: Path) -> None:
    index_dir, normalized_dir = _write_index(tmp_path)
    responses = {
        "m-router": json.dumps({"intent": "rules_question", "confidence": 0.9}),
        "m-answer": "Hack and Slash lets you deal damage. [[moves/hack-and-slash]]",
    }
    handler, bodies = _e2e_handler(responses)
    http_client = mock_http(handler)
    exporter = InMemorySpanExporter()
    settings = Settings.from_env(
        _valid_env(
            LANGFUSE_PUBLIC_KEY=f"pk-test-{uuid4().hex}", LANGFUSE_SECRET_KEY="sk-test"
        )
    )

    runtime = build_runtime(
        settings,
        index_dir=index_dir,
        normalized_dir=normalized_dir,
        http_client=http_client,
        span_exporter=exporter,
    )
    result = asyncio.run(
        runtime.assistant.run(
            TurnInput(
                message="How does hack and slash work?",
                session_id="s1",
                trace_id=TRACE_A,
            )
        )
    )
    asyncio.run(runtime.aclose())

    assert result.reply.kind == "rules_answer"
    assert len(result.reply.citations) == 1
    assert result.reply.citations[0].url == "/rules/moves/hack-and-slash/"

    max_tokens_by_model = {body["model"]: body["max_tokens"] for body in bodies}
    assert max_tokens_by_model == {"m-router": 100, "m-answer": 700}

    spans = exporter.get_finished_spans()
    span_names = {span.name for span in spans}
    assert {"router", "retrieve", "answer_with_citations", "citation_validator"} <= (
        span_names
    )
    generations = [
        span
        for span in spans
        if span.attributes is not None
        and span.attributes.get("langfuse.observation.type") == "generation"
    ]
    assert len(generations) == 2
    for generation in generations:
        assert generation.attributes is not None
        assert "langfuse.observation.usage_details" in generation.attributes
        assert "langfuse.observation.cost_details" in generation.attributes

    for span in spans:
        assert span.attributes is not None
        assert span.attributes["session.id"] == "s1"
        assert span.context is not None
        assert format(span.context.trace_id, "032x") == TRACE_A


def test_end_to_end_move_turn_with_roll(tmp_path: Path) -> None:
    index_dir, normalized_dir = _write_index(tmp_path)
    responses = {
        "m-router": json.dumps({"intent": "action_description", "confidence": 0.9}),
        "m-classifier": json.dumps(
            {
                "move_id": "hack-and-slash",
                "confidence": 0.9,
                "stat": "STR",
                "rationale": "You attack an enemy in melee.",
                "alternatives": [],
            }
        ),
        "m-answer": "You attack with your blade, triggering Hack and Slash.",
    }
    handler, _bodies = _e2e_handler(responses)
    http_client = mock_http(handler)
    settings = Settings.from_env(_valid_env())

    runtime = build_runtime(
        settings,
        index_dir=index_dir,
        normalized_dir=normalized_dir,
        http_client=http_client,
        rng=ScriptedRandom([4, 5]),
    )
    result = asyncio.run(
        runtime.assistant.run(
            TurnInput(
                message="I swing my sword at the goblin",
                session_id="s1",
                trace_id=TRACE_B,
                roll_requested=True,
                modifier=1,
            )
        )
    )
    asyncio.run(runtime.aclose())

    assert result.reply.kind == "move"
    assert result.reply.move is not None
    assert result.reply.move.outcome is not None
    assert result.reply.move.outcome.band == "strong_hit"
    assert result.reply.text.endswith("Rolled 4 + 5 + 1 = 10: 10+.")


def test_build_runtime_meters_llm_cost_when_hook_given(tmp_path: Path) -> None:
    index_dir, normalized_dir = _write_index(tmp_path)
    responses = {
        "m-router": json.dumps({"intent": "rules_question", "confidence": 0.9}),
        "m-answer": "Hack and Slash lets you deal damage. [[moves/hack-and-slash]]",
    }
    handler, _bodies = _e2e_handler(responses)
    http_client = mock_http(handler)
    settings = Settings.from_env(_valid_env())
    costs: list[float] = []

    runtime = build_runtime(
        settings,
        index_dir=index_dir,
        normalized_dir=normalized_dir,
        http_client=http_client,
        on_llm_cost=costs.append,
    )
    asyncio.run(
        runtime.assistant.run(
            TurnInput(
                message="How does hack and slash work?",
                session_id="s1",
                trace_id=TRACE_A,
            )
        )
    )
    asyncio.run(runtime.aclose())

    assert costs == [0.00042, 0.00042]


def test_chat_cli_config_error_exit_2(capsys: pytest.CaptureFixture[str]) -> None:
    code = chat.main(["hi"], environ={})

    captured = capsys.readouterr()
    assert code == 2
    assert captured.err.startswith("chat: error: invalid configuration:")


def _fake_rules_runtime() -> Runtime:
    llm = FakeLLMClient(
        {
            "router": [router_json("rules_question")],
            "answer": ["Hack and Slash deals damage. [[moves/hack-and-slash]]"],
        }
    )
    chunks = [fake_chunk("moves/hack-and-slash", title="Hack and Slash")]
    assistant, _tracer = make_assistant(llm, retriever=FakeRetriever(chunks))

    async def close_callback() -> None:
        return None

    return Runtime(assistant, close_callback)


def test_chat_cli_prints_reply_and_ids(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake_build_runtime(settings: Settings) -> Runtime:
        return _fake_rules_runtime()

    monkeypatch.setattr(chat, "build_runtime", fake_build_runtime)

    code = chat.main(["How does hack and slash work?"], environ=_valid_env())

    captured = capsys.readouterr()
    assert code == 0
    assert "Hack and Slash deals damage." in captured.out
    assert "Citations:" in captured.out
    assert "- Hack and Slash: /rules/moves/hack-and-slash/" in captured.out
    last_line = captured.out.strip().splitlines()[-1]
    assert re.match(
        r"^kind=rules_answer intent=rules_question trace_id=[0-9a-f]{32} "
        r"session_id=[0-9a-f]{32}$",
        last_line,
    )


def test_chat_cli_error_reply_exit_1(monkeypatch: pytest.MonkeyPatch) -> None:
    llm = FakeLLMClient({"router": [PortError("down")]})
    assistant, _tracer = make_assistant(llm)

    async def close_callback() -> None:
        return None

    def fake_build_runtime(settings: Settings) -> Runtime:
        return Runtime(assistant, close_callback)

    monkeypatch.setattr(chat, "build_runtime", fake_build_runtime)

    code = chat.main(["hi"], environ=_valid_env())

    assert code == 1
