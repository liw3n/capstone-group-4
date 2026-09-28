# MyWealth Chat API

FastAPI backend for the chat popup. It can run locally with Uvicorn or on AWS Lambda/API Gateway through Mangum.

## Endpoints

- `GET /chat/sessions?fa_id=<id>`
- `POST /chat/new?fa_id=<id>`
- `GET /chat/history?session_id=<id>`
- `POST /chat/query`

The query endpoint accepts `fa_id` either as a query parameter or in the JSON body:

```json
{ "fa_id": "advisor-1", "message_content": "How many clients need follow-up?" }
```

It returns:

```json
{ "user": "advisor-1", "timestamp": "...", "ai_answer": "..." }
```

The local store is in memory. Replace `app/store.py` with a DynamoDB repository when persistent AWS storage is needed.

## Local setup

This project uses `uv` for dependency management, so the virtual environment and package list are defined in `pyproject.toml`.

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 4000
```

The frontend's Vite proxy forwards `/api` requests to port 4000.

## AWS

Deploy `app.main:handler` as a Lambda function behind API Gateway HTTP API. Mangum adapts the FastAPI application to the Lambda event format.
