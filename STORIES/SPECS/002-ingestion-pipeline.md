# 002 - Ingestion pipeline

**Status:** spec — ready for story-creator.
**Depends on:** 001 (toolchain, `ingestion/` package, `vendor/dungeon-world/` submodule at `e67bd51c09d24518a7f989149b76094fbcc7fecc`, `docs/` stubs, `data/normalized/`).
**Reference:** `HANDOFF_dw-companion.md` sections 3 (MVP item 1), 4.3, 5, 10 (milestone 2), 12.

## Feature Name & Description

**Ingestion pipeline.** An offline Python command (`uv run python -m ingestion`) that parses the Dungeon World InDesign-flavoured XML in `vendor/dungeon-world/text/` into three committed, deterministic JSON files under `data/normalized/` (`sections.json`, `moves.json`, `classes.json`). Every later spec (site, domain types, retrieval, move classifier) consumes these files, so their IDs and shapes are a contract.

**Current state.** No ingestion code exists. Spec 001 creates an empty `ingestion/__init__.py`, a stub `docs/source-notes.md`, `docs/decisions.md` (ADR-001…006) and `data/normalized/.gitkeep`. The source XML was inspected for this spec at the pinned commit (see D1); its real structure is recorded in *Source Facts* and drives every parsing rule below.

**In scope.** `docs/source-notes.md` (written first); a tolerant, loud parser with an unknown-markup counter and a build-failing threshold; sections for every chapter of the source; structured extraction of all 8 basic and 13 special moves (trigger, stat, outcome bands); a minimal `classes.json` for the 8 core classes; a small hand-maintained move-override module; tests on named moves; snapshot tests (the committed JSON is the snapshot); two ADRs.

**Out of scope.** Class moves as structured `moves.json` rows (their text is in the class sections, searchable later via RAG — handoff 3); site generation (spec 004); domain types in `backend/domain/` (spec 005); chunking, embeddings and the index build (spec 007); any LLM call.

## Assumptions & Decisions

