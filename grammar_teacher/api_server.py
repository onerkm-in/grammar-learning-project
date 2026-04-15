from __future__ import annotations

import logging
import os
import secrets
import threading
import time
import uuid
from collections import defaultdict, deque
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from grammar_teacher.tutor import build_answer_payload


DEFAULT_INDEX = Path("build/grammar_teacher/chunks.jsonl")
INDEX_PATH = Path(os.environ.get("GRAMMAR_TEACHER_INDEX", str(DEFAULT_INDEX)))
API_KEY = os.environ.get("GRAMMAR_TEACHER_API_KEY", "").strip()
RATE_LIMIT_PER_MINUTE = int(os.environ.get("GRAMMAR_TEACHER_RATE_LIMIT_PER_MINUTE", "60"))
LOG_DIR = Path(os.environ.get("GRAMMAR_TEACHER_LOG_DIR", "logs"))

app = FastAPI(
    title="The Grammar Teacher API",
    description="Portal-facing API for retrieval-backed grammar tutoring.",
    version="1.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _build_logger() -> logging.Logger:
    logger = logging.getLogger("grammar_teacher.api")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        LOG_DIR / "api_requests.log",
        maxBytes=5_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s request_id=%(request_id)s method=%(method)s "
        "path=%(path)s status=%(status)s ip=%(ip)s duration_ms=%(duration_ms)s message=%(message)s"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return logger


LOGGER = _build_logger()


class SlidingWindowRateLimiter:
    def __init__(self, max_requests: int, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> tuple[bool, int]:
        if now is None:
            now = time.time()
        earliest = now - self.window_seconds

        with self._lock:
            bucket = self._events[key]
            while bucket and bucket[0] <= earliest:
                bucket.popleft()

            if len(bucket) >= self.max_requests:
                retry_after = max(1, int(self.window_seconds - (now - bucket[0])))
                return False, retry_after

            bucket.append(now)
            return True, 0


RATE_LIMITER = SlidingWindowRateLimiter(max_requests=RATE_LIMIT_PER_MINUTE, window_seconds=60)


class AskRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Learner grammar question.")
    top_k: int = Field(3, ge=1, le=10, description="How many chunks to retrieve before selecting the best.")
    stage: str | None = Field(None, description="Optional curriculum stage filter (starter/foundation/etc).")
    include_trace: bool = Field(False, description="When true, include orchestration/retrieval/synthesis trace details.")


def _request_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "").strip()
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _log_request(
    *,
    request_id: str,
    method: str,
    path: str,
    status: int,
    ip: str,
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
            "ip": ip,
            "duration_ms": f"{duration_ms:.2f}",
        },
    )


@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    ip = _request_ip(request)
    start = time.perf_counter()

    try:
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Request-ID"] = request_id
        _log_request(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            ip=ip,
            duration_ms=duration_ms,
            message="request_complete",
        )
        return response
    except Exception:
        duration_ms = (time.perf_counter() - start) * 1000
        _log_request(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status=500,
            ip=ip,
            duration_ms=duration_ms,
            message="request_failed",
        )
        raise


def authorize_and_rate_limit(request: Request) -> None:
    if not API_KEY:
        raise HTTPException(
            status_code=500,
            detail="Server is missing GRAMMAR_TEACHER_API_KEY configuration.",
        )

    provided_key = request.headers.get("x-api-key", "").strip()
    if not provided_key or not secrets.compare_digest(provided_key, API_KEY):
        raise HTTPException(status_code=401, detail="Invalid API key.")

    client_key = f"{_request_ip(request)}:{provided_key}"
    allowed, retry_after = RATE_LIMITER.allow(client_key)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "service": "the-grammar-teacher",
        "index_path": str(INDEX_PATH),
        "index_exists": INDEX_PATH.exists(),
        "auth_enabled": bool(API_KEY),
        "rate_limit_per_minute": RATE_LIMIT_PER_MINUTE,
        "log_file": str((LOG_DIR / "api_requests.log").resolve()),
    }


@app.post("/ask", dependencies=[Depends(authorize_and_rate_limit)])
def ask(request: AskRequest) -> dict:
    payload = build_answer_payload(
        index=INDEX_PATH,
        query=request.query.strip(),
        top_k=request.top_k,
        stage=request.stage,
        include_trace=request.include_trace,
    )
    return payload
