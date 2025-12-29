.PHONY: help install dev format format-check lint lint-fix type check test test-cov clean clean-all scan pkg pkg-install pkg-clean security audit watch ci

# Colors for output
BLUE := \033[36m
RESET := \033[0m
GREEN := \033[32m
YELLOW := \033[33m

help: ## Show this help
	@echo "$(BLUE)Available targets:$(RESET)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(BLUE)%-15s$(RESET) %s\n", $$1, $$2}'

install: ## Install package
	@echo "$(GREEN)Installing package...$(RESET)"
	pip install -e .

dev: ## Install dev dependencies
	@echo "$(GREEN)Installing dev dependencies...$(RESET)"
	pip install -e ".[dev]"

format: ## Format code with Ruff
	@echo "$(GREEN)Formatting code with Ruff...$(RESET)"
	ruff format .
	@echo "$(GREEN)✓ Code formatted$(RESET)"

format-check: ## Check code formatting without changes
	@echo "$(GREEN)Checking code formatting...$(RESET)"
	ruff format --check --diff .

lint: ## Lint code with Ruff (read-only)
	@echo "$(GREEN)Linting code with Ruff...$(RESET)"
	ruff check . --statistics

lint-fix: ## Lint and auto-fix issues with Ruff
	@echo "$(GREEN)Linting and fixing code...$(RESET)"
	ruff check . --fix --show-fixes

type: ## Type check with mypy
	@echo "$(GREEN)Running type checks with mypy...$(RESET)"
	mypy account_scanner.py --show-error-codes --pretty

check: format lint type ## Run all code quality checks
	@echo "$(GREEN)✓ All checks passed!$(RESET)"

test: ## Run tests with pytest
	@echo "$(GREEN)Running tests...$(RESET)"
	pytest -v --tb=short || true

test-cov: ## Run tests with coverage report
	@echo "$(GREEN)Running tests with coverage...$(RESET)"
	pytest -v --cov=. --cov-report=html --cov-report=term-missing

security: ## Run security checks (bandit)
	@echo "$(GREEN)Running security analysis with Bandit...$(RESET)"
	pip install bandit[toml] 2>/dev/null || true
	bandit -r . -ll --skip B101

audit: ## Audit dependencies for vulnerabilities
	@echo "$(GREEN)Auditing dependencies...$(RESET)"
	pip install pip-audit 2>/dev/null || true
	pip-audit --desc

watch: ## Watch for changes and run checks
	@echo "$(YELLOW)Watching for changes (requires entr)...$(RESET)"
	@command -v entr >/dev/null 2>&1 || { echo "Error: entr not installed"; exit 1; }
	git ls-files '*.py' | entr -c make check

ci: format-check lint type test ## Run CI checks locally
	@echo "$(GREEN)✓ CI checks passed!$(RESET)"

clean: ## Clean build artifacts
	@echo "$(GREEN)Cleaning build artifacts...$(RESET)"
	rm -rf build/ dist/ *.egg-info __pycache__ .pytest_cache .mypy_cache .ruff_cache htmlcov/ .coverage
	find . -type f -name '*.pyc' -delete
	find . -type d -name '__pycache__' -delete

clean-all: clean pkg-clean ## Clean all artifacts including packages
	@echo "$(GREEN)✓ All artifacts cleaned$(RESET)"

pkg: ## Build Arch package (local)
	@echo "$(GREEN)Building Arch package...$(RESET)"
	./build.sh

pkg-install: pkg ## Build and install Arch package
	@echo "$(GREEN)Installing Arch package...$(RESET)"
	sudo pacman -U --noconfirm account-scanner-git-*.pkg.tar.zst

pkg-clean: ## Clean package build artifacts
	@echo "$(GREEN)Cleaning package artifacts...$(RESET)"
	rm -f *.pkg.tar.zst
	rm -rf src/ pkg/

scan: ## Run scan (requires USERNAME variable)
	@test -n "$(USERNAME)" || { echo "$(YELLOW)Error: USERNAME not set$(RESET)"; exit 1; }
	@echo "$(GREEN)Running scan for $(USERNAME)...$(RESET)"
	./scan.sh "$(USERNAME)" $(ARGS)
