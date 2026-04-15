# Learning Path (Beginner Friendly): The Grammar Teacher

This is written for first-time users. You do not need ML experience to follow this.

## 1) What This Project Really Is

`The Grammar Teacher` is a grammar assistant built from your local PDF books.

It works in 3 practical layers:

1. `Knowledge Build`: reads PDFs and creates searchable chunks.
2. `Tutor API`: finds relevant chunks and generates a teaching-style answer.
3. `Portal Demo`: a browser page where you can ask questions and inspect internals.

## 2) 10-Minute Local Run

Open Terminal 1:

```powershell
.venv\Scripts\Activate.ps1
.\run_api.ps1 -PythonExe .\.venv\Scripts\python.exe -IndexPath build/grammar_teacher/chunks.jsonl -ApiKey "replace-with-a-strong-key" -Port 8000
```

Open Terminal 2:

```powershell
.venv\Scripts\Activate.ps1
.\run_portal_backend.ps1 -PythonExe .\.venv\Scripts\python.exe -GrammarTeacherApiKey "replace-with-a-strong-key" -Port 8100 -Reload
```

Then open:

`http://127.0.0.1:8100/demo`

Important: use `127.0.0.1`, not `0.0.0.0` in browser URL.

## 3) How A Question Flows (Stage By Stage)

When you ask: `What is a noun?`

### Stage A: Input

- UI captures your exact text as `query_original`.

### Stage B: Question Processing

- System refines/polishes question into `query_refined`.
- Example:
  - Original: `What is a noun?`
  - Refined: `What are nouns? Explain in simple terms with examples.`

### Stage C: Orchestration

- Chooses runtime settings:
  - `top_k`
  - optional `stage` filter
  - trace on/off

### Stage D: Retrieval

- Tokenizes refined query into important words.
- Removes common stopwords.
- Scores chunks from `build/grammar_teacher/chunks.jsonl`.
- Picks top matches.

### Stage E: Synthesis

- Detects concept (`noun`, `verb`, etc).
- Decides response strategy (example: `concept_micro_lesson_first`, `composite_query_segmented`, `daily_lesson_recommendation`).
- Produces:
  - `explanation_points`
  - `quick_check`
  - safe `reference` (rule/introducer/year style, no raw PDF/page leak)

### Stage F: Response Cleanup

- Removes noisy characters.
- Summarizes oversized lines.
- Enforces explanation word limits so replies stay readable.

### Stage G: Final Response

- Returns JSON payload to portal.
- Portal shows learner-facing output plus internal trace (if enabled).

## 4) How To See Internal Pipeline In UI

In `http://127.0.0.1:8100/demo`:

1. Keep `Show pipeline trace` checked.
2. Ask a question.
3. Inspect:
   - `Question Processing`
   - `Pipeline Trace > Orchestration`
   - `Pipeline Trace > Retrieval`
   - `Pipeline Trace > Synthesis`

## 5) What Each Trace Section Means

### Orchestration

- High-level control info.
- Shows original question, refined question, stage filter, top_k.

### Retrieval

- Shows real words/tokens used for search.
- Shows how many chunks were considered.
- Shows top matched sources and scores.

### Synthesis

- Shows detected grammar concept.
- Shows whether beginner/easy mode activated.
- Shows strategy used to build explanation.
- Shows candidate sentences before final compact response.

## 5.1) Fusion/Composite Question Handling

The system now segregates multi-part questions into parts before final synthesis.

Example input:

`What is a noun and what is an adjective?`

What you should see:

- `query_segments_original`: `["What is a noun?", "what is an adjective?"]`
- `query_segments_refined`: refined form for each part
- synthesis strategy: `composite_query_segmented`
- explanation starts with:
  - `Part 1: ...`
  - `Part 2: ...`

This helps avoid mixing two grammar topics into one confusing response.

## 5.2) Daily Lesson Behavior

For prompts like:

`What's the lesson of the day?`

The tutor now uses curated lesson cards instead of retrieval snippets. The response includes:

- suggested topic
- core rule
- examples
- usage tip
- quick check with answer + why

Repeated daily-lesson asks rotate topics during the same day.

## 6) Quick API Test (No UI)

```powershell
$body = @{
  query = "What is a noun?"
  top_k = 3
  include_trace = $true
} | ConvertTo-Json

Invoke-RestMethod -Uri http://127.0.0.1:8100/portal/ask -Method Post -ContentType "application/json" -Body $body
```

Check these fields in output:

- `query_original`
- `query_refined`
- `pipeline_trace.orchestration`
- `pipeline_trace.retrieval.tokens_used`
- `pipeline_trace.synthesis.strategy`

## 7) If Output Looks Confusing

Do this in order:

1. Ask simple concept questions first (`noun`, `verb`, `tense`).
2. Keep `top_k = 3`.
3. Use stage filter `foundation` for beginner flow.
4. Rebuild index if you changed PDF set:

```powershell
python -m grammar_teacher.build_knowledge_base --input-dir . --output-dir build/grammar_teacher --resume
```

5. Run tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## 8) Glossary (Very Simple)

- `Chunk`: a small text piece cut from a source PDF.
- `top_k`: how many top matches we inspect.
- `Stage`: learning level bucket (`starter`, `foundation`, `intermediate`, etc).
- `Reference`: user-safe source label (book/author style).
- `Reference`: user-safe rule attribution (`Rule`, `Introduced by`, `In use since`).
- `Trace`: internal debug visibility for learning and verification.

## 9) Where To Read Next

- `GUIDE.md` for operation commands
- `PORTAL_DEPLOYMENT_GUIDE.md` for deployment/security
- `HANDOVER_REFERENCE.md` for current technical status
