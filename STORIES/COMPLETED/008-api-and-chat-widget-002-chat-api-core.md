# 008-api-and-chat-widget-002-chat-api-core

**Spec:** STORIES/SPECS/008-api-and-chat-widget.md

**Stack:** backend (`python-feature-builder`)

**As a** visitor using the rules assistant from a browser (and the widget that serves them)
**I want** a `POST /api/chat` endpoint that validates my request and streams progress then a structured reply as Server-Sent Events, plus a `GET /api/health` check
**So that** one assistant turn can be run over HTTP with invalid requests rejected before any LLM call

## Acceptance Criteria

```gherkin
Feature: Chat API core (health, request guards 1-5, SSE streaming)

  Scenario: Health check
    When I GET /api/health
    Then the response is 200 {"status": "ok"} with Cache-Control: no-store

  Scenario: Rules question streams status events then a reply
    Given a runtime over fakes with router "rules_question", one chunk, and an answer citing it
    When I POST a valid JSON body to /api/chat
    Then the response is 200 with Content-Type starting with text/event-stream and Cache-Control: no-store
    And the events are status router, retrieve, answer_with_citations, citation_validator, then reply
    And the reply has kind "rules_answer", a citation url "/rules/moves/hack-and-slash/", and a trace_id matching ^[0-9a-f]{32}$

  Scenario: Move turn with roll and modifier
    Given a classifier result hack-and-slash 0.9 and ScriptedRandom([4, 5])
    When I POST {"message": ..., "roll": true, "modifier": 1}
    Then reply.move.roll equals {"dice": [4, 5], "modifier": 1, "total": 10}
    And reply.move.outcome.band equals "strong_hit"

  Scenario: Out-of-scope turn
    When I POST an out-of-scope message
    Then the events are status router, status out_of_scope, then reply with kind "out_of_scope"

  Scenario: Graph error is a normal reply event
    Given the router LLM call raises PortError
    When I POST a valid message
    Then I receive a reply event with kind "error" and spec 006 ERROR_TEXT
    And no error event is sent

  Scenario: Unexpected exception after streaming started
    Given a runtime whose assistant.stream raises RuntimeError("boom") after one NodeCompleted
    When I POST a valid message
    Then the events are status, then error {"code": "internal_error", "message": ERROR_TEXT}
    And the ERROR log contains "RuntimeError" and the trace id
    And the log does not contain the user message

  Scenario: Turn timeout
    Given create_app with turn_timeout_s=0.05 and a SlowLLMClient(1.0)
    When I POST a valid message
    Then the last event is error with code "timeout" and TIMEOUT_TEXT

  Scenario: Session and trace ids
    Given a body session_id of "ab" repeated 16 times
    When I POST it
    Then every FakeTracer record has that session_id
    And when session_id is absent, the tracer records a server-generated 32-hex session id
    And two requests get different trace_ids, each equal to the tracer's trace_id for its turn

  Scenario: Message is stripped before the graph
    When I POST {"message": "  hi  "}
    Then the router request user content contains "<user_message>\nhi\n</user_message>"

  Scenario: max_tokens is set on every LLM call
    When rules and move+roll turns run through the API
    Then FakeLLMClient.requests max_tokens are exactly [100, 700] and [100, 400, 300]

  Scenario Outline: Rejected requests make no LLM call
    When I POST <request> to /api/chat
    Then the response is <status> with body {"error": {"code": "<code>", "message": <text>}} and Cache-Control: no-store
    And FakeLLMClient.requests is empty

    Examples:
      | request                                             | status | code                   | text                        |
      | Content-Type text/plain                             | 415    | unsupported_media_type | UNSUPPORTED_MEDIA_TYPE_TEXT |
      | a 20,000-byte JSON body                             | 413    | request_too_large      | REQUEST_TOO_LARGE_TEXT      |
      | not JSON / [] / {} / wrong types / extra key / out-of-range or bool or float modifier / bad session_id / "   " message | 422 | invalid_request | INVALID_REQUEST_TEXT |
      | a message of 501 "a"s                               | 422    | message_too_long       | MESSAGE_TOO_LONG_TEXT       |

  Scenario: Length limit boundaries
    When I POST 500 "a"s surrounded by spaces
    Then the response is 200
    And when I POST 500 "é" characters (1,000 UTF-8 bytes) the response is 200

  Scenario: API settings from the environment
    Given no CHAT_* variables
    Then ApiSettings has rate_per_minute 5, rate_per_day 50, daily_budget_usd 1.0, trusted_proxy_hops 0
    And whitespace is stripped (" 7 " parses to 7) and "2.50" parses to 2.5
    And several invalid values produce one ConfigError naming every invalid variable
    And NaN and infinite budgets are rejected
    And create_app raises ConfigError when CHAT_RATE_PER_MINUTE is "0"

  Scenario: Runtime lifecycle
    Given create_app(environ={}) with no runtime factory
    Then create_app succeeds, but entering TestClient raises ConfigError naming OPENROUTER_API_KEY
    And with an injected runtime factory, the runtime is closed when the TestClient context exits

  Scenario: Reply payload matches the shared contract fixture
    Given the four entries in backend/tests/fixtures/chat_reply_examples.json
    When reply_payload is called on the matching TurnResult
    Then the result equals the fixture entry, including key order
    And every fixture url follows the spec 004 URL contract

  Scenario: API layering
    Then backend/api/*.py imports only the allow-listed modules
    And no backend package outside backend/api imports fastapi, starlette or backend.api
```

