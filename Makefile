SHELL := /bin/bash

PYTHON ?= python3
VENV ?= .venv
VENV_BIN := $(VENV)/bin
PYTHON_PATHS := scripts plugins/rubric-maker-skill/scripts plugins/rubric-maker-skill/skills plugins/oasis-ingestion/scripts
MARKDOWN_FIND := find . \( -path ./.git -o -path ./.copilot-tracking -o -path ./.ruff_cache -o -path ./.venv -o -path ./venv -o -path ./build -o -path ./dist \) -prune -o -type f -name '*.md' -print0

RUFF ?= $(shell if [ -x "$(VENV_BIN)/ruff" ]; then printf "$(VENV_BIN)/ruff"; else command -v ruff 2>/dev/null || printf ruff; fi)
TY ?= $(shell if [ -x "$(VENV_BIN)/ty" ]; then printf "$(VENV_BIN)/ty"; else command -v ty 2>/dev/null || printf ty; fi)
FLOWMARK ?= $(shell if [ -x "$(VENV_BIN)/flowmark" ]; then printf "$(VENV_BIN)/flowmark"; else command -v flowmark 2>/dev/null || printf flowmark; fi)
PRE_COMMIT ?= $(shell if [ -x "$(VENV_BIN)/pre-commit" ]; then printf "$(VENV_BIN)/pre-commit"; else command -v pre-commit 2>/dev/null || printf pre-commit; fi)
FLOWMARK_ARGS ?= --semantic --cleanups --width 88 --list-spacing preserve
FLOWMARK_WRITE_ARGS ?= --inplace --nobackup $(FLOWMARK_ARGS)

.PHONY: dev-install pre-commit-install check python-check markdown-check format format-check lint ruff-lint ruff-format ruff-format-check typecheck ty-check flowmark-lint flowmark-format smoke marketplace-check version-check changelog-check schema-sync-check grade-sheet-sync-check plugin-smoke release-check release-check-marketplace

dev-install:
	$(PYTHON) -m venv $(VENV)
	$(VENV_BIN)/python -m pip install --upgrade pip
	$(VENV_BIN)/python -m pip install --group dev

pre-commit-install:
	$(PRE_COMMIT) install

check: python-check markdown-check typecheck smoke

python-check: ruff-lint ruff-format-check

markdown-check: flowmark-lint

lint: ruff-lint flowmark-lint

format: ruff-format flowmark-format

format-check: ruff-format-check flowmark-lint

ruff-lint:
	$(RUFF) check $(RUFF_CHECK_ARGS) $(PYTHON_PATHS)

ruff-format:
	$(RUFF) format $(RUFF_FORMAT_ARGS) $(PYTHON_PATHS)

ruff-format-check:
	$(RUFF) format --check $(RUFF_FORMAT_ARGS) $(PYTHON_PATHS)

typecheck: ty-check

ty-check:
	$(TY) check $(TY_ARGS)

flowmark-lint:
	@set -euo pipefail; \
	status=0; \
	while IFS= read -r -d '' file; do \
		tmp=$$(mktemp); \
		$(FLOWMARK) $(FLOWMARK_ARGS) "$$file" > "$$tmp"; \
		if ! cmp -s "$$file" "$$tmp"; then \
			echo "flowmark would reformat $$file"; \
			status=1; \
		fi; \
		rm -f "$$tmp"; \
	done < <($(MARKDOWN_FIND)); \
	exit $$status

flowmark-format:
	@set -euo pipefail; \
	while IFS= read -r -d '' file; do \
		$(FLOWMARK) $(FLOWMARK_WRITE_ARGS) "$$file"; \
	done < <($(MARKDOWN_FIND))

smoke:
	$(MAKE) marketplace-check
	$(MAKE) version-check
	$(MAKE) changelog-check
	$(MAKE) schema-sync-check
	$(MAKE) grade-sheet-sync-check
	$(MAKE) plugin-smoke

marketplace-check:
	python3 scripts/verify_plugin_compat.py

version-check:
	python3 scripts/verify_versions.py

changelog-check:
	python3 scripts/verify_changelog.py

schema-sync-check:
	python3 scripts/verify_schema_sync.py

grade-sheet-sync-check:
	python3 scripts/verify_grade_sheet_schema_sync.py

plugin-smoke:
	python3 scripts/smoke_test.py

release-check:
	python3 scripts/release_check.py --plugin "$(PLUGIN)" --version "$(VERSION)"

release-check-marketplace:
	python3 scripts/release_check.py --marketplace --version "$(VERSION)"
