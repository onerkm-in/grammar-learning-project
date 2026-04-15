# The Grammar Teacher

This repository builds a local, source-backed grammar tutor from the PDF collection in this folder. It combines sequential PDF ingestion, OCR fallback, retrieval, and a small language model so the tutor can teach clearly while still pointing back to real source material.

## Start Here

- [GUIDE.md](GUIDE.md) for setup, daily commands, and troubleshooting
- [HANDOVER_REFERENCE.md](HANDOVER_REFERENCE.md) as the single continuation reference for agents/people
- [PORTAL_DEPLOYMENT_GUIDE.md](PORTAL_DEPLOYMENT_GUIDE.md) for API auth, rate limit, logging, and portal integration
- [LEARNING_PATH.md](LEARNING_PATH.md) to learn the full project flow step by step
- [portal_backend_template/README.md](portal_backend_template/README.md) for a plug-in backend proxy your portal can call safely
- [ARCHITECTURE.md](ARCHITECTURE.md) for the system design and data flow
- [HANDOVER.md](HANDOVER.md) for current project status, validation, and next work
- [THE_GRAMMAR_TEACHER.md](THE_GRAMMAR_TEACHER.md) for the product vision and learning contract

## Current Snapshot

- Date: `2026-04-01`
- Corpus build: `25` source PDFs processed
- Knowledge base: `11,589` chunks in `build/grammar_teacher/chunks.jsonl`
- OCR fallback: enabled for pages that `pypdf` cannot decode
- Main API: FastAPI (`/health`, `/ask`) with API key auth + rate limit + logs
- Portal backend template: `/health`, `/health/upstream`, `/portal/ask`, `/demo`
- Unit tests: `32/32` passing (`tests/test_grammar_teacher.py`)
- Golden retrieval tests: `17/17` passing (`tests/test_retrieval_quality.py`)

## Recent Updates

**2026-04-01 — Retrieval quality improvements:**
- Deduplication: `retrieve()` now deduplicates by text hash; 1,969 exact-duplicate chunks in the corpus no longer waste top-k result slots.
- Quality scoring: `score_chunk()` now applies a `_quality_multiplier()` to discount exercise answer keys, book back-index entries, dotted-leader TOC pages, and list-style navigation chunks.
- Golden regression tests added in `tests/test_retrieval_quality.py` covering no-duplicate and content-quality properties against the live corpus.

**Earlier:**
- Daily lesson intent: `What's the lesson of the day?` now uses curated topic cards, not noisy retrieval snippets.
- Daily lesson rotation: repeated asks rotate through topics within the same day.
- Quick checks now include both:
  - `Answer`
  - short `Why` explanation
- Oversized explanations are auto-summarized and capped by word budget.

## Fast Path

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
.\run_api.ps1 -PythonExe .\.venv\Scripts\python.exe -ApiKey "replace-with-a-strong-key" -IndexPath build/grammar_teacher/chunks.jsonl -Port 8000
.\run_portal_backend.ps1 -PythonExe .\.venv\Scripts\python.exe -GrammarTeacherApiKey "replace-with-a-strong-key" -Port 8100 -Reload
```

Open in browser:

- `http://127.0.0.1:8100/demo`

Use `127.0.0.1` (or `localhost`) in browser URLs, not `0.0.0.0`.
