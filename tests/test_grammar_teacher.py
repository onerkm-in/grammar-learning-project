from __future__ import annotations

import re
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

import torch

from grammar_teacher import build_knowledge_base as bkb
from grammar_teacher import api_server
from grammar_teacher import retrieve
from grammar_teacher import source_catalog
from grammar_teacher import tutor
from portal_backend_template import app as portal_app
from grammar_teacher.ocr import OcrResult
from tiny_lm.model import ModelConfig, TinyTransformerLM


class SourceCatalogTests(unittest.TestCase):
    def test_classify_source_uses_expected_buckets(self) -> None:
        class_book = source_catalog.classify_source("Class-VII-English.pdf")
        teacher_book = source_catalog.classify_source("Grammar for Teachers.pdf")
        composition_book = source_catalog.classify_source("Writing Unleashed.pdf")
        intermediate_book = source_catalog.classify_source("English Grammar in Use.pdf")

        self.assertEqual(class_book.stage, "starter")
        self.assertEqual(class_book.learner_band, "Pre-A1-A2")
        self.assertEqual(teacher_book.stage, "teacher")
        self.assertEqual(composition_book.stage, "writing")
        self.assertEqual(intermediate_book.stage, "intermediate")
        self.assertEqual(intermediate_book.learner_band, "B1-B2")

    def test_curriculum_has_all_expected_stages(self) -> None:
        curriculum = source_catalog.curriculum_definition()
        stages = [entry["stage"] for entry in curriculum]

        self.assertEqual(
            stages,
            [
                "starter",
                "foundation",
                "core",
                "intermediate",
                "advanced",
                "teacher",
                "writing",
                "exam",
            ],
        )

    def test_teacher_profile_contains_memory_contract(self) -> None:
        profile = source_catalog.teacher_profile()

        self.assertEqual(profile["name"], "The Grammar Teacher")
        self.assertIn("learner_level", profile["memory_fields"])
        self.assertIn("reference_backed", profile["personality"])


class RetrieveTests(unittest.TestCase):
    def test_retrieve_ranks_and_filters_chunks(self) -> None:
        chunks = [
            {
                "text": "Subject-verb agreement means the verb matches the subject.",
                "reference": "doc-a, page 1",
                "stage": "core",
                "learner_band": "A2-B1",
                "focus": ["agreement"],
            },
            {
                "text": "This chunk is about adverbs and nothing else.",
                "reference": "doc-b, page 2",
                "stage": "foundation",
                "learner_band": "A1-A2",
                "focus": ["adverbs"],
            },
        ]

        ranked = retrieve.retrieve(chunks, "subject verb agreement", top_k=2, stage="core")

        self.assertEqual(len(ranked), 1)
        self.assertEqual(ranked[0]["reference"], "doc-a, page 1")
        self.assertGreater(ranked[0]["score"], 0)


