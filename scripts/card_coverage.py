#!/usr/bin/env python
"""Per-expansion card-coverage report generator for the card-coverage campaign.

    mise exec -- uv run python scripts/card_coverage.py                # full run
    mise exec -- uv run python scripts/card_coverage.py --set fdn      # one set (spoilers included)
    mise exec -- uv run python scripts/card_coverage.py --refresh-bulk # force re-download bulk data

Reads Scryfall's `oracle-cards` bulk data (cached under a gitignored
directory), classifies every Modern/Pioneer/Standard-legal card's first
printing with the engine's own support oracle
(`magic_cards_model.support.card_support`), and writes one
`docs/card_coverage/<NNN>-<code>/status.md` per Modern-legal expansion plus
a campaign-wide `docs/card_coverage/plan.md`. See the three
`.claude/skills/card-coverage-*` skills for how this is driven.

Deterministic: given the same bulk-data snapshot and the same engine, two
runs produce byte-identical output, except for the `## Notes` sections
(both files) and the campaign-order `state` column (`plan.md`), which are
read back out of the existing files and carried forward untouched - a
regeneration never clobbers a human's notes or a round's progress mark.

Expansion numbering is a stable, zero-padded chronological index: the
oldest Modern-legal set is `001`, and a set's number never changes once
assigned. A brand-new release is - by construction - newer than every set
already numbered, so it always gets the next free number; nothing ever
renumbers (`read_existing_numbers` / `assign_numbers`).
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Iterable, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).parent.parent))

from magic_cards_model.models.card import Card  # noqa: E402
from magic_cards_model.support import card_support  # noqa: E402

HEADERS = {"User-Agent": "magic-cards-model-card-coverage/0.1", "Accept": "*/*"}
BULK_DATA_INDEX_URL = "https://api.scryfall.com/bulk-data"
SEARCH_URL = "https://api.scryfall.com/cards/search"
DEFAULT_CACHE_DIR = Path(".scryfall-cache")
DEFAULT_OUT_DIR = Path("docs/card_coverage")
DEFAULT_PRINTINGS_DIR = Path("src/magic_cards_model/data/printings")
DEFAULT_TESTS_DIR = Path("tests")
DEFAULT_GOLDEN_DIR = Path("tests/golden")
DEFAULT_DECKS_DIRS = [
    Path("../magic-cards-model-api/decks"),
    Path("../../mtg-decks"),
]

#: A set/printing this tooling never counts a card into. `layout` catches
#: tokens/emblems minted as their own Scryfall objects; `set_type` catches
#: the handful of sets that are pure reprint art with no gameplay meaning.
_EXCLUDED_LAYOUTS = {"token", "double_faced_token", "emblem"}
_EXCLUDED_SET_TYPES = {"art_series"}

#: Round states seeded from the campaign already in flight
#: (`campaign_rounds.json` / `STATE.md`, C00 metagame, C01 hob, C02 msh) the
#: first time a plan.md is generated with nothing to read a state back from.
SEED_ROUND_STATES: dict[str, str] = {
    "hob": "done",
    "msh": "in-progress",
}

SupportStatus = Literal["handled", "unaudited", "notice", "silent", "error"]
Bucket = Literal["full", "partial", "not_tested", "not_working"]

_BUCKET_OF: dict[tuple[SupportStatus, bool], Bucket] = {}
for _status in ("handled",):
    _BUCKET_OF[(_status, True)] = "full"
    _BUCKET_OF[(_status, False)] = "not_tested"
for _status in ("unaudited",):
    _BUCKET_OF[(_status, True)] = "partial"
    _BUCKET_OF[(_status, False)] = "partial"
for _status in ("notice", "silent", "error"):
    _BUCKET_OF[(_status, True)] = "not_working"
    _BUCKET_OF[(_status, False)] = "not_working"


def bucket_of(status: str, tested: bool) -> Bucket:
    """full = handled+tested; partial = unaudited (either way); not_tested =
    handled+untested; not_working = silent/notice/error."""
    return _BUCKET_OF[(status, tested)]


# ---------------------------------------------------------------------------
# Naming
# ---------------------------------------------------------------------------


def slug(name: str) -> str:
    """A card's golden-directory slug (`tests/golden/__init__.py`'s own
    convention): lowercase words joined by hyphens, apostrophes dropped."""
    return "-".join(re.findall(r"[a-z0-9]+", name.lower().replace("'", "")))


def front_name(name: str) -> str:
    """The name before ` // ` on a multifaced card, unchanged otherwise."""
    return name.split("//")[0].strip()


def format_expansion_dir(number: int, code: str) -> str:
    return f"{number:03d}-{code}"


# ---------------------------------------------------------------------------
# Eligibility / first-printing selection
# ---------------------------------------------------------------------------


def is_eligible_printing(raw: dict) -> bool:
    """Whether a raw Scryfall card dict counts toward "first printed in a
    set" at all: not a token/emblem/art-series object, and not digital-only.

    Digital-only is `digital: true` (an Alchemy-rebalanced or Arena-exclusive
    card) or a `games` list that never mentions `"paper"` - Scryfall's bulk
    data carries both digital and paper printings in the same file, and
    neither kind was ever released as a physical card this campaign covers.
    """
    if raw.get("layout") in _EXCLUDED_LAYOUTS:
        return False
    if raw.get("set_type") in _EXCLUDED_SET_TYPES:
        return False
    if raw.get("digital"):
        return False
    games = raw.get("games")
    return not (games is not None and "paper" not in games)


def select_first_printing(printings: Sequence[dict]) -> dict | None:
    """The printing a card "belongs to" for coverage purposes: the eligible
    printing with the earliest `released_at`, ties broken by set code so the
    choice is deterministic when two sets shipped the same day."""
    eligible = [p for p in printings if is_eligible_printing(p)]
    if not eligible:
        return None
    return min(
        eligible, key=lambda p: (p.get("released_at") or "9999-99-99", p.get("set") or "zzzzzz")
    )


def group_first_printings(cards: Iterable[dict]) -> dict[str, dict]:
    """Every card's first printing, keyed by oracle id (or by name for the
    rare card printed with none - a reversible card's back face, mostly)."""
    by_key: dict[str, list[dict]] = {}
    for raw in cards:
        key = raw.get("oracle_id") or raw.get("name")
        by_key.setdefault(key, []).append(raw)
    result: dict[str, dict] = {}
    for key, printings in by_key.items():
        first = select_first_printing(printings)
        if first is not None:
            result[key] = first
    return result


