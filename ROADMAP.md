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
| 6 Workbook intelligence | Implemented | Attach a file or folder pack to the **current** Recents chat. Local copy + one-shot inventory (schema, stored formulas, external links). Later questions in that thread reuse the cache. Native chat paperclip + a separate folder picker. No interpreter. |
| 6.1 Honest inventory prompt | Implemented | Compact prompt lists named ranges, links (or none), and stored formulas **before** sheet noise. Persist a finished reply if the page reconnects. Human tests: extraction holds; a 7B still paraphrases facts. |
| 6.2 Inventory lookup | Implemented | The app answers named-range, external-link, and “where is this computed” questions from the structured inventory. Human-verified with the model unloaded and Ready. Fact lookup holds; the 7B can still mis-copy listed formulas on explain / suggest. |
| 6.3 Ground model replies | Implemented | A named `Sheet!A1` is quoted from the inventory with no generate. After a generate, a listed cell that was given the wrong formula gets a short correction. Any workbook; no file-specific hard-coding. |
| 6.4 Deterministic formula references | Implemented | Compact prompt + full local formula index. `[[FORMULA:Sheet!A1]]` and unique `[[FORMULA:File.xlsx!A1]]` resolve from the index (exact match, fail closed). Where-is lists are ranked and capped. Suggested formulas must be labelled. The model is not the source of workbook facts. |
| 6b Workbook library | Later | Sidebar Library under New chat. Reuse packs across conversations. Include / exclude for the active chat only. Not a global always-on corpus. |
| 7 Hidden interpreter | Planned | Restricted execution of generated Pandas; users never see Python |
| 8 Export | Planned | Cleaner `.xlsx` / `.csv` download |
| 9 Portable package | Later | Final product: `LocalGridMind.exe` + sibling `models/`. Closed beta: zip `release/ChatWithExcelFile/` from `tools/beta/assemble.bat`. |

Phase 6 keeps workbooks on the **current** conversation: upload once,
inventory once, ask many times. A later Library step (6b) can reuse
the same pack in other chats. The model still sees a compact inventory,
never the raw workbook.

Hardware envelope: Intel Core i7-150U class, 24 GB RAM, CPU only,
`n_threads=4`. First load and first reply are slow on that class of
machine. The UI must show progress and never look frozen.
