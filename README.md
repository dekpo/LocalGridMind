# LocalGridMind

Private desktop app for finance analysts. It opens complex Excel / CSV
systems, extracts data and spreadsheet logic, explains it, and can emit
a simpler workbook. A local model drives the work. Users never touch
Python or a terminal.

This repository has completed **phase 3 (conversation library)** and is
adding **phase 4 (generate wait UX)**. Read `PRODUCT.md` for intent,
feasibility, and limits. See `CHANGELOG.md` for what landed and
`ROADMAP.md` for the phase plan.

The next public step after this wait-UX work is workbook intelligence
(folder pack, schema, stored formulas, external links). The local model
remains a hidden generator of analysis code and Excel formula text. It
must not invent numeric answers.

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
