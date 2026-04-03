from __future__ import annotations

import importlib.util
import shutil
import unittest
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parent
SCRIPT_PATH = TOOLS_DIR / "scaffold_book_notes.py"
MODULE_SPEC = importlib.util.spec_from_file_location(
    "scaffold_book_notes",
    SCRIPT_PATH,
)
scaffolder = importlib.util.module_from_spec(MODULE_SPEC)
assert MODULE_SPEC.loader is not None
MODULE_SPEC.loader.exec_module(scaffolder)


class ScaffoldBookNotesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = TOOLS_DIR / "tmp_scaffold_book_notes"
        if self.workspace.exists():
            shutil.rmtree(self.workspace, ignore_errors=True)
        self.workspace.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.workspace, ignore_errors=True)

    def test_parse_chapter_lines_ignores_blank_comment_and_leading_numbers(self) -> None:
        lines = [
            "",
            "# comment",
            "1 Learning vocabulary",
            "1. Describing people",
            "Unit 2: Feelings and reactions",
            "Chapter 3 - Work and jobs",
        ]

        titles = scaffolder.parse_chapter_lines(lines)

        self.assertEqual(
            ["Learning vocabulary", "Describing people", "Feelings and reactions", "Work and jobs"],
            titles,
        )

    def test_scaffold_book_writes_yaml_stub_files(self) -> None:
        chapters_file = self.workspace / "chapters.txt"
        chapters_file.write_text("1. Describing people\n2. Feelings and reactions\n", encoding="utf-8")

        args = scaffolder.parse_args.__wrapped__ if hasattr(scaffolder.parse_args, "__wrapped__") else None
        del args
        namespace = type("Args", (), {
            "book_title": "English Vocabulary in Use Upper-Intermediate",
            "book_author": "Michael McCarthy; Felicity O'Dell",
            "book_id": "english-vocabulary-in-use-upper-intermediate",
            "book_cefr": ["B2"],
            "book_tags": ["vocabulary"],
            "chapter_titles": [],
            "chapters_file": chapters_file,
            "folder_name": None,
            "source_dir": self.workspace / "source_notes",
            "format": "yaml",
            "start_order": 1,
            "chapter_file_prefix": "unit",
            "chapter_tags": ["vocabulary", "people"],
            "prompt_skill": "WRITING",
            "include_starter_prompts": True,
            "overwrite": False,
            "dry_run": False,
        })()

        written_paths = scaffolder.scaffold_book(namespace)

        self.assertEqual(2, len(written_paths))
        first_path = written_paths[0]
        self.assertTrue(first_path.exists())
        self.assertEqual("unit-01-describing-people.yaml", first_path.name)
        content = first_path.read_text(encoding="utf-8")
        self.assertIn("book:", content)
        self.assertIn("title: English Vocabulary in Use Upper-Intermediate", content)
        self.assertIn("id: describing-people", content)
        self.assertIn("targetSkill: WRITING", content)

    def test_scaffold_book_dry_run_does_not_write_files(self) -> None:
        namespace = type("Args", (), {
            "book_title": "BBC Interview Worksheets",
            "book_author": "",
            "book_id": "bbc-interview-worksheets",
            "book_cefr": ["A1"],
            "book_tags": ["worksheet", "speaking"],
            "chapter_titles": ["Interview worksheet 1"],
            "chapters_file": None,
            "folder_name": None,
            "source_dir": self.workspace / "source_notes",
            "format": "md",
            "start_order": 1,
            "chapter_file_prefix": "unit",
            "chapter_tags": ["worksheet"],
            "prompt_skill": "SPEAKING",
            "include_starter_prompts": True,
            "overwrite": False,
            "dry_run": True,
        })()

        written_paths = scaffolder.scaffold_book(namespace)

        self.assertEqual(1, len(written_paths))
        self.assertFalse(written_paths[0].exists())


if __name__ == "__main__":
    unittest.main()
