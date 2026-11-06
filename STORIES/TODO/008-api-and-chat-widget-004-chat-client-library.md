# 008-api-and-chat-widget-004-chat-client-library

**Spec:** STORIES/SPECS/008-api-and-chat-widget.md

**Stack:** frontend (`astro-feature-builder`)

**As a** visitor of the rules site
**I want** the browser to talk to the chat API safely and render its replies as readable text with citation links and a move card
**So that** answers are shown with verifiable sources and no server-provided HTML or URL can inject content

## Acceptance Criteria

```gherkin
Feature: Chat client library (SSE parser, protocol, client, rendering)

  Scenario: SSE parsing
    Given an event-stream body
    Then named events, multi-line data, CRLF and CR line endings are parsed per the WHATWG rules
    And the same stream fed byte by byte yields the same messages
    And comments and unknown fields are ignored, one leading space is stripped, and the event name defaults to "message"
    And an unterminated final event is dropped
    And readSse decodes a multi-byte character split across two chunks

  Scenario: Protocol validation
    Given the four replies in backend/tests/fixtures/chat_reply_examples.json
    Then replySchema accepts each of them
    And it rejects a citation url not equal to sectionUrl(section_id), such as "javascript:alert(1)"
    And it rejects a move url not equal to moveUrl(move_id), an unknown kind, and dice outside 1-6
    And unknown keys such as "intent" are stripped from the output
    And httpErrorSchema parses {"error": {"code": "rate_limited", "message": "Slow down."}} but not a body missing message or {"detail": "Not Found"}

  Scenario: Sending a chat request
    When sendChat is called
    Then it POSTs to /api/chat with Content-Type: application/json, Accept: text/event-stream and the exact JSON body
    And status events call onStatus with each step, and a reply event returns the reply
    And unknown events (such as "delta") are ignored

  Scenario Outline: Failure mapping
    When <situation>
    Then sendChat returns failure <code> with <message>

    Examples:
      | situation                                    | code               | message           |
      | an error event arrives                       | the event's code   | the event's text  |
      | a 429 / 503 response with a JSON error body  | rate_limited / budget_exhausted | the server message |
      | a 502 response with an HTML body             | http_502           | UNAVAILABLE       |
      | fetch rejects with TypeError                 | network            | NETWORK_FAILURE   |
      | the stream ends without reply or error       | interrupted        | INTERRUPTED       |
      | a reply event with malformed JSON            | malformed          | INTERRUPTED       |
      | a 200 application/json response              | malformed          | INTERRUPTED       |

  Scenario: Rendering a rules answer
    Given the fixture rules_answer
    Then segmentText yields text, citation 1, text, citation 2, text, and markers not in citations are dropped
    And renderReply gives two paragraphs with links [1] and [2] to /rules/moves/hack-and-slash/ and /rules/moves/defy-danger/
    And each link has target="_blank", rel="noopener noreferrer" and an aria-label starting "Source 1: Hack and Slash"
    And a sources list titled "Sources" is rendered
    And for rules_not_found the list is titled "Closest sections in the rules"

  Scenario: Rendering a move card
    Given the fixture move_rolled_with_modifier
    Then the card heading links to /moves/hack-and-slash/, Roll is "+STR", Dice is "4 + 5 + 1 = 10"
    And the is-result dt reads "10+ (strong hit) (your roll)" and the miss dd reads "Not stated by this move."
    And for move_rolled_without_modifier, Roll is "+stat chosen by how you act", Dice is "3 + 5 = 8, before your modifier", and no band is marked is-result
    And a move with outcomes null and roll null renders no .outcomes block and Roll "Not rolled"
    And diceText formats a negative modifier as "3 + 3 - 1 = 5"

  Scenario: Untrusted text is never parsed as HTML
    Given a reply text "<img src=x onerror=alert(1)>" and a citation title containing "<b>"
    When it is rendered
    Then no img or b element is created and the text is shown literally

  Scenario: Error replies are marked
    Given a reply of kind "error"
    Then the item has class chat-error and the first paragraph starts with "Error: "

  Scenario: Band labels
    Then bandLabel maps strong_hit, weak_hit and miss to "10+ (strong hit)", "7–9 (weak hit)" and "6- (miss)"
```

## Technical Notes

Implements, from the spec:
- **Assumptions & Decisions → D2** (ignore unknown events), **D6** (fetch + own SSE parser, not `EventSource`), **D16** (render safety: `textContent` only, hrefs from `urls.ts`, url equality in schema, marker-to-`[n]` replacement), **D18** (frontend half of the contract fixture), **D19** (`happy-dom`, per-file environment).
- **Configuration → `site/package.json`** (`npm install --save-dev happy-dom`, with the D19 PR line) and **Constants** `CHAT_ENDPOINT`, `MAX_MESSAGE_CHARS` (`site/src/lib/chat/client.ts`).
- **Data Model → Frontend types** (`site/src/lib/chat/protocol.ts`).
- **Widget Behaviour → `sse.ts`, `client.ts` (including the outcome-mapping table), `render.ts`** (all bullets, including the move card and "No HTML from data").
- **User-Facing Copy → Widget**: every constant in `site/src/lib/chat/copy.ts` (the page intro text belongs to story 005).
- **Validation Rules → Widget `server payload` row.**
- **Impact on Existing Code**: `site/src/lib/format.ts` (additive `bandLabel`), `site/package.json` / `site/package-lock.json`.
- **Testing → Frontend** preamble (fixture path read via `fs.readFileSync(new URL(...))`, fake `Response` streams).

`innerHTML` must never be assigned in `site/src/lib/chat/`.

Files: `site/package.json`, `site/package-lock.json`, `site/src/lib/chat/sse.ts`, `site/src/lib/chat/protocol.ts`, `site/src/lib/chat/client.ts`, `site/src/lib/chat/copy.ts`, `site/src/lib/chat/render.ts`, `site/src/lib/format.ts`, and the tests below.

## Tests

From **Testing**:
- `site/tests/unit/chat-sse.test.ts`: all nine cases.
- `site/tests/unit/chat-protocol.test.ts`: all seven cases.
- `site/tests/unit/chat-client.test.ts`: all eleven cases.
- `site/tests/unit/chat-render.test.ts` (happy-dom): all eleven cases.
- `site/tests/unit/format.test.ts` (additive): `bandLabel maps every band`.

**Priority:** High
**Dependencies:** 008-api-and-chat-widget-002-chat-api-core.md (contract fixture); requires spec 004 to be implemented
