# 010 - Model tuning round

**Status:** spec — ready for story-creator.
**Depends on:** 009 (runner, `evals/configs/*.toml` format, report JSON `schema_version` 1, R-LABEL, `Makefile`, `evals/README.md`), 007 (`MODEL_*` env routing, provider ADR with provisional models), 006 (`GraphSettings`), 001 (ADR format, D15). **Start condition:** no story of this spec starts before spec 009's owner gate is complete, meaning the datasets are reviewed and the first baseline report is committed (D2).
**Reference:** `HANDOFF_dw-companion.md` sections 4.2, 6.3, 10 (milestone 9).

## Feature Name & Description

**Configuration comparison tooling and the tuning-round procedure.** This spec adds a second eval config (`classifier-mini`), an offline `evals/compare.py` CLI and a `make compare` target. The CLI reads two to four spec 009 report JSON files, checks that they are comparable, and writes one Markdown comparison: provenance, the settings that differ, a README-ready results table (accuracy deltas next to cost and latency deltas), and per-case flips. It also documents the owner procedure for running the configs, choosing one and recording the choice as an ADR. The value: this produces the "measure before you trust" evidence that handoff 4.2/6.3 ask for in `docs/decisions.md`, and the comparison table that spec 012 pastes into the README.

**Current state.** Nothing is implemented. Specs 001–009 are approved but not built, so paths marked "(new in 00N)" come from those specs and do not exist on disk yet. Spec 009's datasets hold only candidate rows with `"reviewed": false`. Under R-LABEL, the runner refuses to run on them (exit `3`), so no real report exists and none can exist until the owner has reviewed the datasets.

**What this spec's stories deliver, and what they do not.** The stories deliver tooling, a candidate config, documentation and templates, all verified offline with fixture reports. They **do not** produce a populated comparison. They also do not choose a configuration or write the tuning ADR, and no eval number appears in `docs/decisions.md` or `README.md`. The real comparison, the choice and the ADR are **owner-gate steps** (*Owner Procedure*). They run only after the owner has reviewed the datasets and both configs have been run for real. **No-fabrication rule:** no story may write an invented, estimated or placeholder eval number into any committed file. That includes `README.md`, `evals/README.md`, `docs/decisions.md`, anything under `evals/reports/` (including `comparisons/`) and anything under `evals/datasets/`. Test fixtures are the only exception, and only under the fixture rule in *Testing*: written to `tmp_path`, never committed as data, and obviously synthetic.

**In scope.**
- The `evals/configs/classifier-mini.toml` candidate config.
- `evals/compare.py` (loader, comparability checks, metric extraction, Markdown rendering, CLI) and its tests.
- The `make compare` target.
- The tuning procedure, the decision guidance and the ADR template in `evals/README.md`, plus one line in the README.

**Out of scope.**
- Re-running, editing or re-labelling datasets (spec 009 and the owner).
- Changing `GraphSettings` defaults or making them configurable in production (D4).
- Deployment env values (spec 011) and the final README results section (spec 012).
- Any change to the runner or the report schema.

## Assumptions & Decisions

