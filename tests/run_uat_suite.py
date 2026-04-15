from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import time
from textwrap import shorten
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from grammar_teacher.tutor import build_answer_payload


DEFAULT_BANKS_DIR = Path(__file__).resolve().parent
DEFAULT_INDEX_PATH = ROOT_DIR / "build" / "grammar_teacher" / "chunks.jsonl"
DEFAULT_REPORT_PATH = Path(__file__).resolve().with_name("uat_report.json")
DEFAULT_BANK_GLOB = "uat_question_bank_*.json"


@dataclass
class CaseResult:
    bank_file: str
    bank_name: str
    case_id: str
    query: str
    expected_strategy: str | None
    actual_strategy: str | None = None
    status: str = "error"
    message: str = ""
    trace: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "bank_file": self.bank_file,
            "bank_name": self.bank_name,
            "case_id": self.case_id,
            "query": self.query,
            "expected_strategy": self.expected_strategy,
            "actual_strategy": self.actual_strategy,
            "status": self.status,
            "message": self.message,
            "trace": self.trace,
        }


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def discover_bank_files(
    banks_dir: Path,
    bank_glob: str,
    explicit_files: list[Path],
) -> list[Path]:
    files: list[Path] = []
    files.extend(sorted(banks_dir.glob(bank_glob)))
    files.extend(explicit_files)

    unique_files: list[Path] = []
    seen: set[str] = set()
    for path in files:
        resolved = str(path.resolve())
        if resolved in seen:
            continue
        seen.add(resolved)
        unique_files.append(path)
    return unique_files


def normalize_bank_cases(bank_path: Path, payload: Any) -> list[dict[str, Any]]:
    bank_name = bank_path.stem
    default_stage = None
    default_top_k = None
    default_expected = None
    default_query_prefix = None

    if isinstance(payload, dict):
        bank_name = str(payload.get("name") or bank_name)
        default_stage = payload.get("stage")
        default_top_k = payload.get("top_k")
        default_expected = payload.get("expected_strategy")
        default_query_prefix = payload.get("query_prefix")

        for key in ("cases", "questions", "items", "uat_cases"):
            if key in payload:
                payload = payload[key]
                break
        else:
            if "query" in payload:
                payload = [payload]
            else:
                raise ValueError(
                    "Bank file must contain a list of cases or an object with a 'cases' field."
                )

    if not isinstance(payload, list):
        raise ValueError("Bank payload must be a list of cases or a mapping with cases.")

    cases: list[dict[str, Any]] = []
    for index, raw_case in enumerate(payload, start=1):
        if not isinstance(raw_case, dict):
            raise ValueError(f"Case {index} in {bank_path.name} is not an object.")

        query = str(raw_case.get("query") or raw_case.get("prompt") or "").strip()
        if default_query_prefix and query and not query.startswith(default_query_prefix):
            query = f"{default_query_prefix}{query}"
        if not query:
            raise ValueError(f"Case {index} in {bank_path.name} is missing a query.")

        expected_strategy = raw_case.get("expected_strategy")
        if expected_strategy is None:
            expected_strategy = raw_case.get("expected")
        if expected_strategy is None:
            expected_strategy = raw_case.get("strategy")
        if expected_strategy is None:
            expected_strategy = default_expected

        case_id = str(raw_case.get("id") or raw_case.get("case_id") or f"{bank_path.stem}-{index}")
        stage = raw_case.get("stage", default_stage)
        top_k = raw_case.get("top_k", default_top_k)
        notes = raw_case.get("notes") or ""

        cases.append(
            {
                "bank_name": bank_name,
                "bank_file": str(bank_path),
                "case_id": case_id,
                "query": query,
                "expected_strategy": expected_strategy,
                "stage": stage,
                "top_k": top_k,
                "notes": notes,
            }
        )

    return cases


def run_case(index_path: Path, case: dict[str, Any]) -> CaseResult:
    expected_strategy = case.get("expected_strategy")
    result = CaseResult(
        bank_file=case["bank_file"],
        bank_name=case["bank_name"],
        case_id=case["case_id"],
        query=case["query"],
        expected_strategy=str(expected_strategy) if expected_strategy is not None else None,
    )

    if not expected_strategy:
        result.status = "error"
        result.message = "missing expected_strategy"
        return result

    try:
        top_k = int(case.get("top_k") or 3)
        stage = case.get("stage")
        payload = build_answer_payload(
            index_path,
            case["query"],
            top_k=top_k,
            stage=stage,
            include_trace=True,
        )
        trace = payload.get("pipeline_trace") or {}
        synthesis = trace.get("synthesis") or {}
        actual_strategy = synthesis.get("strategy")
        if actual_strategy is None:
            raise RuntimeError("missing pipeline_trace.synthesis.strategy")

        result.actual_strategy = str(actual_strategy)
        result.trace = trace
        result.status = "pass" if str(expected_strategy) == str(actual_strategy) else "fail"
        if result.status == "fail":
            result.message = "expected strategy did not match trace strategy"
    except Exception as exc:  # noqa: BLE001 - report the failure without aborting the suite.
        result.status = "error"
        result.message = f"{type(exc).__name__}: {exc}"

    return result


