# Roadmap

Public plan. Local agent files (`AGENTS.md`, `PROJECT_STATUS.md`,
`LESSONS.md`, `*_HANDOFF.md`) are not on GitHub.

The analyst-facing shell is a familiar chat layout (ChatGPT / Gemini).
The engine stays a hidden generator of analysis code and Excel formula
text. It must not invent numeric answers.

| Phase | Status | What lands |
| --- | --- | --- |
| 0 Bootstrap | Done | Repo, venv, GGUF discovery, Streamlit shell |
| 1 Local GGUF runtime | Done | Load / unload one CPU model, readiness check |
| 2 Conversational shell | Implemented | Fixed input, scrollable history, user right / assistant left, no avatars, timestamps, New chat |
| 3 Conversation library | Implemented | Recents list, SQLite persist, switch threads, auto-titles |
| 4 Generate wait UX | Implemented | 1536-token budget, Stop, honest wait copy, Generate again |
| 5 Reasoning time | Implemented | Sidebar duration (`~2 min`…`~10 min`) maps to the token budget |
| 6 Workbook intelligence | Planned | Folder pack, schema, stored formulas, external-link graph |
| 7 Hidden interpreter | Planned | Restricted execution of generated Pandas; users never see Python |
| 8 Export | Planned | Cleaner `.xlsx` / `.csv` download |
| 9 Portable package | Planned | `LocalGridMind.exe` + sibling `models/` (not a 9 GB single exe) |

Hardware envelope: Intel Core i7-150U class, 24 GB RAM, CPU only,
`n_threads=4`. First load and first reply are slow on that class of
machine. The UI must show progress and never look frozen.