| # | Decision | Reasoning / precedent |
|---|----------|-----------------------|
| D1 | **Stories deliver tooling only. The comparison, the choice and the ADR are owner-gate steps.** Story verification uses fixture reports written by tests in `tmp_path`. No story commits a file under `evals/reports/` or adds the tuning ADR. | Spec 009 R-LABEL point 4: no number may appear in `docs/decisions.md` or the README before owner review. Real numbers need reviewed datasets and paid runs, and the caller explicitly ruled out fabricated numbers. This mirrors spec 009, which built the runner and left "first committed report" as an owner item. |
| D2 | **Every story of this spec starts only after spec 009's owner gate is complete.** That means all spec 009 stories are built, the owner has reviewed every dataset row, and the first baseline report is committed. This spec does not amend spec 009. The tooling stories make no paid call and produce no number, but they still wait. | Spec 009 R-LABEL point 4 is binding on every later spec: "Spec 010 must not start … before the owner has reviewed the datasets and run the first report". Spec 009's story breakdown and success criteria repeat this. |
| D3 | **The comparison is report-to-report, not a run orchestrator.** The owner runs `make eval` once per config (spec 009 CLI, unchanged), then `make compare` on the two JSON reports. There is no script that runs both configs. | Each run is a paid, budget-guarded call that the owner should start deliberately (handoff 12). Comparing committed reports keeps every number traceable to a file with config and dataset SHA-256 hashes (spec 009 D19). The comparison step stays free, offline and fully testable. |
| D4 | **The shipped candidate varies models only. Adoption is applied only through `MODEL_*` env values.** `classifier-mini.toml` equals `baseline.toml` except `classifier = "openai/gpt-4.1-mini"`. The compare tool accepts reports that differ in `[graph]`, and shows those differences, but a `[graph]`-varying winner cannot be adopted under this spec. | Handoff 6.3's example is "small vs large classifier model". Spec 007 D26 builds production `GraphSettings()` with no overrides, so a different `retrieval_k` or `clarify_threshold` would need a code change in the composition root. That change is outside the draft's scope (*Future Considerations*). A model-only change needs no code at all. |
| D5 | **`classifier-mini` changes only the classifier, not the router.** | It isolates a single variable, so the move-accuracy delta is attributable. The router has its own 40-row dataset and can be the subject of a later round. |
| D6 | **Comparability is enforced, not advised.** Every report must be `schema_version` 1 with `status: "completed"` and `labels.all_rows_reviewed: true`. All reports must use the **same judge model**. Each dataset present in every report must have the **same SHA-256** in all of them. At least one dataset must be shared. Violations exit `2`. Different `git_commit` values are allowed but flagged in the output. | Key-fact coverage from different judges is not comparable (spec 009 D5). Different label files make every delta meaningless. Re-checking `all_rows_reviewed` is defence in depth for R-LABEL. Code may legitimately differ between runs, but the reader must be told. |
| D7 | **Only datasets present in every report are compared.** Datasets present in only some reports are listed as skipped in *Notes*. | A `--dataset router` run is a valid, cheaper comparison. Mixing partial and full runs must not silently drop metrics. |
| D8 | **The first report given is the reference.** Every other report gets a Δ column against it. 2–4 reports are accepted (`MIN_REPORTS = 2`, `MAX_REPORTS = 4`). | Handoff asks for "two or three configurations". Four columns plus deltas is the readability limit of a README table. |
| D9 | **Headline metrics are a fixed list** (*Comparison Output*). They are taken from each report's `metrics`. Cost per query and latency are recomputed from `cases[]` over the shared datasets with spec 009's `metrics.percentile`. | These are the handoff 6.2 metrics that move with a model change. Spec 009 reports system metrics per dataset only, while a comparison needs one cross-dataset cost-per-query and latency number per config. Recomputing from the cases (judge excluded, as in spec 009) keeps the definitions identical. |
| D10 | **The comparison shows per-case flips** for router and move classification: the ids correct only in the reference and the ids correct only in the candidate. It also states the size of one case in percentage points for each rate row. | With 40–80 cases, one case is 1.25–2.5 pp, so a small delta may be noise. Flips let the owner check whether a delta comes from a consistent shift or from one or two cases. This uses only report data (`cases[].correct`). |
| D11 | **Output is a Markdown file only**, at `evals/reports/comparisons/<YYYY-MM-DD>-<label1>-vs-<label2>[-vs-…].md`. The date is the UTC date at comparison time. On a collision the suffix `-2`, `-3`… is added (spec 009 D12 rule). The directory is created on demand. The owner commits the file used by the ADR. There is no `--output` flag. | Nothing consumes a JSON comparison. A deterministic path mirrors spec 009's report naming. Committing the file is the owner's act, as for reports (spec 009 D12). |
| D12 | **The README-ready table sits between the markers `<!-- comparison-table:start -->` and `<!-- comparison-table:end -->`.** | Spec 012 and the ADR paste exactly this block. The markers make the copy unambiguous. |
| D13 | **Column labels are config names.** If two reports share a config name, both columns become `<name>-<first 6 hex of run_id>`. | This allows comparing two runs of the same config to measure run-to-run noise, and keeps labels filename-safe (D11). |
| D14 | **Decision guidance, stated in advance and not enforced in code.** Keep the cheaper config unless the more expensive one meets all of these: (a) the metric its change targets improves by more than 2 cases' worth (for `classifier-mini`: move accuracy, more than 2 × (100/n) pp); (b) on the dataset of that targeted metric (for `classifier-mini`: `move_classification`), candidate-only flips exceed reference-only flips by at least 3; (c) no other headline rate regresses by more than 2 cases' worth. These thresholds are final unless the owner changes them in writing in `evals/README.md` before running the tuning round. The owner may also override the outcome, and the ADR must then give the reason. | Writing the rule before seeing the numbers limits post-hoc rationalising. The thresholds come from D10's case granularity. |
| D15 | **The tuning ADR is written from a template in `evals/README.md`** in spec 001 D15 format. It is numbered with the next free number when the owner adds it (spec 009 D20). It records the compared configs, report and comparison paths, the pasted table, the choice, and the D14 outcome or the override reason. It states that it replaces the provisional model values of spec 007's provider ADR ("Model provider: OpenRouter for chat and embeddings"). That ADR is **not** marked superseded, because its provider decision stands. | Handoff 4.2: record "which models were chosen and why, with the eval numbers". The spec 001 convention marks only whole entries as superseded. |
| D16 | **`evals/configs/baseline.toml` is not modified.** Its comment says "spec 010 replaces them with measured ones". The tuning ADR and `.env` values are where that replacement happens. | Editing the file would change its SHA-256, so the owner's committed baseline report would no longer match the file it names. The stale comment is cosmetic. |
| D17 | **No tooling ADR is added by the stories.** | The tooling decisions are recorded here and in `evals/README.md`. Milestone 9's ADR is the model choice itself (owner gate). Adding a process ADR with no numbers would duplicate it. |
| D18 | **`compare.py` imports only the stdlib, `evals.datasets` (`DATASET_ORDER`, `DatasetName`) and `evals.metrics` (`percentile`, `JsonValue`).** It makes no network call and needs no env. | It stays usable offline and in CI tests. Spec 009's `test_evals_import_no_vendor_sdks` covers it automatically. |

