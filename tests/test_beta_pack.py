"""Closed-beta pack templates. Does not copy into release/."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BETA = ROOT / "tools" / "beta"


def test_beta_templates_live_under_tools_not_repo_root() -> None:
    assert (BETA / "assemble.bat").is_file()
    assert (BETA / "setup.bat").is_file()
    assert (BETA / "start.bat").is_file()
    assert (BETA / "TEST_CASES.md").is_file()
    assert "fcffsimpleginzu.xlsx" in (BETA / "TEST_CASES.md").read_text(encoding="utf-8")
    assert not (ROOT / "setup.bat").is_file()
    assert not (ROOT / "start.bat").is_file()
    assert not (ROOT / "BETA.md").is_file()


def test_tester_readme_names_the_prototype_folder() -> None:
    text = (BETA / "README.md").read_text(encoding="utf-8")
    assert "ChatWithExcelFile" in text
    assert "Qwen3.5-9B-Q5_K_M.gguf" in text
    assert "setup.bat" in text
    assert "start.bat" in text
