# OMR Studio

Desktop front end for OMRChecker. No command line needed.

## Run

```bash
pip install -r GUI/requirements.txt     # once
python GUI/main.py
```

## Workflow

1. **Templates** - *Add Template* (folder or `template.json`). Optionally attach an answer key (`evaluation.json`) so sheets are graded. Try *Add bundled sample templates* first.
2. **Process Sheets** - drag & drop sheets/folders (PNG, JPG, PDF), pick a template, press *Process sheets*.
3. **Results** - browse scores and detected answers, click a row to see the marked sheet, then *Export to Excel* (or CSV).

## CLI to GUI mapping

| CLI                | GUI                                              |
|--------------------|--------------------------------------------------|
| `-i inputs/`       | Add files / Add folder / drag & drop             |
| `template.json`    | Templates page                                   |
| `evaluation.json`  | Templates -> Attach answer key                   |
| `-o outputs/`      | Automatic: one folder per run (see *History*)    |
| `-l` (setLayout)   | Preview template layout (shown inside the app)   |
| `-a` (autoAlign)   | Option: Auto-align slightly shifted scans        |
| `Results_*.csv`    | Results table + Export to Excel/CSV              |
| `Manual/*.csv`     | Status column (Multi-marked / Error) + "Needs Review" Excel sheet |

## Data location

`~/OMRStudio` (override with the `OMR_STUDIO_HOME` environment variable):
`templates/`, `sessions/` (each run's input copy, output and history), `exports/`, `logs/`.

## Architecture

```
GUI/
  main.py                    launcher (logging, global error dialog)
  omr_studio/
    services/                UI-free, unit-tested logic
      templates.py           import/validate/remove templates (flat, atomic, engine-validated)
      sessions.py            one folder per run + metadata/history
      engine.py              adapter over the OMRChecker engine (progress, cancel, per-sheet error isolation)
      results.py             reads engine output into typed results
      exporter.py            Excel/CSV export (formula-injection safe)
    ui/                      PySide6 interface (pages, widgets, theme, background workers)
  tests/                     pytest suite:  python -m pytest GUI/tests -c GUI/pytest.ini --rootdir=GUI
```

The engine in `src/` is not modified. A single bad scan is recorded as an error instead of stopping the batch.
