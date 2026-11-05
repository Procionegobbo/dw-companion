# 005 - Domain types and dice resolution

**Status:** spec — ready for story-creator.
**Depends on:** 001 (toolchain, `backend/domain/` and `backend/tests/` packages, `docs/decisions.md`). No code dependency on 002/004 — can be built in parallel; its types mirror the shapes fixed by spec 002.
**Reference:** `HANDOFF_dw-companion.md` sections 4.1, 4.4 (move branch, dice), 10 (milestone 4), 12.

## Feature Name & Description

**Domain types and dice resolution.** The pure core of the backend: immutable, validated types for the rulebook (`Section`, `Move`, `Outcomes`), deterministic `2d6 + modifier` resolution into the Dungeon World bands `10+ | 7-9 | 6-`, and an `Outcome` that pairs a roll with the move's verbatim band text. Later layers (ports, adapters, graph, API) build on these types; the graph's `roll` tool (spec 006) calls the dice primitive here, so the LLM never invents a roll.

**Current state.** Nothing is implemented yet. Spec 001 (approved) will create an empty `backend/domain/__init__.py`, `backend/tests/`, `pyproject.toml`, `uv.lock` and `docs/decisions.md`; paths marked "(new in 001)" below refer to those. Spec 002 (approved) will produce `data/normalized/sections.json` and `data/normalized/moves.json` and mirror them with dataclasses in `ingestion/models.py` (all "new in 002"), which the backend must not import (see D2). No domain code exists.

**In scope.** `backend/domain/rulebook.py`, `backend/domain/dice.py`, `backend/domain/outcome.py`; runtime invariants on every type; pure dict-to-type parsers for the spec 002 shapes; injected randomness so tests are deterministic; unit tests including exhaustive band boundaries, invariant violations, an import-purity guard and a compatibility test against the committed JSON; one ADR.

**Out of scope.** Ports, adapters, the JSON file loader (`RulebookRepository`, specs 006/007), the graph and the `roll` tool's exposure to the LLM (spec 006), the move card UI (spec 008), classes (`classes.json` has no backend consumer yet), any I/O.

## Assumptions & Decisions

