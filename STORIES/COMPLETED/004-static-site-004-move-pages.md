# 004-static-site-004-move-pages

**Spec:** STORIES/SPECS/004-static-site.md

**As a** player looking up a move
**I want** a moves index and a structured card page per move, linked both ways with the move's rules section
**So that** I can quickly see a move's trigger, roll and outcomes, and the assistant can cite a move by a stable URL

## Acceptance Criteria

```gherkin
Feature: Moves index and move cards

  Scenario: Moves index
    When I open dist/moves/index.html
    Then its title is "Moves · Dungeon World Companion" and h1 is "Moves"
    And moves are grouped under h2 "Basic moves", "Special moves", "Class moves" in that order, only for categories present
    And each item links the move name to "/moves/<move_id>/" followed by " — " and its trigger

  Scenario: One card per move
    When I run "npm run build"
    Then for each of the 21 moves dist/moves/<move_id>/index.html exists
    And contains <article data-move-id="<move_id>"> with h1 = name and the category label

  Scenario: Card facts and breadcrumb
    When I open a move card
    Then the breadcrumb is "Contents" → "/", "Moves" → "/moves/", then the move name
    And dl.move-facts shows "Trigger" and "Roll" = rollLabel(stat)
    And h2 "Full text" is followed by the rendered body_markdown
    And "Read it in the rules: " links the section title to "/rules/<section_id>/"

  Scenario: Outcomes with an unstated miss
    When I open the hack-and-slash card
    Then it shows "+STR", "10+ (strong hit)", "7–9 (weak hit)" and "6- (miss)" → "Not stated by this move."

  Scenario: Outcomes with a stated miss
    When I open the last-breath card
    Then the miss band shows its rendered miss text ("On a miss, your fate is sealed.") and Roll is "2d6, no stat added"

  Scenario: Move without outcomes
    When I open the encumbrance card
    Then Roll is "Not rolled" and there is no Outcomes heading or outcome bands

  Scenario: Section page links to its card
    When I open dist/rules/moves/hack-and-slash/index.html
    Then it contains "Move card: " with a link "/moves/hack-and-slash/"
    And section pages without a move have no such link
```

## Technical Notes

Implements:
- Pages & Components → `moves/index.astro`, `moves/[id].astro` (items 1–5, `rollLabel` copy), and `rules/[...id].astro` item 4 (move-card link).
- Assumptions & Decisions → D3 (move pages), D11 (null outcomes displayed, never filled in).
- Uses `moveUrl`, `sectionUrl`, `MOVES_INDEX_URL`, `moveBySectionId`, `renderMarkdown`, `rollLabel`, `categoryLabel` from earlier stories.
- Files: `site/src/pages/moves/index.astro`, `site/src/pages/moves/[id].astro`, `site/src/pages/rules/[...id].astro`.

## Tests

No spec test cases are assigned to this slice; its pages are verified by the dist suite added in story 005 (`moves index links every move`, card and back-link tests) and by the acceptance criteria above against the built output.

**Priority:** High
**Dependencies:** 004-static-site-003-section-pages.md