#: The printing-identity fields a `default-cards` first-printing overrides on
#: an `oracle-cards` entry - everything else (oracle text, keywords, mana
#: cost, legalities...) is identical across a card's printings, so only
#: "which set/when" ever needs correcting.
_FIRST_PRINTING_FIELDS = ("set", "set_name", "set_type", "released_at", "digital", "games")


def merge_first_printing_metadata(
    oracle_cards: Iterable[dict], first_printings_by_key: dict[str, dict]
) -> list[dict]:
    """`oracle-cards` gives one row per card with its current oracle text,
    keywords and legalities - but Scryfall's own pick of *which* printing
    that row represents is "the most recognizable", which is very often the
    newest reprint, not the card's original set. Left uncorrected, that
    misattributes almost every reprinted card in the game to whatever set
    reprinted it most recently, which breaks the whole point of a
    newest-to-oldest per-expansion campaign.

    This corrects it: for every oracle-cards row whose oracle id (or name)
    is present in `first_printings_by_key` (`group_first_printings` run over
    Scryfall's `default-cards` bulk data - every printing, not just one),
    the row's own printing-identity fields are replaced with the true first
    eligible printing's. A row `default-cards` has no record of at all (rare
    in practice) is left exactly as `oracle-cards` gave it - the graceful
    degradation `download_bulk("default-cards", ...)` being optional exists
    for.
    """
    merged: list[dict] = []
    for raw in oracle_cards:
        key = raw.get("oracle_id") or raw.get("name")
        first = first_printings_by_key.get(key)
        if first is None:
            merged.append(raw)
            continue
        overridden = dict(raw)
        for field_name in _FIRST_PRINTING_FIELDS:
            if field_name in first:
                overridden[field_name] = first[field_name]
        merged.append(overridden)
    return merged


# ---------------------------------------------------------------------------
# Set indexing, ordering, numbering
# ---------------------------------------------------------------------------


@dataclass
class SetMeta:
    code: str
    name: str
    release_date: str
    cards: list[dict] = field(default_factory=list)


def build_set_index(first_printings: Iterable[dict]) -> dict[str, SetMeta]:
    """Group first-printed cards by set code. A set's release date is the
    earliest `released_at` seen among its own first-printed cards (all
    normally share one, but a spoiled/staggered set may not yet)."""
    index: dict[str, SetMeta] = {}
    for raw in first_printings:
        code = raw["set"]
        meta = index.get(code)
        if meta is None:
            meta = SetMeta(
                code=code,
                name=raw.get("set_name") or code,
                release_date=raw.get("released_at") or "",
            )
            index[code] = meta
        elif raw.get("released_at") and (
            not meta.release_date or raw["released_at"] < meta.release_date
        ):
            meta.release_date = raw["released_at"]
        meta.cards.append(raw)
    return index


def _in_target_formats(raw: dict) -> bool:
    legalities = raw.get("legalities") or {}
    return any(legalities.get(fmt) != "not_legal" for fmt in ("standard", "pioneer", "modern"))


def modern_legal_codes(index: dict[str, SetMeta]) -> set[str]:
    """Every set with at least one first-printed card that is Modern-legal -
    the "expansions available in modern" the campaign covers."""
    return {
        code
        for code, meta in index.items()
        if any((c.get("legalities") or {}).get("modern") != "not_legal" for c in meta.cards)
    }


