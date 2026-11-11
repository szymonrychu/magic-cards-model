"""`uv run python -m scripts.ironsmith_compare <command>` - see docs/ironsmith-compare.md.

    doctor              check the ironsmith checkout against the pin, and the tools
    build               build ironsmith's status binaries (--behaviour: its WASM engine too)
    collect coverage    feed our card pool to ironsmith's status binaries, normalise the result
    collect behaviour   replay MCM goldens in ironsmith's scenario runner, normalise the result
    compare             join with MCM's verdicts; write report.json, report.md, worklist.csv

Only `build` and `collect` start ironsmith, always as separate processes on the user's
machine; `compare` reads our own normalised files and always exits 0.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

from scripts import card_coverage
from scripts.ironsmith_compare import checkout, coverage, report, scenarios
from scripts.ironsmith_compare.compare import FORMATS, build_rows, legal_formats

ROOT = Path(__file__).resolve().parents[2]
GOLDEN_DIR = ROOT / "tests" / "golden"
DEFAULT_IRONSMITH = Path(os.environ.get("IRONSMITH_DIR", ROOT.parent / "ironsmith"))
COVERAGE_JSONL = "ironsmith-coverage.jsonl"
BEHAVIOUR_JSONL = "ironsmith-behaviour.jsonl"
STATUS_BINARIES = ("sync_registry_db", "sync_card_status_db")
STATUSES = {"silent": {"silent"}, "notice": {"notice"}, "both": {"silent", "notice"}}


def _clone_help(pin: checkout.Pin, path: Path) -> str:
    return "\n".join(
        [
            "Clone ironsmith once, without its UI images, at the pin:",
            f"  git clone --filter=blob:none --no-checkout {pin.repo} {path}",
            f"  git -C {path} sparse-checkout set --no-cone '/*' '!/web/ui/public/'",
            f"  git -C {path} checkout {pin.commit}",
        ]
    )


def _sha(path: Path, fallback: str) -> str:
    if not path.is_dir():
        return fallback
    try:
        return checkout.head_sha(path)
    except subprocess.CalledProcessError:
        return fallback


def _out_dir(args: argparse.Namespace, pin: checkout.Pin) -> Path:
    if args.out:
        return args.out
    iron, mcm = _sha(args.ironsmith, pin.commit), _sha(ROOT, "unknown")
    return ROOT / ".ironsmith-compare" / f"{iron[:12]}-{mcm[:12]}"


def _checked(args: argparse.Namespace, pin: checkout.Pin) -> bool:
    problems = checkout.check_checkout(args.ironsmith, pin)
    for problem in problems:
        print(f"ironsmith-compare: {problem}", file=sys.stderr)
    if problems and not args.allow_unpinned:
        print("refusing to run ironsmith (pass --allow-unpinned to override)", file=sys.stderr)
        return False
    return True


def _pool(args: argparse.Namespace) -> list[dict]:
    bulk = args.bulk or card_coverage.download_bulk(
        "oracle-cards", cache_dir=ROOT / card_coverage.DEFAULT_CACHE_DIR
    )
    return card_coverage.target_format_pool(card_coverage.load_bulk_json(bulk))


def cmd_doctor(args: argparse.Namespace, pin: checkout.Pin) -> int:
    print(f"pin: {pin.repo} @ {pin.commit} ({pin.date}), licence elected: {pin.licence}")
    problems = checkout.check_checkout(args.ironsmith, pin)
    for problem in problems:
        print(f"problem: {problem}", file=sys.stderr)
    licence = args.ironsmith / "LICENSE.md"
    if licence.is_file() and pin.licence not in licence.read_text(errors="replace"):
        print(f"warning: {licence} no longer names {pin.licence}; re-check the terms")
    if problems:
        print(_clone_help(pin, args.ironsmith))
        return 1
    print(f"ok: {args.ironsmith} is an unmodified checkout at the pin")
    return 0


def cmd_build(args: argparse.Namespace, pin: checkout.Pin) -> int:
    if not _checked(args, pin):
        return 2
    log = _out_dir(args, pin) / "logs" / "build.log"
    commands = [pin.coverage_build] + ([pin.behaviour_build] if args.behaviour else [])
    for argv in commands:
        code = checkout.run(argv, cwd=args.ironsmith, log=log)
        if code:
            print(f"build failed ({code}): {' '.join(argv)}; see {log}", file=sys.stderr)
            return code
    print(f"built; log {log}")
    return 0


def cmd_collect_coverage(args: argparse.Namespace, pin: checkout.Pin) -> int:
    if not _checked(args, pin):
        return 2
    binaries = args.ironsmith / "target" / "release"
    missing = [name for name in STATUS_BINARIES if not (binaries / name).exists()]
    if missing:
        print(f"missing {', '.join(missing)} in {binaries}; run build first", file=sys.stderr)
        return 2
    out = _out_dir(args, pin)
    cards, db = out / "cards.json", out / "ironsmith-status.sqlite3"
    log = out / "logs" / "coverage.log"
    coverage.write_cards_json(_pool(args), cards)
    for name in STATUS_BINARIES:
        argv = [str(binaries / name), "--cards", str(cards), "--db-path", str(db)]
        code = checkout.run(argv, cwd=args.ironsmith, log=log)
        if code:
            print(f"{name} failed ({code}); see {log}", file=sys.stderr)
            return code
    rows = coverage.read_status_db(db)
    coverage.write_jsonl(rows, out / COVERAGE_JSONL)
    print(f"{len(rows)} ironsmith rows -> {out / COVERAGE_JSONL}")
    return 0


def cmd_collect_behaviour(args: argparse.Namespace, pin: checkout.Pin) -> int:
    if not _checked(args, pin):
        return 2
    runner = args.ironsmith / "scripts" / "mage-port-runner.mjs"
    if not runner.is_file():
        print(f"{runner} not found; is this an ironsmith checkout?", file=sys.stderr)
        return 2
    out = _out_dir(args, pin)
    specs, junit, log = out / "behaviour", out / "behaviour.junit.xml", out / "logs/behaviour.log"
    paths = sorted(GOLDEN_DIR.glob("*/*.json"))
    manifest = scenarios.write_specs(paths, specs, runner)
    junit.unlink(missing_ok=True)
    argv = [
        "node",
        "--test",
        "--test-isolation=none",
        f"--test-concurrency={args.concurrency}",
        "--test-reporter=junit",
        f"--test-reporter-destination={junit}",
        *(str(shim) for shim in sorted(specs.glob("*.test.mjs"))),
    ]
    # Failing scenarios make node exit non-zero; the JUnit file is the result.
    checkout.run(argv, cwd=args.ironsmith, log=log)
    if not junit.is_file():
        print(f"no JUnit report at {junit}; see {log}", file=sys.stderr)
        return 2
    cards = {scenarios.golden_id(p): json.loads(p.read_text())["card"] for p in paths}
    rows = scenarios.behaviour_rows(manifest, scenarios.parse_junit(junit.read_text()), cards)
    coverage.write_jsonl(rows, out / BEHAVIOUR_JSONL)
    replayed = len(manifest["translated"])
    print(f"{len(rows)} goldens ({replayed} replayed) -> {out / BEHAVIOUR_JSONL}")
    return 0


def _mcm_verdicts(args: argparse.Namespace, pool: list[dict], wanted: set[str]) -> dict:
    """MCM's verdict per oracle id: the committed baseline's status (or, with --live,
    nothing), then a live classification, with its failing clause, of every card in the
    format whose baseline status the worklist wants or that the baseline lacks."""
    verdicts: dict[str, dict] = {}
    if not args.live:
        baseline = card_coverage.parse_support_baseline(args.baseline.read_text())
        verdicts = {
            key: {"status": entry["status"], "clause": "", "reason": ""}
            for key, entry in baseline.items()
        }
    todo = [
        raw
        for raw in pool
        if args.format in legal_formats(raw)
        and verdicts.get(card_coverage.card_key(raw), {}).get("status", "?") in wanted | {"?"}
    ]
    results = card_coverage.classify_many(todo, workers=args.workers)
    for raw, result in zip(todo, results, strict=True):
        verdicts[card_coverage.card_key(raw)] = {
            "status": result.status,
            "clause": result.clause_text,
            "reason": result.reason,
        }
    return verdicts


def latest_collected(base: Path, iron_sha: str) -> Path | None:
    """The most recently collected out dir under `base` for this ironsmith sha, so a
    commit to MCM between `collect` and `compare` does not lose the collected data."""
    dirs = [d for d in base.glob(f"{iron_sha[:12]}-*") if (d / COVERAGE_JSONL).is_file()]
    return max(dirs, key=lambda d: (d / COVERAGE_JSONL).stat().st_mtime, default=None)


def cmd_compare(args: argparse.Namespace, pin: checkout.Pin) -> int:
    out = _out_dir(args, pin)
    wanted = STATUSES[args.status]
    pool = _pool(args)
    source = out
    if not args.out and not (out / COVERAGE_JSONL).is_file():
        source = latest_collected(out.parent, _sha(args.ironsmith, pin.commit)) or out
        if source != out:
            print(f"note: reading collected data from {source}", file=sys.stderr)
    iron_path, behaviour_path = source / COVERAGE_JSONL, source / BEHAVIOUR_JSONL
    if not iron_path.is_file():
        print(f"note: no {iron_path}; every card's ironsmith status is unknown", file=sys.stderr)
    iron = coverage.read_jsonl(iron_path) if iron_path.is_file() else []
    behaviour = coverage.read_jsonl(behaviour_path) if behaviour_path.is_file() else []
    metagame = card_coverage.load_metagame(args.metagame)
    verdicts = _mcm_verdicts(args, pool, wanted)
    comparison = build_rows(pool, verdicts, iron, metagame, fmt=args.format, statuses=wanted)
    meta = {
        "date": datetime.date.today().isoformat(),
        "iron_sha": _sha(args.ironsmith, pin.commit),
        "mcm_sha": _sha(ROOT, "unknown"),
        "pin": pin.commit,
        "licence": pin.licence,
        "format": args.format,
        "statuses": sorted(wanted),
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(report.render_json(comparison, behaviour, meta))
    (out / "report.md").write_text(report.render_md(comparison, behaviour, meta))
    (out / "worklist.csv").write_text(report.render_csv(comparison.worklist))
    print(f"quadrants {comparison.quadrants}; worklist {len(comparison.worklist)} cards")
    print(f"wrote {out / 'report.md'}, report.json, worklist.csv")
    return 0


def _parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--ironsmith",
        type=Path,
        default=DEFAULT_IRONSMITH,
        help="ironsmith checkout (env IRONSMITH_DIR, default ../ironsmith)",
    )
    common.add_argument(
        "--out", type=Path, help="out dir (default .ironsmith-compare/<iron12>-<mcm12>)"
    )
    common.add_argument(
        "--allow-unpinned",
        action="store_true",
        help="run against a checkout that is not the clean pin",
    )
    common.add_argument(
        "--bulk", type=Path, help="Scryfall oracle-cards file (default: cached download)"
    )
    parser = argparse.ArgumentParser(
        prog="ironsmith_compare",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", parents=[common]).set_defaults(func=cmd_doctor)
    build = sub.add_parser("build", parents=[common])
    build.add_argument("--behaviour", action="store_true", help="also build the WASM engine")
    build.set_defaults(func=cmd_build)
    collect = sub.add_parser("collect").add_subparsers(dest="what", required=True)
    collect.add_parser("coverage", parents=[common]).set_defaults(func=cmd_collect_coverage)
    behaviour = collect.add_parser("behaviour", parents=[common])
    behaviour.add_argument("--concurrency", type=int, default=8)
    behaviour.set_defaults(func=cmd_collect_behaviour)
    compare = sub.add_parser("compare", parents=[common])
    compare.add_argument("--format", choices=FORMATS, default="modern")
    compare.add_argument("--status", choices=sorted(STATUSES), default="silent")
    compare.add_argument(
        "--live", action="store_true", help="classify every card now, not from the baseline"
    )
    compare.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    compare.add_argument(
        "--baseline", type=Path, default=ROOT / card_coverage.SUPPORT_BASELINE_PATH
    )
    compare.add_argument(
        "--metagame",
        type=Path,
        default=ROOT / card_coverage.DEFAULT_OUT_DIR / card_coverage.DEFAULT_METAGAME_FILENAME,
    )
    compare.set_defaults(func=cmd_compare)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    return args.func(args, checkout.load_pin())


if __name__ == "__main__":
    sys.exit(main())
