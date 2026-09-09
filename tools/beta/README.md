# ChatWithExcelFile — closed beta

This folder is a **prototype** for testers. It is not the Git repo
and not the final LocalGridMind install. Testers install Python once.
A later phase will ship a double-click app with no Python.

You need Windows 10/11, about **24 GB RAM**, and a CPU (no GPU).

Keep this whole folder together (`src`, `models`, `setup.bat`,
`start.bat`). Do not mix it with the developer LocalGridMind tree.

## Once — allow this folder in Windows (required)

Windows Device Guard / Smart App Control blocks NumPy and the local
model if this is skipped. Do it **before** `setup.bat`.

1. Start menu → **Windows Security** → **App and browser control**.
   If **Smart App Control** is On, set it to **Off** on a test PC.
2. **Virus & threat protection** → **Manage settings** → **Exclusions**
   → **Add an exclusion** → **Folder**.
   Choose this `ChatWithExcelFile` folder.

## Once — install Python

1. Download **Python 3.11** from
   [python.org/downloads/windows](https://www.python.org/downloads/windows/).
2. Run the installer. Tick **Add python.exe to PATH**.
3. Finish. You do not need Git.

Python 3.10+ can work. If `setup.bat` fails on 3.13, use 3.11.

## Once — install this prototype

1. Unzip **ChatWithExcelFile** if you received a ZIP.
2. Double-click **`setup.bat`**. Wait until it says setup finished.
   The first run downloads packages and can take several minutes.
   A key press after an error only closes the window; run `setup.bat`
   again after the scripts are updated.

## Every session — three steps

### 1. Download Qwen and put it in `models`

Download **only this file** (about 6–7 GB), not a whole Git repo:

- Page: https://huggingface.co/unsloth/Qwen3.5-9B-GGUF
- File: **`Qwen3.5-9B-Q5_K_M.gguf`**
- Direct: https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/resolve/main/Qwen3.5-9B-Q5_K_M.gguf

Save it here (same folder as `models\README.md`, not a subfolder):

`ChatWithExcelFile\models\Qwen3.5-9B-Q5_K_M.gguf`

You only do this once unless you replace the model.

### 2. Launch the prototype

Double-click **`start.bat`**. Leave that window open.

### 3. Work in the Streamlit page

The browser should open on its own (usually
[http://localhost:8501](http://localhost:8501)).

1. In **Local model**, choose **Qwen3.5-9B-Q5_K_M**.
2. Click **Load model**. Wait until the status is **Ready** (several
   minutes the first time).
3. Attach a workbook (paperclip) or a folder of linked workbooks.
4. Ask in English in the thread.

To stop: close the `start.bat` window, or press Ctrl+C there.

After Load model is Ready, run the script in **TEST_CASES.md**
(Damodaran WACC + FCFF files from the same family as
https://exinfm.com/free_spreadsheets.html ).

If the window is stuck, in another CMD window:

```bat
taskkill /F /IM streamlit.exe
```

## If the browser shows a red NumPy / DLL error

The app is fine. Windows blocked a file in `.venv`. Close `start.bat`,
complete **Once — allow this folder in Windows**, run `setup.bat`
again (it rebuilds `.venv`), then `start.bat`.

## If Load model fails

Windows Security can block the local engine. In Windows Security, open
**App and browser control**. If **Smart App Control** is On, a test PC
can set it to Off, then run `start.bat` again. This is a Windows
policy, not a bad model file.