| # | Decision | Reasoning / precedent |
|---|----------|-----------------------|
| D1 | **Stdlib only: frozen, slotted `dataclasses` with `__post_init__` validation and `typing.Literal` vocabularies.** No Pydantic, no new dependency. | Same pattern as `ingestion/models.py` (spec 002 D2) and its Literal `Stat`/`Category`; handoff 12 (justify every dependency); handoff 4.1 (domain has no framework imports). Pydantic arrives with FastAPI in spec 008 at the API boundary, where it belongs. |
| D2 | **The domain re-declares the spec 002 shapes rather than importing `ingestion.models`.** Compatibility is proven by tests: inline fixtures copied from spec 002's test contract, plus a test that parses the committed `data/normalized/*.json` when present. | Handoff 4: ingestion is an offline step outside the hexagonal backend; the runtime container must not need the ingestion package. Duplication of ~20 lines of type declarations is cheaper than coupling the runtime to the build tool. |
| D3 | **`Stat` vocabulary = spec 002 D9**: `"STR" \| "DEX" \| "CON" \| "INT" \| "WIS" \| "CHA" \| "BOND" \| "VARIES" \| "NONE"`, `None` = not rolled. A separate `AbilityStat` (`STR…CHA`) is exported for the classifier's output `stat` (handoff 4.4), which stays `AbilityStat \| None`. | Spec 002 D9 and its open risk (a) require spec 005 to mirror the extended vocabulary. The classifier contract is unchanged; mapping (VARIES → classifier picks an ability; BOND/NONE → `null`) is spec 006's job. |
| D4 | **`Outcomes.miss` is `str \| None`; `Move.outcomes` is `Outcomes \| None`.** Invariant: `(move.stat is None) == (move.outcomes is None)`. | Spec 002 D7 (most moves state no miss) and D8 (non-rolled moves have both `null`). Spec 004 D11 renders a `null` miss as "Not stated by this move." — the domain never fills it in. |
| D5 | **Naming: `Outcomes` (plural) = a move's three band texts, mirroring spec 002; `Outcome` (singular) = the resolved result of one roll on one move** (`move_id`, `roll`, `band`, `text`). | Handoff 4.1 names `Outcome` as a domain type and 4.4 has an `outcome` graph node; spec 002 already uses `Outcomes` for the band texts. Keeping both names avoids renaming the approved shape. |
| D6 | **`Band = Literal["strong_hit", "weak_hit", "miss"]`**, values identical to the `outcomes` JSON keys; display labels `10+`, `7-9`, `6-` (ASCII hyphen) via `band_label()`. | One vocabulary from JSON to resolution; ASCII labels avoid ruff `RUF001` in `backend/` and match the handoff's notation. |
| D7 | **Randomness is injected**: `roll(rng, modifier)` takes any object satisfying `RandomSource` (a Protocol with `randint(a, b, /) -> int`); `random.Random` satisfies it structurally. The domain never imports `random` and holds no global RNG. Production creates the generator (spec 006); tests pass `random.Random(seed)` or a scripted fake. | Handoff 4.4 "Seeded RNG in tests"; injection keeps `domain/` free of hidden state and lets tests force exact dice. Values returned by the source outside 1–6 raise `ValueError` (guards broken fakes). `random.Random` is not cryptographic; dice are not security-sensitive. |
| D8 | **Modifier is optional and bounded to `-10…+10` inclusive.** `modifier=None` yields a `Roll` with dice but no `total`/`band`; `Roll.band_with(modifier)` lets the caller report the band for any modifier. `bool` is rejected. | Handoff 4.4: "The user may supply their stat modifier; if not, the tool reports results per band without a total, or asks for the modifier." Stats are −3…+3, plus forward/ongoing bonuses; ±10 covers real play while rejecting nonsense the LLM might pass as a tool argument in spec 006. |
| D9 | **Band rule:** total `≥ 10` → `strong_hit`; `7 ≤ total ≤ 9` → `weak_hit`; `≤ 6` → `miss`. `band_for_total` accepts any `int`. | Handoff 4.1 / Dungeon World rules; no natural-roll special cases exist in the core rules. |
| D10 | **Pure parsers `section_from_dict` / `move_from_dict`** live in the domain. They accept `Mapping[str, object]`, require exactly the spec 002 keys (missing or extra key → `ValueError`), map JSON `class` to `class_`, and construct the validated types. No file access. | Gives specs 006/007 (`RulebookRepository`) one tested place where the JSON contract is enforced; makes D2's compatibility test possible. Rejecting extra keys makes shape drift in spec 002 output fail loudly. |
| D11 | **All validation failures raise `ValueError`** with a message naming the type and field (`"invalid move 'volley': stat must be one of …"`). No custom exception class. | Simplest surface; callers (adapters, tool wrapper) catch one type. |
| D12 | **Invariants enforced at construction** (see *Validation Rules*), including ID patterns from spec 002 D5 and section-hierarchy consistency. | Draft asks for unit-tested "type invariants"; validating in `__post_init__` means an invalid domain object cannot exist. |
| D13 | **Purity is enforced by a test**: an AST scan of `backend/domain/*.py` allows only `__future__`, `collections.abc`, `dataclasses`, `re`, `typing` and `backend.domain.*` imports. | Handoff 4.1 "No I/O, no LLM imports"; makes the rule binary and regression-proof. |
| D14 | **No coverage tool is added.** "Full coverage" is met by the named tests in *Testing*, which exercise every public function and every invariant branch. | Spec 001 D4 (no speculative deps). `pytest-cov` with a 100% gate on `backend/domain` is listed under *Future Considerations*. |
| D15 | **Tests are flat files in `backend/tests/` prefixed `test_domain_`**; non-ASCII fixture text uses `\u2019`/`\u2013` escapes so no ruff per-file-ignore is needed. | Spec 001 D6/Testing (flat files, plain functions); `--import-mode=importlib` already handles duplicate basenames. |
| D16 | **ADR number:** the next free number in `docs/decisions.md` at implementation time (ADR-010 if specs 002 and 004 — ADR-007/008/009 — have landed first). | This spec is buildable in parallel with 002/004; spec 001 D15 forbids renumbering, so the implementer takes the next free number. |
| D17 | **`backend/domain/__init__.py` stays empty**; callers import from submodules (`from backend.domain.dice import roll`). | Spec 001 leaves it empty and its smoke test only imports it; no re-export layer needed for three modules. |

