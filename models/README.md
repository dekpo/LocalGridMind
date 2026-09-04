# Local models

Drop one or more `.gguf` files in this folder. LocalGridMind scans only this
directory (not subfolders) and lists every matching file in the sidebar.

Recommended first target for this machine (Intel i7-150U, 24 GB RAM, CPU only):

- A 14B Q4_K_M GGUF, about 8–9 GB, for example DeepSeek-R1-Distill-Qwen-14B
- Keep only one large model loaded at a time
- Do not commit `.gguf` files; Git ignores them on purpose

After adding a file, refresh the Streamlit app. The dropdown updates automatically.