class BuildKnowledgeBaseTests(unittest.TestCase):
    def test_slugify_normalize_and_split_helpers(self) -> None:
        self.assertEqual(bkb.slugify(" A Test File!!.pdf "), "a-test-file-pdf")
        self.assertEqual(bkb.normalize_text("a\rb\t\tc\n\n\n"), "a\nb c")
        self.assertEqual(
            bkb.normalize_text("https://www.ncertbooks.guru/\n12\nReal text here"),
            "Real text here",
        )

        parts = bkb.split_text("one two three four five", target_chars=9, overlap_chars=2)
        self.assertGreaterEqual(len(parts), 2)
        self.assertTrue(all(part for part in parts))

    def test_build_training_corpus_and_split(self) -> None:
        documents = [
            {"document_id": "doc-1", "filename": "Doc 1.pdf", "stage": "starter", "learner_band": "A0-A2"},
            {"document_id": "doc-2", "filename": "Doc 2.pdf", "stage": "core", "learner_band": "A2-B1"},
        ]
        chunks = [
            {"document_id": "doc-1", "text": "Alpha chunk"},
            {"document_id": "doc-2", "text": "Beta chunk"},
        ]

        corpus = bkb.build_training_corpus(documents, chunks)
        train_text, val_text = bkb.split_train_val(corpus, 0.75)

        self.assertIn("### SOURCE: Doc 1.pdf ###", corpus)
        self.assertIn("### SOURCE: Doc 2.pdf ###", corpus)
        self.assertGreater(len(train_text), 0)
        self.assertGreater(len(val_text), 0)

    def test_extract_pages_uses_ocr_fallback_when_text_extraction_fails(self) -> None:
        class FakePage:
            def extract_text(self) -> str:
                raise RuntimeError("unsupported encoding")

        class FakeReader:
            pages = [FakePage()]

        fake_reader = FakeReader()

        with mock.patch.object(bkb, "PdfReader", return_value=fake_reader), mock.patch.object(
            bkb,
            "ocr_pdf_page",
            return_value=OcrResult(
                text="Recovered page text",
                confidence=88.5,
                tesseract_path="C:\\Program Files\\Tesseract-OCR\\tesseract.exe",
                dpi=200,
                psm=6,
            ),
        ) as ocr_mock:
            pages, stats = bkb.extract_pages(Path("fake.pdf"))

        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0]["text"], "Recovered page text")
        self.assertEqual(pages[0]["extraction_method"], "ocr")
        self.assertIn("ocr", pages[0])
        self.assertEqual(stats["ocr_pages"], 1)
        self.assertEqual(stats["failed_pages"], [])
        ocr_mock.assert_called_once()

    def test_extract_pages_uses_ocr_when_native_text_is_only_watermark_noise(self) -> None:
        class FakePage:
            def extract_text(self) -> str:
                return "https://www.ncertbooks.guru/\nhttps://www.ncertbooks.guru/"

        class FakeReader:
            pages = [FakePage()]

        with mock.patch.object(bkb, "PdfReader", return_value=FakeReader()), mock.patch.object(
            bkb,
            "ocr_pdf_page",
            return_value=OcrResult(
                text="A noun is the name of a person, place, or thing.",
                confidence=90.0,
                tesseract_path="C:\\Program Files\\Tesseract-OCR\\tesseract.exe",
                dpi=200,
                psm=6,
            ),
        ) as ocr_mock:
            pages, stats = bkb.extract_pages(Path("fake.pdf"))

        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0]["extraction_method"], "ocr")
        self.assertIn("A noun is", pages[0]["text"])
        self.assertEqual(stats["ocr_pages"], 1)
        ocr_mock.assert_called_once()


class TinyLmTests(unittest.TestCase):
    def test_forward_and_generate_run_on_small_config(self) -> None:
        torch.manual_seed(1234)
        model = TinyTransformerLM(
            ModelConfig(vocab_size=16, block_size=8, n_embed=8, n_head=2, n_layer=1, dropout=0.0)
        )

        idx = torch.randint(0, 16, (2, 8))
        targets = torch.randint(0, 16, (2, 8))
        logits, loss = model(idx, targets)
        generated = model.generate(idx[:1], max_new_tokens=4)

        self.assertEqual(logits.shape, (2, 8, 16))
        self.assertIsNotNone(loss)
        self.assertEqual(generated.shape, (1, 12))


