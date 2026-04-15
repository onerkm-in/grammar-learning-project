# Portal Backend Template (Python)

This template is a minimal backend that forwards portal questions to The Grammar Teacher API safely.

## Why use this layer

- Keeps `GRAMMAR_TEACHER_API_KEY` on server side
- Lets your portal call a clean endpoint: `POST /portal/ask`
- Adds backend logging and upstream health checks

## Endpoints

- `GET /health`
- `GET /health/upstream`
- `POST /portal/ask`
- `GET /demo` (simple browser UI for localhost preview)

## 1. Install

```powershell
.venv\Scripts\Activate.ps1
pip install -r portal_backend_template/requirements.txt
```

## 2. Configure environment

Copy values from `.env.example` into your environment.

PowerShell example:

```powershell
$env:GRAMMAR_TEACHER_ASK_URL = "http://127.0.0.1:8000/ask"
$env:GRAMMAR_TEACHER_HEALTH_URL = "http://127.0.0.1:8000/health"
$env:GRAMMAR_TEACHER_API_KEY = "replace-with-your-grammar-teacher-api-key"
$env:PORTAL_ALLOWED_ORIGINS = "http://localhost:3000"
$env:PORTAL_LOG_DIR = "logs"
$env:UPSTREAM_TIMEOUT_SECONDS = "20"
```

## 3. Run

```powershell
python -m uvicorn portal_backend_template.app:app --host 0.0.0.0 --port 8100 --reload
```

## 4. Test

Health:

```powershell
Invoke-RestMethod http://localhost:8100/health
Invoke-RestMethod http://localhost:8100/health/upstream
```

Browser demo:

```text
http://localhost:8100/demo
```

Ask:

```powershell
$body = @{
  query = "subject verb agreement"
  top_k = 3
  learner_id = "user-123"
  session_id = "session-abc"
} | ConvertTo-Json

Invoke-RestMethod `
  -Uri http://localhost:8100/portal/ask `
  -Method Post `
  -ContentType "application/json" `
  -Body $body
```

## Request and response shape

Request body:

```json
{
  "query": "subject verb agreement",
  "top_k": 3,
  "stage": "intermediate",
  "learner_id": "user-123",
  "session_id": "session-abc"
}
```

Response:

- all fields from The Grammar Teacher `/ask`
- plus `portal_context` echoing `learner_id` and `session_id`

Current response behavior from upstream includes:

- `query_original`, `query_refined`, and optional `pipeline_trace` for observability
- quick checks with answer + why
- daily lesson intent handling (`What's the lesson of the day?`)
- summarized/word-limited explanation points for readability

## Integration notes

- Frontend should call this template backend, not The Grammar Teacher API directly.
- Keep `GRAMMAR_TEACHER_API_KEY` only in backend environment.
- In production, replace `--reload` with normal process manager startup.
