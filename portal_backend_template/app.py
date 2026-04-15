from __future__ import annotations

import logging
import os
import time
import uuid
from logging.handlers import RotatingFileHandler
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field

from grammar_teacher.retrieve import expand_query_tokens, tokenize
from grammar_teacher.tutor import refine_query, split_composite_query


UPSTREAM_ASK_URL = os.environ.get("GRAMMAR_TEACHER_ASK_URL", "http://127.0.0.1:8000/ask")
UPSTREAM_HEALTH_URL = os.environ.get("GRAMMAR_TEACHER_HEALTH_URL", "http://127.0.0.1:8000/health")
UPSTREAM_API_KEY = os.environ.get("GRAMMAR_TEACHER_API_KEY", "").strip()
PORTAL_ALLOWED_ORIGINS = os.environ.get("PORTAL_ALLOWED_ORIGINS", "*")
PORTAL_LOG_DIR = Path(os.environ.get("PORTAL_LOG_DIR", "logs"))
UPSTREAM_TIMEOUT_SECONDS = float(os.environ.get("UPSTREAM_TIMEOUT_SECONDS", "20"))
DEMO_PAGE_PATH = Path(__file__).with_name("static") / "index.html"

app = FastAPI(
    title="Portal Backend Template",
    description="Minimal backend proxy that forwards safe requests to The Grammar Teacher API.",
    version="1.0.0",
)

allow_origins = [origin.strip() for origin in PORTAL_ALLOWED_ORIGINS.split(",") if origin.strip()]
if not allow_origins:
    allow_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)


def _build_logger() -> logging.Logger:
    logger = logging.getLogger("portal_backend")
    if logger.handlers:
        return logger

    PORTAL_LOG_DIR.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        PORTAL_LOG_DIR / "portal_backend.log",
        maxBytes=2_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s request_id=%(request_id)s method=%(method)s "
            "path=%(path)s status=%(status)s duration_ms=%(duration_ms)s message=%(message)s"
        )
    )
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    return logger


LOGGER = _build_logger()


class PortalAskRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Learner question from portal UI.")
    top_k: int = Field(3, ge=1, le=10, description="How many retrieval chunks to inspect.")
    stage: str | None = Field(None, description="Optional curriculum stage.")
    include_trace: bool = Field(False, description="When true, include internal pipeline trace for debugging/demo.")
    learner_id: str | None = Field(None, description="Optional portal learner identifier.")
    session_id: str | None = Field(None, description="Optional portal session identifier.")


def _build_local_trace_fallback(request: PortalAskRequest, result: dict) -> dict:
    original = (result.get("query_original") or request.query or "").strip()
    refined = (result.get("query_refined") or refine_query(original)).strip()
    segments_original = result.get("query_segments_original") or split_composite_query(original)
    segments_refined = result.get("query_segments_refined") or [refine_query(segment) for segment in segments_original]
    tokens = tokenize(refined)
    expanded_tokens = expand_query_tokens(tokens)
    final_points = result.get("explanation_points", [])
    reference = result.get("reference")

    top_matches: list[dict] = []
    if reference:
        top_matches.append(
            {
                "rank": 1,
                "score": result.get("score"),
                "reference": reference,
                "stage": result.get("stage"),
                "learner_band": result.get("learner_band"),
                "focus": result.get("focus", []),
            }
        )

    return {
        "orchestration": {
            "received_query": original,
            "refined_query": refined,
            "is_composite_query": len(segments_refined) > 1,
            "query_segments_original": segments_original,
            "query_segments_refined": segments_refined,
            "stage_filter": request.stage,
            "top_k": request.top_k,
        },
        "retrieval": {
            "tokens_used": tokens[:20],
            "expanded_tokens_used": expanded_tokens[:30],
            "chunks_total": None,
            "chunks_after_stage_filter": None,
            "top_matches": top_matches,
            "trace_source": "portal_fallback",
        },
        "synthesis": {
            "concept_detected": None,
            "easy_mode": None,
            "strategy": "upstream_trace_unavailable_portal_fallback",
            "candidate_sentences": [],
            "final_points_count": len(final_points) if isinstance(final_points, list) else 0,
        },
    }


