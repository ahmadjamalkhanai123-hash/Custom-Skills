# Makefile — Local CI Mirror (Tier 1 Developer)
# Mirrors CI stages locally for fast feedback before pushing
# Usage: make help | make lint | make test | make build | make ci

.DEFAULT_GOAL := help
.PHONY: help lint type-check format test test-unit test-integration build docker-build \
        docker-push clean ci security check-deps

# ─────────────────────────────────────────────────────────────
# Variables (override via env or make VAR=value)
# ─────────────────────────────────────────────────────────────
APP_NAME        ?= myapp
REGISTRY        ?= ghcr.io/org
IMAGE_TAG       ?= $(shell git rev-parse --short HEAD)
PYTHON          ?= python3
UV              ?= uv
COVERAGE_MIN    ?= 80
PORT            ?= 8080
COMPOSE_FILE    ?= docker-compose.yml

# Colors for output
GREEN  := \033[0;32m
YELLOW := \033[1;33m
RED    := \033[0;31m
NC     := \033[0m

# ─────────────────────────────────────────────────────────────
# HELP
# ─────────────────────────────────────────────────────────────
help: ## Show available commands
	@echo ""
	@echo "$(GREEN)CI/CD Pipeline — Local Commands$(NC)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(YELLOW)%-20s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "Run $(GREEN)make ci$(NC) to simulate the full pipeline locally"
	@echo ""

# ─────────────────────────────────────────────────────────────
# INSTALL
# ─────────────────────────────────────────────────────────────
install: ## Install all dependencies (dev + prod)
	@echo "$(GREEN)Installing dependencies...$(NC)"
	$(UV) sync --frozen
	pre-commit install
	@echo "$(GREEN)✓ Dependencies installed$(NC)"

install-ci: ## Install CI dependencies (no dev tools)
	$(UV) sync --frozen --no-dev

# ─────────────────────────────────────────────────────────────
# CODE QUALITY
# ─────────────────────────────────────────────────────────────
lint: ## Run linters (ruff + mypy)
	@echo "$(GREEN)Running linters...$(NC)"
	$(UV) run ruff check src/ tests/
	$(UV) run ruff format --check src/ tests/
	@echo "$(GREEN)✓ Lint passed$(NC)"

type-check: ## Run type checker (mypy)
	@echo "$(GREEN)Running type check...$(NC)"
	$(UV) run mypy src/ --strict
	@echo "$(GREEN)✓ Type check passed$(NC)"

format: ## Auto-format code (ruff)
	@echo "$(GREEN)Formatting code...$(NC)"
	$(UV) run ruff check --fix src/ tests/
	$(UV) run ruff format src/ tests/
	@echo "$(GREEN)✓ Code formatted$(NC)"

check-deps: ## Check for vulnerable dependencies
	@echo "$(GREEN)Checking dependencies...$(NC)"
	$(UV) run safety check --short-report
	@echo "$(GREEN)✓ Dependencies OK$(NC)"

# ─────────────────────────────────────────────────────────────
# TESTING
# ─────────────────────────────────────────────────────────────
test: test-unit ## Run unit tests (alias)

test-unit: ## Run unit tests with coverage
	@echo "$(GREEN)Running unit tests...$(NC)"
	$(UV) run pytest tests/unit/ \
		--cov=src \
		--cov-report=term-missing \
		--cov-report=html:coverage-html/ \
		--cov-fail-under=$(COVERAGE_MIN) \
		-v \
		--tb=short
	@echo "$(GREEN)✓ Unit tests passed (coverage ≥ $(COVERAGE_MIN)%)$(NC)"

test-integration: ## Run integration tests (requires Docker)
	@echo "$(GREEN)Starting test services...$(NC)"
	docker compose -f docker-compose.test.yml up -d --wait
	@echo "$(GREEN)Running integration tests...$(NC)"
	$(UV) run pytest tests/integration/ -v --timeout=60 || \
		(docker compose -f docker-compose.test.yml down -v && exit 1)
	docker compose -f docker-compose.test.yml down -v
	@echo "$(GREEN)✓ Integration tests passed$(NC)"

test-all: test-unit test-integration ## Run all tests

# ─────────────────────────────────────────────────────────────
# DOCKER
# ─────────────────────────────────────────────────────────────
build: docker-build ## Build Docker image (alias)

docker-build: ## Build Docker image locally
	@echo "$(GREEN)Building Docker image...$(NC)"
	DOCKER_BUILDKIT=1 docker build \
		--build-arg GIT_SHA=$(IMAGE_TAG) \
		--build-arg BUILD_DATE=$(shell date -u +%Y-%m-%dT%H:%M:%SZ) \
		--tag $(APP_NAME):$(IMAGE_TAG) \
		--tag $(APP_NAME):latest \
		.
	@echo "$(GREEN)✓ Image built: $(APP_NAME):$(IMAGE_TAG)$(NC)"

docker-push: docker-build ## Build and push to registry
	@echo "$(GREEN)Pushing image to registry...$(NC)"
	docker tag $(APP_NAME):$(IMAGE_TAG) $(REGISTRY)/$(APP_NAME):$(IMAGE_TAG)
	docker push $(REGISTRY)/$(APP_NAME):$(IMAGE_TAG)
	@echo "$(GREEN)✓ Pushed: $(REGISTRY)/$(APP_NAME):$(IMAGE_TAG)$(NC)"

docker-scan: docker-build ## Scan image for vulnerabilities
	@echo "$(GREEN)Scanning image...$(NC)"
	docker run --rm \
		-v /var/run/docker.sock:/var/run/docker.sock \
		aquasec/trivy:latest image \
		--exit-code 1 \
		--severity CRITICAL,HIGH \
		$(APP_NAME):$(IMAGE_TAG)
	@echo "$(GREEN)✓ No critical/high vulnerabilities$(NC)"

# ─────────────────────────────────────────────────────────────
# LOCAL RUN
# ─────────────────────────────────────────────────────────────
run: ## Run app locally (development mode)
	$(UV) run uvicorn src.main:app --reload --port $(PORT)

run-docker: docker-build ## Run app via Docker
	docker run -it --rm \
		-p $(PORT):$(PORT) \
		--env-file .env \
		$(APP_NAME):$(IMAGE_TAG)

compose-up: ## Start full stack via Docker Compose
	docker compose -f $(COMPOSE_FILE) up -d --build
	@echo "$(GREEN)✓ Stack running at http://localhost:$(PORT)$(NC)"

compose-down: ## Stop Docker Compose stack
	docker compose -f $(COMPOSE_FILE) down -v

compose-logs: ## Show Docker Compose logs
	docker compose -f $(COMPOSE_FILE) logs -f

# ─────────────────────────────────────────────────────────────
# LOCAL CI SIMULATION
# ─────────────────────────────────────────────────────────────
ci: ## Run full CI pipeline locally (mirrors GitHub Actions)
	@echo "$(GREEN)════════════════════════════════════════$(NC)"
	@echo "$(GREEN) Running Local CI Pipeline$(NC)"
	@echo "$(GREEN)════════════════════════════════════════$(NC)"
	@echo ""
	@echo "$(YELLOW)Stage 1: Code Quality$(NC)"
	@$(MAKE) lint type-check
	@echo ""
	@echo "$(YELLOW)Stage 2: Security$(NC)"
	@pre-commit run gitleaks --all-files || echo "$(RED)Secret scan failed$(NC)"
	@$(MAKE) check-deps
	@echo ""
	@echo "$(YELLOW)Stage 3: Tests$(NC)"
	@$(MAKE) test-unit
	@echo ""
	@echo "$(YELLOW)Stage 4: Build$(NC)"
	@$(MAKE) docker-build
	@echo ""
	@echo "$(YELLOW)Stage 5: Image Scan$(NC)"
	@$(MAKE) docker-scan || echo "$(RED)Image scan found issues$(NC)"
	@echo ""
	@echo "$(GREEN)════════════════════════════════════════$(NC)"
	@echo "$(GREEN) ✓ All CI stages passed!$(NC)"
	@echo "$(GREEN)════════════════════════════════════════$(NC)"

act: ## Run GitHub Actions locally with 'act' tool
	@command -v act >/dev/null || (echo "Install act: https://github.com/nektos/act" && exit 1)
	act push -j build --secret-file .env.ci

# ─────────────────────────────────────────────────────────────
# CLEANUP
# ─────────────────────────────────────────────────────────────
clean: ## Remove build artifacts and caches
	@echo "$(GREEN)Cleaning up...$(NC)"
	rm -rf coverage-html/ .coverage coverage.xml reports/ dist/ .ruff_cache/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "$(GREEN)✓ Cleaned$(NC)"

clean-docker: ## Remove local Docker images
	docker rmi $(APP_NAME):$(IMAGE_TAG) $(APP_NAME):latest 2>/dev/null || true
	@echo "$(GREEN)✓ Docker images removed$(NC)"
