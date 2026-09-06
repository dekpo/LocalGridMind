# Changelog

Public history only. Local helper files (`AGENTS.md`, `PROJECT_STATUS.md`,
`LESSONS.md`, `*_HANDOFF.md`) are not part of this log.

## Unreleased

### Phase 6.2 — Inventory lookup (2026-09-06)

Named ranges, external workbook links, and “where is WACC / cost of capital
computed” are answered from the cached pack JSON. Those turns persist
without loading a model. Other questions still use the Phase 6.1 prompt.
Tests use synthetic workbooks only.

### Phase 6.1 — Honest inventory prompt (2026-09-06)

The compact prompt sent to the local model now lists named ranges, external
links (or an explicit `none`), and stored formulas **before** sheet columns.
Empty columns are omitted. Formulas that mention WACC, cost of capital,
lookups, or other workbooks are kept first when the list is capped. The
preamble forbids invented cell addresses. A finished reply is persisted
even if Streamlit dropped the waiting flag after a reconnect. Tests use
synthetic workbooks only. Human checks confirmed the extract on a large
valuation workbook and a two-file linked folder. The local 7B can still
rephrase those facts incorrectly; the next step is deterministic
inventory lookup, not a model swap.

### Phase 6 — Workbook intelligence (2026-09-06)

Attach a workbook or a folder of linked workbooks to the **current**
Recents chat. Files are copied under `data/uploads/` and inventoried
once (sheets, columns, types, samples, stored formulas, named ranges,
external links). VBA / Power Query / Pivot / DAX are flagged as
present, not interpreted. Later questions in that thread reuse the
cached inventory; the local model never receives `.xlsx` bytes. Attach
with the official chat paperclip or a separate folder picker. Tests use
tiny synthetic workbooks only.

### Phase 5 — Reasoning time (2026-09-06)

The Local model expander lists **Selected model** (was Active GGUF
model) and a **Reasoning time** select (`~2 min` … `~10 min`). Those
labels map to a hidden token budget (512 … 2560; default `~6 min` /
1536). Analysts never see the word “token”. The choice lives in
session state and is disabled while the model is loading, generating,
or titling. Tests cover the map and default; no `.gguf` fixtures.

### Phase 4 — Generate wait UX (2026-09-06)

Chat replies use a 1536-token budget so a reasoning model can still
write a visible answer after hidden `<think>` text. A Stop button sits
on the generating line and aborts the completion. Wait copy changes
with elapsed time (a single light line after five minutes). If the
model still produces only hidden reasoning, the notice says so and
**Generate again** retries with a short “answer now” steer. Tests mock
`Llama` and do not ship `.gguf` fixtures.

### Phase 3 — Conversation library (2026-09-05)

Sidebar Recents persist every thread in a local SQLite file
(`data/chats/library.sqlite`, stdlib `sqlite3`). New chat creates an
empty conversation. Clicking a recent reopens its messages after a
restart. After the first exchange, the title is a short heuristic from
the first user line; if a model is Ready, a hidden completion may
refine it. Reasoning tags are stripped. Tests use `tmp_path`.

Assistant replies keep the generation duration under the answer
(same clock as the live “Generating a reply…” line). Recents can
delete the selected conversation (official `st.popover`, no extra
component). Streamlit theme primary is a dark gray so selection and
input focus no longer use error-red.

### Phase 2 — Conversational shell (2026-09-05)

ChatGPT / Gemini-like thread: user bubbles on the right with a timestamp,
assistant text on the left, no avatars, `st.chat_input` pinned at the
bottom. New chat clears the in-memory thread. Model load stays in a
sidebar expander.

Load / generate status polls with a full script rerun (`sleep` +
`st.rerun()`). Streamlit `st.fragment` status panels left ghost Ready +
Loading boxes and could freeze the percent until a browser refresh.
The GGUF worker itself was already correct.

### Phase 1 — Local GGUF runtime (2026-09-05)

Analysts can pick a `.gguf` file from `models/`, load one model at a
time on CPU (`n_threads=4`, no GPU), and run a short readiness check.

- Lazy load / unload via `src/llm/runtime.py` (`llama-cpp-python`)
- Sidebar status: unloaded, loading (percent + elapsed), ready, error
- Reasoning tags such as `<think>…</think>` are stripped before display
- Tests mock `Llama` and do not ship `.gguf` fixtures
- Windows note: Smart App Control can block `llama.dll` (WinError 4551).
  Allow the file in Windows Security, then restart the app.
- Console `WinError 10054` traces on Windows are the browser closing a
  WebSocket (asyncio Proactor). They do not mean the model failed.

### Phase 0 — Bootstrap

Project skeleton, GGUF discovery, Streamlit shell.