**Open risk:** none for existing code (all additions). Forward risk: if spec 002's implementation deviates from its spec (e.g. adds a JSON key), `test_committed_moves_json_parses` / `test_committed_sections_json_parses` fail — intended, the shapes are a contract.

## Architecture / Design Overview

`backend/domain/` is the innermost hexagonal layer (handoff 4.1): it depends on nothing but the standard library, and everything else may depend on it.

```
rulebook.py  Stat, AbilityStat, Category, Outcomes, Move, Section, move_from_dict, section_from_dict
                                                  (imports Band from dice)
dice.py      Band, RandomSource, MIN/MAX_MODIFIER, band_for_total, band_label, Roll, roll
outcome.py   Outcome, resolve_outcome          (imports rulebook + dice)

spec 006 roll tool:  rng = random.Random()  ──▶ roll(rng, modifier) ──▶ Roll
                     move (from RulebookRepository) + Roll ──▶ resolve_outcome ──▶ Outcome
                                                                 (verbatim band text, never LLM-written)
```

Flow for a roll: two dice come from the injected `RandomSource`; if a modifier is known, `Roll.total = d1 + d2 + modifier` and `Roll.band = band_for_total(total)`; `resolve_outcome` then picks `move.outcomes.<band>` verbatim. Without a modifier, the caller uses `band_with(m)` to tell the user which band each modifier lands in, and cannot build an `Outcome` (it requires a band).

## Configuration

No configuration required — no environment variables, settings or `pyproject.toml` changes.

## Data Model

No persistence. In-memory types (all `@dataclass(frozen=True, slots=True)`):

```python
# backend/domain/rulebook.py
Stat = Literal["STR", "DEX", "CON", "INT", "WIS", "CHA", "BOND", "VARIES", "NONE"]
AbilityStat = Literal["STR", "DEX", "CON", "INT", "WIS", "CHA"]
Category = Literal["basic", "special", "class"]
STATS: tuple[Stat, ...]            # = get_args(Stat), declaration order
ABILITY_STATS: tuple[AbilityStat, ...]

class Outcomes:  strong_hit: str; weak_hit: str; miss: str | None
    def text_for(self, band: Band) -> str | None: ...
class Move:      id: str; name: str; category: Category; class_: str | None; stat: Stat | None
                 trigger: str; outcomes: Outcomes | None; body_markdown: str; section_id: str
    @property
    def is_rolled(self) -> bool: ...          # outcomes is not None
class Section:   id: str; chapter: str; title: str; slug: str; parent_id: str | None
                 order: int; text_markdown: str

def move_from_dict(data: Mapping[str, object]) -> Move: ...
def section_from_dict(data: Mapping[str, object]) -> Section: ...

# backend/domain/dice.py
Band = Literal["strong_hit", "weak_hit", "miss"]
BANDS: tuple[Band, ...]            # ("strong_hit", "weak_hit", "miss")
MIN_MODIFIER: Final = -10
MAX_MODIFIER: Final = 10

class RandomSource(Protocol):
    def randint(self, a: int, b: int, /) -> int: ...

def band_for_total(total: int) -> Band: ...
def band_label(band: Band) -> str: ...        # "10+" | "7-9" | "6-"
class Roll:      dice: tuple[int, int]; modifier: int | None
    @property
    def dice_total(self) -> int: ...          # dice[0] + dice[1]
    @property
    def total(self) -> int | None: ...        # dice_total + modifier, None if modifier is None
    @property
    def band(self) -> Band | None: ...        # band_for_total(total), None if modifier is None
    def band_with(self, modifier: int) -> Band: ...   # validates modifier range
def roll(rng: RandomSource, modifier: int | None = None) -> Roll: ...
    # two calls rng.randint(1, 6), in order → dice

# backend/domain/outcome.py
class Outcome:   move_id: str; roll: Roll; band: Band; text: str | None
def resolve_outcome(move: Move, roll: Roll) -> Outcome: ...
```

