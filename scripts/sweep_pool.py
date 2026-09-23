#!/usr/bin/env python
"""Sweep the scenario card pool for cards that would do nothing if played.

    uv run python scripts/sweep_pool.py            # the summary
    uv run python scripts/sweep_pool.py --keywords # only the keyword report
    uv run python scripts/sweep_pool.py --effects  # only the effect report
    uv run python scripts/sweep_pool.py --targeting # targeting text nobody can read
    uv run python scripts/sweep_pool.py --card "Grief"

Three different holes look identical from a passing test, and all three are here.

**No effect anywhere in the dispatch chain.** `machines/effects.py` no longer
keys most cards by name at all - a card with no `EFFECTS`/`TRIGGER_EFFECTS`/
`ACTIVATED_EFFECTS` row falls through to a parser that reads the shape straight
off the card's own oracle text (`effect_for`, `trigger_effect_for`,
`activated_effect_for`), and a parser that cannot read the text still may record
one of several notices - `LayerNotice`, `TargetingNotice`, `InterveningIfNotice`,
`ModeNotice`, `AnaphoricClauseNotice`, `DelayedClauseNotice`, `EvasionNotice`,
`ImprintNotice`, `UndefinedPowerNotice` - rather than silently doing nothing.
**Registry membership was never the right thing to measure**: `ACTIVATED_EFFECTS`
is empty by design, and most of `EFFECTS`/`TRIGGER_EFFECTS` are gone on purpose,
their old rows now read by a parser instead (see each registry's own docstring
in `machines/effects.py`). The effect report below calls the real dispatchers -
`effect_for`, `trigger_effect_for`, `activated_effect_for` - with the same
arguments `models/game.py` calls them with, and sorts the result into four
buckets: **handled** (a registry row or a parser produced a real effect),
**notice** (the engine recognised the text and fails closed with one of the
notices above, which is correct behaviour), **static_unaudited** (a permanent's
own static ability, CR 604.2 / CR 113.3d, whose subsystem this tool does not
audit - an unknown, never a claim of coverage), and **silent** (nothing happened
and nothing was recorded - the only bucket that is actually a bug).

**The verdict is per clause, and the card's own verdict is the worst of them.**
A card is not "handled" because one of its four abilities is; it is only as good
as its deadest clause. Reporting the best outcome per card is how Territorial
Kavu's dead characteristic-defining ability (CR 613.4a), Obsidian Charmaw's dead
cost-reduction line and Engineered Explosives' dead sunburst all read clean for
a whole day of measurement. `classify_clauses` returns every clause's own
outcome; `classify_card` reduces it with `silent < static_unaudited < notice <
handled`. Two things are deliberately **not** clauses: a permanent spell's
resolution (CR 608.3a - it becomes a permanent and enters the battlefield, so
`effect_for` returning `None` for one is correct, not a gap), and a mana ability
(CR 605.1a), which never reaches a dispatcher at all.

**No execution path for a keyword.** This is the one that hid. A card can have
its keyword parsed, printed, and reported by `parse_abilities`, and still have
nothing anywhere in the engine that acts on it - Solitude's evoke used to parse
as a static ability and then do nothing at all, and every sweep called the card
fine because it had no *effect* entry to miss either. A keyword is only counted
as executed here if some named machine reads it:

- combat reads it (`machines/combat.Keyword`),
- it hands out a way to cast the card (`machines/casting.keyword_cast_options`),
- it changes *when* or *at what* a card may be cast
  (`machines/casting.TIMING_KEYWORDS`, `TARGET_LEGALITY_KEYWORDS`), or is an
  optional additional cost on it (`ADDITIONAL_COST_KEYWORDS`),
- `machines/keywords.executes` claims it - cycling, equip, ward, prowess,
  cascade, persist, dredge, mobilize, indestructible, exert (morph, disguise and
  madness are ways to *cast* a card, not to act on a keyword, so they are
  `machines/casting.keyword_cast_options`'s business instead, and are already
  counted through that path),
- protection is enforced in `models/game.py`, which is the one authority outside
  `machines/`,
- it is a mana ability the payment path can tap (`parse_mana_abilities`),
- or it is on the explicitly-inert list below, where the keyword genuinely needs
  no code because it only changes what a card *is*.

Anything else is reported as ignored, with the card that carries it.

**Targeting text nobody can read.** `machines/targeting.py` reports
`understood=False` for a phrase it could not parse, and CR 115 legality is then
not checked at all - which looks exactly like a card that targets nothing. The
report exists to drive that count toward zero as the pool grows, not because it
already is.

**Where the verdict lives.** This script is a report over the fixture pool
and nothing more: every per-card and per-clause verdict it prints comes from
`magic_cards_model.support.card_support`, the engine's own support oracle,
which a deck checker or any other consumer asks the same question of. The
classification code, and the history of why each rule in it exists, is in
`src/magic_cards_model/support.py`.
"""

