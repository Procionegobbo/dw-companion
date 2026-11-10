"""Tests for opt-in static site serving from `create_app` (spec 011 Testing).

Every case except `test_chat_still_streams_with_site_mounted` also asserts the
fake LLM was never called, so mounting the site never triggers an LLM request.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.tests.api_helpers import make_client, parse_sse, post_chat
from backend.tests.fakes.llm import FakeLLMClient
from backend.tests.graph_helpers import router_json


def make_site(tmp_path: Path) -> Path:
    """Writes spec 011's shared site fixture under `tmp_path` and returns `site/`."""
    site = tmp_path / "site"
    (site / "rules" / "x").mkdir(parents=True)
    (site / "index.html").write_text("<p>home</p>", encoding="utf-8")
    (site / "rules" / "x" / "index.html").write_text("<p>rule x</p>", encoding="utf-8")
    (site / "404.html").write_text("<p>missing</p>", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("top secret", encoding="utf-8")
    return site


def test_site_not_mounted_by_default() -> None:
    llm = FakeLLMClient({})
    client, _state = make_client(llm)

    with client:
        response = client.get("/")

    assert response.status_code == 404
    assert "home" not in response.text
    assert llm.requests == []


def test_home_served(tmp_path: Path) -> None:
    site = make_site(tmp_path)
    llm = FakeLLMClient({})
    client, _state = make_client(llm, env={"SITE_DIR": str(site)})

    with client:
        response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<p>home</p>" in response.text
    assert llm.requests == []


def test_directory_index_served(tmp_path: Path) -> None:
    site = make_site(tmp_path)
    llm = FakeLLMClient({})
    client, _state = make_client(llm, env={"SITE_DIR": str(site)})

    with client:
        response = client.get("/rules/x/")

    assert response.status_code == 200
    assert "<p>rule x</p>" in response.text
    assert llm.requests == []


def test_slashless_directory_redirects(tmp_path: Path) -> None:
    site = make_site(tmp_path)
    llm = FakeLLMClient({})
    client, _state = make_client(llm, env={"SITE_DIR": str(site)})

    with client:
        response = client.get("/rules/x", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"].endswith("/rules/x/")
    assert llm.requests == []


@pytest.mark.parametrize("path", ["/nope/", "/api/nope"])
def test_unknown_path_serves_404_page(tmp_path: Path, path: str) -> None:
    site = make_site(tmp_path)
    llm = FakeLLMClient({})
    client, _state = make_client(llm, env={"SITE_DIR": str(site)})

    with client:
        response = client.get(path)

    assert response.status_code == 404
    assert "<p>missing</p>" in response.text
    assert llm.requests == []


def test_api_routes_take_precedence(tmp_path: Path) -> None:
    site = make_site(tmp_path)
    llm = FakeLLMClient({})
    client, _state = make_client(llm, env={"SITE_DIR": str(site)})

    with client:
        health = client.get("/api/health")
        chat = post_chat(client, {})

    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert health.headers["cache-control"] == "no-store"
    assert chat.status_code == 422
    assert chat.json()["error"]["code"] == "invalid_request"
    assert llm.requests == []


def test_chat_still_streams_with_site_mounted(tmp_path: Path) -> None:
    site = make_site(tmp_path)
    llm = FakeLLMClient({"router": [router_json("out_of_scope")]})
    client, _state = make_client(llm, env={"SITE_DIR": str(site)})

    with client:
        response = post_chat(client, {"message": "what's the weather like"})

    events = parse_sse(response.text)
    assert [name for name, _ in events] == ["status", "status", "reply"]
    steps = [data["step"] for name, data in events if name == "status"]
    assert steps == ["router", "out_of_scope"]
    assert events[-1][1]["kind"] == "out_of_scope"
    assert len(llm.requests) == 1


@pytest.mark.parametrize("path", ["/../secret.txt", "/%2e%2e/secret.txt"])
def test_path_traversal_blocked(tmp_path: Path, path: str) -> None:
    site = make_site(tmp_path)
    llm = FakeLLMClient({})
    client, _state = make_client(llm, env={"SITE_DIR": str(site)})

    with client:
        response = client.get(path)

    assert response.status_code != 200
    assert "top secret" not in response.text
    assert llm.requests == []


def test_head_matches_get_without_body(tmp_path: Path) -> None:
    site = make_site(tmp_path)
    llm = FakeLLMClient({})
    client, _state = make_client(llm, env={"SITE_DIR": str(site)})

    with client:
        get_response = client.get("/")
        head_response = client.head("/")

    assert head_response.status_code == get_response.status_code
    assert head_response.headers["content-type"] == get_response.headers["content-type"]
    assert head_response.content == b""
    assert llm.requests == []


def test_post_to_static_path_not_allowed(tmp_path: Path) -> None:
    site = make_site(tmp_path)
    llm = FakeLLMClient({})
    client, _state = make_client(llm, env={"SITE_DIR": str(site)})

    with client:
        response = client.post("/")

    assert response.status_code == 405
    assert llm.requests == []