JSON ↔ type mapping is exactly spec 002 *Data Model* (`sections.json`, `moves.json`), with JSON key `class` ↔ field `class_`. `Outcome.text` is `move.outcomes.text_for(band)` — `None` only when `band == "miss"` and the move states no miss. `Outcome.band` equals `roll.band` (stored for convenience; invariant enforced).

## Impact on Existing Code

| Path | Action | Notes |
|------|--------|-------|
| `backend/domain/__init__.py` (new in 001) | unchanged | Stays empty (D17). |
| `backend/domain/rulebook.py` (new) | create | Rulebook types, vocabularies, parsers. |
| `backend/domain/dice.py` (new) | create | Bands, `RandomSource`, `Roll`, `roll`. |
| `backend/domain/outcome.py` (new) | create | `Outcome`, `resolve_outcome`. |
| `backend/tests/domain_helpers.py` (new) | create | `ScriptedRandom` and fixture dicts (see *Testing*). Not collected by pytest (no `test_` prefix). |
| `backend/tests/test_domain_dice.py` (new) | create | See *Testing*. |
| `backend/tests/test_domain_rulebook.py` (new) | create | See *Testing*. |
| `backend/tests/test_domain_outcome.py` (new) | create | See *Testing*. |
| `backend/tests/test_domain_purity.py` (new) | create | See *Testing*. |
| `docs/decisions.md` (new in 001) | modify — **additive** | Append one ADR (D16); existing ADRs untouched. |

No change to `pyproject.toml`, `uv.lock`, CI or any spec 001/002/004 file. Spec 001's `test_layer_package_is_importable` keeps passing (the package's `__init__.py` is untouched).

## Python Module Behaviour

**`rulebook.py`.** Each dataclass validates in `__post_init__` per *Validation Rules*. Parsers check, in order: input is a `Mapping`; key set equals the expected set exactly (message lists missing and unexpected keys); each value's runtime type (`str`, `int` not `bool`, `None` where allowed, nested mapping for `outcomes` with exactly `strong_hit`, `weak_hit`, `miss`); Literal membership via `TypeGuard` helpers (`is_stat`, `is_category`) so pyright strict narrows without `cast`; then construct the dataclass (which applies the invariants). `move_from_dict` errors name the move id when it is a string, else `'?'`.

**`dice.py`.** `roll` validates `modifier` before drawing (so an invalid modifier consumes no randomness), draws exactly two values with `rng.randint(1, 6)`, and builds `Roll`, whose `__post_init__` rejects any die outside 1–6. `band_label` returns `"10+"`, `"7-9"`, `"6-"`.

**`outcome.py`.** `resolve_outcome(move, roll)`:

| Condition | Result |
|-----------|--------|
| `move.outcomes is None` | `ValueError("cannot resolve move '<id>': it is not rolled")` |
| `roll.modifier is None` | `ValueError("cannot resolve move '<id>': modifier is required")` |
| otherwise | `Outcome(move.id, roll, roll.band, move.outcomes.text_for(roll.band))` |

`Outcome.__post_init__` enforces `roll.band is not None`, `band == roll.band`, and `text is None or text != ""`.

## Validation Rules

All failures raise `ValueError` (D11). Patterns: `SLUG = ^[a-z0-9]+(-[a-z0-9]+)*$`; `SECTION_ID = ^[a-z0-9]+(-[a-z0-9]+)*(/[a-z0-9]+(-[a-z0-9]+)*)?$` (spec 002 D5).

