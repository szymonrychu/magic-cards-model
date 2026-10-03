#!/usr/bin/env python
"""Regression guard: catch a fix silently touching an already-passing test or
already-fixed card, rather than trusting an agent's own summary of its diff.

    uv run python scripts/regression_guard.py --repo <path> --base <sha> [--head HEAD] \
        [--ratchet [--bulk <oracle-cards file>] [--workers N]]

Two independent checks, both against `git diff base..head` on `--repo`
(any repo, engine or api):

**A. Protected-test report** (always runs). Every change under `tests/`
that touches *pre-existing* test content is reported - a deleted test
function or file, a removed or changed `assert`/`pytest.raises` line in a
test that existed at base, a changed or removed module-level expectation
constant that an existing test references, a changed or deleted file under
`tests/golden/`, or an `xfail`/`skip` marker newly added to an existing
test. Purely added tests and files are never flagged - only content that
existed at base and changed shape at head.

This is a syntactic diff (Python `ast`), not a semantic one: it cannot tell
a legitimate strengthening of an assertion from a weakening that hides a
regression. That judgment is for the human or reviewer agent who reads the
`before`/`after` snippets this prints - the report's job is only to make
sure every such change gets read by someone, not to auto-approve or
auto-reject any of them.

**B. Card-status ratchet** (`--ratchet`, engine repo only). Classifies two
sets of cards with the engine's own support oracle, once with the base
commit's code and once with head's, in isolated git worktrees so the two
never share a Python import:

- *pool* - every printing that exists at base under
  `src/magic_cards_model/data/printings/` (`card_support` directly);
- *oracle* - every Modern/Pioneer/Standard-legal card in Scryfall's
  `oracle-cards` bulk (~22,700 cards), selected and classified exactly the
  way `scripts/card_coverage.py` does it: one shared parse of the cached
  bulk (`--bulk`, else `$REGRESSION_GUARD_BULK`, else
  `<repo>/.scryfall-cache/oracle-cards.jsonl.gz`, downloaded if missing),
  `target_format_pool`, then each worktree's *own*
  `scripts/card_coverage.py` `classify_card_raw` (so `support.status` is
  the worst of the rules-text *and* keyword clauses).

A card whose status gets worse at head than at base (handled ->
unaudited/notice/silent/error/removed, and so on) is a hard failure, and a
pool card tested at base but untested at head is too. An oracle card is also
held to the committed floor `docs/card_coverage/support-baseline.json` as it
stands at base (`git show base:<path>`; written by `card_coverage.py`, and
by `mise run coverage:baseline`): head reading it worse than the baseline
fails unless Scryfall re-worded it (its oracle-text+keywords hash changed),
which is reported under `oracle_changed` instead. Cards absent from the
baseline (`new_cards`), cards the engine now beats the baseline on
(`improved_vs_baseline`, with a hint to regenerate it) and baseline cards
gone from the bulk (`left_pool`) are reported, never failed. Each offender
names its `source` (`pool` or `oracle`). A missing or unreadable bulk fails
closed (exit 2), never a silent pass. At most 6 workers per side (the
suite-lock budget).

"Tested" here means the card's name is quoted somewhere under `tests/*.py`
or it has a `tests/golden/<slug>/` directory - being one of the probe
printings in `data/printings/` is not itself evidence a test exercises it,
since that directory *is* the pool's own candidate set.

Both checks are read-only: nothing under `--repo` is ever modified. The
temporary worktrees this makes for `--ratchet` are removed before the
process exits, even on failure.
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class RegressionGuardError(RuntimeError):
    """A precondition the guard cannot work around (not a card/test finding)."""


# ---------------------------------------------------------------------------
# git plumbing
# ---------------------------------------------------------------------------


def _run_git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=check)


def resolve_sha(repo: Path, ref: str) -> str:
    result = _run_git(repo, "rev-parse", ref)
    return result.stdout.strip()


def file_at(repo: Path, rev: str, path: str) -> str | None:
    """`path`'s content at `rev`, or `None` if it does not exist there."""
    result = _run_git(repo, "show", f"{rev}:{path}", check=False)
    if result.returncode != 0:
        return None
    return result.stdout


