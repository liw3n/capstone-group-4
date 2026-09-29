# PULSE Chat API

FastAPI backend for the chat popup.

## Endpoints

- `GET /chat/sessions?fa_id=<id>`
- `POST /chat/new?fa_id=<id>`
- `GET /chat/history?session_id=<id>`
- `POST /chat/query`

Detailed API contract can be found in `docs/api_contract.md`.

## Local setup

This project uses `uv` for dependency management, so the virtual environment and package list are defined in `pyproject.toml`.

1. Install `uv`, FakeCloud, and Terraform if they are not already available:

```bash
brew install uv fakecloud
brew tap hashicorp/tap
brew install hashicorp/tap/terraform
```

2. Start the virtual environment:

```bash
uv venv
source .venv/bin/activate
uv sync
```

3. Run the setup script in the virtual environment: 

```bash
cd backend
./setup.sh
```

The setup script starts FakeCloud on port 4566, then initializes Terraform and applies the AWS resources. Terraform will ask for confirmation before applying.