| # | Decision | Reasoning / precedent |
|---|----------|-----------------------|
| D1 | **Parser rules were designed from a direct read of the pinned commit's XML** (read-only clone of `https://github.com/Sagelt/Dungeon-World` at `e67bd51c09d24518a7f989149b76094fbcc7fecc`, 2026-11-04), because spec 001 is not implemented yet and the submodule is not wired in. The findings are in *Source Facts*; story 1 re-verifies them against the submodule while writing `docs/source-notes.md`. | Draft: "inspect the actual XML … not assumed". The pin is fixed by spec 001 D7, so the content cannot drift. |
| D2 | **Python stdlib only** (`xml.etree.ElementTree`, `dataclasses`, `json`, `argparse`, `logging`, `re`, `unicodedata`). No new dependency; no `defusedxml`, no `lxml`, no `pydantic`, no snapshot library. | Handoff 12 ("boring libraries, justify every dependency"); spec 001 D4. All 37 files are well-formed UTF-8 that ElementTree parses; input is pinned, trusted upstream text (expat's built-in entity-expansion limits suffice). Pydantic-based domain types belong to spec 005. |
| D3 | **One chapter per XML file, defined by a hand-written manifest** (`ingestion/manifest.py`) giving file, chapter id, display title and book order (table in *Chapter Manifest*). The build fails if `text/` contains an `.xml` file not in the manifest or the manifest lists a missing file. | The XML has no reliable chapter title (e.g. `Moves.xml` starts with `<h1>Basic Moves</h1>`; `Introduction.xml` and `Thanks.xml` have no root-level `h1`) and no book order. An explicit manifest is deterministic and loud when upstream changes. |
| D4 | **Section granularity: chapter → `h1` → `h2`.** `h3`/`h4` and heading-like paragraph styles stay inside their section's `text_markdown` as `###`/`####` lines. A section's `text_markdown` holds only its own content up to the next `h1`/`h2`, never its children's. | Gives citation-sized sections (e.g. one per basic move, one per GM-principles group) without hundreds of one-line sections for monsters, spells and list items. No duplicated text between parent and child. |
| D5 | **ID scheme.** Chapter section id = chapter id (e.g. `fighter`). Other sections: `{chapter_id}/{slug}` where `slug = slugify(title)`; on a collision within a chapter, `-2`, `-3`… in document order (none occur at the pin). `slug` field = last path segment (chapter section: the chapter id). Move id = `slugify(name)` (e.g. `hack-and-slash`). Class id = chapter id. IDs derive from the pinned source once; any change is visible in the snapshot diff. | Handoff 4.5: slugs derive from IDs, not display titles; IDs must be stable for citations. Slash-separated ids map naturally to site paths for spec 004. |
| D6 | **`moves.json` contains only the 21 basic and special moves from `Moves.xml`.** `category` is `"basic"` or `"special"` (from the enclosing `h1`); the schema keeps `"class"` as a valid enum value and the `class` key (always `null`) so the handoff shape is unchanged. Moves repeated in `Moves_Discussion.xml` are discussion text, not moves. | Draft out-of-scope; handoff 3 keeps class moves out of the classifier. Class-move text stays in class sections. |
| D7 | **Outcome bands follow the source: `miss` is `null` when the move does not state a miss.** The source says so explicitly (`Playing_the_Game.xml`: "Each move will tell you what happens on a 10+ and a 7–9. Most moves won't say what happens on a 6-, that's up to the GM but you also always mark XP."). Only Last Breath, Take Watch, Carouse and Recruit state a miss. **This is a flagged discrepancy with handoff milestone 2 ("three outcome bands")**; per handoff 12 the source wins. Acceptance is restated in *Success Criteria* as: every rolled move has `trigger`, `stat`, `strong_hit`, `weak_hit`, and an `outcomes` object with all three keys. Recorded as ADR-008. | Inventing miss text would put words in the authors' mouth and break "outcomes quoted from structured data, not regenerated". Spec 006's explanation can cite the general rule section for `null` misses. |
| D8 | **Non-rolled special moves** (Encumbrance, Make Camp, Level Up, End of Session, Recover, Bolster) have `outcomes: null` and `stat: null`. | They contain no roll and no outcome bands in the source. |
| D9 | **`stat` vocabulary:** `"STR" \| "DEX" \| "CON" \| "INT" \| "WIS" \| "CHA" \| "BOND" \| "VARIES" \| "NONE"` or `null` (not rolled). `BOND` = Aid or Interfere (`roll+Bond`); `VARIES` = Defy Danger (stat chosen by approach); `NONE` = rolled with no stat (Last Breath, Carouse, Recruit). | The handoff names `stat` without a type; the source needs these cases. Downstream note: the classifier's output `stat` (handoff 4.4) stays `STR…CHA \| null` — for `VARIES` the classifier picks the stat, for `BOND`/`NONE` it returns `null`. Spec 005/006 must accept this vocabulary. |
| D10 | **Outcome strings are verbatim source sentences in Markdown, including their "On a …" lead-in** (e.g. `"On a 10+ you deal your damage…"`). An "On a hit" segment is prefixed to both `strong_hit` and `weak_hit`. Text that applies to more than one band (shared rules, shared option lists) stays only in `body_markdown`. | Verbatim text needs no rewriting or capitalisation fixes and reads correctly when quoted on the move card. |
| D11 | **Overrides are a typed Python module** (`ingestion/overrides.py`), not a data file. Each entry names a move id, a reason, and replacement `stat` and/or band strings. Every replacement band string **must be a verbatim substring of that move's `body_markdown`** and **must differ from the automatic result**; otherwise the build fails. Six entries at the pin (see *Move Overrides*). | Handoff 5 allows a small override file. The substring rule keeps "never hand-copy text" true; the must-differ rule stops stale overrides. A Python module gets pyright checking for free. |
| D12 | **Unknown-markup threshold = 0** (CLI flag `--max-unknown N` to raise it locally). Unknown = any tag, attribute, `aid:pstyle` value or `aid:cstyle` value not in the known inventory. Each occurrence is logged and counted; its text is still rendered. | Every tag and style at the pin was inventoried, so the real count is 0; any unknown means the source changed and a human must look. "Tolerant" = keep the text; "loud" = fail the build. |
| D13 | **The committed `data/normalized/*.json` files are the snapshots.** A test rebuilds in memory and compares byte-for-byte with the committed files; regenerating is `uv run python -m ingestion`. | Draft: "snapshot tests … so changes are visible in diffs". Committing the output also gives spec 004 its input without running Python. No snapshot library needed (D2). |
| D14 | **Output format:** each file is a JSON array, UTF-8, `ensure_ascii=False`, `indent=2`, keys in the field order of *Data Model*, LF line endings, trailing newline. Typographic characters (’ “ ” — – …) are kept verbatim; only `✴` (U+2734) and zero-width spaces (U+200B) are removed. | Deterministic diffs; faithful text. `✴` is a print-layout marker before outcome bands. |
| D15 | **`classes.json` is minimal:** `id`, `name`, `section_id`, `order`, `max_hp_base`, `base_damage`, `load_base`, extracted by fixed patterns from each class chapter; the build fails if any is missing. | "Minimal, enough for site pages": the class page renders its sections; these fields cover a stat block. |
| D16 | **Tests live in `ingestion/tests/`** (package with `__init__.py`). | Spec 001 D6 already added `ingestion` to `testpaths` "so later specs' tests are collected without config changes"; keeps ingestion self-contained. |
| D17 | **Ruff per-file ignores (additive):** `RUF001` for `ingestion/**` (the source's en dashes and curly quotes are data, not confusables); `E501` for `ingestion/overrides.py` and `ingestion/tests/**` (verbatim expected strings). | Without them ruff fails on legitimate typographic literals. Scoped to ingestion only. |
| D18 | **`Thanks.xml` (backer lists) and all appendices are ingested** like any chapter. | The draft says parse the source; filtering for retrieval is spec 007's choice. |
| D19 | **`data/normalized/.gitkeep` is kept.** | Spec 001's success criteria list it as tracked; deleting it gains nothing. |

**Open risk:** none for existing code. Forward risks: (a) D9's extended `stat` vocabulary and D7's nullable `miss` must be mirrored by spec 005's domain types and spec 006's move card; (b) each basic/special move exists both as a section (`moves/<id>`) and a move row with identical text — spec 007 must index one or the other, not both (see *Future Considerations*).

## Architecture / Design Overview

Ingestion is an offline batch step outside the hexagonal backend (handoff 4). It reads only `vendor/dungeon-world/text/**/*.xml`, never imports from `backend/`, and writes only `data/normalized/`.

```
manifest (37 chapters, ordered)
   │  verify manifest == text/**/*.xml
   ▼
for each chapter file ──▶ ElementTree parse ──▶ flatten blocks (descend Root/Body/Story/div)
                                                   │  h1/h2 ─▶ section boundary
                                                   │  other blocks ─▶ markdown.render_block()
                                                   │                    └─▶ UnknownMarkup.record()
                                                   ▼
                                        sections (global order)
   ├──▶ moves.extract(chapter "moves" elements, sections) ─▶ overrides.apply() ─▶ validate
   └──▶ classes.extract(8 class chapters)                                         ─▶ validate
   ▼
BuildResult(sections, moves, classes, unknown counts, overrides applied)
   ▼  CLI: report ─▶ unknown total > threshold? exit 1 (nothing written)
   ▼  serialize ─▶ data/normalized/{sections,moves,classes}.json
```

Key choices: everything is built in memory and written only after all gates pass, so a failed run never leaves partial output; extraction of moves reads the XML elements (not rendered Markdown) for trigger and stat, and the shared Markdown renderer for outcome text, so `body_markdown` and outcome strings use identical escaping (needed for D11's substring check).

## Source Facts

Verified at the pin; these are the requirements behind the parsing rules and the required content of `docs/source-notes.md`.

- **Files:** 37 XML files — 24 in `text/`, 4 in `text/appendices/`, 9 in `text/monster_settings/`. All UTF-8, well-formed, root `<Root xmlns:aid="http://ns.adobe.com/AdobeInDesign/4.0/">`. 29 files wrap content in `<Body>`, 8 in one or more `<Story>` (`Moves.xml` has three `Story` blocks; the third has no `h1` and continues "Special Moves").
- **Tag inventory (occurrences):** `p` 2574, `li` 1231, `span` 488, `em` 358, `h3` 308, `ul` 297, `strong` 294, `h2` 237, `div` 103, `h4` 99, `h1` 62, `Root` 37, `Body` 29, `TableBody` 15, `Cell` 14, `Story` 10, `Strong` 10, `TableHeader` 3, `ol` 3, `Center` 1, `StatTable` 1. No other tags. No block element is nested inside `p`/`li`/headings.
- **Attributes:** `aid:pstyle`, `aid:cstyle`, `id` (on `div` and on `span id="Damage"`), and table attributes `aid:table`, `aid:crows`, `aid:ccols`, `aid:ccolwidth`, `aid:theader`, `aid:trows`, `aid:tcols`.
- **Paragraph styles (`aid:pstyle`):** `NoIndent`, `MonsterStats`, `MoveName`, `MonsterName`, `MonsterDescription`, `NumberedList`, `MonsterQualities`, `ReNumberedList`, `Option`, `Item`, `SpellName`, `ExampleDialogue`, `Requirement`, `li`, `BasicMoveName`, `Example`, `MagicItem`, `InstructionsAfterHeader`, `MoveOneLine`, `Instructions`, `ExampleDialogueFirstLine`, `ItemDescription`, `ExampleDialogueLastLine`, `Lastli`, `Exampleli`, `MoveFirstLine`, `MoveLastLine`, `BackerList`, `BackerListNoIndent` (29 values). **Character styles (`aid:cstyle`):** `Tags`, `SpellName`.
- **Inconsistencies:** `strong` and `Strong` both mean bold. `BasicMoveName` is used on `h2` (moves in `Moves.xml`), on `h3` (class starting moves) and on a non-move heading (`The_World.xml` "Elements of a Steading"); class moves use both `MoveName` and `BasicMoveName`. `h1` is used both as chapter title and as mid-file subsection (`Class_Moves_Discussion.xml`, `Equipment.xml` "Magic Items", `Fronts.xml`). The single table (`Character_Creation.xml`, score → modifier) wraps cells inconsistently: children of `StatTable` are `Cell`, `TableHeader` or `TableBody`, each wrapping a `TableHeader`/`TableBody` text node; header cells carry `aid:theader`. `Druid.xml` has loose text ("Choose one:") directly inside a `div`. Monsters, spells and magic items are paragraphs (`MonsterName`, `SpellName`, `MagicItem`), not headings. Tabs separate columns inside paragraphs (spell level, item tags, dialogue speaker).
- **Characters:** ’ (1876), ” “ (≈320 each), — (318), ✴ (136, outcome marker, e.g. `✴On a 10+`), – (108, mostly in `7–9`; some files use `7-9`), … (58), × (12), accented names, U+200B zero-width space (2). Markdown-sensitive text: `_______________` blanks in bonds, dice notation `b[2d6]` / `w[]`, a literal `>` in `Thanks.xml`.
- **Move text:** outcome markers are "On a 10+", "On a 7–9" (or "7-9"), "On a hit", "On a miss", "On a 6-". The trigger is the bold text of the first paragraph. Most moves state no miss (see D7). `Moves.xml` has 8 moves under `h1` "Basic Moves" and 13 under "Special Moves", all `h2[aid:pstyle=BasicMoveName]`.
- **Class stat lines** (all 8 class files): "Your maximum HP is N+Constitution.", "Your base damage is `<span id="Damage">dN</span>`.", "Your load is N+Str. …".

## Configuration

No environment variables.

**CLI** — `uv run python -m ingestion [--source PATH] [--out PATH] [--max-unknown N]`, run from the repo root:

| Flag | Default | Meaning |
|------|---------|---------|
| `--source` | `vendor/dungeon-world/text` | Directory containing the manifest's XML files. |
| `--out` | `data/normalized` | Output directory (created if missing). |
| `--max-unknown` | `0` (`DEFAULT_MAX_UNKNOWN` in `ingestion/pipeline.py`) | Build fails if total unknown-markup occurrences exceed it. Integer ≥ 0. |

**Exit codes:** `0` success (three files written); `1` unknown markup over threshold (nothing written); `2` `IngestionError` (missing source dir, manifest mismatch, XML parse error, move/class/override validation failure) — message on stderr as `ingestion: error: <message>`; argparse usage errors keep argparse's own exit code `2`.

**Stdout report** (always printed before the exit decision):

```
ingestion: 37 chapters, <N> sections, 21 moves (15 rolled), 8 classes
ingestion: move overrides applied: 6
ingestion: unknown markup: <total> (threshold <N>)
  <key>: <count>          # one line per unknown key, sorted by key; omitted when total is 0
```

Unknown keys are `tag:<name>`, `attr:<name>`, `pstyle:<value>`, `cstyle:<value>`. Each occurrence is also logged at `WARNING` on logger `ingestion` (`unknown <key> in <relative file path>`); the CLI configures `logging.basicConfig(level=logging.WARNING)` to stderr.

**`pyproject.toml`** — additive (D17):

```toml
[tool.ruff.lint.per-file-ignores]
"ingestion/**" = ["RUF001"]
"ingestion/overrides.py" = ["E501"]
"ingestion/tests/**" = ["E501"]
```

## Chapter Manifest

`CHAPTERS` in `ingestion/manifest.py`, in this order (index = book order). Paths are relative to `--source`.

| # | File | Chapter id | Title |
|---|------|-----------|-------|
| 0 | `Introduction.xml` | `introduction` | Introduction |
| 1 | `Playing_the_Game.xml` | `playing-the-game` | Playing the Game |
| 2 | `Example.xml` | `example` | Example of Play |
| 3 | `Character_Creation.xml` | `character-creation` | Character Creation |
| 4 | `Moves.xml` | `moves` | Moves |
| 5 | `Moves_Discussion.xml` | `moves-discussion` | Moves Discussion |
| 6 | `Bard.xml` | `bard` | The Bard |
| 7 | `Cleric.xml` | `cleric` | The Cleric |
| 8 | `Cleric_Spells.xml` | `cleric-spells` | Cleric Spells |
| 9 | `Druid.xml` | `druid` | The Druid |
| 10 | `Fighter.xml` | `fighter` | The Fighter |
| 11 | `Paladin.xml` | `paladin` | The Paladin |
| 12 | `Ranger.xml` | `ranger` | The Ranger |
| 13 | `Thief.xml` | `thief` | The Thief |
| 14 | `Wizard.xml` | `wizard` | The Wizard |
| 15 | `Wizard_Spells.xml` | `wizard-spells` | Wizard Spells |
| 16 | `Class_Moves_Discussion.xml` | `class-moves-discussion` | Moves in Detail |
| 17 | `Equipment.xml` | `equipment` | Equipment |
| 18 | `GM.xml` | `gm` | The GM |
| 19 | `First_Session.xml` | `first-session` | First Session |
| 20 | `Fronts.xml` | `fronts` | Fronts |
| 21 | `The_World.xml` | `the-world` | The World |
| 22 | `Monsters.xml` | `monsters` | Monsters |
| 23 | `monster_settings/Caverns.xml` | `caverns` | Cavern Dwellers |
| 24 | `monster_settings/Depths.xml` | `depths` | Lower Depths |
| 25 | `monster_settings/Experiments.xml` | `experiments` | Twisted Experiments |
| 26 | `monster_settings/Folk.xml` | `folk` | Folk of the Realm |
| 27 | `monster_settings/Hordes.xml` | `hordes` | Ravenous Hordes |
| 28 | `monster_settings/Planes.xml` | `planes` | Planar Powers |
| 29 | `monster_settings/Swamp.xml` | `swamp` | Swamp Denizens |
| 30 | `monster_settings/Undead.xml` | `undead` | Undead Legions |
| 31 | `monster_settings/Woods.xml` | `woods` | Dark Woods |
| 32 | `Advanced_Delving.xml` | `advanced-delving` | Advanced Delving |
| 33 | `appendices/Teaching.xml` | `teaching` | Teaching the Game |
| 34 | `appendices/Conversion.xml` | `conversion` | Adventure Conversion |
| 35 | `appendices/NPCs.xml` | `npcs` | Instant NPCs |
| 36 | `appendices/Thanks.xml` | `thanks` | Thanks |

Class chapters (`CLASS_CHAPTER_IDS`): `bard`, `cleric`, `druid`, `fighter`, `paladin`, `ranger`, `thief`, `wizard`.

## Data Model

No database. Three JSON files (arrays) mirrored by frozen dataclasses in `ingestion/models.py`; each has a `to_dict()` returning keys in the order below (`GameClass`/`Move` map Python `class_` to JSON `class`).

```python
Category = Literal["basic", "special", "class"]
Stat = Literal["STR", "DEX", "CON", "INT", "WIS", "CHA", "BOND", "VARIES", "NONE"]

@dataclass(frozen=True, slots=True)
class Section:  id: str; chapter: str; title: str; slug: str; parent_id: str | None; order: int; text_markdown: str
@dataclass(frozen=True, slots=True)
class Outcomes: strong_hit: str; weak_hit: str; miss: str | None
@dataclass(frozen=True, slots=True)
class Move:     id: str; name: str; category: Category; class_: str | None; stat: Stat | None
                trigger: str; outcomes: Outcomes | None; body_markdown: str; section_id: str
@dataclass(frozen=True, slots=True)
class GameClass: id: str; name: str; section_id: str; order: int; max_hp_base: int; base_damage: str; load_base: int
```

**`sections.json`** — one object per section, sorted by `order`.

| Field | Type | Rule |
|-------|------|------|
| `id` | string | D5; unique; matches `^[a-z0-9]+(-[a-z0-9]+)*(/[a-z0-9]+(-[a-z0-9]+)*)?$`. |
| `chapter` | string | Chapter id from the manifest. |
| `title` | string | Plain heading text (whitespace-normalised, `✴`/U+200B removed); for chapter sections, the manifest title. Non-empty. |
| `slug` | string | Last segment of `id`. |
| `parent_id` | string \| null | `null` for chapter sections; an `h1` section's parent is its chapter; an `h2` section's parent is the most recent non-consumed `h1` section in the same file, else the chapter. |
| `order` | int | Global 0-based document order across the manifest; contiguous. |
| `text_markdown` | string | The section's own content (see *Markdown Rendering*); `""` if none. |

**`moves.json`** — 21 objects in `Moves.xml` document order.

| Field | Type | Rule |
|-------|------|------|
| `id` | string | `slugify(name)`; unique. |
| `name` | string | `h2` text. |
| `category` | `"basic"` \| `"special"` | From the most recent `h1` ("Basic Moves" / "Special Moves"); any other `h1` text is an `IngestionError`. (`"class"` is valid in the type, unused — D6.) |
| `class` | null | Always `null` (D6). |
| `stat` | Stat \| null | See *Move Extraction*. |
| `trigger` | string | Non-empty plain text. |
| `outcomes` | object \| null | `null` iff the move has no outcome marker; otherwise `{strong_hit: string, weak_hit: string, miss: string \| null}` (all three keys always present). |
| `body_markdown` | string | Equal to the `text_markdown` of `section_id`. |
| `section_id` | string | `moves/<id>`. |

**`classes.json`** — 8 objects in manifest order.

| Field | Type | Rule |
|-------|------|------|
| `id` | string | Chapter id (`fighter`). |
| `name` | string | Chapter's first `h1` text with leading `The ` removed (`Fighter`). |
| `section_id` | string | = `id` (the chapter section). |
| `order` | int | 0–7. |
| `max_hp_base` | int | `N` from `Your maximum HP is N+Constitution`. |
| `base_damage` | string | Text of `span[@id="Damage"]` (`d10`). |
| `load_base` | int | `N` from `Your load is N+Str`. |

## Impact on Existing Code

Files marked "(new in 001)" are created by spec 001, which is approved but not yet implemented; this spec assumes they exist, as it does `.github/workflows/ci.yml` (spec 001). Paths under `vendor/dungeon-world/` (including every XML file named in this spec) are upstream content that appears when spec 001 adds the submodule; they were verified in a read-only clone of the pinned commit on 2026-11-04 (D1).

| Path | Action | Notes |
|------|--------|-------|
| `ingestion/__init__.py` (new in 001) | unchanged | Stays empty. |
| `ingestion/__main__.py` (new) | create | `from ingestion.cli import main`; `raise SystemExit(main())`. |
| `ingestion/cli.py` (new) | create | `main(argv: Sequence[str] \| None = None) -> int` — argparse, report, threshold, write. |
| `ingestion/manifest.py` (new) | create | `Chapter(file, id, title)` dataclass, `CHAPTERS`, `CLASS_CHAPTER_IDS`. |
| `ingestion/models.py` (new) | create | *Data Model* types. |
| `ingestion/markdown.py` (new) | create | `UnknownMarkup`, known-markup inventories, `render_block`, `render_inline`, `plain_text`, `slugify`. |
| `ingestion/sections.py` (new) | create | Block flattening and sectioning per chapter. |
| `ingestion/moves.py` (new) | create | Move extraction, override application, validation. |
| `ingestion/classes.py` (new) | create | Class extraction and validation. |
| `ingestion/overrides.py` (new) | create | `MoveOverride` dataclass and `MOVE_OVERRIDES`. |
| `ingestion/pipeline.py` (new) | create | `IngestionError`, `BuildResult`, `build()`, `serialize()`, `write()`, `DEFAULT_MAX_UNKNOWN = 0`. |
| `ingestion/tests/__init__.py` (new) | create | Empty. |
| `ingestion/tests/conftest.py` (new) | create | `REPO_ROOT`, `SOURCE_DIR`, session fixture `real_build`; helper to write a tiny synthetic source + manifest under `tmp_path`. |
| `ingestion/tests/test_markdown.py` (new) | create | See *Testing*. |
| `ingestion/tests/test_sections.py` (new) | create | See *Testing*. |
| `ingestion/tests/test_moves.py` (new) | create | See *Testing*. |
| `ingestion/tests/test_overrides.py` (new) | create | See *Testing*. |
| `ingestion/tests/test_classes.py` (new) | create | See *Testing*. |
| `ingestion/tests/test_pipeline.py` (new) | create | See *Testing*. |
| `data/normalized/sections.json` (new) | create | Generated, committed (snapshot). |
| `data/normalized/moves.json` (new) | create | Generated, committed. |
| `data/normalized/classes.json` (new) | create | Generated, committed. |
| `data/normalized/.gitkeep` (new in 001) | unchanged | D19. |
| `docs/source-notes.md` (new in 001) | modify — **additive** | Replaces the one-line stub, which says it is "written in spec 002"; no code reads it. Content in *Documentation*. |
| `docs/decisions.md` (new in 001) | modify — **additive** | Append ADR-007 and ADR-008; existing ADRs untouched. |
| `pyproject.toml` (new in 001) | modify — **additive** | Add `[tool.ruff.lint.per-file-ignores]` (D17). No dependency, pyright or pytest change; relaxes two rules for `ingestion/` paths only, so no existing check gets stricter or breaks. |

CI (`.github/workflows/ci.yml`) needs no change: its `python` job checks out submodules and runs `uv run pytest`, which collects `ingestion/tests/`.

## Python Modules & Interfaces

### Public signatures

```python
# ingestion/pipeline.py
class IngestionError(Exception): ...
@dataclass(frozen=True, slots=True)
class BuildResult:
    sections: tuple[Section, ...]; moves: tuple[Move, ...]; classes: tuple[GameClass, ...]
    unknown: Mapping[str, int]          # key -> occurrences; empty when none
    overrides_applied: int
    @property
    def unknown_total(self) -> int: ...
def build(source_dir: Path, chapters: Sequence[Chapter] = CHAPTERS,
          overrides: Mapping[str, MoveOverride] = MOVE_OVERRIDES) -> BuildResult
def serialize(result: BuildResult) -> dict[str, str]   # {"sections.json": text, "moves.json": ..., "classes.json": ...}
def write(result: BuildResult, out_dir: Path) -> None   # mkdir -p, write_text(..., encoding="utf-8", newline="\n")

# ingestion/overrides.py
@dataclass(frozen=True, slots=True)
class MoveOverride:
    reason: str
    stat: Stat | None = None
    strong_hit: str | None = None
    weak_hit: str | None = None
    miss: str | None = None
MOVE_OVERRIDES: Final[Mapping[str, MoveOverride]]
```

`build()` raises `IngestionError` for: `source_dir` not a directory; manifest/file-set mismatch (message lists missing and unlisted files); XML parse error (message names the file); duplicate chapter id; a validation failure from *Validation Rules*. Move extraction runs only if chapter `moves` is in `chapters`; class extraction only for `CLASS_CHAPTER_IDS` present in `chapters` (lets tests use tiny synthetic manifests; the real manifest always contains them — enforced by tests).

### Block flattening and sectioning (`sections.py`)

Walk each file's tree in document order. `Root`, `Body`, `Story`, `div` are transparent containers: descend into them; non-whitespace text directly inside a container (its `.text` or a child's `.tail`) becomes its own paragraph block. Every other element is a block.

1. The first `h1`/`h2`/`h3`/`h4` element in document order is the **chapter heading** if it is an `h1` whose plain text equals the manifest title case-insensitively (`casefold()`); it is consumed (produces no section).
2. The chapter section (`id` = chapter id, `title` = manifest title, `parent_id` = null) collects all blocks before the first non-consumed `h1`/`h2`.
3. Each non-consumed `h1`/`h2` starts a new section per D5 and *Data Model* parent rules; it collects following blocks until the next `h1`/`h2` or end of file.
4. `text_markdown` = rendered blocks joined with `"\n\n"`.

### Markdown rendering (`markdown.py`)

**Inline** (contents of `p`, `li`, `h3`, `h4`, table cells):

| Source | Output |
|--------|--------|
| text node | Whitespace runs (spaces, tabs, newlines) → one space; remove `✴` and U+200B; escape `\`, `*`, `_`, `` ` ``, `[`, `]` with a backslash. |
| `em` | `*…*` |
| `strong`, `Strong` | `**…**` |
| `span` with `aid:cstyle="Tags"` | `*…*` |
| `span` with `aid:cstyle="SpellName"` or no cstyle | contents unchanged |
| any unknown tag | its rendered contents (recorded as unknown) |

Emphasis whose content is empty after trimming is dropped; leading/trailing spaces inside emphasis move outside the markers. The final inline string is trimmed. Escaping happens before markers are added, so emitted `*`/`**` are never escaped.

**Blocks:**

| Source | Output |
|--------|--------|
| `p` (default, any known pstyle not below) | inline text |
| `p` pstyle `MonsterName`, `SpellName`, `MagicItem` | `#### ` + inline |
| `p` pstyle `Example`, `ExampleDialogue`, `ExampleDialogueFirstLine`, `ExampleDialogueLastLine` | `> ` + inline |
| `p` pstyle `Requirement` | `*` + inline + `*` |
| `h3` / `h4` | `### ` / `#### ` + inline |
| `ul` | one `- ` + inline line per `li`, joined with `"\n"` |
| `ol` | `1. `, `2. `… per `li` (numbering restarts per `ol`) |
| `Center` > `StatTable` | GFM table: `StatTable`'s children in order are cells regardless of tag name; column count = `aid:tcols`; leading cells with `aid:theader` form the header row (`\| Score \| Modifier \|`, then `\| --- \| --- \|`), the rest fill body rows left to right; cell text = plain text of the cell. |
| loose container text | inline-normalised paragraph |
| unknown block tag | its contents rendered inline as a paragraph (recorded as unknown) |

After rendering a paragraph or a list item's content (before the `- `/`1. ` prefix is added), escape a block marker at its start: `#`, `>`, `-`/`+`/`*` followed by a space, or `\d+[.)]` followed by a space, get a leading backslash. Empty blocks are dropped.

**Unknown tracking:** `UnknownMarkup.record(key, file)` increments a `Counter` and logs at WARNING. Known inventories are exactly those in *Source Facts* (tags, attributes, 29 pstyles, 2 cstyles); the `xmlns:aid` declaration is not an attribute in ElementTree. Every element visited during rendering is checked: tag, each attribute name, and the pstyle/cstyle value.

**`slugify(text)`:** NFKD-normalise, drop combining marks, lowercase, delete `’` and `'`, replace `&` with ` and `, replace each run of characters outside `[a-z0-9]` with `-`, strip `-`. Empty result → `section-<order>`.

**`plain_text(el)`:** concatenated text of the element and descendants, whitespace-normalised, `✴`/U+200B removed, no Markdown.

### Move extraction (`moves.py`)

For each section in chapter `moves` whose heading is an `h2` with `aid:pstyle="BasicMoveName"`, take the elements between that heading and the next `h1`/`h2` (the "block"):

1. **Trigger:** in the block's first `p`, the plain text from the paragraph start through the end of its last `strong`/`Strong` element, with trailing whitespace and `,.;:` stripped. No `strong` in the first `p` → `IngestionError`.
2. **Markers:** render each block `p` inline (with a throwaway `UnknownMarkup`, so sectioning remains the only place unknowns are counted); find `On a (10\+|7[–-]9|hit|miss|6-)` (the `✴` is already removed). Each segment runs from a marker to the next marker or paragraph end, trimmed. Band map: `10+` → strong; `7–9`/`7-9` → weak; `hit` → both strong and weak; `miss`/`6-` → miss. Segments of the same band join with one space, in document order (a `hit` segment therefore precedes the band's own segment).
3. **Lists:** a `ul`/`ol` that immediately follows a `p` whose last segment belongs to band B is rendered as a Markdown list and appended to B (both bands for `hit`) with `"\n\n"` as separator.
4. **Outcomes:** no marker in the block → `outcomes = null`, `stat = null`. Otherwise `Outcomes(strong_hit, weak_hit, miss or None)`.
5. **Stat** (rolled moves only): first match of `\brolls?\s*\+\s*(Str|Dex|Con|Int|Wis|Cha|Bond)\b` (case-insensitive) in the plain text of the block's `p` elements → uppercased; no match → `"NONE"`.
6. **Overrides** (D11): apply `MOVE_OVERRIDES[id]` field by field (`None` = keep automatic value); then validate.
7. `body_markdown` = the section's `text_markdown`; `section_id` = the section id; `class_` = `None`.

### Move Overrides

`MOVE_OVERRIDES` at the pin — exactly these six entries (strings verbatim, including ’ and –):

| Move id | Field → value | Reason |
|---------|---------------|--------|
| `defy-danger` | `stat` → `"VARIES"` | The stat is chosen by approach from a `+Str … +Cha` list; there is no `roll+STAT` phrase. |
| `defend` | `weak_hit` → `"On a 7–9, hold 1."` | The spend-hold rules and option list that follow apply to both hit bands. |
| `spout-lore` | `weak_hit` → `"On a 7–9 the GM will only tell you something interesting—it’s on you to make it useful."` | "The GM might ask you …" applies to both hit bands. |
| `discern-realities` | `weak_hit` → `"On a 7–9 ask 1."` | "Take +1 forward …" and the question list apply to both hit bands. |
| `carouse` | `miss` → `"On a miss, you still choose one, but things get really out of hand."` | The option list applies to all three bands. |
| `recruit` | `miss` → `"On a miss someone influential and ill-suited declares they’d like to come along (a foolhardy youth, a loose-cannon, or a veiled enemy, for example), bring them and take the consequences or turn them away."` | "If you turn away applicants …" applies regardless of the roll. |

### Expected results for the named moves (test contract)

`body_markdown` omitted; `category`, `class` (`null`) and `section_id` (`moves/<id>`) as per *Data Model*.

```json
[
  {"id": "hack-and-slash", "category": "basic", "stat": "STR",
   "trigger": "When you attack an enemy in melee",
   "outcomes": {"strong_hit": "On a 10+ you deal your damage to the enemy and avoid their attack. At your option, you may choose to do +1d6 damage but expose yourself to the enemy’s attack.",
                "weak_hit": "On a 7–9, you deal your damage to the enemy and the enemy makes an attack against you.",
                "miss": null}},
  {"id": "defy-danger", "category": "basic", "stat": "VARIES",
   "trigger": "When you act despite an imminent threat or suffer a calamity",
   "outcomes": {"strong_hit": "On a 10+, you do what you set out to, the threat doesn’t come to bear.",
                "weak_hit": "On a 7–9, you stumble, hesitate, or flinch: the GM will offer you a worse outcome, hard bargain, or ugly choice.",
                "miss": null}},
  {"id": "volley", "category": "basic", "stat": "DEX",
   "trigger": "When you take aim and shoot at an enemy at range",
   "outcomes": {"strong_hit": "On a 10+ you have a clear shot—deal your damage.",
                "weak_hit": "On a 7–9, choose one (whichever you choose you deal your damage):\n\n- You have to move to get the shot placing you in danger of the GM’s choice\n- You have to take what you can get: -1d6 damage\n- You have to take several shots, reducing your ammo by one.",
                "miss": null}},
  {"id": "discern-realities", "category": "basic", "stat": "WIS",
   "trigger": "When you closely study a situation or person",
   "outcomes": {"strong_hit": "On a 10+ ask the GM 3 questions from the list below.",
                "weak_hit": "On a 7–9 ask 1.",
                "miss": null}},
  {"id": "last-breath", "category": "special", "stat": "NONE",
   "trigger": "When you’re dying",
   "outcomes": {"strong_hit": "On a 10+ you’ve cheated death—you’re in a bad spot but you’re still alive.",
                "weak_hit": "On a 7–9 Death will offer you a bargain. Take it and stabilize or refuse and pass beyond the Black Gates into whatever fate awaits you.",
                "miss": "On a miss, your fate is sealed. You’re marked as Death’s own and you’ll cross the threshold soon. The GM will tell you when."}}
]
```

Full move lists (ids, document order): **basic** `hack-and-slash`, `volley`, `defy-danger`, `defend`, `spout-lore`, `discern-realities`, `parley`, `aid-or-interfere`; **special** `last-breath`, `encumbrance`, `make-camp`, `take-watch`, `undertake-a-perilous-journey`, `level-up`, `end-of-session`, `carouse`, `supply`, `recover`, `recruit`, `outstanding-warrants`, `bolster`.

Expected stats of rolled moves: `defend` CON; `spout-lore` INT; `parley`, `supply`, `outstanding-warrants` CHA; `aid-or-interfere` BOND; `take-watch`, `undertake-a-perilous-journey` WIS; `carouse`, `recruit` NONE (plus the named moves above).

### Class extraction (`classes.py`)

For each chapter in `CLASS_CHAPTER_IDS` (manifest order): `name` from the first `h1`; `max_hp_base` from `Your maximum HP is (\d+)\+Constitution`; `base_damage` from the text of the first `span` with `id="Damage"`; `load_base` from `Your load is (\d+)\+Str` (regexes over the chapter's plain paragraph text). Any missing value → `IngestionError` naming the class and field.

## Validation Rules

No user input; these are build-time rules. Each failure raises `IngestionError` (exit 2) unless noted.

| Subject | Rule |
|---------|------|
| Source dir | Exists and is a directory. |
| Manifest | Set of manifest files == set of `**/*.xml` under source (relative POSIX paths); chapter ids unique and matching `^[a-z0-9]+(-[a-z0-9]+)*$`. |
| XML | Each file parses; parse errors name the file. |
| Unknown markup | Total occurrences ≤ `--max-unknown` (default 0); else exit 1, nothing written. |
| Section | `title` non-empty; `id` unique and matches the *Data Model* pattern; `parent_id` refers to an earlier section. |
| Move | `category` resolvable from the enclosing `h1`; `id` unique; `trigger` non-empty; if `outcomes` present: `strong_hit` and `weak_hit` non-empty and `stat` non-null; if absent: `stat` is null. |
| Override | Key is an existing move id; each band string is a substring of that move's `body_markdown`; each set field (band or `stat`) differs from the automatic value; band override on a move with `outcomes: null` is invalid. |
| Class | All three stat lines found; `max_hp_base`, `load_base` parse as positive ints; `base_damage` matches `^d\d+$`. |
| CLI | `--max-unknown` is an int ≥ 0 (argparse error otherwise). |

## Authorization & Security

No users, endpoints or permissions. Security-relevant choices:

- Reads only the XML files listed in the manifest under `--source` (default `vendor/dungeon-world/text/`), honouring spec 001 D10; nothing else in the submodule is read.
- Writes only the three files in `--out`.
- No network access, no secrets, no LLM calls; runs in CI under spec 001's read-only, secret-free workflow.
- XML input is the pinned, trusted upstream; stdlib expat's entity-expansion protections apply (D2).

## Documentation

**`docs/source-notes.md`** replaces the stub. Title `# Source notes`, then sections with this content (facts from *Source Facts*, re-verified against the submodule):

1. *Pinned source* — upstream URL, commit hash, "only `text/` is read".
2. *File layout* — the 37 files, `Body` vs `Story` wrappers, the chapter manifest and why it exists (D3).
3. *Tag and attribute inventory* — tag counts, attributes, all pstyle and cstyle values, and how each renders (link to the rendering tables by summarising them).
4. *Inconsistencies found* — every bullet under "Inconsistencies" in *Source Facts*.
5. *Special characters* — the character list, what is kept verbatim and what is removed (D14), Markdown escaping.
6. *Moves* — marker forms, trigger convention, the "most moves won't say what happens on a 6-" rule (quoted, with file), and the resulting nullable `miss` (D7).
7. *Move overrides* — the six entries and their reasons, plus the substring and must-differ rules (D11).
8. *Unknown-markup gate* — the threshold (0), the key format, and how to update the inventory if upstream changes.

**`docs/decisions.md`** — append, same format as ADR-001…006 (spec 001 D15):

| ADR | Title | Content source |
|-----|-------|----------------|
| ADR-007 | Ingestion: stdlib parser, chapter manifest, IDs, committed output as snapshot | D2, D3, D4, D5, D12, D13, D14 |
| ADR-008 | Outcome bands follow the source; extended stat vocabulary | D7, D8, D9, D10 — must state the discrepancy with handoff milestone 2 and that the source wins (handoff 12). |

## Testing

pytest, plain functions, files in `ingestion/tests/`. Shared in `conftest.py`: `REPO_ROOT = Path(__file__).resolve().parents[2]`, `SOURCE_DIR = REPO_ROOT / "vendor/dungeon-world/text"`, a session-scoped `real_build` fixture (`build(SOURCE_DIR)`; calls `pytest.fail` with a hint to run `git submodule update --init` if `SOURCE_DIR` is missing), and a helper `make_source(tmp_path, files: dict[str, str]) -> tuple[Path, tuple[Chapter, ...]]` that writes XML files and returns a matching manifest. Unit tests use small inline XML strings parsed with `ET.fromstring`. All tests are offline and deterministic.

**`test_markdown.py`**
- `test_emphasis_tags_render_as_markdown` — `<p>a <em>b</em> <strong>c</strong> <Strong>d</Strong></p>` → `a *b* **c** **d**`.
- `test_whitespace_star_glyph_and_zero_width_space_are_normalised` — `roll+Str. ✴On a 10+,\tchoose​ 3` → `roll+Str. On a 10+, choose 3`.
- `test_markdown_metacharacters_are_escaped` — `b[2d6] and ___` → `b\[2d6\] and \_\_\_`.
- `test_leading_block_marker_is_escaped` — paragraph `- a` → `\- a`; `+2 damage` unchanged.
- `test_tags_span_is_italic_and_spellname_span_is_plain`.
- `test_monster_spell_and_magic_item_paragraphs_render_as_h4`.
- `test_example_paragraphs_render_as_blockquote`.
- `test_requirement_paragraph_renders_italic`.
- `test_lists_render_bulleted_and_numbered` — `ol` numbering restarts per list.
- `test_stat_table_with_mixed_cell_tags_renders_gfm_table` — a 2-column snippet with `Cell`/`TableHeader`/`TableBody` wrappers as in `Character_Creation.xml` → header `| Score | Modifier |` and correct body rows.
- `test_loose_container_text_becomes_paragraph`.
- `test_unknown_tag_is_counted_and_its_text_kept` — `<p>x <Blink>y</Blink></p>` → `x y`, `unknown == {"tag:Blink": 1}`.
- `test_unknown_attribute_pstyle_and_cstyle_are_counted` — keys `attr:foo`, `pstyle:Bogus`, `cstyle:Bogus`.
- `test_slugify` — parametrized: `Hack and Slash`→`hack-and-slash`; `What’s Dungeon World Like to Play?`→`whats-dungeon-world-like-to-play`; `1. Choose a Class`→`1-choose-a-class`; `Magic & Treasure`→`magic-and-treasure`; `Viertiö`→`viertio`.

**`test_sections.py`**
- `test_matching_first_h1_is_consumed_as_chapter_heading` (synthetic).
- `test_non_matching_first_h1_becomes_child_section` (synthetic; mirrors `Moves.xml`).
- `test_h2_parents_to_latest_h1_else_chapter` (synthetic, across two `Story` blocks).
- `test_duplicate_heading_in_chapter_gets_numeric_suffix` (synthetic → `x/notes`, `x/notes-2`).
- `test_section_text_excludes_child_sections` (synthetic).
- `test_build_fails_when_source_has_unlisted_file` and `test_build_fails_when_manifest_file_is_missing` (synthetic; `IngestionError` message names the file).
- `test_build_fails_on_malformed_xml` (synthetic).
- `test_manifest_matches_real_source_files` (real).
- `test_every_chapter_has_a_root_section_in_manifest_order` (real).
- `test_section_ids_unique_and_well_formed`, `test_parent_ids_resolve_to_earlier_sections`, `test_order_is_contiguous_from_zero` (real).
- `test_moves_chapter_hierarchy` (real) — `moves/basic-moves` parent `moves`; `moves/hack-and-slash` parent `moves/basic-moves`; `moves/bolster` parent `moves/special-moves`.

**`test_moves.py`**
- `test_move_ids_match_source_lists` — basic and special id lists exactly as in *Expected results*.
- `test_named_move_parses_correctly` — parametrized over the five named moves; asserts every field in the expected JSON, plus `class is None` and `section_id`.
- `test_every_rolled_move_has_trigger_stat_and_hit_bands` — 15 rolled moves; milestone acceptance.
- `test_miss_present_only_where_source_states_it` — ids with non-null `miss` == `{last-breath, take-watch, carouse, recruit}`.
- `test_unrolled_moves_have_no_outcomes_and_no_stat` — == `{encumbrance, make-camp, level-up, end-of-session, recover, bolster}`.
- `test_rolled_move_stats` — the expected-stat list.
- `test_on_a_hit_prefixes_both_hit_bands` — `parley`: both bands start with `On a hit they ask you for something`; `weak_hit` ends with `right now.`.
- `test_list_after_band_attaches_to_that_band` — `outstanding-warrants.weak_hit` ends with `- Someone important to you has been put in a bad spot as a result of your actions`.
- `test_repeated_band_segments_are_joined` — `undertake-a-perilous-journey.strong_hit` contains three `On a 10+`.
- `test_move_body_equals_its_section_text`.
- `test_rolled_move_without_weak_hit_fails_build` (synthetic `Moves.xml`).
- `test_move_under_unexpected_h1_fails_build` (synthetic).

**`test_overrides.py`**
- `test_override_set_is_exactly_the_documented_six`.
- `test_every_override_targets_an_existing_move` (real).
- `test_override_bands_are_verbatim_substrings_of_move_body` (real).
- `test_every_override_changes_the_automatic_result` — `build(SOURCE_DIR, overrides={})` vs `real_build`: each overridden field differs.
- `test_override_with_non_source_text_fails_build`, `test_override_for_unknown_move_fails_build`, `test_override_equal_to_automatic_value_fails_build` (synthetic or real source with a custom overrides mapping).

**`test_classes.py`**
- `test_classes_are_the_eight_core_classes_in_order`.
- `test_class_stats_match_source` — parametrized: bard 6/d6/9; cleric 8/d6/10; druid 6/d6/6; fighter 10/d10/12; paladin 10/d10/12; ranger 8/d8/11; thief 6/d8/9; wizard 4/d4/7 (`max_hp_base`/`base_damage`/`load_base`); `name` is the capitalised class name without "The".
- `test_class_section_ids_resolve`.
- `test_missing_class_stat_line_fails_build` (synthetic `Fighter.xml` without the load line).

**`test_pipeline.py`**
- `test_real_source_has_no_unknown_markup` — `real_build.unknown == {}`.
- `test_committed_output_matches_fresh_build` — `serialize(real_build)` equals each committed file's text; failure message: "normalized output is stale: run `uv run python -m ingestion` and review the diff".
- `test_serialization_is_deterministic` — two `serialize` calls on two builds are equal.
- `test_cli_writes_three_files_and_reports_counts` — `main(["--out", str(tmp)])` returns 0, writes three files, stdout contains `21 moves (15 rolled), 8 classes` and `unknown markup: 0 (threshold 0)`.
- `test_cli_exits_1_and_writes_nothing_when_unknown_markup_exceeds_threshold` — copy the real source to `tmp_path`, inject `<Sparkle>shiny</Sparkle>` into a paragraph of `Introduction.xml`; returns 1, out dir has no JSON files, stdout lists `tag:Sparkle: 1`.
- `test_cli_raised_threshold_accepts_unknown_markup_and_keeps_text` — same source with `--max-unknown 1`; returns 0 and `shiny` appears in the `introduction` section text.
- `test_cli_exits_2_on_missing_source_dir` — stderr starts with `ingestion: error:`.

**Manual / CI verification (not pytest):** `uv run python -m ingestion` on a fresh `--recurse-submodules` clone produces no git diff in `data/normalized/`; ruff, ruff format, pyright exit 0.

## Suggested Story Breakdown

1. **Source notes, manifest and Markdown renderer** — `docs/source-notes.md` (sections 1–5 and 8; re-verify facts against the submodule), `manifest.py`, `models.py` (types only), `markdown.py`, the ruff per-file ignores, `test_markdown.py`, `test_manifest_matches_real_source_files`. Verifiable by unit tests. Depends on spec 001.
2. **Sections, pipeline and CLI with unknown gate** — `sections.py`, `pipeline.py`, `cli.py`, `__main__.py`, `conftest.py`, `test_sections.py`, `test_pipeline.py`; commit all three files. Until stories 3–4 land, `build()` has no `overrides` parameter, `moves.json`/`classes.json` are `[]`, and `test_cli_writes_three_files_and_reports_counts` asserts the interim line `0 moves (0 rolled), 0 classes`; stories 3–4 extend the signature and update that assertion to its final form. Depends on 1.
3. **Move extraction and overrides** — `moves.py`, `overrides.py` (adds the `overrides` parameter to `build()`), `test_moves.py`, `test_overrides.py`, regenerate and commit `moves.json` (`sections.json` must not change); source-notes sections 6–7; ADR-008. Depends on 2.
4. **Classes and close-out** — `classes.py`, `test_classes.py`, regenerate `classes.json`, ADR-007, final CLI report test (`21 moves (15 rolled), 8 classes`). Depends on 2 (independent of 3, but run after it so the report test is final).

## Success Criteria

- [ ] Every test listed in *Testing* exists and passes with `uv run pytest`.
- [ ] `uv run ruff format --check .`, `uv run ruff check .`, `uv run pyright` exit 0.
- [ ] `uv run python -m ingestion` exits 0, prints `unknown markup: 0 (threshold 0)`, and leaves `git status data/normalized/` clean on a fresh clone.
- [ ] `moves.json` has 21 moves (8 basic, 13 special); all 15 rolled moves have non-empty `trigger`, non-null `stat`, and `outcomes` with non-empty `strong_hit` and `weak_hit` and a `miss` key (milestone 2 acceptance as restated in D7).
- [ ] The five named moves match *Expected results* exactly (`test_named_move_parses_correctly`).
- [ ] The CLI exits 1 and writes nothing when unknown markup exceeds the threshold (`test_cli_exits_1_and_writes_nothing_when_unknown_markup_exceeds_threshold`).
- [ ] `docs/source-notes.md` contains the eight sections of *Documentation*; `docs/decisions.md` contains ADR-007 and ADR-008.
- [ ] No file outside `vendor/dungeon-world/text/` is read by `ingestion/` (all reads go through the manifest).

## Future Considerations

- Class moves as structured `moves.json` rows (`category: "class"`) with best-effort outcome extraction, for richer class pages — not for the classifier.
- Spec 007 should index either move rows or `moves/*` sections, not both, to avoid duplicate retrieval hits.
- Monster and spell entries as their own sections (or a `monsters.json`) if retrieval evals show the large monster-setting sections hurt recall.
- Record the submodule commit in an output metadata file once the site wants to display "source version".
