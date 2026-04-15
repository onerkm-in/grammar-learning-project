# UAT Runner

The UAT runner checks grammar tutor traces against one or more question banks and writes a JSON report for later review.

## Expected bank format

By default it loads every file matching `tests/uat_question_bank_*.json`.
You can also pass explicit files with `--question-bank`; those are combined with the discovered files.

Supported shapes:

- A list of case objects
- A mapping with `cases`, `questions`, `items`, or `uat_cases`
- A single case object with `query`

Each case should provide:

- `query`
- `expected_strategy`

Optional fields:

- `id` or `case_id`
- `stage`
- `top_k`
- `notes`

## Run

```powershell
python tests/run_uat_suite.py
```

## Output

The runner writes a JSON report to:

```powershell
tests/uat_report.json
```

It also prints a compact console table with pass/fail status for each case and exits non-zero when any case fails or errors.

## Current Baseline

- Latest known full-suite report: `tests/uat_report_after5.json`
- Latest known status: `110 pass, 0 fail, 0 error`

The UAT suite validates strategy routing traces (for example composite segmentation and sentence parsing), not full semantic scoring of explanation text.
