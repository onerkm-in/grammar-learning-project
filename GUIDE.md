# Guide

`The Grammar Teacher` turns the PDFs in this folder into a local grammar tutor that can explain, quiz, motivate, and cite its sources.

## Prerequisites

- A full Python installation, not a Windows app alias and not an embedded runtime
- Tesseract OCR installed and available on `PATH` or at `C:\Program Files\Tesseract-OCR\tesseract.exe`
- A working virtual environment in `.venv`

## Quick Start

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -c "import sys, encodings; print(sys.executable)"
pip install -r requirements.txt
.\run_grammar_teacher.ps1 -PythonExe .\.venv\Scripts\python.exe -Resume
```

## What The Pipeline Produces

- `build/grammar_teacher/documents/<doc>/` with per-document manifests, pages, and chunks
- `build/grammar_teacher/chunks.jsonl` for retrieval-backed answers
- `build/grammar_teacher/references.json` and `curriculum.json` for source navigation
- `build/grammar_teacher/train.txt` and `val.txt` for model training
- `runs/the-grammar-teacher/model.pt` for the latest checkpoint

## Daily Commands

Full tutor pipeline:

```powershell
.\run_grammar_teacher.ps1 -PythonExe .\.venv\Scripts\python.exe -Resume
```

Run API + portal locally (recommended for end-to-end testing):

Terminal 1:

```powershell
.\run_api.ps1 -PythonExe .\.venv\Scripts\python.exe -IndexPath build/grammar_teacher/chunks.jsonl -ApiKey "replace-with-a-strong-key" -RateLimitPerMinute 60 -Host 127.0.0.1 -Port 8000
```

Terminal 2:

```powershell
.\run_portal_backend.ps1 -PythonExe .\.venv\Scripts\python.exe -GrammarTeacherApiKey "replace-with-a-strong-key" -Port 8100 -Reload
```

Browser:

- `http://127.0.0.1:8100/demo`

Reprocess one document with the latest extractor logic:

```powershell
python -m grammar_teacher.build_knowledge_base --input-dir . --output-dir build/grammar_teacher --resume --force-documents "SLM-III Sem-English -Grammar and Usage-1.pdf"
```

Run retrieval manually:

```powershell
python -m grammar_teacher.retrieve --index build/grammar_teacher/chunks.jsonl --query "subject verb agreement"
```

Run validation tests:

```powershell
python -m unittest discover -s tests -v
```

Current expected result: `32/32` unit tests passing (`tests/test_grammar_teacher.py`).

Run golden retrieval regression tests (requires the corpus index; slow — ~15 min):

```powershell
python -m unittest tests.test_retrieval_quality -v
```

Current expected result: `17/17` passing. These tests enforce no-duplicate results and content quality properties against the real `chunks.jsonl` index.

## Run API For Portal

Start the FastAPI service:

```powershell
.\run_api.ps1 -PythonExe .\.venv\Scripts\python.exe -IndexPath build/grammar_teacher/chunks.jsonl -ApiKey "replace-with-a-strong-key" -RateLimitPerMinute 60 -Host 0.0.0.0 -Port 8000
```

Health check:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

Ask endpoint:

```powershell
$body = @{
  query = "subject verb agreement"
  top_k = 3
  include_trace = $true
} | ConvertTo-Json
Invoke-RestMethod -Uri http://localhost:8000/ask -Method Post -ContentType "application/json" -Headers @{ "X-API-Key" = "replace-with-a-strong-key" } -Body $body
```

Trace learning tip:

- Check `query_original`, `query_refined`, and `pipeline_trace` in the response JSON to understand orchestration, retrieval, and synthesis stages.

Production wrapper summary:

- `POST /ask` requires `X-API-Key`
- Rate limit is enforced per minute
- Requests are logged to `logs/api_requests.log`
- Use [PORTAL_DEPLOYMENT_GUIDE.md](PORTAL_DEPLOYMENT_GUIDE.md) for deployment notes and learning walkthrough

Portal proxy template (recommended for frontend apps):

```powershell
.\run_portal_backend.ps1 -PythonExe .\.venv\Scripts\python.exe -GrammarTeacherApiKey "replace-with-a-strong-key" -Port 8100 -Reload
```

Then your portal can call:

- `POST http://localhost:8100/portal/ask`

## Learning Flow

1. Start with `starter` and `foundation` sources.
2. Move through `core` and `intermediate` grammar control.
3. Use quick quizzes to check understanding after each topic.
4. Use retrieval mode when you want source-backed explanations.
5. Progress into `advanced`, `writing`, `teacher`, and `exam` material.
6. Use daily lesson prompts (for example `What's the lesson of the day?`) for guided topic suggestions.

## Troubleshooting

- If Python fails with `No module named 'encodings'`, delete `.venv` and recreate it from a real Python install.
- If extraction fails on a page, the build continues and records the page as failed or OCR-recovered.
- If OCR output is noisy, reprocess the document later after improving OCR settings rather than trusting the text blindly.
- If generation is weak, increase training depth or rely more heavily on retrieval for factual answers.
- If API output still shows old behavior after code changes, restart both servers.

## Output Controls

Explanation length can be tuned with environment variables:

- `GRAMMAR_TEACHER_MAX_EXPLANATION_WORDS` (default `120`)
- `GRAMMAR_TEACHER_MAX_EXPLANATION_WORDS_COMPOSITE` (default `170`)
- `GRAMMAR_TEACHER_MAX_POINT_WORDS` (default `48`)
- `GRAMMAR_TEACHER_MAX_POINT_WORDS_COMPOSITE` (default `58`)

Daily lesson rotation state is stored in:

- `build/grammar_teacher/daily_lesson_state.json`
