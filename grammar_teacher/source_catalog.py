from __future__ import annotations

from dataclasses import asdict, dataclass


STAGE_ORDER = {
    "starter": 0,
    "foundation": 1,
    "core": 2,
    "intermediate": 3,
    "advanced": 4,
    "teacher": 5,
    "writing": 6,
    "exam": 7,
}


@dataclass(frozen=True)
class SourceProfile:
    stage: str
    learner_band: str
    focus: list[str]
    notes: str
    priority: int

    def to_dict(self) -> dict:
        return asdict(self)


RULES: list[tuple[list[str], SourceProfile]] = [
    (
        ["class-iii", "classiv", "classv-", "class-vi", "class-vii", "class-viii", "class-ten"],
        SourceProfile(
            stage="starter",
            learner_band="Pre-A1-A2",
            focus=["school_grammar", "reading", "sentence_basics"],
            notes="School-style source for learners starting from the basics.",
            priority=10,
        ),
    ),
    (
        ["basic-english-grammar", "parts of speech", "complete english grammar rules", "-free-english-grammar"],
        SourceProfile(
            stage="foundation",
            learner_band="A1-A2",
            focus=["parts_of_speech", "sentence_basics", "usage"],
            notes="Direct grammar explanations and beginner practice material.",
            priority=20,
        ),
    ),
    (
        ["slm-iii", "sem-english", "grammar-and-usage"],
        SourceProfile(
            stage="intermediate",
            learner_band="B1-B2",
            focus=["grammar_usage", "sentence_transformation", "modality"],
            notes="Sem-level grammar and usage material that sits between core grammar and advanced reference.",
            priority=25,
        ),
    ),
    (
        ["high-school-english-grammar-and-composition", "grammar-and-composition-by-wren-and-martin"],
        SourceProfile(
            stage="intermediate",
            learner_band="B1-B2",
            focus=["grammar_composition", "sentence_transformation", "revision"],
            notes="High-school grammar and composition material that works well as bridge content.",
            priority=27,
        ),
    ),
    (
        ["english grammar in use", "wren-and-martin", "grammar and usage"],
        SourceProfile(
            stage="intermediate",
            learner_band="B1-B2",
            focus=["core_grammar", "sentence_patterns", "practice"],
            notes="Intermediate grammar study with broad coverage, examples, and self-study practice.",
            priority=30,
        ),
    ),
    (
        ["english composition", "writing unleashed", "bad ideas about writing"],
        SourceProfile(
            stage="writing",
            learner_band="B1-C1",
            focus=["writing", "style", "composition"],
            notes="Writing-oriented material for expression, editing, and composition.",
            priority=60,
        ),
    ),
    (
        ["grammar for teachers", "grammar-for-english-language-teacher", "ed622780"],
        SourceProfile(
            stage="teacher",
            learner_band="B2-C2",
            focus=["pedagogy", "teaching", "error_analysis"],
            notes="Teacher-facing material useful for explanations and lesson design.",
            priority=50,
        ),
    ),
    (
        ["competitive examinations"],
        SourceProfile(
            stage="exam",
            learner_band="B1-C1",
            focus=["exam_prep", "error_detection", "speed_practice"],
            notes="Exam-style source for drills, correction tasks, and mixed review.",
            priority=70,
        ),
    ),
    (
        ["comprehensive", "espressoenglish"],
        SourceProfile(
            stage="advanced",
            learner_band="B2-C2",
            focus=["advanced_grammar", "usage", "reference"],
            notes="Large grammar references useful for deeper explanations.",
            priority=40,
        ),
    ),
]


def classify_source(filename: str) -> SourceProfile:
    """Map a PDF filename to the most useful curriculum stage."""
    lower_name = filename.lower()
    for patterns, profile in RULES:
        if any(pattern in lower_name for pattern in patterns):
            return profile

    return SourceProfile(
        stage="core",
        learner_band="A2-B2",
        focus=["grammar", "usage"],
        notes="Fallback grammar source classification.",
        priority=999,
    )


