.PHONY: install proto lint format-check test run-http run-grpc worker reservation-scheduler

install:
	uv sync

proto:
	uv run python scripts/generate_proto.py

lint:
	uv run ruff check .

format-check:
	uv run ruff format --check .

test:
	uv run pytest

run-http:
	uv run uvicorn --app-dir src gameclub_backend.presentation.http.app:app --reload

run-grpc:
	uv run python -m gameclub_backend.main

worker:
	uv run dramatiq gameclub_backend.jobs.reservations gameclub_backend.jobs.billing --processes 1 --threads 4

reservation-scheduler:
	uv run python -m gameclub_backend.jobs.scheduler
