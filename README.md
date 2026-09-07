# LocalGridMind

Private desktop app for finance analysts. It opens complex Excel / CSV
systems, extracts data and spreadsheet logic, explains it, and can emit
a simpler workbook. A local model drives the work. Users never touch
Python or a terminal.

This repository has completed **phase 6.4 (deterministic formula references)**.
Read `PRODUCT.md` for intent, feasibility, and limits. See
`CHANGELOG.md` for what landed and `ROADMAP.md` for the phase plan.

Attach a file or a folder of linked workbooks to the current chat.
The app keeps a local copy and a compact inventory (schema, stored
formulas, external links). Later questions reuse that cache. A Workbook
library (reuse a pack across chats) comes later.

## Asking questions

There are **two kinds of replies**. The app chooses. You do not flip a
switch. English questions only (the chat is English).

| What you see | What happened |
| --- | --- |
| Answer appears at once. No spinner. No “Generated in …” | The app quoted the **workbook inventory** it built when you attached the files. The local model is not used, even if it is Ready. |
| Spinner, wait copy, then “Generated in 2 min …” | The **local model** wrote the reply. You must click **Load model** and wait for Ready first. |

**Load model is not required** for inventory questions. It **is**
required for explanations and suggested formulas.

### When the inventory answers (no model)

A workbook must already be attached to **this** chat. The app then
looks for a **fact** question. These English patterns are the
triggers. They are not case-sensitive.

1. **Named ranges** — the question contains `named range` or
   `named ranges`.
2. **Links to other workbooks** — the question contains
   `external link`, `external links`, `external workbook link`,
   or `workbook links`.
3. **Where is this computed?** — the question contains `Where is` or
   `Where are`. Treat **WACC** and **cost of capital** as the same
   hunt. The app quotes matching stored formulas (cell + formula +
   label) from the full local formula index when that index is present.
   It matches the row label or column header, not the sheet name, and
   shows at most a short ranked list.
4. **Which file does this workbook read?** — the question matches
   `Which file does … read` or `What file does … read`.
5. **What does this cell do?** — the question names a `Sheet!A1` or
   `'Sheet name'!A1` address. The app quotes that stored formula
   (cell + formula + label) from the full local formula index. If the
   cell is not there, it says so. It does not open Excel again.

If the question matches one of those five, the model is **not**
called. That is intentional: the inventory is the source of truth
for names, links, and stored cells.

`How is …`, `Explain …`, and `Suggest …` are **not** magic words.
They usually go to the model because they do **not** match the list
above — unless the question also names a `Sheet!A1` cell, in which
case the inventory answers. The opposite also holds: `Where is
terminal value computed?` is an inventory question; `How is terminal
value calculated?` is a model question.

### When the model answers (spinner)

If the question is **not** one of the five fact patterns, and a model
is Ready, the app sends a short inventory extract plus your question
to the local model. That path is for:

- explaining a listed formula in plain English
- suggesting Excel formula text you can paste
- any other question that is not a fact lookup

The model must not invent numbers in tokens, and it should not invent
cell addresses that are not in the inventory. When it refers to an
existing formula it should cite `[[FORMULA:Sheet!A1]]` (or
`[[FORMULA:File.xlsx!A1]]` when that A1 is unique in that file). The
app fills in the stored formula. If the cite cannot be verified, the
reply says so; the app does not guess a nearby cell. New Excel text
must be labelled **SUGGESTED FORMULA**. If the model still **mis-copies
a listed formula**, the app appends a short correction that quotes the
stored formula. The model draft stays visible. Always check the
inventory turn at the top of the chat before pasting anything into
Excel. A local 7B often ignores the cite protocol; a 9B may follow it
more often. Neither is the source of truth for workbook facts.

If no model is loaded, those questions get a short notice to load
one. They do not wait on a spinner.

### Tiny example (two linked files)

Imagine this pack:

**Books.xlsx** (sheet `Books`)

| Book | Name |
| --- | --- |
| A | Alpha |
| B | Bravo |

**Rates.xlsx** (sheet `Rates`)

| Date | Book | Rate | (column E) |
| --- | --- | --- | --- |
| 2026-01-01 | A | 1.5 | `=[Books.xlsx]Books!B2` |

Named range: `RateTable` → `Rates!$A$1:$C$3`.

