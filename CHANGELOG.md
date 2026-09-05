# Changelog

Public history only. Local helper files (`AGENTS.md`, `PROJECT_STATUS.md`,
`LESSONS.md`, `*_HANDOFF.md`) are not part of this log.

## Unreleased

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