def order_newest_first(index: dict[str, SetMeta], codes: Iterable[str]) -> list[str]:
    return sorted(codes, key=lambda code: (index[code].release_date, code), reverse=True)


_DIR_RE = re.compile(r"^(\d+)-([a-z0-9]+)$")


def read_existing_numbers(out_dir: Path) -> dict[str, int]:
    """The numbering already committed, read straight off
    `docs/card_coverage/<NNN>-<code>/` folder names - the only source of
    truth for "nothing renumbers", since a fresh run's own chronological
    sort would otherwise have no memory of a prior run's assignment."""
    numbers: dict[str, int] = {}
    if not out_dir.exists():
        return numbers
    for child in out_dir.iterdir():
        if not child.is_dir():
            continue
        match = _DIR_RE.match(child.name)
        if match:
            numbers[match.group(2)] = int(match.group(1))
    return numbers


def assign_numbers(ordered_oldest_first: list[str], existing: dict[str, int]) -> dict[str, int]:
    """Stable zero-padded chronological numbering: every code already in
    `existing` keeps its number; every other code gets the next free number,
    in oldest-to-newest order among the newly-seen codes."""
    numbers = dict(existing)
    next_number = max(existing.values(), default=0) + 1
    for code in ordered_oldest_first:
        if code in numbers:
            continue
        numbers[code] = next_number
        next_number += 1
    return numbers


# ---------------------------------------------------------------------------
# Tested-card detection
# ---------------------------------------------------------------------------

_QUOTED_RE = re.compile(r"[\"']([^\"'\n]{2,80})[\"']")


@dataclass(frozen=True)
class TestedIndex:
    printings_names: frozenset[str]
    quoted_names: frozenset[str]
    golden_slugs: frozenset[str]

    def is_tested(self, name: str) -> bool:
        for candidate in (name, front_name(name)):
            if candidate in self.printings_names or candidate in self.quoted_names:
                return True
            if slug(candidate) in self.golden_slugs:
                return True
        return False


def build_tested_index(*, printings_dir: Path, tests_dir: Path, golden_dir: Path) -> TestedIndex:
    """`tested` means: in `src/magic_cards_model/data/printings/`, or the
    card's name is referenced (as a quoted string literal) somewhere under
    `tests/`, or it has a golden directory under `tests/golden/`."""
    printings_names: set[str] = set()
    if printings_dir.exists():
        for path in printings_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            name = data.get("name")
            if name:
                printings_names.add(name)
                printings_names.add(front_name(name))

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

    return TestedIndex(
        printings_names=frozenset(printings_names),
        quoted_names=frozenset(quoted_names),
        golden_slugs=frozenset(golden_slugs),
    )


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClassificationResult:
    name: str
    status: SupportStatus
    clause_kind: str
    clause_text: str
    reason: str
    error: bool


def classify_card_raw(raw: dict) -> ClassificationResult:
    """`raw` (a Scryfall card dict) run through the engine's support oracle,
    reduced to the worst clause. Never raises: a card the engine's own `Card`
    model rejects, or that `card_support` itself blows up on, comes back as
    `status="error"` rather than aborting the whole sweep - a coverage report
    that stops at the first malformed record would be worse than useless on
    22,000 cards."""
    name = raw.get("name", "<unknown>")
    try:
        card = Card.model_validate(raw)
    except Exception as exc:  # noqa: BLE001 - a coverage report must not die on one bad record
        return ClassificationResult(
            name=name,
            status="error",
            clause_kind="",
            clause_text="",
            reason=f"failed to parse card: {exc}",
            error=True,
        )
    try:
        support = card_support(card)
    except Exception as exc:  # noqa: BLE001 - see above
        return ClassificationResult(
            name=card.name,
            status="error",
            clause_kind="",
            clause_text="",
            reason=f"card_support raised: {exc}",
            error=True,
        )
    clause = next((c for c in support.clauses if c.status == support.status), None)
    return ClassificationResult(
        name=support.name,
        status=support.status,
        clause_kind=clause.kind if clause else "",
        clause_text=clause.text if clause else "",
        reason=clause.reason if clause else "",
        error=False,
    )


def classify_many(cards: Sequence[dict], *, workers: int = 1) -> list[ClassificationResult]:
    """`classify_card_raw` over every card, in order. `workers > 1` runs a
    process pool - classification is CPU-bound pure-Python parsing, and a
    single process on ~22k cards is the slow path this exists to avoid."""
    if workers <= 1 or len(cards) < 2:
        return [classify_card_raw(raw) for raw in cards]
    chunksize = max(1, len(cards) // (workers * 8))
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(classify_card_raw, cards, chunksize=chunksize))


# ---------------------------------------------------------------------------
# Missing-mechanics clustering
# ---------------------------------------------------------------------------

_CLUSTER_STRIP_RE = re.compile(r"\{[^}]*\}|\"[^\"]*\"|'[^']*'|\d+")
_CARD_NAME_STOPWORD_RE = re.compile(r"[^a-z ]+")


