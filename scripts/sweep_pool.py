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
arguments `models/game.py` calls them with, and sorts the result into three
buckets: **handled** (a registry row or a parser produced a real effect),
**notice** (the engine recognised the text and fails closed with one of the
notices above, which is correct behaviour), and **silent** (nothing happened and
nothing was recorded - the only bucket that is actually a bug).

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
    ActivatedAbility,
    TriggeredAbility,
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
    activated_effect_for,
    create_continuous_effect,
    create_continuous_effect_of_ability,
    effect_for,
    parse_mode_effect,
    resolve_modal_spell,
    trigger_effect_for,
)
from magic_cards_model.machines.layers import (  # noqa: E402
    LAYER_EFFECTS,
    looks_like_unparsed_layer_effect,
    parsed_layer_effects,
)
from magic_cards_model.machines.modes import modal_profile  # noqa: E402
from magic_cards_model.machines.targeting import profile_for_text  # noqa: E402
from magic_cards_model.models.card import Card, Type  # noqa: E402

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
    {
        "delirium",
        "ferocious",
        "metalcraft",
        "landfall",
        "flurry",
        "channel",
        "ascend",
        "imprint",
    }
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


#: Card types a permanent can have (CR 205.2a). Used only to tell a
#: permanent's own **static** ability line (owned by whichever subsystem
#: reads it - `machines/replacement.py`'s "enters tapped", `machines/
#: combat.py`'s restrictions, `models/game.py`'s protection, none of them
#: `machines/effects.py`) from an instant or sorcery's resolution text, which
#: `abilities.py` also files under `AbilityKind.STATIC` (CR 113.3a: "the text
#: of an instant or sorcery is not a static ability, but this parser does not
#: read type lines") and which very much is `effect_for`'s business.
_PERMANENT_TYPES = frozenset(
    {Type.ARTIFACT, Type.BATTLE, Type.CREATURE, Type.ENCHANTMENT, Type.LAND, Type.PLANESWALKER}
)


def has_rules_text(printing: Card) -> bool:
    """Whether the card has anything `classify_card` can actually judge.

    A pure mana ability (CR 605.1a) never counts: it never reaches a
    dispatcher (`classify_card` skips it too), and the keyword/mana report
    already covers it. A **static** line only counts for a permanent when it
    looks like a continuous-effect shape (`_layer_category`) - every other
    static line on a permanent belongs to a subsystem this tool does not
    audit, and counting it would flag cards like a shockland (a `machines/
    replacement.py` "you may pay life or it enters tapped" line) as silently
    doing nothing for a mechanism `machines/effects.py` was never going to
    own. On a nonpermanent spell a static-kind line **is** the spell's own
    resolution text and always counts.
    """
    is_permanent = bool(set(printing.types) & _PERMANENT_TYPES)
    for ability in parse_abilities(printing):
        if ability.kind is AbilityKind.KEYWORD:
            continue
        if (
            isinstance(ability, ActivatedAbility)
            and ability.mana is not None
            and ability.loyalty is None
        ):
            continue
        if ability.kind is AbilityKind.STATIC and is_permanent:
            continue
        return True
    return _layer_category(printing) is not None


#: `effect_for`/`trigger_effect_for`/`activated_effect_for` fall back, on an
#: otherwise-unreadable clause, to one of these three inline stand-ins - see
#: `_ability_effect_or_notice`/`_spell_effect_or_notice` in `machines/effects.py`.
#: Each records a notice (`AnaphoricClauseNotice`, `DelayedClauseNotice`,
#: `ImprintNotice`) and does nothing else, which is correct, fail-closed
#: behaviour rather than a card silently doing nothing - so a dispatcher
#: returning one of these by name is "notice", not "handled".
_NOTICE_STAND_IN_NAMES = frozenset(
    {"anaphoric_notice_only", "delayed_notice_only", "imprint_notice_only"}
)

HANDLED = "handled"
NOTICE = "notice"
SILENT = "silent"


def _layer_category(printing: Card) -> str | None:
    """Handled/notice for this card's own continuous-effect text (CR 611.2,
    CR 611.3), read exactly the way the battlefield sweep
    (`machines/layers.effects_for`) reads it: `LAYER_EFFECTS` first, then
    `parsed_layer_effects` on the card's own oracle text, and - only if neither
    reads it - `looks_like_unparsed_layer_effect` for a `LayerNotice`.

    `None` when nothing about the text even looks like a pump, keyword grant,
    base P/T set, "becomes a creature" or anthem shape: that is not this
    sweep's business at all, the same way a combat restriction or a cost
    modifier is not `machines/layers.py`'s. Only a genuine near-miss on one of
    those four shapes counts as a gap here.
    """
    text = printing.oracle_text
    if printing.name in LAYER_EFFECTS or parsed_layer_effects(text) is not None:
        return HANDLED
    if looks_like_unparsed_layer_effect(text):
        return NOTICE
    return None


def _modal_category(printing: Card) -> str:
    """Handled/notice/silent for a modal spell, mirroring `resolve_modal_spell`
    mode by mode: it runs whichever chosen mode's text `parse_mode_effect`
    reads and appends a `ModeNotice` for one it cannot, per mode - so a card
    with at least one readable mode is "handled" (some chosen mode really does
    something), and one where every mode is unreadable is "notice" rather than
    "silent", because choosing *any* mode of it always leaves a `ModeNotice`
    behind. An unrecognised modal structure (`understood=False`) never reaches
    `resolve_modal_spell`'s per-mode loop at all and is silent with no notice.
    """
    modal = modal_profile(printing)
    if modal is None or not modal.understood or not modal.modes:
        return SILENT
    if any(parse_mode_effect(mode, 0) is not None for mode in modal.modes):
        return HANDLED
    return NOTICE