| Type / input | Field | Rule |
|--------------|-------|------|
| `Outcomes` | `strong_hit`, `weak_hit` | Non-empty after `strip()`. |
| `Outcomes` | `miss` | `None` or non-empty after `strip()`. |
| `Move` | `id` | Matches `SLUG`. |
| `Move` | `name`, `trigger` | Non-empty after `strip()`. |
| `Move` | `category` | In `Category`. |
| `Move` | `class_` | Non-empty string iff `category == "class"`; else `None`. |
| `Move` | `stat` | In `Stat` or `None`; `(stat is None) == (outcomes is None)`. |
| `Move` | `body_markdown` | `str` (may be empty). |
| `Move` | `section_id` | Matches `SECTION_ID`. |
| `Section` | `id` | Matches `SECTION_ID`. |
| `Section` | `chapter` | Matches `SLUG`. |
| `Section` | `title` | Non-empty after `strip()`. |
| `Section` | hierarchy | Either chapter section (`id == chapter == slug`, `parent_id is None`) or child (`id == f"{chapter}/{slug}"`, `parent_id` not `None` and matches `SECTION_ID`). |
| `Section` | `order` | `int`, not `bool`, `≥ 0`. |
| `Section` | `text_markdown` | `str` (may be empty). |
| `move_from_dict` / `section_from_dict` | keys | Exactly the spec 002 keys; values of the JSON types in spec 002 *Data Model*; `int` fields reject `bool`. |
| `roll` / `Roll` / `band_with` | `modifier` | `int` (not `bool`) in `[-10, 10]`, or `None` (not for `band_with`). |
| `Roll` | `dice` | Exactly two `int`s, each in `[1, 6]`. |
| `band_for_total` | `total` | Any `int`. |
| `Outcome` | — | See *Python Module Behaviour*. |

## Authorization & Security

Not applicable for access control — the domain has no users, endpoints or I/O. Security-relevant points: modifier bounds (D8) reject garbage tool arguments before spec 006 exposes `roll` to the LLM; the purity test (D13) keeps network/LLM code out of the layer; non-cryptographic RNG is acceptable because dice outcomes protect nothing.

## Testing

pytest, plain functions, files in `backend/tests/` (D15), offline and deterministic. Shared helpers live in `backend/tests/domain_helpers.py` (new): `ScriptedRandom` (returns a fixed sequence from `randint`, records the `(a, b)` arguments, fails the test if exhausted) and the move/section fixture dicts. Invalid-type and invalid-Literal cases go through `move_from_dict`/`section_from_dict` with modified fixture dicts, so tests need no `cast` or `pyright: ignore`, except the dice-arity case, which builds `Roll(dice=cast(tuple[int, int], (1, 2, 3)), modifier=None)`. Move/section fixtures are inline dicts copied from spec 002's *Expected results for the named moves* (Hack and Slash, Defy Danger, Volley, Discern Realities, Last Breath). Fields spec 002's contract omits are filled in like this: `name` is the move's display name ("Hack and Slash", "Defy Danger", "Volley", "Discern Realities", "Last Breath"); `class` is `None`; `section_id` is `moves/<id>`; `body_markdown` is the placeholder `"(body)"`, because the domain checks only that it is a `str`. The non-rolled fixture is `{"id": "make-camp", "name": "Make Camp", "category": "special", "class": None, "stat": None, "trigger": "When you settle in to rest", "outcomes": None, "body_markdown": "(body)", "section_id": "moves/make-camp"}`. The trigger text is synthetic, since only its shape matters. Non-ASCII text uses `\u2019`/`\u2013` escapes.

