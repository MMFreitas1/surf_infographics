.DEFAULT_GOAL := help
.PHONY: help setup dev api web check lint fmt typecheck test evals verify labels logs errors clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

setup: ## Install all dependencies
	cd api && uv sync --group dev
	cd web && pnpm install

api: ## Run the API on :8000
	cd api && uv run uvicorn surf.main:app --reload --host 127.0.0.1 --port 8000

web: ## Run the UI on :3000
	cd web && pnpm run dev

check: lint typecheck test evals ## Everything CI runs

lint: ## Lint both stacks
	cd api && uv run ruff check . ../evals && uv run ruff format --check . ../evals
	cd web && pnpm run lint

fmt: ## Autoformat both stacks
	cd api && uv run ruff check --fix . ../evals && uv run ruff format . ../evals
	cd web && pnpm exec biome check --write .

typecheck: ## Type check both stacks
	cd api && uv run mypy
	cd web && pnpm run typecheck

test: ## Unit tests
	cd api && uv run pytest
	cd web && pnpm run test

evals: ## Detection eval gate
	cd api && uv run pytest ../evals

verify: ## Drive the UI with Playwright: screenshots + console errors -> web/verification/
	cd web && pnpm run verify

labels: ## What the human labels say, including the GPS-recovery hypothesis
	cd api && uv run python -m surf.report

logs: ## Tail the API's structured log
	@tail -n 50 data/logs/api.jsonl 2>/dev/null || echo "no log yet - start the API first"

errors: ## Show recent errors from the running API
	@curl -s http://127.0.0.1:8000/diagnostics/errors | python3 -m json.tool || echo "API not running"

clean: ## Remove caches and build output
	rm -rf api/.pytest_cache api/.mypy_cache api/.ruff_cache web/.next web/*.tsbuildinfo
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