**Open risks.**
- (a) **Small samples.** On 40–80 cases, real differences under about 5 pp cannot be told apart from noise. D10 and D14 make this visible but cannot remove it. The ADR template asks the owner to state the flip counts.
- (b) **LLM run-to-run variance.** Temperature is 0 (spec 006 D25), but provider outputs are not guaranteed deterministic. The procedure recommends running both configs on the same commit and the same day. Comparing two runs of the same config (D13) measures this variance if the owner wants it.
- (c) **The spec 009 report shape is the contract.** `compare.py` depends on the key names in spec 009's *Report JSON* and *Metrics*. `test_compare_end_to_end_on_runner_reports` builds reports with spec 009's real `main` and fakes, so a schema drift fails that test.
- (d) **Model availability and price drift.** `openai/gpt-4.1-mini` was listed on OpenRouter on 2026-11-05 (spec 007 D13). If it is delisted before the owner runs, the runner's price lookup exits `2` (spec 009 D10) and the owner must pick another larger classifier and record it in the ADR.

## Architecture / Design Overview

`evals/compare.py` is a pure, offline consumer of spec 009 report files. It never touches the runtime, datasets or network. The runner and the report schema are unchanged.

```
owner (after spec 009 owner gate)
  make eval CONFIG=baseline          ─▶ evals/reports/<d>-baseline.json        (spec 009, paid, R-LABEL, budget guard)
  make eval CONFIG=classifier-mini   ─▶ evals/reports/<d>-classifier-mini.json
  make compare REPORTS="<ref.json> <cand.json>"
        evals/compare.py main
          1 args: 2..4 paths                                   ── exit 2
          2 load_report each: JSON, schema_version 1, completed, all_rows_reviewed   ── exit 2
          3 check_comparable: same judge, shared datasets, equal dataset sha256      ── exit 2
          4 headline_rows (metrics + cases[]) ; case_flips ; config_diff
          5 render_comparison ─▶ evals/reports/comparisons/<date>-baseline-vs-classifier-mini.md
  owner reads it, applies D14, commits reports + comparison, appends ADR (template), sets MODEL_* in .env
```

## Configuration

**Environment variables.** None added. `.env.example` is unchanged; its `MODEL_*` values stay empty (spec 001 rule). After the owner gate, the chosen ids go into the owner's local `.env` and into the deploy env, which is spec 011's concern (D4).

**`evals/configs/classifier-mini.toml`** (new, exact content):

```toml
# Tuning-round candidate (spec 010): identical to baseline.toml except a larger classifier model.
# The judge must stay identical to baseline so key-fact coverage is comparable.
[models]
router = "openai/gpt-4.1-nano"
classifier = "openai/gpt-4.1-mini"
answer = "openai/gpt-4.1-mini"
embeddings = "openai/text-embedding-3-small"
judge = "anthropic/claude-haiku-5.5"

[graph]
retrieval_k = 6
clarify_threshold = 0.6
```

**`Makefile`** (new in 009) gains a target (recipe line uses a tab). The existing `eval` target and variables are untouched:

```make
.PHONY: compare
compare:
	uv run python -m evals.compare $(REPORTS)
```

`compare` needs no `.env` because it is offline. An empty `REPORTS` reaches argparse and exits `2`.

**Constants** (`evals/compare.py`): `MIN_REPORTS = 2`, `MAX_REPORTS = 4`, `MAX_FLIP_IDS = 20`, `TABLE_START = "<!-- comparison-table:start -->"`, `TABLE_END = "<!-- comparison-table:end -->"`, `REPO_ROOT = Path(__file__).resolve().parent.parent`, `DEFAULT_COMPARISONS_DIR = REPO_ROOT / "evals/reports/comparisons"`.

