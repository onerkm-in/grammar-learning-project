# Handover Reference

This document is the single continuation reference for any person, agent, or LLM resuming work on this project.

## Project Identity

- Project name: `The Grammar Teacher`
- Goal: grammar tutoring with source-backed answers from local PDFs
- Primary mode: retrieval-backed tutoring (`grammar_teacher/tutor.py`)
- Optional mode: tiny LM generation (`tiny_lm/*`) for experimentation only

## Current Snapshot (validated)

- Date: `2026-04-01`
- Corpus documents: `25`
- Retrieval chunks: `11,589`
- Build summary source: `build/grammar_teacher/build_summary.json`
- Main API: `grammar_teacher/api_server.py`
- Portal proxy template: `portal_backend_template/app.py`
- Local demo UI: `http://localhost:8100/demo`
- Unit suite: `32/32` passing (`tests/test_grammar_teacher.py`)
- Golden retrieval tests: `17` tests in `tests/test_retrieval_quality.py` (require corpus index)

## Core Components

- Ingestion and corpus build: `grammar_teacher/build_knowledge_base.py`
- OCR fallback: `grammar_teacher/ocr.py`
- Text cleanup: `grammar_teacher/text_cleaning.py`
- Retrieval: `grammar_teacher/retrieve.py`
- Tutor response shaping: `grammar_teacher/tutor.py`
- Main secured API: `grammar_teacher/api_server.py`
- Main API launcher: `run_api.ps1`
- Portal proxy template: `portal_backend_template/app.py`
- Portal launcher: `run_portal_backend.ps1`

## Runtime Topology

Terminal 1:

- run Grammar Teacher API on `:8000` (`/health`, `/ask`)
- owns `X-API-Key` auth + rate limit + request logs

Terminal 2:

- run portal backend proxy on `:8100` (`/health`, `/health/upstream`, `/portal/ask`, `/demo`)
- forwards to `:8000` using server-side key

Browser:

- open `http://localhost:8100/demo` for local visual testing

## Start Commands

Activate environment:

```powershell
.venv\Scripts\Activate.ps1
```

Start Grammar Teacher API:

```powershell
.\run_api.ps1 -PythonExe .\.venv\Scripts\python.exe -IndexPath build/grammar_teacher/chunks.jsonl -ApiKey "replace-with-a-strong-key" -RateLimitPerMinute 60 -Port 8000
```

Start portal proxy:

```powershell
.\run_portal_backend.ps1 -PythonExe .\.venv\Scripts\python.exe -GrammarTeacherApiKey "replace-with-a-strong-key" -Port 8100 -Reload
```

## Health Checks

```powershell
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8100/health
Invoke-RestMethod http://localhost:8100/health/upstream
```

## API Contracts

Main API:

- `POST /ask` requires header `X-API-Key`
- Body:
```json
{
  "query": "subject verb agreement",
  "top_k": 3,
  "stage": "intermediate",
  "include_trace": true
}
```

Portal proxy API:

- `POST /portal/ask` (no Grammar Teacher key in frontend)
- Body:
```json
{
  "query": "subject verb agreement",
  "top_k": 3,
  "include_trace": true,
  "learner_id": "user-123",
  "session_id": "session-abc"
}
```

- Response includes:
  - `ok`
  - `topic`
  - `query_original`
  - `query_refined`
  - `query_sent_to_tutor`
  - `message`
  - `explanation_points`
  - `quick_check`
  - `reference`
  - `learner_band`
  - `stage`
  - `score`
  - `focus`
  - `pipeline_trace` (when `include_trace=true`)
  - `portal_context`

Behavior highlights:

- Daily lesson prompts (for example `What's the lesson of the day?`) use curated lesson cards with:
  - topic
  - rule
  - examples
  - usage tip
  - quick check
- Daily lessons rotate across topics during the day and persist state in:
  - `build/grammar_teacher/daily_lesson_state.json`
- Quick checks include `Answer` and `Why`.
- Oversized explanation text is summarized with word caps before response.

## Security and Controls

Grammar Teacher API:

- Auth: `X-API-Key` against `GRAMMAR_TEACHER_API_KEY`
- Rate limit: sliding window per `client_ip + api_key`
- Default limit: `60` requests/minute
- Request logs: `logs/api_requests.log`

Portal proxy:

- Keeps upstream API key server-side
- CORS configurable via `PORTAL_ALLOWED_ORIGINS`
- Request logs: `logs/portal_backend.log`

## Environment Variables

Grammar Teacher API:

- `GRAMMAR_TEACHER_INDEX`
- `GRAMMAR_TEACHER_API_KEY`
- `GRAMMAR_TEACHER_RATE_LIMIT_PER_MINUTE`
- `GRAMMAR_TEACHER_LOG_DIR`
- `GRAMMAR_TEACHER_MAX_EXPLANATION_WORDS` (default `120`)
- `GRAMMAR_TEACHER_MAX_EXPLANATION_WORDS_COMPOSITE` (default `170`)
- `GRAMMAR_TEACHER_MAX_POINT_WORDS` (default `48`)
- `GRAMMAR_TEACHER_MAX_POINT_WORDS_COMPOSITE` (default `58`)

Portal proxy:

- `GRAMMAR_TEACHER_ASK_URL`
- `GRAMMAR_TEACHER_HEALTH_URL`
- `GRAMMAR_TEACHER_API_KEY`
- `PORTAL_ALLOWED_ORIGINS`
- `PORTAL_LOG_DIR`
- `UPSTREAM_TIMEOUT_SECONDS`

## Validation Commands

```powershell
python -m unittest discover -s tests -v
python -m compileall grammar_teacher portal_backend_template tests
```

Last known passing unit test count: `32`.

## Known Limits

- OCR-derived text can still include noisy phrasing on some pages.
- Retrieval is lexical (no embedding reranker yet).
- Tiny LM output quality is not production-ready for standalone responses.
- Demo UI is intentionally minimal and local-only.

## Recommended Next Steps

1. Add semantic retrieval or reranking for better source precision (lexical retrieval still misses synonyms).
2. Add learner-memory persistence in portal proxy (`learner_id` + `session_id` storage).
3. Add API key rotation/multi-key support and optional JWT in proxy.
4. Add JSON structured logs export (SIEM-friendly format).
5. De-duplicate the corpus at build time so scores are not distorted by repeated chunks.

## Resume Checklist

1. Confirm `.venv` works (`python -c "import sys, encodings; print(sys.executable)"`).
2. Run unit tests.
3. Start both services.
4. Verify health endpoints.
5. Open `/demo` and run at least 3 question checks.
6. Inspect latest logs for 2xx/4xx/5xx patterns.

## Useful References

- `README.md`
- `GUIDE.md`
- `PORTAL_DEPLOYMENT_GUIDE.md`
- `LEARNING_PATH.md`
- `HANDOVER.md`
