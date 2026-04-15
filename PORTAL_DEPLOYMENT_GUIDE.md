# Portal Deployment Guide

This guide explains how to run **The Grammar Teacher API** safely for a portal.

## What We Added

- API key authentication on `POST /ask` using header `X-API-Key`
- Sliding-window rate limit per `client_ip + api_key`
- Request logging with request IDs to `logs/api_requests.log`

## Why These Controls Matter

- API key auth prevents anonymous calls from using your tutor endpoint.
- Rate limiting protects the server from accidental floods and basic abuse.
- Request logs help troubleshoot failures and track usage patterns.

## Endpoint Summary

- `GET /health`
- `POST /ask`

`/health` is open for monitoring. `/ask` requires a valid API key.

## Required Runtime Settings

The API reads these environment variables:

- `GRAMMAR_TEACHER_INDEX`
- `GRAMMAR_TEACHER_API_KEY`
- `GRAMMAR_TEACHER_RATE_LIMIT_PER_MINUTE`
- `GRAMMAR_TEACHER_LOG_DIR`
- `GRAMMAR_TEACHER_MAX_EXPLANATION_WORDS`
- `GRAMMAR_TEACHER_MAX_EXPLANATION_WORDS_COMPOSITE`
- `GRAMMAR_TEACHER_MAX_POINT_WORDS`
- `GRAMMAR_TEACHER_MAX_POINT_WORDS_COMPOSITE`

`run_api.ps1` sets these for you.

## Local Run (Production-Like)

```powershell
.venv\Scripts\Activate.ps1
.\run_api.ps1 -PythonExe .\.venv\Scripts\python.exe -IndexPath build/grammar_teacher/chunks.jsonl -ApiKey "replace-with-a-strong-key" -RateLimitPerMinute 60 -Host 0.0.0.0 -Port 8000
```

## Test Calls

Health:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

Ask:

```powershell
$body = @{
  query = "subject verb agreement"
  top_k = 3
} | ConvertTo-Json

Invoke-RestMethod `
  -Uri http://localhost:8000/ask `
  -Method Post `
  -ContentType "application/json" `
  -Headers @{ "X-API-Key" = "replace-with-a-strong-key" } `
  -Body $body
```

## Example Response Fields

- `ok`
- `topic`
- `message`
- `explanation_points`
- `quick_check`
- `reference`
- `learner_band`
- `stage`
- `score`
- `focus`

Behavior notes:

- Daily lesson intent (`What's the lesson of the day?`) returns curated topic cards.
- Quick checks include answer + why.
- Oversized explanations are summarized and word-limited before response.

## Logs

Default log file:

- `logs/api_requests.log`

Each request includes:

- timestamp
- request id
- method + path
- status code
- client IP
- duration (ms)

## Rate Limit Behavior

- Default: `60` requests per minute per `client_ip + api_key`
- On limit exceeded:
  - HTTP `429`
  - `Retry-After` header

## Portal Integration Pattern

1. Store API key in your portal backend secret manager.
2. Call `/ask` from backend only (not directly from browser).
3. Add `X-API-Key` header from server-side config.
4. Return tutor JSON to frontend.
5. Keep `/health` for uptime probes.

## Plug-In Proxy Template

A ready template is available in:

- `portal_backend_template/app.py`
- `portal_backend_template/README.md`
- `run_portal_backend.ps1`

This proxy exposes `POST /portal/ask` for your frontend and forwards safely to The Grammar Teacher API with server-side API key handling.

## Suggested First Production Settings

- `RateLimitPerMinute`: `60`
- `Host`: `0.0.0.0`
- `Port`: `8000` (or your standard API port)
- API key: at least 24 random characters

## Current Limitation

This is a minimal production wrapper. It is intentionally simple and does not yet include:

- multiple API keys with rotation
- persistent distributed rate limiting (e.g., Redis)
- structured JSON logs to external SIEM
- JWT-based user identity

Those can be added next once the portal integration is stable.