**CLI.** `uv run python -m evals.compare REPORT REPORT [REPORT ...]`. Positional report paths (relative to cwd or absolute); the first is the reference. Stdout on success: `compare: wrote <path relative to cwd, or absolute if outside it>`. Errors go to stderr as `compare: error: <message>`. Exit codes: `0` written; `2` usage, unreadable or invalid report, or incomparable reports.

**Budget.** No change. With baseline prices, spec 009 estimates about $1.05 per full run. `classifier-mini` raises only the classifier's price, so both full runs together stay well under twice the default `--budget-usd 3.00`.

## Data Model

No database and no report schema change. `LoadedReport`, `MetricRow` and `CaseFlips` are `@dataclass(frozen=True, slots=True)` (spec 005 D11). They are built only by this module, so they need no `__post_init__` validation. `ComparisonError` is a plain exception.

```python
# evals/compare.py
class ComparisonError(Exception): ...                       # message is the user-facing text after "compare: error: "

class LoadedReport:
    path: Path; label: str                                  # label set by assign_labels (D13)
    data: Mapping[str, JsonValue]                           # the parsed report

def load_report(path: Path) -> Mapping[str, JsonValue]: ...                     # ComparisonError (Validation Rules)
def assign_labels(paths: Sequence[Path], reports: Sequence[Mapping[str, JsonValue]]) -> tuple[LoadedReport, ...]: ...
def check_comparable(reports: Sequence[LoadedReport]) -> tuple[tuple[DatasetName, ...], tuple[DatasetName, ...]]: ...
    # (shared datasets in DATASET_ORDER, skipped datasets in DATASET_ORDER); ComparisonError

Unit = Literal["rate", "usd", "ms"]
class MetricRow:
    label: str; unit: Unit
    cases: int | None                                       # "Cases" column; None renders "—"
    values: tuple[float | None, ...]                        # one per report, reference first

def headline_rows(reports: Sequence[LoadedReport], shared: Sequence[DatasetName]) -> tuple[MetricRow, ...]: ...
def format_value(unit: Unit, value: float | None) -> str: ...
def format_delta(unit: Unit, reference: float | None, value: float | None) -> str: ...

class CaseFlips:
    dataset: DatasetName                                    # "router" or "move_classification" only
    reference_only: tuple[str, ...]                         # ids correct in reference, incorrect in candidate (file order)
    candidate_only: tuple[str, ...]

def case_flips(reference: LoadedReport, candidate: LoadedReport, dataset: DatasetName) -> CaseFlips: ...
def config_diff(reports: Sequence[LoadedReport]) -> tuple[tuple[str, tuple[str, ...]], ...]: ...
    # ("models.classifier", (value per report)) for each models.* / graph.* key whose values are not all equal;
    # models keys in spec 009 order, then graph keys sorted; values rendered with str()
def render_comparison(reports: Sequence[LoadedReport], shared: Sequence[DatasetName],
                      skipped: Sequence[DatasetName], generated_at: datetime) -> str: ...
def comparison_path(comparisons_dir: Path, date: str, labels: Sequence[str]) -> Path: ...   # D11 suffixing
def main(argv: Sequence[str] | None = None, *, comparisons_dir: Path = DEFAULT_COMPARISONS_DIR,
         now: Callable[[], datetime] = <UTC now>) -> int: ...
```

`if __name__ == "__main__": raise SystemExit(main())`.

## Comparison Output

`render_comparison` writes these sections, in this order (Markdown, LF, trailing newline). `<L1>`, `<L2>`… are report labels and the first is the reference.

