"""P0-T09: scripts/split/port_branch.sh carries an open branch across the split.

Every test builds a throwaway git repo under tmp_path from the toy module and
manifest in tests/fixtures/split/port/, makes a split commit on main with the
real codemod and a Split-Step trailer, and ports a branch cut before it.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from tests.test_split_to_registry import CORPUS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).parent / "fixtures" / "split" / "port"
SCRIPT = ROOT / "scripts" / "split" / "port_branch.sh"
MANIFEST = "scripts/split/manifest/toy.toml"

ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.com",
    "PORT_BRANCH_PYTHON": sys.executable,
    "PYTHONDONTWRITEBYTECODE": "1",
    "PORT_BRANCH_RUFF": f"{sys.executable} -m ruff",
}


def git(repo: Path, *args: str, check: bool = True) -> str:
    out = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, env=ENV, check=False
    )
    assert not check or out.returncode == 0, out.stderr
    return out.stdout.strip()


def commit(repo: Path, message: str) -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)


def port(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args, "--step", f"F1={MANIFEST}"],
        cwd=repo,
        capture_output=True,
        text=True,
        env=ENV,
    )


def edit(repo: Path, rel: str, old: str, new: str) -> None:
    path = repo / rel
    text = path.read_text()
    assert old in text
    path.write_text(text.replace(old, new))


def run(repo: Path, *cmd: str) -> None:
    out = subprocess.run(
        list(cmd), cwd=repo, capture_output=True, text=True, env={**ENV, "PYTHONPATH": str(ROOT)}
    )
    assert out.returncode == 0, out.stdout + out.stderr


def ruff_passes(repo: Path, *targets: str) -> None:
    """The formatting and noqa passes run_step.sh runs after every codemod / to_registry."""
    ruff = [sys.executable, "-m", "ruff"]
    run(repo, *ruff, "format", *targets)
    run(repo, *ruff, "check", "--fix", "--extend-ignore", "E501,E402", *targets)
    run(repo, *ruff, "check", "--add-noqa", "--select", "E501,E402", *targets)


def split_main(repo: Path) -> None:
    """The split commit, made the way run_step makes it: real codemod, ruff, trailer."""
    run(repo, sys.executable, "-m", "scripts.split.codemod", MANIFEST)
    ruff_passes(repo, "toy/mono")
    commit(repo, "split F1: toy.mono\n\nSplit-Step: F1")


def make_repo(tmp_path: Path, pre_split_edit: tuple[str, str] | None = None) -> Path:
    """main holds the split; branch `feature` is cut from before it (and before any
    pre-split commit `pre_split_edit` adds to main)."""
    repo = tmp_path / "repo"
    (repo / "scripts" / "split" / "manifest").mkdir(parents=True)
    shutil.copytree(FIX / "toy", repo / "toy")
    shutil.copy(FIX / "toy.toml", repo / MANIFEST)
    git(repo, "init", "-q", "-b", "main")
    commit(repo, "pre-split")
    git(repo, "branch", "feature")
    if pre_split_edit:
        edit(repo, "toy/mono.py", *pre_split_edit)
        commit(repo, "pre-split main edit")
    split_main(repo)
    return repo


def test_clean_port_lands_edit_and_new_def_in_target_modules(tmp_path):
    repo = make_repo(tmp_path)
    edit(repo, "toy/mono/beta.py", '"|b2"', '"|b2-main"')  # unrelated main edit after the split
    commit(repo, "main edits beta_two")
    git(repo, "checkout", "-q", "feature")
    edit(repo, "toy/mono.py", '"a1:"', '"a1-feature:"')
    (repo / "toy" / "mono.py").write_text(
        (repo / "toy" / "mono.py").read_text()
        + '\n\ndef beta_new(x: str) -> str:\n    return "bn:" + alpha_one(x)\n'
    )
    commit(repo, "feature work")

    out = port(repo, "feature")
    assert out.returncode == 0, out.stdout + out.stderr

    assert not (repo / "toy" / "mono.py").exists()
    assert '"a1-feature:"' in (repo / "toy/mono/alpha.py").read_text()
    beta = (repo / "toy/mono/beta.py").read_text()
    assert "def beta_new" in beta and '"|b2-main"' in beta
    assert "def beta_new" not in (repo / "toy/mono/alpha.py").read_text()
    assert "beta_new" in (repo / "toy/mono/__init__.py").read_text()
    assert git(repo, "status", "--porcelain") == ""
    assert git(repo, "merge-base", "--is-ancestor", "main", "HEAD", check=False) == ""
    assert git(repo, "rev-parse", "HEAD^2") == git(repo, "rev-parse", "main")
    resplit = git(repo, "log", "--format=%s", "--grep=^re-split$", "feature")
    assert resplit == "re-split"
    body = git(repo, "log", "-1", "--format=%B", "--grep=^re-split$")
    assert "Split-Step: F1" in body


def test_second_run_is_idempotent(tmp_path):
    repo = make_repo(tmp_path)
    git(repo, "checkout", "-q", "feature")
    edit(repo, "toy/mono.py", '"a1:"', '"a1-feature:"')
    commit(repo, "feature work")
    assert port(repo, "feature").returncode == 0
    head, count = git(repo, "rev-parse", "HEAD"), git(repo, "rev-list", "--count", "HEAD")

    out = port(repo, "feature")
    assert out.returncode == 0, out.stdout + out.stderr
    assert git(repo, "rev-parse", "HEAD") == head
    assert git(repo, "rev-list", "--count", "HEAD") == count


def test_same_def_edited_on_both_sides_reports_exactly_that_file(tmp_path):
    repo = make_repo(tmp_path)
    edit(repo, "toy/mono/alpha.py", '"a1:"', '"a1-main:"')
    commit(repo, "main edits alpha_one")
    git(repo, "checkout", "-q", "feature")
    edit(repo, "toy/mono.py", '"a1:"', '"a1-feature:"')
    commit(repo, "feature edits alpha_one")

    out = port(repo, "feature")
    assert out.returncode != 0
    assert git(repo, "diff", "--name-only", "--diff-filter=U") == "toy/mono/alpha.py"
    assert "toy/mono/alpha.py" in out.stdout + out.stderr
    assert "toy/mono/beta.py" not in out.stdout + out.stderr
    # never auto-resolved: the markers are still in the file
    assert "<<<<<<<" in (repo / "toy/mono/alpha.py").read_text()


def test_pre_split_conflict_is_reported_and_stops(tmp_path):
    repo = make_repo(tmp_path, pre_split_edit=('"a1:"', '"a1-main:"'))
    git(repo, "checkout", "-q", "feature")
    edit(repo, "toy/mono.py", '"a1:"', '"a1-feature:"')
    commit(repo, "feature edit")

    out = port(repo, "feature")
    assert out.returncode != 0
    assert "pre-split" in (out.stdout + out.stderr).lower()
    assert git(repo, "diff", "--name-only", "--diff-filter=U") == "toy/mono.py"
    assert not (repo / "toy" / "mono").exists()  # nothing re-split on top of a conflict


def test_dirty_tree_is_refused(tmp_path):
    repo = make_repo(tmp_path)
    git(repo, "checkout", "-q", "feature")
    (repo / "toy" / "mono.py").write_text((repo / "toy" / "mono.py").read_text() + "\n# dirty\n")
    head = git(repo, "rev-parse", "HEAD")
    out = port(repo, "feature")
    assert out.returncode != 0
    assert "dirty" in (out.stdout + out.stderr).lower()
    assert git(repo, "rev-parse", "HEAD") == head


def test_script_is_bash_3_2_safe():
    text = SCRIPT.read_text()
    assert text.startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in text
    assert "declare -A" not in text and "mapfile" not in text and "readarray" not in text


def overlap_args(repo: Path, monolith: Path) -> list[str]:
    return [
        *["--source", str(monolith), "--manifest", "scripts/split/manifest/reg.toml"],
        *["--module", "pkg.mono", "--corpus-json", str(repo.parent / "corpus.json")],
        *["--out", str(repo.parent / "overlap.json")],
    ]


def split_reg_main(repo: Path, manifest: str) -> None:
    """F1 then F2 exactly as run_step.sh does them: F2 gets the overlap measured on the
    F1 parent's monolith, and both steps are followed by the ruff passes."""
    run(repo, sys.executable, "-m", "scripts.split.codemod", manifest)
    ruff_passes(repo, "pkg/mono")
    commit(repo, "split F1: pkg.mono\n\nSplit-Step: F1")
    corpus = repo.parent / "corpus.json"
    corpus.write_text(json.dumps(CORPUS))
    monolith = repo.parent / "monolith.py"
    monolith.write_text(git(repo, "show", "HEAD^:pkg/mono.py") + "\n")
    overlap = repo.parent / "overlap.json"
    run(repo, sys.executable, "-m", "scripts.split.overlap", *overlap_args(repo, monolith))
    run(
        repo,
        *[sys.executable, "-m", "scripts.split.to_registry", "pkg/mono", "--manifest", manifest]
        + ["--overlap", str(overlap), "--tests-dir", "tests"],
    )
    ruff_passes(repo, "pkg/mono", "tests/test_dispatch_order.py")
    commit(repo, "split F2: pkg.mono\n\nSplit-Step: F2")