def _name_status(repo: Path, base: str, head: str, *paths: str) -> list[list[str]]:
    """`git diff --name-status -M base..head -- paths`, one row per line."""
    result = _run_git(repo, "diff", "--name-status", "-M", f"{base}..{head}", "--", *paths)
    rows = []
    for line in result.stdout.splitlines():
        if line.strip():
            rows.append(line.split("\t"))
    return rows


# ---------------------------------------------------------------------------
# Protected-test report: Python test-file diffing
# ---------------------------------------------------------------------------

_MARKER_RE = {
    "xfail": re.compile(r"\bmark\.xfail\b"),
    "skip": re.compile(r"\bmark\.skip(if)?\b"),
}


def _is_test_name(name: str) -> bool:
    return name.startswith("test_")


def _decorator_markers(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    markers: set[str] = set()
    for dec in node.decorator_list:
        try:
            text = ast.unparse(dec)
        except Exception:  # noqa: BLE001 - a decorator ast.unparse cannot help with
            continue
        for name, pattern in _MARKER_RE.items():
            if pattern.search(text):
                markers.add(name)
    return markers


def _assert_like_statements(node: ast.AST) -> list[str]:
    stmts: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Assert):
            try:
                stmts.append(ast.unparse(child))
            except Exception:  # noqa: BLE001
                continue
        elif isinstance(child, ast.With):
            for item in child.items:
                try:
                    text = ast.unparse(item.context_expr)
                except Exception:  # noqa: BLE001
                    continue
                if "raises" in text:
                    stmts.append(f"with {text}:")
    return stmts


@dataclass(frozen=True)
class TestFunction:
    qualname: str
    source: str
    asserts: tuple[str, ...]
    markers: frozenset[str]


def parse_test_functions(source: str) -> dict[str, TestFunction]:
    """Every `test_*` function or method in `source`, keyed by its qualified
    name (`Class.test_foo` for a method, `test_foo` for a bare function)."""
    tree = ast.parse(source)
    found: dict[str, TestFunction] = {}

    def visit(body: Iterable[ast.stmt], prefix: str) -> None:
        for child in body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if _is_test_name(child.name):
                    qualname = f"{prefix}{child.name}"
                    found[qualname] = TestFunction(
                        qualname=qualname,
                        source=ast.get_source_segment(source, child) or "",
                        asserts=tuple(_assert_like_statements(child)),
                        markers=frozenset(_decorator_markers(child)),
                    )
                # a test function nested inside another is not a pattern this
                # codebase uses; not walked further on purpose.
            elif isinstance(child, ast.ClassDef):
                visit(child.body, f"{prefix}{child.name}.")

    visit(tree.body, "")
    return found


def module_constants(source: str) -> dict[str, str]:
    """Every module-level `NAME = <expr>` (or annotated) assignment, as its
    normalized source text - the "expectation constants" a test can compare
    against."""
    tree = ast.parse(source)
    out: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and not target.id.startswith("_"):
                out[target.id] = ast.unparse(node.value)
        elif isinstance(node, ast.AnnAssign):
            if (
                isinstance(node.target, ast.Name)
                and not node.target.id.startswith("_")
                and node.value is not None
            ):
                out[node.target.id] = ast.unparse(node.value)
    return out