class TutorTests(unittest.TestCase):
    def test_answer_question_returns_reference_backed_response(self) -> None:
        chunks_path = Path("test_chunks.jsonl")
        chunks_path.write_text(
            '{"text":"A noun is the name of a person, place, or thing. Nouns can be singular or plural.","reference":"English Grammar in Use.pdf, page 12","filename":"English Grammar in Use.pdf","stage":"foundation","learner_band":"A1-A2","focus":["noun"]}\n',
            encoding="utf-8",
        )
        try:
            answer = tutor.answer_question(chunks_path, "noun", top_k=1)
        finally:
            chunks_path.unlink(missing_ok=True)

        self.assertIn("The Grammar Teacher", answer)
        self.assertIn("Reference: Rule:", answer)
        self.assertIn("Introduced by:", answer)
        self.assertIn("In use since:", answer)
        self.assertNotIn(".pdf", answer.lower())
        self.assertNotIn("page", answer.lower())
        self.assertIn("Quick check:", answer)

    def test_build_answer_payload_is_portal_ready(self) -> None:
        chunks_path = Path("test_chunks.jsonl")
        chunks_path.write_text(
            '{"text":"A noun is the name of a person, place, or thing. Nouns can be singular or plural.","reference":"English Grammar in Use.pdf, page 12","filename":"English Grammar in Use.pdf","stage":"foundation","learner_band":"A1-A2","focus":["noun"]}\n',
            encoding="utf-8",
        )
        try:
            payload = tutor.build_answer_payload(chunks_path, "noun", top_k=1)
        finally:
            chunks_path.unlink(missing_ok=True)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["topic"], "noun")
        self.assertIn("Rule:", payload["reference"])
        self.assertIn("Introduced by:", payload["reference"])
        self.assertIn("In use since:", payload["reference"])
        self.assertNotIn(".pdf", payload["reference"].lower())
        self.assertNotIn("page", payload["reference"].lower())
        self.assertEqual(payload["stage"], "foundation")
        self.assertGreaterEqual(len(payload["explanation_points"]), 1)
        self.assertIn("Quick check:", payload["quick_check"])

    def test_reference_uses_rule_format_even_without_book_name(self) -> None:
        chunks_path = Path("test_chunks.jsonl")
        chunks_path.write_text(
            '{"text":"Nouns can be singular or plural.","reference":" , page 1","stage":"foundation","learner_band":"A1-A2","focus":["noun"]}\n',
            encoding="utf-8",
        )
        try:
            payload = tutor.build_answer_payload(chunks_path, "noun", top_k=1)
            answer = tutor.answer_question(chunks_path, "noun", top_k=1)
        finally:
            chunks_path.unlink(missing_ok=True)

        self.assertIsNotNone(payload["reference"])
        self.assertIn("Rule:", payload["reference"])
        self.assertIn("Reference: Rule:", answer)

    def test_tutor_prefers_complete_sentences_over_fragments(self) -> None:
        chunks_path = Path("test_chunks.jsonl")
        chunks_path.write_text(
            (
                '{"text":"School of Distance Education\\nThe word concord means agreement between the subject and the verb. '
                'A singular subject usually takes a singular verb.\\nSources and References","reference":"Doc B, page 2",'
                '"stage":"intermediate","learner_band":"B1-B2","focus":["agreement"]}\n'
            ),
            encoding="utf-8",
        )
        try:
            answer = tutor.answer_question(chunks_path, "subject verb agreement", top_k=1)
        finally:
            chunks_path.unlink(missing_ok=True)

        self.assertIn("The word concord means agreement between the subject and the verb.", answer)
        self.assertNotIn("School of Distance Education", answer)

    def test_easy_verb_question_returns_simple_concept_first_response(self) -> None:
        original_query = "Can you please explain me about Verbs what are Verbs in easy terms using examples?"
        chunks_path = Path("test_chunks.jsonl")
        chunks_path.write_text(
            (
                '{"text":"For example: To love another person is a wonderful thing. '
                'A phrasal verb consists of a verb followed by either a preposition or a particle.","reference":"SLE-ENGLISHGRAMMAR-FOR-CLASS-TEN.pdf, page 29",'
                '"filename":"SLE-ENGLISHGRAMMAR-FOR-CLASS-TEN.pdf","stage":"starter","learner_band":"Pre-A1-A2","focus":["sentence_basics"]}\n'
            ),
            encoding="utf-8",
        )
        try:
            payload = tutor.build_answer_payload(
                chunks_path,
                original_query,
                top_k=1,
            )
        finally:
            chunks_path.unlink(missing_ok=True)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["query_original"], original_query)
        self.assertEqual(payload["query_refined"], "What are verbs? Explain in simple terms with examples.")
        self.assertEqual(payload["query_sent_to_tutor"], payload["query_refined"])
        self.assertGreaterEqual(len(payload["explanation_points"]), 2)
        self.assertIn("A verb is a word", payload["explanation_points"][0])
        self.assertIn("Action example", payload["explanation_points"][1])

    def test_build_answer_payload_uses_refined_query_for_retrieval(self) -> None:
        original_query = "Can you please explain me about Verbs what are Verbs in easy terms using examples?"
        fake_chunk = {
            "text": "A verb is a word that shows action.",
            "reference": "Doc.pdf, page 1",
            "filename": "Doc.pdf",
            "stage": "foundation",
            "learner_band": "A1-A2",
            "focus": ["verb"],
            "score": 0.95,
        }

        with mock.patch.object(tutor, "load_chunks", return_value=[fake_chunk]), mock.patch.object(
            tutor, "retrieve", return_value=[fake_chunk]
        ) as retrieve_mock:
            payload = tutor.build_answer_payload(Path("unused.jsonl"), original_query, top_k=1)

        self.assertEqual(payload["query_refined"], "What are verbs? Explain in simple terms with examples.")
        self.assertEqual(retrieve_mock.call_args.args[1], payload["query_refined"])

    def test_build_answer_payload_include_trace_adds_pipeline_stages(self) -> None:
        chunks_path = Path("test_chunks.jsonl")
        chunks_path.write_text(
            '{"text":"A noun is a naming word. Nouns can be people, places, things, or ideas.","reference":"English Grammar in Use.pdf, page 12","filename":"English Grammar in Use.pdf","stage":"foundation","learner_band":"A1-A2","focus":["noun"]}\n',
            encoding="utf-8",
        )
        try:
            payload = tutor.build_answer_payload(chunks_path, "What is a noun?", top_k=1, include_trace=True)
        finally:
            chunks_path.unlink(missing_ok=True)

        self.assertIn("pipeline_trace", payload)
        trace = payload["pipeline_trace"]
        self.assertIn("orchestration", trace)
        self.assertIn("retrieval", trace)
        self.assertIn("synthesis", trace)
        self.assertEqual(trace["orchestration"]["received_query"], "What is a noun?")
        self.assertGreaterEqual(trace["retrieval"]["chunks_total"], 1)

    def test_compact_point_prefers_sentence_boundary(self) -> None:
        text = (
            "Subject-verb agreement means the verb must match the subject in number and person. "
            "This second sentence is intentionally long enough to force compacting behavior."
        )
        compacted = tutor._compact_point(text, max_chars=95)
        self.assertTrue(compacted.endswith("."))
        self.assertNotIn("...", compacted)

    def test_subject_verb_agreement_query_is_polished_for_retrieval(self) -> None:
        chunks_path = Path("test_chunks.jsonl")
        chunks_path.write_text(
            '{"text":"Subject-verb agreement means the verb must agree with the subject in number.","reference":"Doc.pdf, page 1","filename":"Doc.pdf","stage":"core","learner_band":"A2-B1","focus":["agreement"]}\n',
            encoding="utf-8",
        )
        try:
            payload = tutor.build_answer_payload(chunks_path, "subject verb agreement", top_k=1, include_trace=True)
        finally:
            chunks_path.unlink(missing_ok=True)

        self.assertEqual(
            payload["query_refined"],
            "Explain subject-verb agreement clearly with rules and examples.",
        )
        self.assertIn("subject", payload["pipeline_trace"]["retrieval"]["tokens_used"])

    def test_explanation_is_summarized_and_word_limited_when_oversized(self) -> None:
        chunks_path = Path("test_chunks.jsonl")
        long_text = (
            "Subject-verb agreement means the verb should match the subject in number and person. "
            "This explanation sentence is intentionally long and repeated to simulate oversized output for testing. "
            "This explanation sentence is intentionally long and repeated to simulate oversized output for testing. "
            "This explanation sentence is intentionally long and repeated to simulate oversized output for testing. "
            "This explanation sentence is intentionally long and repeated to simulate oversized output for testing."
        )
        chunks_path.write_text(
            (
                '{"text":"' + long_text + '","reference":"Doc.pdf, page 1","filename":"Doc.pdf",'
                '"stage":"core","learner_band":"A2-B1","focus":["agreement"]}\n'
            ),
            encoding="utf-8",
        )
        try:
            with mock.patch.object(tutor, "MAX_EXPLANATION_WORDS", 36), mock.patch.object(
                tutor, "MAX_POINT_WORDS", 18
            ):
                payload = tutor.build_answer_payload(chunks_path, "subject verb agreement", top_k=1, include_trace=True)
        finally:
            chunks_path.unlink(missing_ok=True)

        total_words = sum(len(re.findall(r"[A-Za-z0-9']+", point)) for point in payload["explanation_points"])
        self.assertLessEqual(total_words, 36)

    def test_noun_and_verb_sentence_query_gets_sentence_parse_response(self) -> None:
        chunks_path = Path("test_chunks.jsonl")
        chunks_path.write_text(
            '{"text":"A noun names a person, place, or thing. A verb shows action or state.","reference":"Doc.pdf, page 1","filename":"Doc.pdf","stage":"foundation","learner_band":"A1-A2","focus":["noun","verb"]}\n',
            encoding="utf-8",
        )
        query = 'what is noun here and what is verb? in "He is my Father"'
        try:
            payload = tutor.build_answer_payload(chunks_path, query, top_k=1, include_trace=True)
        finally:
            chunks_path.unlink(missing_ok=True)

        self.assertEqual(
            payload["query_refined"],
            'Identify the noun and verb in this sentence and explain why: "He is my Father".',
        )
        self.assertEqual(payload["query_segments_original"], ["what is noun here?", "what is verb?"])
        points = " ".join(payload["explanation_points"])
        self.assertIn('verb is "is"', points)
        self.assertIn('noun is "Father"', points)
        self.assertEqual(payload["pipeline_trace"]["synthesis"]["strategy"], "sentence_parse_noun_verb")

    def test_noun_and_pronoun_sentence_query_identifies_sentence_items(self) -> None:
        chunks_path = Path("test_chunks.jsonl")
        chunks_path.write_text(
            '{"text":"Pronouns replace nouns. Nouns name people or things.","reference":"Doc.pdf, page 1","filename":"Doc.pdf","stage":"foundation","learner_band":"A1-A2","focus":["noun","pronoun"]}\n',
            encoding="utf-8",
        )
        query = "What is the Noun and Pronoun in following sentence:\nHe is a very talented person, and he know's many things."
        try:
            payload = tutor.build_answer_payload(chunks_path, query, top_k=1, include_trace=True)
        finally:
            chunks_path.unlink(missing_ok=True)

        self.assertEqual(
            payload["query_refined"],
            'Identify the nouns and pronouns in this sentence and explain why: "He is a very talented person, and he know\'s many things".',
        )
        points = " ".join(payload["explanation_points"])
        self.assertIn('pronoun(s): "He" (x2)', points)
        self.assertIn('Noun(s): "person", "things"', points)
        self.assertEqual(payload["pipeline_trace"]["synthesis"]["strategy"], "sentence_parse_noun_pronoun")

    def test_simple_noun_and_pronoun_query_covers_both_topics(self) -> None:
        chunks_path = Path("test_chunks.jsonl")
        chunks_path.write_text(
            (
                '{"text":"A noun is a naming word.","reference":"Doc.pdf, page 1","filename":"Doc.pdf","stage":"foundation","learner_band":"A1-A2","focus":["noun"]}\n'
                '{"text":"A pronoun replaces a noun.","reference":"Doc2.pdf, page 2","filename":"Doc2.pdf","stage":"foundation","learner_band":"A1-A2","focus":["pronoun"]}\n'
            ),
            encoding="utf-8",
        )
        query = "Please explain noun and pronoun in simple terms"
        try:
            payload = tutor.build_answer_payload(chunks_path, query, top_k=2, include_trace=True)
        finally:
            chunks_path.unlink(missing_ok=True)

        self.assertEqual(payload["pipeline_trace"]["synthesis"]["strategy"], "composite_query_segmented")
        self.assertGreaterEqual(len(payload["query_segments_refined"]), 2)
        self.assertIn("What are nouns?", payload["query_segments_refined"][0])
        self.assertIn("What are pronouns?", payload["query_segments_refined"][1])
        points = " ".join(payload["explanation_points"])
        self.assertIn("A noun is a word", points)
        self.assertIn("A pronoun is a word", points)

    def test_composite_query_is_segmented_into_parts(self) -> None:
        chunks_path = Path("test_chunks.jsonl")
        chunks_path.write_text(
            (
                '{"text":"A noun is a naming word. An adjective describes a noun.","reference":"Doc.pdf, page 1","filename":"Doc.pdf","stage":"foundation","learner_band":"A1-A2","focus":["noun","adjective"]}\n'
                '{"text":"An adjective gives more information about a noun.","reference":"Doc2.pdf, page 2","filename":"Doc2.pdf","stage":"foundation","learner_band":"A1-A2","focus":["adjective"]}\n'
            ),
            encoding="utf-8",
        )
        query = "What is a noun and what is an adjective?"
        try:
            payload = tutor.build_answer_payload(chunks_path, query, top_k=2, include_trace=True)
        finally:
            chunks_path.unlink(missing_ok=True)

        self.assertEqual(len(payload["query_segments_original"]), 2)
        self.assertEqual(payload["pipeline_trace"]["orchestration"]["is_composite_query"], True)
        self.assertEqual(payload["pipeline_trace"]["synthesis"]["strategy"], "composite_query_segmented")
        self.assertTrue(any(point.startswith("Part 1:") for point in payload["explanation_points"]))
        self.assertTrue(any(point.startswith("Part 2:") for point in payload["explanation_points"]))

    def test_composite_correction_segment_includes_suggested_correction(self) -> None:
        chunks_path = Path("test_chunks.jsonl")
        chunks_path.write_text(
            '{"text":"Present perfect is not normally used with yesterday.","reference":"Doc.pdf, page 1","filename":"Doc.pdf","stage":"foundation","learner_band":"A1-A2","focus":["tense"]}\n',
            encoding="utf-8",
        )
        query = "Explain present perfect and correct this sentence: I have seen him yesterday."
        try:
            payload = tutor.build_answer_payload(chunks_path, query, top_k=1, include_trace=True)
        finally:
            chunks_path.unlink(missing_ok=True)

        points = " ".join(payload["explanation_points"])
        self.assertIn("Suggested correction:", points)
        self.assertIn("I saw him yesterday", points)
        self.assertEqual(payload["pipeline_trace"]["synthesis"]["strategy"], "composite_query_segmented")

    def test_pronoun_and_verb_sentence_query_routes_to_sentence_parse_noun_verb(self) -> None:
        chunks_path = Path("test_chunks.jsonl")
        chunks_path.write_text(
            '{"text":"Pronouns replace nouns and verbs show action.","reference":"Doc.pdf, page 1","filename":"Doc.pdf","stage":"foundation","learner_band":"A1-A2","focus":["pronoun","verb"]}\n',
            encoding="utf-8",
        )
        query = 'Sentence: "She runs every morning." Extract the pronoun and verb.'
        try:
            payload = tutor.build_answer_payload(chunks_path, query, top_k=1, include_trace=True)
        finally:
            chunks_path.unlink(missing_ok=True)

        self.assertEqual(payload["pipeline_trace"]["synthesis"]["strategy"], "sentence_parse_noun_verb")
        joined = " ".join(payload["explanation_points"])
        self.assertIn('pronoun(s): "She"', joined)
        self.assertIn('Verb: "runs"', joined)

    def test_composite_who_whom_whose_query_uses_clean_rule_guidance(self) -> None:
        chunks_path = Path("test_chunks.jsonl")
        chunks_path.write_text(
            '{"text":"Pronouns include who, whom, and whose.","reference":"Doc.pdf, page 1","filename":"Doc.pdf","stage":"foundation","learner_band":"A1-A2","focus":["pronoun"]}\n',
            encoding="utf-8",
        )
        query = (
            "Please help with the use of whom, whose, and who, because I am not sure: "
            "Whom book is this and who did you give it to?"
        )
        try:
            payload = tutor.build_answer_payload(chunks_path, query, top_k=1, include_trace=True)
        finally:
            chunks_path.unlink(missing_ok=True)

        self.assertEqual(payload["pipeline_trace"]["synthesis"]["strategy"], "composite_query_segmented")
        points = " ".join(payload["explanation_points"])
        self.assertIn("Whose book is this.", points)
        self.assertIn('Use "whom" as the object in formal grammar', points)

    def test_daily_lesson_query_returns_curated_topic(self) -> None:
        with mock.patch.object(tutor, "load_chunks") as load_chunks_mock:
            payload = tutor.build_answer_payload(
                Path("unused.jsonl"),
                "What's the lesson of the day?",
                include_trace=True,
            )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["pipeline_trace"]["synthesis"]["strategy"], "daily_lesson_recommendation")
        self.assertTrue(payload["explanation_points"][0].startswith("Today's suggested topic:"))
        self.assertTrue(any(point.startswith("Rule:") for point in payload["explanation_points"]))
        self.assertTrue(any(point.startswith("Examples:") for point in payload["explanation_points"]))
        self.assertTrue(any(point.startswith("Usage tip:") for point in payload["explanation_points"]))
        self.assertIn("Quick check:", payload["quick_check"])
        load_chunks_mock.assert_not_called()

    def test_daily_lesson_rotates_within_same_day(self) -> None:
        state_path = Path("test_daily_lesson_state.json")
        state_path.unlink(missing_ok=True)
        try:
            with mock.patch.object(tutor, "DAILY_LESSON_STATE_PATH", state_path):
                first = tutor._pick_daily_lesson_card(today=date(2026, 3, 21))
                second = tutor._pick_daily_lesson_card(today=date(2026, 3, 21))
        finally:
            state_path.unlink(missing_ok=True)

        self.assertNotEqual(first["title"], second["title"])


