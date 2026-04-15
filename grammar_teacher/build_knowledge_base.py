from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
from pathlib import Path

from pypdf import PdfReader

from grammar_teacher.ocr import OcrResult, ocr_pdf_page
from grammar_teacher.source_catalog import (
    STAGE_ORDER,
    classify_source,
    curriculum_definition,
    teacher_profile,
    web_reference_pack,
)
from grammar_teacher.text_cleaning import assess_text_quality, normalize_text


def slugify(value: str) -> str:
    """Convert a filename into a stable document id."""
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "document"


def _page_ocr_metadata(result: OcrResult) -> dict:
    """Store enough OCR metadata to explain how a page was recovered."""
    return {
        "engine": "tesseract",
        "engine_path": result.tesseract_path,
        "confidence": result.confidence,
        "dpi": result.dpi,
        "psm": result.psm,
    }

def extract_pages(pdf_path: Path, *, ocr_lang: str = "eng") -> tuple[list[dict], dict]:
    """Extract page text, falling back to OCR when native parsing fails."""
    reader = PdfReader(str(pdf_path))
    pages: list[dict] = []
    stats = {
        "native_pages": 0,
        "ocr_pages": 0,
        "failed_pages": [],
        "ocr_confidence_total": 0.0,
        "ocr_confidence_count": 0,
    }
    for page_number, page in enumerate(reader.pages, start=1):
        extraction_method = "pypdf"
        ocr_result: OcrResult | None = None
        try:
            # Suppress noisy parser output so the build log stays readable.
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                raw_text = page.extract_text() or ""
        except Exception as exc:
            raw_text = ""

        text = normalize_text(raw_text)
        quality = assess_text_quality(text)

        if not quality.usable:
            try:
                ocr_result = ocr_pdf_page(pdf_path, page_number, lang=ocr_lang)
                ocr_text = normalize_text(ocr_result.text)
                ocr_quality = assess_text_quality(ocr_text)
                if ocr_quality.usable and ocr_quality.score >= quality.score:
                    text = ocr_text
                    quality = ocr_quality
                    extraction_method = "ocr"
            except Exception as exc:
                ocr_result = None

        if quality.usable:
            if extraction_method == "ocr":
                stats["ocr_pages"] += 1
                if ocr_result and ocr_result.confidence is not None:
                    stats["ocr_confidence_total"] += ocr_result.confidence
                    stats["ocr_confidence_count"] += 1
            else:
                stats["native_pages"] += 1
            page_record = {
                "page_number": page_number,
                "text": text,
                "characters": len(text),
                "extraction_method": extraction_method,
            }
            if extraction_method == "ocr":
                page_record["ocr"] = _page_ocr_metadata(ocr_result)
            pages.append(
                page_record
            )
        else:
            stats["failed_pages"].append(page_number)
    return pages, stats


