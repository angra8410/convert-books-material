from __future__ import annotations

import importlib.util
import shutil
import sys
import textwrap
import unittest
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parent
SCRIPT_PATH = TOOLS_DIR / "import_notes.py"
MODULE_SPEC = importlib.util.spec_from_file_location(
    "import_notes",
    SCRIPT_PATH,
)
importer = importlib.util.module_from_spec(MODULE_SPEC)
assert MODULE_SPEC.loader is not None
sys.modules[MODULE_SPEC.name] = importer
MODULE_SPEC.loader.exec_module(importer)


class ImportNotesTest(unittest.TestCase):
    def test_build_repository_can_filter_by_book_and_chapter_order(self) -> None:
        temp_root = TOOLS_DIR.parent / "temp_test_import_notes_case"
        shutil.rmtree(temp_root, ignore_errors=True)
        source_dir = temp_root / "source_notes"
        book_a = source_dir / "book-a"
        book_b = source_dir / "book-b"
        book_a.mkdir(parents=True, exist_ok=True)
        book_b.mkdir(parents=True, exist_ok=True)

        (book_a / "unit-1.yaml").write_text(
            textwrap.dedent(
                """
                book:
                  id: book-a
                  title: Book A
                chapter:
                  id: chapter-a1
                  title: Chapter A1
                  order: 1
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        (book_a / "unit-2.yaml").write_text(
            textwrap.dedent(
                """
                book:
                  id: book-a
                  title: Book A
                chapter:
                  id: chapter-a2
                  title: Chapter A2
                  order: 2
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        (book_b / "unit-1.yaml").write_text(
            textwrap.dedent(
                """
                book:
                  id: book-b
                  title: Book B
                chapter:
                  id: chapter-b1
                  title: Chapter B1
                  order: 1
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )

        repository = importer.build_repository(
            source_dir,
            book_ids={"book-a"},
            chapter_order_min=2,
            chapter_order_max=2,
        )

        self.assertEqual(1, len(repository["books"]))
        self.assertEqual("book-a", repository["books"][0]["id"])
        self.assertEqual(1, len(repository["books"][0]["chapters"]))
        self.assertEqual("chapter-a2", repository["books"][0]["chapters"][0]["id"])

        shutil.rmtree(temp_root, ignore_errors=True)

    def test_format_preview_lists_books_and_chapters(self) -> None:
        preview = importer.format_preview(
            {
                "books": [
                    {
                        "id": "book-a",
                        "title": "Book A",
                        "chapters": [
                            {"id": "chapter-a1", "title": "Chapter A1", "order": 1},
                            {"id": "chapter-a2", "title": "Chapter A2", "order": 2},
                        ],
                    }
                ]
            }
        )

        self.assertIn("Preview: 1 book(s), 2 chapter(s)", preview)
        self.assertIn("- Book A (book-a): 2 chapter(s)", preview)
        self.assertIn("1  chapter-a1  Chapter A1", preview)

    def test_export_books_writes_one_json_per_book(self) -> None:
        temp_root = TOOLS_DIR.parent / "temp_test_import_notes_exports"
        shutil.rmtree(temp_root, ignore_errors=True)
        export_dir = temp_root / "exports"

        repository = {
            "version": 2,
            "generatedAt": "2026-04-03T00:00:00+00:00",
            "books": [
                {
                    "id": "book-a",
                    "title": "Book A",
                    "chapters": [{"id": "chapter-a1", "title": "Chapter A1", "order": 1}],
                },
                {
                    "id": "book-b",
                    "title": "Book B",
                    "chapters": [{"id": "chapter-b1", "title": "Chapter B1", "order": 1}],
                },
            ],
        }

        written = importer.export_books(repository, export_dir)

        self.assertEqual(2, len(written))
        self.assertTrue((export_dir / "book-a.json").exists())
        self.assertTrue((export_dir / "book-b.json").exists())

        payload = (export_dir / "book-a.json").read_text(encoding="utf-8")
        self.assertIn('"version": 2', payload)
        self.assertIn('"id": "book-a"', payload)
        self.assertIn('"title": "Book A"', payload)

        shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

