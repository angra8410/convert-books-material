#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("Missing dependency: pyyaml\nInstall with: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


DEFAULT_SOURCE_DIR = Path("source_notes")


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^a-z0-9]+", "-", ascii_only.lower()).strip("-")
    collapsed = re.sub(r"-{2,}", "-", cleaned)
    return collapsed or "untitled"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate one chapter stub file per unit for a whole book so the notes "
            "can later be imported by tools/import_notes.py."
        )
    )
    parser.add_argument("--book-title", required=True)
    parser.add_argument("--book-author", default="")
    parser.add_argument("--book-id", help="Optional stable id. Defaults to a slug from the title.")
    parser.add_argument("--book-cefr", nargs="+", required=True)
    parser.add_argument("--book-tags", nargs="*", default=[])
    parser.add_argument(
        "--chapter-titles",
        nargs="*",
        default=[],
        help="Chapter titles inline. Use this for short lists.",
    )
    parser.add_argument(
        "--chapters-file",
        type=Path,
        help=(
            "Optional text file with one chapter title per line. Blank lines and lines "
            "starting with # are ignored."
        ),
    )
    parser.add_argument(
        "--folder-name",
        help="Optional output folder name under source_notes. Defaults to the book id slug.",
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=DEFAULT_SOURCE_DIR,
        help="Root source_notes directory.",
    )
    parser.add_argument(
        "--format",
        choices=("yaml", "json", "md"),
        default="yaml",
        help="Stub file format.",
    )
    parser.add_argument(
        "--start-order",
        type=int,
        default=1,
        help="Order number to start from.",
    )
    parser.add_argument(
        "--chapter-file-prefix",
        default="unit",
        help="File name prefix, for example 'unit' or 'chapter'.",
    )
    parser.add_argument(
        "--chapter-tags",
        nargs="*",
        default=[],
        help="Default tags applied to every chapter stub.",
    )
    parser.add_argument(
        "--prompt-skill",
        choices=("WRITING", "READING", "LISTENING", "SPEAKING", "VOCABULARY"),
        default="WRITING",
        help="Default target skill for the starter practice prompt.",
    )
    parser.add_argument(
        "--include-starter-prompts",
        action="store_true",
        help="Add one starter open-text prompt to each chapter stub.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow overwriting existing stub files.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the plan without writing files.",
    )
    return parser.parse_args()


def parse_chapter_lines(lines: list[str]) -> list[str]:
    titles: list[str] = []
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        line = re.sub(r"^\d+[\.\)\-:]\s*", "", line)
        line = re.sub(r"^(unit|chapter|lesson)\s+\d+\s*[\.\)\-:]?\s*", "", line, flags=re.IGNORECASE)
        cleaned = line.strip()
        if cleaned:
            titles.append(cleaned)
    return titles


def load_chapter_titles(args: argparse.Namespace) -> list[str]:
    titles = list(args.chapter_titles)
    if args.chapters_file is not None:
        lines = args.chapters_file.read_text(encoding="utf-8-sig").splitlines()
        titles.extend(parse_chapter_lines(lines))
    normalized = [title.strip() for title in titles if title.strip()]
    if not normalized:
        raise SystemExit("Provide chapter titles with --chapter-titles or --chapters-file.")
    return normalized


def build_book_metadata(args: argparse.Namespace) -> dict[str, Any]:
    book_id = args.book_id or slugify(args.book_title)
    return {
        "id": book_id,
        "title": args.book_title.strip(),
        "author": args.book_author.strip(),
        "cefr": [value.strip() for value in args.book_cefr if value.strip()],
        "tags": [value.strip() for value in args.book_tags if value.strip()],
    }


def build_prompt_stub(chapter_id: str, title: str, prompt_skill: str) -> dict[str, Any]:
    return {
        "id": f"{chapter_id}-prompt-1",
        "type": "open_text",
        "targetSkill": prompt_skill,
        "prompt": f"Write a short response using the key language from '{title}'.",
    }


