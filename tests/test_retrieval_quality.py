"""Golden regression tests for retrieval quality.

These tests run against the real corpus index (build/grammar_teacher/chunks.jsonl)
and enforce observable quality properties — no duplicates, no index/TOC clutter,
explanatory content before exercise keys — without requiring exact chunk text matches.

Skip gracefully when the index file is not available (CI without corpus data).
"""
from __future__ import annotations

import hashlib
import re
import unittest
from pathlib import Path

from grammar_teacher.retrieve import (
    _quality_multiplier,
    load_chunks,
    retrieve,
)

INDEX_PATH = Path("build/grammar_teacher/chunks.jsonl")
_CHUNKS: list[dict] | None = None


def _get_chunks() -> list[dict]:
    global _CHUNKS
    if _CHUNKS is None:
        _CHUNKS = load_chunks(INDEX_PATH)
    return _CHUNKS


def _skip_if_no_index(test: unittest.TestCase) -> bool:
    if not INDEX_PATH.exists():
        test.skipTest("Index file not present — skipping golden retrieval tests")
        return True
    return False


class RetrievalDeduplicationTests(unittest.TestCase):
    """Top-k results must never return the same chunk text twice.

    Retrievals for all test queries are pre-computed once in setUpClass.
    """

    _QUERIES = [
        "tense",
        "passive voice",
        "conditional sentences",
        "subject verb agreement",
        "noun",
        "parts of speech",
    ]
    _results: dict[str, list[dict]] = {}

    @classmethod
    def setUpClass(cls) -> None:
        if not INDEX_PATH.exists():
            return
        chunks = _get_chunks()
        for query in cls._QUERIES:
            cls._results[query] = retrieve(chunks, query, top_k=5, stage=None)

    def _assert_no_duplicates(self, query: str) -> None:
        if not INDEX_PATH.exists():
            self.skipTest("Index file not present — skipping golden retrieval tests")
        results = self._results.get(query, [])
        hashes = [
            hashlib.md5(r["text"].encode("utf-8", errors="replace")).hexdigest()
            for r in results
        ]
        self.assertEqual(
            len(hashes),
            len(set(hashes)),
            f"Duplicate chunks in results for query {repr(query)}: "
            + str([r["text"][:60] for r in results]),
        )

    def test_no_duplicates_tense(self) -> None:
        self._assert_no_duplicates("tense")

    def test_no_duplicates_passive_voice(self) -> None:
        self._assert_no_duplicates("passive voice")

    def test_no_duplicates_conditional_sentences(self) -> None:
        self._assert_no_duplicates("conditional sentences")

    def test_no_duplicates_subject_verb_agreement(self) -> None:
        self._assert_no_duplicates("subject verb agreement")

    def test_no_duplicates_noun(self) -> None:
        self._assert_no_duplicates("noun")

    def test_no_duplicates_parts_of_speech(self) -> None:
        self._assert_no_duplicates("parts of speech")


class RetrievalQualityMultiplierTests(unittest.TestCase):
    """Known chunk types must receive correct quality multipliers."""

    def test_index_entry_chunk_receives_low_multiplier(self) -> None:
        """A book back-index chunk (term · page) should be heavily penalised."""
        if _skip_if_no_index(self):
            return
        chunks = _get_chunks()
        for chunk in chunks:
            if "subjects, compound" in chunk["text"] and "subject-verb agreement" in chunk["text"]:
                multiplier = _quality_multiplier(chunk)
                self.assertLessEqual(
                    multiplier,
                    0.4,
                    f"Index entry chunk should have multiplier <= 0.4, got {multiplier}",
                )
                return
        self.skipTest("Expected index entry chunk not found in corpus")

    def test_exercise_answer_key_chunk_receives_low_multiplier(self) -> None:
        """A chunk made up of exercise answer keys should be heavily penalised."""
        fake_chunk = {
            "text": (
                "1-a, 2-b, 3-c, 4-d, 5-a\n"
                "6-b, 7-c, 8-a, 9-d, 10-b\n"
                "11-a, 12-c, 13-b, 14-a, 15-d"
            ),
            "reference": "test",
            "stage": "exam",
            "learner_band": "B1-B2",
            "focus": [],
        }
        self.assertLessEqual(_quality_multiplier(fake_chunk), 0.4)

    def test_list_toc_chunk_receives_low_multiplier(self) -> None:
        """A table-of-contents / list chunk with mostly 1-3 word lines should be penalised."""
        fake_chunk = {
            "text": (
                "Nouns\nPronouns\nVerbs\nAdjectives\nAdverbs\n"
                "Articles\nPrepositions\nConjunctions\nInterjections\n"
                "Noun Phrases\nVerb Phrases\nAdjective Phrases\nAdverb Phrases\n"
                "Dependent Clauses\nIndependent Clauses\nRelative Clauses"
            ),
            "reference": "test",
            "stage": "foundation",
            "learner_band": "A1-A2",
            "focus": [],
        }
        self.assertLessEqual(_quality_multiplier(fake_chunk), 0.4)

    def test_short_chunk_receives_low_multiplier(self) -> None:
        fake_chunk = {
            "text": "A verb shows action.",
            "reference": "test",
            "stage": "foundation",
            "learner_band": "A1-A2",
            "focus": [],
        }
        self.assertLessEqual(_quality_multiplier(fake_chunk), 0.6)

    def test_good_explanatory_chunk_receives_full_multiplier(self) -> None:
        fake_chunk = {
            "text": (
                "Subject-verb agreement means the verb must agree with the subject in number. "
                "A singular subject takes a singular verb, and a plural subject takes a plural verb. "
                "For example: 'She writes every day' (singular) versus 'They write every day' (plural)."
            ),
            "reference": "test",
            "stage": "foundation",
            "learner_band": "A1-A2",
            "focus": ["agreement"],
        }
        self.assertGreaterEqual(_quality_multiplier(fake_chunk), 1.0)


