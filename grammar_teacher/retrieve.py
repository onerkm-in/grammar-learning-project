from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

from grammar_teacher.source_catalog import STAGE_ORDER


TOKEN_RE = re.compile(r"[a-zA-Z']+")
# Patterns that indicate low-quality chunks (exercise keys, TOC entries, headers).
_EXERCISE_ANSWER_RE = re.compile(r"\b\d+\s*[-–]\s*[a-eA-E]\b")  # "1-a", "3 - b"
_TOC_ENTRY_RE = re.compile(r"\.{4,}\s*\d+")                       # "Section....... 14"
_PAGE_REF_RE = re.compile(r"--\s*\d{1,4}\s*$", re.MULTILINE)     # "-- 208" at line end
# Index entries: "term [middle-dot U+00B7 / em-dash / en-dash] page-number" (book back-indexes).
_INDEX_ENTRY_RE = re.compile(r"\S.*?[\u00b7—–\-]{1,2}\s*\d{1,4}")
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "have",
    "how",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "their",
    "this",
    "to",
    "what",
    "which",
    "with",
}
QUERY_HINTS: dict[tuple[str, ...], tuple[str, ...]] = {
    ("parts", "of", "speech"): ("noun", "pronoun", "verb", "adjective", "adverb"),
    ("subject", "verb", "agreement"): ("subject", "agreement", "concord"),
    ("direct", "indirect", "speech"): ("reported", "speech", "narration"),
    ("mood", "modality"): ("modal", "modals", "possibility", "obligation"),
    ("active", "passive"): ("voice", "passive"),
    ("sentence", "transformation"): ("rewrite", "change", "transform"),
    ("composition",): ("writing", "paragraph", "essay"),
    ("modals",): ("modal", "permission", "ability"),
}


def tokenize(text: str) -> list[str]:
    """Tokenize and trim stopwords so retrieval focuses on content words."""
    return [token for token in TOKEN_RE.findall(text.lower()) if token not in STOPWORDS]


def expand_query_tokens(tokens: list[str]) -> list[str]:
    """Add a few grammar-specific synonyms when a query clearly implies them."""
    expanded = list(tokens)
    token_set = set(tokens)
    for phrase, additions in QUERY_HINTS.items():
        if all(token in token_set for token in phrase):
            expanded.extend(additions)
    return expanded


def score_overlap(terms: Counter[str], chunk_terms: Counter[str]) -> float:
    return float(sum(min(terms[token], chunk_terms[token]) for token in terms))


def _quality_multiplier(chunk: dict) -> float:
    """Return a [0, 1] multiplier that discounts low-quality chunks.

    Penalises:
    - Very short chunks (< 15 words) — mostly headers/footers.
    - Exercise answer-key content ("1-a, 2-b, 3-c" patterns).
    - Table-of-contents / index entries (dotted leaders or "-- 208" page refs).
    - Book back-index entries ("term · page_number" lines).
    - List-style TOC pages (almost every line is a short label).
    """
    text = chunk.get("text", "")
    words = TOKEN_RE.findall(text)
    word_count = len(words)

    if word_count < 8:
        return 0.1
    if word_count < 15:
        return 0.5

    # Exercise answer-key: use a quick first-pass before running findall.
    if "-" in text:
        answer_key_hits = len(_EXERCISE_ANSWER_RE.findall(text))
        if answer_key_hits >= 3:
            return 0.3
        if answer_key_hits >= 1:
            return 0.7

    # Dotted TOC / end-of-line page refs.
    toc_hits = 0
    if "." in text:
        toc_hits += len(_TOC_ENTRY_RE.findall(text))
    if "--" in text:
        toc_hits += len(_PAGE_REF_RE.findall(text))
    if toc_hits >= 3:
        return 0.3
    if toc_hits >= 1:
        return 0.75

    # Book back-index entries (term · page): only run the regex if the separator is present.
    _INDEX_SEPARATORS = ("\u00b7", "\u2014", "\u2013")
    if any(sep in text for sep in _INDEX_SEPARATORS):
        index_hits = len(_INDEX_ENTRY_RE.findall(text))
        if index_hits >= 4:
            return 0.3
        if index_hits >= 2:
            return 0.6

    # List-style TOC/index pages: almost every line is a short label (navigation content).
    # Require the first 4 non-empty lines to also be short to avoid penalising chunks
    # that start with real explanatory sentences and then include a table or list.
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) >= 8:
        first_lines_short = sum(1 for line in lines[:4] if len(line.split()) <= 3)
        if first_lines_short >= 3:
            short_lines = sum(1 for line in lines if len(line.split()) <= 3)
            if short_lines / len(lines) >= 0.80:
                return 0.3

    return 1.0


