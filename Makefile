.PHONY: lint format type-check test-unit test-all coverage clean build

lint:
	uv run ruff check plugins/ tests/

format:
	uv run ruff format plugins/ tests/

format-check:
	uv run ruff format --check plugins/ tests/

type-check:
	uv run mypy plugins/

test-unit:
	uv run pytest tests/unit/ -v

test-all: lint format-check type-check test-unit

coverage:
	uv run pytest tests/unit/ --cov=plugins --cov-report=html --cov-report=term

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

build:
	ansible-galaxy collection build --force
