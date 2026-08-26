.PHONY: help dev floci-up floci-down floci-init test k6-load

help:
	@echo "Available make commands:"
	@echo "  make dev          - Start voting platform services"
	@echo "  make floci-up     - Start voting platform + Floci AWS/GCP/Azure & Floci UI"
	@echo "  make floci-init   - Seed test cloud resources in Floci (S3, Secrets)"
	@echo "  make floci-down   - Stop Floci and services"
	@echo "  make test         - Run end-to-end Python test suite"
	@echo "  make k6-load      - Run k6 load test (requires k6 installed)"

dev:
	docker compose up -d

floci-up:
	docker compose -f docker-compose.floci.yml up -d
	@echo "\n🚀 Services running:"
	@echo "  - Voting Web UI:  http://localhost:8080"
	@echo "  - Floci UI Cloud: http://localhost:4500"
	@echo "  - Floci AWS Core: http://localhost:4566"
	@echo "  - Floci GCP:      http://localhost:4588"
	@echo "  - Floci Azure:    http://localhost:4577"

floci-init:
	python3 scripts/init_floci.py

floci-down:
	docker compose -f docker-compose.floci.yml down

test:
	python3 test_e2e.py

k6-load:
	k6 run load-test/spike.js