def build_chapter_stub(
    title: str,
    order: int,
    book: dict[str, Any],
    chapter_tags: list[str],
    prompt_skill: str,
    include_starter_prompts: bool,
) -> dict[str, Any]:
    chapter_id = slugify(title)
    chapter: dict[str, Any] = {
        "id": chapter_id,
        "title": title,
        "order": order,
        "cefr": list(book["cefr"]),
        "tags": [tag for tag in chapter_tags if tag],
        "summary": "",
        "points": [],
        "examples": [],
        "pitfalls": [],
        "practicePrompts": [],
        "related": [],
    }
    if include_starter_prompts:
        chapter["practicePrompts"] = [build_prompt_stub(chapter_id, title, prompt_skill)]
    return chapter


def render_yaml(book: dict[str, Any], chapter: dict[str, Any]) -> str:
    payload = {"book": book, "chapter": chapter}
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)


def render_json(book: dict[str, Any], chapter: dict[str, Any]) -> str:
    payload = {"book": book, "chapter": chapter}
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def render_markdown(book: dict[str, Any], chapter: dict[str, Any]) -> str:
    front_matter = yaml.safe_dump({"book": book, "chapter": {
        "id": chapter["id"],
        "title": chapter["title"],
        "order": chapter["order"],
        "cefr": chapter["cefr"],
        "tags": chapter["tags"],
        "related": chapter["related"],
    }}, sort_keys=False, allow_unicode=True).rstrip()

    prompt_lines = []
    for prompt in chapter["practicePrompts"]:
        prompt_lines.append(f"- {prompt['prompt']}")

    sections = [
        "---",
        front_matter,
        "---",
        "",
        "# Summary",
        chapter["summary"],
        "",
        "# Points",
        *(f"- {item}" for item in chapter["points"]),
        "",
        "# Examples",
        *(f"- {item['english']}" + (f" | {item['note']}" if item.get("note") else "") for item in chapter["examples"]),
        "",
        "# Pitfalls",
        *(f"- {item}" for item in chapter["pitfalls"]),
        "",
        "# PracticePrompts",
        *prompt_lines,
        "",
    ]
    return "\n".join(sections)


def file_extension(output_format: str) -> str:
    return {"yaml": ".yaml", "json": ".json", "md": ".md"}[output_format]


def render_content(output_format: str, book: dict[str, Any], chapter: dict[str, Any]) -> str:
    if output_format == "yaml":
        return render_yaml(book, chapter)
    if output_format == "json":
        return render_json(book, chapter)
    return render_markdown(book, chapter)


def build_output_path(
    source_dir: Path,
    folder_name: str,
    prefix: str,
    order: int,
    title: str,
    output_format: str,
) -> Path:
    return source_dir / folder_name / f"{prefix}-{order:02d}-{slugify(title)}{file_extension(output_format)}"


def scaffold_book(args: argparse.Namespace) -> list[Path]:
    chapter_titles = load_chapter_titles(args)
    book = build_book_metadata(args)
    folder_name = args.folder_name or book["id"]
    written_paths: list[Path] = []

    for offset, title in enumerate(chapter_titles):
        order = args.start_order + offset
        chapter = build_chapter_stub(
            title=title,
            order=order,
            book=book,
            chapter_tags=[value.strip() for value in args.chapter_tags],
            prompt_skill=args.prompt_skill,
            include_starter_prompts=args.include_starter_prompts,
        )
        output_path = build_output_path(
            source_dir=args.source_dir,
            folder_name=folder_name,
            prefix=args.chapter_file_prefix,
            order=order,
            title=title,
            output_format=args.format,
        )
        if output_path.exists() and not args.overwrite:
            raise SystemExit(
                f"Refusing to overwrite existing file: {output_path}. Use --overwrite to replace it."
            )
        content = render_content(args.format, book, chapter)
        written_paths.append(output_path)
        if args.dry_run:
            continue
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")

    return written_paths


def main() -> None:
    args = parse_args()
    written_paths = scaffold_book(args)
    if args.dry_run:
        print(f"Dry run: {len(written_paths)} file(s) would be created.")
    else:
        print(f"Created {len(written_paths)} file(s).")
    for path in written_paths:
        print(path)


if __name__ == "__main__":
    main()
