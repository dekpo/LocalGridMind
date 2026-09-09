"""Launcher path helper. Does not start Streamlit or PyInstaller."""

from pathlib import Path

from tools.portable.launcher import portable_root, streamlit_command


def test_portable_root_is_repo_root_when_not_frozen() -> None:
    root = portable_root()
    assert (root / "src" / "app.py").is_file()
    assert (root / "tools" / "portable" / "launcher.py").is_file()


def test_portable_root_uses_exe_folder_when_frozen(monkeypatch, tmp_path: Path) -> None:
    exe = tmp_path / "LocalGridMind.exe"
    exe.write_bytes(b"x")
    monkeypatch.setattr("tools.portable.launcher.sys.frozen", True, raising=False)
    monkeypatch.setattr("tools.portable.launcher.sys.executable", str(exe))
    assert portable_root() == tmp_path


def test_streamlit_command_uses_portable_python(tmp_path: Path) -> None:
    command = streamlit_command(tmp_path)
    assert command[0] == str(tmp_path / "runtime" / "python.exe")
    assert command[1:4] == ["-m", "streamlit", "run"]
    assert command[4] == str(tmp_path / "src" / "app.py")
