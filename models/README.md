# Local models

Drop one or more `.gguf` files in this folder. LocalGridMind scans only this
directory (not subfolders) and lists every matching file in the sidebar.

**Closed beta (use this file):**

- https://huggingface.co/unsloth/Qwen3.5-9B-GGUF
- File: `Qwen3.5-9B-Q5_K_M.gguf` (about 6–7 GB)
- Direct: https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/resolve/main/Qwen3.5-9B-Q5_K_M.gguf

Save it as `models/Qwen3.5-9B-Q5_K_M.gguf`. Do not put it in a subfolder.

Other optional files (download **only** the GGUF, not the whole repo):

- Target (14B, ~9 GB):
  https://huggingface.co/bartowski/DeepSeek-R1-Distill-Qwen-14B-GGUF
  File: `DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf`
- Faster first test (7B, ~4.7 GB):
  https://huggingface.co/bartowski/DeepSeek-R1-Distill-Qwen-7B-GGUF
  File: `DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf`

Keep only one large model loaded at a time. Do not commit `.gguf`
files, incomplete browser downloads (`.crdownload`), or other binaries;
Git ignores everything in this folder except this README.

After adding a file, refresh the Streamlit app. The dropdown updates automatically.