import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tests.cards import CARD_POOL, card, pool  # noqa: E402

from magic_cards_model.machines.abilities import AbilityKind, parse_abilities  # noqa: E402
from magic_cards_model.machines.modes import modal_profile  # noqa: E402
from magic_cards_model.machines.targeting import profile_for_text  # noqa: E402
from magic_cards_model.models.card import Card  # noqa: E402
from magic_cards_model.support import (  # noqa: E402
    HANDLED,
    NOTICE,
    QUOTED_EFFECT,
    SILENT,
    STATIC_UNAUDITED,
    UNMATCHABLE_CONDITION,
    WHOLE_CARD_TEXT_SOURCE,
    card_support,
    classify_card,
    has_rules_text,
    ignored_keywords,
    in_target_formats,
)

#: What other scripts and tests import from here. The classifier itself moved
#: to `magic_cards_model.support`; these stay importable from the sweep so a
#: caller that only knows the script keeps working.
__all__ = [
    "HANDLED",
    "NOTICE",
    "QUOTED_EFFECT",
    "SILENT",
    "STATIC_UNAUDITED",
    "UNMATCHABLE_CONDITION",
    "card",
    "classify_card",
    "has_rules_text",
    "ignored_keywords",
    "in_target_formats",
    "legal_cards_failing_closed",
    "main",
    "pool",
    "report_effects",
    "targeting_gaps",
]


def _ignored_keywords_of(printing: Card) -> list[str]:
    """`ignored_keywords`, read off `card_support`'s own keyword clauses."""
    return sorted(
        clause.text
        for clause in card_support(printing).clauses
        if clause.kind == "keyword" and clause.outcome == SILENT
    )


def report_keywords(names: list[str]) -> int:
    by_keyword: dict[str, list[str]] = defaultdict(list)
    for name in names:
        for keyword in _ignored_keywords_of(card(name)):
            by_keyword[keyword].append(name)

    print("Keywords with no execution path")
    print("-" * 62)
    if not by_keyword:
        print("  none - every keyword in the pool is read by some machine")
        return 0
    for keyword, cards in sorted(by_keyword.items()):
        print(f"  {keyword:<18} {', '.join(sorted(cards))}")
    print(f"\n  {len(by_keyword)} keyword(s) ignored across {len(names)} cards")
    return len(by_keyword)


def legal_cards_failing_closed(names: list[str]) -> list[tuple[str, str]]:
    """Cards among `names` that are legal in Modern, Pioneer or Standard
    (`in_target_formats`) whose worst clause (`classify_card`) fails closed
    with a `NOTICE` - the owner rule's own gap list.

    A `NOTICE` is correct, fail-closed behaviour in the ordinary sense
    `report_effects`'s own module docstring describes it - nothing silently
    did nothing - but the owner rule is stricter than "not a bug": every
    card legal in one of the three target formats must be **fully
    supported**, so a legal card resting on a notice is never an acceptable
    end state, only a still-open gap that has not been closed yet. A card
    outside the three target formats can rest on a notice indefinitely; this
    list is deliberately silent about those - `in_target_formats` is checked
    here directly, regardless of whether the caller already filtered `names`
    (main()'s default run) or passed the whole pool (`--all-formats`), so the
    answer never depends on which one happened to call it.
    """
    found: list[tuple[str, str]] = []
    for name in names:
        printing = card(name)
        support = card_support(printing)
        if not support.has_rules_text or not in_target_formats(printing):
            continue
        if support.effect_outcome == NOTICE:
            found.append((name, support.effect_detail))
    return found


