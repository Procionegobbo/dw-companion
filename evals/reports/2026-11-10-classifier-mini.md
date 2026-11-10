# Eval report: classifier-mini

- run_id: 8b82f20dce21471abf54166e68ea69c6
- status: completed
- started_at: 2026-11-10T17:33:47.642187+00:00
- finished_at: 2026-11-10T17:44:38.890862+00:00
- git_commit: ae64ee9bdae6dfbef0fe6f651b3c932e4aa5e5ed
- budget: limit $3.0, estimated $1.27864, spent $0.216189, unknown-cost calls 0

## router

- file: evals/datasets/router.jsonl (sha256 0773b7a98aae)
- rows: 45, completed: 45

Metrics:
- n: 45
- accuracy: 0.8444

System:
- all: n=45, p50=3247.8ms, p95=5583.1ms, cost_mean=$0.001009
- rules_question: n=20, p50=4439.6ms, p95=5610.1ms, cost_mean=$0.001862
- action_description: n=11, p50=3342.2ms, p95=5553.4ms, cost_mean=$0.000714
- out_of_scope: n=12, p50=778.9ms, p95=1148.7ms, cost_mean=$2.4e-05
- error: n=2, p50=2494.3ms, p95=2514.8ms, cost_mean=$0.0

Failures: 7
- router-026: kind=rules_answer
- router-028: kind=rules_answer
- router-029: kind=rules_answer
- router-030: kind=rules_answer
- router-041: kind=error
- router-042: kind=error
- router-043: kind=rules_answer

## rules_qa

- file: evals/datasets/rules_qa.jsonl (sha256 4935ef76b113)
- rows: 45, completed: 45

Metrics:
- n: 45
- answerable_n: 36
- unanswerable_n: 9
- retrieval_k: 6
- recall_at_k: 1.0
- citations_valid: 76
- citations_stripped: 0
- answers_without_citations: 1
- citation_validity_rate: 1.0
- key_fact_coverage: 0.9421
- key_fact_judged_n: 36
- judge_errors: 0
- correct_refusal_rate: 0.1111
- misrouted: 0

System:
- all: n=45, p50=3724.0ms, p95=6171.1ms, cost_mean=$0.001636
- rules_question: n=45, p50=3724.0ms, p95=6171.1ms, cost_mean=$0.001636

Judge overhead: 36 call(s), $0.035989

Failures: 8
- rules-036: kind=rules_answer
- rules-038: kind=rules_answer
- rules-039: kind=rules_answer
- rules-041: kind=rules_answer
- rules-042: kind=rules_answer
- rules-043: kind=rules_answer
- rules-044: kind=rules_answer
- rules-045: kind=rules_answer

## move_classification

- file: evals/datasets/move_classification.jsonl (sha256 6235f338d746)
- rows: 86, completed: 86

Metrics:
- n: 86
- accuracy: 0.8721
- no_move_precision: 1.0
- no_move_recall: 0.5625
- clarification_rate: 0.0
- misrouted: 6

System:
- all: n=86, p50=3232.8ms, p95=4741.8ms, cost_mean=$0.000712
- rules_question: n=3, p50=3319.3ms, p95=4124.2ms, cost_mean=$0.001833
- action_description: n=80, p50=3258.9ms, p95=4881.0ms, cost_mean=$0.000696
- out_of_scope: n=1, p50=910.5ms, p95=910.5ms, cost_mean=$2.5e-05
- error: n=2, p50=1873.3ms, p95=2832.6ms, cost_mean=$0.0

Failures: 11
- move-002: kind=error
- move-008: kind=error
- move-026: kind=rules_answer
- move-043: kind=move
- move-072: kind=rules_answer
- move-075: kind=rules_answer
- move-077: kind=out_of_scope
- move-079: kind=move
- move-082: kind=move
- move-085: kind=move
- move-086: kind=move

