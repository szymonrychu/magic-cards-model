"""P0-T10: step driver (scripts/split/run_step.sh) and gates (scripts/split/gates.sh).

Tooling tests only: `--dry-print` shows the commands each script would run and the
tests assert on that text; the commit tests run the driver in a tmp git repo over the
tiny codemod fixture package. Nothing here runs the real suite or the real engine
modules.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUN_STEP = ROOT / "scripts" / "split" / "run_step.sh"
GATES = ROOT / "scripts" / "split" / "gates.sh"
FIX = Path(__file__).parent / "fixtures" / "split" / "codemod"

STEP_MODULE = {
    "F1": "effects",
    "F2": "effects",
    "F3": "game",
    "F4a": "layers",
    "F4b": "replacement",
    "F4c": "casting",
    "F4d": "triggers",
    "F4e": "cost",
}


def sh(script: Path, *args: str, cwd: Path = ROOT, env: dict | None = None):
    full_env = {**os.environ, **(env or {})}
    return subprocess.run(
        ["bash", str(script), *args], cwd=cwd, env=full_env, capture_output=True, text=True
    )


def git(cwd: Path, *args: str) -> str:
    res = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)
    return res.stdout


# ----- run_step.sh: arguments -----


@pytest.mark.parametrize("args", [[], ["F9"], ["f1"], ["F1", "F2"], ["--bogus", "F1"]])
def test_run_step_rejects_bad_arguments(args):
    res = sh(RUN_STEP, *args)
    assert res.returncode == 2
    assert "usage" in res.stderr.lower()


# ----- run_step.sh: step -> command mapping -----


@pytest.mark.parametrize("step,module", sorted(STEP_MODULE.items()))
def test_run_step_dry_print_maps_step_to_commands(step, module):
    res = sh(RUN_STEP, "--dry-print", step)
    assert res.returncode == 0, res.stderr
    out = res.stdout
    assert f"manifest/{module}.toml" in out
    if step == "F2":
        assert "overlap.py" in out
        assert "to_registry.py" in out
        assert "codemod.py" not in out
        assert out.index("overlap.py") < out.index("to_registry.py")
    else:
        assert "codemod.py" in out
        assert "to_registry.py" not in out
        assert "overlap.py" not in out
    assert "ruff format" in out
    assert "ruff check --fix" in out
    assert f"split {step}: {module}" in out
    assert f"Split-Step: {step}" in out
    # format/lint come after the generator and before the commit
    assert out.index("ruff format") < out.index("git commit")


def test_run_step_dry_print_restricts_ruff_to_the_new_package():
    out = sh(RUN_STEP, "--dry-print", "F4c").stdout
    ruff_lines = [ln for ln in out.splitlines() if "ruff" in ln]
    assert ruff_lines
    assert all("machines/casting" in ln for ln in ruff_lines)


def test_run_step_dry_print_ignores_a_dirty_tree(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    git(repo, "init", "-q")
    (repo / "x").write_text("x")
    res = sh(RUN_STEP, "--dry-print", "F3", cwd=repo)
    assert res.returncode == 0
    assert "codemod.py" in res.stdout


# ----- run_step.sh: refusals and the commit, in a tmp repo -----

GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.com",
    "PYTHONDONTWRITEBYTECODE": "1",
}


@pytest.fixture
def repo(tmp_path):
    work = tmp_path / "repo"
    shutil.copytree(FIX, work, ignore=shutil.ignore_patterns("__pycache__"))
    mdir = tmp_path / "manifests"
    mdir.mkdir()
    for name in STEP_MODULE.values():
        shutil.copy(FIX / "mod.toml", mdir / f"{name}.toml")
    (work / ".gitignore").write_text("__pycache__/\n")
    git(work, "init", "-q")
    git(work, "config", "commit.gpgsign", "false")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "fixture")
    env = {
        **GIT_ENV,
        "SPLIT_MANIFEST_DIR": str(mdir),
        "SPLIT_SURFACE": str(FIX / "surface_mod.json"),
        "SPLIT_PY": sys.executable,
        "SPLIT_RUFF": f"{sys.executable} -m ruff",
    }
    return work, env


def test_run_step_refuses_a_dirty_tree(repo):
    work, env = repo
    head = git(work, "rev-parse", "HEAD")
    (work / "stray.txt").write_text("dirty")
    res = sh(RUN_STEP, "F1", cwd=work, env=env)
    assert res.returncode != 0
    assert "dirty" in res.stderr.lower()
    assert git(work, "rev-parse", "HEAD") == head
    assert (work / "root/fxtop/pk/mod.py").exists()


def test_run_step_refuses_a_modified_tracked_file(repo):
    work, env = repo
    with (work / "root/fxtop/pk/mod.py").open("a") as fh:
        fh.write("\n# edit\n")
    res = sh(RUN_STEP, "F1", cwd=work, env=env)
    assert res.returncode != 0
    assert "dirty" in res.stderr.lower()


@pytest.mark.parametrize("step,prev", [("F2", "F1"), ("F3", "F2"), ("F4a", "F3"), ("F4e", "F4d")])
def test_run_step_refuses_without_the_previous_steps_trailer(repo, step, prev):
    work, env = repo
    res = sh(RUN_STEP, step, cwd=work, env=env)
    assert res.returncode != 0
    assert f"Split-Step: {prev}" in res.stderr
    assert git(work, "status", "--porcelain") == ""


def test_run_step_f1_makes_exactly_one_commit_with_the_trailer(repo):
    work, env = repo
    before = git(work, "rev-list", "--count", "HEAD").strip()
    res = sh(RUN_STEP, "F1", cwd=work, env=env)
    assert res.returncode == 0, res.stderr
    assert int(git(work, "rev-list", "--count", "HEAD")) == int(before) + 1
    assert git(work, "log", "-1", "--format=%s") == "split F1: effects\n"
    trailers = git(work, "log", "-1", "--format=%(trailers:key=Split-Step,valueonly)")
    assert trailers.strip() == "F1"
    assert git(work, "status", "--porcelain") == ""
    pk = work / "root/fxtop/pk"
    assert not (pk / "mod.py").exists()
    assert (pk / "mod" / "__init__.py").exists()
    committed = git(work, "show", "--name-only", "--format=", "HEAD")
    assert "root/fxtop/pk/mod/__init__.py" in committed
    assert "root/fxtop/pk/mod.py" in committed  # the deletion


def test_run_step_next_step_passes_the_precondition_after_the_previous_one(repo):
    work, env = repo
    assert sh(RUN_STEP, "F1", cwd=work, env=env).returncode == 0
    # F3 needs F2's trailer, which this repo does not have: refused on exactly that
    res = sh(RUN_STEP, "F3", cwd=work, env=env)
    assert res.returncode != 0
    assert "Split-Step: F2" in res.stderr


# ----- gates.sh: arguments -----


def gates(*args: str):
    return sh(GATES, *args)


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["bogus", "--baseline", "b.json", "--step", "F1"],
        ["cheap", "--step", "F1"],
        ["cheap", "--baseline", "b.json"],
        ["cheap", "--baseline", "b.json", "--step", "F9"],
        ["cheap", "--baseline", "b.json", "--step", "F4"],
        ["cheap", "--baseline", "/nonexistent/b.json", "--step", "F1"],
        ["cheap", "--baseline", "b.json", "--step", "F1", "--wat"],
    ],
)
def test_gates_rejects_bad_arguments(args):
    res = gates(*args)
    assert res.returncode == 2
    assert "usage" in res.stderr.lower() or "baseline" in res.stderr.lower()


def test_gates_dry_print_does_not_need_the_baseline_file():
    res = gates("--dry-print", "cheap", "--baseline", "/nonexistent/b.json", "--step", "F1")
    assert res.returncode == 0, res.stderr


# ----- gates.sh: what each mode runs -----


def dry(mode: str, step: str, *extra: str) -> str:
    res = gates("--dry-print", mode, "--baseline", "before.json", "--step", step, *extra)
    assert res.returncode == 0, res.stderr
    return res.stdout


def test_cheap_gate_runs_lint_measure_compare_and_the_split_tests():
    out = dry("cheap", "F1")
    assert "mise run lint" in out
    assert "baselines.py measure" in out
    assert "baselines.py compare before.json" in out
    assert "--step F1" in out
    assert "tests/test_module_hygiene.py" in out
    assert "tests/test_split_surface.py" in out
    assert "test_dispatch_order.py" not in out


def test_cheap_gate_does_not_run_the_full_suite_or_the_guard():
    out = dry("cheap", "F3")
    assert "test:full" not in out
    assert "regression:guard" not in out
    assert "tests/golden" not in out
    assert "--full" not in out


@pytest.mark.parametrize("step", ["F2", "F3", "F4a", "F4b", "F4c", "F4d", "F4e"])
def test_dispatch_order_test_joins_from_f2_on(step):
    assert "tests/test_dispatch_order.py" in dry("cheap", step)


def test_full_gate_adds_full_suite_goldens_and_the_ratchet_guard():
    out = dry("full", "F2", "--base", "abc1234")
    assert "mise run lint" in out
    assert "tests/test_dispatch_order.py" in out
    assert "baselines.py measure" in out
    assert "--full" in out
    assert "git diff --exit-code -- tests/golden" in out
    assert "mise run regression:guard -- --repo . --base abc1234 --ratchet" in out
    assert "--step F2" in out


def test_full_gate_takes_the_guard_base_from_the_baseline_by_default():
    out = dry("full", "F1")
    assert "regression:guard -- --repo . --base" in out
    assert "engine_sha" in out


def test_gates_dry_print_names_every_check():
    out = dry("full", "F2")
    for name in ("lint", "fingerprint", "sweep hash", "import time", "test count", "goldens"):
        assert name in out


# ----- gates.sh: verdicts, with stubbed tools (no real suite) -----

STUB_BASELINES = """\
import json, os, sys

