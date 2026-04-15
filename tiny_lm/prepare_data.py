from __future__ import annotations

import argparse
import json
from pathlib import Path

from pypdf import PdfReader
from grammar_teacher.text_cleaning import assess_text_quality, normalize_text


def extract_pdf_text(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    pages: list[str] = []
    for page_number, page in enumerate(reader.pages, start=1):
        try:
            content = page.extract_text() or ""
        except Exception as exc:
            print(
                f"Warning: failed to extract text from {pdf_path.name} page {page_number}: {exc}"
            )
            continue
        cleaned = normalize_text(content)
        if assess_text_quality(cleaned).usable:
            pages.append(cleaned)
    return normalize_text("\n\n".join(pages))


def build_corpus(input_dir: Path) -> tuple[str, list[dict]]:
    pdf_files = sorted(input_dir.glob("*.pdf"))
    if not pdf_files:
        raise FileNotFoundError(f"No PDF files found in {input_dir}")

    chunks: list[str] = []
    metadata: list[dict] = []

    for pdf_path in pdf_files:
        text = extract_pdf_text(pdf_path)
        if not text:
            continue

        chunks.append(f"\n\n### SOURCE: {pdf_path.name} ###\n\n{text}\n")
        metadata.append(
            {
                "file": pdf_path.name,
                "characters": len(text),
                "pages": len(PdfReader(str(pdf_path)).pages),
            }
        )

    if not chunks:
        raise ValueError("PDF files were found, but no readable text was extracted.")

    corpus = "".join(chunks)
    return corpus, metadata


def split_text(text: str, train_ratio: float) -> tuple[str, str]:
    split_index = int(len(text) * train_ratio)
    return text[:split_index], text[split_index:]


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract text from PDFs for LM training.")
    parser.add_argument("--input-dir", type=Path, required=True, help="Directory with PDF files.")
    parser.add_argument(
        "--output-dir", type=Path, default=Path("data"), help="Directory for output text files."
    )
    parser.add_argument(
        "--train-ratio", type=float, default=0.9, help="Fraction of text to use for training."
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    corpus, metadata = build_corpus(args.input_dir)
    train_text, val_text = split_text(corpus, args.train_ratio)

    (args.output_dir / "corpus.txt").write_text(corpus, encoding="utf-8")
    (args.output_dir / "train.txt").write_text(train_text, encoding="utf-8")
    (args.output_dir / "val.txt").write_text(val_text, encoding="utf-8")
    (args.output_dir / "metadata.json").write_text(
        json.dumps(
            {
                "source_dir": str(args.input_dir.resolve()),
                "num_documents": len(metadata),
                "total_characters": len(corpus),
                "train_characters": len(train_text),
                "val_characters": len(val_text),
                "documents": metadata,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"Saved corpus to {args.output_dir.resolve()}")
    print(f"Documents: {len(metadata)}")
    print(f"Total characters: {len(corpus):,}")
    print(f"Train characters: {len(train_text):,}")
    print(f"Validation characters: {len(val_text):,}")


if __name__ == "__main__":
    main()
