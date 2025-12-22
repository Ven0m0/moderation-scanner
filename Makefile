. PHONY: help install dev format lint type check test clean scan pkg pkg-install pkg-clean

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## Install package
	pip install -e . 

dev: ## Install dev dependencies
	pip install -e ".[dev]"

format: ## Format code with ruff
	ruff format .

lint: ## Lint code with ruff
	ruff check .  --fix

type: ## Type check with mypy
	mypy account_scanner.py

check: format lint type ## Run all checks

test: ## Run tests
	pytest -v || true

clean: ## Clean build artifacts
	rm -rf build/ dist/ *.egg-info __pycache__ .pytest_cache . mypy_cache . ruff_cache
	find . -type f -name '*.pyc' -delete
	find . -type d -name '__pycache__' -delete

pkg: ## Build Arch package (local)
	./build.sh

pkg-install: pkg ## Build and install Arch package
	sudo pacman -U --noconfirm account-scanner-git-*. pkg.tar.zst

pkg-clean: ## Clean package build artifacts
	rm -f *.pkg.tar.zst
	rm -rf src/ pkg/

scan: ## Run scan (requires USERNAME variable)
	@test -n "$(USERNAME)" || { echo "Error: USERNAME not set"; exit 1; }
	./scan.sh "$(USERNAME)" $(ARGS)
