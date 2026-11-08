# 008-api-and-chat-widget-005-assistant-page-and-widget

**Spec:** STORIES/SPECS/008-api-and-chat-widget.md

**Stack:** frontend (`astro-feature-builder`)

**As a** Dungeon World player visiting the rules site
**I want** an `/assistant/` page, linked from the header, where I can ask a rules question or describe an action, optionally roll dice, and see progress then the answer
**So that** I can use the rules assistant from my browser and follow its citations to the rules pages

## Acceptance Criteria

```gherkin
Feature: Assistant page and chat widget

  Scenario: Assistant page renders the widget
    When the site is built
    Then dist/assistant/index.html contains id="chat-form", maxlength="500", role="log", role="status", <label for="chat-message"> and a <script type="module"
    And every HTML page contains href="/assistant/" in the header

  Scenario: Sending a message
    Given the widget is mounted with a fake send and a fixed session id
    When I type "  hi  " and submit
    Then send receives {message: "hi", roll: false, modifier: null, session_id: <the id>}
    And the log gets a user item and a reply item
    And two submits in the same mount send the same session id

  Scenario: Empty message is blocked
    When I submit "   "
    Then send is not called and "Type a message first." is visible

  Scenario: Modifier only with a roll
    Then the modifier field is disabled until "Roll the dice for me" is checked
    And with roll checked and modifier "-2", send receives modifier -2
    And with roll unchecked, the field is disabled and modifier null is sent
    And with roll checked and modifier "11", send is not called and MODIFIER_INVALID is shown

  Scenario: Progress while pending
    Given send returns a pending promise
    When I submit "hi"
    Then the submit button is disabled with text "Asking…" and the status reads "Reading your message…"
    And onStatus("retrieve") changes the status to "Writing an answer from the rules…"
    And onStatus("citation_validator") leaves the status unchanged
    And a second submit while pending is ignored
    And after the reply resolves, the status is empty, the button is enabled with text "Ask", and the log has 2 items

  Scenario: Failure restores the message
    When send returns a failure
    Then a chat-error item is appended and the textarea again contains the sent message

  Scenario: Keyboard and counter
    Then Enter submits and Shift+Enter does not
    And the character counter shows "<length>/500" as I type
```

## Technical Notes

Implements, from the spec:
- **Assumptions & Decisions → D6** (dev proxy for `/api`), **D15** (vanilla TypeScript island, dedicated `/assistant/` page, header link, new-tab links).
- **Configuration → `site/astro.config.ts`** (Vite `server.proxy` with `API_PROXY_TARGET`) and **Constants** `API_PROXY_TARGET`.
- **Widget Behaviour → Page and component** (`assistant.astro`, `ChatWidget.astro` markup in the stated order, `maxlength`/counter interpolated from `MAX_MESSAGE_CHARS`, CSS bullets) and **`widget.ts`** (all bullets).
- **User-Facing Copy → Widget**: the page intro text (in `assistant.astro`); the copy constants from story 004 are consumed here.
- **Validation Rules → Widget `message` and `modifier` rows.**
- **Impact on Existing Code**: `site/src/lib/urls.ts` (`ASSISTANT_URL`), `site/src/components/SiteHeader.astro` (third nav link with `aria-current`), `site/src/styles/global.css`, `site/astro.config.ts`, `site/tests/dist/site.test.ts` (additive). Rules pages stay script-free.
- **Documentation**: ADR "Chat widget: vanilla island on /assistant/, same-origin fetch" (required contents; number per D20); `docs/architecture.md` `## API and chat widget`: add the one-line descriptions of the `site/src/lib/chat/` modules; `README.md` `### Running the API and chat widget locally`: the `npm run dev` / `http://localhost:4321/assistant/` / proxy line.
- Open risks (d) and (e).

`innerHTML` must never be assigned in `site/src/lib/chat/`.

Files: `site/src/lib/chat/widget.ts`, `site/src/components/ChatWidget.astro`, `site/src/pages/assistant.astro`, `site/src/lib/urls.ts`, `site/src/components/SiteHeader.astro`, `site/src/styles/global.css`, `site/astro.config.ts`, `site/tests/unit/chat-widget.test.ts`, `site/tests/dist/site.test.ts`, `docs/decisions.md`, `docs/architecture.md`, `README.md`.

## Tests

From **Testing**:
- `site/tests/unit/chat-widget.test.ts` (happy-dom): all eleven cases.
- `site/tests/dist/site.test.ts` (additive): `assistant page renders the chat widget`, `header links the assistant on every page`.

Manual owner verification (Success Criteria → Owner verification, real keys; performed by the owner after this story, not by the feature-builder):
- "How does Hack and Slash work?" shows progress, then an answer with numbered citation links opening the matching `/rules/…/` pages.
- "I swing my sword at the goblin" with roll and modifier `1` shows a move card with name, `+STR`, three bands, the dice line and "(your roll)".
- A 501-character curl message gets 422 `message_too_long`; with `CHAT_RATE_PER_MINUTE=1` a second quick question shows the "too quickly" message; with `CHAT_DAILY_BUDGET_USD=0.0001` the second question shows the budget message.
- Langfuse shows the widget's turns under one session id, and no IP in any trace.

**Priority:** High
**Dependencies:** 008-api-and-chat-widget-003-rate-limit-and-spend-cap.md, 008-api-and-chat-widget-004-chat-client-library.md