def _ensure_observability_fields(request: PortalAskRequest, result: dict) -> dict:
    original = (result.get("query_original") or request.query or "").strip()
    refined = (result.get("query_refined") or refine_query(original)).strip()
    segments_original = result.get("query_segments_original") or split_composite_query(original)
    segments_refined = result.get("query_segments_refined") or [refine_query(segment) for segment in segments_original]

    result["query_original"] = original
    result["query_refined"] = refined
    result["query_sent_to_tutor"] = refined
    result["query_segments_original"] = segments_original
    result["query_segments_refined"] = segments_refined

    if request.include_trace and not isinstance(result.get("pipeline_trace"), dict):
        result["pipeline_trace"] = _build_local_trace_fallback(request, result)
    return result


def _log(
    *,
    request_id: str,
    method: str,
    path: str,
    status: int,
    duration_ms: float,
    message: str,
) -> None:
    LOGGER.info(
        message,
        extra={
            "request_id": request_id,
            "method": method,
            "path": path,
            "status": status,
            "duration_ms": f"{duration_ms:.2f}",
        },
    )


@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    started = time.perf_counter()
    try:
        response = await call_next(request)
        duration_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = request_id
        _log(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=duration_ms,
            message="request_complete",
        )
        return response
    except Exception:
        duration_ms = (time.perf_counter() - started) * 1000
        _log(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status=500,
            duration_ms=duration_ms,
            message="request_failed",
        )
        raise


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "service": "portal-backend-template",
        "upstream_ask_url": UPSTREAM_ASK_URL,
        "upstream_health_url": UPSTREAM_HEALTH_URL,
        "has_upstream_api_key": bool(UPSTREAM_API_KEY),
    }


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/demo")


@app.get("/demo", include_in_schema=False)
def demo() -> FileResponse:
    if not DEMO_PAGE_PATH.exists():
        raise HTTPException(status_code=500, detail="Demo page file is missing.")
    return FileResponse(DEMO_PAGE_PATH)


@app.get("/health/upstream")
def health_upstream() -> dict:
    try:
        with httpx.Client(timeout=UPSTREAM_TIMEOUT_SECONDS) as client:
            response = client.get(UPSTREAM_HEALTH_URL)
            return {
                "ok": response.status_code == 200,
                "status_code": response.status_code,
                "upstream": response.json() if response.headers.get("content-type", "").startswith("application/json") else None,
            }
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Unable to reach upstream health endpoint: {exc}")


@app.post("/portal/ask")
def portal_ask(request: PortalAskRequest) -> dict:
    if not UPSTREAM_API_KEY:
        raise HTTPException(status_code=500, detail="Server misconfigured: GRAMMAR_TEACHER_API_KEY is missing.")

    payload = {
        "query": request.query.strip(),
        "top_k": request.top_k,
        "stage": request.stage,
        "include_trace": request.include_trace,
    }
    payload = {key: value for key, value in payload.items() if value is not None}

    headers = {
        "X-API-Key": UPSTREAM_API_KEY,
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=UPSTREAM_TIMEOUT_SECONDS) as client:
            upstream = client.post(UPSTREAM_ASK_URL, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Upstream request failed: {exc}")

    if upstream.status_code >= 400:
        detail = None
        try:
            detail = upstream.json()
        except ValueError:
            detail = {"message": upstream.text}
        raise HTTPException(status_code=502, detail={"upstream_status": upstream.status_code, "upstream_error": detail})

    result = upstream.json()
    if isinstance(result, dict):
        result = _ensure_observability_fields(request, result)
    result["portal_context"] = {
        "learner_id": request.learner_id,
        "session_id": request.session_id,
    }
    return result
