CONFIG ?= baseline
DATASET ?= all

.PHONY: eval
eval:
	uv run --env-file .env python -m evals.run --config $(CONFIG) --dataset $(DATASET) $(if $(BUDGET),--budget-usd $(BUDGET))

.PHONY: compare
compare:
	uv run python -m evals.compare $(REPORTS)
