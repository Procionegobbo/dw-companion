# Source notes

Describes the actual structure of the Dungeon World XML in `vendor/dungeon-world/text/`, as
read by the ingestion pipeline (`ingestion/`). Facts below were re-verified by walking the
submodule's XML with `xml.etree.ElementTree` at the commit pinned below.

## Pinned source

- Upstream: <https://github.com/Sagelt/Dungeon-World>
- Pinned commit: `e67bd51c09d24518a7f989149b76094fbcc7fecc` (see ADR-003).
- Only `vendor/dungeon-world/text/` is read by the ingestion pipeline. The rest of the
  submodule (`layout/`, `character_sheets/`, `resources/`, the top-level `LICENSE` and
  `README.md`) is vendored for completeness but never parsed or served.

## File layout

`text/` holds 37 XML files that the ingestion pipeline turns into sections: 24 directly under
`text/`, 4 under `text/appendices/`, 9 under `text/monster_settings/`. Every file's root element
is `<Root xmlns:aid="http://ns.adobe.com/AdobeInDesign/4.0/">`. Beneath `Root`, content is
wrapped in either `Body` (29 files) or one or more `Story` elements (8 files, 10 `Story`
elements in total — `Moves.xml` alone has three: the first holds the basic moves, the second
the first several special moves, and the third has no `h1` of its own and simply continues
"Special Moves" with Carouse onward).

The XML carries no reliable chapter title or book order: `Moves.xml`'s first heading is an `h1`
reading "Basic Moves", not "Moves"; `Introduction.xml` and `appendices/Thanks.xml` have no
root-level `h1` at all (their root children start directly with a `Story`). Because of this, the
chapter list is a hand-written manifest (`ingestion/manifest.py`, `CHAPTERS`) pairing each file
with an explicit chapter id, display title and position — the build fails loudly if the
manifest and the files on disk ever disagree, rather than guessing a title or order from content
that can't reliably supply one.

## Tag and attribute inventory

Tag occurrences across all 37 files:

| Tag | Count | | Tag | Count |
|-----|------:|-|-----|------:|
| `p` | 2574 | | `TableBody` | 15 |
| `li` | 1231 | | `Cell` | 14 |
| `span` | 488 | | `Story` | 10 |
| `em` | 358 | | `Strong` | 10 |
| `h3` | 308 | | `TableHeader` | 3 |
| `ul` | 297 | | `ol` | 3 |
| `strong` | 294 | | `Center` | 1 |
| `h2` | 237 | | `StatTable` | 1 |
| `div` | 103 | | | |
| `h4` | 99 | | | |
| `h1` | 62 | | | |
| `Root` | 37 | | | |
| `Body` | 29 | | | |

No other tags appear, and no block element is ever nested inside `p`, `li` or a heading.