@dataclass(frozen=True)
class MechanicCluster:
    signature: str
    label: str
    count: int
    cards: tuple[str, ...]


def _clause_signature(text: str) -> str:
    """A clustering key for one failing clause's printed text: mana costs,
    quoted sub-clauses and numbers stripped (the parts of a template that
    vary card to card), lowercased, collapsed to its first few words - two
    clauses sharing that signature are (almost always) the same template."""
    stripped = _CLUSTER_STRIP_RE.sub(" ", text.lower())
    stripped = _CARD_NAME_STOPWORD_RE.sub(" ", stripped)
    words = stripped.split()
    return " ".join(words[:5])


def cluster_missing_mechanics(
    entries: Sequence[tuple[str, str, str, str, str]],
) -> list[MechanicCluster]:
    """Cluster failing clauses (`(card_name, status, clause_kind,
    clause_text, reason)` tuples - status/kind/reason are carried for the
    caller's own use, not part of the clustering key) by shared wording. One
    cluster is one probable missing mechanic; `label` is a representative
    printed clause."""
    by_signature: dict[str, list[tuple[str, str]]] = {}
    for card_name, _status, _kind, clause_text, _reason in entries:
        signature = _clause_signature(clause_text)
        if not signature:
            signature = f"__unsignatured__:{card_name}"
        by_signature.setdefault(signature, []).append((card_name, clause_text))
    clusters: list[MechanicCluster] = []
    for signature, rows in by_signature.items():
        cards = tuple(dict.fromkeys(name for name, _ in rows))  # unique, order-preserving
        label = max((text for _, text in rows), key=len) if rows else ""
        clusters.append(
            MechanicCluster(signature=signature, label=label, count=len(cards), cards=cards)
        )
    clusters.sort(key=lambda c: (-c.count, c.signature))
    return clusters


# ---------------------------------------------------------------------------
# Notes / round-state extraction (regeneration must not clobber these)
# ---------------------------------------------------------------------------

_SECTION_RE_TEMPLATE = r"^## {heading}\s*\n(.*?)(?=\n## |\Z)"


def extract_section(markdown: str, heading: str) -> str | None:
    """The verbatim body of a `## <heading>` section (up to but not
    including the next `## ` heading), or `None` if the section is not
    present. Leading/trailing blank lines are trimmed; interior formatting is
    untouched."""
    pattern = re.compile(
        _SECTION_RE_TEMPLATE.format(heading=re.escape(heading)), re.DOTALL | re.MULTILINE
    )
    match = pattern.search(markdown)
    if not match:
        return None
    body = match.group(1).strip("\n")
    return body if body else None


_ROUND_ROW_RE = re.compile(
    r"\|\s*\d+\s*\|\s*\[([a-z0-9]+)\]\([^)]*\)[^|]*\|[^|]*\|[^|]*\|\s*([a-z-]+)\s*\|"
)


def extract_round_states(markdown: str) -> dict[str, str]:
    """Every `(code -> state)` pair out of the campaign-order table's `State`
    column, so a regeneration carries a round's progress mark forward
    instead of resetting it to `todo`."""
    states: dict[str, str] = {}
    for match in _ROUND_ROW_RE.finditer(markdown):
        states[match.group(1)] = match.group(2)
    return states


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _format_bucket_table(counts: dict[Bucket, int], total: int) -> str:
    lines = ["| Bucket | Count | % |", "|---|---|---|"]
    labels: dict[Bucket, str] = {
        "full": "Full (handled + tested)",
        "partial": "Partial (unaudited)",
        "not_tested": "Not tested (handled, untested)",
        "not_working": "Not working (silent / notice / error)",
    }
    for bucket in ("full", "partial", "not_tested", "not_working"):
        count = counts.get(bucket, 0)
        pct = f"{(100.0 * count / total):.1f}%" if total else "0.0%"
        lines.append(f"| {labels[bucket]} | {count} | {pct} |")
    return "\n".join(lines)


