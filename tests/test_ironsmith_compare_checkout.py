"""`scripts/ironsmith_compare/checkout.py`: the pin and the checks `doctor` runs on the
user's ironsmith checkout. A throwaway `git init` repo stands in for the checkout; no
ironsmith code or tool is ever run here."""

from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.ironsmith_compare.checkout import check_checkout, head_sha, load_pin, run


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "ironsmith"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.invalid")
    _git(repo, "config", "user.name", "t")
    (repo / "README").write_text("stand-in\n")
    _git(repo, "add", "README")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


def _all_tools(_name: str) -> str:
    return "/usr/bin/tool"


def test_the_committed_pin_names_the_reviewed_ironsmith_commit():
    pin = load_pin()
    assert pin.repo == "https://github.com/Chiplis/ironsmith"
    assert pin.commit == "a59720c3966b02437c50807b8ed664496862810b"
    assert pin.licence == "AGPL-3.0-or-later"
    assert pin.coverage_build[0] == "cargo"


def test_a_clean_checkout_at_the_pin_has_no_problems(tmp_path):
    repo = _repo(tmp_path)
    pin = load_pin()._replace(commit=head_sha(repo))
    assert check_checkout(repo, pin, which=_all_tools) == []


def test_a_checkout_at_another_commit_is_reported(tmp_path):
    repo = _repo(tmp_path)
    problems = check_checkout(repo, load_pin(), which=_all_tools)
    assert any("HEAD" in p and "a59720c39" in p for p in problems)


def test_a_modified_checkout_is_reported(tmp_path):
    repo = _repo(tmp_path)
    (repo / "README").write_text("patched\n")
    (repo / "extra.txt").write_text("x\n")
    pin = load_pin()._replace(commit=head_sha(repo))
    problems = check_checkout(repo, pin, which=_all_tools)
    assert any("not clean" in p for p in problems)


def test_a_missing_checkout_is_reported(tmp_path):
    problems = check_checkout(tmp_path / "nowhere", load_pin(), which=_all_tools)
    assert len(problems) == 1
    assert "does not exist" in problems[0]


def test_each_missing_tool_is_reported(tmp_path):
    repo = _repo(tmp_path)
    pin = load_pin()._replace(commit=head_sha(repo))
    problems = check_checkout(repo, pin, which=lambda name: None)
    assert any("cargo" in p for p in problems)


def test_run_passes_argv_without_a_shell_and_logs_output(tmp_path):
    log = tmp_path / "logs" / "echo.log"
    assert run(["echo", "a;b"], cwd=tmp_path, log=log) == 0
    assert log.read_text().strip().endswith("a;b")