class ApiServerTests(unittest.TestCase):
    class _FakeRequest:
        class _Client:
            def __init__(self, host: str) -> None:
                self.host = host

        def __init__(self, headers: dict[str, str] | None = None, host: str = "127.0.0.1") -> None:
            self.headers = headers or {}
            self.client = self._Client(host)

    def test_rate_limiter_blocks_after_limit(self) -> None:
        limiter = api_server.SlidingWindowRateLimiter(max_requests=2, window_seconds=60)
        allowed_1, retry_1 = limiter.allow("k", now=100.0)
        allowed_2, retry_2 = limiter.allow("k", now=110.0)
        allowed_3, retry_3 = limiter.allow("k", now=120.0)

        self.assertTrue(allowed_1)
        self.assertTrue(allowed_2)
        self.assertFalse(allowed_3)
        self.assertEqual(retry_1, 0)
        self.assertEqual(retry_2, 0)
        self.assertGreaterEqual(retry_3, 1)

    def test_authorize_requires_valid_api_key(self) -> None:
        request = self._FakeRequest(headers={"x-api-key": "bad-key"})
        with mock.patch.object(api_server, "API_KEY", "good-key"), self.assertRaises(Exception) as raised:
            api_server.authorize_and_rate_limit(request)

        self.assertIn("Invalid API key", str(raised.exception))

    def test_authorize_accepts_valid_api_key(self) -> None:
        request = self._FakeRequest(headers={"x-api-key": "good-key"})
        with mock.patch.object(api_server, "API_KEY", "good-key"), mock.patch.object(
            api_server, "RATE_LIMITER", api_server.SlidingWindowRateLimiter(max_requests=10, window_seconds=60)
        ):
            # Should not raise.
            api_server.authorize_and_rate_limit(request)


class PortalBackendTests(unittest.TestCase):
    def test_portal_fallback_adds_refined_query_and_trace(self) -> None:
        request = portal_app.PortalAskRequest(
            query="subject verb agreement",
            top_k=3,
            include_trace=True,
        )
        upstream_result = {
            "ok": True,
            "explanation_points": ["Subject-verb agreement means the verb must match the subject."],
            "stage": "core",
            "learner_band": "A2-B1",
            "score": 1.23,
            "focus": ["agreement"],
            "reference": "Free English Grammar",
        }

        enriched = portal_app._ensure_observability_fields(request, dict(upstream_result))

        self.assertEqual(
            enriched["query_refined"],
            "Explain subject-verb agreement clearly with rules and examples.",
        )
        self.assertGreaterEqual(len(enriched["query_segments_refined"]), 1)
        self.assertIn("pipeline_trace", enriched)
        self.assertIn("retrieval", enriched["pipeline_trace"])
        self.assertEqual(
            enriched["pipeline_trace"]["retrieval"]["trace_source"],
            "portal_fallback",
        )


if __name__ == "__main__":
    unittest.main()
