from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parent
SCRIPT_PATH = TOOLS_DIR / "extract_pdf_text.py"
MODULE_SPEC = importlib.util.spec_from_file_location(
    "extract_pdf_text",
    SCRIPT_PATH,
)
extractor = importlib.util.module_from_spec(MODULE_SPEC)
assert MODULE_SPEC.loader is not None
sys.modules[MODULE_SPEC.name] = extractor
MODULE_SPEC.loader.exec_module(extractor)


class ExtractPdfTextTest(unittest.TestCase):
    def test_normalize_input_path_text_flattens_multiline_paths(self) -> None:
        raw = "C:\\Books\\Book One\n  Student Book.pdf"

        normalized = extractor.normalize_input_path_text(raw)

        self.assertEqual("C:\\Books\\Book One Student Book.pdf", normalized)

    def test_normalize_extracted_text_collapses_excess_spacing(self) -> None:
        raw = "Line one   \nLine two\r\n\r\n\r\nLine   three"

        normalized = extractor.normalize_extracted_text(raw)

        self.assertEqual("Line one\nLine two\n\nLine three\n", normalized)


if __name__ == "__main__":
    unittest.main()
