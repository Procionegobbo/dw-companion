# 008-api-and-chat-widget-003-rate-limit-and-spend-cap

**Spec:** STORIES/SPECS/008-api-and-chat-widget.md

**Stack:** backend (`python-feature-builder`)

**As a** project owner running a public demo
**I want** per-IP rate limits and a global daily LLM spend cap enforced before any LLM call
**So that** abuse or a traffic spike cannot run up the LLM bill, and visitors' IPs are never stored or logged raw

## Acceptance Criteria

```gherkin
Feature: Rate limiting and spend cap (guards 6-7)

  Scenario: Per-minute rate limit
    Given CHAT_RATE_PER_MINUTE=2
    When the same client sends three valid requests
    Then the third gets 429 rate_limited with RATE_LIMIT_MINUTE_TEXT and Retry-After: 60
    And the router requests total exactly 2
    And after the clock advances 61 seconds the next request gets 200

  Scenario: Daily rate limit
    Given CHAT_RATE_PER_DAY=2 and CHAT_RATE_PER_MINUTE=100
    When the same client sends three valid requests
    Then the third gets 429 with RATE_LIMIT_DAY_TEXT and Retry-After equal to the seconds until the next UTC midnight

  Scenario: Rate limit keyed by the trusted forwarded IP
    Given CHAT_TRUSTED_PROXY_HOPS=1 and CHAT_RATE_PER_MINUTE=2
    When two requests come from "X-Forwarded-For: 9.9.9.9, 1.1.1.1" and one from "9.9.9.9, 2.2.2.2"
    Then all three get 200
    And a third request ending in "1.1.1.1" gets 429, even when its spoofed leftmost entry changes

  Scenario: Forwarded header ignored by default
    Given CHAT_TRUSTED_PROXY_HOPS is unset (0)
    When requests carry two different X-Forwarded-For values
    Then they share the socket peer's bucket

  Scenario: Budget exhausted
    Given CHAT_DAILY_BUDGET_USD=0.01 and the fake LLM reports cost_usd None (fallback 0.01)
    When the first out_of_scope turn completes with 200
    Then the second request gets 503 budget_exhausted with BUDGET_EXHAUSTED_TEXT and a Retry-After header
    And the router requests total 1

  Scenario: Budget counts reported cost
    Given CostLLMClient(cost=0.004), CHAT_DAILY_BUDGET_USD=0.01 and rules turns (2 calls each)
    Then the second turn is allowed (0.008 < 0.01) and the third is rejected with 503 (0.016 >= 0.01)

  Scenario: Budget resets at UTC midnight
    Given the budget is exhausted
    When the clock advances past the next UTC midnight
    Then the next request gets 200

  Scenario: Rejections do not consume the rate limit
    Given CHAT_RATE_PER_MINUTE=1
    When three invalid requests are followed by one valid request
    Then the valid request gets 200
    And given CHAT_DAILY_BUDGET_USD=0.01 and CHAT_RATE_PER_MINUTE=2, after one 200 turn and three 503s and a clock advance past the next UTC midnight, two requests get 200 and the third gets 429

  Scenario: Health is unaffected by the budget
    Given the budget is exhausted
    When I GET /api/health
    Then the response is 200 {"status": "ok"} and no further router request is made

  Scenario: No IP in traces or logs
    Given CHAT_TRUSTED_PROXY_HOPS=1, CHAT_RATE_PER_MINUTE=1 and X-Forwarded-For: 203.0.113.7
    When one rules turn runs and a second request is rejected with 429
    Then "203.0.113.7" appears in no FakeTracer node, generation or event (ids and attribute values)
    And in no captured log record at any level

  Scenario: Limiter and ledger units
    Then RateLimiter, SpendLedger, seconds_until_utc_midnight, client_ip and ClientKeyer behave as specified under API Behaviour -> Limits
    And SpendLedger.record rejects negative and NaN costs with ValueError
```

## Technical Notes

Implements, from the spec:
- **Assumptions & Decisions → D3** (429 and 503 with `Retry-After`), **D8** guards 6–7 (spend cap, then rate limit which records the request), **D9, D10, D11, D12** (ledger side), **D17**.
- **Data Model → Backend types → `backend/api/limits.py`** (`Clock`, `RateDecision`, `RateLimiter`, `SpendLedger`, `seconds_until_utc_midnight`, `client_ip`, `ClientKeyer`) and the `keyer` parameter of `create_app`.
- **API Behaviour → `POST /api/chat`** checks 6 and 7, **Lifespan and wiring** steps 2 and 3 (ledger, limiter, keyer; `runtime_factory(ledger.record)` replacing story 002's no-op sink), **Limits (`limits.py`)**.
- **Validation Rules**: Business `spend` and `rate` rows, `SpendLedger.record` row.
- **User-Facing Copy → Backend**: `BUDGET_EXHAUSTED_TEXT`, `RATE_LIMIT_MINUTE_TEXT`, `RATE_LIMIT_DAY_TEXT` (defined in story 002, used here).
- **Authorization & Security → Cost, Privacy.**
- **Testing → Backend** preamble: `make_client` now passes `keyer=ClientKeyer(b"test-salt")`.
- **Documentation**: ADR "Chat API: SSE protocol, guardrails and in-memory limits" (all required contents; number per D20), `docs/architecture.md` `## API and chat widget` section with the diagram and the one-line descriptions of the `backend/api/` modules, `README.md` `### Running the API and chat widget locally` with the API-side lines (`.env` configuration, uvicorn command with `--no-access-log` and single worker, health-check curl).

Files: `backend/api/limits.py`, `backend/api/app.py`, `backend/tests/api_helpers.py`, `backend/tests/test_api_limits.py`, `backend/tests/test_api_guardrails.py`, `backend/tests/test_api_validation.py` (one added case), `docs/decisions.md`, `docs/architecture.md`, `README.md`.

## Tests

From **Testing**:
- `test_api_limits.py`: all tests (`test_minute_limit_allows_then_rejects`, `test_minute_window_slides`, `test_day_limit_rejects_until_midnight`, `test_day_resets_at_utc_midnight`, `test_rejected_requests_not_counted`, `test_keys_are_independent`, `test_least_recent_client_evicted`, `test_seconds_until_utc_midnight`, `test_spend_ledger_accumulates_and_exhausts`, `test_spend_ledger_resets_next_utc_day`, `test_spend_ledger_rejects_invalid_cost`, `test_client_ip_cases`, `test_client_keyer_hides_ip`).
- `test_api_guardrails.py`: all eleven tests, including `test_no_ip_in_traces_or_logs`.
- `test_api_validation.py`: `test_invalid_requests_do_not_consume_rate_limit`.

**Priority:** Critical
**Dependencies:** 008-api-and-chat-widget-002-chat-api-core.md
