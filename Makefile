.PHONY: help install install-dev test test-cov lint typecheck security coverage format format-check clean build quality bump bump-patch bump-minor bump-major bump-dry version release release-patch release-minor release-major publish

.DEFAULT_GOAL := help

help:  ## Show this help message
	@echo '================================'
	@echo 'git-notes-memory-manager - Make Targets'
	@echo '================================'
	@echo ''
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Installation:'
	@grep -E '^(install|install-dev):.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
	@echo ''
	@echo 'Quality:'
	@grep -E '^(quality|lint|typecheck|security|format|format-check):.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
	@echo ''
	@echo 'Testing:'
	@grep -E '^(test|test-cov|coverage):.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
	@echo ''
	@echo 'Build:'
	@grep -E '^(build|clean):.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
	@echo ''
	@echo 'Version:'
	@grep -E '^(version|bump|bump-patch|bump-minor|bump-major|bump-dry):.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
	@echo ''
	@echo 'Release:'
	@grep -E '^(release|release-patch|release-minor|release-major|publish):.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
	@echo ''

install:  ## Install package
	uv pip install -e .

install-dev:  ## Install with dev dependencies
	uv sync

test:  ## Run tests
	uv run pytest

test-cov:  ## Run tests with coverage
	uv run pytest --cov=git_notes_memory --cov-report=html --cov-report=term-missing

lint:  ## Run linter (ruff)
	uv run ruff check src/ tests/

typecheck:  ## Run type checker (mypy)
	uv run mypy src/

security:  ## Run security scan (bandit)
	uv run bandit -r src/ -ll

format:  ## Format code (ruff)
	uv run ruff format src/ tests/
	uv run ruff check --fix src/ tests/

format-check:  ## Check formatting
	uv run ruff format --check src/ tests/
	uv run ruff check src/ tests/

coverage:  ## Run tests with coverage threshold
	uv run pytest --cov=git_notes_memory --cov-report=term-missing --cov-fail-under=80

quality:  ## Run all quality checks
	@echo "Running quality checks..."
	@echo ""
	@echo "1. Formatting..."
	@uv run ruff format src/ tests/
	@uv run ruff check --fix src/ tests/
	@echo "Formatting: PASS"
	@echo ""
	@echo "2. Linting..."
	@uv run ruff check src/ tests/
	@echo "Linting: PASS"
	@echo ""
	@echo "3. Type checking..."
	@uv run mypy src/
	@echo "Type checking: PASS"
	@echo ""
	@echo "4. Security..."
	@uv run bandit -r src/ -ll -q
	@echo "Security: PASS"
	@echo ""
	@echo "5. Tests with coverage..."
	@uv run pytest --cov=git_notes_memory --cov-report=term-missing --cov-fail-under=80 -q
	@echo ""
	@echo "ALL QUALITY CHECKS PASSED"

build:  ## Build distribution packages
	uv run python -m build

clean:  ## Clean build artifacts
	rm -rf build/ dist/ *.egg-info .pytest_cache .mypy_cache .ruff_cache htmlcov/ .coverage
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# =============================================================================
# Release / Version Bumping
# =============================================================================

version:  ## Show current version
	@uv run bump-my-version show current_version

bump: bump-patch  ## Bump version (alias for bump-patch)

bump-patch:  ## Bump patch version (0.3.0 → 0.3.1)
	@echo "Bumping patch version..."
	uv run bump-my-version bump patch
	@echo ""
	@echo "✓ Version bumped. Don't forget to push with tags:"
	@echo "  git push && git push --tags"

bump-minor:  ## Bump minor version (0.3.0 → 0.4.0)
	@echo "Bumping minor version..."
	uv run bump-my-version bump minor
	@echo ""
	@echo "✓ Version bumped. Don't forget to push with tags:"
	@echo "  git push && git push --tags"

bump-major:  ## Bump major version (0.3.0 → 1.0.0)
	@echo "Bumping major version..."
	uv run bump-my-version bump major
	@echo ""
	@echo "✓ Version bumped. Don't forget to push with tags:"
	@echo "  git push && git push --tags"

bump-dry:  ## Show what would be bumped (dry run)
	@echo "Dry run - showing what would change for patch bump:"
	@echo ""
	uv run bump-my-version bump patch --dry-run --verbose --allow-dirty

# =============================================================================
# Release Workflow
# =============================================================================

release: release-patch  ## Release (alias for release-patch)

release-patch:  ## Release patch version (quality → bump → push → gh-release → build)
	@echo "Starting patch release..."
	@echo ""
	@$(MAKE) quality
	@echo ""
	@echo "Quality checks passed. Bumping version..."
	uv run bump-my-version bump patch
	@echo ""
	@echo "Pushing to remote..."
	git push && git push --tags
	@echo ""
	@echo "Creating GitHub release..."
	@NEW_VERSION=$$(uv run bump-my-version show current_version) && \
		gh release create "v$$NEW_VERSION" --title "v$$NEW_VERSION" --generate-notes
	@echo ""
	@echo "Building package..."
	@$(MAKE) build
	@echo ""
	@echo "✓ Release complete! Version: $$(uv run bump-my-version show current_version)"

release-minor:  ## Release minor version (quality → bump → push → gh-release → build)
	@echo "Starting minor release..."
	@echo ""
	@$(MAKE) quality
	@echo ""
	@echo "Quality checks passed. Bumping version..."
	uv run bump-my-version bump minor
	@echo ""
	@echo "Pushing to remote..."
	git push && git push --tags
	@echo ""
	@echo "Creating GitHub release..."
	@NEW_VERSION=$$(uv run bump-my-version show current_version) && \
		gh release create "v$$NEW_VERSION" --title "v$$NEW_VERSION" --generate-notes
	@echo ""
	@echo "Building package..."
	@$(MAKE) build
	@echo ""
	@echo "✓ Release complete! Version: $$(uv run bump-my-version show current_version)"

release-major:  ## Release major version (quality → bump → push → gh-release → build)
	@echo "Starting major release..."
	@echo ""
	@$(MAKE) quality
	@echo ""
	@echo "Quality checks passed. Bumping version..."
	uv run bump-my-version bump major
	@echo ""
	@echo "Pushing to remote..."
	git push && git push --tags
	@echo ""
	@echo "Creating GitHub release..."
	@NEW_VERSION=$$(uv run bump-my-version show current_version) && \
		gh release create "v$$NEW_VERSION" --title "v$$NEW_VERSION" --generate-notes
	@echo ""
	@echo "Building package..."
	@$(MAKE) build
	@echo ""
	@echo "✓ Release complete! Version: $$(uv run bump-my-version show current_version)"

publish:  ## Publish to PyPI (requires PYPI_TOKEN)
	@echo "Publishing to PyPI..."
	uv run twine upload dist/*
	@echo ""
	@echo "✓ Published to PyPI"
