# The Grammar Teacher

This workspace is organized around a small local grammar tutor called **The Grammar Teacher**.

## Product Goal

Build a compact grammar-learning system that:

- learns from every suitable PDF in this folder
- helps beginners start anywhere and progress step by step
- grows into intermediate, advanced, writing, and exam support
- stays friendly, motivating, and practical
- asks quizzes and checks understanding often
- keeps references visible so answers stay grounded

## Working Strategy

The project is intentionally hybrid:

1. A document-by-document knowledge base preserves source identity and citations.
2. A small local model provides tutoring style, examples, and practice flow.
3. Retrieval brings real source content into answers.
4. Learner memory makes the tutor feel continuous across sessions.

This matters because a tiny model trained from scratch can imitate grammar-book language, but it cannot reliably preserve exact references unless those references live in a separate searchable layer.

## What Exists Today

Running the build pipeline creates:

- `build/grammar_teacher/documents/<doc>/manifest.json`
- `build/grammar_teacher/documents/<doc>/pages.jsonl`
- `build/grammar_teacher/documents/<doc>/chunks.jsonl`
- `build/grammar_teacher/documents.jsonl`
- `build/grammar_teacher/chunks.jsonl`
- `build/grammar_teacher/references.json`
- `build/grammar_teacher/curriculum.json`
- `build/grammar_teacher/teacher_profile.json`
- `build/grammar_teacher/teacher_prompt.md`
- `build/grammar_teacher/session_memory_template.json`
- `build/grammar_teacher/train.txt`
- `build/grammar_teacher/val.txt`

The current build has already processed `25` documents into `11,589` chunks.
Retrieval is deduplicated and quality-scored as of `2026-04-01`; exercise keys, index entries, and list-style TOC pages are penalised in ranking.

## Curriculum Path

- `starter`: school books and very early grammar confidence
- `foundation`: parts of speech, sentence basics, and early usage
- `core`: tense, agreement, clauses, and common grammar control
- `intermediate`: bridge topics that connect rules to more flexible usage
- `advanced`: deeper grammar explanations and nuanced usage
- `teacher`: pedagogy, explanation quality, and error analysis
- `writing`: composition, revision, and style
- `exam`: correction drills and mixed review

## Tutor Contract

The Grammar Teacher should:

- meet the learner at their current level
- explain clearly before using heavy terminology
- give real-life examples whenever possible
- include a quick practice prompt in most replies
- include quick checks with answer + why explanation
- celebrate progress without sounding fake or harsh
- cite the best matching source whenever possible

Daily lesson behavior:

- For prompts like `What's the lesson of the day?`, provide:
  - a suggested grammar topic
  - one core rule
  - simple examples
  - a usage tip
  - a quick check
- Rotate daily lesson topics so repeated asks do not return the same topic every time.

## Reference Model

The reference pack combines:

- local PDF sources processed from this workspace
- curated web references for reinforcement and level support

Answers should prefer the local corpus first when a good match exists, then use curated web references as reinforcement rather than as the default source.

## Best Next Milestone

The strongest next milestone is a live retrieval-backed tutor runtime that:

- chooses lesson, quiz, or reference mode
- pulls the best chunk from `chunks.jsonl`
- uses learner memory to adapt difficulty
- returns a friendly explanation with a citation and one quick check

## Retrieval Quality Contract

The retrieval layer must guarantee:

- **No duplicate chunks** in top-k results (enforced by MD5 deduplication in `retrieve()`).
- **Navigation content discounted**: exercise answer keys, back-index entries (`term · page`), dotted-leader TOC entries, and list-style navigation pages receive a quality multiplier of ≤ 0.75 before scoring.
- **Golden tests**: `tests/test_retrieval_quality.py` enforces these properties against the live corpus on every run.
