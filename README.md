# Convert Books Material

This repo is a staging workspace for turning book notes into a catalog JSON.

## Existing flow

`tools/import_notes.py` reads curated chapter files under `source_notes/` and writes:

- `app/src/main/assets/content_repository.json`

Supported note formats:

- `yaml`
- `json`
- `md` with optional front matter

Run it like this:

```powershell
python tools/import_notes.py
```

### Preview a filtered import

You can preview a subset before writing the JSON file. For example, to preview the first
10 units of the B2 vocabulary book:

```powershell
python tools/import_notes.py `
  --preview `
  --book-id english-vocabulary-in-use-upper-intermediate `
  --chapter-order-min 1 `
  --chapter-order-max 10
```

If you want to generate a filtered preview file instead of the full catalog:

```powershell
python tools/import_notes.py `
  source_notes `
  temp\b2_batch_1_preview.json `
  --book-id english-vocabulary-in-use-upper-intermediate `
  --chapter-order-min 1 `
  --chapter-order-max 10
```

## New full-book scaffolding flow

`tools/scaffold_book_notes.py` creates one chapter stub file per unit so a whole book can be staged quickly before import.

### Example: inline chapter titles

```powershell
python tools/scaffold_book_notes.py `
  --book-title "English Vocabulary in Use Upper-Intermediate" `
  --book-author "Michael McCarthy; Felicity O'Dell" `
  --book-id english-vocabulary-in-use-upper-intermediate `
  --book-cefr B2 `
  --book-tags vocabulary `
  --chapter-titles "Describing people" "Feelings and reactions" "Work and jobs" `
  --include-starter-prompts
```

### Example: chapter titles from a text file

Create a text file with one chapter title per line, for example:

```text
1. Describing people
2. Feelings and reactions
3. Work and jobs
```

Then run:

```powershell
python tools/scaffold_book_notes.py `
  --book-title "English Vocabulary in Use Upper-Intermediate" `
  --book-author "Michael McCarthy; Felicity O'Dell" `
  --book-id english-vocabulary-in-use-upper-intermediate `
  --book-cefr B2 `
  --book-tags vocabulary `
  --chapters-file .\chapters.txt `
  --include-starter-prompts
```

That writes stub files under:

- `source_notes/english-vocabulary-in-use-upper-intermediate/`

After that:

1. Fill in `summary`, `points`, `examples`, `pitfalls`, and the prompt text.
2. Run `python tools/import_notes.py`
3. Inspect `app/src/main/assets/content_repository.json`

## Ollama chapter drafting

`tools/draft_chapter_with_ollama.py` drafts missing chapter fields from raw unit text using local Ollama.

Example:

```powershell
python tools/draft_chapter_with_ollama.py `
  --chapter-file source_notes\english-vocabulary-in-use-upper-intermediate\unit-01-learning-vocabulary.yaml `
  --source-text-file .\raw_unit_01.txt `
  --model gemma3:27b `
  --timeout-seconds 300 `
  --apply
```

By default it fills only missing `summary`, `points`, `examples`, and `pitfalls`, and it replaces the scaffold's placeholder starter prompt when a better Ollama prompt is returned.

Use these flags when needed:

- `--replace-practice-prompts`
- `--replace-nonempty`

## PDF TOC extraction

`tools/extract_pdf_toc.py` extracts a chapter list from a PDF using embedded bookmarks when they exist, and text heuristics when they do not.

It requires `pypdf`:

```powershell
pip install pypdf
```

Example:

```powershell
python tools/extract_pdf_toc.py `
  "C:\path\to\English Vocabulary in Use Upper-Intermediate.pdf" `
  --format titles `
  --output chapters.txt
```

The extractor now prints progress to the terminal while it works, for example when it opens the PDF, checks bookmarks, and scans TOC pages. If you want silent mode, add:

```powershell
--quiet
```

Then feed that chapter list into the scaffolder:

```powershell
python tools/scaffold_book_notes.py `
  --book-title "English Vocabulary in Use Upper-Intermediate" `
  --book-author "Michael McCarthy; Felicity O'Dell" `
  --book-id english-vocabulary-in-use-upper-intermediate `
  --book-cefr B2 `
  --book-tags vocabulary `
  --chapters-file .\chapters.txt `
  --include-starter-prompts
```

## PDF page-range text extraction

`tools/extract_pdf_text.py` extracts raw text from a PDF page range into a `.txt` file for Ollama drafting.

Example:

```powershell
python tools/extract_pdf_text.py `
  "C:\path\to\English Vocabulary in Use Upper-Intermediate.pdf" `
  --start-page 8 `
  --end-page 9 `
  --output raw_unit_01.txt
```

Then use that file with the Ollama drafter:

```powershell
python tools/draft_chapter_with_ollama.py `
  --chapter-file source_notes\english-vocabulary-in-use-upper-intermediate\unit-01-learning-vocabulary.yaml `
  --source-text-file .\raw_unit_01.txt `
  --model gemma3:12b `
  --timeout-seconds 180 `
  --apply
```
## Batch 7 import preview

Use this command to preview B2 units 61 to 70 before writing or merging a larger catalog update:

```powershell
python tools/import_notes.py `
  --preview `
  --preview-detailed `
  --book-id english-vocabulary-in-use-upper-intermediate `
  --chapter-order-min 61 `
  --chapter-order-max 70
```
## Batch 8 import preview

Use this command to preview B2 units 71 to 80 before writing or merging a larger catalog update:

```powershell
python tools/import_notes.py `
  --preview `
  --preview-detailed `
  --book-id english-vocabulary-in-use-upper-intermediate `
  --chapter-order-min 71 `
  --chapter-order-max 80
```
## Batch 9 import preview

Use this command to preview B2 units 81 to 90 before writing or merging a larger catalog update:

```powershell
python tools/import_notes.py `
  --preview `
  --preview-detailed `
  --book-id english-vocabulary-in-use-upper-intermediate `
  --chapter-order-min 81 `
  --chapter-order-max 90
```

