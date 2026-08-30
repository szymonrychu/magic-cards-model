#!/usr/bin/env python
"""Sweep the scenario card pool for text the engine silently ignores.

    uv run python scripts/sweep_pool.py            # the summary
    uv run python scripts/sweep_pool.py --keywords # only the keyword report
    uv run python scripts/sweep_pool.py --effects  # only the effect report
    uv run python scripts/sweep_pool.py --targeting # targeting text nobody can read
    uv run python scripts/sweep_pool.py --card "Grief"

Three different holes look identical from a passing test, and all three are here.

**No effect entry.** `machines/effects.py` is keyed by card name, so a card with
no entry resolves and does nothing. That is correct for a vanilla creature and
silently wrong for anything with rules text.

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
  cascade, persist, dredge,
- protection is enforced in `models/game.py`, which is the one authority outside
  `machines/`,
- it is a mana ability the payment path can tap (`parse_mana_abilities`),
- or it is on the explicitly-inert list below, where the keyword genuinely needs
  no code because it only changes what a card *is*.

Anything else is reported as ignored, with the card that carries it.

**Targeting text nobody can read.** `machines/targeting.py` reports
`understood=False` for a phrase it could not parse, and CR 115 legality is then
not checked at all - which looks exactly like a card that targets nothing. The
count is zero today; the report exists to keep it there as the pool grows.
"""

import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tests.cards import CARD_POOL, card, pool  # noqa: E402

from magic_cards_model.machines import keywords as keyword_machine  # noqa: E402
from magic_cards_model.machines.abilities import (  # noqa: E402
    AbilityKind,
    keyword_abilities,
    parse_abilities,
    parse_mana_abilities,
)
from magic_cards_model.machines.casting import (  # noqa: E402
    ADDITIONAL_COST_KEYWORDS,
    TARGET_LEGALITY_KEYWORDS,
    TIMING_KEYWORDS,
    adventure_face,
    keyword_cast_options,
)
from magic_cards_model.machines.combat import Keyword  # noqa: E402
from magic_cards_model.machines.effects import (  # noqa: E402
    ACTIVATED_EFFECTS,
    EFFECTS,
    TRIGGER_EFFECTS,
)
from magic_cards_model.machines.modes import modal_profile  # noqa: E402
from magic_cards_model.machines.targeting import profile_for_text  # noqa: E402
from magic_cards_model.models.card import Card  # noqa: E402

#: Keywords that need no code because they change what a card *is*, not what the
#: engine has to do. Each is inert in the sense that the rules attach no action
#: to it that this engine would otherwise have to perform.
NEEDS_NO_CODE = frozenset(
    {
        # No CR numbers here on purpose: they would be numbers nobody looked
        # up. What each entry claims is only that the engine has nothing to do.
        "devoid",  # it has no colour. A characteristic, not an action.
        "transform",  # performed by CardState.transform when told to.
        "mill",  # an action word, not a keyword ability.
        "scry",  # an action word, executed by an effect entry.
        "surveil",  # an action word.
        "food",  # a predefined token type, not an ability.
        "treasure",  # a predefined token type, not an ability.
        "double",  # an action word on a card's own text.
        "adapt",  # an activated ability, parsed as one.
        "landwalk",  # the umbrella name Scryfall prints beside the real one.
        "umbra armor",  # an ability-word-shaped label on a totem armour Aura.
    }
)

#: Ability words (CR 207.2c). They have no rules meaning at all, so a card
#: carrying one is not carrying an unexecuted keyword.
ABILITY_WORDS = frozenset(
    {"delirium", "ferocious", "metalcraft", "landfall", "flurry", "channel", "ascend"}
)