def report_effects(names: list[str]) -> int:
    """Sort every clause of every card with rules text into handled / notice /
    static_unaudited / silent / unmatchable_condition / quoted_effect, and
    print the buckets that are not coverage: the dead clauses, the static
    abilities nothing here audits, the triggers whose own condition can never
    fire, and the clauses whose effect was matched out of quoted text.

    A vanilla creature (no rules text at all) is not asked about - it is
    correct for one to have no effect, and `has_rules_text` is the same gate
    `classify_card` itself is meaningless without.

    The counts are **per card, by its worst clause** (`classify_card`), and
    the dead-clause list names the clause, so a card that is 90% working and
    10% dead is listed with the 10% rather than counted as fine.

    `handled` here is a narrower claim than it looks: it means a dispatcher
    produced a real effect for *some* reading of the clause, not that
    `machines/triggers.condition_matches` (CR 603.2) can ever actually
    trigger it, nor that a fallback parser's answer came from the clause's
    own text rather than a quoted span inside it - both of those are now
    checked separately, and a clause failing either one is moved out of
    `handled` into its own bucket rather than counted as coverage.
    """
    with_text = [name for name in names if card_support(card(name)).has_rules_text]
    counts: dict[str, int] = {
        HANDLED: 0,
        NOTICE: 0,
        STATIC_UNAUDITED: 0,
        SILENT: 0,
        UNMATCHABLE_CONDITION: 0,
        QUOTED_EFFECT: 0,
    }
    silent: list[tuple[str, str]] = []
    unaudited: list[tuple[str, str]] = []
    unmatchable: list[tuple[str, str]] = []
    quoted: list[tuple[str, str]] = []
    for name in with_text:
        support = card_support(card(name))
        category, detail = support.effect_outcome or SILENT, support.effect_detail
        counts[category] += 1
        if category == SILENT:
            silent.append((name, detail))
        elif category == STATIC_UNAUDITED:
            unaudited.append((name, detail))
        elif category == UNMATCHABLE_CONDITION:
            unmatchable.append((name, detail))
        elif category == QUOTED_EFFECT:
            quoted.append((name, detail))

    print("\nCards with a clause that does nothing at all and logs nothing")
    print("-" * 62)
    if not silent:
        print("  none - every clause in the pool is handled or fails closed with a notice")
    for name, detail in sorted(silent):
        print(f"  {name}")
        if detail:
            print(f"    {detail[:70]}")

    print("\nStatic abilities this tool does not audit (CR 604.2) - unknown, not clean")
    print("-" * 62)
    if not unaudited:
        print("  none")
    for name, detail in sorted(unaudited):
        print(f"  {name}")
        if detail:
            print(f"    {detail[:70]}")

    print("\nTriggers whose own condition (CR 603.2) can never be satisfied")
    print("-" * 62)
    if not unmatchable:
        print("  none - every readable trigger condition matches some real permanent")
    for name, detail in sorted(unmatchable):
        print(f"  {name}")
        if detail:
            print(f"    {detail[:70]}")

    print("\nClauses whose effect was matched out of a quoted span, not their own text")
    print("-" * 62)
    if not quoted:
        print("  none - no dispatcher answer depends on what a quote happens to say")
    for name, detail in sorted(quoted):
        print(f"  {name}")
        if detail:
            print(f"    {detail[:70]}")

    # OWNER RULE: a card legal in Modern, Pioneer or Standard must be fully
    # supported - a fail-closed notice is not an acceptable end state for one
    # of those, even though `NOTICE` is ordinarily correct behaviour (see
    # this function's own docstring). So a legal card resting on a notice is
    # listed here as a gap in its own right, never folded into the "fine"
    # reading `counts[NOTICE]` alone would otherwise invite.
    legal_gaps = legal_cards_failing_closed(names)
    print("\nLegal cards (Modern/Pioneer/Standard) failing closed with a notice")
    print("-" * 62)
    if not legal_gaps:
        print("  none - no legal card rests on a fail-closed notice")
    for name, detail in sorted(legal_gaps):
        print(f"  {name}")
        if detail:
            print(f"    {detail[:70]}")
    print(
        f"\n  {len(legal_gaps)} legal card(s) failing closed with a notice - OWNER RULE: "
        "not an acceptable end state, still a gap to close"
    )

    print(
        f"\n  {len(silent)} of {len(with_text)} cards with rules text have a clause that does "
        f"nothing and logs nothing\n  ({counts[HANDLED]} handled by a registry row or a parser, "
        f"{counts[NOTICE]} fail closed with a notice, "
        f"{counts[STATIC_UNAUDITED]} rest on a static ability nobody here audits, "
        f"{counts[UNMATCHABLE_CONDITION]} have a trigger condition that can never fire, "
        f"{counts[QUOTED_EFFECT]} have an effect matched out of quoted text)"
    )
    return len(silent)


