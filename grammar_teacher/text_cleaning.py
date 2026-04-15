from __future__ import annotations

import re
from dataclasses import dataclass

URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
PAGE_NUMBER_RE = re.compile(r"^(page\s+)?\d{1,4}$", re.IGNORECASE)
WORD_RE = re.compile(r"[A-Za-z]{2,}")

MOJIBAKE_REPLACEMENTS = {
    "â€™": "'",
    "â€˜": "'",
    "â€œ": '"',
    "â€": '"',
    "â": "'",
    "â": "'",
    "â": '"',
    "â": '"',
    "â€“": "-",
    "â€”": "-",
    "â€¦": "...",
    "â": "-",
    "â": "-",
    "â¦": "...",
    "Â": "",
    "ï¬": "fi",
    "ï¬‚": "fl",
    "\ufeff": "",
}

KNOWN_NOISE_LINES = {
    "facebook.com/lingualib",
    "vk.com/lingualib",
}


@dataclass(frozen=True)
class TextQuality:
    usable: bool
    score: int
    alpha_chars: int
    word_count: int
    unique_words: int
    line_count: int


def _repair_mojibake(text: str) -> str:
    # Some sources contain UTF-8 bytes mis-decoded as Latin-1; attempt a safe round-trip repair.
    markers = ("â", "Ã", "Â", "ð")
    marker_count = sum(text.count(marker) for marker in markers)
    if marker_count:
        try:
            candidate = text.encode("latin-1", errors="strict").decode("utf-8", errors="strict")
            candidate_marker_count = sum(candidate.count(marker) for marker in markers)
            if candidate_marker_count < marker_count:
                text = candidate
        except UnicodeError:
            pass

    for bad, good in MOJIBAKE_REPLACEMENTS.items():
        text = text.replace(bad, good)
    return text


def _is_noise_line(line: str) -> bool:
    lowered = line.strip().lower()
    if not lowered:
        return False
    if lowered in KNOWN_NOISE_LINES:
        return True
    if URL_RE.fullmatch(lowered):
        return True
    if re.fullmatch(r"[_.,:/\\|\-~=\s]+", line):
        return True
    return False


def normalize_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = text.replace("\u00ad", "")
    text = text.replace("\r", "\n")
    text = _repair_mojibake(text)

    cleaned_lines: list[str] = []
    for raw_line in text.split("\n"):
        line = re.sub(r"[ \t]+", " ", raw_line).strip()
        if not line:
            if cleaned_lines and cleaned_lines[-1] != "":
                cleaned_lines.append("")
            continue
        if _is_noise_line(line):
            continue
        cleaned_lines.append(line)

    non_blank_lines = [line for line in cleaned_lines if line]
    if any(not PAGE_NUMBER_RE.fullmatch(line) for line in non_blank_lines):
        cleaned_lines = [line for line in cleaned_lines if not PAGE_NUMBER_RE.fullmatch(line or "")]

    cleaned = "\n".join(cleaned_lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def assess_text_quality(text: str) -> TextQuality:
    normalized = normalize_text(text)
    if not normalized:
        return TextQuality(False, 0, 0, 0, 0, 0)

    words = WORD_RE.findall(normalized)
    unique_words = len({word.lower() for word in words})
    alpha_chars = sum(char.isalpha() for char in normalized)
    line_count = len([line for line in normalized.splitlines() if line.strip()])
    score = alpha_chars + min(len(words) * 6, 240) + min(unique_words * 4, 160)
    usable = alpha_chars >= 15 and len(words) >= 3 and unique_words >= 3
    return TextQuality(usable, score, alpha_chars, len(words), unique_words, line_count)
