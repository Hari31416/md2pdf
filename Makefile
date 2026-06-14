.DEFAULT_GOAL := help

.PHONY: fmt fmt-check lint lint-fix check fix test test-cov docs help

# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

fmt:  ## Auto-format source code with black
	uv run black md2pdf/ tests/

fmt-check:  ## Check formatting without modifying files
	uv run black --check md2pdf/ tests/

# ---------------------------------------------------------------------------
# Linting
# ---------------------------------------------------------------------------

lint:  ## Run ruff linter
	uv run ruff check md2pdf/ tests/

lint-fix:  ## Run ruff and auto-fix safe issues
	uv run ruff check --fix md2pdf/ tests/

# ---------------------------------------------------------------------------
# Combined
# ---------------------------------------------------------------------------

check: fmt-check lint  ## Run all checks (no modifications)

fix: fmt lint-fix  ## Format and auto-fix everything

# ---------------------------------------------------------------------------
# Testing
# ---------------------------------------------------------------------------

test:  ## Run the test suite
	uv run pytest

test-cov:  ## Run tests with coverage report
	uv run pytest --cov=md2pdf --cov-report=term-missing

benchmark:  ## Run rendering engine speed benchmarks
	uv run --with playwright python scripts/benchmark.py

# ---------------------------------------------------------------------------
# Documentation
# ---------------------------------------------------------------------------

docs:  ## Build all documentation and examples as PDFs
	uv run python scripts/build_docs.py

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------

help:  ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*##"}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'