def split_text(text: str, target_chars: int, overlap_chars: int) -> list[str]:
    """Split long pages into overlapping chunks without breaking words early."""
    if len(text) <= target_chars:
        return [text]

    parts: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + target_chars, len(text))
        if end < len(text):
            split_at = text.rfind(" ", start, end)
            if split_at > start + (target_chars // 2):
                end = split_at
        chunk = text[start:end].strip()
        if chunk:
            parts.append(chunk)
        if end >= len(text):
            break
        start = max(end - overlap_chars, start + 1)
    return parts


def chunk_pages(document_id: str, filename: str, pages: list[dict], source_meta: dict) -> list[dict]:
    """Turn page records into retrievable chunk records with provenance."""
    chunks: list[dict] = []
    for page in pages:
        sub_chunks = split_text(page["text"], target_chars=1800, overlap_chars=200)
        for chunk_index, chunk_text in enumerate(sub_chunks, start=1):
            chunk_id = f"{document_id}-p{page['page_number']:04d}-c{chunk_index:02d}"
            chunks.append(
                {
                    "chunk_id": chunk_id,
                    "document_id": document_id,
                    "filename": filename,
                    "page_number": page["page_number"],
                    "chunk_index": chunk_index,
                    "stage": source_meta["stage"],
                    "learner_band": source_meta["learner_band"],
                    "focus": source_meta["focus"],
                    "reference": f"{filename}, page {page['page_number']}",
                    "text": chunk_text,
                    "characters": len(chunk_text),
                }
            )
    return chunks


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def ordered_pdfs(input_dir: Path) -> list[Path]:
    pdfs = list(input_dir.glob("*.pdf"))
    return sorted(
        pdfs,
        key=lambda path: (
            STAGE_ORDER.get(classify_source(path.name).stage, 999),
            classify_source(path.name).priority,
            path.name.lower(),
        ),
    )


def build_state_path(output_dir: Path) -> Path:
    return output_dir / "build_state.json"


def load_state(output_dir: Path) -> dict:
    state_path = build_state_path(output_dir)
    if state_path.exists():
        return json.loads(state_path.read_text(encoding="utf-8"))
    return {"processed_documents": []}


def save_state(output_dir: Path, state: dict) -> None:
    write_json(build_state_path(output_dir), state)


def process_document(pdf_path: Path, output_dir: Path, *, ocr_lang: str = "eng") -> tuple[dict, list[dict]]:
    """Process one PDF, persist its artifacts, and return the in-memory records."""
    source_profile = classify_source(pdf_path.name)
    source_meta = source_profile.to_dict()
    document_id = slugify(pdf_path.stem)
    document_dir = output_dir / "documents" / document_id
    document_dir.mkdir(parents=True, exist_ok=True)

    pages, extraction_stats = extract_pages(pdf_path, ocr_lang=ocr_lang)
    combined_text = "\n\n".join(page["text"] for page in pages)
    chunks = chunk_pages(document_id, pdf_path.name, pages, source_meta)
    ocr_pages = extraction_stats["ocr_pages"]
    average_ocr_confidence = None
    if extraction_stats["ocr_confidence_count"]:
        average_ocr_confidence = round(
            extraction_stats["ocr_confidence_total"] / extraction_stats["ocr_confidence_count"],
            2,
        )

    document_record = {
        "document_id": document_id,
        "filename": pdf_path.name,
        "path": str(pdf_path.resolve()),
        "stage": source_meta["stage"],
        "learner_band": source_meta["learner_band"],
        "focus": source_meta["focus"],
        "notes": source_meta["notes"],
        "priority": source_meta["priority"],
        "page_count": len(pages),
        "chunk_count": len(chunks),
        "characters": len(combined_text),
        "ocr_pages": ocr_pages,
        "native_pages": extraction_stats["native_pages"],
        "failed_pages": extraction_stats["failed_pages"],
        "ocr_average_confidence": average_ocr_confidence,
        "reference_label": pdf_path.name,
    }

    write_json(document_dir / "manifest.json", document_record)
    write_jsonl(document_dir / "pages.jsonl", pages)
    write_jsonl(document_dir / "chunks.jsonl", chunks)

    if extraction_stats["failed_pages"]:
        failed_preview = ", ".join(str(page) for page in extraction_stats["failed_pages"][:8])
        if len(extraction_stats["failed_pages"]) > 8:
            failed_preview += ", ..."
        print(
            f"Processed {pdf_path.name}: {len(pages)} pages, {ocr_pages} via OCR, "
            f"{len(extraction_stats['failed_pages'])} failed ({failed_preview})"
        )
    elif ocr_pages:
        print(
            f"Processed {pdf_path.name}: {len(pages)} pages, {ocr_pages} via OCR, "
            f"average OCR confidence {average_ocr_confidence}"
        )

    return document_record, chunks


def load_existing_document(output_dir: Path, pdf_path: Path) -> tuple[dict, list[dict]]:
    source_meta = classify_source(pdf_path.name).to_dict()
    document_id = slugify(pdf_path.stem)
    document_dir = output_dir / "documents" / document_id
    manifest = json.loads((document_dir / "manifest.json").read_text(encoding="utf-8"))
    chunks: list[dict] = []
    with (document_dir / "chunks.jsonl").open("r", encoding="utf-8") as handle:
        for line in handle:
            chunk = json.loads(line)
            chunk["stage"] = source_meta["stage"]
            chunk["learner_band"] = source_meta["learner_band"]
            chunk["focus"] = source_meta["focus"]
            chunks.append(chunk)

    manifest["stage"] = source_meta["stage"]
    manifest["learner_band"] = source_meta["learner_band"]
    manifest["focus"] = source_meta["focus"]
    manifest["notes"] = source_meta["notes"]
    manifest["priority"] = source_meta["priority"]

    write_json(document_dir / "manifest.json", manifest)
    write_jsonl(document_dir / "chunks.jsonl", chunks)
    return manifest, chunks


def build_training_corpus(documents: list[dict], all_chunks: list[dict]) -> str:
    """Concatenate document chunks in source order for the tiny LM corpus."""
    chunks_by_document: dict[str, list[dict]] = {}
    for chunk in all_chunks:
        chunks_by_document.setdefault(chunk["document_id"], []).append(chunk)

    parts: list[str] = []
    for document in documents:
        parts.append(
            "\n\n".join(
                [
                    f"### SOURCE: {document['filename']} ###",
                    f"### STAGE: {document['stage']} ###",
                    f"### LEVEL: {document['learner_band']} ###",
                    "\n\n".join(
                        chunk["text"] for chunk in chunks_by_document.get(document["document_id"], [])
                    ),
                ]
            )
        )
    return "\n\n".join(parts).strip() + "\n"


def split_train_val(text: str, train_ratio: float) -> tuple[str, str]:
    split_index = int(len(text) * train_ratio)
    return text[:split_index], text[split_index:]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build The Grammar Teacher knowledge base from local PDFs."
    )
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("build/grammar_teacher"))
    parser.add_argument("--train-ratio", type=float, default=0.9)
    parser.add_argument("--ocr-lang", type=str, default="eng")
    parser.add_argument(
        "--force-documents",
        nargs="*",
        default=[],
        help="Specific PDF filenames to reprocess even when --resume is used.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Reuse previously processed documents when possible.",
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "documents").mkdir(parents=True, exist_ok=True)

    pdfs = ordered_pdfs(args.input_dir)
    if not pdfs:
        raise FileNotFoundError(f"No PDFs found in {args.input_dir}")

    state = load_state(args.output_dir) if args.resume else {"processed_documents": []}
    processed = set(state.get("processed_documents", []))
    force_documents = set(args.force_documents)

    documents: list[dict] = []
    all_chunks: list[dict] = []

    for pdf_path in pdfs:
        print(f"Processing: {pdf_path.name}")
        if args.resume and pdf_path.name in processed and pdf_path.name not in force_documents:
            document_record, chunks = load_existing_document(args.output_dir, pdf_path)
        else:
            document_record, chunks = process_document(pdf_path, args.output_dir, ocr_lang=args.ocr_lang)
            processed.add(pdf_path.name)
            state["processed_documents"] = sorted(processed)
            save_state(args.output_dir, state)

        documents.append(document_record)
        all_chunks.extend(chunks)

    documents.sort(
        key=lambda doc: (STAGE_ORDER.get(doc["stage"], 999), doc["priority"], doc["filename"].lower())
    )
    all_chunks.sort(key=lambda chunk: (chunk["document_id"], chunk["page_number"], chunk["chunk_index"]))

    curriculum = curriculum_definition()
    references = {
        "local_documents": [
            {
                "title": document["filename"],
                "type": "local_pdf",
                "stage": document["stage"],
                "learner_band": document["learner_band"],
                "focus": document["focus"],
                "path": document["path"],
            }
            for document in documents
        ],
        "web_sources": web_reference_pack(),
    }

    corpus = build_training_corpus(documents, all_chunks)
    train_text, val_text = split_train_val(corpus, args.train_ratio)

    write_jsonl(args.output_dir / "documents.jsonl", documents)
    write_jsonl(args.output_dir / "chunks.jsonl", all_chunks)
    write_json(args.output_dir / "curriculum.json", curriculum)
    write_json(args.output_dir / "references.json", references)
    write_json(args.output_dir / "teacher_profile.json", teacher_profile())
    (args.output_dir / "teacher_prompt.md").write_text(
        (Path(__file__).with_name("teacher_prompt.md")).read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (args.output_dir / "session_memory_template.json").write_text(
        (Path(__file__).with_name("session_memory_template.json")).read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (args.output_dir / "corpus.txt").write_text(corpus, encoding="utf-8")
    (args.output_dir / "train.txt").write_text(train_text, encoding="utf-8")
    (args.output_dir / "val.txt").write_text(val_text, encoding="utf-8")
    write_json(
        args.output_dir / "build_summary.json",
        {
            "project_name": "The Grammar Teacher",
            "source_directory": str(args.input_dir.resolve()),
            "document_count": len(documents),
            "chunk_count": len(all_chunks),
            "total_characters": len(corpus),
            "train_characters": len(train_text),
            "val_characters": len(val_text),
            "stages": {
                stage["stage"]: len([doc for doc in documents if doc["stage"] == stage["stage"]])
                for stage in curriculum
            },
        },
    )

    print(f"Processed documents: {len(documents)}")
    print(f"Generated chunks: {len(all_chunks)}")
    print(f"Saved knowledge base to: {args.output_dir.resolve()}")


if __name__ == "__main__":
    main()
