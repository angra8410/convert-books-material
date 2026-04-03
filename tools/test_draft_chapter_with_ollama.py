from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parent
SCRIPT_PATH = TOOLS_DIR / "draft_chapter_with_ollama.py"
MODULE_SPEC = importlib.util.spec_from_file_location(
    "draft_chapter_with_ollama",
    SCRIPT_PATH,
)
drafter = importlib.util.module_from_spec(MODULE_SPEC)
assert MODULE_SPEC.loader is not None
sys.modules[MODULE_SPEC.name] = drafter
MODULE_SPEC.loader.exec_module(drafter)


class DraftChapterWithOllamaTest(unittest.TestCase):
    def test_normalize_ascii_punctuation_handles_smart_quotes_and_mojibake(self) -> None:
        text = (
            "Be aware of a word"
            + "\u00e2\u20ac\u2122"
            + "s register and use "
            + "\u201cnatural\u201d"
            + " punctuation."
        )

        normalized = drafter.normalize_ascii_punctuation(text)

        self.assertEqual("Be aware of a word's register and use \"natural\" punctuation.", normalized)

    def test_build_prompt_includes_core_book_chapter_and_source_text(self) -> None:
        prompt = drafter.build_prompt(
            book={"title": "Book", "author": "Author", "cefr": ["B2"]},
            chapter={
                "id": "chapter-1",
                "title": "Learning vocabulary",
                "order": 1,
                "cefr": ["B2"],
                "tags": ["vocabulary"],
            },
            source_text="Raw unit text goes here.",
        )

        self.assertIn("Book title: Book", prompt)
        self.assertIn("Chapter title: Learning vocabulary", prompt)
        self.assertIn("Source text:\nRaw unit text goes here.", prompt)

    def test_normalize_draft_shapes_examples_and_prompts(self) -> None:
        draft = drafter.normalize_draft(
            {"title": "English Vocabulary in Use Upper-Intermediate", "tags": ["vocabulary"]},
            {"id": "learning-vocabulary", "title": "Learning vocabulary", "tags": []},
            {
                "summary": "A short summary.",
                "points": ["Point one", "Point two"],
                "examples": [
                    {"english": "rich vocabulary", "note": "collocation"},
                    "to express an opinion",
                ],
                "pitfalls": ["Do not learn words in isolation."],
                "practicePrompts": [
                    {"id": "prompt1", "prompt": "Write five collocations.", "targetSkill": "collocations"}
                ],
            },
            "You should learn words in phrases and notice collocations such as rich vocabulary and to express an opinion.",
        )

        self.assertEqual("A short summary.", draft["summary"])
        self.assertEqual(2, len(draft["examples"]))
        self.assertEqual("learning-vocabulary-prompt-1", draft["practicePrompts"][0]["id"])
        self.assertEqual("VOCABULARY", draft["practicePrompts"][0]["targetSkill"])

    def test_merge_chapter_data_only_fills_missing_fields_by_default(self) -> None:
        chapter = {
            "summary": "",
            "points": [],
            "examples": [],
            "pitfalls": [],
            "practicePrompts": [
                {
                    "id": "learning-vocabulary-prompt-1",
                    "type": "open_text",
                    "targetSkill": "WRITING",
                    "prompt": "Write a short response using the key language from 'Learning vocabulary'.",
                }
            ],
        }
        draft = {
            "summary": "Summary",
            "points": ["Point one"],
            "examples": [{"english": "rich vocabulary", "note": "collocation"}],
            "pitfalls": ["Do not learn words in isolation."],
            "practicePrompts": [
                {
                    "id": "learning-vocabulary-prompt-1",
                    "type": "open_text",
                    "targetSkill": "WRITING",
                    "prompt": "Explain what it means to know a word well.",
                }
            ],
        }

        merged = drafter.merge_chapter_data(chapter, draft)

        self.assertEqual("Summary", merged["summary"])
        self.assertEqual(["Point one"], merged["points"])
        self.assertEqual("Explain what it means to know a word well.", merged["practicePrompts"][0]["prompt"])

    def test_merge_chapter_data_keeps_nonempty_fields_without_replace_flag(self) -> None:
        chapter = {
            "summary": "Existing summary",
            "points": ["Existing point"],
            "examples": [{"english": "existing example"}],
            "pitfalls": ["Existing pitfall"],
            "practicePrompts": [
                {
                    "id": "chapter-1-prompt-1",
                    "type": "open_text",
                    "targetSkill": "WRITING",
                    "prompt": "Existing prompt",
                }
            ],
        }
        draft = {
            "summary": "New summary",
            "points": ["New point"],
            "examples": [{"english": "new example"}],
            "pitfalls": ["New pitfall"],
            "practicePrompts": [
                {
                    "id": "chapter-1-prompt-1",
                    "type": "open_text",
                    "targetSkill": "WRITING",
                    "prompt": "New prompt",
                }
            ],
        }

        merged = drafter.merge_chapter_data(chapter, draft)

        self.assertEqual("Existing summary", merged["summary"])
        self.assertEqual(["Existing point"], merged["points"])
        self.assertEqual("Existing prompt", merged["practicePrompts"][0]["prompt"])

    def test_normalize_target_skill_falls_back_to_valid_values(self) -> None:
        self.assertEqual("VOCABULARY", drafter.normalize_target_skill("register", "WRITING"))
        self.assertEqual("WRITING", drafter.normalize_target_skill("unknown", "WRITING"))

    def test_normalize_draft_filters_ungrounded_examples_and_uses_source_fallbacks(self) -> None:
        draft = drafter.normalize_draft(
            {"title": "English Vocabulary in Use Upper-Intermediate", "tags": ["vocabulary"]},
            {"id": "learning-vocabulary", "title": "Learning vocabulary", "tags": []},
            {
                "summary": "Summary",
                "points": ["Point one"],
                "examples": [
                    {"english": "make a decision", "note": "invented"},
                ],
                "pitfalls": ["Pitfall"],
                "practicePrompts": [],
            },
            "Learn collocations, e.g. rich vocabulary, classical music, common sense.",
        )

        self.assertEqual(
            [
                {"english": "rich vocabulary"},
                {"english": "classical music"},
                {"english": "common sense"},
            ],
            draft["examples"],
        )
        self.assertEqual("VOCABULARY", draft["practicePrompts"][0]["targetSkill"])


if __name__ == "__main__":
    unittest.main()
