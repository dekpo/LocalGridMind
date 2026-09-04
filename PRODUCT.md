# Product intent

LocalGridMind is a **portable, offline Windows app** for finance and
banking data analysts. They are not developers. They must never need
Python, Pandas, a terminal, or a Git workflow.

The job is to open **complex, nested spreadsheet systems** and make
their data and logic understandable, extractable, and simpler to reuse.

## Primary users

- Data analysts in finance / banking
- No Python, no command line
- Work on confidential workbooks that must stay on the machine
- Typical files: multi-sheet `.xlsx`, `.csv`, lookups across files,
  external workbook links, nested joins, dense Excel formulas

## What the product must do (v1 priority)

1. **Load** one workbook or a **folder of related workbooks** (external
   links are common; a single file is often incomplete).
2. **Inventory** sheets, columns, types, samples, empty regions, and
   obvious quality issues.
3. **Extract logic**: list existing Excel formulas, named ranges, and
   cross-sheet / cross-file references (`[Other.xlsx]Sheet!A1`).
4. **Explain** that logic in plain English for a human analyst.
5. **Join and extract** data across sheets and linked files when keys
   can be inferred or confirmed by the user.
6. **Simplify / convert**: produce a cleaner `.xlsx` or `.csv` that a
   human can read and re-analyze (flatten, rename, split, denormalize,
   drop noise).
7. **Suggest Excel formulas** the analyst can paste back into Excel
   (lookups, conditional aggregates, and similar). The app proposes;
   the analyst keeps control of the workbook.

## What is deferred

- Dashboards and charts are **not** a v1 goal. Plotly may exist later
  as an optional extra, never as the reason the app exists.
- VBA macros, Power Query (M), Pivot caches, and DAX are **out of v1**
  unless a later phase explicitly adds parsers. They must be detected
  and reported as "present but not interpreted" rather than silently
  ignored.

## What the user sees vs what the engine does

| User sees | Engine does (hidden) |
| --- | --- |
| File / folder picker, English UI | openpyxl / Pandas load |
| Questions in business language | Schema + formula inventory sent to the local LLM |
| Explanations, extracted tables, suggested Excel formulas | LLM emits Python (and/or Excel formula text) |
| Download a cleaner workbook | Restricted local execution, then export |

Users never see generated Python. The local LLM is a **hidden code and
formula generator**, not a mental calculator and not a chat toy.

## Distribution (non-developer machines)

Target machines may have **no Python installed**.

- Ship a **portable folder**, not a 9 GB single exe:
  `LocalGridMind.exe` (double-click) + `models/` beside it.
- Double-click starts the app and opens the UI. No CMD for end users.
- The GGUF file is installed next to the app (USB copy, internal share,
  or first-run copy). Analysts do not run `pip`.
- Dev machines still use a venv. That is a developer concern only.

## Hardware envelope

Intel Core i7-150U class, 24 GB RAM, CPU only, `n_threads=4`.
Expect slow generation on a 14B Q4 model. The UI must show progress
and never freeze Windows.

## Feasibility and constraints (keep this cap)

This product is **feasible** if Excel is treated as a file system of
tables and stored formulas, not as a magic black box.

### What v1 can do well

- Inventory sheets, columns, types, samples, and empty regions.
- Read **stored** Excel formulas and named ranges (openpyxl).
- Map external links such as `[Other.xlsx]Sheet!A1`.
- Join and extract when keys can be inferred or confirmed.
- Write a cleaner `.xlsx` / `.csv` a human can reread.
- Suggest paste-ready formulas (`XLOOKUP`, `SUMIFS`, and similar).
- Keep Python hidden. The analyst sees English, tables, and downloads.
- Stay offline. That is a compliance feature, not a slogan.

### What will not work as magic

- VBA, Power Query (M), Pivot caches, and DAX: **detect only** in v1.
- A single file is often incomplete. Analysts must load the **folder**
  of linked workbooks.
- The app reads formulas; it does not replace Excel as the calculator.
- A 14B Q4 model on this CPU will be **slow**. Show progress. Never
  freeze the desktop (`n_threads=4`).
- “Innovative” formulas: strong on standard Excel, weaker on LAMBDA /
  dynamic arrays / bank-specific conventions. The analyst decides.

### Engine rule

The local LLM is a **hidden generator** of Pandas scripts and Excel
formula text. It must not invent numeric answers in tokens. Users never
see the Python. End users never use a terminal. Distribution is a
portable folder (`LocalGridMind.exe` + sibling `models/`), not a 9 GB
single exe and not a `pip` install on analyst PCs.
