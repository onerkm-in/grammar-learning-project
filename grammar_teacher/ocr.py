from __future__ import annotations

import io
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

import fitz
import pytesseract
from PIL import Image, ImageOps


COMMON_TESSERACT_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]


@dataclass(frozen=True)
class OcrResult:
    """Structured OCR output so the build can record quality and provenance."""
    text: str
    confidence: float | None
    tesseract_path: str | None
    dpi: int
    psm: int


def configure_tesseract() -> str | None:
    """Find Tesseract from env, PATH, or the common Windows install locations."""
    configured = os.environ.get("TESSERACT_CMD")
    if configured and Path(configured).exists():
        pytesseract.pytesseract.tesseract_cmd = configured
        return configured

    discovered = shutil.which("tesseract")
    if discovered:
        pytesseract.pytesseract.tesseract_cmd = discovered
        return discovered

    for candidate in COMMON_TESSERACT_PATHS:
        if Path(candidate).exists():
            pytesseract.pytesseract.tesseract_cmd = candidate
            return candidate

    return None


def _render_page(pdf_path: Path, page_number: int, dpi: int) -> Image.Image:
    """Render a PDF page to an image suitable for OCR."""
    scale = dpi / 72.0
    with fitz.open(pdf_path) as document:
        page = document.load_page(page_number - 1)
        pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)

    image = Image.open(io.BytesIO(pixmap.tobytes("png")))
    image = ImageOps.grayscale(image)
    return ImageOps.autocontrast(image)


def _mean_confidence(data: dict[str, list[str]]) -> float | None:
    """Average Tesseract confidences while ignoring missing or invalid values."""
    confidences: list[float] = []
    for raw_value in data.get("conf", []):
        try:
            confidence = float(raw_value)
        except (TypeError, ValueError):
            continue
        if confidence >= 0:
            confidences.append(confidence)

    if not confidences:
        return None

    return round(sum(confidences) / len(confidences), 2)


def ocr_pdf_page(
    pdf_path: Path,
    page_number: int,
    *,
    lang: str = "eng",
    dpi: int = 200,
    psm: int = 6,
) -> OcrResult:
    """Run OCR for one PDF page and return the recovered text plus metadata."""
    tesseract_path = configure_tesseract()
    if not tesseract_path:
        raise RuntimeError(
            "Tesseract OCR was not found. Install it or set TESSERACT_CMD to the executable path."
        )

    image = _render_page(pdf_path, page_number, dpi)
    config = f"--psm {psm}"
    text = pytesseract.image_to_string(image, lang=lang, config=config)
    data = pytesseract.image_to_data(
        image,
        lang=lang,
        config=config,
        output_type=pytesseract.Output.DICT,
    )

    return OcrResult(
        text=text,
        confidence=_mean_confidence(data),
        tesseract_path=tesseract_path,
        dpi=dpi,
        psm=psm,
    )
