#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import socket
import sys
import unicodedata
from pathlib import Path
from typing import Any
from urllib import error, request

try:
    import yaml
except ImportError:
    print("Missing dependency: pyyaml\nInstall with: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


PLACEHOLDER_PROMPT_PATTERN = re.compile(
    r"^Write a short response using the key language from '.+'\.$"
)
VALID_TARGET_SKILLS = {"WRITING", "READING", "LISTENING", "SPEAKING", "VOCABULARY"}
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "it",
    "its",
    "of",
    "on",
    "or",
    "that",
    "the",
    "their",
    "this",
    "to",
    "use",
    "with",
    "word",
    "words",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Use local Ollama to draft missing fields for a scaffolded chapter file "
            "from raw unit text."
        )
    )
    parser.add_argument("--chapter-file", type=Path, required=True)
    parser.add_argument("--source-text-file", type=Path, required=True)
    parser.add_argument("--model", default="gemma3:27b")
    parser.add_argument("--host", default="http://127.0.0.1:11434")
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=300,
        help="HTTP timeout for the Ollama call. Large local models may need several minutes.",
    )
    parser.add_argument(
        "--replace-practice-prompts",
        action="store_true",
        help="Replace starter scaffold prompts with Ollama-generated prompts.",
    )
    parser.add_argument(
        "--replace-nonempty",
        action="store_true",
        help="Replace existing non-empty summary, points, examples and pitfalls.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the merged draft back to the chapter file.",
    )
    return parser.parse_args()


def load_structured_file(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    raw = path.read_text(encoding="utf-8-sig")
    if suffix in {".yaml", ".yml"}:
        data = yaml.safe_load(raw)
    elif suffix == ".json":
        data = json.loads(raw)
    else:
        raise SystemExit(
            f"Unsupported chapter file format: {path.name}. "
            "Use YAML or JSON scaffold files."
        )
    if not isinstance(data, dict) or "chapter" not in data or "book" not in data:
        raise SystemExit(f"Expected a top-level book/chapter object in {path}")
    return data


def write_structured_file(path: Path, payload: dict[str, Any]) -> None:
    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        path.write_text(
            yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        return
    if suffix == ".json":
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return
    raise SystemExit(f"Unsupported chapter file format: {path.name}")


def build_prompt(book: dict[str, Any], chapter: dict[str, Any], source_text: str) -> str:
    return (
        "You are drafting structured study content for an English-learning app.\n"
        "Return valid JSON only with these keys:\n"
        "summary: string\n"
        "points: array of concise strings\n"
        "examples: array of objects with english and optional note\n"
        "pitfalls: array of concise strings\n"
        "practicePrompts: array of objects with id, type, targetSkill, prompt\n\n"
        "Requirements:\n"
        "- Base everything on the source text only.\n"
        "- Keep the summary to 1 or 2 sentences.\n"
        "- Write 4 to 6 points.\n"
        "- Write 3 to 6 examples only when they are explicitly supported by the source text.\n"
        "- Write 2 to 4 pitfalls when possible.\n"
        "- You may omit examples or practicePrompts if the source text does not support them clearly.\n"
        "- Ground every field in the source text. Do not invent facts that are not supported by it.\n"
        "- Prefer examples that reuse exact phrases or very close wording from the source text.\n"
        "- Keep CEFR and tone appropriate for the chapter level.\n"
        "- Use open_text prompts.\n"
        "- Use targetSkill values only from this set: WRITING, READING, LISTENING, SPEAKING, VOCABULARY.\n"
        "- Do not mention page numbers or exercise numbering.\n"
        "- Do not wrap the JSON in markdown fences.\n\n"
        f"Book title: {book.get('title', '')}\n"
        f"Book author: {book.get('author', '')}\n"
        f"Book CEFR: {', '.join(book.get('cefr', []))}\n"
        f"Chapter id: {chapter.get('id', '')}\n"
        f"Chapter title: {chapter.get('title', '')}\n"
        f"Chapter order: {chapter.get('order', '')}\n"
        f"Chapter CEFR: {', '.join(chapter.get('cefr', []))}\n"
        f"Existing tags: {', '.join(chapter.get('tags', []))}\n\n"
        "Source text:\n"
        f"{source_text.strip()}\n"
    )


def normalize_ascii_punctuation(value: str) -> str:
    normalized = value
    for _ in range(2):
        if not any(marker in normalized for marker in ("â", "Ã", "€", "™", "Â")):
            break
        try:
            repaired = normalized.encode("cp1252").decode("utf-8")
            if repaired == normalized:
                break
            normalized = repaired
        except (UnicodeEncodeError, UnicodeDecodeError):
            break
    normalized = unicodedata.normalize("NFKC", normalized)
    replacements = {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u2026": "...",
        "\u00a0": " ",
        "â€™": "'",
        "â€œ": '"',
        "â€\x9d": '"',
        "â€“": "-",
        "â€”": "-",
        "â€¦": "...",
        "ā€TM": "'",
        "\u00e2\u20acTM": "'",
    }
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def tokenize_content_words(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-Z]{3,}", normalize_ascii_punctuation(value).lower())
        if token not in STOPWORDS
    }


def is_grounded_text(candidate: str, source_text: str, min_overlap_ratio: float = 0.5) -> bool:
    normalized_candidate = normalize_ascii_punctuation(candidate).lower()
    normalized_source = normalize_ascii_punctuation(source_text).lower()
    if normalized_candidate and normalized_candidate in normalized_source:
        return True

    candidate_tokens = tokenize_content_words(candidate)
    if not candidate_tokens:
        return False
    source_tokens = tokenize_content_words(source_text)
    overlap = candidate_tokens & source_tokens
    return (len(overlap) / len(candidate_tokens)) >= min_overlap_ratio


def extract_source_examples(source_text: str) -> list[dict[str, str]]:
    normalized_source = normalize_ascii_punctuation(source_text)
    examples: list[dict[str, str]] = []
    seen: set[str] = set()
    for match in re.finditer(r"e\.g\.\s*([^.;\n]+)", normalized_source, flags=re.IGNORECASE):
        raw_items = [item.strip() for item in match.group(1).split(",")]
        for raw_item in raw_items:
            if not raw_item:
                continue
            if len(raw_item.split()) > 8:
                continue
            key = raw_item.lower()
            if key in seen:
                continue
            seen.add(key)
            examples.append({"english": raw_item})
    return examples


def call_ollama(host: str, model: str, prompt: str, timeout_seconds: int) -> dict[str, Any]:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
    }
    url = host.rstrip("/") + "/api/generate"
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout_seconds) as response:
            decoded = json.loads(response.read().decode("utf-8"))
    except error.URLError as exc:
        raise SystemExit(
            f"Could not reach Ollama at {url}. Make sure Ollama is running."
        ) from exc
    except TimeoutError as exc:
        raise SystemExit(
            f"Ollama timed out after {timeout_seconds} seconds. "
            "Try a smaller source text, a smaller model, or a larger --timeout-seconds value."
        ) from exc
    except socket.timeout as exc:
        raise SystemExit(
            f"Ollama timed out after {timeout_seconds} seconds. "
            "Try a smaller source text, a smaller model, or a larger --timeout-seconds value."
        ) from exc

    raw_response = str(decoded.get("response", "")).strip()
    if not raw_response:
        raise SystemExit("Ollama returned an empty response.")
    try:
        return json.loads(raw_response)
    except json.JSONDecodeError as exc:
        raise SystemExit(
            "Ollama did not return valid JSON. Try again or tighten the source text."
        ) from exc