class RetrievalContentQualityTests(unittest.TestCase):
    """Explanatory content should rank above navigation/index content.

    All retrievals are pre-computed once in setUpClass so that individual test
    methods run quickly without re-scanning 11 000+ chunks each time.
    """

    # Topics whose results are pre-computed once for the whole class.
    _TOPICS = [
        "noun",
        "verb",
        "pronoun",
        "adjective",
        "adverb",
        "tense",
        "passive voice",
        "subject verb agreement",
        "articles",
        "preposition",
    ]
    _results: dict[str, list[dict]] = {}

    @classmethod
    def setUpClass(cls) -> None:
        if not INDEX_PATH.exists():
            return
        chunks = _get_chunks()
        for topic in cls._TOPICS:
            cls._results[topic] = retrieve(chunks, topic, top_k=5, stage=None)

    def _results_for(self, topic: str) -> list[dict]:
        if not INDEX_PATH.exists():
            self.skipTest("Index file not present — skipping golden retrieval tests")
        return self._results.get(topic, [])

    def test_subject_verb_agreement_top_results_contain_no_index_entries(self) -> None:
        """Index chunks (term · page) must not appear in any of the top-5 SVA results."""
        results = self._results_for("subject verb agreement")
        _index_line_re = re.compile(r"\S.*?[\u00b7]\s*\d{1,4}")
        for i, r in enumerate(results):
            index_line_count = len(_index_line_re.findall(r["text"]))
            self.assertLess(
                index_line_count,
                4,
                f"Result {i+1} looks like an index entry ({index_line_count} index lines): "
                + repr(r["text"][:100]),
            )

    def test_passive_voice_no_list_toc_in_top5(self) -> None:
        """A flat list-style TOC must not appear in the first 5 passive-voice results."""
        results = self._results_for("passive voice")
        for i, r in enumerate(results):
            lines = [ln.strip() for ln in r["text"].splitlines() if ln.strip()]
            if len(lines) >= 8:
                short = sum(1 for ln in lines if len(ln.split()) <= 3)
                ratio = short / len(lines)
                self.assertLess(
                    ratio,
                    0.80,
                    f"Result {i+1} for 'passive voice' appears to be a list-style TOC "
                    f"({ratio:.0%} short lines): {repr(r['text'][:100])}",
                )

    def test_results_not_empty_for_core_grammar_topics(self) -> None:
        """Every core grammar topic must return at least one result."""
        if not INDEX_PATH.exists():
            self.skipTest("Index file not present — skipping golden retrieval tests")
        for topic in self._TOPICS:
            with self.subTest(topic=topic):
                results = self._results_for(topic)
                self.assertGreaterEqual(
                    len(results),
                    1,
                    f"No results for topic {repr(topic)}",
                )

    def test_subject_verb_agreement_results_contain_relevant_text(self) -> None:
        """Top results for SVA must collectively mention 'subject' and 'verb'."""
        results = self._results_for("subject verb agreement")
        combined = " ".join(r["text"].lower() for r in results)
        self.assertIn("subject", combined)
        self.assertIn("verb", combined)

    def test_passive_voice_results_contain_relevant_text(self) -> None:
        """Top results for passive voice must collectively mention 'passive'."""
        results = self._results_for("passive voice")
        combined = " ".join(r["text"].lower() for r in results)
        self.assertIn("passive", combined)

    def test_scores_are_positive_for_matching_queries(self) -> None:
        """All pre-computed results must have a positive score."""
        if not INDEX_PATH.exists():
            self.skipTest("Index file not present — skipping golden retrieval tests")
        score_topics = ["noun", "verb", "tense", "passive voice", "subject verb agreement"]
        for topic in score_topics:
            with self.subTest(topic=topic):
                for r in self._results_for(topic):
                    self.assertGreater(
                        r["score"],
                        0,
                        f"Result for {repr(topic)} has non-positive score: {r['score']}",
                    )


if __name__ == "__main__":
    unittest.main()
