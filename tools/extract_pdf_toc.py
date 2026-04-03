#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from pypdf import PdfReader  # type: ignore
except ImportError:  # pragma: no cover - handled at runtime
    PdfReader = None


IGNORED_TITLES = {
    "contents",
    "content",
    "answer key",
    "answers",
    "acknowledgements",
    "acknowledgments",
    "introduction",
    "foreword",
}


@dataclass
class TocEntry:
    title: str
    page: int | None
    level: int = 1
    source: str = "unknown"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Extract a table of contents from a PDF using embedded bookmarks when available "
            "and text heuristics as a fallback."
        )
    )
    parser.add_argument("pdf_path")
    parser.add_argument(
        "--mode",
        choices=("auto", "bookmarks", "text"),
        default="auto",
        help="Prefer embedded bookmarks, scanned text, or try both.",
    )
    parser.add_argument(
        "--toc-start-page",
        type=int,
        default=1,
        help="First PDF page to scan when using text mode. One-based.",
    )
    parser.add_argument(
        "--toc-end-page",
        type=int,
        default=8,
        help="Last PDF page to scan when using text mode. One-based.",
    )
    parser.add_argument(
        "--format",
        choices=("titles", "text", "json"),
        default="titles",
        help="Output format.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional output file.",
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


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalize_title(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    normalized = normalized.replace("\u2013", "-").replace("\u2014", "-")
    normalized = re.sub(r"\.{2,}", " ", normalized)
    normalized = normalize_whitespace(normalized)
    return normalized.strip(" -._")


def is_probably_content_title(title: str) -> bool:
    lowered = normalize_title(title).lower()
    if not lowered:
        return False
    if lowered in IGNORED_TITLES:
        return False
    if not re.search(r"[a-zA-Z]", lowered):
        return False
    return True


def dedupe_entries(entries: list[TocEntry]) -> list[TocEntry]:
    seen: set[tuple[str, int | None]] = set()
    result: list[TocEntry] = []
    for entry in entries:
        key = (entry.title.lower(), entry.page)
        if key in seen:
            continue
        seen.add(key)
        result.append(entry)
    return result


def build_progress_bar(done: int, total: int, width: int = 24) -> str:
    if total <= 0:
        return "[" + ("-" * width) + "]"
    clamped_done = max(0, min(done, total))
    filled = int(width * clamped_done / total)
    return "[" + ("#" * filled) + ("-" * (width - filled)) + "]"


def emit_progress(message: str, enabled: bool, done: int | None = None, total: int | None = None) -> None:
    if not enabled:
        return
    if done is not None and total is not None and total > 0:
        bar = build_progress_bar(done, total)
        print(f"{bar} {done}/{total} {message}", file=sys.stderr, flush=True)
        return
    print(message, file=sys.stderr, flush=True)


def flatten_outline_items(reader: Any, items: list[Any], level: int = 1) -> list[TocEntry]:
    entries: list[TocEntry] = []
    for item in items:
        if isinstance(item, list):
            entries.extend(flatten_outline_items(reader, item, level + 1))
            continue

        title = normalize_title(str(getattr(item, "title", "") or item))
        if not is_probably_content_title(title):
            continue

        page_number: int | None = None
        try:
            if hasattr(reader, "get_destination_page_number"):
                page_number = int(reader.get_destination_page_number(item)) + 1
        except Exception:
            page_number = None

        entries.append(TocEntry(title=title, page=page_number, level=level, source="bookmarks"))
    return entries


def extract_bookmark_toc(reader: Any) -> list[TocEntry]:
    outline = None
    for attribute_name in ("outline", "outlines"):
        try:
            outline = getattr(reader, attribute_name)
        except Exception:
            outline = None
        if outline:
            break

    if outline is None:
        return []

    if not isinstance(outline, list):
        outline = [outline]

    return dedupe_entries(flatten_outline_items(reader, outline))


def parse_toc_line(line: str) -> TocEntry | None:
    cleaned = normalize_title(line)
    if not cleaned:
        return None

    patterns = [
        r"^(?P<label>(?:unit|chapter|lesson)\s+\d+[A-Za-z]?)\s*[:.\-]?\s*(?P<title>.+?)\s+(?P<page>\d{1,4})$",
        r"^(?P<number>\d+[A-Za-z]?)\s+(?P<title>.+?)\s+(?P<page>\d{1,4})$",
        r"^(?P<title>.+?)\s+\.{2,}\s*(?P<page>\d{1,4})$",
        r"^(?P<title>[A-Za-z].+?)\s+(?P<page>\d{1,4})$",
    ]

    for pattern in patterns:
        match = re.match(pattern, cleaned, flags=re.IGNORECASE)
        if not match:
            continue

        title = match.groupdict().get("title") or cleaned
        label = match.groupdict().get("label") or match.groupdict().get("number")
        if label:
            title = f"{label} {title}"
        title = normalize_title(title)
        if not is_probably_content_title(title):
            continue

        try:
            page = int(match.group("page"))
        except (TypeError, ValueError):
            page = None
        return TocEntry(title=title, page=page, source="text")

    return None


def extract_text_toc(
    reader: Any,
    start_page: int,
    end_page: int,
    progress_enabled: bool = False,
) -> list[TocEntry]:
    start_index = max(start_page - 1, 0)
    end_index = min(end_page, len(reader.pages))
    entries: list[TocEntry] = []
    total_pages = max(0, end_index - start_index)

    for offset, page_index in enumerate(range(start_index, end_index), start=1):
        emit_progress(
            f"Scanning TOC page {page_index + 1}",
            enabled=progress_enabled,
            done=offset,
            total=total_pages,
        )
        page = reader.pages[page_index]
        text = page.extract_text() or ""
        for raw_line in text.splitlines():
            entry = parse_toc_line(raw_line)
            if entry is not None:
                entries.append(entry)

    return dedupe_entries(entries)


def choose_entries(bookmark_entries: list[TocEntry], text_entries: list[TocEntry], mode: str) -> list[TocEntry]:
    if mode == "bookmarks":
        return bookmark_entries
    if mode == "text":
        return text_entries
    return bookmark_entries or text_entries


def extract_toc(
    pdf_path: Path,
    mode: str = "auto",
    toc_start_page: int = 1,
    toc_end_page: int = 8,
    progress_enabled: bool = False,
) -> list[TocEntry]:
    require_pypdf()
    emit_progress(f"Opening PDF: {pdf_path}", enabled=progress_enabled)
    reader = PdfReader(str(pdf_path))
    emit_progress(f"Loaded PDF with {len(reader.pages)} pages", enabled=progress_enabled)

    bookmark_entries: list[TocEntry] = []
    if mode in {"auto", "bookmarks"}:
        emit_progress("Checking embedded PDF bookmarks", enabled=progress_enabled)
        bookmark_entries = extract_bookmark_toc(reader)
        emit_progress(
            f"Bookmark extraction found {len(bookmark_entries)} candidate entries",
            enabled=progress_enabled,
        )

    text_entries: list[TocEntry] = []
    if mode in {"auto", "text"}:
        emit_progress(
            f"Scanning pages {toc_start_page} to {toc_end_page} for TOC text",
            enabled=progress_enabled,
        )
        text_entries = extract_text_toc(
            reader,
            toc_start_page,
            toc_end_page,
            progress_enabled=progress_enabled,
        )
        emit_progress(
            f"Text extraction found {len(text_entries)} candidate entries",
            enabled=progress_enabled,
        )
    return choose_entries(bookmark_entries, text_entries, mode)


def render_titles(entries: list[TocEntry]) -> str:
    return "\n".join(entry.title for entry in entries) + ("\n" if entries else "")


def render_text(entries: list[TocEntry]) -> str:
    lines = []
    for entry in entries:
        if entry.page is None:
            lines.append(f"{entry.title}")
        else:
            lines.append(f"{entry.title} | page {entry.page} | {entry.source}")
    return "\n".join(lines) + ("\n" if lines else "")


def render_json(entries: list[TocEntry]) -> str:
    payload = [
        {
            "title": entry.title,
            "page": entry.page,
            "level": entry.level,
            "source": entry.source,
        }
        for entry in entries
    ]
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def render(entries: list[TocEntry], output_format: str) -> str:
    if output_format == "titles":
        return render_titles(entries)
    if output_format == "json":
        return render_json(entries)
    return render_text(entries)


def main() -> None:
    args = parse_args()
    pdf_path = normalize_pdf_path(args.pdf_path)
    if str(pdf_path) != args.pdf_path:
        emit_progress(
            f"Normalized multiline PDF path to: {pdf_path}",
            enabled=not args.quiet,
        )
    entries = extract_toc(
        pdf_path=pdf_path,
        mode=args.mode,
        toc_start_page=args.toc_start_page,
        toc_end_page=args.toc_end_page,
        progress_enabled=not args.quiet,
    )
    rendered = render(entries, args.format)
    if args.output is not None:
        args.output.write_text(rendered, encoding="utf-8")
        emit_progress(f"Wrote {len(entries)} TOC entries to {args.output}", enabled=not args.quiet)
        return
    print(rendered, end="")


if __name__ == "__main__":
    main()