args = sys.argv[1:]
if args[0] == "measure":
    out = args[args.index("--out") + 1]
    data = {"suite": {"wall_s": 1.0, "returncode": int(os.environ.get("STUB_SUITE_RC", "0"))}}
    if "--full" in args:
        data["suite_full"] = {"wall_s": 2.0, "returncode": 0}
    open(out, "w").write(json.dumps(data))
else:
    for line in os.environ.get("STUB_VIOLATIONS", "").split(";"):
        if line:
            print("VIOLATION: " + line)
    sys.exit(1 if os.environ.get("STUB_VIOLATIONS") else 0)
"""


@pytest.fixture
def stubbed(tmp_path):
    tools = tmp_path / "tools"
    tools.mkdir()
    shutil.copy(GATES, tools / "gates.sh")
    (tools / "baselines.py").write_text(STUB_BASELINES)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    mise = bin_dir / "mise"
    mise.write_text('#!/bin/sh\nexit "${STUB_MISE_RC:-0}"\n')
    mise.chmod(0o755)
    repo = tmp_path / "repo"
    (repo / "tests" / "golden").mkdir(parents=True)
    (repo / "tests" / "golden" / "g.json").write_text("{}")
    for name in ("test_module_hygiene", "test_split_surface", "test_dispatch_order"):
        (repo / "tests" / f"{name}.py").write_text("def test_ok():\n    pass\n")
    git(repo, "init", "-q")
    git(repo, "config", "commit.gpgsign", "false")
    git(repo, "add", "-A")
    subprocess.run(
        ["git", "commit", "-q", "-m", "x"], cwd=repo, env={**os.environ, **GIT_ENV}, check=True
    )
    (tmp_path / "before.json").write_text('{"engine_sha": "cafe123"}')
    env = {
        "SPLIT_PY": sys.executable,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
    }

    def run(*args, **extra):
        return sh(
            tools / "gates.sh",
            *args,
            "--baseline",
            str(tmp_path / "before.json"),
            "--step",
            "F1",
            cwd=repo,
            env={**env, **extra},
        )

    return run


def test_gates_pass_prints_pass_lines_with_wall_times_and_exits_zero(stubbed):
    res = stubbed("cheap")
    lines = res.stdout.splitlines()
    assert res.returncode == 0, res.stdout
    checks = [ln for ln in lines if ln.startswith(("PASS", "FAIL"))]
    assert checks and all(ln.rstrip().endswith("s)") for ln in checks)
    for name in ("lint", "mise run test", "fingerprint compare", "sweep hash", "import time"):
        assert any(name in ln for ln in checks), name


def test_gates_compare_violation_fails_only_its_check_and_exits_nonzero(stubbed):
    res = stubbed("cheap", STUB_VIOLATIONS="sweep hash changed: a -> b")
    assert res.returncode == 1
    assert any(ln.startswith("FAIL sweep hash") for ln in res.stdout.splitlines())
    assert any(ln.startswith("PASS import time") for ln in res.stdout.splitlines())
    assert "sweep hash changed: a -> b" in res.stdout


def test_gates_cheap_ignores_a_missing_suite_full_measurement(stubbed):
    res = stubbed("cheap", STUB_VIOLATIONS="suite_full wall time: not measured in after")
    assert not any(ln.startswith("FAIL") for ln in res.stdout.splitlines()), res.stdout


def test_gates_full_fails_on_a_suite_full_violation(stubbed):
    res = stubbed("full", STUB_VIOLATIONS="suite_full wall time: not measured in after")
    assert res.returncode == 1
    assert any(ln.startswith("FAIL suite_full") for ln in res.stdout.splitlines())


def test_gates_failing_lint_exits_nonzero(stubbed):
    res = stubbed("cheap", STUB_MISE_RC="1")
    assert res.returncode == 1
    assert any(ln.startswith("FAIL lint") for ln in res.stdout.splitlines())


def test_gates_failing_suite_is_a_fail_line(stubbed):
    res = stubbed("cheap", STUB_SUITE_RC="1")
    assert res.returncode == 1
    assert any(ln.startswith("FAIL mise run test") for ln in res.stdout.splitlines())


def test_gates_full_pass_runs_goldens_and_guard_checks(stubbed):
    res = stubbed("full")
    assert res.returncode == 0, res.stdout
    names = [ln for ln in res.stdout.splitlines() if ln.startswith("PASS")]
    for name in ("mise run test:full", "goldens byte-identical", "regression guard"):
        assert any(name in ln for ln in names), name


def test_gates_full_fails_when_the_guard_fails(stubbed):
    res = stubbed("full", STUB_MISE_RC="1")
    assert res.returncode == 1
    assert any(ln.startswith("FAIL regression guard") for ln in res.stdout.splitlines())


# ----- mise wiring -----

SPLIT_TASKS = {
    "split:surface": "scripts/split/surface.py",
    "split:manifest-check": "scripts/split/manifest_lib.py check",
    "split:codemod": "scripts/split/codemod.py",
    "split:to-registry": "scripts/split/to_registry.py",
    "split:overlap": "scripts/split/overlap.py",
    "split:baselines": "scripts/split/baselines.py",
    "split:step": "scripts/split/run_step.sh",
    "split:gate": "scripts/split/gates.sh",
    "split:port-branch": "scripts/split/port_branch.sh",
}


def test_mise_has_one_thin_task_per_split_script():
    import tomllib

    tasks = tomllib.loads((ROOT / "mise.toml").read_text())["tasks"]
    for name, script in SPLIT_TASKS.items():
        assert name in tasks, name
        assert tasks[name]["description"]
        assert tasks[name]["run"].endswith(script)


def test_run_step_f2_regenerates_the_committed_dispatch_fingerprint_baseline():
    """F2 reorders the chains (FAMILIES, then source order), so the F2 commit carries the
    regenerated tests/dispatch_fingerprint_baseline.json (design: regenerated once) that
    `mise run test`'s fingerprint test reads from then on; no other step touches it."""
    out = sh(RUN_STEP, "--dry-print", "F2").stdout
    line = next(ln for ln in out.splitlines() if "dispatch_fingerprint.py" in ln)
    assert "tests/dispatch_fingerprint_baseline.json" in line
    fp = out.index("dispatch_fingerprint.py")
    assert out.index("ruff check --fix") < fp < out.index("git commit")
    for step in ("F1", "F3", "F4e"):
        assert "dispatch_fingerprint" not in sh(RUN_STEP, "--dry-print", step).stdout
