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
