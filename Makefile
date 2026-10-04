SHELL := /bin/bash
.DEFAULT_GOAL := help

BACKEND_DIR := backend
FRONTEND_DIR := frontend
BACKEND_VENV := $(BACKEND_DIR)/.venv
PYTHON := $(BACKEND_VENV)/bin/python
PYTEST := $(BACKEND_VENV)/bin/pytest
UVICORN := $(BACKEND_VENV)/bin/uvicorn

.PHONY: help doctor configure install bootstrap check-dev dev backend-dev frontend-dev \
	provision test test-backend test-frontend frontend-build verify

help: ## Show the available commands.
	@printf '%s\n' \
		'PULSE CRM development commands' \
		'' \
		'  make bootstrap       Install project dependencies and create backend/.env' \
		'  make dev             Run the backend and frontend development servers' \
		'  make backend-dev     Run FastAPI :4000 and FastMCP :8001' \
		'  make frontend-dev    Run Vite on http://localhost:3000' \
		'  make provision       Provision the local FakeCloud/PostgreSQL stack' \
		'  make test            Run backend tests and frontend type checking' \
		'  make frontend-build  Build the production frontend' \
		'  make verify          Run the complete repository verification suite' \
		'  make doctor          Check local development prerequisites' \
		'' \
		'First-time setup requires Node.js 20, npm, and uv.'

doctor: ## Check required commands and local project state.
	@status=0; \
	for command_name in node npm uv; do \
		if command -v "$$command_name" >/dev/null 2>&1; then \
			printf 'ok: %s\n' "$$command_name"; \
		else \
			printf 'missing: %s\n' "$$command_name"; \
			status=1; \
		fi; \
	done; \
	if [[ -x "$(UVICORN)" ]]; then \
		printf 'ok: backend virtual environment\n'; \
	else \
		printf 'missing: backend virtual environment (run make install)\n'; \
		status=1; \
	fi; \
	if [[ -d "$(FRONTEND_DIR)/node_modules" ]]; then \
		printf 'ok: frontend dependencies\n'; \
	else \
		printf 'missing: frontend dependencies (run make install)\n'; \
		status=1; \
	fi; \
	if [[ -f "$(BACKEND_DIR)/.env" ]]; then \
		printf 'ok: backend/.env\n'; \
	else \
		printf 'missing: backend/.env (run make configure)\n'; \
		status=1; \
	fi; \
	exit $$status

configure: ## Create backend/.env from the example if it does not exist.
	@if [[ -f "$(BACKEND_DIR)/.env" ]]; then \
		printf 'backend/.env already exists; leaving it unchanged.\n'; \
	else \
		cp "$(BACKEND_DIR)/.env.example" "$(BACKEND_DIR)/.env"; \
		printf 'Created backend/.env. Set GROQ_API_KEY before using chat.\n'; \
	fi

install: ## Install locked backend and frontend dependencies.
	@command -v uv >/dev/null 2>&1 || { printf 'uv is required. Install it with: brew install uv\n' >&2; exit 1; }
	@command -v npm >/dev/null 2>&1 || { printf 'npm is required. Install Node.js 20 first.\n' >&2; exit 1; }
	cd "$(BACKEND_DIR)" && uv sync --dev
	cd "$(FRONTEND_DIR)" && npm ci

bootstrap: install configure ## Prepare a new checkout for local development.
	@printf '%s\n' \
		'Bootstrap complete.' \
		'1. Set GROQ_API_KEY and DATABASE_URL in backend/.env.' \
		'2. Run make provision if the local database has not been created.' \
		'3. Run make dev.'

check-dev:
	@command -v npm >/dev/null 2>&1 || { printf 'npm is required. Install Node.js 20 first.\n' >&2; exit 1; }
	@test -x "$(UVICORN)" || { printf 'Backend dependencies are missing. Run make install.\n' >&2; exit 1; }
	@test -d "$(FRONTEND_DIR)/node_modules" || { printf 'Frontend dependencies are missing. Run make install.\n' >&2; exit 1; }
	@test -f "$(BACKEND_DIR)/.env" || { printf 'backend/.env is missing. Run make configure.\n' >&2; exit 1; }

dev: check-dev ## Run FastAPI and Vite together; Ctrl-C stops both.
	@set -e; \
	PATH="$(abspath $(BACKEND_VENV))/bin:$$PATH" bash "$(BACKEND_DIR)/run_services.sh" & \
	backend_pid=$$!; \
	cleanup() { \
		kill "$$backend_pid" 2>/dev/null || true; \
		wait "$$backend_pid" 2>/dev/null || true; \
	}; \
	trap cleanup EXIT INT TERM; \
	cd "$(FRONTEND_DIR)" && npm run dev

backend-dev: ## Run only the FastAPI development server.
	@test -x "$(UVICORN)" || { printf 'Backend dependencies are missing. Run make install.\n' >&2; exit 1; }
	@test -f "$(BACKEND_DIR)/.env" || { printf 'backend/.env is missing. Run make configure.\n' >&2; exit 1; }
	PATH="$(abspath $(BACKEND_VENV))/bin:$$PATH" bash "$(BACKEND_DIR)/run_services.sh"

frontend-dev: ## Run only the Vite development server.
	@command -v npm >/dev/null 2>&1 || { printf 'npm is required. Install Node.js 20 first.\n' >&2; exit 1; }
	@test -d "$(FRONTEND_DIR)/node_modules" || { printf 'Frontend dependencies are missing. Run make install.\n' >&2; exit 1; }
	cd "$(FRONTEND_DIR)" && npm run dev

provision: ## Provision FakeCloud resources and initialize local PostgreSQL.
	cd "$(BACKEND_DIR)" && ./setup.sh

test-backend: ## Run backend pytest tests.
	@test -x "$(PYTEST)" || { printf 'Backend test dependencies are missing. Run make install.\n' >&2; exit 1; }
	"$(PYTEST)" -q "$(BACKEND_DIR)/tests"

test-frontend: ## Run strict TypeScript checking.
	@command -v npm >/dev/null 2>&1 || { printf 'npm is required. Install Node.js 20 first.\n' >&2; exit 1; }
	@test -d "$(FRONTEND_DIR)/node_modules" || { printf 'Frontend dependencies are missing. Run make install.\n' >&2; exit 1; }
	cd "$(FRONTEND_DIR)" && npm run lint

test: test-backend test-frontend ## Run backend and frontend checks.

frontend-build: ## Create the production frontend bundle.
	@command -v npm >/dev/null 2>&1 || { printf 'npm is required. Install Node.js 20 first.\n' >&2; exit 1; }
	@test -d "$(FRONTEND_DIR)/node_modules" || { printf 'Frontend dependencies are missing. Run make install.\n' >&2; exit 1; }
	cd "$(FRONTEND_DIR)" && npm run build

verify: test frontend-build ## Run all repository verification commands.
	@test -x "$(PYTHON)" || { printf 'Backend dependencies are missing. Run make install.\n' >&2; exit 1; }
	"$(PYTHON)" -m compileall -q "$(BACKEND_DIR)/app" "$(BACKEND_DIR)/mcp"
	bash -n "$(BACKEND_DIR)/setup.sh"
	@command -v terraform >/dev/null 2>&1 || { printf 'terraform is required for the final verification step.\n' >&2; exit 1; }
	terraform -chdir="$(BACKEND_DIR)/terraform" fmt -check
