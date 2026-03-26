.PHONY: install dev test lint format run clean

install:
	pip install -e .

dev:
	pip install -e ".[dev]"

test:
	pytest tests/ -v --tb=short --cov=src/finspark --cov-report=term-missing

test-unit:
	pytest tests/unit/ -v --tb=short

test-integration:
	pytest tests/integration/ -v --tb=short

lint:
	ruff check src/ tests/
	ruff format --check src/ tests/

format:
	ruff check src/ tests/ --fix
	ruff format src/ tests/

run:
	uvicorn finspark.main:app --reload --host 0.0.0.0 --port 8000

clean:
	rm -rf .pytest_cache __pycache__ .coverage htmlcov dist build *.db
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