| You type | Path | Typical reply |
| --- | --- | --- |
| `Which file does Rates read, and is it in this pack?` | Inventory, instant | Rates.xlsx reads **Books.xlsx** from `Rates!E2`. That file is in this pack. |
| `List the named ranges from the inventory.` | Inventory, instant | `RateTable` → `Rates!$A$1:$C$3` |
| `Are there external workbook links in the inventory?` | Inventory, instant | `Rates!E2` reads **Books.xlsx** (in this pack) |
| `Where is the rate name pulled from?` | Inventory if it matches `Where is …` | Quoted stored formula if the label/cell matches; otherwise not in the listed set |
| `What does Rates!E2 do?` | Inventory, instant | `Rates!E2`: `=[Books.xlsx]Books!B2` |
| `Explain the Rates!E2 formula in plain English.` | Inventory, instant | Same quote: the question names `Rates!E2`. |
| `Suggest a paste-ready formula that looks up a name the same way Rates already does.` | Model, spinner | Prefer a formula that quotes `=[Books.xlsx]Books!B2`. If the model assigns a different formula to a listed cell, a correction appears under the draft. |

### Tiny example (cost of capital on one sheet)

| Cell | Formula or label |
| --- | --- |
| `Input sheet!B35` | `='Cost of capital'!B13` — Initial cost of capital |
| `Cost of capital!B13` | `=B10*B11+B12` — Cost of capital |
| `Valuation output!B18` | `=B16/(B17-M2)` — Terminal value |

| You type | Path |
| --- | --- |
| `Where is WACC or the cost of capital computed?` | Inventory. Quotes B35 and B13 (and any other listed row whose label says cost of capital). |
| `List the named ranges from the inventory.` | Inventory. `none` if there are none. |
| `What does Input sheet!B35 do?` | Inventory. Quotes `='Cost of capital'!B13`. |
| `How is terminal value calculated? Quote only a formula that is in the inventory.` | Model. Should cite `Valuation output!B18`. The app resolves the stored formula. If it assigns a wrong formula to a listed cell, a correction quotes the stored one. |
| `Suggest a paste-ready FCFF-from-EBIT formula only if the inventory shows that logic.` | Model. If the listed formulas do not show that logic, the honest answer is that it is not in the inventory. Do not paste a formula the model invented. |

### Practical rule

- **Where / named ranges / external links / which file does X read / what does Sheet!A1 do** → trust the instant answer; it came from the file scan.
- **How / explain / suggest** (no `Sheet!A1` in the question) → the model is drafting; existing formulas should appear only after the app resolves a `[[FORMULA:…]]` cite. Reconcile with the inventory list before you change Excel.

## Requirements (developers only)

- Windows 10/11
- Python 3.10 or newer
- 24 GB RAM for a 14B Q4_K_M model
- CPU only (`n_threads` locked to 4)

End-user machines will **not** need Python. That is a later packaging step.

## Repository layout

```text
LocalGridMind/
├── PRODUCT.md
├── requirements.txt
├── requirements-dev.txt
├── src/
│   ├── app.py
│   ├── config.py
│   ├── core/
│   ├── llm/
│   ├── interpreter/
│   └── ui/
├── models/          # place .gguf files here; binaries are not committed
├── data/uploads/
├── data/chats/      # local SQLite library (gitignored)
├── outputs/
└── tests/
```

## Developer setup

Use **classic CMD** for Python. Use **Git Bash** for Git.
Do not use PowerShell.

### Git Bash — first-time repo (already done on this machine)

```bash
cd /c/Users/elise/Documents/CURSOR/LocalGridMind
git status
```

### CMD — virtualenv and dependencies

Type each line, then Enter. This machine uses `python` (3.13). There is no `py` launcher.

```bat
cd /d C:\Users\elise\Documents\CURSOR\LocalGridMind
python -m venv .venv
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
pip install -r requirements-dev.txt
pytest
streamlit run src/app.py
```

The prompt should show `(.venv)` after `activate.bat`.
Place a `.gguf` file in `models/`. In the sidebar, choose it and click
**Load model**. Wait until the status is Ready (first load can take
several minutes on a 24 GB CPU laptop). Then send a short test message.

To stop Streamlit on Windows if Ctrl+C fails, use another CMD window:

```bat
taskkill /F /IM streamlit.exe
```

If load fails with Windows error 4551, Windows Security blocked
`llama.dll`. Allow that file (or turn off Smart App Control), then
restart the app.

If the `llama-cpp-python` CPU wheel fails on Python 3.13, install
Python 3.11 from python.org, then recreate the venv with that
interpreter instead of `python`.

## Git workflow (human only, Git Bash)

| Branch | Purpose |
| --- | --- |
| `main` | Release snapshots |
| `develop` | Integration |
| `feature/<short-name>` | New work |
| `fix/<short-name>` | Bug fixes |