def render_status_md(
    meta: SetMeta,
    *,
    number: int,
    classifications: dict[str, ClassificationResult],
    tested: dict[str, bool],
    existing_notes: str | None,
) -> str:
    """One expansion's coverage report. `classifications`/`tested` are keyed
    by card name and must cover every target-format-legal card in `meta`."""
    target_cards = [c for c in meta.cards if _in_target_formats(c)]
    legal_counts = {"standard": 0, "pioneer": 0, "modern": 0}
    for c in target_cards:
        legalities = c.get("legalities") or {}
        for fmt in legal_counts:
            if legalities.get(fmt) not in (None, "not_legal"):
                legal_counts[fmt] += 1

    bucket_counts: dict[Bucket, int] = {}
    rows_not_full: list[tuple[str, ClassificationResult]] = []
    rows_full: list[str] = []
    cluster_entries: list[tuple[str, str, str, str, str]] = []
    for c in sorted(target_cards, key=lambda c: c["name"]):
        name = c["name"]
        result = classifications.get(name)
        if result is None:
            continue
        is_tested = tested.get(name, False)
        bucket = bucket_of(result.status, is_tested)
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
        if bucket == "full":
            rows_full.append(name)
        else:
            rows_not_full.append((name, result))
            if result.status in ("silent", "notice", "unaudited"):
                cluster_entries.append(
                    (name, result.status, result.clause_kind, result.clause_text, result.reason)
                )

    total = len(target_cards)
    lines: list[str] = []
    lines.append(f"# {meta.name} ({meta.code})")
    lines.append("")
    lines.append(f"- Expansion: {number:03d}")
    lines.append(f"- Set code: `{meta.code}`")
    lines.append(f"- Release date: {meta.release_date or 'unknown'}")
    lines.append(f"- Cards in scope (Modern/Pioneer/Standard-legal): {total}")
    lines.append("")
    lines.append("## Legality")
    lines.append("")
    lines.append("| Format | Legal cards |")
    lines.append("|---|---|")
    lines.append(f"| Modern | {legal_counts['modern']} |")
    lines.append(f"| Pioneer | {legal_counts['pioneer']} |")
    lines.append(f"| Standard | {legal_counts['standard']} |")
    lines.append("")
    lines.append("## Coverage")
    lines.append("")
    lines.append(_format_bucket_table(bucket_counts, total))
    lines.append("")
    lines.append("## Cards needing work")
    lines.append("")
    if rows_not_full:
        lines.append("| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |")
        lines.append("|---|---|---|---|---|---|")
        severity = {"silent": 0, "error": 0, "notice": 1, "unaudited": 2}
        for name, result in sorted(
            rows_not_full, key=lambda nr: (severity.get(nr[1].status, 3), nr[0])
        ):
            c = next(c for c in target_cards if c["name"] == name)
            legalities = c.get("legalities") or {}
            leg = "/".join(
                "Y" if legalities.get(fmt) not in (None, "not_legal") else "-"
                for fmt in ("modern", "pioneer", "standard")
            )
            clause = (result.clause_text or "").replace("|", "\\|").replace("\n", " ")[:160]
            reason = (result.reason or "").replace("|", "\\|")
            bucket = bucket_of(result.status, tested.get(name, False))
            lines.append(f"| {name} | {result.status} | {clause} | {reason} | {leg} | {bucket} |")
    else:
        lines.append("None - every card in scope is fully supported.")
    lines.append("")
    lines.append("## Fully supported")
    lines.append("")
    lines.append("<details>")
    lines.append(f"<summary>{len(rows_full)} cards</summary>")
    lines.append("")
    for name in rows_full:
        lines.append(f"- {name}")
    lines.append("")
    lines.append("</details>")
    lines.append("")
    lines.append("## Missing mechanics")
    lines.append("")
    clusters = cluster_missing_mechanics(cluster_entries)
    if clusters:
        lines.append("| Mechanic (representative clause) | Cards | Count |")
        lines.append("|---|---|---|")
        for cluster in clusters:
            card_list = ", ".join(cluster.cards)
            clause = cluster.label.replace("|", "\\|").replace("\n", " ")[:160]
            lines.append(f"| {clause} | {card_list} | {cluster.count} |")
    else:
        lines.append("None.")
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append(existing_notes if existing_notes else "")
    return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class PlanRow:
    number: int
    code: str
    name: str
    release_date: str
    total: int
    full: int
    state: str


def render_plan_md(
    *,
    rows: list[PlanRow],
    round0_cards: list[str],
    missing_mechanics: list[MechanicCluster],
    existing_notes: str | None,
    existing_done: str | None,
) -> str:
    # Newest to oldest by release date - the campaign order, independent of
    # (but normally consistent with) the stable chronological `number`.
    newest_first = sorted(rows, key=lambda r: (r.release_date, r.number), reverse=True)

    total_cards = sum(r.total for r in rows)
    total_full = sum(r.full for r in rows)
    overall_pct = f"{(100.0 * total_full / total_cards):.1f}%" if total_cards else "0.0%"

    lines: list[str] = []
    lines.append("# Card coverage campaign plan")
    lines.append("")
    lines.append(
        "Every Modern-legal expansion, newest to oldest. Each row links to its "
        "`status.md` (`docs/card_coverage/<NNN>-<code>/status.md`)."
    )
    lines.append("")
    lines.append("## Overall coverage")
    lines.append("")
    lines.append("| Expansions | Cards in scope | Fully supported | % |")
    lines.append("|---|---|---|---|")
    lines.append(f"| {len(rows)} | {total_cards} | {total_full} | {overall_pct} |")
    lines.append("")
    lines.append("## Campaign order")
    lines.append("")
    lines.append("| Round | Set | Release date | Cards | Full | State |")
    lines.append("|---|---|---|---|---|---|")
    round0_state = "in-progress" if round0_cards else "done"
    round0_count = len(round0_cards)
    lines.append(
        f"| Round 0 | metagame decks ({round0_count} cards not full) "
        f"| - | {round0_count} | - | {round0_state} |"
    )
    for row in newest_first:
        dir_name = format_expansion_dir(row.number, row.code)
        link = f"[{row.code}]({dir_name}/status.md)"
        lines.append(
            f"| {row.number} | {link} - {row.name} | {row.release_date} "
            f"| {row.total} | {row.full} | {row.state} |"
        )
    lines.append("")
    lines.append("## Missing mechanics")
    lines.append("")
    if missing_mechanics:
        lines.append("| Mechanic (representative clause) | Cards affected | Count |")
        lines.append("|---|---|---|")
        for cluster in missing_mechanics:
            clause = cluster.label.replace("|", "\\|").replace("\n", " ")[:160]
            card_list = ", ".join(cluster.cards[:12])
            more = " ..." if len(cluster.cards) > 12 else ""
            lines.append(f"| {clause} | {card_list}{more} | {cluster.count} |")
    else:
        lines.append("None.")
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append(existing_notes if existing_notes else "")
    lines.append("")
    lines.append("## Done")
    lines.append("")
    lines.append(existing_done if existing_done else "")
    lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


