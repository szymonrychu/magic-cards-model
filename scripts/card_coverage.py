#!/usr/bin/env python
"""Per-expansion card-coverage report generator for the card-coverage campaign.

    mise exec -- uv run python scripts/card_coverage.py                # full run
    mise exec -- uv run python scripts/card_coverage.py --set fdn      # one set (spoilers included)
    mise exec -- uv run python scripts/card_coverage.py --refresh-bulk # force re-download bulk data
    mise run coverage:baseline                                         # just support-baseline.json

Reads Scryfall's `oracle-cards` bulk data (cached under a gitignored
directory), classifies every Modern/Pioneer/Standard-legal card's first
printing with the engine's own support oracle
(`magic_cards_model.support.card_support`), and writes one
`docs/card_coverage/<NNN>-<code>/status.md` per Modern-legal expansion plus
a campaign-wide `docs/card_coverage/plan.md`. See the three
`.claude/skills/card-coverage-*` skills for how this is driven.

The same run writes `docs/card_coverage/support-baseline.json`: one line per
target-format card (`oracle_id`, `name`, `status`, oracle-text+keywords
`text_hash`), the committed floor `scripts/regression_guard.py --ratchet`
holds every one of those cards to. `--baseline-only` writes just that file.

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
import hashlib
import json
import re
import shutil
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
#: The committed per-card support floor `scripts/regression_guard.py
#: --ratchet` holds every target-format card to (see `render_support_baseline`).
SUPPORT_BASELINE_FILENAME = "support-baseline.json"
SUPPORT_BASELINE_PATH = f"{DEFAULT_OUT_DIR.as_posix()}/{SUPPORT_BASELINE_FILENAME}"
DEFAULT_PRINTINGS_DIR = Path("src/magic_cards_model/data/printings")
DEFAULT_TESTS_DIR = Path("tests")
DEFAULT_GOLDEN_DIR = Path("tests/golden")
DEFAULT_DECKS_DIRS = [
    Path("../magic-cards-model-api/decks"),
    Path("../../../mtg-decks/decks"),
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


#: Scryfall `set_type` values that mark a set as promo-like rather than a
#: card's genuine gameplay home - a WPN/Prerelease/Pro-Tour promo, a
#: memorabilia object, or a token set.
_PROMO_LIKE_SET_TYPES = {"promo", "memorabilia", "token"}


def is_promo_like_printing(raw: dict) -> bool:
    """Whether a printing is promo-like for first-printing-attribution
    purposes: a promo/memorabilia/token `set_type`, or flagged `promo: true`
    or `digital: true` on the printing itself. A card whose earliest
    printing is promo-like but that also has a genuine (non-promo-like,
    non-Commander-like) printing is homed in that genuine printing, never
    the promo - see `select_first_printing`."""
    return (
        raw.get("set_type") in _PROMO_LIKE_SET_TYPES
        or bool(raw.get("promo"))
        or bool(raw.get("digital"))
    )


#: Scryfall `set_type` values that mark a set as a Commander preconstructed-
#: deck product (e.g. msc, lcc). Owner instruction 2026-09-26: Commander
#: products must never be a card's preferred home, and must never become a
#: campaign row (`modern_legal_codes`) - unlike promo, which is still
#: allowed to be a card's home when nothing else exists at all.
_COMMANDER_SET_TYPES = {"commander"}


def is_commander_like_printing(raw: dict) -> bool:
    """Whether a printing is a Commander-product printing for first-printing-
    attribution purposes: `set_type == "commander"` (an ordinary Commander
    precon), or the set's own name contains "Commander" - Scryfall's own
    `set_type` is not consistent for the Commander Legends draft-innovation
    line (`clb`'s `set_type` is `draft_innovation`, not `commander`) or for
    Commander-dedicated Masters sets (`cmm`'s is `masters`), so `set_type`
    alone under-detects the owner's named examples (msc, lcc, **clb**). A
    set's declared name is a much more reliable "is this a Commander
    product" signal than its `set_type` bucket, and does not risk catching
    an unrelated `draft_innovation`/`masters` set (Conspiracy, Battlebond,
    Modern Masters, ... none of those have "Commander" in their name).

    A card whose earliest printing is Commander-like but that also has a
    genuine (non-Commander, non-promo) printing is homed in that genuine
    printing, never the Commander one - see `select_first_printing`."""
    if raw.get("set_type") in _COMMANDER_SET_TYPES:
        return True
    return "commander" in (raw.get("set_name") or "").lower()


def select_first_printing(printings: Sequence[dict]) -> dict | None:
    """The printing a card "belongs to" for coverage purposes: the eligible,
    genuine (non-promo-like, non-Commander-like) printing with the earliest
    `released_at` - a prerelease, promo, or Commander-product printing
    sharing or preceding the main expansion's release date must not win the
    card's home away from that expansion. When a card has no genuine
    printing at all, the earliest eligible promo-like printing wins over a
    Commander-like one; only when *nothing* else is eligible at all (a WPN-,
    Pro-Tour-, or Commander-exclusive card) does the earliest eligible
    printing of any kind win - Commander is the least-preferred tier, never
    the most. Ties are broken by set code so the choice is deterministic
    when two sets shipped the same day."""
    eligible = [p for p in printings if is_eligible_printing(p)]
    if not eligible:
        return None
    genuine = [
        p for p in eligible if not is_promo_like_printing(p) and not is_commander_like_printing(p)
    ]
    if genuine:
        pool = genuine
    else:
        non_commander = [p for p in eligible if not is_commander_like_printing(p)]
        pool = non_commander if non_commander else eligible
    return min(pool, key=lambda p: (p.get("released_at") or "9999-99-99", p.get("set") or "zzzzzz"))


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


def _is_commander_set(meta: SetMeta) -> bool:
    """Whether `meta` is a Commander product, by `is_commander_like_printing`
    on one of its own cards (a set's `set_type`/`set_name` are uniform
    across its cards). A defense-in-depth backstop alongside
    `select_first_printing`'s Commander-last preference: even in the
    hypothetical case where a card's only eligible printing at all is a
    Commander one, that product still never earns a campaign row - owner
    instruction 2026-09-26, "Commander products must never be a campaign
    row" has no stated exception."""
    return bool(meta.cards) and is_commander_like_printing(meta.cards[0])


def modern_legal_codes(index: dict[str, SetMeta]) -> set[str]:
    """Every set with at least one first-printed card that is Modern-legal -
    the "expansions available in modern" the campaign covers - excluding
    Commander products outright (`_is_commander_set`)."""
    return {
        code
        for code, meta in index.items()
        if not _is_commander_set(meta)
        and any((c.get("legalities") or {}).get("modern") != "not_legal" for c in meta.cards)
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
        if not child.is_dir() or child.name == ROUND0_DIR_NAME:
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


def find_orphaned_set_dirs(out_dir: Path, modern_codes: set[str]) -> dict[str, Path]:
    """Existing `docs/card_coverage/<NNN>-<code>/` directories whose code is
    no longer in this run's `modern_codes` - every one of that set's cards
    got reattributed elsewhere (typically `select_first_printing`'s promo
    preference homing them at the real expansion instead), so the set no
    longer has any first-printed card in scope and its stale directory would
    otherwise keep reporting numbers nobody can act on."""
    orphans: dict[str, Path] = {}
    if not out_dir.exists():
        return orphans
    for child in out_dir.iterdir():
        if not child.is_dir():
            continue
        if child.name == ROUND0_DIR_NAME:
            # Round 0's own directory (000-metagame) - never a numbered
            # expansion, never subject to set-orphan pruning.
            continue
        match = _DIR_RE.match(child.name)
        if not match:
            continue
        code = match.group(2)
        if code not in modern_codes:
            orphans[code] = child
    return orphans


def prune_orphaned_sets(
    out_dir: Path, modern_codes: set[str]
) -> tuple[list[str], list[tuple[str, str]]]:
    """Deletes every orphaned set directory (`find_orphaned_set_dirs`) - but
    never one whose `status.md` carries a non-empty `## Notes` section: a
    human wrote something there, so that directory is left on disk
    untouched, and its `(code, notes)` pair is returned instead for the
    caller to fold into `plan.md`'s own `## Notes`
    (`merge_pruned_notes_into_plan`) so the record survives even though the
    set no longer appears anywhere else in the campaign.

    Returns `(pruned_codes, kept_with_notes)`, both sorted by code for
    deterministic output."""
    pruned: list[str] = []
    kept_with_notes: list[tuple[str, str]] = []
    for code, path in sorted(find_orphaned_set_dirs(out_dir, modern_codes).items()):
        status_path = path / "status.md"
        notes = extract_section(status_path.read_text(), "Notes") if status_path.exists() else None
        if notes:
            kept_with_notes.append((code, notes))
            continue
        shutil.rmtree(path)
        pruned.append(code)
    return pruned, kept_with_notes


def merge_pruned_notes_into_plan(
    existing_notes: str | None, kept_with_notes: list[tuple[str, str]]
) -> str | None:
    """`existing_notes` (plan.md's own `## Notes` body, already read back
    for the caller to carry forward) with one tagged block appended per
    `(code, notes)` pair `prune_orphaned_sets` chose to keep rather than
    delete. Idempotent across repeated runs: a code whose tagged block is
    already present in `existing_notes` (because a prior run already
    recovered it, and the directory - still holding notes - is still
    orphaned) is not appended again."""
    notes = existing_notes or ""
    for code, set_notes in kept_with_notes:
        marker = f"### Pruned set `{code}`"
        if marker in notes:
            continue
        block = f"{marker}\n\n{set_notes}"
        notes = f"{notes}\n\n{block}" if notes.strip() else block
    return notes if notes.strip() else None


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
# Support baseline
# ---------------------------------------------------------------------------


def card_key(raw: dict) -> str:
    """A card's identity across printings and bulk snapshots: its oracle id,
    or its name for the rare card Scryfall gives none."""
    return raw.get("oracle_id") or raw.get("name") or "<unknown>"


def card_text_hash(raw: dict) -> str:
    """A short digest of what the support oracle reads off a card: its
    oracle text (every face's, for a multi-face card) and its keywords. A
    change here means Scryfall re-worded the card, so a status drop against
    the committed baseline is an oracle change, not an engine regression."""
    payload = {
        "oracle_text": raw.get("oracle_text"),
        "faces": [face.get("oracle_text") for face in raw.get("card_faces") or []],
        "keywords": sorted(raw.get("keywords") or []),
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8"))
    return digest.hexdigest()[:16]


def target_format_pool(raw_cards: Iterable[dict]) -> list[dict]:
    """Every eligible (`is_eligible_printing`) Modern/Pioneer/Standard card
    (`_in_target_formats`) in an `oracle-cards` snapshot, once per
    `card_key` - the set the support baseline and the regression guard's
    oracle ratchet both cover."""
    seen: dict[str, dict] = {}
    for raw in raw_cards:
        if is_eligible_printing(raw) and _in_target_formats(raw):
            seen.setdefault(card_key(raw), raw)
    return list(seen.values())


def render_support_baseline(cards: Sequence[dict], results: Sequence[ClassificationResult]) -> str:
    """The committed baseline: a JSON array with one card object per line
    (`oracle_id`, `name`, `status`, `text_hash`), sorted by name then oracle
    id so a regeneration's diff shows exactly the cards whose status moved."""
    entries = [
        {
            "oracle_id": card_key(raw),
            "name": raw.get("name", "<unknown>"),
            "status": result.status,
            "text_hash": card_text_hash(raw),
        }
        for raw, result in zip(cards, results, strict=True)
    ]
    entries.sort(key=lambda e: (e["name"], e["oracle_id"]))
    lines = [json.dumps(e, ensure_ascii=False) for e in entries]
    return "[\n" + ",\n".join(lines) + "\n]\n"


def parse_support_baseline(text: str) -> dict[str, dict]:
    """A baseline's entries keyed by `oracle_id`."""
    return {entry["oracle_id"]: entry for entry in json.loads(text)}


def generate_support_baseline(*, bulk_path: Path, out_path: Path, workers: int = 1) -> int:
    """The `--baseline-only` path: classify the target-format pool of an
    `oracle-cards` snapshot and write just the baseline. Returns the card
    count."""
    pool = target_format_pool(load_bulk_json(bulk_path))
    results = classify_many(pool, workers=workers)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_support_baseline(pool, results))
    return len(pool)


# ---------------------------------------------------------------------------
# Missing-mechanics clustering
# ---------------------------------------------------------------------------

#: How many example card names a cluster carries for display - enough to
#: recognize the mechanic without dumping the whole affected list.
_CLUSTER_EXAMPLE_LIMIT = 5

_MANA_SYMBOL_RE = re.compile(r"\{[^}]*\}")
_TEMPLATE_QUOTED_RE = re.compile(r"\"[^\"]*\"|'[^']*'")
_NUMBER_RE = re.compile(r"\d+")
_X_WORD_RE = re.compile(r"\bx\b")
_SELF_REFERENCE_RE = re.compile(r"\bthis [a-z']+\b")
_WHITESPACE_RE = re.compile(r"\s+")

#: A clause led by a keyword or ability word ("Waterbend", "Landfall",
#: "Offspring", ...) followed by an em dash or a " - " - CR 207.2c's ability
#: word template. Captured before any other normalization so the label reads
#: exactly as printed.
_KEYWORD_LEAD_RE = re.compile(r"^([A-Z][A-Za-z'’]*(?:\s+[A-Za-z][A-Za-z'’]*){0,3})\s*[-—]\s+")

#: A Saga/Case chapter marker ("I —", "II —", "I, II —", CR 714.2/CR 715.2)
#: leading a clause. Plain roman-numeral chapter counters, never ability
#: words - "I" is not a keyword and must never be clustered as one.
_CHAPTER_LEAD_RE = re.compile(r"^([IVX]+(?:\s*,\s*[IVX]+)*)\s*[-—]\s+")
_ROMAN_CHAPTER_TOKENS = {"I", "II", "III", "IV", "V", "VI"}

#: A reason string that implicates the Saga/Case chapter machinery itself
#: (chapter/lore-counter advancement not modelled) rather than just one
#: chapter's own unparsed effect text - the rare case that earns the extra
#: "Saga chapter (see templates)" roll-up row alongside the per-template
#: clusters every chapter clause gets regardless.
_SAGA_MACHINERY_REASON_RE = re.compile(r"\bsaga\b", re.IGNORECASE)

_SAGA_MACHINERY_SIGNATURE = "meta:saga-chapter-machinery"
_SAGA_MACHINERY_LABEL = "Saga chapter (see templates)"


@dataclass(frozen=True)
class MechanicCluster:
    signature: str
    label: str
    count: int
    cards: tuple[str, ...]
    sets: tuple[str, ...]


def _keyword_lead_label(text: str) -> str | None:
    """The keyword/ability word a clause is led by ("Waterbend — ..."), or
    `None` if the clause isn't in that template."""
    match = _KEYWORD_LEAD_RE.match(text.strip())
    return match.group(1).strip() if match else None


def _chapter_lead_strip(text: str) -> str | None:
    """`text` with a leading Saga/Case chapter marker removed, or `None` if
    it isn't led by one. A chapter marker is one or more roman numerals
    (`I`..`VI`, comma-separated for a shared chapter like "I, II —") - never
    an ability word, so callers must check this before `_keyword_lead_label`
    to keep "I"/"II"/"III" out of the keyword-cluster path entirely."""
    stripped = text.strip()
    match = _CHAPTER_LEAD_RE.match(stripped)
    if not match:
        return None
    tokens = [token.strip() for token in match.group(1).split(",")]
    if not all(token in _ROMAN_CHAPTER_TOKENS for token in tokens):
        return None
    return stripped[match.end() :]


def _normalize_template(text: str, card_name: str) -> str:
    """The clause's printed text reduced to a normalized TEMPLATE: the
    card's own name and generic self-references ("this creature", "this
    spell", ...) become `~`; numbers and the variable `X` become `N`; mana
    symbols become `{M}`; quoted ability text becomes `"..."`; the whole
    thing is lowercased with whitespace collapsed. Two clauses sharing this
    normalized template are (almost always) the same underlying mechanic,
    unlike the old "same first 5 words" heuristic it replaces."""
    working = text
    for name in sorted({card_name, front_name(card_name)}, key=len, reverse=True):
        if name:
            working = re.sub(re.escape(name), "~", working, flags=re.IGNORECASE)
    working = working.lower()
    working = _SELF_REFERENCE_RE.sub("~", working)
    working = _TEMPLATE_QUOTED_RE.sub('"..."', working)
    working = _MANA_SYMBOL_RE.sub("{M}", working)
    working = _NUMBER_RE.sub("N", working)
    working = _X_WORD_RE.sub("N", working)
    working = _WHITESPACE_RE.sub(" ", working).strip()
    return working


def clause_signature(card_name: str, clause_text: str) -> tuple[str, str]:
    """The `(signature, label)` a failing clause clusters under in
    `cluster_missing_mechanics`: a chapter clause by its effect text's
    template, a keyword-led clause by its keyword, anything else by its
    normalized template, and an empty template by the card itself."""
    chapter_remainder = _chapter_lead_strip(clause_text)
    is_chapter = chapter_remainder is not None
    effect_text = chapter_remainder if is_chapter else clause_text
    keyword = None if is_chapter else _keyword_lead_label(effect_text)
    if keyword:
        return f"kw:{keyword.lower()}", keyword
    template = _normalize_template(effect_text, card_name)
    if not template:
        return f"__unsignatured__:{card_name}", clause_text
    return f"tmpl:{template}", template


def cluster_missing_mechanics(
    entries: Sequence[tuple[str, str, str, str, str, str]],
) -> list[MechanicCluster]:
    """Cluster failing clauses (`(card_name, status, clause_kind,
    clause_text, reason, set_code)` tuples - status/kind/reason are carried
    for the caller's own use, not part of the clustering key) into probable
    missing mechanics.

    A clause led by a Saga/Case chapter marker ("I —", "II —", ...) is never
    treated as an ability word: the marker is stripped and the chapter's own
    effect text clusters by normalized template like any other clause. When
    a chapter clause's own `reason` implicates the chapter/lore-counter
    machinery itself (rather than just that one chapter's unparsed effect),
    it also feeds one extra roll-up cluster labelled
    "Saga chapter (see templates)" - a pointer at the per-template clusters,
    not a replacement for them.

    Anything else led by a keyword or ability word ("Waterbend — ...")
    clusters by that word, labelled with it. Everything else clusters by its
    normalized TEMPLATE (`_normalize_template`) - only identical templates
    group together, never a loose "same first few words" match, so unrelated
    clauses that happen to open the same way land in separate clusters."""
    groups: dict[str, dict[str, object]] = {}
    for card_name, _status, _kind, clause_text, reason, set_code in entries:
        is_chapter = _chapter_lead_strip(clause_text) is not None
        signature, label = clause_signature(card_name, clause_text)
        bucket = groups.setdefault(signature, {"label": label, "cards": {}, "sets": set()})
        bucket["cards"][card_name] = None  # dict used as an ordered set
        bucket["sets"].add(set_code)

        if is_chapter and _SAGA_MACHINERY_REASON_RE.search(reason or ""):
            meta = groups.setdefault(
                _SAGA_MACHINERY_SIGNATURE,
                {"label": _SAGA_MACHINERY_LABEL, "cards": {}, "sets": set()},
            )
            meta["cards"][card_name] = None
            meta["sets"].add(set_code)
    clusters: list[MechanicCluster] = []
    for signature, data in groups.items():
        cards = tuple(data["cards"].keys())
        clusters.append(
            MechanicCluster(
                signature=signature,
                label=data["label"],
                count=len(cards),
                cards=cards[:_CLUSTER_EXAMPLE_LIMIT],
                sets=tuple(sorted(data["sets"])),
            )
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


#: `.*` (not `[^|]*`) between the code and the state column so this keeps
#: matching regardless of how many columns sit between them - the campaign-
#: order table has grown a column before now (Works, alongside Tested) and
#: may again; only the row's very last field is ever the state.
_ROUND_ROW_RE = re.compile(
    r"^\|\s*\d+\s*\|\s*\[([a-z0-9]+)\]\([^)]*\).*\|\s*([a-z-]+)\s*\|\s*$",
    re.MULTILINE,
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


#: Display labels for each `Bucket`, in the order every rendered table shows
#: them: Tested (handled + tested) -> Works (handled, untested) -> Partial
#: (unaudited) -> Not working (silent / notice / error).
_BUCKET_LABELS: dict[Bucket, str] = {
    "full": "Tested",
    "not_tested": "Works (untested)",
    "partial": "Partial (unaudited)",
    "not_working": "Not working",
}
_BUCKET_DISPLAY_ORDER: tuple[Bucket, ...] = ("full", "not_tested", "partial", "not_working")


def _format_bucket_table(counts: dict[Bucket, int], total: int) -> str:
    lines = ["| Bucket | Count | % |", "|---|---|---|"]
    for bucket in _BUCKET_DISPLAY_ORDER:
        count = counts.get(bucket, 0)
        pct = f"{(100.0 * count / total):.1f}%" if total else "0.0%"
        lines.append(f"| {_BUCKET_LABELS[bucket]} | {count} | {pct} |")
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
    cluster_entries: list[tuple[str, str, str, str, str, str]] = []
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
                    (
                        name,
                        result.status,
                        result.clause_kind,
                        result.clause_text,
                        result.reason,
                        meta.code,
                    )
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
        lines.append("| Mechanic (label / template) | Count | Example cards | Sets |")
        lines.append("|---|---|---|---|")
        for cluster in clusters:
            card_list = ", ".join(cluster.cards)
            clause = cluster.label.replace("|", "\\|").replace("\n", " ")[:160]
            sets = ", ".join(cluster.sets)
            lines.append(f"| {clause} | {cluster.count} | {card_list} | {sets} |")
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
    tested: int
    works: int
    partial: int
    not_working: int
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
    total_bucket_counts: dict[Bucket, int] = {
        "full": sum(r.tested for r in rows),
        "not_tested": sum(r.works for r in rows),
        "partial": sum(r.partial for r in rows),
        "not_working": sum(r.not_working for r in rows),
    }

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
    lines.append(f"{len(rows)} expansions, {total_cards} cards in scope.")
    lines.append("")
    lines.append(_format_bucket_table(total_bucket_counts, total_cards))
    lines.append("")
    lines.append("## Campaign order")
    lines.append("")
    lines.append("| Round | Set | Release date | Cards | Tested | Works | State |")
    lines.append("|---|---|---|---|---|---|---|")
    round0_state = "in-progress" if round0_cards else "done"
    round0_count = len(round0_cards)
    lines.append(
        f"| Round 0 | [metagame decks]({ROUND0_DIR_NAME}/status.md) "
        f"({round0_count} cards not full) | - | {round0_count} | - | - | {round0_state} |"
    )
    for row in newest_first:
        dir_name = format_expansion_dir(row.number, row.code)
        link = f"[{row.code}]({dir_name}/status.md)"
        lines.append(
            f"| {row.number} | {link} - {row.name} | {row.release_date} "
            f"| {row.total} | {row.tested} | {row.works} | {row.state} |"
        )
    lines.append("")
    lines.append("## Missing mechanics")
    lines.append("")
    if missing_mechanics:
        lines.append("| Mechanic (label / template) | Count | Example cards | Sets |")
        lines.append("|---|---|---|---|")
        # Top 50 by card count - `missing_mechanics` is already sorted
        # (-count, signature) by `cluster_missing_mechanics`.
        for cluster in missing_mechanics[:50]:
            clause = cluster.label.replace("|", "\\|").replace("\n", " ")[:160]
            card_list = ", ".join(cluster.cards)
            sets = ", ".join(cluster.sets)
            lines.append(f"| {clause} | {cluster.count} | {card_list} | {sets} |")
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
    """Every card name found in `*.txt` decklists under each directory in
    `decks_dirs`. Each directory is searched flat first (`*.txt` directly
    inside it) - the layout the api repo's own decks/ dir uses. Only when
    that comes up empty does it fall back to a recursive search for files
    literally named `decklist.txt` - mtg-decks's own layout, nothing at the
    top level, one `<archetype>/decklist.txt` per archetype nested one
    level down, alongside plenty of non-decklist `.txt`/`.md`/`.json` notes
    (NOTES.md, archetype.json, a `plays/` subtree...) that a generic
    recursive `*.txt` would also have picked up.

    A directory that does not exist at all is reported on stderr rather
    than silently skipped - a missing decks dir contributing zero cards to
    Round 0 is exactly the silent-undercount shape this project's other
    tooling is written not to allow."""
    names: set[str] = set()
    for directory in decks_dirs:
        if not directory.exists():
            print(f"WARNING: deck dir {directory} does not exist, skipping it", file=sys.stderr)
            continue
        paths = list(directory.glob("*.txt"))
        if not paths:
            paths = list(directory.rglob("decklist.txt"))
        for path in paths:
            names.update(parse_deck_file(path))
    return names


#: `docs/card_coverage/metagame.json`'s own default location and directory
#: name (`scripts/fetch_metagame.py` writes it; `generate_all` reads it and
#: writes `docs/card_coverage/000-metagame/status.md` alongside it).
DEFAULT_METAGAME_FILENAME = "metagame.json"
ROUND0_DIR_NAME = "000-metagame"


def load_metagame(path: Path) -> dict:
    """The parsed `metagame.json`, or an empty-formats shape if the file is
    missing or unreadable - `fetch_metagame.py` may not have been run yet in
    a fresh checkout, and Round 0 must still degrade to "deck-dir cards
    only" rather than crashing the whole coverage run."""
    if not path.exists():
        return {"formats": {}}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {"formats": {}}


def cards_from_metagame(metagame: dict) -> dict[str, list[tuple[str, str, float]]]:
    """Every card `metagame.json` pulled in, flattened to
    `name -> [(format, archetype, rate), ...]` - one entry per
    (format, archetype) whose `cards` mapping named that card, so a card
    pulled in by several archetypes (or several formats) carries every rate
    that pulled it in, not just one."""
    pulls: dict[str, list[tuple[str, str, float]]] = {}
    for fmt, archetypes in (metagame.get("formats") or {}).items():
        for archetype_name, data in archetypes.items():
            for name, rate in (data.get("cards") or {}).items():
                pulls.setdefault(name, []).append((fmt, archetype_name, rate))
    return pulls


@dataclass(frozen=True)
class Round0Row:
    """One Round 0 card: its resolved engine name, its bucket/status
    against the classification pool already computed for the whole
    Modern/Pioneer/Standard-legal card set, every `(format, archetype,
    rate)` that pulled it into Round 0 (empty if it came only from a
    deck-dir file), and `max_rate` - the sort key, highest rate first."""

    name: str
    bucket: str
    status: str
    pulls: tuple[tuple[str, str, float], ...]
    from_deck_file: bool
    max_rate: float


def _resolve_round0_name(
    name: str, *, classifications_by_name: dict, front_index: dict[str, str]
) -> str:
    if name in classifications_by_name:
        return name
    if "/" in name and " // " not in name:
        # Deck-file split spelling "Wear/Tear" -> engine "Wear // Tear".
        joined = " // ".join(part.strip() for part in name.split("/"))
        if joined in classifications_by_name:
            return joined
    return front_index.get(name, name)


def build_round0_rows(
    *,
    metagame: dict,
    decks_dirs: Iterable[Path],
    classifications_by_name: dict[str, ClassificationResult],
    tested_by_name: dict[str, bool],
) -> tuple[list[Round0Row], list[str]]:
    """Round 0 = the union of every card `metagame.json` pulled in
    (`cards_from_metagame`) and every card named in a deck-dir file
    (`cards_from_deck_dirs`), classified against the classification pool
    already computed for the whole target-format-legal card set, filtered
    to cards that are NOT `full` (handled + tested), sorted most-played
    first (`max_rate` descending, then name).

    A raw name (a deck file's own front-face-only spelling of a split/MDFC
    card, say) is resolved to the engine's own name the same way
    `TestedIndex` does - `front_name` - before being merged; two spellings
    of the same card become one row, not two. A name that resolves to
    nothing in the classification pool at all is returned in the second
    element (`unresolved`, sorted) for the caller to report on stderr,
    never silently dropped.
    """
    pulls_by_name = cards_from_metagame(metagame)
    deck_names = cards_from_deck_dirs(decks_dirs)

    front_index: dict[str, str] = {}
    for full_name in classifications_by_name:
        front = front_name(full_name)
        if front != full_name:
            front_index.setdefault(front, full_name)

    resolved_pulls: dict[str, list[tuple[str, str, float]]] = {}
    for name, pulls in pulls_by_name.items():
        resolved = _resolve_round0_name(
            name, classifications_by_name=classifications_by_name, front_index=front_index
        )
        resolved_pulls.setdefault(resolved, []).extend(pulls)

    deck_only: set[str] = set()
    for name in deck_names:
        resolved = _resolve_round0_name(
            name, classifications_by_name=classifications_by_name, front_index=front_index
        )
        resolved_pulls.setdefault(resolved, resolved_pulls.get(resolved, []))
        deck_only.add(resolved)

    rows: list[Round0Row] = []
    unresolved: list[str] = []
    for resolved_name in set(resolved_pulls) | deck_only:
        result = classifications_by_name.get(resolved_name)
        if result is None:
            unresolved.append(resolved_name)
            continue
        bucket = bucket_of(result.status, tested_by_name.get(resolved_name, False))
        if bucket == "full":
            continue
        pulls = tuple(
            sorted(set(resolved_pulls.get(resolved_name, [])), key=lambda p: (-p[2], p[0], p[1]))
        )
        rows.append(
            Round0Row(
                name=resolved_name,
                bucket=bucket,
                status=result.status,
                pulls=pulls,
                from_deck_file=resolved_name in deck_only,
                max_rate=pulls[0][2] if pulls else 0.0,
            )
        )
    rows.sort(key=lambda r: (-r.max_rate, r.name))
    return rows, sorted(unresolved)


def render_round0_status_md(rows: list[Round0Row]) -> str:
    """Round 0's own `status.md`
    (`docs/card_coverage/000-metagame/status.md`), in the same style as a
    per-expansion one: a coverage table by bucket, then one row per card
    (already filtered to not-full, already sorted most-played first by the
    caller) naming which format/archetype pulled it in and at what rate, or
    "deck file" when a deck-dir file is its only source."""
    bucket_counts: dict[Bucket, int] = {}
    for row in rows:
        bucket_counts[row.bucket] = bucket_counts.get(row.bucket, 0) + 1

    lines: list[str] = []
    lines.append("# Round 0 - metagame decks")
    lines.append("")
    lines.append(f"- Cards not full: {len(rows)}")
    lines.append("")
    lines.append("## Coverage")
    lines.append("")
    lines.append(_format_bucket_table(bucket_counts, len(rows)))
    lines.append("")
    lines.append("## Cards")
    lines.append("")
    if rows:
        lines.append("| Card | Status | Bucket | Pulled in by |")
        lines.append("|---|---|---|---|")
        for row in rows:
            pulled_in_by = ", ".join(
                f"{fmt}/{archetype} {rate:.2f}" for fmt, archetype, rate in row.pulls
            )
            if row.from_deck_file:
                pulled_in_by = f"{pulled_in_by}, deck file" if pulled_in_by else "deck file"
            lines.append(f"| {row.name} | {row.status} | {row.bucket} | {pulled_in_by} |")
    else:
        lines.append("None - every Round 0 card is fully supported.")
    lines.append("")
    return "\n".join(lines) + "\n"


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
    pruned_codes: tuple[str, ...] = ()
    recovered_notes_codes: tuple[str, ...] = ()
    round0_not_full: int = 0


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
) -> tuple[int, dict[Bucket, int]]:
    classifications, tested = _classifications_and_tested_for_meta(meta, tested_index, workers)
    return _write_set_status_from_classifications(meta, number, out_dir, classifications, tested)


def _write_set_status_from_classifications(
    meta: SetMeta,
    number: int,
    out_dir: Path,
    classifications: dict[str, ClassificationResult],
    tested: dict[str, bool],
) -> tuple[int, dict[Bucket, int]]:
    """Renders and writes one set's `status.md` from already-computed
    classifications, so a full run's single big classification pass
    (`generate_all`) never re-classifies a set's cards a second time just to
    write its file. Returns the total card count and every bucket's count
    (`full`/`not_tested`/`partial`/`not_working`), not just `full` - the
    campaign-order table's Tested/Works columns and the overall roll-up need
    all four."""
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
    bucket_counts: dict[Bucket, int] = {}
    for name, r in classifications.items():
        bucket = bucket_of(r.status, tested.get(name, False))
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
    return total, bucket_counts


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
    metagame_path: Path | None = None,
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

    `metagame_path` (default `out_dir / DEFAULT_METAGAME_FILENAME`) is
    `docs/card_coverage/metagame.json` (`scripts/fetch_metagame.py`'s own
    output) - Round 0's other input alongside `decks_dirs`.
    """
    raw_cards = load_bulk_json(bulk_path)
    # The baseline pool is taken from the oracle snapshot itself, before the
    # first-printing merge rewrites `digital`/`games`, so it is exactly the
    # set `regression_guard.py --ratchet` selects from the same file.
    baseline_pool = target_format_pool(raw_cards)
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

    # A set whose cards all got reattributed elsewhere this run (typically
    # select_first_printing's promo preference) no longer has any
    # first-printed card in `modern_codes` at all - its directory is
    # orphaned. Prune it, unless a human left notes there, in which case it
    # survives untouched and its notes move into plan.md's own Notes.
    pruned_codes, recovered_notes = prune_orphaned_sets(out_dir, modern_codes)
    existing_plan_notes = merge_pruned_notes_into_plan(existing_plan_notes, recovered_notes)

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
    # The baseline pool and the per-set cards share one classification pass.
    unique_cards = {card_key(raw): raw for raw in baseline_pool}
    for raw in all_target_cards:
        unique_cards.setdefault(card_key(raw), raw)
    unique_keys = list(unique_cards)
    unique_results = classify_many([unique_cards[k] for k in unique_keys], workers=workers)
    results_by_key = dict(zip(unique_keys, unique_results, strict=True))
    all_results = [results_by_key[card_key(raw)] for raw in all_target_cards]
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / SUPPORT_BASELINE_FILENAME).write_text(
        render_support_baseline(
            baseline_pool, [results_by_key[card_key(raw)] for raw in baseline_pool]
        )
    )

    classifications_by_set: dict[str, dict[str, ClassificationResult]] = {
        code: {} for code in ordered_codes
    }
    tested_by_set: dict[str, dict[str, bool]] = {code: {} for code in ordered_codes}
    # Also kept flat by name, across every set - Round 0 (metagame.json +
    # deck-dir cards) needs to look a card's bucket up without caring which
    # set it belongs to.
    classifications_by_name: dict[str, ClassificationResult] = {}
    tested_by_name: dict[str, bool] = {}
    for code, raw, result in zip(card_set_codes, all_target_cards, all_results, strict=True):
        classifications_by_set[code][result.name] = result
        is_tested = tested_index.is_tested(raw["name"])
        tested_by_set[code][raw["name"]] = is_tested
        classifications_by_name[result.name] = result
        tested_by_name[result.name] = is_tested

    rows: list[PlanRow] = []
    all_cluster_entries: list[tuple[str, str, str, str, str, str]] = []
    total_card_count = 0
    for code in modern_codes:
        meta = index[code]
        number = numbers[code]
        classifications = classifications_by_set[code]
        tested = tested_by_set[code]
        total, bucket_counts = _write_set_status_from_classifications(
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
                tested=bucket_counts.get("full", 0),
                works=bucket_counts.get("not_tested", 0),
                partial=bucket_counts.get("partial", 0),
                not_working=bucket_counts.get("not_working", 0),
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
                        code,
                    )
                )

    missing_mechanics = cluster_missing_mechanics(all_cluster_entries)

    resolved_metagame_path = (
        metagame_path if metagame_path is not None else out_dir / DEFAULT_METAGAME_FILENAME
    )
    metagame = load_metagame(resolved_metagame_path)
    round0_rows, round0_unresolved = build_round0_rows(
        metagame=metagame,
        decks_dirs=decks_dirs,
        classifications_by_name=classifications_by_name,
        tested_by_name=tested_by_name,
    )
    for name in round0_unresolved:
        print(
            f"WARNING: Round 0 card {name!r} not found in the target-format card pool",
            file=sys.stderr,
        )
    round0_dir = out_dir / ROUND0_DIR_NAME
    round0_dir.mkdir(parents=True, exist_ok=True)
    (round0_dir / "status.md").write_text(render_round0_status_md(round0_rows))

    round0_cards = [row.name for row in round0_rows]
    plan_text = render_plan_md(
        rows=rows,
        round0_cards=round0_cards,
        missing_mechanics=missing_mechanics,
        existing_notes=existing_plan_notes,
        existing_done=existing_plan_done,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(plan_text)

    return GenerateResult(
        set_count=len(rows),
        card_count=total_card_count,
        pruned_codes=tuple(pruned_codes),
        recovered_notes_codes=tuple(code for code, _notes in recovered_notes),
        round0_not_full=len(round0_rows),
    )


def generate_one_set(
    *,
    code: str,
    raw_cards: list[dict],
    out_dir: Path,
    printings_dir: Path,
    tests_dir: Path,
    golden_dir: Path,
    workers: int = 1,
) -> tuple[int, dict[Bucket, int]]:
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
        "--baseline-only",
        action="store_true",
        help=f"write only <out-dir>/{SUPPORT_BASELINE_FILENAME} (the regression guard's floor)",
    )
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
        total, bucket_counts = generate_one_set(
            code=args.set_code,
            raw_cards=raw_cards,
            out_dir=args.out_dir,
            printings_dir=args.printings_dir,
            tests_dir=args.tests_dir,
            golden_dir=args.golden_dir,
            workers=args.workers,
        )
        tested = bucket_counts.get("full", 0)
        print(f"{args.set_code}: {total} cards in scope, {tested} tested")
        return 0

    bulk_path = download_bulk("oracle-cards", cache_dir=args.cache_dir, force=args.refresh_bulk)
    if args.baseline_only:
        count = generate_support_baseline(
            bulk_path=bulk_path,
            out_path=args.out_dir / SUPPORT_BASELINE_FILENAME,
            workers=args.workers,
        )
        print(f"{count} cards written to {args.out_dir / SUPPORT_BASELINE_FILENAME}")
        return 0
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
    print(f"Round 0: {result.round0_not_full} cards not full")
    if result.pruned_codes:
        print(
            f"pruned {len(result.pruned_codes)} orphaned set dirs: {', '.join(result.pruned_codes)}"
        )
    if result.recovered_notes_codes:
        print(
            f"kept {len(result.recovered_notes_codes)} orphaned set dirs with notes "
            f"(moved into plan.md): {', '.join(result.recovered_notes_codes)}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