def load_chunks(path: Path) -> list[dict]:
    chunks: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            chunks.append(json.loads(line))
    return chunks


def score_chunk(query_terms: Counter[str], chunk: dict) -> float:
    """Score chunks using text overlap, metadata overlap, and light heuristic bonuses."""
    chunk_terms = Counter(tokenize(chunk["text"]))
    metadata_terms = Counter(
        tokenize(
            " ".join(
                [
                    chunk.get("reference", ""),
                    chunk.get("filename", ""),
                    chunk.get("stage", ""),
                    chunk.get("learner_band", ""),
                    " ".join(chunk.get("focus", [])),
                ]
            )
        )
    )

    overlap = score_overlap(query_terms, chunk_terms)
    metadata_overlap = score_overlap(query_terms, metadata_terms)
    density = overlap / max(len(chunk_terms), 1)
    focus_terms = Counter(tokenize(" ".join(chunk.get("focus", []))))
    focus_bonus = 0.2 * score_overlap(query_terms, focus_terms)
    phrase_bonus = 0.0
    raw_text = f"{chunk.get('reference', '')} {chunk.get('filename', '')} {chunk.get('text', '')}".lower()
    for token in query_terms:
        if token in raw_text:
            phrase_bonus += 0.05

    raw_score = overlap + (0.85 * metadata_overlap) + (0.5 * density) + focus_bonus + phrase_bonus
    return raw_score * _quality_multiplier(chunk)


def retrieve(chunks: list[dict], query: str, top_k: int, stage: str | None) -> list[dict]:
    """Return the strongest source-backed matches for a learner query."""
    query_tokens = expand_query_tokens(tokenize(query))
    query_terms = Counter(query_tokens)
    ranked: list[tuple[float, dict]] = []
    for chunk in chunks:
        if stage and chunk.get("stage") != stage:
            continue
        score = score_chunk(query_terms, chunk)
        if score > 0:
            ranked.append((score, chunk))

    if not ranked:
        fallback_candidates = [chunk for chunk in chunks if not stage or chunk.get("stage") == stage]
        fallback_candidates.sort(
            key=lambda chunk: (
                STAGE_ORDER.get(chunk.get("stage", ""), 999),
                chunk.get("filename", ""),
                chunk.get("page_number", 0),
                chunk.get("chunk_index", 0),
            )
        )
        ranked = [(0.0, chunk) for chunk in fallback_candidates[:top_k]]

    ranked.sort(key=lambda item: item[0], reverse=True)

    # Deduplicate: skip chunks whose text was already included in the results.
    seen_hashes: set[str] = set()
    results: list[dict] = []
    for score, chunk in ranked:
        if len(results) >= top_k:
            break
        text_hash = hashlib.md5(chunk["text"].encode("utf-8", errors="replace")).hexdigest()
        if text_hash in seen_hashes:
            continue
        seen_hashes.add(text_hash)
        results.append(
            {
                "score": round(score, 4),
                "reference": chunk["reference"],
                "filename": chunk.get("filename"),
                "stage": chunk["stage"],
                "learner_band": chunk["learner_band"],
                "text": chunk["text"],
                "focus": chunk.get("focus", []),
            }
        )
    return results


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Retrieve reference-backed chunks for The Grammar Teacher.")
    parser.add_argument("--index", type=Path, default=Path("build/grammar_teacher/chunks.jsonl"))
    parser.add_argument("--query", type=str, required=True)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--stage", type=str, default=None)
    args = parser.parse_args()

    chunks = load_chunks(args.index)
    results = retrieve(chunks, args.query, args.top_k, args.stage)
    print(json.dumps({"query": args.query, "results": results}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