def _referenced_names(test_functions: dict[str, TestFunction]) -> set[str]:
    referenced: set[str] = set()
    for fn in test_functions.values():
        try:
            tree = ast.parse(fn.source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                referenced.add(node.id)
    return referenced


def _snippet(text: str | None, limit: int = 400) -> str | None:
    if text is None:
        return None
    text = text.strip("\n")
    if len(text) > limit:
        text = text[:limit] + "…"
    return text


def _finding(file: str, test: str | None, kind: str, before: Any, after: Any) -> dict:
    return {
        "file": file,
        "test": test,
        "kind": kind,
        "before": _snippet(before if isinstance(before, str) or before is None else str(before)),
        "after": _snippet(after if isinstance(after, str) or after is None else str(after)),
    }


def diff_test_file(path: str, base_source: str | None, head_source: str | None) -> list[dict]:
    """Every protected-test finding between one file's content at base and
    at head. `base_source is None` (the file did not exist at base, a pure
    add) always yields nothing. `head_source is None` (the file was deleted)
    flags every test that existed at base as deleted."""
    if base_source is None:
        return []
    try:
        base_tests = parse_test_functions(base_source)
    except SyntaxError:
        return []
    head_tests: dict[str, TestFunction] = {}
    if head_source is not None:
        try:
            head_tests = parse_test_functions(head_source)
        except SyntaxError:
            head_tests = {}

    findings: list[dict] = []
    for qualname, base_fn in base_tests.items():
        head_fn = head_tests.get(qualname)
        if head_fn is None:
            findings.append(_finding(path, qualname, "deleted_test", base_fn.source, None))
            continue

        added_markers = sorted(head_fn.markers - base_fn.markers)
        for marker in added_markers:
            findings.append(
                _finding(
                    path,
                    qualname,
                    "marker_added",
                    f"(no @pytest.mark.{marker} at base)",
                    f"@pytest.mark.{marker}",
                )
            )

        for i, base_assert in enumerate(base_fn.asserts):
            head_assert = head_fn.asserts[i] if i < len(head_fn.asserts) else None
            if head_assert != base_assert:
                findings.append(
                    _finding(path, qualname, "assert_changed", base_assert, head_assert)
                )

    try:
        base_consts = module_constants(base_source)
    except SyntaxError:
        base_consts = {}
    head_consts: dict[str, str] = {}
    if head_source is not None:
        try:
            head_consts = module_constants(head_source)
        except SyntaxError:
            head_consts = {}
    referenced = _referenced_names(base_tests)
    for name, base_val in base_consts.items():
        if name not in referenced:
            continue
        head_val = head_consts.get(name)
        if head_val != base_val:
            findings.append(
                _finding(path, name, "expectation_constant_changed", base_val, head_val)
            )

    return findings


def golden_findings(repo: Path, base: str, head: str) -> list[dict]:
    """Every changed or deleted file under `tests/golden/` (added ones are
    not flagged)."""
    findings: list[dict] = []
    for row in _name_status(repo, base, head, "tests/golden"):
        status = row[0]
        if status.startswith("A"):
            continue
        if status.startswith("R"):
            old_path, new_path = row[1], row[2]
        else:
            old_path = new_path = row[1]
        before = file_at(repo, base, old_path)
        after = None if status.startswith("D") else file_at(repo, head, new_path)
        findings.append(_finding(new_path, None, "golden_changed", before, after))
    return findings


def protected_test_report(repo: Path, base: str, head: str) -> list[dict]:
    """Every protected-test finding in `git diff base..head` under `tests/`
    in `repo`. JSON-serializable list of `{file, test, kind, before, after}`."""
    findings = golden_findings(repo, base, head)
    for row in _name_status(repo, base, head, "tests"):
        status = row[0]
        if status.startswith("R"):
            old_path, new_path = row[1], row[2]
        else:
            old_path = new_path = row[1]
        if new_path.startswith("tests/golden/"):
            continue  # handled above
        if not new_path.endswith(".py"):
            continue
        if status.startswith("A"):
            continue  # purely added file - never flagged
        base_source = file_at(repo, base, old_path)
        head_source = None if status.startswith("D") else file_at(repo, head, new_path)
        findings.extend(diff_test_file(new_path, base_source, head_source))
    return findings


# ---------------------------------------------------------------------------
# Card-status ratchet
# ---------------------------------------------------------------------------

_QUOTED_RE = re.compile(r"[\"']([^\"'\n]{2,80})[\"']")


def _slug(name: str) -> str:
    return "-".join(re.findall(r"[a-z0-9]+", name.lower().replace("'", "")))


def _front_name(name: str) -> str:
    return name.split("//")[0].strip()


@dataclass(frozen=True)
class TestedIndex:
    """Whether a card is "tested", for the ratchet's own narrower meaning:
    quoted in a test file, or has a golden directory. Deliberately *not*
    `card_coverage.py`'s broader `TestedIndex` (which also counts mere
    membership in `data/printings/` as tested) - here that directory *is*
    the candidate pool, so counting membership as evidence of testing would
    make the "untested at head" check vacuous."""

    quoted_names: frozenset[str]
    golden_slugs: frozenset[str]

    def is_tested(self, name: str) -> bool:
        for candidate in (name, _front_name(name)):
            if candidate in self.quoted_names:
                return True
            if _slug(candidate) in self.golden_slugs:
                return True
        return False


def build_tested_index(worktree_dir: Path) -> TestedIndex:
    tests_dir = worktree_dir / "tests"
    golden_dir = tests_dir / "golden"

    quoted_names: set[str] = set()
    if tests_dir.exists():
        for path in tests_dir.rglob("*.py"):
            try:
                text = path.read_text(errors="ignore")
            except OSError:
                continue
            quoted_names.update(_QUOTED_RE.findall(text))

    golden_slugs: set[str] = set()
    if golden_dir.exists():
        golden_slugs = {child.name for child in golden_dir.iterdir() if child.is_dir()}

    return TestedIndex(quoted_names=frozenset(quoted_names), golden_slugs=frozenset(golden_slugs))


def _printings_dir(worktree_dir: Path) -> Path:
    return worktree_dir / "src" / "magic_cards_model" / "data" / "printings"


def _printing_stems(printings_dir: Path) -> dict[str, str]:
    """`{stem: card name}` for every printing at base - the ratchet's pool.
    The stem (filename without `.json`), not the name, is the tracked
    identity, since it is stable across an oracle-text edit that changes
    what `card["name"]` even is for a renamed/merged printing."""
    out: dict[str, str] = {}
    if not printings_dir.exists():
        return out
    for path in sorted(printings_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        out[path.stem] = data.get("name", path.stem)
    return out


#: The worker subprocess run once per worktree. It imports *that worktree's*
#: `magic_cards_model` (via `REGRESSION_GUARD_SRC_DIR` on `sys.path`,
#: propagated through the environment rather than argv, so a spawned
#: `ProcessPoolExecutor` worker - which re-imports this file fresh rather
#: than inheriting the parent's already-mutated `sys.path` - sees the same
#: value) and *that worktree's* `scripts/card_coverage.py`, whose
#: `classify_card_raw` classifies the oracle cards (falling back to
#: `card_support` directly for a commit that predates it). Two job kinds go
#: through one process pool: a pool printing (by stem; `"removed"` when the
#: printing does not exist in this worktree) and an oracle card (by index
#: into the shared `REGRESSION_GUARD_ORACLE_FILE`, written once by the
#: parent from its single bulk parse). A card whose classification raises
#: is `"error"` - never crashes the sweep.
_CLASSIFY_WORKER_SCRIPT = """
import importlib.util
import json
import os
import sys
from pathlib import Path

_SRC_DIR = os.environ["REGRESSION_GUARD_SRC_DIR"]
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from magic_cards_model.models.card import Card  # noqa: E402
from magic_cards_model.support import card_support  # noqa: E402


def _load_classifier():
    path = Path(os.environ["REGRESSION_GUARD_WORKTREE"]) / "scripts" / "card_coverage.py"
    if not path.exists():
        return None, "card_support"
    spec = importlib.util.spec_from_file_location("_regression_guard_card_coverage", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses look their module up here
    spec.loader.exec_module(module)
    classify = getattr(module, "classify_card_raw", None)
    if classify is None:
        return None, "card_support"
    return classify, "card_coverage.classify_card_raw"


_CLASSIFY_RAW, CLASSIFIER = _load_classifier()
_ORACLE_CARDS = None


def _oracle_cards():
    global _ORACLE_CARDS
    if _ORACLE_CARDS is None:
        _ORACLE_CARDS = json.loads(Path(os.environ["REGRESSION_GUARD_ORACLE_FILE"]).read_text())
    return _ORACLE_CARDS


def _status_of(raw):
    try:
        if _CLASSIFY_RAW is not None:
            return _CLASSIFY_RAW(raw).status
        return card_support(Card.model_validate(raw)).status
    except Exception:
        return "error"


def _classify_job(job):
    kind, value = job
    if kind == "oracle":
        return _status_of(_oracle_cards()[value])
    if value is None:
        return "removed"
    try:
        data = json.loads(Path(value).read_text())
        return card_support(Card.model_validate(data)).status
    except Exception:
        return "error"


def main():
    printings_dir = Path(os.environ["REGRESSION_GUARD_PRINTINGS_DIR"])
    stems = json.loads(Path(os.environ["REGRESSION_GUARD_STEMS_FILE"]).read_text())
    oracle_count = int(os.environ.get("REGRESSION_GUARD_ORACLE_COUNT", "0"))
    workers = int(os.environ.get("REGRESSION_GUARD_WORKERS", "1"))

    jobs = [
        ("pool", str(p) if (p := printings_dir / f"{stem}.json").exists() else None)
        for stem in stems
    ]
    jobs.extend(("oracle", i) for i in range(oracle_count))

    if workers <= 1 or len(jobs) < 2:
        statuses = [_classify_job(job) for job in jobs]
    else:
        from concurrent.futures import ProcessPoolExecutor

        chunksize = max(1, len(jobs) // (workers * 8))
        with ProcessPoolExecutor(max_workers=workers) as pool:
            statuses = list(pool.map(_classify_job, jobs, chunksize=chunksize))

    print(
        json.dumps(
            {
                "pool": dict(zip(stems, statuses[: len(stems)])),
                "oracle": statuses[len(stems) :],
                "classifier": CLASSIFIER,
            }
        )
    )


if __name__ == "__main__":
    main()
"""


def _classify_worktree(
    worktree_dir: Path,
    stems: list[str],
    *,
    workers: int,
    tmp_dir: Path,
    oracle_file: Path | None = None,
    oracle_count: int = 0,
) -> dict[str, Any]:
    """`{"pool": {stem: status}, "oracle": [status per oracle card],
    "classifier": ...}` for one worktree."""
    script_path = tmp_dir / f"classify-worker-{uuid.uuid4().hex}.py"
    script_path.write_text(_CLASSIFY_WORKER_SCRIPT)
    stems_file = tmp_dir / f"stems-{uuid.uuid4().hex}.json"
    stems_file.write_text(json.dumps(stems))

    env = dict(os.environ)
    env["REGRESSION_GUARD_SRC_DIR"] = str(worktree_dir / "src")
    env["REGRESSION_GUARD_WORKTREE"] = str(worktree_dir)
    env["REGRESSION_GUARD_PRINTINGS_DIR"] = str(_printings_dir(worktree_dir))
    env["REGRESSION_GUARD_STEMS_FILE"] = str(stems_file)
    env["REGRESSION_GUARD_WORKERS"] = str(max(1, workers))
    env["REGRESSION_GUARD_ORACLE_COUNT"] = str(oracle_count)
    if oracle_file is not None:
        env["REGRESSION_GUARD_ORACLE_FILE"] = str(oracle_file)

    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=worktree_dir,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RegressionGuardError(
            f"card-status classification failed in {worktree_dir}: {result.stderr}"
        )
    return json.loads(result.stdout)


#: Worst first. `removed` (the printing no longer exists at all) is worse
#: than `error` (it exists but the engine could not classify it), which is
#: worse than every real `SupportStatus`.
_STATUS_SEVERITY: dict[str, int] = {
    "removed": -2,
    "error": -1,
    "silent": 0,
    "unaudited": 1,
    "notice": 2,
    "handled": 3,
}


def _severity(status: str) -> int:
    return _STATUS_SEVERITY.get(status, -1)


def ratchet_offenders(
    stems: dict[str, str],
    base_status: dict[str, str],
    head_status: dict[str, str],
    base_index: TestedIndex,
    head_index: TestedIndex,
) -> list[dict]:
    offenders: list[dict] = []
    for stem, name in stems.items():
        b_status = base_status.get(stem, "removed")
        h_status = head_status.get(stem, "removed")
        b_tested = base_index.is_tested(name)
        h_tested = head_index.is_tested(name)

        reasons = []
        if _severity(h_status) < _severity(b_status):
            reasons.append(f"status regressed: {b_status} -> {h_status}")
        if b_tested and not h_tested:
            reasons.append("tested at base, untested at head")

        if reasons:
            offenders.append(
                {
                    "source": "pool",
                    "stem": stem,
                    "name": name,
                    "base_status": b_status,
                    "head_status": h_status,
                    "base_tested": b_tested,
                    "head_tested": h_tested,
                    "reasons": reasons,
                }
            )
    return offenders


#: How many cards each informational list (`oracle_changed`, `new_cards`,
#: `improved_vs_baseline`, `left_pool`) shows; its `count` is always exact.
_REPORT_SAMPLE = 50

_BASELINE_HINT = (
    "the engine now beats the committed baseline: run `mise run coverage:baseline` "
    "and commit docs/card_coverage/support-baseline.json to raise the floor"
)


def _capped(entries: list[dict], **extra: Any) -> dict:
    return {
        "count": len(entries),
        "cards": entries[:_REPORT_SAMPLE],
        "truncated": len(entries) > _REPORT_SAMPLE,
        **extra,
    }


def oracle_ratchet(
    cards: list[tuple[str, str, str]],
    base_status: dict[str, str],
    head_status: dict[str, str],
    baseline: dict[str, dict] | None,
) -> dict:
    """The oracle-wide ratchet over `cards` (`(oracle_id, name, text_hash)`
    for every target-format card in the bulk). A card fails when head reads
    it worse than base, or worse than the committed `baseline` floor while
    its oracle text is unchanged. A floor drop on a card Scryfall re-worded
    (`text_hash` differs) is reported under `oracle_changed`, not failed; a
    card the baseline has never seen is reported under `new_cards`; one the
    engine now beats the baseline on under `improved_vs_baseline`, with a
    hint to regenerate it; a baseline card no longer in the bulk's target
    formats under `left_pool`."""
    offenders: list[dict] = []
    oracle_changed: list[dict] = []
    new_cards: list[dict] = []
    improved: list[dict] = []
    seen: set[str] = set()
    for key, name, text_hash in cards:
        seen.add(key)
        b_status = base_status.get(key, "error")
        h_status = head_status.get(key, "error")
        reasons = []
        if _severity(h_status) < _severity(b_status):
            reasons.append(f"status regressed: {b_status} -> {h_status}")
        entry = baseline.get(key) if baseline is not None else None
        floor = entry["status"] if entry is not None else None
        card = {"oracle_id": key, "name": name, "head_status": h_status}
        if baseline is not None and entry is None:
            new_cards.append(card)
        elif entry is not None:
            if _severity(h_status) > _severity(floor):
                improved.append({**card, "baseline_status": floor})
            elif _severity(h_status) < _severity(floor):
                if entry.get("text_hash") != text_hash:
                    oracle_changed.append({**card, "baseline_status": floor})
                else:
                    reasons.append(f"below baseline floor: {floor} -> {h_status}")
        if reasons:
            offenders.append(
                {
                    "source": "oracle",
                    "oracle_id": key,
                    "name": name,
                    "base_status": b_status,
                    "head_status": h_status,
                    "baseline_status": floor,
                    "reasons": reasons,
                }
            )
    left_pool = [
        {"oracle_id": key, "name": entry.get("name"), "baseline_status": entry.get("status")}
        for key, entry in (baseline or {}).items()
        if key not in seen
    ]
    return {
        "offenders": offenders,
        "oracle_changed": _capped(oracle_changed),
        "new_cards": _capped(new_cards),
        "improved_vs_baseline": _capped(improved, hint=_BASELINE_HINT),
        "left_pool": _capped(left_pool),
    }


_CARD_COVERAGE_MODULE: Any = None


def _card_coverage() -> Any:
    """This checkout's own `scripts/card_coverage.py` - the one bulk loader,
    target-format filter, text hash and baseline parser, so the guard reads
    the bulk exactly the way the coverage report and baseline writer do."""
    global _CARD_COVERAGE_MODULE
    if _CARD_COVERAGE_MODULE is None:
        path = Path(__file__).resolve().parent / "card_coverage.py"
        spec = importlib.util.spec_from_file_location("_regression_guard_cc", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module  # dataclasses look their module up here
        spec.loader.exec_module(module)
        _CARD_COVERAGE_MODULE = module
    return _CARD_COVERAGE_MODULE


BULK_ENV = "REGRESSION_GUARD_BULK"
_FAIL_CLOSED = "the ratchet fails closed rather than skip the oracle-wide check"


def resolve_bulk_path(repo: Path, override: Path | str | None, *, download: Any = None) -> Path:
    """The oracle-cards bulk to ratchet over: `override` when given (it must
    exist), else `<repo>/.scryfall-cache/oracle-cards.jsonl.gz` (the
    coverage report's own gitignored cache), downloading it there first if
    it is missing. Any failure raises - never a silent pass."""
    if override is not None:
        path = Path(override)
        if not path.exists():
            raise RegressionGuardError(f"oracle bulk {path} does not exist; {_FAIL_CLOSED}")
        return path
    cache_dir = repo / ".scryfall-cache"
    cached = cache_dir / "oracle-cards.jsonl.gz"
    if cached.exists():
        return cached
    if download is None:
        download = _card_coverage().download_bulk
    try:
        return Path(download("oracle-cards", cache_dir=cache_dir))
    except Exception as exc:  # noqa: BLE001 - any download failure is fail-closed
        raise RegressionGuardError(
            f"no cached oracle bulk at {cached} and downloading it failed ({exc}); "
            f"{_FAIL_CLOSED}. Pass --bulk <path> or set {BULK_ENV} to a local "
            "oracle-cards file."
        ) from exc


def _add_worktree(repo: Path, sha: str, dest: Path) -> None:
    _run_git(repo, "worktree", "add", "--detach", str(dest), sha)


def _remove_worktree(repo: Path, dest: Path) -> None:
    _run_git(repo, "worktree", "remove", "--force", str(dest), check=False)


#: The suite-lock budget: two full gates share the machine, six workers each.
MAX_WORKERS = 6


def run_ratchet(
    repo: Path,
    base: str,
    head: str,
    *,
    workers: int | None = None,
    bulk_path: Path | str | None = None,
) -> dict:
    """Classify every printing that exists at base, and every
    Modern/Pioneer/Standard-legal card in the oracle-cards bulk, with base's
    and head's own engine code in isolated worktrees, and report offenders
    (`source` `pool` or `oracle`). Raises `RegressionGuardError` when `repo`
    is not the engine (no `magic_cards_model.support` module) - the ratchet
    is engine-only - or when the bulk cannot be read (fail closed)."""
    if not (repo / "src" / "magic_cards_model" / "support.py").exists():
        raise RegressionGuardError(
            f"--ratchet is engine-only: no src/magic_cards_model/support.py under {repo}"
        )

    started = time.monotonic()
    base_sha = resolve_sha(repo, base)
    head_sha = resolve_sha(repo, head)
    workers = max(1, min(workers or os.cpu_count() or 1, MAX_WORKERS))

    cc = _card_coverage()
    bulk = resolve_bulk_path(repo, bulk_path if bulk_path is not None else os.environ.get(BULK_ENV))
    try:
        oracle_pool = cc.target_format_pool(cc.load_bulk_json(bulk))
    except Exception as exc:  # noqa: BLE001 - an unreadable bulk is fail-closed
        raise RegressionGuardError(
            f"could not read oracle bulk {bulk} ({exc}); {_FAIL_CLOSED}"
        ) from exc
    if not oracle_pool:
        raise RegressionGuardError(
            f"oracle bulk {bulk} holds no Modern/Pioneer/Standard-legal card; {_FAIL_CLOSED}"
        )
    oracle_cards = [
        (cc.card_key(raw), raw.get("name", ""), cc.card_text_hash(raw)) for raw in oracle_pool
    ]
    baseline_text = file_at(repo, base_sha, cc.SUPPORT_BASELINE_PATH)
    baseline = cc.parse_support_baseline(baseline_text) if baseline_text is not None else None
    bulk_seconds = time.monotonic() - started

    with tempfile.TemporaryDirectory(prefix="regression-guard-") as tmp:
        tmp_path = Path(tmp)
        oracle_file = tmp_path / "oracle-pool.json"
        oracle_file.write_text(json.dumps(oracle_pool))
        base_dir = tmp_path / "base"
        head_dir = tmp_path / "head"
        _add_worktree(repo, base_sha, base_dir)
        _add_worktree(repo, head_sha, head_dir)
        try:
            stems = _printing_stems(_printings_dir(base_dir))
            base_index = build_tested_index(base_dir)
            head_index = build_tested_index(head_dir)
            sides = {}
            side_seconds = {}
            for side, side_dir in (("base", base_dir), ("head", head_dir)):
                t0 = time.monotonic()
                sides[side] = _classify_worktree(
                    side_dir,
                    list(stems),
                    workers=workers,
                    tmp_dir=tmp_path,
                    oracle_file=oracle_file,
                    oracle_count=len(oracle_pool),
                )
                side_seconds[side] = round(time.monotonic() - t0, 1)
        finally:
            _remove_worktree(repo, base_dir)
            _remove_worktree(repo, head_dir)

    keys = [key for key, _name, _hash in oracle_cards]
    oracle = oracle_ratchet(
        oracle_cards,
        dict(zip(keys, sides["base"]["oracle"], strict=True)),
        dict(zip(keys, sides["head"]["oracle"], strict=True)),
        baseline,
    )
    offenders = ratchet_offenders(
        stems, sides["base"]["pool"], sides["head"]["pool"], base_index, head_index
    )
    return {
        "base": base_sha,
        "head": head_sha,
        "bulk": str(bulk),
        "cards_checked": len(stems),
        "cards_checked_oracle": len(oracle_cards),
        "classifier": {"base": sides["base"]["classifier"], "head": sides["head"]["classifier"]},
        "baseline": {
            "path": cc.SUPPORT_BASELINE_PATH,
            "present": baseline is not None,
            "cards": len(baseline or {}),
        },
        "offenders": offenders + oracle.pop("offenders"),
        **oracle,
        "workers": workers,
        "timing_seconds": {
            "bulk": round(bulk_seconds, 1),
            **side_seconds,
            "total": round(time.monotonic() - started, 1),
        },
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--repo", required=True, type=Path, help="path to the repo to check")
    parser.add_argument("--base", required=True, help="base ref/sha to diff from")
    parser.add_argument("--head", default="HEAD", help="head ref/sha to diff to (default HEAD)")
    parser.add_argument(
        "--ratchet",
        action="store_true",
        help="also run the card-status ratchet (engine repos only)",
    )
    parser.add_argument(
        "--bulk",
        type=Path,
        default=None,
        help=(
            f"oracle-cards bulk for the ratchet (default: ${BULK_ENV}, else "
            "<repo>/.scryfall-cache/oracle-cards.jsonl.gz, downloaded if missing)"
        ),
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help=f"classification workers per side (default and cap: {MAX_WORKERS})",
    )
    args = parser.parse_args(argv)

    repo = args.repo.resolve()
    exit_code = 0
    result: dict[str, Any] = {}

    try:
        findings = protected_test_report(repo, args.base, args.head)
    except subprocess.CalledProcessError as exc:
        print(f"regression_guard: git diff failed: {exc.stderr}", file=sys.stderr)
        return 2
    result["protected_test_findings"] = findings
    if findings:
        exit_code = 1

    if args.ratchet:
        try:
            ratchet_result = run_ratchet(
                repo, args.base, args.head, workers=args.workers, bulk_path=args.bulk
            )
        except RegressionGuardError as exc:
            print(f"regression_guard: {exc}", file=sys.stderr)
            return 2
        result["ratchet"] = ratchet_result
        if ratchet_result["offenders"]:
            exit_code = 1

    print(json.dumps(result, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