def normalize_string_list(value: Any) -> list[str]:
    result: list[str] = []
    if not isinstance(value, list):
        return result
    for item in value:
        text = normalize_ascii_punctuation(str(item))
        if text:
            result.append(text)
    return result


def normalize_examples(value: Any) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    if not isinstance(value, list):
        return result
    for item in value:
        if isinstance(item, str):
            text = normalize_ascii_punctuation(item)
            if text:
                result.append({"english": text})
            continue
        if not isinstance(item, dict):
            continue
        english = normalize_ascii_punctuation(str(item.get("english", "")))
        if not english:
            continue
        example: dict[str, str] = {"english": english}
        note = normalize_ascii_punctuation(str(item.get("note", "")))
        if note:
            example["note"] = note
        result.append(example)
    return result


def infer_default_target_skill(book: dict[str, Any], chapter: dict[str, Any]) -> str:
    tags = [str(tag).lower() for tag in book.get("tags", []) + chapter.get("tags", [])]
    title_text = f"{book.get('title', '')} {chapter.get('title', '')}".lower()
    if "vocabulary" in tags or "vocabulary" in title_text:
        return "VOCABULARY"
    if "listening" in tags or "listen" in title_text:
        return "LISTENING"
    if "speaking" in tags or "speaking" in title_text:
        return "SPEAKING"
    if "reading" in tags or "reading" in title_text:
        return "READING"
    return "WRITING"


def build_fallback_practice_prompts(
    chapter_id: str,
    chapter_title: str,
    fallback_skill: str,
) -> list[dict[str, str]]:
    normalized_title = normalize_ascii_punctuation(chapter_title)
    if fallback_skill == "VOCABULARY":
        prompts = [
            f"List five useful words or phrases from '{normalized_title}' and explain what they mean.",
            f"Write five short sentences using vocabulary or collocations from '{normalized_title}'.",
        ]
    elif fallback_skill == "READING":
        prompts = [
            f"Summarize the main idea of '{normalized_title}' in your own words.",
            f"Explain two key details from '{normalized_title}' and why they matter.",
        ]
    elif fallback_skill == "LISTENING":
        prompts = [
            f"Summarize the speaker's main point in '{normalized_title}'.",
            f"Describe one supporting detail from '{normalized_title}' and why it is important.",
        ]
    elif fallback_skill == "SPEAKING":
        prompts = [
            f"Give a short spoken explanation of the main idea in '{normalized_title}'.",
            f"Give one example related to '{normalized_title}' and explain it clearly.",
        ]
    else:
        prompts = [
            f"Explain the main idea of '{normalized_title}' in your own words.",
            f"Write a short response using key language from '{normalized_title}'.",
        ]

    return [
        {
            "id": f"{chapter_id}-prompt-{index}",
            "type": "open_text",
            "targetSkill": fallback_skill,
            "prompt": prompt,
        }
        for index, prompt in enumerate(prompts, start=1)
    ]


