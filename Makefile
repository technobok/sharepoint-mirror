.PHONY: help sync install init-db migrate-db run rundev check clean docker-up docker-down

SHELL := /bin/bash
VENV_DIR := .venv
PYTHON := $(VENV_DIR)/bin/python
FLASK := $(VENV_DIR)/bin/flask
RUFF := $(VENV_DIR)/bin/ruff
TY := $(VENV_DIR)/bin/ty

help:
	@echo "SharePoint Mirror - Document Sync Tool"
	@echo "--------------------------------------"
	@echo "sync     - Sync dependencies with uv (creates venv if needed)"
	@echo "install  - Alias for sync"
	@echo "init-db     - Create a blank database"
	@echo "migrate-db  - Run pending database migrations"
	@echo "run      - Run server with production settings (HOST:PORT)"
	@echo "rundev   - Run server with dev settings (DEV_HOST:DEV_PORT, debug=True)"
	@echo "check    - Run ruff and ty for code quality"
	@echo "clean    - Remove temporary files and database"
	@echo ""
	@echo "Sync Commands:"
	@echo "do-sync     - Run SharePoint sync"
	@echo "do-sync-dry - Preview sync changes (dry run)"
	@echo "do-sync-full- Force full sync (ignore delta tokens)"
	@echo "status      - Show sync status"
	@echo "list        - List synced documents"

sync:
	@echo "--- Syncing dependencies ---"
	@uv sync --extra dev

install: sync

init-db:
	@echo "--- Creating blank database ---"
	@$(FLASK) --app wsgi init-db
	@echo "Database created. Run 'make run' to start the server."

migrate-db:
	@echo "--- Running database migrations ---"
	@$(FLASK) --app wsgi migrate-db

run:
	@echo "--- Starting server (production settings) ---"
	@$(PYTHON) wsgi.py

rundev:
	@echo "--- Starting server (dev settings, debug=True) ---"
	@$(PYTHON) wsgi.py --dev

do-sync:
	@echo "--- Running SharePoint sync ---"
	@$(FLASK) --app wsgi sync

do-sync-dry:
	@echo "--- Running SharePoint sync (dry run) ---"
	@$(FLASK) --app wsgi sync --dry-run

do-sync-full:
	@echo "--- Running full SharePoint sync ---"
	@$(FLASK) --app wsgi sync --full

status:
	@echo "--- Sync Status ---"
	@$(FLASK) --app wsgi status

list:
	@echo "--- Documents ---"
	@$(FLASK) --app wsgi list

check:
	@echo "--- Running code quality checks ---"
	@$(RUFF) format src
	@$(RUFF) check src --fix
	@$(TY) check src

docker-up:
	@test -f config.ini || { echo "Error: config.ini not found — copy from config.ini.example first"; exit 1; }
	docker compose up -d

docker-down:
	docker compose down

clean:
	@echo "--- Cleaning up ---"
	@find . -type f -name '*.py[co]' -delete
	@find . -type d -name '__pycache__' -delete
	@rm -f instance/sharepoint_mirror.sqlite3
	@rm -rf instance/blobs/*