def targeting_gaps(printing: Card) -> list[tuple[str, str]]:
    """Every line of this printing's text whose targeting the parser cannot read.

    `machines/targeting.py` says so itself: a profile it could not read comes
    back with `understood=False`, and CR 115 legality is then not checked at
    all - which is a hole that looks exactly like a card with no targets.

    Every line is asked separately, because they are asked separately in play:
    a spell's own text is CR 601.2c, a triggered ability chooses its targets as
    it goes on the stack (CR 603.3d), an activated ability as it is activated
    (CR 602.2b), and a mode only once it has been chosen (CR 700.2c).
    """
    gaps: list[tuple[str, str]] = []

    for ability in parse_abilities(printing):
        if ability.kind is AbilityKind.KEYWORD:
            continue
        text = getattr(ability, "effect", None) or ability.text
        if "target" not in text.lower():
            continue
        if not profile_for_text(text).understood:
            gaps.append((ability.kind.value, text))

    profile = modal_profile(printing)
    for mode in profile.modes if profile is not None else ():
        if "target" in mode.text.lower() and not profile_for_text(mode.text).understood:
            gaps.append(("mode", mode.text))

    return gaps


def report_targeting(names: list[str]) -> int:
    print("\nTargeting text the parser cannot read")
    print("-" * 62)
    total = 0
    for name in sorted(names):
        for kind, text in targeting_gaps(card(name)):
            total += 1
            print(f"  {name}")
            print(f"    [{kind}] {text[:70]}")
    if not total:
        print("  none - every targeting phrase in the pool is understood")
    print(f"\n  {total} unreadable targeting phrase(s) across {len(names)} cards")
    return total


def report_card(name: str) -> int:
    printing = card(name)
    print(f"{printing.name}  [{printing.type_line}]")
    print("-" * 62)
    if not in_target_formats(printing):
        print("  outside Modern/Pioneer/Standard - not counted")
    for ability in parse_abilities(printing):
        detail = getattr(ability, "cost", None) or getattr(ability, "parameter", None) or ""
        print(f"  {ability.kind.value:<10} {ability.text[:60]}  {detail}")
    support = card_support(printing)
    print("\n  keyword execution:")
    for clause in support.clauses:
        if clause.kind == "keyword":
            where = clause.reason if clause.outcome == HANDLED else "IGNORED"
            print(f"    {clause.text:<18} {where}")
    if support.has_rules_text:
        print("\n  clause outcomes:")
        for clause in support.clauses:
            if clause.kind == "keyword" or clause.source == WHOLE_CARD_TEXT_SOURCE:
                continue
            print(f"    {clause.outcome:<17} [{clause.source}] {clause.text[:60]}")
        category, detail = support.effect_outcome, support.effect_detail
        print(f"\n  outcome (worst clause): {category}" + (f" - {detail[:70]}" if detail else ""))
    else:
        print("\n  outcome: n/a (no rules text)")
    return 0


def format_filter_footer(all_names: list[str], filtered_names: list[str]) -> None:
    """The report footer the format rule owes every report it filtered:
    how many pool cards `in_target_formats` dropped, so the count above never
    reads as the *whole* pool's coverage by accident."""
    excluded = len(all_names) - len(filtered_names)
    print(
        f"\n  {excluded} pool card(s) excluded (not legal in Modern, Pioneer or Standard) "
        "- pass --all-formats to include them"
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keywords", action="store_true", help="only the keyword report")
    parser.add_argument(
        "--effects",
        action="store_true",
        help="only the effect report: cards that would do nothing at all if played",
    )
    parser.add_argument(
        "--targeting", action="store_true", help="only the unreadable-targeting report"
    )
    parser.add_argument("--card", help="report on one card by name")
    parser.add_argument(
        "--all-formats",
        action="store_true",
        help=(
            "disable the Modern/Pioneer/Standard filter (`in_target_formats`) and report "
            "on the whole card pool"
        ),
    )
    args = parser.parse_args(argv)

    if args.card:
        return report_card(args.card)

    all_names = sorted(pool())
    if not all_names:
        print(f"no cards in {CARD_POOL}")
        return 1

    names = (
        all_names
        if args.all_formats
        else [name for name in all_names if in_target_formats(card(name))]
    )

    if args.effects:
        report_effects(names)
        if not args.all_formats:
            format_filter_footer(all_names, names)
        return 0
    if args.keywords:
        report_keywords(names)
        if not args.all_formats:
            format_filter_footer(all_names, names)
        return 0
    if args.targeting:
        report_targeting(names)
        if not args.all_formats:
            format_filter_footer(all_names, names)
        return 0

    report_keywords(names)
    report_effects(names)
    report_targeting(names)
    if not args.all_formats:
        format_filter_footer(all_names, names)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
