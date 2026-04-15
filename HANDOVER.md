# Handover

This project is in a usable state and can be continued directly from the working `.venv` in this repository.

## Current State

- Date: `2026-04-01`
- `25` PDFs processed into `build/grammar_teacher/`
- Knowledge base contains `11,589` chunks
- OCR fallback is enabled and recovered unreadable pages from `SLM-III Sem-English -Grammar and Usage-1.pdf`
- Working model checkpoints exist in `runs/`
- Main API: `grammar_teacher/api_server.py` (launcher: `run_api.ps1`)
- Portal proxy template: `portal_backend_template/app.py` (launcher: `run_portal_backend.ps1`)
- Unit tests: `32/32` passing (`tests/test_grammar_teacher.py`)
- Golden regression tests added: `tests/test_retrieval_quality.py` (17 tests, require corpus index)

## Retrieval Quality Improvements (2026-04-01)

Three issues were found and fixed in `grammar_teacher/retrieve.py`:

1. **Duplicate results** — 1,969 of 11,589 chunks were exact text duplicates (some appearing up to 21×).
   The `retrieve()` function now deduplicates by MD5 hash before returning top-k, ensuring each distinct
   text appears at most once in results.

2. **Noisy/navigation chunk scoring** — Exercise answer keys (1-a, 2-b patterns), book back-index entries
   (term · page_number), dotted-leader TOC entries, and list-style navigation pages were scoring on par
   with explanatory content. A `_quality_multiplier()` function now applies penalties (0.1–0.75) to these
   chunk types, which are multiplied into the final score in `score_chunk()`.

3. **Golden regression tests** — `tests/test_retrieval_quality.py` was added with 17 tests covering:
   - No duplicate texts in top-k for 6 core queries
   - Known noisy chunk types receive the expected low multipliers
   - Content quality: index entries do not appear at rank 1, core topics return results with relevant text

## Main Entry Points

- `README.md` for the shortest orientation path
- `HANDOVER_REFERENCE.md` as the primary continuation document for agents/people
- `GUIDE.md` for setup, daily use, and troubleshooting
- `PORTAL_DEPLOYMENT_GUIDE.md` for production API setup and portal integration
- `ARCHITECTURE.md` for design and data flow
- `THE_GRAMMAR_TEACHER.md` for product scope and teaching contract

## Key Commands

```powershell
.venv\Scripts\Activate.ps1
.\run_grammar_teacher.ps1 -PythonExe .\.venv\Scripts\python.exe -Resume
python -m grammar_teacher.retrieve --index build/grammar_teacher/chunks.jsonl --query "subject verb agreement"
.\run_api.ps1 -PythonExe .\.venv\Scripts\python.exe -IndexPath build/grammar_teacher/chunks.jsonl -ApiKey "replace-with-a-strong-key" -RateLimitPerMinute 60 -Port 8000
.\run_portal_backend.ps1 -PythonExe .\.venv\Scripts\python.exe -GrammarTeacherApiKey "replace-with-a-strong-key" -Port 8100 -Reload
python -m unittest discover -s tests -v
```

## What Works

- Sequential PDF ingestion with resume support
- OCR fallback for pages that native PDF extraction cannot recover
- Per-document manifests, page records, and chunk generation
- Curriculum, teacher profile, references, and session template generation
- Small-model training and sample generation
- Retrieval against processed chunks with source-aware output
- Portal-ready HTTP endpoints (`/health`, `/ask`) for integration
- API key authentication for `/ask`
- Sliding-window rate limiting and request logging for API traffic
- Daily lesson intent routing (`What's the lesson of the day?`) with curated lessons
- Rotating daily lesson topics via persisted state
- Quick checks now include answer + short why explanation
- Oversized explanations are summarized and word-limited automatically
- Unit and smoke validation

## Known Limits

- OCR text is slower to produce and noisier than native extraction.
- The tiny model is best used as a tutoring and phrasing layer, not as a standalone knowledge source.
- Retrieval is still lexical and can be improved with embeddings or reranking later.

## Best Next Upgrades

- Add OCR text cleanup for OCR-heavy documents.
- Strengthen retrieval with semantic search or reranking (lexical retrieval still misses topic synonyms).
- Persist learner memory across sessions in a live tutor runtime.
- Upgrade or fine-tune the tutoring model once the retrieval path is stable.
- Add user-selectable response style presets (brief, normal, detailed).
- Add semantic quality scoring for explanation points before final output.
- De-duplicate the corpus at build time (not just at query time) to improve scoring fidelity.
- Add API key rotation/multi-key support and optional JWT in portal proxy.
