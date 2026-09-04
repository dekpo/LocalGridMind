# Local models

Drop one or more `.gguf` files in this folder. LocalGridMind scans only this
directory (not subfolders) and lists every matching file in the sidebar.

Recommended files (download **only** the Q4_K_M file, not the whole repo):

- Target (14B, ~9 GB):
  https://huggingface.co/bartowski/DeepSeek-R1-Distill-Qwen-14B-GGUF
  File: `DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf`
- Faster first test (7B, ~4.7 GB):
  https://huggingface.co/bartowski/DeepSeek-R1-Distill-Qwen-7B-GGUF
  File: `DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf`

Save the `.gguf` directly in this folder. Keep only one large model loaded at a
time. Do not commit `.gguf` files; Git ignores them on purpose.

After adding a file, refresh the Streamlit app. The dropdown updates automatically.
