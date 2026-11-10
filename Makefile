CONFIG ?= baseline
DATASET ?= all

.PHONY: eval
eval:
	uv run --env-file .env python -m evals.run --config $(CONFIG) --dataset $(DATASET) $(if $(BUDGET),--budget-usd $(BUDGET))

.PHONY: compare
compare:
	uv run python -m evals.compare $(REPORTS)

.PHONY: image
image:
	docker build -t dw-companion:local .

.PHONY: smoke
smoke:
	infra/smoke.sh "$(URL)"

export GCP_PROJECT GCP_REGION MIN_INSTANCES

.PHONY: gcp-setup
gcp-setup:
	infra/setup.sh

.PHONY: deploy
deploy:
	infra/deploy.sh