def executed_keywords(printing: Card) -> dict[str, str]:
    """Every keyword on this printing, mapped to the machine that acts on it.

    A keyword missing from the result has no execution path anywhere.
    """
    found: dict[str, str] = {}

    for keyword in Keyword:
        if any(k.lower() == keyword.value for k in printing.keywords):
            found[keyword.value] = "machines/combat.py"

    for option in keyword_cast_options(printing):
        where = "machines/casting.py" if option.understood else "machines/casting.py (unread cost)"
        found[option.keyword.lower()] = where

    if parse_mana_abilities(printing):
        for ability in keyword_abilities(printing):
            if ability.cost and "{T}" in ability.cost:
                found[ability.canonical.lower()] = "machines/abilities.py"

    # A keyword that is shorthand for an activated ability is executed as long
    # as the parser produced the activated ability - CR 702.29a's cycling is the
    # example, and the ability is what `Game.begin_activating` runs.
    activated = [a for a in parse_abilities(printing) if a.kind is AbilityKind.ACTIVATED]
    if activated:
        for ability in keyword_abilities(printing):
            if ability.canonical.lower() in {"equip", "adapt", "eternalize", "unearth"}:
                found[ability.canonical.lower()] = "machines/abilities.py (activated)"

    for keyword_name in printing.keywords:
        lowered = keyword_name.lower()
        if lowered in TIMING_KEYWORDS:
            # Flash: `machines/casting.why_cannot_cast_now` reads it (CR 702.8a).
            found[lowered] = "machines/casting.py (timing)"
        elif lowered in TARGET_LEGALITY_KEYWORDS:
            # Hexproof: `Casting.choose_targets` refuses the announcement.
            found[lowered] = "machines/casting.py (target legality)"
        elif lowered in ADDITIONAL_COST_KEYWORDS:
            # Kicker: `Casting.pay_kicker` charges it (CR 702.33a, CR 118.8a).
            found[lowered] = "machines/casting.py (additional cost)"
        elif lowered == "enchant":
            # CR 702.5a restricts what an Aura spell can target and what an Aura
            # can enchant. `Casting.choose_targets` refuses the announcement.
            found[lowered] = "machines/casting.py (target legality)"
        elif lowered == "protection":
            # The odd one out: protection is enforced in `models/game.py`
            # (`protection_qualities`/`protection_refusal`, CR 702.16b), which
            # is not one of the machines this sweep started out asking.
            found[lowered] = "models/game.py"
        elif keyword_machine.executes(keyword_name):
            found[lowered] = "machines/keywords.py"

    if adventure_face(printing) is not None:
        found["adventure"] = "machines/casting.py"

    # Escalate is a cast cost rather than a way to cast, so it is not a
    # KeywordCastOption - `Casting.pay_escalate` charges it (CR 702.120a).
    profile = modal_profile(printing)
    if profile is not None and profile.escalate_cost is not None:
        found["escalate"] = "machines/casting.py (additional cost)"
    # Entwine is an additional cost too (CR 702.42a), charged by
    # `Casting.choose_modes(entwined=True)`.
    if profile is not None and profile.entwine_cost is not None:
        found["entwine"] = "machines/casting.py (additional cost)"

    return found


def ignored_keywords(printing: Card) -> list[str]:
    """Keywords on this printing that nothing in the engine acts on."""
    executed = executed_keywords(printing)
    ignored = []
    for keyword in printing.keywords:
        lowered = keyword.lower()
        if lowered in executed or lowered in NEEDS_NO_CODE or lowered in ABILITY_WORDS:
            continue
        ignored.append(keyword)
    return sorted(ignored)


def has_effect_entry(printing: Card) -> bool:
    """Whether anything in the effect registries is keyed to this card."""
    if printing.name in EFFECTS:
        return True
    if any(key[0] == printing.name for key in TRIGGER_EFFECTS):
        return True
    return any(key[0] == printing.name for key in ACTIVATED_EFFECTS)


def has_rules_text(printing: Card) -> bool:
    """Whether the card says anything a resolution effect would have to do."""
    return any(ability.kind is not AbilityKind.KEYWORD for ability in parse_abilities(printing))


def report_keywords(names: list[str]) -> int:
    by_keyword: dict[str, list[str]] = defaultdict(list)
    for name in names:
        for keyword in ignored_keywords(card(name)):
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


def report_effects(names: list[str]) -> int:
    missing = [
        name for name in names if has_rules_text(card(name)) and not has_effect_entry(card(name))
    ]
    print("\nCards with rules text and no effect entry")
    print("-" * 62)
    for name in sorted(missing):
        print(f"  {name}")
    print(f"\n  {len(missing)} of {len(names)} cards resolve doing nothing")
    return len(missing)


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
    for ability in parse_abilities(printing):
        detail = getattr(ability, "cost", None) or getattr(ability, "parameter", None) or ""
        print(f"  {ability.kind.value:<10} {ability.text[:60]}  {detail}")
    executed = executed_keywords(printing)
    print("\n  keyword execution:")
    for keyword in printing.keywords:
        where = executed.get(keyword.lower())
        if where is None and keyword.lower() in NEEDS_NO_CODE | ABILITY_WORDS:
            where = "no code needed"
        print(f"    {keyword:<18} {where or 'IGNORED'}")
    print(f"\n  effect entry: {'yes' if has_effect_entry(printing) else 'no'}")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keywords", action="store_true", help="only the keyword report")
    parser.add_argument("--effects", action="store_true", help="only the effect report")
    parser.add_argument(
        "--targeting", action="store_true", help="only the unreadable-targeting report"
    )
    parser.add_argument("--card", help="report on one card by name")
    args = parser.parse_args(argv)

    if args.card:
        return report_card(args.card)

    names = sorted(pool())
    if not names:
        print(f"no cards in {CARD_POOL}")
        return 1

    if args.effects:
        report_effects(names)
        return 0
    if args.keywords:
        report_keywords(names)
        return 0
    if args.targeting:
        report_targeting(names)
        return 0

    report_keywords(names)
    report_effects(names)
    report_targeting(names)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