## Technical Notes

Implements, from the spec:
- **Assumptions & Decisions → D1, D2, D3** (except 429/503, which are story 003), **D5, D7, D8** guards 1–5 (content type → body size → schema → message rules), **D13, D14, D17, D18**.
- **Configuration → Environment variables** (all four, parsed by `ApiSettings`), **`.env.example`** block, **Constants** (`MAX_MESSAGE_CHARS`, `MAX_BODY_BYTES`, `TURN_TIMEOUT_S`, `MAX_TRACKED_CLIENTS` in `backend/api/settings.py`), **`pyproject.toml`** (`uv add fastapi uvicorn`, with the D5 PR lines).
- **Data Model → Backend types**: `backend/api/settings.py`, `backend/api/schemas.py`, `backend/api/sse.py`, `backend/api/app.py`; **Wire contract** (error body, SSE events, reply payload, contract fixture with exact content).
- **API Behaviour → `GET /api/health`**, **`POST /api/chat`** checks 1–5 plus the streaming `gen()` and `TurnInput` construction, **Lifespan and wiring (`create_app`)**.
- **User-Facing Copy → Backend**: all rows in `backend/api/messages.py` (the rate-limit and budget texts are defined here and used in story 003).
- **Validation Rules**: HTTP rows, `ChatRequest` rows, `ApiSettings`, `sse_event`.
- **Authorization & Security → Errors** (no exception text in responses).
- **Testing → Backend** preamble and **`backend/tests/api_helpers.py`** (all helpers listed there).

Slice boundary (from **Suggested Story Breakdown** item 2): no rate limiter or spend ledger yet. `create_app` has no `keyer` parameter in this story, and the runtime factory receives a no-op cost sink; story 003 wires `ledger.record`. Helpers and tests in this story never reference `ClientKeyer` or `client_ip`.

Files: `pyproject.toml`, `uv.lock`, `.env.example`, `backend/api/settings.py`, `backend/api/schemas.py`, `backend/api/sse.py`, `backend/api/messages.py`, `backend/api/app.py`, `backend/tests/fixtures/chat_reply_examples.json`, `backend/tests/api_helpers.py`, and the test files below. `backend/api/__init__.py` stays empty.

## Tests

From **Testing**:
- `test_api_settings.py`: all five tests.
- `test_api_sse.py`: all four tests.
- `test_api_contract.py`: all three tests.
- `test_api_chat.py`: all fifteen tests.
- `test_api_validation.py`: `test_wrong_content_type_415`, `test_body_too_large_413`, `test_invalid_request_422` (all parametrized cases), `test_message_too_long_422`, `test_message_at_limit_accepted`, `test_non_ascii_length_counts_code_points`. (`test_invalid_requests_do_not_consume_rate_limit` belongs to story 003.)
- `test_api_layering.py`: `test_api_imports_allow_list`, `test_web_framework_confined_to_api`.

**Priority:** Critical
**Dependencies:** 008-api-and-chat-widget-001-graph-streaming-and-cost-metering.md
