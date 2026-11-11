"""The ironsmith pin and the checks run against the user's checkout before `collect`.

Every subprocess is an argv list (never a shell string) whose output goes to a log file.
"""

from __future__ import annotations

import shutil
import subprocess
import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

PIN_PATH = Path(__file__).with_name("pin.toml")

#: Tools `collect` starts: cargo for the status binaries, node for the scenario runner.
REQUIRED_TOOLS = ("git", "cargo", "node")


class Pin(NamedTuple):
    repo: str
    commit: str
    date: str
    licence: str
    coverage_build: list[str]
    behaviour_build: list[str]


def load_pin(path: Path = PIN_PATH) -> Pin:
    data = tomllib.loads(path.read_text())
    return Pin(**{field: data[field] for field in Pin._fields})


def _git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(path), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def head_sha(path: Path) -> str:
    return _git(path, "rev-parse", "HEAD")


def check_checkout(
    path: Path, pin: Pin, *, which: Callable[[str], str | None] = shutil.which
) -> list[str]:
    """Every reason `path` is not an unmodified ironsmith checkout at `pin`, plus every
    required tool missing from PATH; empty when all is well. Build outputs do not count
    as modifications: ironsmith's own `.gitignore` covers them."""
    if not path.is_dir():
        return [f"ironsmith checkout {path} does not exist (see docs/ironsmith-compare.md)"]
    problems: list[str] = []
    try:
        head = head_sha(path)
    except subprocess.CalledProcessError:
        problems.append(f"{path} is not a git checkout")
    else:
        if head != pin.commit:
            problems.append(f"HEAD {head[:12]} != pin {pin.commit} (git checkout {pin.commit})")
        if _git(path, "status", "--porcelain"):
            problems.append(f"{path} is not clean: ironsmith must stay unmodified (git status)")
    missing = [tool for tool in REQUIRED_TOOLS if not which(tool)]
    problems += [f"required tool '{tool}' not found on PATH" for tool in missing]
    return problems


def run(argv: list[str], *, cwd: Path, log: Path, env: dict[str, str] | None = None) -> int:
    """Run `argv` in `cwd`, stdout and stderr appended to `log`; the exit code."""
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a") as out:
        out.write(f"$ {' '.join(argv)}  (cwd {cwd})\n")
        out.flush()
        done = subprocess.run(argv, cwd=cwd, stdout=out, stderr=subprocess.STDOUT, env=env)
        return done.returncode
