from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

from grammar_teacher.retrieve import expand_query_tokens, load_chunks, retrieve, tokenize
from grammar_teacher.text_cleaning import normalize_text


SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
TOKEN_RE = re.compile(r"[A-Za-z']+")
WORD_RE = re.compile(r"[A-Za-z0-9']+")
INCLUDE_INTERNAL_REFERENCE = os.environ.get("GRAMMAR_TEACHER_INCLUDE_INTERNAL_REFERENCE", "0") == "1"
MAX_EXPLANATION_WORDS = int(os.environ.get("GRAMMAR_TEACHER_MAX_EXPLANATION_WORDS", "120"))
MAX_EXPLANATION_WORDS_COMPOSITE = int(os.environ.get("GRAMMAR_TEACHER_MAX_EXPLANATION_WORDS_COMPOSITE", "170"))
MAX_POINT_WORDS = int(os.environ.get("GRAMMAR_TEACHER_MAX_POINT_WORDS", "48"))
MAX_POINT_WORDS_COMPOSITE = int(os.environ.get("GRAMMAR_TEACHER_MAX_POINT_WORDS_COMPOSITE", "58"))
RULE_REFERENCE_FALLBACK = {
    "rule": "General English Grammar Usage",
    "introduced_by": "No single introducer (standardized by many grammarians)",
    "since": "In use for centuries",
}
EASY_HINTS = (
    "easy",
    "simple",
    "beginner",
    "explain me",
    "explain in",
    "what is",
    "what are",
)
CONCEPT_CANONICAL_QUESTIONS: dict[str, str] = {
    "agreement": "What is subject-verb agreement? Explain in simple terms with examples.",
    "verb": "What are verbs? Explain in simple terms with examples.",
    "noun": "What are nouns? Explain in simple terms with examples.",
    "pronoun": "What are pronouns? Explain in simple terms with examples.",
    "adjective": "What are adjectives? Explain in simple terms with examples.",
    "adverb": "What are adverbs? Explain in simple terms with examples.",
    "article": "What are articles? Explain in simple terms with examples.",
    "tense": "What are tenses? Explain in simple terms with examples.",
}
SPECIAL_QUERY_REWRITES: list[tuple[tuple[str, ...], str]] = [
    (
        ("subject", "verb", "agreement"),
        "Explain subject-verb agreement clearly with rules and examples.",
    ),
    (
        ("parts", "of", "speech"),
        "Explain parts of speech with simple definitions and examples.",
    ),
    (
        ("direct", "indirect", "speech"),
        "Explain direct and indirect speech with simple examples.",
    ),
]
CONCEPT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "agreement": ("agreement", "concord"),
    "verb": ("verb", "verbs"),
    "noun": ("noun", "nouns"),
    "pronoun": ("pronoun", "pronouns"),
    "adjective": ("adjective", "adjectives"),
    "adverb": ("adverb", "adverbs"),
    "article": ("article", "articles"),
    "tense": ("tense", "tenses"),
}
CONCEPT_MICRO_LESSONS: dict[str, list[str]] = {
    "agreement": [
        "Subject-verb agreement means the verb form must match the subject in number and person.",
        "Singular subject: 'She writes every day.' Plural subject: 'They write every day.'",
        "Quick rule: singular subject usually takes singular verb; plural subject takes plural verb.",
    ],
    "verb": [
        "A verb is a word that shows an action or a state.",
        "Action example: 'Riya writes every day.' Here, 'writes' is the verb.",
        "State example: 'They are tired.' Here, 'are' is the verb.",
    ],
    "noun": [
        "A noun is a word for a person, place, thing, or idea.",
        "Example: 'Ravi opened the door.' 'Ravi' and 'door' are nouns.",
        "Example: 'Honesty is important.' 'Honesty' is a noun (an idea).",
    ],
    "pronoun": [
        "A pronoun is a word used in place of a noun.",
        "Example: 'Ravi is late. He missed the bus.' Here, 'He' replaces 'Ravi'.",
        "Common pronouns: I, you, he, she, it, we, they, me, him, her, us, them.",
    ],
    "adjective": [
        "An adjective describes a noun.",
        "Example: 'She has a red bag.' 'Red' describes 'bag'.",
        "Example: 'It was a difficult question.' 'Difficult' describes 'question'.",
    ],
    "adverb": [
        "An adverb usually describes a verb, adjective, or another adverb.",
        "Example: 'He runs quickly.' 'Quickly' describes how he runs.",
        "Example: 'She is very smart.' 'Very' describes the adjective 'smart'.",
    ],
    "article": [
        "Articles are 'a', 'an', and 'the'.",
        "Use 'a'/'an' for non-specific singular nouns: 'a pen', 'an apple'.",
        "Use 'the' for specific things: 'the pen on the table'.",
    ],
    "tense": [
        "Tense shows time in a sentence: past, present, or future.",
        "Present: 'She plays.' Past: 'She played.' Future: 'She will play.'",
        "Tense helps the listener understand when an action happens.",
    ],
}
IGNORED_TEACHING_LINES = {
    "school of distance education",
    "university of calicut",
    "contents",
    "introduction",
    "sources and references",
}
POLITE_PREFIX_RE = re.compile(
    r"^(?:can you please|could you please|can you|could you|please|kindly)\s+",
    re.IGNORECASE,
)
INTERROGATIVE_PREFIX_RE = re.compile(r"^(what|which|who|whom|when|where|why|how)\b", re.IGNORECASE)
QUOTED_SENTENCE_RE = re.compile(r"[\"']([^\"']{3,})[\"']")
TOPIC_TERMS = {
    "noun",
    "pronoun",
    "verb",
    "adjective",
    "adverb",
    "article",
    "tense",
    "voice",
    "active",
    "passive",
    "speech",
    "reported",
    "clause",
    "phrase",
    "preposition",
    "conjunction",
    "modal",
    "punctuation",
    "conditional",
    "comparison",
    "comparative",
    "superlative",
    "agreement",
    "subject",
    "predicate",
    "determiner",
    "gerund",
    "infinitive",
}
COMPOSITE_INTENT_MARKERS = (
    " and correct",
    " and fix",
    " and rewrite",
    " and revise",
    " and improve",
    " and change",
    " then rewrite",
    " then fix",
    " then change",
    " plus fix",
    " plus correct",
    " both rules and examples",
    "compare ",
    "difference between",
    "grammar check plus",
    "combined explanation",
    "mix grammar and",
)
DAILY_LESSON_QUERY_MARKERS = (
    "lesson of the day",
    "lesson for today",
    "today's lesson",
    "todays lesson",
    "topic of the day",
    "grammar topic for today",
    "what should i learn today",
)
DAILY_LESSON_STATE_PATH = Path("build/grammar_teacher/daily_lesson_state.json")
DAILY_LESSON_CARDS: list[dict[str, str]] = [
    {
        "title": "Subject-Verb Agreement",
        "concept": "agreement",
        "stage": "foundation",
        "learner_band": "A1-A2",
        "focus": "agreement",
        "rule": "A singular subject takes a singular verb; a plural subject takes a plural verb.",
        "example_1": "She writes every day.",
        "example_2": "They write every day.",
        "usage_tip": "Always identify the true subject first, then choose the verb form.",
        "quick_check": (
            "Quick check: Choose the correct sentence: 'The boys plays football' or 'The boys play football'? "
            "Answer: 'The boys play football.' Why: 'Boys' is plural, so the verb should be 'play' (not 'plays')."
        ),
    },
    {
        "title": "Nouns and Pronouns",
        "concept": "pronoun",
        "stage": "foundation",
        "learner_band": "A1-A2",
        "focus": "parts_of_speech",
        "rule": "A noun names a person/place/thing/idea; a pronoun replaces a noun to avoid repetition.",
        "example_1": "Ravi lost Ravi's book. -> Ravi lost his book.",
        "example_2": "Mina is absent. She is unwell.",
        "usage_tip": "After introducing a noun once, use a matching pronoun (he/she/it/they).",
        "quick_check": (
            "Quick check: Replace the repeated noun with a pronoun: 'Asha said Asha is ready.' "
            "Answer: 'Asha said she is ready.' Why: 'She' correctly replaces the repeated noun 'Asha'."
        ),
    },
    {
        "title": "Articles (a, an, the)",
        "concept": "article",
        "stage": "foundation",
        "learner_band": "A1-A2",
        "focus": "usage",
        "rule": "Use 'a/an' for non-specific singular nouns and 'the' for specific nouns.",
        "example_1": "I saw a dog in the park.",
        "example_2": "She ate an apple and kept the peel.",
        "usage_tip": "Use 'an' before vowel sounds (an hour) and 'a' before consonant sounds (a university).",
        "quick_check": (
            "Quick check: Fill in the blanks: 'I saw ___ owl on ___ tree.' "
            "Answer: 'I saw an owl on a tree.' Why: use 'an' before vowel sound in 'owl' and 'a' for a nonspecific singular noun 'tree'."
        ),
    },
    {
        "title": "Simple Tense Basics",
        "concept": "tense",
        "stage": "core",
        "learner_band": "A2-B1",
        "focus": "tense",
        "rule": "Present for habits, past for completed actions, and future for planned/expected actions.",
        "example_1": "Present: She reads at night.",
        "example_2": "Past/Future: She read yesterday. She will read tomorrow.",
        "usage_tip": "Time words like 'yesterday' usually pair with simple past, not present perfect.",
        "quick_check": (
            "Quick check: Change to past tense: 'They play cricket after school.' "
            "Answer: 'They played cricket after school.' Why: simple past of 'play' is 'played'."
        ),
    },
    {
        "title": "Preposition Accuracy",
        "concept": None,
        "stage": "core",
        "learner_band": "A2-B1",
        "focus": "usage",
        "rule": "Prepositions show relation in time/place/direction and must match common usage patterns.",
        "example_1": "She is good at math.",
        "example_2": "The train arrived on time.",
        "usage_tip": "Learn common pairs: depend on, interested in, proud of, good at.",
        "quick_check": (
            "Quick check: Choose the correct phrase: 'depends of' or 'depends on'? "
            "Answer: 'depends on.' Why: in standard English, the verb 'depend' takes the preposition 'on'."
        ),
    },
]
CLOSED_CLASS_PRONOUNS = {"i", "you", "he", "she", "it", "we", "they", "me", "him", "her", "us", "them"}
PRONOUNS = {
    "i",
    "you",
    "he",
    "she",
    "it",
    "we",
    "they",
    "me",
    "him",
    "her",
    "us",
    "them",
}
DETERMINERS = {"a", "an", "the", "my", "your", "his", "her", "its", "our", "their", "this", "that"}
BE_VERBS = {"am", "is", "are", "was", "were", "be", "been", "being"}
AUXILIARY_VERBS = {"do", "does", "did", "have", "has", "had", "will", "would", "shall", "should", "can", "could"}
QUANTIFIERS = {"many", "much", "few", "several", "some", "any", "each", "every", "more", "most"}
FUNCTION_WORDS = {"and", "or", "but", "very", "here", "there", "then", "than"}