Attributes: `aid:pstyle` and `aid:cstyle` (InDesign paragraph/character style), a bare `id`
(on `div`, and on the `span id="Damage"` that carries each class's base damage die), and the
table-geometry attributes `aid:table`, `aid:crows`, `aid:ccols`, `aid:ccolwidth`, `aid:theader`,
`aid:trows`, `aid:tcols`. (The `xmlns:aid` namespace declaration itself is not surfaced by
`ElementTree` as an attribute, so it is not part of this inventory.)

The 29 paragraph styles (`aid:pstyle`) that occur are: `BackerList`, `BackerListNoIndent`,
`BasicMoveName`, `Example`, `ExampleDialogue`, `ExampleDialogueFirstLine`,
`ExampleDialogueLastLine`, `Exampleli`, `Instructions`, `InstructionsAfterHeader`, `Item`,
`ItemDescription`, `Lastli`, `MagicItem`, `MonsterDescription`, `MonsterName`,
`MonsterQualities`, `MonsterStats`, `MoveFirstLine`, `MoveLastLine`, `MoveName`, `MoveOneLine`,
`NoIndent`, `NumberedList`, `Option`, `ReNumberedList`, `Requirement`, `SpellName`, `li`. The 2
character styles (`aid:cstyle`) are `Tags` and `SpellName`.

How each renders is the rendering tables in `ingestion/markdown.py` (and summarised in the
spec's *Markdown rendering* section): most paragraph styles render as a plain paragraph;
`MonsterName`/`SpellName`/`MagicItem` render as `####` headings; `Example*` styles render as
blockquotes; `Requirement` renders italic; a `Tags`-styled span renders italic, a
`SpellName`-styled span (or no cstyle at all) renders unchanged.

## Inconsistencies found

- `strong` and `Strong` both mean bold — both exist in the source and both render the same way.
- `BasicMoveName` is reused for more than move headings: it appears on `h2` (the 21 moves in
  `Moves.xml`), on `h3` (class starting moves), and on at least one non-move heading
  (`The_World.xml`, "Elements of a Steading"); class moves mix `MoveName` and `BasicMoveName`.
- `h1` is used both as a chapter title and as a mid-file subsection heading — e.g.
  `Class_Moves_Discussion.xml`, `Equipment.xml` ("Magic Items"), and `Fronts.xml` all contain an
  `h1` that is not the chapter title.
- The single table in the source (`Character_Creation.xml`, the ability-score-to-modifier
  table) wraps its cells inconsistently: the children of `StatTable` are a mix of `Cell`,
  `TableHeader` and `TableBody` elements, and each of those in turn wraps a single
  `TableHeader` or `TableBody` text node — the wrapper tag name does not reliably say whether a
  cell is a header or a body cell; only the `aid:theader` attribute on the outer `Cell`/
  `TableHeader` does.
- `Druid.xml` has loose, non-whitespace text directly inside a `div` (as the tail of a `ul`
  element, reading "Choose one:") rather than inside a paragraph.
- Monsters, spells and magic items are rendered as paragraphs (`MonsterName`, `SpellName`,
  `MagicItem` styles), not as headings, even though they read like section titles.
- Tabs are used to separate columns inside paragraphs (spell level, item tags, dialogue
  speaker) rather than any table or list markup.

## Special characters

Across the 37 files: `’` (1876), `”`/`“` (≈320 each), `—` (318), `✴` (136 — a print-layout
marker placed immediately before an outcome band, e.g. `✴On a 10+`), `–` (108, mostly the en
dash in `7–9`; a few files instead spell it `7-9` with a plain hyphen), `…` (58), `×` (12),
assorted accented names (e.g. "Aaro Viertiö" in the `appendices/Thanks.xml` backer list), and
two U+200B zero-width spaces.

Typographic characters (`’ “ ” — – …`) are kept verbatim in rendered Markdown — they are part of
the authors' text, not Markdown or XML syntax. Only `✴` and U+200B are removed, since they are
layout artifacts with no meaning once the text is Markdown.

Markdown-sensitive raw text also appears: underscores used as blanks in bonds
(`_______________`), dice notation such as `b[2d6]` and `w[]`, and a literal `>` character in
`appendices/Thanks.xml`'s backer list ("...“Evil” Avi Zacherman, >B, a-bomb & g-girl..."). The
renderer backslash-escapes `\`, `*`, `_`, `` ` ``, `[` and `]` in plain text (never inside the
`*…*`/`**…**` markers it emits itself), and escapes a line-leading block marker (`#`, `>`, a
list marker followed by a space, or a number followed by `.`/`)` and a space) so none of this
raw text is misread as Markdown syntax.

## Moves

`Moves.xml` holds all 8 basic and 13 special moves, each an `h2[aid:pstyle="BasicMoveName"]`
under an `h1` of "Basic Moves" or "Special Moves" (the chapter's own first `h1`, "Basic Moves",
doesn't match the chapter title "Moves" and so becomes an ordinary child section rather than
the consumed chapter heading — see *File layout*). Every move's first paragraph opens with
"When you " (or similar) followed by a bold (`strong`/`Strong`) trigger phrase; the trigger is
the plain text from the paragraph's start through the end of that last bold run, trailing
whitespace and `,.;:` stripped.

Outcome bands are marked inline, immediately before the sentence they introduce: "On a 10+"
(strong hit), "On a 7–9" (or "7-9" with a plain hyphen; weak hit), "On a hit" (prefixed to both
hit bands), and "On a miss" or "On a 6-" (miss). A move with no such marker anywhere in its text
has no roll at all (`outcomes: null`, `stat: null` — Encumbrance, Make Camp, Level Up, End of
Session, Recover, Bolster). A `ul`/`ol` immediately following a paragraph attaches to that
paragraph's last band (both hit bands, for "On a hit").

`Playing_the_Game.xml` states the rule behind the nullable `miss` field directly: "Each move
will tell you what happens on a 10+ and a 7–9. Most moves won't say what happens on a 6-, that's
up to the GM — but you also always mark XP." Of the 15 rolled moves, only Last Breath, Take
Watch, Carouse and Recruit state a miss outcome in the text; the other 11 leave the 6- case to
the table, and `moves.json` records that honestly as `miss: null` rather than inventing text —
see ADR-008.

Each move's `stat` comes from the first `roll+<Stat>` (or `rolls+<Stat>`) phrase in its block's
paragraphs; a rolled move with no such phrase gets the automatic value `"NONE"` (Carouse,
Recruit — overridden where wrong, see below).

## Move overrides

Six moves need a small hand-written correction on top of the automatic extraction
(`MOVE_OVERRIDES` in `ingestion/overrides.py`), because the general rules above get the wrong
answer for them specifically:

- **Defy Danger** — `stat` → `"VARIES"`. Its paragraph says "roll" with no `+Stat` phrase at
  all; the six stats are instead offered as a bulleted list ("…by powering through, +Str" etc.)
  for the player to choose from by approach, which the automatic `roll+Stat` regex can't see.
- **Defend**, **Spout Lore**, **Discern Realities** — their `weak_hit` is shortened. The
  automatic segmentation attaches *everything* after the last "On a 7–9…" to the weak band,
  including a sentence or option list that in fact applies to both hit bands (Defend's
  spend-hold rules, Spout Lore's "The GM might ask you…", Discern Realities' "Take +1 forward…"
  and its question list). The override keeps only the band-specific sentence; the shared text
  stays visible in `body_markdown`, just not duplicated into (or claimed by) one band alone.
- **Carouse**, **Recruit** — their `miss` is shortened the same way: Carouse's option list
  applies on a 10+, 7-9 *or* a miss, not only a miss; Recruit's closing "If you turn away
  applicants you take -1 forward to Recruit" applies regardless of how the roll came out.

Every override string is required to be a verbatim substring of that move's own
`body_markdown` (so it can never introduce text that isn't in the source) and to differ from
what automatic extraction would have produced (so a stale override that no longer changes
anything fails the build loudly instead of silently doing nothing).

## Unknown-markup gate

The build tracks every tag, attribute name, `aid:pstyle` value and `aid:cstyle` value it
encounters while rendering, and compares the total against a threshold (`--max-unknown`,
default `0`). At the pinned commit the real count is `0` — every tag and style above was
inventoried from the actual source, not assumed. An unknown occurrence does not lose any text:
it still renders (so the pipeline is "tolerant"), but it is counted and logged as a `WARNING` on
the `ingestion` logger and fails the build once the total exceeds the threshold (so the pipeline
is "loud") — because an unknown tag or style only appears if the upstream source has changed in
a way nobody has reviewed yet.

If upstream changes and introduces genuinely new markup, update the known-tag, known-attribute,
known-pstyle or known-cstyle inventory in `ingestion/markdown.py` (after reading what the new
markup actually means, by the same process as this file), then re-run
`uv run python -m ingestion` and review the diff in `data/normalized/`.
