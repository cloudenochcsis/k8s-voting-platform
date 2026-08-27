.PHONY: help dev down test reveal k6-load

help:
	@echo "  make dev      - Build and start the stack (http://localhost:8080)"
	@echo "  make down     - Stop the stack and drop the database volume"
	@echo "  make test     - Run the integration test against the running stack"
	@echo "  make reveal   - Flip the reveal flag (same script as the Kubernetes CronJob)"
	@echo "  make k6-load  - Run the k6 spike test (requires k6)"

dev:
	docker compose up -d --build

down:
	docker compose down -v

test:
	python3 test_e2e.py

reveal:
	docker compose run --rm reveal-gate

k6-load:
	k6 run load-test/spike.js
