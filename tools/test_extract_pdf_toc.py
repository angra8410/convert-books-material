from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parent
SCRIPT_PATH = TOOLS_DIR / "extract_pdf_toc.py"
MODULE_SPEC = importlib.util.spec_from_file_location(
    "extract_pdf_toc",
    SCRIPT_PATH,
)
extractor = importlib.util.module_from_spec(MODULE_SPEC)
assert MODULE_SPEC.loader is not None
sys.modules[MODULE_SPEC.name] = extractor
MODULE_SPEC.loader.exec_module(extractor)


class ExtractPdfTocTest(unittest.TestCase):
    def test_normalize_input_path_text_flattens_multiline_paths(self) -> None:
        raw = (
            "C:\\Books\\English Vocabulary in Use Upper-Intermediate Book with Answers and Enhanced eBook_\n"
            "  Vocabulary Reference and Practice.pdf"
        )

        normalized = extractor.normalize_input_path_text(raw)

        self.assertEqual(
            "C:\\Books\\English Vocabulary in Use Upper-Intermediate Book with Answers and Enhanced eBook_ Vocabulary Reference and Practice.pdf",
            normalized,
        )

    def test_build_progress_bar_renders_expected_fill(self) -> None:
        self.assertEqual("[############------------]", extractor.build_progress_bar(2, 4))
        self.assertEqual("[------------------------]", extractor.build_progress_bar(0, 4))

    def test_parse_toc_line_supports_numbered_and_dotted_patterns(self) -> None:
        cases = [
            ("1 Describing people 12", "1 Describing people", 12),
            ("Unit 2: Feelings and reactions 18", "Unit 2 Feelings and reactions", 18),
            ("Work and jobs ........ 23", "Work and jobs", 23),
        ]

        for raw_line, expected_title, expected_page in cases:
            with self.subTest(raw_line=raw_line):
                entry = extractor.parse_toc_line(raw_line)
                self.assertIsNotNone(entry)
                assert entry is not None
                self.assertEqual(expected_title, entry.title)
                self.assertEqual(expected_page, entry.page)
                self.assertEqual("text", entry.source)

    def test_parse_toc_line_filters_noise(self) -> None:
        self.assertIsNone(extractor.parse_toc_line("Contents"))
        self.assertIsNone(extractor.parse_toc_line("123 456"))

    def test_dedupe_entries_removes_same_title_and_page(self) -> None:
        entries = [
            extractor.TocEntry(title="Work and jobs", page=23, source="text"),
            extractor.TocEntry(title="Work and jobs", page=23, source="bookmarks"),
            extractor.TocEntry(title="Feelings and reactions", page=18, source="text"),
        ]

        deduped = extractor.dedupe_entries(entries)

        self.assertEqual(2, len(deduped))
        self.assertEqual("Work and jobs", deduped[0].title)
        self.assertEqual("Feelings and reactions", deduped[1].title)

    def test_render_titles_outputs_scaffolder_friendly_lines(self) -> None:
        entries = [
            extractor.TocEntry(title="Describing people", page=12, source="text"),
            extractor.TocEntry(title="Feelings and reactions", page=18, source="text"),
        ]

        rendered = extractor.render(entries, "titles")

        self.assertEqual("Describing people\nFeelings and reactions\n", rendered)


if __name__ == "__main__":
    unittest.main()