# ---------------------------------------------------------------------------
# Deck parsing (Round 0)
# ---------------------------------------------------------------------------

_DECK_LINE_RE = re.compile(r"^\s*(?:\d+\s*x?\s+)?(.+?)\s*$")
_DECK_IGNORE_PREFIXES = ("//", "#", "sideboard", "commander", "deck")


def parse_deck_file(path: Path) -> set[str]:
    """Card names out of a plain-text decklist: `"4 Lightning Bolt"` or bare
    `"Lightning Bolt"` per line, blank lines and comment/section headers
    ignored."""
    names: set[str] = set()
    try:
        text = path.read_text(errors="ignore")
    except OSError:
        return names
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lowered = line.lower()
        if any(lowered.startswith(prefix) for prefix in _DECK_IGNORE_PREFIXES) and not re.match(
            r"^\d", line
        ):
            continue
        match = _DECK_LINE_RE.match(line)
        if not match:
            continue
        name = match.group(1).strip()
        if name:
            names.add(name)
    return names


def cards_from_deck_dirs(decks_dirs: Iterable[Path]) -> set[str]:
    names: set[str] = set()
    for directory in decks_dirs:
        if not directory.exists():
            continue
        for path in directory.glob("*.txt"):
            names.update(parse_deck_file(path))
    return names


# ---------------------------------------------------------------------------
# Bulk-data fetching
# ---------------------------------------------------------------------------


def _http_get_json(url: str) -> dict:
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read())


