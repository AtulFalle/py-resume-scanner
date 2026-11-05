.PHONY: install dev test lint format format-check typecheck check

install:
	uv sync

dev:
	uv run uvicorn resume_ai.main:app --reload --app-dir src

test:
	uv run pytest

lint:
	uv run ruff check .

format:
	uv run ruff check --fix .
	uv run ruff format .

format-check:
	uv run ruff format --check .

typecheck:
	uv run mypy src

check: lint format-check typecheck test