1. `# Eval comparison: <L1> vs <L2>[ vs <L3>…]`
2. `Generated <generated_at ISO 8601 UTC> by \`evals/compare.py\`. Reference: \`<L1>\`.`
3. `## Reports` — a table `| Config | Report | Run id | Started (UTC) | Git commit | Eval spend |`. Report = the path as given. Git commit = first 12 chars, or `n/a`. Eval spend = `budget.spent_usd` formatted `$x.xxxx`. If the reports' `git_commit` values are not all equal (including any `null`), add a line after the table: `**Note:** reports come from different commits; deltas may include code changes, not only configuration.`
4. `## Configurations` — a table `| Setting | <L1> | <L2> … |` with one row per `config_diff` entry, each value in backticks. If there are no entries: `No setting differs: these are repeated runs of the same configuration.`. Then always the line `Judge (identical in all reports): \`<judge>\`.`
5. `## Results` — `TABLE_START`, the table, `TABLE_END`, each on its own line. Header: `| Metric | Cases | <L1> | <L2> | Δ |` for two reports; for three or four, each non-reference value column is followed by `Δ <Lk>`. Rows follow, in this order, **only those whose dataset is shared** (cost and latency rows are always present):

   | Row label | Unit | Value source (per report) | Cases |
   |-----------|------|---------------------------|-------|
   | Router accuracy | rate | `datasets.router.metrics.accuracy` | router `metrics.n` |
   | Retrieval recall@`k` | rate | `rules_qa.metrics.recall_at_k` | `answerable_n` |
   | Citation validity | rate | `rules_qa.metrics.citation_validity_rate` | rules `n` |
   | Key-fact coverage | rate | `rules_qa.metrics.key_fact_coverage` | `answerable_n` |
   | Correct refusals | rate | `rules_qa.metrics.correct_refusal_rate` | `unanswerable_n` |
   | Move accuracy | rate | `move_classification.metrics.accuracy` | move `n` |
   | `no_move` precision | rate | `…no_move_precision` | `—` |
   | `no_move` recall | rate | `…no_move_recall` | count of reference `cases[]` with `expected_move_id == "no_move"` |
   | Clarification rate | rate | `…clarification_rate` | move `n` |
   | Cost per query | usd | mean of non-null `cases[].cost_usd` over all shared datasets; `None` if none | total shared cases |
   | Cost per rules question | usd | same, restricted to `cases[].intent == "rules_question"` | reference count of those cases |
   | Cost per action description | usd | same, `intent == "action_description"` | reference count |
   | Latency p50 | ms | `percentile(all shared cases[].latency_ms, 50)` | total shared cases |
   | Latency p95 | ms | `percentile(…, 95)` | total shared cases |

   The recall label shows the reference's `retrieval_k` (e.g. `Retrieval recall@6`). If the reports' `retrieval_k` values differ, the label is `Retrieval recall@k (k differs, see Configurations)`. `Cases` values come from the reference report.

   Formatting (`format_value` / `format_delta`):

   | Unit | Value | Δ | Example |
   |------|-------|---|---------|
   | rate | `f"{v*100:.1f}%"` | `f"{d*100:+.1f} pp"` | `87.5%`, `+2.5 pp` |
   | usd | `f"${v:.5f}"` | sign, `$`, `f"{abs(d):.5f}"`, then ` ({d/ref*100:+.0f}%)` unless `ref == 0` | `$0.00125`, `+$0.00040 (+32%)`, `-$0.00010 (-8%)` |
   | ms | `f"{v:.0f} ms"` | `f"{d:+.0f} ms"` | `1840 ms`, `-120 ms` |

   `None` renders `n/a`. A Δ where either side is `None` renders `n/a`. A zero usd delta renders `+$0.00000`. The examples illustrate formatting only; they are not results.