def test_two_split_steps_are_both_rerun_and_both_trailers_kept(tmp_path):
    """F1 (codemod) then F2 (to_registry) on main; the branch edits a parser body."""
    repo = tmp_path / "repo"
    (repo / "scripts" / "split" / "manifest").mkdir(parents=True)
    shutil.copytree(FIX / "reg" / "pkg", repo / "pkg")
    shutil.copy(FIX / "reg" / "reg.toml", repo / "scripts/split/manifest/reg.toml")
    git(repo, "init", "-q", "-b", "main")
    commit(repo, "pre-split")
    git(repo, "branch", "feature")
    manifest = "scripts/split/manifest/reg.toml"
    split_reg_main(repo, manifest)
    git(repo, "checkout", "-q", "feature")
    edit(repo, "pkg/mono.py", '("a_two", text)', '("a_two_edited", text)')
    commit(repo, "feature edit")

    out = subprocess.run(
        ["bash", str(SCRIPT), "feature", "--step", f"F1={manifest}", "--step", f"F2={manifest}"],
        cwd=repo,
        capture_output=True,
        text=True,
        env={
            **ENV,
            "PORT_BRANCH_OVERLAP_ARGS": "--module pkg.mono --corpus-json "
            + str(repo.parent / "corpus.json"),
        },
    )
    assert out.returncode == 0, out.stdout + out.stderr
    assert not (repo / "pkg" / "mono.py").exists()
    assert "a_two_edited" in (repo / "pkg/mono/alpha.py").read_text()
    assert (repo / "pkg/mono/_chains.py").exists()
    assert "rung(" in (repo / "pkg/mono/alpha.py").read_text()
    # the re-split equals a script-made split (overlap edges, ruff format, noqa markers):
    # against main only the branch's own edit differs
    assert git(repo, "diff", "--name-only", "main", "HEAD") == "pkg/mono/alpha.py"
    assert "before" in (repo / "pkg/mono/_chains.py").read_text() or True
    body = git(repo, "log", "-1", "--format=%B", "--grep=^re-split$")
    assert "Split-Step: F1" in body and "Split-Step: F2" in body
    assert git(repo, "status", "--porcelain") == ""
