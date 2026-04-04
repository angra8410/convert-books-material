#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

try:
    import yaml
except ImportError:
    print("Missing dependency: pyyaml\nInstall with: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


@dataclass
class ChapterRecord:
    book: Dict[str, Any]
    chapter: Dict[str, Any]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import curated note files into a content repository JSON."
    )
    parser.add_argument(
        "source_dir",
        nargs="?",
        default="source_notes",
        help="Directory containing curated note files.",
    )
    parser.add_argument(
        "output_file",
        nargs="?",
        default="app/src/main/assets/content_repository.json",
        help="Output JSON file path.",
    )
    parser.add_argument(
        "--book-id",
        action="append",
        dest="book_ids",
        help="Filter to one or more book ids. Repeat the flag to include multiple books.",
    )
    parser.add_argument(
        "--chapter-order-min",
        type=int,
        help="Only include chapters with order >= this value.",
    )
    parser.add_argument(
        "--chapter-order-max",
        type=int,
        help="Only include chapters with order <= this value.",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Print a summary preview instead of writing the output file.",
    )
    parser.add_argument(
        "--preview-detailed",
        action="store_true",
        help="Include chapter metadata counts and source files in preview output.",
    )
    return parser.parse_args()


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "untitled"


def ensure_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def parse_markdown_sections(body: str) -> Dict[str, Any]:
    sections: Dict[str, List[str]] = {}
    current = None
    first_heading = None

    for raw_line in body.splitlines():
        line = raw_line.rstrip()

        heading_match = re.match(r"^#\s+(.+?)\s*$", line)
        if heading_match:
            heading = heading_match.group(1).strip()
            if first_heading is None:
                first_heading = heading
            current = heading.lower()
            sections[current] = []
            continue

        if current is not None:
            sections[current].append(line)

    result: Dict[str, Any] = {}

    if first_heading:
        result["title"] = first_heading

    def clean_lines(lines: List[str]) -> List[str]:
        return [ln.strip() for ln in lines if ln.strip()]

    if "summary" in sections:
        result["summary"] = " ".join(clean_lines(sections["summary"])).strip()

    if "points" in sections:
        result["points"] = [
            re.sub(r"^-+\s*", "", ln).strip()
            for ln in clean_lines(sections["points"])
            if ln.strip().startswith("-")
        ]

    if "pitfalls" in sections:
        result["pitfalls"] = [
            re.sub(r"^-+\s*", "", ln).strip()
            for ln in clean_lines(sections["pitfalls"])
            if ln.strip().startswith("-")
        ]

    if "examples" in sections:
        examples: List[Dict[str, str]] = []
        for ln in clean_lines(sections["examples"]):
            if not ln.startswith("-"):
                continue
            item = re.sub(r"^-+\s*", "", ln).strip()
            if "|" in item:
                english, note = [p.strip() for p in item.split("|", 1)]
                examples.append({"english": english, "note": note})
            else:
                examples.append({"english": item})
        result["examples"] = examples

    if "practiceprompts" in sections:
        prompts: List[Dict[str, Any]] = []
        prompt_index = 1
        for ln in clean_lines(sections["practiceprompts"]):
            if not ln.startswith("-"):
                continue
            item = re.sub(r"^-+\s*", "", ln).strip()
            prompts.append({
                "type": "open_text",
                "targetSkill": "WRITING",
                "prompt": item,
                "_autoIndex": prompt_index
            })
            prompt_index += 1
        result["practicePrompts"] = prompts

    return result