def _dispatch_category(effect: object, printing: Card) -> str:
    """What actually happens if `effect` - what a real dispatcher just
    returned for this card - runs: a real effect, a fail-closed notice, or
    nothing at all. `effect` is always the literal object `effect_for`,
    `trigger_effect_for` or `activated_effect_for` returned, so this never
    re-derives what those functions already decided - it only reads the
    shape of their answer.
    """
    if effect is None:
        return SILENT
    if effect is create_continuous_effect or effect is create_continuous_effect_of_ability:
        # `_layer_category` never actually falls through to `None` from this
        # path - `looks_like_unparsed_layer_effect`'s own regex is a superset
        # of the one that routed here in the first place - but SILENT is the
        # right default if it ever did, not an optimistic HANDLED.
        return _layer_category(printing) or SILENT
    if effect is resolve_modal_spell:
        return _modal_category(printing)
    if getattr(effect, "__name__", "") in _NOTICE_STAND_IN_NAMES:
        return NOTICE
    return HANDLED


def classify_card(printing: Card) -> tuple[str, str]:
    """The real outcome of playing this card, and one example clause when the
    answer is the dangerous one.

    Calls the production dispatchers - `effect_for`, `trigger_effect_for`,
    `activated_effect_for` - with the exact arguments `models/game.py` calls
    them with for a resolving spell, a resolving triggered ability and a
    resolving activated ability in turn, so this can never drift from what the
    engine actually does the way keying on registry membership did. The card's
    overall answer is the best one seen anywhere on it (CR 608.2n: an ability
    with no effect still went on the stack and is not the card's only ability),
    because a card is only genuinely dead if *nothing* on it does anything.

    Three things never reach a dispatcher and are read directly instead:

    - a **land** (`Card.is_land`, CR 305.1) is played as a special action and
      never goes on the stack at all (`Game.play_land`), so `effect_for` is
      never called for one in a real game either - asking it would report a
      shockland's own "you may pay life or it enters tapped" replacement
      effect as silent for a mechanism `effect_for` was never going to own.
    - a **mana ability** (CR 605.1a) never goes on the stack at all
      (`Game.activate_ability`), so it is skipped rather than misreported as
      silent - the keyword/mana report already covers it.
    - a **triggered ability whose condition `machines/triggers.py` does not
      recognise** (`event is None`) never triggers in a real game either
      (`matches_condition`'s own docstring: "a condition this module cannot
      read never fires"), so it is counted silent directly rather than asked
      about, because asking would wrongly credit a card with a mechanism that
      never runs.
    """
    outcomes: list[tuple[str, str]] = []

    if not printing.is_land:
        outcomes.append(
            (_dispatch_category(effect_for(printing.name, printing.oracle_text), printing), "")
        )

    activated_index = 0
    for ability in parse_abilities(printing):
        if isinstance(ability, ActivatedAbility):
            index = activated_index
            activated_index += 1
            if ability.mana is not None and ability.loyalty is None:
                continue
            effect = activated_effect_for(printing.name, index, ability.effect)
            outcomes.append((_dispatch_category(effect, printing), ability.text))
        elif isinstance(ability, TriggeredAbility):
            if ability.event is None:
                outcomes.append((SILENT, ability.text))
                continue
            effect = trigger_effect_for(printing.name, ability.event, ability.effect)
            outcomes.append((_dispatch_category(effect, printing), ability.text))

    layer_only = _layer_category(printing)
    if layer_only is not None:
        outcomes.append((layer_only, ""))

    for wanted in (HANDLED, NOTICE):
        for category, detail in outcomes:
            if category == wanted:
                return category, detail
    silent_detail = next((detail for category, detail in outcomes if detail), "")
    return SILENT, silent_detail


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
    """Sort every card with rules text into handled / notice / silent, and
    print the only bucket that is actually a bug.

    A vanilla creature (no rules text at all) is not asked about - it is
    correct for one to have no effect, and `has_rules_text` is the same gate
    `classify_card` itself is meaningless without.
    """
    with_text = [name for name in names if has_rules_text(card(name))]
    handled = 0
    notices = 0
    silent: list[tuple[str, str]] = []
    for name in with_text:
        category, detail = classify_card(card(name))
        if category == HANDLED:
            handled += 1
        elif category == NOTICE:
            notices += 1
        else:
            silent.append((name, detail))

    print("\nCards that would do nothing at all if played right now")
    print("-" * 62)
    if not silent:
        print("  none - every card with rules text is handled or fails closed with a notice")
    for name, detail in sorted(silent):
        print(f"  {name}")
        if detail:
            print(f"    {detail[:70]}")
    print(
        f"\n  {len(silent)} of {len(with_text)} cards with rules text do nothing and log "
        f"nothing\n  ({handled} handled by a registry row or a parser, "
        f"{notices} fail closed with a notice)"
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
    if has_rules_text(printing):
        category, detail = classify_card(printing)
        print(f"\n  outcome: {category}" + (f" - {detail[:70]}" if detail else ""))
    else:
        print("\n  outcome: n/a (no rules text)")
    return 0


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