**`test_domain_dice.py`**
- `test_band_boundaries` — parametrized: 6→`miss`, 7→`weak_hit`, 9→`weak_hit`, 10→`strong_hit`.
- `test_band_for_every_reachable_total` — parametrized over totals −8…22: `strong_hit` iff ≥10, `weak_hit` iff 7–9, else `miss`.
- `test_band_for_extreme_totals` — −100→`miss`, 100→`strong_hit`.
- `test_band_label` — `strong_hit`→`10+`, `weak_hit`→`7-9`, `miss`→`6-`.
- `test_roll_uses_two_d6_draws_in_order` — `ScriptedRandom([3, 5])`: `dice == (3, 5)`, recorded calls `[(1, 6), (1, 6)]`.
- `test_roll_with_modifier_totals_and_bands` — parametrized: dice (3,3)+0 → 6 `miss`; (3,3)+1 → 7 `weak_hit`; (4,5)+0 → 9 `weak_hit`; (4,5)+1 → 10 `strong_hit`; (1,1)−3 → −1 `miss`; (6,6)+3 → 15 `strong_hit`.
- `test_roll_without_modifier_has_no_total_or_band` — `modifier is None`, `total is None`, `band is None`, `dice_total == 8` for (3,5).
- `test_band_with_reports_band_per_modifier` — dice (3,5): `band_with(-2)`→`miss`, `band_with(-1)`→`weak_hit`, `band_with(1)`→`weak_hit`, `band_with(2)`→`strong_hit`.
- `test_roll_band_matches_band_for_total_exhaustively` — for all 36 dice pairs × modifiers −10…10, a constructed `Roll` has `band == band_for_total(d1 + d2 + m)`.
- `test_modifier_out_of_range_rejected` — parametrized −11, 11 for `roll`, `Roll(...)`, `band_with` → `ValueError`; `roll` consumed no draws.
- `test_modifier_bounds_accepted` — −10 and 10 succeed.
- `test_bool_modifier_rejected` — `True` → `ValueError`.
- `test_die_out_of_range_rejected` — `ScriptedRandom([0, 3])` and `([3, 7])` → `ValueError`; `Roll(dice=(1, 2, 3)...)` (wrong arity) → `ValueError`.
- `test_seeded_rolls_are_reproducible` — two `random.Random(1234)` produce identical sequences of 50 `roll(...)` results.
- `test_seeded_rolls_cover_all_faces` — 1,000 rolls with `random.Random(7)`: every die in 1–6 and each face appears at least once.
- `test_random_random_works_as_random_source` — `roll(random.Random(0), 1)` returns a `Roll` with both dice in 1–6 and `total == dice_total + 1`. (That `random.Random` satisfies `RandomSource` statically is checked by `uv run pyright` over this call, see *Manual / CI*.)
- `test_roll_is_immutable` — assigning `roll.modifier` raises `dataclasses.FrozenInstanceError`.

**`test_domain_rulebook.py`**
- `test_named_moves_parse` — parametrized over the five spec 002 fixtures: every field equals the fixture (JSON `class` → `class_`), `outcomes` is an `Outcomes`.
- `test_last_breath_states_miss` / `test_hack_and_slash_miss_is_none` — `miss` text present / `None`.
- `test_extended_stats_parse` — `VARIES` (defy-danger), `NONE` (last-breath), and a `BOND` variant of a fixture all construct.
- `test_non_rolled_move_parses` — `make-camp` fixture: `stat is None`, `outcomes is None`, `is_rolled is False`.
- `test_rolled_move_is_rolled` — `hack-and-slash.is_rolled is True`.
- `test_outcomes_text_for_each_band` — returns `strong_hit`, `weak_hit`, `miss` texts per band.
- `test_stat_outcomes_consistency_enforced` — `stat="STR"` with `outcomes=None`, and `stat=None` with outcomes → `ValueError`.
- `test_class_field_consistency_enforced` — `category="class"` with `class_=None`; `category="basic"` with `class_="fighter"` → `ValueError`; `category="class", class_="fighter"` succeeds.
- `test_invalid_move_values_rejected` — parametrized, each via `move_from_dict` on a modified fixture: bad id (`"Hack and Slash"`), empty name, blank trigger, unknown stat (`"LUCK"`), unknown category, empty `strong_hit`, empty-string `miss`, bad `section_id` (`"moves/"`) → `ValueError` whose message contains the field name.
- `test_move_from_dict_rejects_missing_and_extra_keys` — dropping `trigger` and adding `"extra"` each raise `ValueError` naming the key.
- `test_move_from_dict_rejects_wrong_types` — `stat: 1`, `outcomes: "x"`, outcomes missing `miss` → `ValueError`.
- `test_sections_parse` — chapter section `{"id": "moves", "chapter": "moves", "title": "Moves", "slug": "moves", "parent_id": None, "order": 4, "text_markdown": ""}` and child `{"id": "moves/hack-and-slash", "chapter": "moves", "title": "Hack and Slash", "slug": "hack-and-slash", "parent_id": "moves", "order": 6, "text_markdown": "(body)"}` construct with every field equal to the input.
- `test_section_hierarchy_enforced` — chapter section with a parent; child with `parent_id=None`; child whose id ≠ `chapter/slug`; chapter section whose slug ≠ id → `ValueError`.
- `test_section_order_rules` — `order=-1` and `order=True` → `ValueError`; `text_markdown=""` accepted.
- `test_section_from_dict_rejects_missing_and_extra_keys` — as for moves.
- `test_vocabularies` — `STATS` has the 9 values in declaration order; `ABILITY_STATS` the 6; `BANDS` the 3.
- `test_committed_moves_json_parses` — if `data/normalized/moves.json` exists, every element parses with `move_from_dict` and the ids include the five named moves; otherwise `pytest.skip("spec 002 output not present")`.
- `test_committed_sections_json_parses` — same for `sections.json` with `section_from_dict`; every move's `section_id` is among the parsed section ids when both files exist.