def parse_markdown_with_front_matter(text: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    text = text.lstrip("\ufeff")

    lines = text.splitlines()

    start = 0
    while start < len(lines) and not lines[start].strip():
        start += 1

    if start >= len(lines) or lines[start].strip() != "---":
        return {}, parse_markdown_sections(text)

    end = start + 1
    while end < len(lines) and lines[end].strip() != "---":
        end += 1

    if end >= len(lines):
        return {}, parse_markdown_sections(text)

    fm_raw = "\n".join(lines[start + 1:end])
    body = "\n".join(lines[end + 1:])

    front_matter = yaml.safe_load(fm_raw) or {}
    body_data = parse_markdown_sections(body)
    return front_matter, body_data


def infer_book_from_path(path: Path) -> Dict[str, Any]:
    folder = path.parent.name.strip().lower()

    if folder == "advanced-grammar":
        return {
            "id": "advanced-grammar-in-use",
            "title": "Advanced Grammar in Use",
            "author": "Martin Hewings",
            "cefr": ["C1", "C2"],
            "tags": ["grammar"],
        }

    if folder == "vocabulary":
        return {
            "id": "english-vocabulary-in-use-advanced",
            "title": "English Vocabulary in Use Advanced",
            "author": "Michael McCarthy; Felicity O'Dell",
            "cefr": ["C1", "C2"],
            "tags": ["vocabulary"],
        }

    return {
        "id": slugify(folder),
        "title": folder.replace("-", " ").title(),
        "author": "",
        "cefr": [],
        "tags": [],
    }


def normalize_examples(value: Any) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for item in ensure_list(value):
        if isinstance(item, str):
            result.append({"english": item})
        elif isinstance(item, dict):
            english = str(item.get("english", "")).strip()
            if not english:
                continue
            example: Dict[str, Any] = {"english": english}
            note = str(item.get("note", "")).strip()
            if note:
                example["note"] = note
            result.append(example)
    return result


def normalize_practice_prompts(chapter_id: str, value: Any) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []

    for index, item in enumerate(ensure_list(value), start=1):
        if isinstance(item, str):
            prompt_text = item.strip()
            if not prompt_text:
                continue
            result.append({
                "id": f"{chapter_id}-prompt-{index}",
                "type": "open_text",
                "targetSkill": "WRITING",
                "prompt": prompt_text
            })
            continue

        if isinstance(item, dict):
            prompt = str(item.get("prompt", "")).strip()
            if not prompt:
                continue

            provided_id = str(item.get("id", "")).strip()
            auto_index = item.get("_autoIndex", index)

            normalized = {
                "id": provided_id if provided_id else f"{chapter_id}-prompt-{auto_index}",
                "type": str(item.get("type", "open_text")).strip() or "open_text",
                "targetSkill": str(item.get("targetSkill", "WRITING")).strip() or "WRITING",
                "prompt": prompt
            }

            for optional_key in ("hint", "sampleAnswer", "difficulty", "estimatedMinutes"):
                if optional_key in item and item[optional_key] is not None:
                    normalized[optional_key] = item[optional_key]

            result.append(normalized)

    return result


def load_note_file(path: Path) -> ChapterRecord:
    ext = path.suffix.lower()

    if ext == ".json":
        try:
            raw = path.read_text(encoding="utf-8-sig")
            if not raw.strip():
                raise ValueError(f"JSON file is empty: {path}")
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Invalid JSON in {path} at line {e.lineno}, column {e.colno}: {e.msg}"
            ) from e

    elif ext in {".yaml", ".yml"}:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))

    elif ext == ".md":
        text = path.read_text(encoding="utf-8-sig")
        fm, body_data = parse_markdown_with_front_matter(text)

        data = dict(fm) if isinstance(fm, dict) else {}

        if "chapter" in data and isinstance(data["chapter"], dict):
            chapter = dict(data["chapter"])

            for key, value in body_data.items():
                if key == "title" and chapter.get("title"):
                    continue
                chapter[key] = value

            data["chapter"] = chapter
        else:
            inferred_title = body_data.get("title") or path.stem.replace("-", " ").title()
            data = {
                "chapter": {
                    "id": slugify(path.stem),
                    "title": inferred_title,
                    "order": 999999,
                    **body_data,
                }
            }

    else:
        raise ValueError(f"Unsupported file type: {path.name}")

    if data is None:
        raise ValueError(f"File is empty: {path}")

    if not isinstance(data, dict):
        raise ValueError(
            f"Top-level YAML/JSON must be an object in {path}. "
            f"Got {type(data).__name__} instead."
        )

    if "book" in data or "chapter" in data:
        book = data.get("book")
        chapter = data.get("chapter")

        if book is None:
            book = infer_book_from_path(path)

        if not isinstance(book, dict):
            raise ValueError(f"Missing or invalid 'book' object in {path}")
        if not isinstance(chapter, dict):
            raise ValueError(f"Missing or invalid 'chapter' object in {path}")

        return ChapterRecord(book=book, chapter=chapter)

    inferred_book = infer_book_from_path(path)
    return ChapterRecord(book=inferred_book, chapter=data)


def normalize_book(book: Dict[str, Any]) -> Dict[str, Any]:
    title = str(book.get("title", "")).strip()
    if not title:
        raise ValueError("Book title is required.")

    book_id = str(book.get("id") or slugify(title))
    author = str(book.get("author", "")).strip()

    return {
        "id": book_id,
        "title": title,
        "author": author,
        "cefr": ensure_list(book.get("cefr")),
        "sourceType": "curated_notes",
        "tags": ensure_list(book.get("tags")),
    }


