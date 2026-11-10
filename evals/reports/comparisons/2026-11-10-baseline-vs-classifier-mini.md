# Eval comparison: baseline vs classifier-mini

Generated 2026-11-10T17:46:51.445504+00:00 by `evals/compare.py`. Reference: `baseline`.

## Reports

| Config | Report | Run id | Started (UTC) | Git commit | Eval spend |
| --- | --- | --- | --- | --- | --- |
| baseline | evals/reports/2026-11-09-baseline.json | 57ad717b964a4f5a934a2e64e7f56b9d | 2026-11-09T22:33:39.200539+00:00 | 8188831d1ce9 | $0.1197 |
| classifier-mini | evals/reports/2026-11-10-classifier-mini.json | 8b82f20dce21471abf54166e68ea69c6 | 2026-11-10T17:33:47.642187+00:00 | ae64ee9bdae6 | $0.2162 |

**Note:** reports come from different commits; deltas may include code changes, not only configuration.

## Configurations

| Setting | baseline | classifier-mini |
| --- | --- | --- |
| `models.classifier` | `openai/gpt-4.1-nano` | `openai/gpt-4.1-mini` |

Judge (identical in all reports): `anthropic/claude-haiku-4.5`.

## Results

<!-- comparison-table:start -->
| Metric | Cases | baseline | classifier-mini | Δ |
| --- | --- | --- | --- | --- |
| Router accuracy | 45 | 84.4% | 84.4% | +0.0 pp |
| Retrieval recall@6 | 36 | 100.0% | 100.0% | +0.0 pp |
| Citation validity | 45 | 100.0% | 100.0% | +0.0 pp |
| Key-fact coverage | 36 | 93.3% | 94.2% | +0.9 pp |
| Correct refusals | 9 | 22.2% | 11.1% | -11.1 pp |
| Move accuracy | 86 | 60.5% | 87.2% | +26.7 pp |
| no_move precision | — | 80.0% | 100.0% | +20.0 pp |
| no_move recall | 16 | 25.0% | 56.2% | +31.2 pp |
| Clarification rate | 86 | 2.3% | 0.0% | -2.3 pp |
| Cost per query | 176 | $0.00048 | $0.00102 | +$0.00055 (+115%) |
| Cost per rules question | 68 | $0.00084 | $0.00171 | +$0.00087 (+104%) |
| Cost per action description | 87 | $0.00031 | $0.00070 | +$0.00039 (+129%) |
| Latency p50 | 176 | 3409 ms | 3316 ms | -93 ms |
| Latency p95 | 176 | 5142 ms | 5592 ms | +450 ms |
<!-- comparison-table:end -->

## Changed cases

### router: baseline vs classifier-mini
Correct only in baseline (0): none
Correct only in classifier-mini (0): none

### move_classification: baseline vs classifier-mini
Correct only in baseline (0): none
Correct only in classifier-mini (23): move-005, move-009, move-010, move-018, move-020, move-024, move-040, move-041, move-047, move-048, move-058, move-064, move-065, move-066, move-067, move-068, move-069, move-070, move-073, move-074, … and 3 more

## Notes

- Datasets compared: router, rules_qa, move_classification.
- router: 45 cases; one case = 2.2 pp.
- rules_qa: 45 cases; one case = 2.2 pp.
- move_classification: 86 cases; one case = 1.2 pp.
- Differences of one or two cases are within run-to-run noise; check Changed cases before attributing a delta to the configuration.