**`test_domain_outcome.py`**
- `test_resolve_strong_weak_miss` — parametrized on hack-and-slash with scripted dice: (5,5)+0 → `strong_hit` with the 10+ text; (3,4)+0 → `weak_hit` text; (1,2)+0 → `miss`, `text is None`.
- `test_resolve_stated_miss` — last-breath, (1,1)+0 → `miss`, text equals its miss string.
- `test_resolve_requires_modifier` — `Roll` with `modifier=None` → `ValueError` containing `modifier is required`.
- `test_resolve_rejects_non_rolled_move` — make-camp → `ValueError` containing `not rolled`.
- `test_outcome_text_is_verbatim` — `outcome.text is move.outcomes.strong_hit` (same object, nothing regenerated).
- `test_outcome_invariants` — `Outcome` with `band != roll.band`, or with a roll lacking a band, or `text=""` → `ValueError`.

**`test_domain_purity.py`**
- `test_domain_imports_are_pure` — AST-parse every `backend/domain/*.py`; every `import`/`from` module (relative imports resolved to `backend.domain`) is in the D13 allow-list; failure message names file and module. Asserts `dice.py` is among the scanned files (cannot pass vacuously; holds from story 1 onward, and later modules are picked up automatically by the glob).

**Manual / CI:** `uv run ruff format --check .`, `uv run ruff check .`, `uv run pyright` (strict, zero errors) and `uv run pytest` exit 0.

## Documentation

Append to `docs/decisions.md` (spec 001 D15 format, `Status: Accepted`): **ADR-NNN: Domain layer — stdlib types, mirrored ingestion shapes, injected dice randomness** (number per D16), content from D1, D2, D3, D5, D7, D8, D9. It must state the band rule (`≥10` / `7–9` / `≤6`), the modifier range `-10…+10`, and that the LLM never produces dice values — only `backend.domain.dice.roll` does.

## Suggested Story Breakdown

1. **Dice resolution** — `dice.py`, `domain_helpers.py` (`ScriptedRandom` only), `test_domain_dice.py`, `test_domain_purity.py`. Verifiable: band tests and seeded tests pass; pyright strict clean. Depends on spec 001.
2. **Rulebook types and parsers** — `rulebook.py`, fixture dicts added to `domain_helpers.py`, `test_domain_rulebook.py` (committed-JSON tests skip until spec 002 lands). Depends on 1 (`Band` used by `Outcomes.text_for`).
3. **Outcome resolution and ADR** — `outcome.py`, `test_domain_outcome.py`, ADR append. Depends on 1–2.

## Success Criteria

- [ ] Every test in *Testing* exists and passes with `uv run pytest`; the two committed-JSON tests pass (not skip) once spec 002's output is committed.
- [ ] `uv run ruff format --check .`, `uv run ruff check .`, `uv run pyright` exit 0 with no new per-file ignores or `pyright: ignore` comments in `backend/domain/`.
- [ ] `backend/domain/` imports only the D13 allow-list (`test_domain_imports_are_pure` green).
- [ ] `pyproject.toml` and `uv.lock` are unchanged by this spec.
- [ ] `docs/decisions.md` contains the new ADR stating the band rule and modifier range.

## Future Considerations

- `pytest-cov` with `--cov=backend/domain --cov-fail-under=100` to turn "full coverage" into a gate (D14).
- A helper mapping a `Move` plus classifier output to the modifier source (ability vs Bond vs none) once spec 006 settles the roll-tool arguments.
- Domain types for classes (`classes.json`) when a backend consumer appears.