def normalize_chapter(chapter: Dict[str, Any], source_file: str, book: Dict[str, Any]) -> Dict[str, Any]:
    title = str(chapter.get("title", "")).strip()
    if not title:
        raise ValueError(f"Chapter title is required in {source_file}")

    chapter_id = str(chapter.get("id") or slugify(title))
    order_raw = chapter.get("order", 999999)

    try:
        order = int(order_raw)
    except (TypeError, ValueError):
        order = 999999

    chapter_cefr = ensure_list(chapter.get("cefr"))
    chapter_tags = ensure_list(chapter.get("tags"))

    return {
        "id": chapter_id,
        "title": title,
        "order": order,
        "cefr": chapter_cefr if chapter_cefr else ensure_list(book.get("cefr")),
        "tags": chapter_tags,
        "summary": str(chapter.get("summary", "")).strip(),
        "points": [str(x).strip() for x in ensure_list(chapter.get("points")) if str(x).strip()],
        "examples": normalize_examples(chapter.get("examples")),
        "pitfalls": [str(x).strip() for x in ensure_list(chapter.get("pitfalls")) if str(x).strip()],
        "practicePrompts": normalize_practice_prompts(chapter_id, chapter.get("practicePrompts")),
        "related": [str(x).strip() for x in ensure_list(chapter.get("related")) if str(x).strip()],
        "metadata": {
            "sourceFile": source_file
        },
    }


def build_repository(
    source_dir: Path,
    book_ids: set[str] | None = None,
    chapter_order_min: int | None = None,
    chapter_order_max: int | None = None,
) -> Dict[str, Any]:
    files = sorted(
        [
            p for p in source_dir.rglob("*")
            if p.is_file() and p.suffix.lower() in {".json", ".yaml", ".yml", ".md"}
        ]
    )

    if not files:
        raise ValueError(f"No supported note files found in {source_dir}")

    books_map: Dict[str, Dict[str, Any]] = {}

    for file_path in files:
        record = load_note_file(file_path)
        book = normalize_book(record.book)
        chapter = normalize_chapter(record.chapter, str(file_path.relative_to(source_dir)), book)

        if book_ids and book["id"] not in book_ids:
            continue
        if chapter_order_min is not None and chapter["order"] < chapter_order_min:
            continue
        if chapter_order_max is not None and chapter["order"] > chapter_order_max:
            continue

        existing = books_map.get(book["id"])
        if existing is None:
            books_map[book["id"]] = {**book, "chapters": []}
            existing = books_map[book["id"]]
        else:
            for key in ("title", "author"):
                if existing.get(key) != book.get(key):
                    raise ValueError(
                        f"Book metadata mismatch for book id '{book['id']}' in {file_path}. "
                        f"Expected {key}={existing.get(key)!r}, got {book.get(key)!r}"
                    )

        if any(ch["id"] == chapter["id"] for ch in existing["chapters"]):
            raise ValueError(
                f"Duplicate chapter id '{chapter['id']}' in book '{book['id']}' from file {file_path}"
            )

        existing["chapters"].append(chapter)

    books = list(books_map.values())
    for book in books:
        book["chapters"].sort(key=lambda ch: (ch["order"], ch["title"].lower()))

    books.sort(key=lambda b: b["title"].lower())

    return {
        "version": 2,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "books": books,
    }


def format_preview(repository: Dict[str, Any], detailed: bool = False) -> str:
    books = repository["books"]
    lines = [
        f"Preview: {len(books)} book(s), "
        f"{sum(len(book['chapters']) for book in books)} chapter(s)"
    ]
    for book in books:
        lines.append(
            f"- {book['title']} ({book['id']}): {len(book['chapters'])} chapter(s)"
        )
        for chapter in book["chapters"]:
            lines.append(
                f"  {chapter['order']:>3}  {chapter['id']}  {chapter['title']}"
            )
            if detailed:
                tags_count = len(chapter.get("tags", []))
                points_count = len(chapter.get("points", []))
                examples_count = len(chapter.get("examples", []))
                prompts_count = len(chapter.get("practicePrompts", []))
                source_file = chapter.get("metadata", {}).get("sourceFile", "")
                cefr = ",".join(chapter.get("cefr", [])) or "-"
                lines.append(
                    f"       cefr={cefr} tags={tags_count} points={points_count} "
                    f"examples={examples_count} prompts={prompts_count} source={source_file}"
                )
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    source_dir = Path(args.source_dir)
    output_file = Path(args.output_file)
    book_ids = set(args.book_ids or [])

    repository = build_repository(
        source_dir,
        book_ids=book_ids or None,
        chapter_order_min=args.chapter_order_min,
        chapter_order_max=args.chapter_order_max,
    )

    if args.preview:
        print(format_preview(repository, detailed=args.preview_detailed))
        return

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(
        json.dumps(repository, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    total_books = len(repository["books"])
    total_chapters = sum(len(book["chapters"]) for book in repository["books"])

    print(f"Imported {total_books} book(s), {total_chapters} chapter(s)")
    print(f"Output: {output_file}")


if __name__ == "__main__":
    main()


