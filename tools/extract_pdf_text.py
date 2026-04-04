#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from pathlib import Path

try:
    from pypdf import PdfReader  # type: ignore
except ImportError:  # pragma: no cover - handled at runtime
    PdfReader = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract raw text from a PDF page range into a .txt file for Ollama drafting."
    )
    parser.add_argument("pdf_path")
    parser.add_argument("--start-page", type=int, required=True, help="One-based start page.")
    parser.add_argument("--end-page", type=int, required=True, help="One-based end page.")
    parser.add_argument("--output", type=Path, required=True, help="Output .txt file path.")
    parser.add_argument(
        "--page-breaks",
        action="store_true",
        help="Insert a page marker between extracted pages.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output.",
    )
    return parser.parse_args()


def require_pypdf() -> None:
    if PdfReader is None:
        raise SystemExit(
            "Missing dependency: pypdf\n"
            "Install with: pip install pypdf"
        )


def normalize_input_path_text(value: str) -> str:
    normalized = re.sub(r"\s*[\r\n]+\s*", " ", value)
    return normalized.strip()


def normalize_pdf_path(value: str) -> Path:
    return Path(normalize_input_path_text(value))


def emit_progress(message: str, enabled: bool) -> None:
    if enabled:
        print(message, file=sys.stderr, flush=True)


def normalize_extracted_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"[ \t]+\n", "\n", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    normalized = re.sub(r"[ \t]{2,}", " ", normalized)
    return normalized.strip() + "\n"


def extract_pdf_text(
    pdf_path: Path,
    start_page: int,
    end_page: int,
    include_page_breaks: bool = False,
    progress_enabled: bool = False,
) -> str:
    require_pypdf()
    if start_page < 1 or end_page < 1:
        raise SystemExit("Page numbers must be one-based positive integers.")
    if end_page < start_page:
        raise SystemExit("--end-page must be greater than or equal to --start-page.")

    emit_progress(f"Opening PDF: {pdf_path}", progress_enabled)
    reader = PdfReader(str(pdf_path))
    total_pages = len(reader.pages)
    emit_progress(f"Loaded PDF with {total_pages} pages", progress_enabled)

    start_index = start_page - 1
    end_index = min(end_page, total_pages)
    if start_index >= total_pages:
        raise SystemExit(
            f"Start page {start_page} is outside the PDF page count ({total_pages})."
        )

    chunks: list[str] = []
    for page_number in range(start_index + 1, end_index + 1):
        emit_progress(f"Extracting page {page_number}", progress_enabled)
        page_text = reader.pages[page_number - 1].extract_text() or ""
        normalized_page = normalize_extracted_text(page_text)
        if include_page_breaks and chunks:
            chunks.append(f"\n--- Page {page_number} ---\n\n")
        chunks.append(normalized_page)

    combined = "".join(chunks).strip() + "\n"
    return combined


def main() -> None:
    args = parse_args()
    pdf_path = normalize_pdf_path(args.pdf_path)
    if str(pdf_path) != args.pdf_path:
        emit_progress(
            f"Normalized multiline PDF path to: {pdf_path}",
            enabled=not args.quiet,
        )
    extracted = extract_pdf_text(
        pdf_path=pdf_path,
        start_page=args.start_page,
        end_page=args.end_page,
        include_page_breaks=args.page_breaks,
        progress_enabled=not args.quiet,
    )
    args.output.write_text(extracted, encoding="utf-8")
    emit_progress(f"Wrote extracted text to {args.output}", enabled=not args.quiet)


if __name__ == "__main__":
    main()