def curriculum_definition() -> list[dict]:
    """Define the staged learning path that the tutor should follow."""
    return [
        {
            "stage": "starter",
            "goal": "Help absolute beginners recognize sentence parts, simple tense, and basic word forms.",
            "quiz_modes": ["choose_the_word_type", "fill_in_the_blank", "read_and_repeat"],
        },
        {
            "stage": "foundation",
            "goal": "Build confidence with parts of speech, articles, pronouns, simple clauses, and common errors.",
            "quiz_modes": ["correct_the_sentence", "multiple_choice", "guided_examples"],
        },
        {
            "stage": "core",
            "goal": "Strengthen tense control, agreement, sentence patterns, and everyday grammar usage.",
            "quiz_modes": ["sentence_rewrite", "spot_the_error", "mini_dialogue_practice"],
        },
        {
            "stage": "intermediate",
            "goal": "Practice clause combinations, conditionals, reported speech, voice, and editing choices.",
            "quiz_modes": ["transform_the_sentence", "choose_the_best_form", "why_is_this_wrong"],
        },
        {
            "stage": "advanced",
            "goal": "Handle nuanced grammar, authentic usage, style choices, and subtle register differences.",
            "quiz_modes": ["compare_two_forms", "usage_judgment", "edit_for_clarity"],
        },
        {
            "stage": "teacher",
            "goal": "Explain grammar clearly, diagnose mistakes, and adapt teaching to learner needs.",
            "quiz_modes": ["teach_back", "error_analysis", "lesson_design_prompt"],
        },
        {
            "stage": "writing",
            "goal": "Apply grammar to real writing, revision, coherence, and expression.",
            "quiz_modes": ["rewrite_for_style", "paragraph_fix", "guided_composition"],
        },
        {
            "stage": "exam",
            "goal": "Practice speed, accuracy, mixed review, and exam-style correction tasks.",
            "quiz_modes": ["timed_quiz", "mixed_revision", "exam_error_detection"],
        },
    ]


def teacher_profile() -> dict:
    """Describe the response contract used by The Grammar Teacher."""
    return {
        "name": "The Grammar Teacher",
        "mission": (
            "Teach English grammar from basic to advanced level in a friendly, motivating, "
            "step-by-step way while keeping references visible."
        ),
        "personality": [
            "friendly",
            "encouraging",
            "clear",
            "patient",
            "reference_backed",
        ],
        "response_contract": [
            "Start from the learner's current level or infer a safe starting point.",
            "Explain one concept at a time in plain language.",
            "Give at least one fresh real-world example.",
            "End with a quick check, mini quiz, or next step.",
            "Provide a source reference whenever possible.",
        ],
        "quiz_styles": [
            "multiple_choice",
            "fill_in_the_blank",
            "error_correction",
            "sentence_rewrite",
            "micro_quiz",
            "timed_review",
        ],
        "motivation_rules": [
            "Notice progress explicitly.",
            "Keep corrections kind and specific.",
            "Never shame the learner for basic questions.",
            "Offer the next step in the same session.",
        ],
        "answer_sections": [
            "short_explanation",
            "worked_example",
            "quick_practice",
            "reference",
        ],
        "memory_fields": [
            "learner_level",
            "completed_topics",
            "weak_topics",
            "quiz_history",
            "wins",
            "next_topic",
        ],
    }


def web_reference_pack() -> list[dict]:
    """Approved external references that can reinforce the local corpus."""
    return [
        {
            "title": "British Council LearnEnglish",
            "url": "https://learnenglish.britishcouncil.org/",
            "provider": "British Council",
            "best_for": ["all_levels", "grammar_practice", "level_guidance"],
            "notes": "Free level-tagged English learning resources.",
        },
        {
            "title": "British Council English Grammar Reference",
            "url": "https://learnenglish.britishcouncil.org/grammar/english-grammar-reference",
            "provider": "British Council",
            "best_for": ["reference", "grammar_topics", "guided_practice"],
            "notes": "Clear grammar reference pages with exercises.",
        },
        {
            "title": "British Council A1-A2 Grammar",
            "url": "https://learnenglish.britishcouncil.org/grammar/a1-a2-grammar",
            "provider": "British Council",
            "best_for": ["beginners", "foundation"],
            "notes": "A useful beginner set of structured grammar lessons.",
        },
        {
            "title": "British Council Online English Level Test",
            "url": "https://learnenglish.britishcouncil.org/english-levels/online-english-level-test",
            "provider": "British Council",
            "best_for": ["placement", "starting_level"],
            "notes": "Approximate level placement for a new learner.",
        },
        {
            "title": "Cambridge Dictionary Grammar",
            "url": "https://dictionary.cambridge.org/grammar/british-grammar/",
            "provider": "Cambridge Dictionary",
            "best_for": ["intermediate", "advanced", "reference"],
            "notes": "Large grammar reference with authentic examples.",
        },
        {
            "title": "Purdue OWL Grammar",
            "url": "https://owl.purdue.edu/owl/general_writing/grammar/index.html",
            "provider": "Purdue OWL",
            "best_for": ["grammar", "writing", "editing"],
            "notes": "Free writing-lab material for grammar and sentence clarity.",
        },
        {
            "title": "Purdue OWL Grammar Exercises",
            "url": "https://owl.purdue.edu/owl_exercises/grammar_exercises/index.html",
            "provider": "Purdue OWL",
            "best_for": ["practice", "drills"],
            "notes": "Exercise bank covering common grammar topics.",
        },
        {
            "title": "VOA Learning English",
            "url": "https://learningenglish.voanews.com/",
            "provider": "Voice of America",
            "best_for": ["real_world_examples", "listening", "usage"],
            "notes": "Simple English content useful for authentic examples and learner-friendly phrasing.",
        },
    ]