def print_table(results: list[CaseResult]) -> None:
    if not results:
        print("No UAT cases executed.")
        return

    headers = ["STATUS", "BANK", "CASE", "EXPECTED", "ACTUAL", "QUERY"]
    widths = [8, 22, 18, 22, 22, 44]
    row_fmt = " | ".join(f"{{:{width}}}" for width in widths)
    separator = "-+-".join("-" * width for width in widths)

    print(row_fmt.format(*headers))
    print(separator)
    for item in results:
        print(
            row_fmt.format(
                shorten(item.status, width=widths[0] - 1, placeholder="..."),
                shorten(item.bank_name, width=widths[1] - 1, placeholder="..."),
                shorten(item.case_id, width=widths[2] - 1, placeholder="..."),
                shorten(item.expected_strategy or "", width=widths[3] - 1, placeholder="..."),
                shorten(item.actual_strategy or "", width=widths[4] - 1, placeholder="..."),
                shorten(item.query, width=widths[5] - 1, placeholder="..."),
            )
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run UAT cases against The Grammar Teacher tutor.")
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX_PATH)
    parser.add_argument("--banks-dir", type=Path, default=DEFAULT_BANKS_DIR)
    parser.add_argument("--bank-glob", type=str, default=DEFAULT_BANK_GLOB)
    parser.add_argument(
        "--question-bank",
        type=Path,
        action="append",
        default=[],
        help="Explicit bank file path. Can be supplied multiple times.",
    )
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    args = parser.parse_args()

    report_path = args.report_path
    report_path.parent.mkdir(parents=True, exist_ok=True)
    started_at = time.monotonic()

    summary: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "index_path": str(args.index.resolve()),
        "bank_files": [],
        "case_count": 0,
        "pass_count": 0,
        "fail_count": 0,
        "error_count": 0,
        "runtime_seconds": None,
        "results": [],
    }

    if not args.index.exists():
        summary["error_count"] = 1
        summary["runtime_seconds"] = round(time.monotonic() - started_at, 3)
        summary["results"].append(
            {
                "status": "error",
                "message": f"Index file not found: {args.index}",
                "bank_file": None,
                "bank_name": None,
                "case_id": None,
                "query": None,
            }
        )
        report_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Index missing: {args.index}")
        print(f"Report written to {report_path}")
        return 2

    bank_files = discover_bank_files(args.banks_dir, args.bank_glob, args.question_bank)
    summary["bank_files"] = [str(path.resolve()) for path in bank_files]

    if not bank_files:
        summary["runtime_seconds"] = round(time.monotonic() - started_at, 3)
        report_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        print("No UAT question banks found.")
        print(f"Report written to {report_path}")
        return 0

    all_results: list[CaseResult] = []
    for bank_path in bank_files:
        try:
            payload = load_json(bank_path)
            cases = normalize_bank_cases(bank_path, payload)
        except Exception as exc:  # noqa: BLE001 - keep running other banks.
            all_results.append(
                CaseResult(
                    bank_file=str(bank_path),
                    bank_name=bank_path.stem,
                    case_id="bank-load",
                    query="",
                    expected_strategy=None,
                    status="error",
                    message=f"{type(exc).__name__}: {exc}",
                )
            )
            continue

        for case in cases:
            all_results.append(run_case(args.index, case))

    for item in all_results:
        if item.status == "pass":
            summary["pass_count"] += 1
        elif item.status == "fail":
            summary["fail_count"] += 1
        else:
            summary["error_count"] += 1

    summary["case_count"] = len(all_results)
    summary["results"] = [item.to_dict() for item in all_results]
    summary["runtime_seconds"] = round(time.monotonic() - started_at, 3)

    report_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print_table(all_results)
    print(
        f"Summary: {summary['pass_count']} pass, {summary['fail_count']} fail, "
        f"{summary['error_count']} error, {summary['case_count']} total"
    )
    print(f"Report written to {report_path}")

    return 0 if summary["fail_count"] == 0 and summary["error_count"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