6. `## Changed cases` — for each shared dataset among `router` and `move_classification`, and for each non-reference report, a `### <dataset>: <L1> vs <Lk>` heading followed by two lines: `Correct only in <L1> (<count>): <ids comma-separated>` and `Correct only in <Lk> (<count>): …`. Ids are capped at `MAX_FLIP_IDS`, followed by `, … and N more`; zero ids render `none`. Cases are matched by `id`, and an id missing from either report is ignored. If neither dataset is shared: `No router or move cases to compare.`
7. `## Notes` — bullet lines:
   - `Datasets compared: <comma list>.` and, if any, `Skipped (not in every report): <comma list>.`
   - For each shared dataset: `<dataset>: <rows> cases; one case = <100/rows:.1f> pp.` (rows from the reference's `datasets.<name>.rows`).
   - If any report has `rules_qa.metrics.judge_errors > 0`: `Judge errors (excluded from key-fact coverage): <L>: <n>, …`.
   - Always: `Differences of one or two cases are within run-to-run noise; check Changed cases before attributing a delta to the configuration.`

## Owner Procedure

This section is reproduced in `evals/README.md` under `## Tuning round`. The procedure happens after story 2, and so after spec 009's owner gate (D2). No step is performed by a story.

1. Make sure the datasets are reviewed (spec 009 R-LABEL) and committed, and the working tree is clean.
2. On one commit, on the same day: `make eval CONFIG=baseline` and `make eval CONFIG=classifier-mini`. Both must exit `0`.
3. `make compare REPORTS="evals/reports/<date>-baseline.json evals/reports/<date>-classifier-mini.json"`.
4. Read *Changed cases*. Spot-check a few flipped cases in Langfuse (session id = the report's `run_id`).
5. Apply the decision guidance (D14) and note the outcome, or your override and its reason.
6. Commit both reports and the comparison file: `chore(evals): tuning round <date>`.
7. Append the ADR from the template below to `docs/decisions.md`, pasting the block between the comparison markers verbatim.
8. Set the chosen `MODEL_*` values in your local `.env`, and use them for deployment (spec 011). `.env.example` stays empty.

**ADR template** (in `evals/README.md`, verbatim except the angle-bracket placeholders, which the owner fills from the real files; spec 001 D15 format):

```markdown
## ADR-<NNN>: Model configuration from the tuning round

Date: <YYYY-MM-DD>
Status: Accepted

### Context
Spec 007 shipped provisional model choices. The tuning round compared `<reference>` and `<candidate>` on the owner-reviewed eval datasets (<dataset>: sha256 <first 12 hex>, …) at commit <short sha>. Reports: `<json paths>`. Comparison: `<comparison path>`.

### Decision
Use `<chosen config>`: router `<id>`, classifier `<id>`, answer `<id>`, embeddings `<id>`; `GraphSettings` at defaults.

<paste the comparison table block, markers included>

Decision guidance (spec 010 D14): <met / not met, with the flip counts>. <Override reason, if any.>

### Consequences
- Replaces the provisional model values in ADR-<provider ADR number> ("Model provider: OpenRouter for chat and embeddings"); its provider decision stands.
- `MODEL_*` for local runs and deployment use the values above; `.env.example` stays empty.
- Re-run the round when a dataset changes, a model is delisted or repriced, or the graph changes.
```

## Impact on Existing Code

| Path | Action | Notes |
|------|--------|-------|
| `evals/compare.py` (new) | create | *Data Model*, *Comparison Output*. |
| `evals/configs/classifier-mini.toml` (new) | create | *Configuration*. |
| `evals/tests/test_compare.py` (new) | create | *Testing*. |
| `evals/tests/test_config.py` (new in 009) | modify — **additive** | One new test (*Testing*); spec 009 tests untouched. |
| `Makefile` (new in 009) | modify — **additive** | `compare` target with its own `.PHONY` line; `eval` target, `CONFIG`, `DATASET`, `BUDGET` unchanged. |
| `evals/README.md` (new in 009) | modify — **additive** | New `## Tuning round` section: *Owner Procedure*, D14 guidance, the ADR template, and the note that the stories did not produce a comparison. Existing sections, including R-LABEL, unchanged. |
| `README.md` (new in 001; extended by 004, 007, 009) | modify — **additive** | In `### Running evals` (spec 009), append one sentence: compare two committed reports with `make compare REPORTS="<ref.json> <candidate.json>"`; the procedure is in `evals/README.md`. No numbers. `## Attribution` untouched. |
| `evals/reports/comparisons/` (new) | created at runtime | Not created by the stories, and no `.gitkeep`. The owner commits comparison files at the owner gate. |
| `docs/decisions.md` (new in 001) | **unchanged by the stories** | The tuning ADR is appended at the owner gate (D1, D15, D17). |
| `evals/configs/baseline.toml` (new in 009) | unchanged | D16. |

No change to `evals/run.py`, `evals/report.py`, `evals/metrics.py`, `evals/datasets.py`, the report schema, `evals/datasets/*.jsonl` (all new in 009), `.github/workflows/*`, `backend/`, `.env.example` or `pyproject.toml` (new in 001–009). `compare.py` imports only `DATASET_ORDER`/`DatasetName` and `percentile`/`JsonValue`, all spec 009 public names used read-only. No existing contract changes, so there are no regression paths into the runner, the API or CI.

## Validation Rules

| Subject | Field / input | Rule | Failure (exit 2, stderr `compare: error: …`) |
|---------|---------------|------|----------------------------------------------|
| CLI | positional reports | `MIN_REPORTS ≤ count ≤ MAX_REPORTS` | argparse usage error, or `expected 2 to 4 report files, got <n>` |
| CLI | each path | Exists and is a file | `<path>: no such report file` |
| Report | file | UTF-8 JSON object | `<path>: not valid JSON` |
| Report | `schema_version` | Exactly `1` | `<path>: unsupported report schema_version <v>` |
| Report | `status` | `"completed"` | `<path>: report status is <status>; only completed runs can be compared` |
| Report | `labels.all_rows_reviewed` | Exactly `true` | `<path>: report is not based on fully reviewed datasets` |
| Report | structure | `run_id` str; `started_at` str; `git_commit` str or null; `config.name` str; `config.models` object with the five spec 009 keys as str; `config.graph` object; `budget.spent_usd` number; `datasets` non-empty object whose keys are in `DATASET_ORDER`, each with `sha256` str, `rows` int, `metrics` object, `cases` list of objects with `id` str, `intent` str, `latency_ms` number, `cost_usd` number or null | `<path>: not a spec 009 report (<first problem, dotted key path>)` |
| Comparability | `config.models.judge` | Equal in all reports | `reports use different judge models (<L>: <id>, …); key-fact coverage is not comparable` |
| Comparability | shared datasets | At least one dataset present in all reports | `no dataset is present in every report` |
| Comparability | `datasets.<shared>.sha256` | Equal in all reports | `<dataset> labels differ between reports (sha256 <12 hex> vs <12 hex>); re-run on the same dataset files` |
| Metric values | any read metric | Number or null. A missing key or wrong type is a structure error | as structure row |

Check order in `main`: arguments, then each report in argument order (existence, JSON, schema version, status, labels, structure), then comparability (judge, shared datasets, hashes). The first failure stops the run, and no file is written.

`main` derives the date from `now()`, which must be timezone-aware UTC.

## Authorization & Security

There are no users or endpoints. `compare.py` reads local JSON with `json` only (no `eval`, no pickle) and writes one Markdown file under `evals/reports/comparisons/`. It needs no secrets and makes no network call (enforced in tests by the socket guard in `evals/tests/conftest.py`, new in 009). Reports contain no secrets (spec 009), so the comparison contains none either. Paid calls stay confined to the spec 009 runner and its budget guard. Label integrity: comparison refuses reports not marked `all_rows_reviewed` (D6), and dataset hashes are checked across reports.

## Testing

pytest, plain functions, in `evals/tests/` (spec 009 D16), with no env vars and no network. Report fixtures are dicts built by a local builder in `test_compare.py`, `report(config="a", *, judge="m-judge", models=None, graph=None, datasets=None, git_commit="c0ffee", run_id=…)`. It produces the spec 009 shape.

**Fixture rule.** The builder's default metric values are fixed and obviously synthetic: every rate is `0.11`, every USD value `0.000111` and every latency `111.0`. A test overrides only the specific values it asserts on. Overrides use round, non-realistic values such as `0.5`, `0.25` or `0.99`, or the exact values listed in that test. The builder's docstring states: `Synthetic test data; these values are not eval results and must never be copied into docs or reports.` Fixtures are written only to `tmp_path` with `json.dumps`. No fixture is written under `evals/reports/` or `evals/datasets/`, and none is committed as a data file.

**`evals/tests/test_compare.py`**
- `test_load_report_errors`, parametrized: missing file, invalid JSON, `schema_version: 2`, `status: "aborted_budget"`, `all_rows_reviewed: false`, missing `datasets`, `cases[0].latency_ms` a string → `ComparisonError` with the documented message prefix.
- `test_rejects_different_judge`.
- `test_rejects_dataset_sha_mismatch`: the message names the dataset and both 12-hex prefixes.
- `test_rejects_no_shared_dataset`: one router-only and one rules-only report.
- `test_shared_and_skipped_datasets_in_order`: a full report and a router + move report → shared `(router, move_classification)`, skipped `(rules_qa,)`; *Notes* lists the skipped one and the result table has no rules rows.
- `test_headline_rows_values_and_cases`: values and `Cases` per row match the fixture metrics, including the `no_move` recall count from `cases[]` and `—` for `no_move` precision.
- `test_cost_and_latency_recomputed_from_cases`: null `cost_usd` cases are excluded from cost means; cost per intent covers only the shared datasets; latency p50/p95 equal `metrics.percentile` over all shared cases; all-null cost → `n/a`.
- `test_format_value_and_delta`, parametrized: rate `0.875` → `87.5%`, delta `+0.025` → `+2.5 pp`; usd reference `0.00085`, value `0.00125` → `+$0.00040 (+47%)`; negative usd delta; reference `0` → no percentage; ms; `None` on either side → `n/a`.
- `test_recall_label_uses_k_or_flags_difference`.
- `test_case_flips_router_and_move`: matched by id, file order kept, more than 20 ids → `… and N more`, zero → `none`.
- `test_config_diff_lists_only_differing_settings`: baseline vs classifier-mini fixtures → exactly one row, `models.classifier`; identical configs → the "repeated runs" sentence.
- `test_duplicate_config_names_get_run_id_suffix` (D13), with the labels used in the file name.
- `test_three_reports_have_delta_column_per_candidate`.
- `test_table_markers_appear_once_and_wrap_table`: exactly one `TABLE_START` and one `TABLE_END`, and every line between them starts with `|`.
- `test_different_commits_note`: shown when commits differ (including `null`), absent when equal.
- `test_judge_errors_note`.
- `test_cli_report_count_bounds`, parametrized over 1 and 5 report paths → exit `2`, no file written.
- `test_cli_writes_comparison_and_suffixes_on_collision`: two runs with the same fixed `now` → `<date>-a-vs-b.md`, then `<date>-a-vs-b-2.md`; stdout `compare: wrote …`; exit `0`.
- `test_cli_error_writes_nothing`: an incomparable pair → exit `2`, stderr starts `compare: error: `, and `comparisons_dir` does not exist.
- `test_compare_end_to_end_on_runner_reports` (contract with spec 009, open risk c): using spec 009's `fixture_paths`, `fake_services` and `FAKE_ENV` (`evals/tests/helpers.py`, new in 009), plus a second config `configs/test-b.toml` that differs only in `classifier` (`m-classifier-b`, included in the `prices` passed to `fake_services`), run spec 009's `evals.run.main` once per config on one reviewed case per dataset (rows written with spec 009's builders in `tmp_path`). Then run `compare.main` on the two JSON reports → exit `0`. The output has every result row, a `models.classifier` configuration row and a *Changed cases* section for router and move.

**`evals/tests/test_config.py`** (additive)
- `test_classifier_mini_config_differs_from_baseline_only_in_classifier`: both committed configs load with spec 009's `load_config`. Their `models` differ only in `classifier`, which is `openai/gpt-4.1-mini` in the candidate. Their `graph` values are equal, and their judges are equal.

**Manual / CI:** `uv run ruff format --check .`, `uv run ruff check .`, `uv run pyright`, `uv run pytest` exit 0. Spec 009's `test_evals_import_no_vendor_sdks` stays green with `compare.py` included.

## Suggested Story Breakdown

1. **Candidate config and comparison core.** `evals/configs/classifier-mini.toml`; in `evals/compare.py`: `load_report`, `assign_labels`, `check_comparable`, `headline_rows`, `format_value`, `format_delta`, `case_flips`, `config_diff`; the matching unit tests in `test_compare.py` and the `test_config.py` addition. Offline. Starts only after spec 009's owner gate (D2): all spec 009 stories are implemented, the datasets are owner-reviewed and the first baseline report is committed. Spec 009 must be implemented by then, even though nothing exists on disk today.
2. **Rendering, CLI, Makefile and docs.** `render_comparison`, `comparison_path`, `main`; the `compare` Makefile target; the `## Tuning round` section in `evals/README.md` (procedure, D14 guidance, ADR template); the README sentence; the CLI tests and `test_compare_end_to_end_on_runner_reports`. Depends on 1. Named verification step: `docs/decisions.md` has no tuning ADR, and no file was added under `evals/reports/`.

After story 2: **owner gate** (*Owner Procedure*). Spec 012 uses the committed comparison afterwards.

## Success Criteria

Automated (implementer):
- [ ] Story 1 began only after spec 009's owner gate. At that point every row in `evals/datasets/*.jsonl` had `"reviewed": true`, and a `evals/reports/<date>-baseline.json` with `status: "completed"` was committed.
- [ ] Every test in *Testing* exists and passes with `uv run pytest`, with no env vars and no network.
- [ ] `uv run ruff format --check .`, `uv run ruff check .` and `uv run pyright` exit 0.
- [ ] Spec 009's tests pass unmodified; the only change in `evals/tests/test_config.py` is the added test.
- [ ] `make -n compare REPORTS="a.json b.json"` prints `uv run python -m evals.compare a.json b.json`, and `make -n eval` prints the same command as before this spec.
- [ ] At the end of the stories, `docs/decisions.md` contains no tuning-round ADR, `evals/reports/` contains no file added by the stories, and neither `README.md` nor `evals/README.md` contains an eval metric value.
- [ ] `evals/README.md` contains the `## Tuning round` section with the procedure, the D14 guidance and the ADR template.

Owner gate (after story 2; needs reviewed datasets and real keys):
- [ ] `make eval CONFIG=baseline` and `make eval CONFIG=classifier-mini` exit `0` on the same commit.
- [ ] `make compare` on those two reports exits `0` and writes the comparison file.
- [ ] Both reports and the comparison are committed.
- [ ] `docs/decisions.md` has the tuning ADR from the template, with the pasted table, the chosen model ids and the D14 outcome or override reason.
- [ ] The chosen `MODEL_*` values are in the owner's `.env`.

## Future Considerations

- Make `GraphSettings` configurable in production (env or config file) so a `[graph]`-varying winner, such as a different `retrieval_k` or `clarify_threshold`, can be adopted (D4).
- A router-model round and an answer-model round, reusing the same tooling.
- A paired significance test (for example McNemar on the flip counts) next to the D10 flips.
- Rules-QA per-case deltas (recall and key-fact coverage) in *Changed cases*.
- A `--max-cases` sampling flag on the runner for cheap pre-screening of candidates (spec 009 Future Considerations).