def download_bulk(kind: str, *, cache_dir: Path, force: bool = False) -> Path:
    """The cached path of Scryfall's `kind` bulk-data file (`oracle-cards` or
    `default-cards`), downloading it first if it is not already cached or
    `force` is set.

    Scryfall serves bulk data as gzip-compressed JSON Lines
    (`jsonl_download_uri`) under a `type` that spells the kind with
    underscores (`oracle_cards`); `kind` itself stays hyphenated on this
    tool's own CLI/cache-file naming since that is how Scryfall's docs and
    this project's own scripts (`add_card.py`) usually spell it. The cached
    file is kept gzip-compressed on disk - `load_bulk_json` decompresses it
    on read - since the uncompressed oracle-cards file alone is tens of
    megabytes.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    dest = cache_dir / f"{kind}.jsonl.gz"
    if dest.exists() and not force:
        return dest
    scryfall_type = kind.replace("-", "_")
    index = _http_get_json(BULK_DATA_INDEX_URL)
    entry = next((e for e in index.get("data", []) if e.get("type") == scryfall_type), None)
    if entry is None:
        raise ValueError(f"no bulk-data entry of type {scryfall_type!r}")
    request = urllib.request.Request(entry["jsonl_download_uri"], headers=HEADERS)
    with urllib.request.urlopen(request, timeout=600) as response:
        dest.write_bytes(response.read())
    return dest


def load_bulk_json(path: Path) -> list[dict]:
    """Every card object out of a cached bulk-data file. Handles both the
    real Scryfall shape (gzip-compressed JSON Lines, one card object per
    line) and a plain JSON array (what a hand-written test fixture, or an
    older cache file, holds) - sniffed from the file's own gzip magic bytes
    rather than its extension, so either can be pointed at directly."""
    raw = path.read_bytes()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    text = raw.decode("utf-8")
    stripped = text.lstrip()
    if stripped.startswith("["):
        return json.loads(text)
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def fetch_set_cards(code: str) -> list[dict]:
    """Every card (including unreleased spoilers) of set `code`, via the
    Scryfall search endpoint, paginated."""
    cards: list[dict] = []
    url = f"{SEARCH_URL}?q=e%3A{code}&unique=cards"
    while url:
        payload = _http_get_json(url)
        cards.extend(payload.get("data", []))
        url = payload.get("next_page") if payload.get("has_more") else None
    return cards


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


@dataclass
class GenerateResult:
    set_count: int
    card_count: int


def _classifications_and_tested_for_meta(
    meta: SetMeta, tested_index: TestedIndex, workers: int
) -> tuple[dict[str, ClassificationResult], dict[str, bool]]:
    target_cards = [c for c in meta.cards if _in_target_formats(c)]
    results = classify_many(target_cards, workers=workers)
    classifications = {r.name: r for r in results}
    tested = {c["name"]: tested_index.is_tested(c["name"]) for c in target_cards}
    return classifications, tested


def _write_set_status(
    meta: SetMeta,
    number: int,
    out_dir: Path,
    tested_index: TestedIndex,
    workers: int,
) -> tuple[int, int]:
    classifications, tested = _classifications_and_tested_for_meta(meta, tested_index, workers)
    return _write_set_status_from_classifications(meta, number, out_dir, classifications, tested)


def _write_set_status_from_classifications(
    meta: SetMeta,
    number: int,
    out_dir: Path,
    classifications: dict[str, ClassificationResult],
    tested: dict[str, bool],
) -> tuple[int, int]:
    """Renders and writes one set's `status.md` from already-computed
    classifications, so a full run's single big classification pass
    (`generate_all`) never re-classifies a set's cards a second time just to
    write its file."""
    dir_name = format_expansion_dir(number, meta.code)
    set_dir = out_dir / dir_name
    set_dir.mkdir(parents=True, exist_ok=True)
    status_path = set_dir / "status.md"
    existing_notes = None
    if status_path.exists():
        existing_notes = extract_section(status_path.read_text(), "Notes")

    text = render_status_md(
        meta,
        number=number,
        classifications=classifications,
        tested=tested,
        existing_notes=existing_notes,
    )
    status_path.write_text(text)

    total = len(classifications)
    full = sum(
        1
        for name, r in classifications.items()
        if bucket_of(r.status, tested.get(name, False)) == "full"
    )
    return total, full


def generate_all(
    *,
    bulk_path: Path,
    out_dir: Path,
    printings_dir: Path,
    tests_dir: Path,
    golden_dir: Path,
    decks_dirs: Iterable[Path],
    workers: int = 1,
    default_bulk_path: Path | None = None,
) -> GenerateResult:
    """The full run: every Modern-legal expansion's `status.md` plus
    `plan.md`, from a cached bulk-data JSON file already on disk.

    `bulk_path` is `oracle-cards` (one row per card, current oracle text and
    legalities). `default_bulk_path`, when given, is `default-cards` (every
    printing) - used only to correct which set each card's row is
    attributed to, via `merge_first_printing_metadata`: without it, a
    reprinted card is attributed to whatever set `oracle-cards` happened to
    pick as its "most recognizable" printing (usually the newest), which is
    almost never the set it was first printed in.
    """
    raw_cards = load_bulk_json(bulk_path)
    if default_bulk_path is not None:
        default_cards = load_bulk_json(default_bulk_path)
        first_printings_by_key = group_first_printings(default_cards)
        raw_cards = merge_first_printing_metadata(raw_cards, first_printings_by_key)
    first_printings = group_first_printings(raw_cards)
    index = build_set_index(first_printings.values())
    modern_codes = modern_legal_codes(index)
    existing_numbers = read_existing_numbers(out_dir)
    ordered_oldest_first = sorted(modern_codes, key=lambda code: (index[code].release_date, code))
    numbers = assign_numbers(ordered_oldest_first, existing_numbers)

    tested_index = build_tested_index(
        printings_dir=printings_dir, tests_dir=tests_dir, golden_dir=golden_dir
    )

    plan_path = out_dir / "plan.md"
    existing_plan_text = plan_path.read_text() if plan_path.exists() else ""
    round_states = extract_round_states(existing_plan_text) if existing_plan_text else {}
    existing_plan_notes = (
        extract_section(existing_plan_text, "Notes") if existing_plan_text else None
    )
    existing_plan_done = extract_section(existing_plan_text, "Done") if existing_plan_text else None

    # One classification pass across every set's target-format-legal cards,
    # through a single process pool - not one pool per set (200+ of them on
    # a full run) and not classified twice for the status.md write and the
    # cross-set missing-mechanics rollup.
    ordered_codes = list(modern_codes)
    all_target_cards: list[dict] = []
    card_set_codes: list[str] = []
    for code in ordered_codes:
        for raw in index[code].cards:
            if _in_target_formats(raw):
                all_target_cards.append(raw)
                card_set_codes.append(code)
    all_results = classify_many(all_target_cards, workers=workers)

    classifications_by_set: dict[str, dict[str, ClassificationResult]] = {
        code: {} for code in ordered_codes
    }
    tested_by_set: dict[str, dict[str, bool]] = {code: {} for code in ordered_codes}
    for code, raw, result in zip(card_set_codes, all_target_cards, all_results, strict=True):
        classifications_by_set[code][result.name] = result
        tested_by_set[code][raw["name"]] = tested_index.is_tested(raw["name"])

    rows: list[PlanRow] = []
    all_cluster_entries: list[tuple[str, str, str, str, str]] = []
    total_card_count = 0
    for code in modern_codes:
        meta = index[code]
        number = numbers[code]
        classifications = classifications_by_set[code]
        tested = tested_by_set[code]
        total, full = _write_set_status_from_classifications(
            meta, number, out_dir, classifications, tested
        )
        total_card_count += total
        state = round_states.get(code) or SEED_ROUND_STATES.get(code, "todo")
        rows.append(
            PlanRow(
                number=number,
                code=code,
                name=meta.name,
                release_date=meta.release_date,
                total=total,
                full=full,
                state=state,
            )
        )
        for result in classifications.values():
            if result.status in ("silent", "notice", "unaudited"):
                all_cluster_entries.append(
                    (
                        result.name,
                        result.status,
                        result.clause_kind,
                        result.clause_text,
                        result.reason,
                    )
                )

    missing_mechanics = cluster_missing_mechanics(all_cluster_entries)

    round0_cards = sorted(cards_from_deck_dirs(decks_dirs))
    plan_text = render_plan_md(
        rows=rows,
        round0_cards=round0_cards,
        missing_mechanics=missing_mechanics,
        existing_notes=existing_plan_notes,
        existing_done=existing_plan_done,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(plan_text)

    return GenerateResult(set_count=len(rows), card_count=total_card_count)


def generate_one_set(
    *,
    code: str,
    raw_cards: list[dict],
    out_dir: Path,
    printings_dir: Path,
    tests_dir: Path,
    golden_dir: Path,
    workers: int = 1,
) -> tuple[int, int]:
    """The `--set` fast path: classify and write just one set's `status.md`
    (fetched fresh, spoilers included), assigning it a number if it does not
    already have one, without touching any other set's file."""
    first_printings = group_first_printings(raw_cards)
    index = build_set_index(v for v in first_printings.values() if v["set"] == code)
    if code not in index:
        raise ValueError(f"no eligible first-printed cards found for set {code!r}")
    meta = index[code]
    existing_numbers = read_existing_numbers(out_dir)
    numbers = assign_numbers([code], existing_numbers)
    tested_index = build_tested_index(
        printings_dir=printings_dir, tests_dir=tests_dir, golden_dir=golden_dir
    )
    return _write_set_status(meta, numbers[code], out_dir, tested_index, workers)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--printings-dir", type=Path, default=DEFAULT_PRINTINGS_DIR)
    parser.add_argument("--tests-dir", type=Path, default=DEFAULT_TESTS_DIR)
    parser.add_argument("--golden-dir", type=Path, default=DEFAULT_GOLDEN_DIR)
    parser.add_argument("--decks-dir", action="append", type=Path, default=None, help="repeatable")
    parser.add_argument(
        "--set", dest="set_code", default=None, help="fetch and regenerate just this one set"
    )
    parser.add_argument(
        "--refresh-bulk", action="store_true", help="force re-download of the bulk-data snapshot"
    )
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument(
        "--no-first-print-detection",
        action="store_true",
        help=(
            "skip fetching default-cards (every printing) for accurate first-print "
            "set attribution; falls back to oracle-cards' own (usually most-recent) "
            "printing pick, which is faster but attributes reprints to the wrong set"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    decks_dirs = args.decks_dir if args.decks_dir is not None else DEFAULT_DECKS_DIRS

    if args.set_code:
        raw_cards = fetch_set_cards(args.set_code)
        total, full = generate_one_set(
            code=args.set_code,
            raw_cards=raw_cards,
            out_dir=args.out_dir,
            printings_dir=args.printings_dir,
            tests_dir=args.tests_dir,
            golden_dir=args.golden_dir,
            workers=args.workers,
        )
        print(f"{args.set_code}: {total} cards in scope, {full} fully supported")
        return 0

    bulk_path = download_bulk("oracle-cards", cache_dir=args.cache_dir, force=args.refresh_bulk)
    default_bulk_path = None
    if not args.no_first_print_detection:
        default_bulk_path = download_bulk(
            "default-cards", cache_dir=args.cache_dir, force=args.refresh_bulk
        )
    result = generate_all(
        bulk_path=bulk_path,
        default_bulk_path=default_bulk_path,
        out_dir=args.out_dir,
        printings_dir=args.printings_dir,
        tests_dir=args.tests_dir,
        golden_dir=args.golden_dir,
        decks_dirs=decks_dirs,
        workers=args.workers,
    )
    print(f"{result.set_count} expansions, {result.card_count} cards in scope")
    return 0


if __name__ == "__main__":
    sys.exit(main())
