# 012 - README polish and launch

**Status:** draft — to be expanded by spec-builder.
**Depends on:** all prior specs, especially 009/010 (eval numbers) and 011 (demo link).
**Reference:** `HANDOFF_dw-companion.md`, section 11 (full requirements), 10 (milestone 11).

## Scope

Write the final `README.md` in exactly the order section 11 specifies:

1. One-paragraph problem statement (players and GMs at the table).
2. Live demo link + a short GIF or screenshot.
3. What the assistant does (the two intents) and what it deliberately doesn't do with AI
   (dice, outcome text, citation validation are deterministic code — and why).
4. Architecture diagram and a short walkthrough of the graph.
5. Eval results table + the configuration comparison from spec 010 + how to reproduce
   (`make eval`).
6. Cost and latency per query, and the guardrails in place (section 7).
7. Trade-offs and decisions, linking to `docs/decisions.md`.
8. What I'd do next — the out-of-scope list from section 3 (class moves in the classifier,
   character sheets/sessions/multiplayer/login, an "AI GM", fine-tuning, translation; note
   the "nice to have" multilingual answering idea too).
9. Attribution and licensing (rules text CC BY 3.0, code MIT, unofficial).

## Out of scope

- Any code change — this spec is documentation only, drawing on what every prior spec
  already built and measured.