def _tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def _safe_display(text: str) -> str:
    # Keep API text stable for portal rendering even when upstream OCR/PDF text has mojibake bytes.
    cleaned = normalize_text(text)
    cleaned = re.sub(r"[^\x09\x0A\x0D\x20-\x7E]", "", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned.strip()


def _compact_point(text: str, max_chars: int = 180) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    compact = re.sub(r"\([^)]{30,}\)", "", compact).strip()
    compact = re.sub(r"\s{2,}", " ", compact).strip()
    if len(compact) <= max_chars:
        return compact
    # Prefer keeping a complete sentence if we can find a natural boundary.
    sentence_boundary = max(
        compact.rfind(".", 0, max_chars + 1),
        compact.rfind("?", 0, max_chars + 1),
        compact.rfind("!", 0, max_chars + 1),
    )
    if sentence_boundary >= int(max_chars * 0.55):
        return compact[: sentence_boundary + 1].strip()

    cut = compact[:max_chars].rstrip()
    if " " in cut:
        cut = cut[: cut.rfind(" ")].rstrip()
    return cut + "..."


def _word_count(text: str) -> int:
    return len(WORD_RE.findall(text))


def _truncate_to_words(text: str, max_words: int) -> str:
    value = re.sub(r"\s+", " ", text).strip()
    if not value:
        return ""
    words = value.split(" ")
    if len(words) <= max_words:
        return value
    if max_words <= 0:
        return ""
    trimmed = " ".join(words[:max_words]).strip().rstrip(".,;:")
    return trimmed + "..."


def _summarize_point_by_words(text: str, max_words: int) -> str:
    value = re.sub(r"\s+", " ", text).strip()
    if not value:
        return ""
    if _word_count(value) <= max_words:
        return value

    sentences = [sentence.strip() for sentence in SENTENCE_RE.split(value) if sentence.strip()]
    if not sentences:
        return _truncate_to_words(value, max_words)

    selected: list[str] = []
    used_words = 0
    for sentence in sentences:
        words = _word_count(sentence)
        if words <= 0:
            continue
        if used_words + words <= max_words:
            selected.append(sentence)
            used_words += words
            continue
        if not selected:
            return _truncate_to_words(sentence, max_words)
        break

    summary = " ".join(selected).strip()
    if _word_count(summary) > max_words:
        summary = _truncate_to_words(summary, max_words)
    if summary and summary[-1] not in ".!?":
        summary += "."
    return summary


def _finalize_explanation_points(points: list[str], composite_mode: bool) -> list[str]:
    max_chars = 220 if composite_mode else 420
    max_points = 5 if composite_mode else 3
    max_total_words = MAX_EXPLANATION_WORDS_COMPOSITE if composite_mode else MAX_EXPLANATION_WORDS
    max_point_words = MAX_POINT_WORDS_COMPOSITE if composite_mode else MAX_POINT_WORDS

    finalized: list[str] = []
    used_total = 0
    for point in points:
        display = _compact_point(_safe_display(point), max_chars=max_chars)
        if not display:
            continue
        display = _summarize_point_by_words(display, max_point_words)
        if not display:
            continue

        words = _word_count(display)
        remaining = max_total_words - used_total
        if remaining <= 0:
            break
        if words > remaining:
            minimum_remaining = 8 if composite_mode else 10
            if remaining < minimum_remaining:
                break
            display = _truncate_to_words(display, remaining)
            words = _word_count(display)
            if not display:
                break

        finalized.append(display)
        used_total += words
        if len(finalized) >= max_points:
            break

    if not finalized:
        fallback = "Summary: I found related content, but the output was shortened for readability."
        return [fallback]
    return finalized


def _wants_easy_explanation(query: str) -> bool:
    lowered = query.lower()
    return any(hint in lowered for hint in EASY_HINTS)


def _token_set(text: str) -> set[str]:
    return set(_tokenize(text))


def _detect_concept(query: str) -> str | None:
    tokens = _token_set(query)
    if {"subject", "verb", "agreement"}.issubset(tokens) or ("concord" in tokens and "verb" in tokens):
        return "agreement"
    for concept, keywords in CONCEPT_KEYWORDS.items():
        if any(keyword in tokens for keyword in keywords):
            return concept
    return None


def _detected_concepts(query: str) -> list[str]:
    tokens = _token_set(query)
    concepts: list[str] = []
    if {"subject", "verb", "agreement"}.issubset(tokens) or ("concord" in tokens and "verb" in tokens):
        concepts.append("agreement")
    for concept, keywords in CONCEPT_KEYWORDS.items():
        if concept in concepts:
            continue
        if any(keyword in tokens for keyword in keywords):
            concepts.append(concept)
    return concepts


def _extract_quoted_sentence(query: str) -> str | None:
    match = QUOTED_SENTENCE_RE.search(query)
    if not match:
        return None
    sentence = normalize_text(match.group(1)).strip()
    return sentence or None


def _extract_sentence_context(query: str) -> str | None:
    cleaned = normalize_text(query).strip()
    if not cleaned:
        return None

    quoted = _extract_quoted_sentence(cleaned)
    if quoted:
        return quoted.strip()

    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    if len(lines) >= 2:
        candidate = lines[-1].strip(" \"'")
        if len(candidate.split()) >= 3 and not INTERROGATIVE_PREFIX_RE.search(candidate):
            return candidate

    if ":" in cleaned:
        tail = cleaned.rsplit(":", 1)[1].strip(" \"'")
        if len(tail.split()) >= 3 and not INTERROGATIVE_PREFIX_RE.search(tail):
            return tail

    marker_match = re.search(r"in\s+(?:the\s+)?following\s+sentence\s*[:\-]?\s*(.+)$", cleaned, re.IGNORECASE)
    if marker_match:
        candidate = marker_match.group(1).strip(" \"'")
        if len(candidate.split()) >= 3:
            return candidate
    return None


def _is_composite_intent_query(query: str) -> bool:
    cleaned = normalize_text(query).strip()
    if not cleaned:
        return False
    lowered = cleaned.lower()
    if "subject-verb agreement" in lowered or "subject verb agreement" in lowered:
        return False
    tokens = _tokenize(cleaned)
    if len(tokens) < 6:
        return False

    if any(marker in lowered for marker in COMPOSITE_INTENT_MARKERS):
        return True
    if ":" in cleaned and any(word in lowered for word in ("correct", "fix", "rewrite", "revise", "improve", "change")):
        return True
    if ", because" in lowered and any(word in lowered for word in ("wrong", "fix", "correct", "improve", "say", "wrote")):
        return True

    topic_hits = [term for term in TOPIC_TERMS if re.search(rf"\b{re.escape(term)}\b", lowered)]
    if len(set(topic_hits)) >= 2 and (" and " in lowered or "," in lowered):
        return True
    return False


def _is_daily_lesson_request(query: str) -> bool:
    cleaned = normalize_text(query).strip().lower()
    if not cleaned:
        return False
    if any(marker in cleaned for marker in DAILY_LESSON_QUERY_MARKERS):
        return True
    return "lesson" in cleaned and "today" in cleaned


def _load_daily_lesson_state() -> dict:
    try:
        if DAILY_LESSON_STATE_PATH.exists():
            return json.loads(DAILY_LESSON_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {}


def _save_daily_lesson_state(state: dict) -> None:
    try:
        DAILY_LESSON_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        DAILY_LESSON_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    except Exception:
        # Daily lesson rotation is best-effort; failures should not break answering.
        pass


def _pick_daily_lesson_card(today: date | None = None) -> dict[str, str]:
    today = today or date.today()
    base_index = today.toordinal() % len(DAILY_LESSON_CARDS)
    today_key = today.isoformat()
    state = _load_daily_lesson_state()

    if state.get("date") == today_key:
        next_offset = int(state.get("offset", -1)) + 1
    else:
        next_offset = 0

    offset = next_offset % len(DAILY_LESSON_CARDS)
    index = (base_index + offset) % len(DAILY_LESSON_CARDS)

    _save_daily_lesson_state({"date": today_key, "offset": offset, "index": index})
    return DAILY_LESSON_CARDS[index]


def _with_question(text: str) -> str:
    value = text.strip(" .!?")
    if not value:
        return ""
    if value[-1] not in ".!?":
        value += "?"
    return value


def _fallback_composite_segments(cleaned: str) -> list[str]:
    if not cleaned:
        return []

    lowered = cleaned.lower()
    concepts = _detected_concepts(cleaned)
    instructional_multi_concept = (
        len(concepts) >= 2
        and (" and " in lowered or "," in lowered)
        and any(marker in lowered for marker in ("explain", "teach", "what is", "what are", "define"))
    )
    if instructional_multi_concept:
        return [
            _with_question(CONCEPT_CANONICAL_QUESTIONS.get(concept, f"Explain {concept} clearly with examples."))
            for concept in concepts[:3]
        ]

    if ":" in cleaned:
        prefix, suffix = cleaned.split(":", 1)
        prefix_q = _with_question(prefix)
        suffix_clean = suffix.strip(" \"'")
        if prefix_q and suffix_clean:
            return [prefix_q, _with_question(f'Correct this sentence: "{suffix_clean}"')]

    if ", because" in lowered:
        head, tail = re.split(r",\s*because\s+", cleaned, maxsplit=1, flags=re.IGNORECASE)
        head_q = _with_question(head)
        if head_q and tail.strip():
            tail_clean = tail.strip(" \"'")
            return [head_q, _with_question(f'Correct this sentence: "{tail_clean}"')]

    split_markers = [
        r"\bthen\b",
        r"\bplus\b",
        r"\band\s+(?:correct|fix|rewrite|revise|improve|change|transform|edit|solve)\b",
    ]
    for marker in split_markers:
        pieces = re.split(marker, cleaned, maxsplit=1, flags=re.IGNORECASE)
        if len(pieces) == 2 and pieces[0].strip() and pieces[1].strip():
            return [_with_question(pieces[0]), _with_question(pieces[1])]

    for marker in [", and ", " and "]:
        if marker in lowered:
            idx = lowered.find(marker)
            left = cleaned[:idx].strip()
            right = cleaned[idx + len(marker) :].strip()
            if left and right and len(left.split()) >= 3 and len(right.split()) >= 3:
                return [_with_question(left), _with_question(right)]
    return [cleaned]


def _extract_correction_sentence(segment_text: str) -> str | None:
    cleaned = normalize_text(segment_text).strip()
    if not cleaned:
        return None

    def _trim_meta_prefix(sentence: str) -> str:
        value = sentence.strip()
        if ":" not in value:
            return value
        lead, tail = value.rsplit(":", 1)
        lead_lower = lead.lower()
        if any(
            marker in lead_lower
            for marker in (
                "please help",
                "i am not sure",
                "use of",
                "tell me",
                "explain",
                "confused",
            )
        ):
            tail_clean = tail.strip(" \"'")
            if len(tail_clean.split()) >= 2:
                return tail_clean
        return value

    match = re.search(r'correct this sentence\s*:\s*"([^"]+)"', cleaned, re.IGNORECASE)
    if match:
        sentence = _trim_meta_prefix(match.group(1).strip())
        return sentence or None
    match_single = re.search(r"correct this sentence\s*:\s*'([^']+)'", cleaned, re.IGNORECASE)
    if match_single:
        sentence = _trim_meta_prefix(match_single.group(1).strip())
        return sentence or None
    if ":" in cleaned and "correct this sentence" in cleaned.lower():
        candidate = _trim_meta_prefix(cleaned.split(":", 1)[1].strip(" \"'"))
        return candidate or None
    return None


def _cap_after_punctuation(text: str) -> str:
    chars = list(text)
    cap_next = True
    for idx, ch in enumerate(chars):
        if cap_next and ch.isalpha():
            chars[idx] = ch.upper()
            cap_next = False
        if ch in ".!?":
            cap_next = True
    return "".join(chars)


def _suggest_sentence_correction(sentence: str) -> tuple[str, list[str]]:
    corrected = normalize_text(sentence).strip()
    notes: list[str] = []
    if not corrected:
        return sentence, notes

    replacements: list[tuple[re.Pattern[str], str, str]] = [
        (re.compile(r"\bknow's\b", re.IGNORECASE), "knows", "Fixed apostrophe in a verb."),
        (re.compile(r"\bwho's\s+book\b", re.IGNORECASE), "whose book", "Used possessive 'whose', not 'who is'."),
        (re.compile(r"\bwhom\s+book\b", re.IGNORECASE), "whose book", "Used possessive 'whose' for ownership."),
        (re.compile(r"\bdon't likes\b", re.IGNORECASE), "doesn't like", "Fixed subject-verb agreement."),
        (re.compile(r"\bdo not knows\b", re.IGNORECASE), "do not know", "Fixed auxiliary + base verb form."),
        (re.compile(r"\bmore better\b", re.IGNORECASE), "better", "Removed double comparative."),
        (re.compile(r"\bThere is many\b", re.IGNORECASE), "There are many", "Fixed singular/plural agreement."),
        (re.compile(r"\ba advice\b", re.IGNORECASE), "advice", "Removed article before uncountable noun."),
        (re.compile(r"\bgood in\b", re.IGNORECASE), "good at", "Corrected preposition choice."),
        (re.compile(r"\bdepends of\b", re.IGNORECASE), "depends on", "Corrected preposition choice."),
        (re.compile(r"\bmust to\b", re.IGNORECASE), "must", "Modal verbs take base form without 'to'."),
        (re.compile(r"\bbeautiful and quick\b", re.IGNORECASE), "beautifully and quickly", "Used adverbs for verb modification."),
        (re.compile(r"\bfurnitures\b", re.IGNORECASE), "furniture", "Used uncountable noun form."),
        (re.compile(r"\bbreads\b", re.IGNORECASE), "bread", "Used uncountable noun form."),
        (re.compile(r"\bless people\b", re.IGNORECASE), "fewer people", "Used 'fewer' with countable nouns."),
        (re.compile(r"\bwill going to\b", re.IGNORECASE), "am going to", "Fixed mixed future form."),
    ]

    if re.search(r"\bI have seen\b", corrected, re.IGNORECASE) and re.search(r"\byesterday\b", corrected, re.IGNORECASE):
        corrected = re.sub(r"\bI have seen\b", "I saw", corrected, flags=re.IGNORECASE)
        notes.append("Used simple past with a finished-time marker ('yesterday').")

    if re.search(r"\bIf I will\b", corrected, re.IGNORECASE):
        corrected = re.sub(r"\bIf I will\b", "If I", corrected, flags=re.IGNORECASE)
        notes.append("Removed 'will' from the if-clause.")
        if re.search(r"\bI tell him\b", corrected, re.IGNORECASE):
            corrected = re.sub(r"\bI tell him\b", "I will tell him", corrected, flags=re.IGNORECASE)
            notes.append("Used future form in the main clause.")

    for pattern, replacement, note in replacements:
        if pattern.search(corrected):
            corrected = pattern.sub(replacement, corrected)
            notes.append(note)

    # Pronoun case adjustment for a common learner pattern.
    if re.search(r"\bMe and him\b", corrected, re.IGNORECASE):
        corrected = re.sub(r"\bMe and him\b", "He and I", corrected, flags=re.IGNORECASE)
        notes.append("Adjusted pronoun case in compound subject.")

    corrected = re.sub(r"\s{2,}", " ", corrected).strip()
    corrected = corrected[0].upper() + corrected[1:] if corrected else corrected
    corrected = _cap_after_punctuation(corrected)
    if corrected and corrected[-1] not in ".!?":
        corrected += "."
    return corrected, notes


def _wh_pronoun_guidance(text: str) -> str | None:
    tokens = _token_set(text)
    if not tokens.intersection({"who", "whom", "whose"}):
        return None

    if "give" in tokens and "to" in tokens and "who" in tokens and "whom" not in tokens:
        return (
            'Use "whom" as the object in formal grammar: "Whom did you give it to?" '
            'In everyday speech, "Who did you give it to?" is also common.'
        )
    return (
        'Use "who" for subjects, "whom" for objects, and "whose" for possession. '
        'Examples: "Who called?", "Whom did you call?", "Whose book is this?"'
    )


def _split_composite_query(query: str) -> list[str]:
    cleaned = normalize_text(query).strip()
    if not cleaned:
        return []

    placeholders: list[str] = []

    def _protect(match: re.Match[str]) -> str:
        placeholders.append(match.group(0))
        return f" __Q{len(placeholders)-1}__ "

    masked = QUOTED_SENTENCE_RE.sub(_protect, cleaned)
    masked = re.sub(r"\?\s*", " ? ", masked)
    masked = re.sub(
        (
            r"\b(?:and|also|plus|then)\s+"
            r"(?=(?:what|which|who|whom|when|where|why|how)\s+"
            r"(?:is|are|do|does|did|can|could|should|would|will|has|have|had|to|i|you|he|she|it|we|they)\b)"
        ),
        " ? ",
        masked,
        flags=re.IGNORECASE,
    )
    masked = re.sub(r"\s*;\s*", " ? ", masked)
    masked = re.sub(r"\s{2,}", " ", masked).strip()

    raw_parts = [part.strip(" .!?") for part in masked.split("?") if part.strip(" .!?")]
    restored_parts: list[str] = []
    for part in raw_parts:
        restored = part
        for idx, quoted in enumerate(placeholders):
            restored = restored.replace(f"__Q{idx}__", quoted)
        restored = re.sub(r"\s{2,}", " ", restored).strip()
        if not restored:
            continue
        if not INTERROGATIVE_PREFIX_RE.search(restored):
            leading_tokens = _tokenize(restored)
            if (
                leading_tokens
                and leading_tokens[0] in {"in", "for", "with", "about", "from"}
                and _extract_quoted_sentence(restored)
            ):
                continue
            looks_like_sentence = (
                len(restored.split()) >= 4
                and any(token in _token_set(restored) for token in CLOSED_CLASS_PRONOUNS)
            )
            if looks_like_sentence:
                restored_clean = restored.strip(" \"'")
                restored = f'Correct this sentence: "{restored_clean}"'
            else:
                restored = f"What is {restored}".strip()
        if restored[-1] not in ".!?":
            restored += "?"
        restored_parts.append(restored)

    deduped: list[str] = []
    seen: set[str] = set()
    for part in restored_parts:
        key = part.lower().strip()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(part)

    if len(deduped) <= 1:
        return _fallback_composite_segments(cleaned)
    return deduped


def _is_noun_and_verb_sentence_query(query: str) -> bool:
    tokens = _token_set(query)
    return "noun" in tokens and "verb" in tokens and _extract_sentence_context(query) is not None


def _is_noun_and_pronoun_sentence_query(query: str) -> bool:
    tokens = _token_set(query)
    return "noun" in tokens and "pronoun" in tokens and _extract_sentence_context(query) is not None


def _is_pronoun_and_verb_sentence_query(query: str) -> bool:
    tokens = _token_set(query)
    return "pronoun" in tokens and "verb" in tokens and _extract_sentence_context(query) is not None


def _unique_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def _analyze_sentence_noun_verb(sentence: str) -> tuple[str | None, str | None, str | None, str | None]:
    tokens = re.findall(r"[A-Za-z']+", sentence)
    if not tokens:
        return None, None, None, None

    lowered_tokens = [token.lower() for token in tokens]
    subject_pronoun = tokens[0] if lowered_tokens[0] in PRONOUNS else None

    verb: str | None = None
    for idx, token in enumerate(lowered_tokens):
        if token in BE_VERBS or token in AUXILIARY_VERBS:
            verb = tokens[idx]
            break
    if verb is None:
        for idx, token in enumerate(lowered_tokens):
            if token.endswith(("ed", "ing", "s")) and token not in DETERMINERS and token not in PRONOUNS:
                verb = tokens[idx]
                break

    noun: str | None = None
    for idx in range(len(tokens) - 1, -1, -1):
        token = lowered_tokens[idx]
        if token in DETERMINERS or token in PRONOUNS:
            continue
        if verb and tokens[idx].lower() == verb.lower():
            continue
        noun = tokens[idx]
        break

    determiner: str | None = None
    if noun:
        noun_idx = next((i for i, token in enumerate(tokens) if token.lower() == noun.lower()), None)
        if noun_idx is not None and noun_idx > 0:
            prev = lowered_tokens[noun_idx - 1]
            if prev in DETERMINERS:
                determiner = tokens[noun_idx - 1]

    return noun, verb, subject_pronoun, determiner


def _analyze_sentence_noun_pronoun(sentence: str) -> tuple[list[str], list[str], str | None]:
    tokens = re.findall(r"[A-Za-z']+", sentence)
    if not tokens:
        return [], [], None

    lowered_tokens = [token.lower() for token in tokens]
    pronouns = [tokens[idx] for idx, token in enumerate(lowered_tokens) if token in PRONOUNS]

    verb_indexes: set[int] = set()
    for idx, token in enumerate(lowered_tokens):
        if token in BE_VERBS or token in AUXILIARY_VERBS:
            verb_indexes.add(idx)
            continue
        if token.endswith("'s") and idx > 0 and lowered_tokens[idx - 1] in PRONOUNS:
            verb_indexes.add(idx)
            continue
        if token.endswith("s") and idx > 0 and lowered_tokens[idx - 1] in PRONOUNS:
            verb_indexes.add(idx)

    nouns: list[str] = []
    for idx, token in enumerate(lowered_tokens):
        if idx in verb_indexes:
            continue
        if token in PRONOUNS or token in DETERMINERS or token in BE_VERBS or token in AUXILIARY_VERBS:
            continue
        if token in QUANTIFIERS or token in FUNCTION_WORDS:
            continue
        if token.endswith(("ed", "ing")):
            continue

        prev1 = lowered_tokens[idx - 1] if idx > 0 else ""
        prev2 = lowered_tokens[idx - 2] if idx > 1 else ""
        prev3 = lowered_tokens[idx - 3] if idx > 2 else ""
        next1 = lowered_tokens[idx + 1] if idx + 1 < len(lowered_tokens) else ""
        noun_like = (
            prev1 in DETERMINERS
            or prev1 in QUANTIFIERS
            or prev2 in DETERMINERS
            or prev3 in DETERMINERS
            or token.endswith(("tion", "ment", "ness", "ity", "ship"))
            or (token.endswith("s") and prev1 not in PRONOUNS)
            or next1 in {"and", "or", "but"}
        )
        if noun_like:
            nouns.append(tokens[idx])

    pronouns = _unique_preserve_order(pronouns)
    nouns = _unique_preserve_order(nouns)

    correction_note: str | None = None
    if re.search(r"\bknow's\b", sentence, re.IGNORECASE):
        correction_note = 'Note: In standard writing, "know\'s" is usually corrected to "knows".'
    return nouns, pronouns, correction_note


def _refine_query(query: str) -> str:
    cleaned = normalize_text(query).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"[?]{2,}", "?", cleaned)
    cleaned = re.sub(r"[.]{2,}", ".", cleaned)
    if not cleaned:
        return query.strip()

    lowered = cleaned.lower()
    token_set = set(_tokenize(cleaned))
    concept = _detect_concept(cleaned)
    easy_requested = _wants_easy_explanation(cleaned)

    if _is_pronoun_and_verb_sentence_query(cleaned):
        sentence = (_extract_sentence_context(cleaned) or "").rstrip(" .!?")
        return f'Identify the pronoun and verb in this sentence and explain why: "{sentence}".'

    if _is_noun_and_pronoun_sentence_query(cleaned):
        sentence = (_extract_sentence_context(cleaned) or "").rstrip(" .!?")
        return f'Identify the nouns and pronouns in this sentence and explain why: "{sentence}".'

    if _is_noun_and_verb_sentence_query(cleaned):
        quoted = (_extract_sentence_context(cleaned) or "").rstrip(" .!?")
        return f'Identify the noun and verb in this sentence and explain why: "{quoted}".'

    if concept and easy_requested:
        return CONCEPT_CANONICAL_QUESTIONS.get(concept, cleaned)

    if _is_composite_intent_query(cleaned):
        return cleaned

    for required_tokens, rewrite in SPECIAL_QUERY_REWRITES:
        if all(token in token_set for token in required_tokens):
            return rewrite

    refined = POLITE_PREFIX_RE.sub("", cleaned).strip()
    if concept and "explain me" in lowered:
        if concept == "article":
            refined = "Explain articles clearly with easy examples."
        elif concept == "tense":
            refined = "Explain tenses clearly with easy examples."
        else:
            refined = f"Explain {concept}s clearly with easy examples."

    if not refined:
        refined = cleaned
    refined = refined[0].upper() + refined[1:] if refined else cleaned
    if refined and refined[-1] not in ".!?":
        refined += "?"
    return refined


def refine_query(query: str) -> str:
    """Public helper for consistent query polishing across API and portal layers."""
    return _refine_query(query)


def split_composite_query(query: str) -> list[str]:
    """Public helper for decomposing fusion/composite questions into sub-questions."""
    return _split_composite_query(query)


def _strip_ignored_prefixes(text: str) -> str:
    cleaned = text.strip()
    lowered = cleaned.lower()
    changed = True
    while changed:
        changed = False
        for prefix in IGNORED_TEACHING_LINES:
            if lowered.startswith(prefix + " "):
                cleaned = cleaned[len(prefix) :].strip()
                lowered = cleaned.lower()
                changed = True
    return cleaned


def _candidate_units(text: str) -> list[str]:
    pieces: list[str] = []
    blocks = [block.strip() for block in text.splitlines() if block.strip()]
    buffer = ""
    for block in blocks:
        line = block.strip()
        if not line:
            continue
        if buffer:
            line = f"{buffer} {line}"
            buffer = ""
        parts = [part.strip() for part in SENTENCE_RE.split(line) if part.strip()]
        if line and line[-1] not in ".!?":
            if parts:
                buffer = parts.pop()
            else:
                buffer = line
        pieces.extend(parts)
    if buffer:
        pieces.append(buffer.strip())
    return pieces


def _sentence_score(sentence: str, query: str) -> float:
    sentence = _strip_ignored_prefixes(sentence)
    lowered = sentence.lower()
    if lowered in IGNORED_TEACHING_LINES:
        return -1.0

    query_tokens = set(_tokenize(query))
    sentence_tokens = _tokenize(sentence)
    overlap = sum(1 for token in sentence_tokens if token in query_tokens)
    score = float(overlap)

    if any(marker in lowered for marker in (" means ", " refers to ", " is ", " are ", " use ", " used ")):
        score += 1.5
    if sentence.endswith((".", "!", "?")):
        score += 1.0
    if 50 <= len(sentence) <= 220:
        score += 0.5
    return score


def _teaching_points(query: str, text: str, limit: int = 3) -> list[str]:
    scored: list[tuple[float, str]] = []
    for unit in _candidate_units(text):
        unit = _strip_ignored_prefixes(unit)
        alpha_chars = sum(char.isalpha() for char in unit)
        if alpha_chars < 25:
            continue
        score = _sentence_score(unit, query)
        if score <= 0:
            continue
        scored.append((score, unit.strip()))

    scored.sort(key=lambda item: item[0], reverse=True)
    points: list[str] = []
    for _, unit in scored:
        if unit in points:
            continue
        points.append(unit)
        if len(points) >= limit:
            break
    return points


def _rank_teaching_units(query: str, text: str, limit: int = 6) -> list[dict]:
    scored: list[tuple[float, str]] = []
    for unit in _candidate_units(text):
        unit = _strip_ignored_prefixes(unit)
        if sum(char.isalpha() for char in unit) < 25:
            continue
        score = _sentence_score(unit, query)
        if score <= 0:
            continue
        scored.append((score, unit.strip()))

    scored.sort(key=lambda item: item[0], reverse=True)
    ranked: list[dict] = []
    seen: set[str] = set()
    for score, unit in scored:
        if unit in seen:
            continue
        seen.add(unit)
        ranked.append({"score": round(score, 3), "text": unit})
        if len(ranked) >= limit:
            break
    return ranked


def _fallback_summary(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    kept: list[str] = []
    for line in lines:
        line = _strip_ignored_prefixes(line)
        lowered = line.lower()
        if lowered in IGNORED_TEACHING_LINES:
            continue
        if sum(char.isalpha() for char in line) < 25:
            continue
        kept.append(line)
        if len(" ".join(kept)) >= 220:
            break
    summary = " ".join(kept).strip()
    if not summary:
        summary = "I found a related source section, but it needs cleaner extraction before I can explain it well."
    if summary[-1] not in ".!?":
        summary += "."
    return summary


def _build_quick_check(query: str) -> str:
    lowered = query.lower()
    if "noun" in lowered:
        return (
            "Quick check: Identify the noun in this sentence: 'The child opened the window.' "
            "Answer: 'child' and 'window.' Why: both are names of a person/thing."
        )
    if "pronoun" in lowered:
        return (
            "Quick check: Replace the noun with a pronoun: 'Riya is reading. ___ is focused.' "
            "Answer: 'She is focused.' Why: 'She' is the pronoun that replaces 'Riya'."
        )
    if "verb" in lowered and "agreement" in lowered:
        return (
            "Quick check: Which is correct: 'The boys plays football' or 'The boys play football'? "
            "Answer: 'The boys play football.' Why: 'boys' is plural, so we use 'play'."
        )
    if "verb" in lowered:
        return (
            "Quick check: Identify the verb in this sentence: 'Mina reads a story every night.' "
            "Answer: 'reads.' Why: it shows the action Mina does."
        )
    if "tense" in lowered:
        return (
            "Quick check: Rewrite this in the past tense: 'She walks to school every day.' "
            "Answer: 'She walked to school every day.' Why: past tense of 'walks' is 'walked'."
        )
    if "article" in lowered:
        return (
            "Quick check: Fill in the blank: 'I saw ___ elephant at the zoo.' "
            "Answer: 'an.' Why: 'elephant' starts with a vowel sound."
        )
    return (
        "Quick check: Write one sentence of your own using this grammar point. "
        "Sample answer: 'They were excited about the trip.' Why: it applies a clear subject + verb structure."
    )


def _prettify_title(value: str) -> str:
    title = value.strip()
    title = re.sub(r"(?i)\.pdf$", "", title)
    title = title.replace("_", " ")
    title = re.sub(r"-+", " ", title)
    title = re.sub(r"\s{2,}", " ", title)
    tokens = [token for token in title.split(" ") if token]
    cleaned_tokens: list[str] = []
    for token in tokens:
        if re.fullmatch(r"[0-9a-fA-F]{6,}", token):
            continue
        if re.fullmatch(r"[A-Za-z0-9]{6,}", token) and re.search(r"[A-Za-z]", token) and re.search(r"\d", token):
            continue
        cleaned_tokens.append(token)
    if not cleaned_tokens:
        return ""
    pretty = " ".join(cleaned_tokens).strip()
    pretty = pretty.title()
    return pretty


def _extract_source_title(filename: str | None, internal_reference: str | None) -> str | None:
    if filename:
        title = _prettify_title(filename)
        if title:
            return title
    if internal_reference:
        raw = internal_reference.split(",")[0].strip()
        title = _prettify_title(raw)
        if title:
            return title
    return None


def _source_reference(filename: str | None, internal_reference: str | None) -> str | None:
    title = _extract_source_title(filename, internal_reference)
    if not title:
        return None
    return title


def _rule_profile(
    query: str,
    concept: str | None,
    focus: list[str] | None,
    strategy: str,
    composite_mode: bool = False,
    query_segments_refined: list[str] | None = None,
) -> dict[str, str]:
    lowered = query.lower()
    focus_text = " ".join(focus or []).lower()

    if composite_mode and query_segments_refined:
        segment_rules: list[str] = []
        for segment in query_segments_refined:
            seg_profile = _rule_profile(segment, _detect_concept(segment), None, strategy, composite_mode=False)
            if seg_profile["rule"] not in segment_rules:
                segment_rules.append(seg_profile["rule"])
        if segment_rules:
            return {
                "rule": "Composite Grammar Query: " + "; ".join(segment_rules[:3]),
                "introduced_by": "No single introducer (combines multiple grammar traditions)",
                "since": "In use for centuries",
            }

    if "subject" in lowered and "verb" in lowered and ("agreement" in lowered or "concord" in lowered):
        return {
            "rule": "Subject-Verb Agreement (Concord)",
            "introduced_by": "Robert Lowth (codified in English school grammar)",
            "since": "1762",
        }
    if "active" in lowered and "passive" in lowered:
        return {
            "rule": "Active-Passive Voice Distinction",
            "introduced_by": "Classical Greek grammar tradition (Dionysius Thrax lineage)",
            "since": "c.100 BCE",
        }
    if "direct speech" in lowered or "indirect speech" in lowered or "reported speech" in lowered:
        return {
            "rule": "Direct and Indirect (Reported) Speech",
            "introduced_by": "No single introducer (standardized in school grammars)",
            "since": "In general use since the 19th century",
        }
    if "phrase" in lowered and "clause" in lowered:
        return {
            "rule": "Phrase-Clause Distinction",
            "introduced_by": "Henry Sweet (major modern English grammar codification)",
            "since": "1891",
        }
    if "preposition" in lowered and "conjunction" in lowered:
        return {
            "rule": "Preposition and Conjunction Distinction",
            "introduced_by": "Classical parts-of-speech tradition (Dionysius Thrax lineage)",
            "since": "c.100 BCE",
        }
    if "subject" in lowered and "predicate" in lowered:
        return {
            "rule": "Subject-Predicate Sentence Structure",
            "introduced_by": "Classical grammar tradition (Aristotelian/Greek lineage)",
            "since": "In use for centuries",
        }

    if strategy in {"sentence_parse_noun_verb", "sentence_parse_noun_pronoun"}:
        return {
            "rule": "Parts of Speech Identification (Sentence-Level)",
            "introduced_by": "Dionysius Thrax (early parts-of-speech framework)",
            "since": "c.100 BCE",
        }

    if concept in {"noun", "pronoun", "verb", "adjective", "adverb", "article"}:
        rule_name = {
            "noun": "Noun Identification Rule",
            "pronoun": "Pronoun Identification Rule",
            "verb": "Verb Identification Rule",
            "adjective": "Adjective Identification Rule",
            "adverb": "Adverb Identification Rule",
            "article": "Article Usage Rule",
        }[concept]
        return {
            "rule": rule_name,
            "introduced_by": "Dionysius Thrax (early parts-of-speech framework)",
            "since": "c.100 BCE",
        }
    if concept == "tense" or "tense" in lowered or "present" in lowered or "past" in lowered or "future" in lowered:
        return {
            "rule": "Tense System (Past/Present/Future)",
            "introduced_by": "Classical grammar tradition (later codified in English grammars)",
            "since": "In use for centuries",
        }

    if "agreement" in focus_text:
        return {
            "rule": "Subject-Verb Agreement (Concord)",
            "introduced_by": "Robert Lowth (codified in English school grammar)",
            "since": "1762",
        }
    if "parts_of_speech" in focus_text:
        return {
            "rule": "Parts of Speech Framework",
            "introduced_by": "Dionysius Thrax",
            "since": "c.100 BCE",
        }
    return dict(RULE_REFERENCE_FALLBACK)


def _rule_reference(
    query: str,
    concept: str | None,
    focus: list[str] | None,
    strategy: str,
    composite_mode: bool = False,
    query_segments_refined: list[str] | None = None,
) -> str:
    profile = _rule_profile(
        query=query,
        concept=concept,
        focus=focus,
        strategy=strategy,
        composite_mode=composite_mode,
        query_segments_refined=query_segments_refined,
    )
    return (
        f"Rule: {profile['rule']} | "
        f"Introduced by: {profile['introduced_by']} | "
        f"In use since: {profile['since']}"
    )


def _daily_lesson_payload(
    *,
    query_original: str,
    query_refined: str,
    top_k: int,
    stage: str | None,
    include_trace: bool,
) -> dict:
    card = _pick_daily_lesson_card()
    reference = _rule_reference(
        query=card["title"],
        concept=card.get("concept"),
        focus=[card["focus"]],
        strategy="daily_lesson_recommendation",
    )
    explanation_points = [
        f"Today's suggested topic: {card['title']}.",
        f"Rule: {card['rule']}",
        f"Examples: {card['example_1']} {card['example_2']}",
        f"Usage tip: {card['usage_tip']}",
    ]
    payload = {
        "ok": True,
        "topic": query_original,
        "query_original": query_original,
        "query_refined": query_refined,
        "query_sent_to_tutor": query_refined,
        "query_segments_original": [query_original],
        "query_segments_refined": [query_refined],
        "message": "Generated today's grammar lesson recommendation.",
        "explanation_points": explanation_points,
        "quick_check": card["quick_check"],
        "reference": reference,
        "learner_band": card["learner_band"],
        "stage": card["stage"],
        "score": 1.0,
        "focus": ["daily_lesson", card["focus"]],
    }
    if include_trace:
        payload["pipeline_trace"] = {
            "orchestration": {
                "received_query": query_original,
                "refined_query": query_refined,
                "is_composite_query": False,
                "query_segments_original": [query_original],
                "query_segments_refined": [query_refined],
                "stage_filter": stage,
                "top_k": top_k,
            },
            "retrieval": {
                "tokens_used": [],
                "expanded_tokens_used": [],
                "chunks_total": None,
                "chunks_after_stage_filter": None,
                "top_matches": [],
            },
            "synthesis": {
                "concept_detected": card.get("concept"),
                "easy_mode": True,
                "strategy": "daily_lesson_recommendation",
                "candidate_sentences": [],
                "final_points_count": len(explanation_points),
            },
        }
    return payload


def _segment_answer(
    *,
    chunks: list[dict],
    segment_original: str,
    segment_refined: str,
    stage: str | None,
) -> dict:
    correction_sentence = _extract_correction_sentence(segment_refined) or _extract_correction_sentence(segment_original)
    if correction_sentence:
        corrected, notes = _suggest_sentence_correction(correction_sentence)
        point = f'Suggested correction: "{corrected}"'
        if notes:
            point = point + " " + " ".join(notes[:2])
        return {
            "segment_original": segment_original,
            "segment_refined": segment_refined,
            "strategy": "segment_correction_rule_based",
            "concept": "correction",
            "score": 1.0,
            "point": point,
            "result": None,
        }

    wh_guidance = _wh_pronoun_guidance(segment_refined) or _wh_pronoun_guidance(segment_original)
    if wh_guidance:
        return {
            "segment_original": segment_original,
            "segment_refined": segment_refined,
            "strategy": "segment_wh_pronoun_rule_based",
            "concept": "pronoun",
            "score": 1.0,
            "point": wh_guidance,
            "result": None,
        }

    segment_results = retrieve(chunks, segment_refined, top_k=1, stage=stage)
    if not segment_results:
        return {
            "segment_original": segment_original,
            "segment_refined": segment_refined,
            "strategy": "segment_no_match",
            "concept": _detect_concept(segment_refined) or _detect_concept(segment_original),
            "score": 0.0,
            "point": "I could not find a strong source match for this part yet.",
            "result": None,
        }

    best_segment = segment_results[0]
    source_text = normalize_text(best_segment["text"])
    concept = _detect_concept(segment_refined) or _detect_concept(segment_original)
    easy_requested = _wants_easy_explanation(segment_refined) or _wants_easy_explanation(segment_original)
    points = _teaching_points(segment_refined, source_text, limit=2)
    if not points:
        points = [_fallback_summary(source_text)]

    strategy = "segment_source_sentence_selection"
    if concept and easy_requested:
        strategy = "segment_concept_micro_lesson"
        points = CONCEPT_MICRO_LESSONS.get(concept, points)[:2]
    elif concept and CONCEPT_MICRO_LESSONS.get(concept):
        strategy = "segment_concept_then_source"
        points = [CONCEPT_MICRO_LESSONS[concept][0]] + points[:1]

    display_points = _finalize_explanation_points(points, composite_mode=True)
    primary = display_points[0] if display_points else "I found a related source, but need a cleaner segment answer."
    return {
        "segment_original": segment_original,
        "segment_refined": segment_refined,
        "strategy": strategy,
        "concept": concept,
        "score": best_segment["score"],
        "point": primary,
        "result": best_segment,
    }


def build_answer_payload(
    index: Path,
    query: str,
    top_k: int = 3,
    stage: str | None = None,
    include_trace: bool = False,
) -> dict:
    query_original = query.strip()
    query_refined = _refine_query(query_original)
    query_segments_original = _split_composite_query(query_original)
    query_segments_refined = [_refine_query(segment) for segment in query_segments_original]
    sentence_for_parse = _extract_sentence_context(query_original) or _extract_sentence_context(query_refined)
    pronoun_verb_sentence_query = _is_pronoun_and_verb_sentence_query(query_original) or _is_pronoun_and_verb_sentence_query(query_refined)
    noun_pronoun_sentence_query = _is_noun_and_pronoun_sentence_query(query_original) or _is_noun_and_pronoun_sentence_query(query_refined)
    dual_sentence_query = _is_noun_and_verb_sentence_query(query_original) or _is_noun_and_verb_sentence_query(query_refined)
    composite_intent = _is_composite_intent_query(query_original) or _is_composite_intent_query(query_refined)
    composite_mode = (
        (len(query_segments_refined) > 1 or composite_intent)
        and not dual_sentence_query
        and not noun_pronoun_sentence_query
        and not pronoun_verb_sentence_query
    )
    daily_lesson_request = _is_daily_lesson_request(query_original) or _is_daily_lesson_request(query_refined)

    if daily_lesson_request:
        return _daily_lesson_payload(
            query_original=query_original,
            query_refined=query_refined,
            top_k=top_k,
            stage=stage,
            include_trace=include_trace,
        )

    chunks = load_chunks(index)
    filtered_chunks = [chunk for chunk in chunks if not stage or chunk.get("stage") == stage]
    retrieval_tokens = tokenize(query_refined)
    expanded_tokens = expand_query_tokens(retrieval_tokens)
    results = retrieve(chunks, query_refined, top_k=top_k, stage=stage)
    if not results:
        payload = {
            "ok": False,
            "topic": query_original,
            "query_original": query_original,
            "query_refined": query_refined,
            "query_sent_to_tutor": query_refined,
            "message": (
                "I could not find a strong source match for that question yet. "
                "Try asking with a simpler grammar keyword such as 'noun', "
                "'articles', or 'subject verb agreement'."
            ),
            "explanation_points": [],
            "quick_check": _build_quick_check(query_refined),
            "reference": None,
            "learner_band": None,
            "stage": None,
            "score": 0.0,
            "focus": [],
        }
        if include_trace:
            payload["pipeline_trace"] = {
                "orchestration": {
                    "received_query": query_original,
                    "refined_query": query_refined,
                    "is_composite_query": composite_mode,
                    "query_segments_original": query_segments_original,
                    "query_segments_refined": query_segments_refined,
                    "stage_filter": stage,
                    "top_k": top_k,
                },
                "retrieval": {
                    "tokens_used": retrieval_tokens[:20],
                    "expanded_tokens_used": expanded_tokens[:30],
                    "chunks_total": len(chunks),
                    "chunks_after_stage_filter": len(filtered_chunks),
                    "top_matches": [],
                },
                "synthesis": {
                    "concept_detected": _detect_concept(query_refined) or _detect_concept(query_original),
                    "easy_mode": _wants_easy_explanation(query_refined) or _wants_easy_explanation(query_original),
                    "strategy": "no_match",
                    "candidate_sentences": [],
                    "final_points_count": 0,
                },
            }
        return payload

    best = results[0]
    concept = _detect_concept(query_refined) or _detect_concept(query_original)
    if pronoun_verb_sentence_query:
        concept = "pronoun+verb"
    elif noun_pronoun_sentence_query:
        concept = "noun+pronoun"
    elif dual_sentence_query:
        concept = "noun+verb"
    easy_requested = _wants_easy_explanation(query_refined) or _wants_easy_explanation(query_original)

    ranked_units: list[dict] = []
    strategy = "source_sentence_selection"
    teaching_points: list[str] = []
    segment_answers: list[dict] = []
    selected_results: list[dict] = []

    if composite_mode:
        strategy = "composite_query_segmented"
        for segment_original, segment_refined in zip(query_segments_original, query_segments_refined):
            segment_answer = _segment_answer(
                chunks=chunks,
                segment_original=segment_original,
                segment_refined=segment_refined,
                stage=stage,
            )
            segment_answers.append(segment_answer)
            if segment_answer["result"]:
                selected_results.append(segment_answer["result"])

        for idx, segment_answer in enumerate(segment_answers, start=1):
            label = segment_answer["segment_original"].rstrip(" ?")
            teaching_points.append(f"Part {idx}: {label} -> {segment_answer['point']}")

        if not teaching_points:
            teaching_points = ["I detected multiple parts, but could not retrieve strong matches yet."]
        if not selected_results:
            selected_results = [best]
    else:
        source_text = normalize_text(best["text"])
        ranked_units = _rank_teaching_units(query_refined, source_text, limit=6)
        teaching_points = _teaching_points(query_refined, source_text)
        if not teaching_points:
            teaching_points = [_fallback_summary(source_text)]

        if pronoun_verb_sentence_query and sentence_for_parse:
            nouns, pronouns, correction_note = _analyze_sentence_noun_pronoun(sentence_for_parse)
            noun, verb, _, _ = _analyze_sentence_noun_verb(sentence_for_parse)
            strategy = "sentence_parse_noun_verb"
            pronoun_labels = ", ".join(f'"{item}"' for item in pronouns) if pronouns else "none"
            if verb:
                teaching_points = [
                    f'In the sentence "{sentence_for_parse}", pronoun(s): {pronoun_labels}.',
                    f'Verb: "{verb}".',
                ]
            else:
                teaching_points = [f'In the sentence "{sentence_for_parse}", pronoun(s): {pronoun_labels}.']
                teaching_points.append("I could not confidently detect the verb from that sentence.")
            if noun and len(teaching_points) < 3:
                teaching_points.append(f'Extra note: noun detected as "{noun}".')
            if correction_note and len(teaching_points) < 3:
                teaching_points.append(correction_note)
        elif noun_pronoun_sentence_query and sentence_for_parse:
            nouns, pronouns, correction_note = _analyze_sentence_noun_pronoun(sentence_for_parse)
            strategy = "sentence_parse_noun_pronoun"
            sentence_tokens_lower = [token.lower() for token in re.findall(r"[A-Za-z']+", sentence_for_parse)]
            pronoun_labels = ", ".join(
                f'"{item}" (x{sum(1 for token in sentence_tokens_lower if token == item.lower())})'
                if sum(1 for token in sentence_tokens_lower if token == item.lower()) > 1
                else f'"{item}"'
                for item in pronouns
            )
            noun_labels = ", ".join(f'"{item}"' for item in nouns)
            if pronouns:
                teaching_points = [
                    f'In the sentence "{sentence_for_parse}", pronoun(s): {pronoun_labels}.'
                ]
            else:
                teaching_points = [f'I could not confidently detect pronouns in "{sentence_for_parse}".']

            if nouns:
                teaching_points.append(f"Noun(s): {noun_labels}.")
            else:
                teaching_points.append("I could not confidently detect nouns from that sentence.")

            if correction_note:
                teaching_points.append(correction_note)
        elif dual_sentence_query and sentence_for_parse:
            noun, verb, subject_pronoun, determiner = _analyze_sentence_noun_verb(sentence_for_parse)
            strategy = "sentence_parse_noun_verb"
            if verb:
                teaching_points = [
                    f'In the sentence "{sentence_for_parse}", the verb is "{verb}" because it tells the state/action.',
                ]
            else:
                teaching_points = [f'I could not confidently detect the verb in "{sentence_for_parse}".']
            if noun:
                teaching_points.append(
                    f'The noun is "{noun}" because it names a person, place, thing, or idea.'
                )
            else:
                teaching_points.append("I could not confidently detect the noun from that sentence.")
            if subject_pronoun:
                teaching_points.append(
                    f'"{subject_pronoun}" is a pronoun (subject), not a noun.'
                )
            elif determiner:
                teaching_points.append(f'"{determiner}" is a determiner before the noun.')
        elif concept and easy_requested:
            strategy = "concept_micro_lesson_first"
            teaching_points = CONCEPT_MICRO_LESSONS.get(concept, teaching_points)
        elif concept and CONCEPT_MICRO_LESSONS.get(concept):
            # Keep one concise concept-first line before source-derived details.
            strategy = "concept_then_source"
            teaching_points = [CONCEPT_MICRO_LESSONS[concept][0]] + teaching_points[:2]
        elif teaching_points and teaching_points[0].startswith("I found a related source section"):
            strategy = "fallback_summary"
        selected_results = [best]

    teaching_points = _finalize_explanation_points(teaching_points, composite_mode=composite_mode)

    primary_result = selected_results[0] if selected_results else best
    combined_focus: list[str] = []
    for result_item in selected_results:
        for item in result_item.get("focus", []):
            if item not in combined_focus:
                combined_focus.append(item)

    public_reference = _rule_reference(
        query=query_refined,
        concept=concept,
        focus=combined_focus,
        strategy=strategy,
        composite_mode=composite_mode,
        query_segments_refined=query_segments_refined,
    )
    average_score = (
        round(sum(result_item["score"] for result_item in selected_results) / max(len(selected_results), 1), 4)
        if selected_results
        else 0.0
    )
    quick_check = (
        "Quick check: Answer each part above with one short sentence and one example."
        if composite_mode
        else _build_quick_check(query_refined)
    )
    payload = {
        "ok": True,
        "topic": query_original,
        "query_original": query_original,
        "query_refined": query_refined,
        "query_sent_to_tutor": query_refined,
        "query_segments_original": query_segments_original,
        "query_segments_refined": query_segments_refined,
        "message": "Retrieved a source-backed explanation.",
        "explanation_points": teaching_points,
        "quick_check": quick_check,
        "reference": public_reference,
        "learner_band": primary_result["learner_band"],
        "stage": primary_result["stage"],
        "score": average_score,
        "focus": combined_focus,
        **({"reference_internal": primary_result["reference"]} if INCLUDE_INTERNAL_REFERENCE else {}),
    }
    if include_trace:
        payload["pipeline_trace"] = {
            "orchestration": {
                "received_query": query_original,
                "refined_query": query_refined,
                "is_composite_query": composite_mode,
                "query_segments_original": query_segments_original,
                "query_segments_refined": query_segments_refined,
                "stage_filter": stage,
                "top_k": top_k,
            },
            "retrieval": {
                "tokens_used": retrieval_tokens[:20],
                "expanded_tokens_used": expanded_tokens[:30],
                "chunks_total": len(chunks),
                "chunks_after_stage_filter": len(filtered_chunks),
                "top_matches": [
                    {
                        "rank": idx + 1,
                        "score": candidate["score"],
                        "reference": _source_reference(candidate.get("filename"), candidate.get("reference")),
                        "stage": candidate.get("stage"),
                        "learner_band": candidate.get("learner_band"),
                        "focus": candidate.get("focus", []),
                    }
                    for idx, candidate in enumerate(results[:top_k])
                ],
                "segment_routes": [
                    {
                        "segment_index": idx + 1,
                        "segment_original": segment_answer["segment_original"],
                        "segment_refined": segment_answer["segment_refined"],
                        "strategy": segment_answer["strategy"],
                        "score": segment_answer["score"],
                        "reference": (
                            _source_reference(
                                segment_answer["result"].get("filename"),
                                segment_answer["result"].get("reference"),
                            )
                            if segment_answer["result"]
                            else None
                        ),
                    }
                    for idx, segment_answer in enumerate(segment_answers)
                ],
            },
            "synthesis": {
                "concept_detected": concept,
                "easy_mode": easy_requested,
                "strategy": strategy,
                "candidate_sentences": [
                    {
                        "score": item["score"],
                        "sentence": _compact_point(_safe_display(item["text"]), max_chars=160),
                    }
                    for item in ranked_units[:4]
                ],
                "segment_points": [
                    {
                        "segment_index": idx + 1,
                        "segment_original": segment_answer["segment_original"],
                        "point": segment_answer["point"],
                    }
                    for idx, segment_answer in enumerate(segment_answers)
                ],
                "final_points_count": len(teaching_points),
            },
        }
    return payload


def answer_question(index: Path, query: str, top_k: int = 3, stage: str | None = None) -> str:
    payload = build_answer_payload(index, query, top_k=top_k, stage=stage)
    if not payload["ok"]:
        return payload["message"]

    answer_lines = [
        "The Grammar Teacher",
        "",
        f"Topic: {payload['query_refined']}",
        "",
        "Explanation:",
    ]
    answer_lines.extend(f"- {point}" for point in payload["explanation_points"])
    answer_lines.extend(
        [
            "",
            payload["quick_check"],
            "",
            f"Level: {payload['learner_band']} | Stage: {payload['stage']}",
        ]
    )
    if payload["reference"]:
        answer_lines.insert(-1, f"Reference: {payload['reference']}")
    return "\n".join(answer_lines)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Answer a grammar question with retrieval-backed references.")
    parser.add_argument("--index", type=Path, default=Path("build/grammar_teacher/chunks.jsonl"))
    parser.add_argument("--query", type=str, required=True)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--stage", type=str, default=None)
    args = parser.parse_args()

    print(answer_question(args.index, args.query, top_k=args.top_k, stage=args.stage))


if __name__ == "__main__":
    main()