def normalize_target_skill(value: Any, fallback: str) -> str:
    normalized = normalize_ascii_punctuation(str(value or "")).upper()
    if normalized in VALID_TARGET_SKILLS:
        return normalized

    alias_map = {
        "VOCAB": "VOCABULARY",
        "COLLOCATION": "VOCABULARY",
        "COLLOCATIONS": "VOCABULARY",
        "REGISTER": "VOCABULARY",
        "GRAMMAR": "WRITING",
    }
    return alias_map.get(normalized, fallback)


def normalize_prompts(
    chapter_id: str,
    value: Any,
    fallback_skill: str,
    source_text: str,
) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    if not isinstance(value, list):
        return result
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            continue
        prompt_text = normalize_ascii_punctuation(str(item.get("prompt", "")))
        if not prompt_text:
            continue
        prompt_id = f"{chapter_id}-prompt-{index}"
        prompt_type = "open_text"
        target_skill = normalize_target_skill(item.get("targetSkill"), fallback_skill)
        if not is_grounded_text(prompt_text, source_text, min_overlap_ratio=0.2):
            continue
        result.append(
            {
                "id": prompt_id,
                "type": prompt_type,
                "targetSkill": target_skill,
                "prompt": prompt_text,
            }
        )
    return result


def normalize_draft(
    book: dict[str, Any],
    chapter: dict[str, Any],
    draft: dict[str, Any],
    source_text: str,
) -> dict[str, Any]:
    fallback_skill = infer_default_target_skill(book, chapter)
    draft_examples = [
        example
        for example in normalize_examples(draft.get("examples"))
        if is_grounded_text(example["english"], source_text)
    ]
    if not draft_examples:
        draft_examples = extract_source_examples(source_text)

    draft_prompts = normalize_prompts(
        chapter["id"],
        draft.get("practicePrompts"),
        fallback_skill,
        source_text,
    )
    if not draft_prompts:
        draft_prompts = build_fallback_practice_prompts(
            chapter["id"],
            chapter["title"],
            fallback_skill,
        )

    return {
        "summary": normalize_ascii_punctuation(str(draft.get("summary", ""))),
        "points": normalize_string_list(draft.get("points")),
        "examples": draft_examples,
        "pitfalls": normalize_string_list(draft.get("pitfalls")),
        "practicePrompts": draft_prompts,
    }


def has_placeholder_prompt(prompts: list[dict[str, Any]]) -> bool:
    if len(prompts) != 1:
        return False
    prompt_text = str(prompts[0].get("prompt", "")).strip()
    return bool(PLACEHOLDER_PROMPT_PATTERN.match(prompt_text))


def merge_chapter_data(
    chapter: dict[str, Any],
    draft: dict[str, Any],
    replace_nonempty: bool = False,
    replace_practice_prompts: bool = False,
) -> dict[str, Any]:
    merged = dict(chapter)

    if draft["summary"] and (replace_nonempty or not str(chapter.get("summary", "")).strip()):
        merged["summary"] = draft["summary"]

    for field in ("points", "examples", "pitfalls"):
        current = chapter.get(field) or []
        if draft[field] and (replace_nonempty or not current):
            merged[field] = draft[field]

    current_prompts = chapter.get("practicePrompts") or []
    should_replace_prompts = (
        replace_practice_prompts
        or not current_prompts
        or has_placeholder_prompt(current_prompts)
    )
    if draft["practicePrompts"] and should_replace_prompts:
        merged["practicePrompts"] = draft["practicePrompts"]

    return merged


def main() -> None:
    args = parse_args()
    payload = load_structured_file(args.chapter_file)
    source_text = args.source_text_file.read_text(encoding="utf-8-sig")
    prompt = build_prompt(payload["book"], payload["chapter"], source_text)
    raw_draft = call_ollama(args.host, args.model, prompt, args.timeout_seconds)
    normalized_draft = normalize_draft(
        payload["book"],
        payload["chapter"],
        raw_draft,
        source_text,
    )
    merged_chapter = merge_chapter_data(
        payload["chapter"],
        normalized_draft,
        replace_nonempty=args.replace_nonempty,
        replace_practice_prompts=args.replace_practice_prompts,
    )

    if args.apply:
        payload["chapter"] = merged_chapter
        write_structured_file(args.chapter_file, payload)
        print(f"Updated {args.chapter_file}")
        return

    print(json.dumps(merged_chapter, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
