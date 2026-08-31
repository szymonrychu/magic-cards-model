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
"""

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import NamedTuple

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
from magic_cards_model.machines.cost import (  # noqa: E402
    cost_modifier_effect,
    looks_like_unparsed_cost_modifier,
)
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
from magic_cards_model.models.card import Card, Layout, Type, types_of  # noqa: E402

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

#: Ability words (CR 207.2c: "An ability word appears in italics at the
#: beginning of some abilities. Ability words are similar to keywords in that
#: they tie together cards that have similar functionality, but they have no
#: special rules meaning"). A card carrying one is not carrying an unexecuted
#: keyword, so listing one here is never a coverage claim - the clause under
#: the word is judged on its own by `classify_card`, exactly like any other.
#:
#: `converge`, `revolt`, `undergrowth` and `domain` were reported as ignored
#: *keywords* by several deck sweeps, and every one of those reports was this
#: table's own false positive: `knowledge_search(type="rules")` returns no
#: numbered rule for any of the four - they are ability words, and nothing more
#: specific may be cited - and three of the four have their clause read by a
#: real parser today (`_parse_converge_exile_by_colors_spent`,
#: `Game.revolt_active_for` with `_parse_revolt_destroy_or_exile_clause`, and
#: `_parse_undergrowth_pump_and_fight_clause`). Listing a word here only stops
#: the *keyword* report claiming an execution path is missing; the clause the
#: word introduces is still judged on its own by `classify_card`, which is why
#: Territorial Kavu's domain characteristic-defining ability still reports as a
#: dead clause below rather than disappearing with the word.
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
        "converge",
        "revolt",
        "undergrowth",
        "domain",
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

    # Suspend (CR 702.62a) is not a `KeywordCastOption`: unlike Flashback's
    # static "from the graveyard, for this cost" grant, its free cast is a
    # dynamic `PlayPermission` handed out only once a *specific suspended
    # object* actually has zero time counters (`machines/casting.
    # finish_suspend`), the same Ugin/Ragavan shape `keyword_cast_options`
    # was never meant to cover. `MarkedExile.suspend` is CR 116.2f's special
    # action and `remove_suspend_time_counter` is the upkeep trigger; none of
    # them show up in `keyword_cast_options` output, so they are named here
    # by hand instead of falling through to "ignored".
    if any(k.lower() == "suspend" for k in printing.keywords):
        found["suspend"] = "machines/casting.py (MarkedExile.suspend, finish_suspend)"

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
    already covers it. A keyword line does not count either - the keyword
    report owns it.

    **A permanent's static line always counts.** It used to count only when
    `_layer_category` recognised a continuous-effect shape, on the reasoning
    that every other static line belongs to a subsystem this tool does not
    audit (a shockland's "you may pay life or it enters tapped" is
    `machines/replacement.py`'s, not `machines/effects.py`'s). The reasoning
    was right and the conclusion was backwards: "not audited here" is not
    "nothing to audit", and folding those lines into `no_rules_text` made a
    *count of cards this tool never looked at* read as coverage. Measured on
    the fixture pool, that silently cleared Grafdigger's Cage, Voice of
    Victory, Kaheera, Harbinger of the Seas and twenty others - every one of
    them a permanent carrying a real static ability (CR 604.2: "Static
    abilities create continuous effects"; CR 113.3d: "Static abilities are
    written as statements. They're simply true").

    They are now classified into their own bucket, `STATIC_UNAUDITED`, which
    is an explicit *unknown* and never a claim of coverage - see
    `_static_ability_category`. On a nonpermanent spell a static-kind line
    **is** the spell's own resolution text (CR 113.3a) and is judged through
    `effect_for` like any other resolution text.
    """
    for ability in parse_abilities(printing):
        if ability.kind is AbilityKind.KEYWORD:
            continue
        if (
            isinstance(ability, ActivatedAbility)
            and ability.mana is not None
            and ability.loyalty is None
        ):
            continue
        return True
    return _layer_category(printing) is not None


#: `effect_for`/`trigger_effect_for`/`activated_effect_for` fall back, on an
#: otherwise-unreadable clause, to one of these three inline stand-ins - see
#: `_ability_effect_or_notice`/`_spell_effect_or_notice` in `machines/effects.py`.
#: Each records a notice (`AnaphoricClauseNotice`, `DelayedClauseNotice`,
#: `ImprintNotice`, `UnmodeledTriggerEffectNotice`) and does nothing else,
#: which is correct, fail-closed behaviour rather than a card silently doing
#: nothing - so a dispatcher returning one of these by name is "notice", not
#: "handled".
_NOTICE_STAND_IN_NAMES = frozenset(
    {
        "anaphoric_notice_only",
        "delayed_notice_only",
        "imprint_notice_only",
        "conditional_notice_only",
        "cast_permission_notice_only",
        "unbounded_hand_choice_notice_only",
        "event_player_target_notice_only",
        "reflexive_notice_only",
        "suspend_redirect_notice_only",
        "damage_then_group_grant_notice_only",
        "control_replacement_notice_only",
    }
)

HANDLED = "handled"
NOTICE = "notice"
SILENT = "silent"
#: A permanent's own static ability (CR 604.2, CR 113.3d) that no part of this
#: tool audits: not a layer effect (`machines/layers.py`), so whichever
#: subsystem owns it - `machines/replacement.py`'s "enters tapped",
#: `machines/casting_restrictions.py`'s "your opponents can't cast spells
#: during your turn", `machines/cost.py`'s cost modifiers, `models/game.py`'s
#: protection - is the one that would have to answer for it. An explicit
#: unknown, deliberately its own bucket so it can never be counted as either
#: coverage or a bug.
STATIC_UNAUDITED = "static_unaudited"

#: Worst first. `classify_card` returns the worst outcome on the card, so a
#: dead clause can never hide behind a working one.
_SEVERITY: dict[str, int] = {SILENT: 0, STATIC_UNAUDITED: 1, NOTICE: 2, HANDLED: 3}


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
    # `front_oracle_text`, not the top-level field: a `transform` or
    # `modal_dfc` printing leaves `oracle_text` null and puts each face's text
    # on `card_faces`, so reading the top-level field scored eleven
    # double-faced cards SILENT whose layer text `parsed_layer_effects` reads
    # perfectly well - Flamescroll Celebrant's "{1}{R}: This creature gets
    # +2/+0" among them. That was a defect in this measurement, not in the
    # engine, and it is the same fallback `_spell_faces` below already makes.
    text = printing.front_oracle_text
    # `card_name=` mirrors `machines/layers.effects_for`'s own call - Ruby,
    # Daring Tracker's "Ruby gets +2/+2 until end of turn." is CR 201.5's
    # self-reference by literal printed name rather than CR 700.7's "this
    # creature"; without normalizing it the same way the real engine does,
    # this sweep would misjudge a trigger that resolves correctly in a real
    # game as an unrecognised shape.
    if printing.name in LAYER_EFFECTS or parsed_layer_effects(text, card_name=printing.name):
        return HANDLED
    # `static_only=True` for the same reason the battlefield sweep passes it:
    # without it, a *triggered* ability's own effect sentence ("... gets +X/+X
    # until end of turn") is mistaken for an unparsed static pump and reported
    # as a gap on a card whose trigger works perfectly (Kraul Harpooner).
    if looks_like_unparsed_layer_effect(text, static_only=True, card_name=printing.name):
        return NOTICE
    return None


#: The combat keywords `machines/layers.py` will actually accept in a grant
#: (`_KNOWN_KEYWORDS` there is this same enum), longest first so "first
#: strike" wins over a prefix of it.
_GRANTABLE_KEYWORDS = "|".join(
    sorted((re.escape(keyword.value) for keyword in Keyword), key=len, reverse=True)
)

#: Card types (CR 205.2a) and basic land types (CR 305.6: "The basic land
#: types are Plains, Island, Swamp, Mountain, and Forest") a board-wide type
#: grant hands out.
_GRANTABLE_TYPES = (
    r"artifacts?|creatures?|enchantments?|lands?|planeswalkers?|battles?"
    r"|Plains|Islands?|Swamps?|Mountains?|Forests?"
    r"|(?:every )?basic land types?"
)

#: Static shapes that are unmistakably `machines/layers.py`'s business (a
#: continuous effect, CR 611.3) and that `looks_like_unparsed_layer_effect`
#: does **not** recognise even as a near-miss, so today they produce no
#: `LayerNotice` and nothing else either: they fail silently **open**.
#:
#: This table is the sweep-side mirror of `machines/layers.
#: _LOOKS_LIKE_LAYER_EFFECT_RE`, which only opens on "target/this creature ..."
#: and "[other] creatures you control/your opponents control get|have ...".
#: Six cards in the fixture pool - Stormscale Scion ("Other Dragons you
#: control get +1/+1."), Kaheera, Harbinger of the Seas ("Nonbasic lands are
#: Islands."), Yavimaya, Leyline of the Guildpact and Toph - carry a real
#: unmodelled continuous effect and match none of it. Three of the six were
#: each found by hand, independently, by a different deck agent, which is the
#: whole reason this table exists: a detector that fails open makes every
#: other layer gap invisible.
#:
#: A sentence matched here is reported `SILENT`, not `NOTICE`: the engine
#: really does record nothing for it. Once `machines/layers.py` widens its own
#: regex (this plan's Task 1.3), these same sentences start producing a
#: `LayerNotice`, `looks_like_unparsed_layer_effect` answers first in
#: `_static_ability_category`, and they move to `NOTICE` on their own - the
#: two detectors are ordered so the engine's answer always wins over this
#: tool's guess.
_MISSED_LAYER_SHAPES: tuple[tuple[str, re.Pattern[str]], ...] = (
    # CR 613.4c - "Layer 7c: Effects and counters that modify power and/or
    # toughness ... are applied."
    ("layer 7c pump", re.compile(r"\bgets? [+-]\d+/[+-]\d+", re.IGNORECASE)),
    # CR 613.4a - "Layer 7a: Effects from characteristic-defining abilities
    # that define power and/or toughness are applied." Territorial Kavu's
    # domain P/T is the pool's example.
    (
        "layer 7a characteristic-defining P/T",
        re.compile(r"\bpower (?:and|or) toughness\b[^.]*\bequal to\b", re.IGNORECASE),
    ),
    # CR 613.1f - "Layer 6: Ability-adding effects ... are applied."
    (
        "layer 6 keyword grant",
        re.compile(rf"\b(?:has|have|gains?) (?:{_GRANTABLE_KEYWORDS})\b", re.IGNORECASE),
    ),
    # CR 613.1d - "Layer 4: Type-changing effects are applied."
    (
        "layer 4 type grant",
        re.compile(
            rf"\b(?:is|are) (?:an? )?(?:{_GRANTABLE_TYPES})\b"
            r"|\bin addition to (?:its|their) other\b",
            re.IGNORECASE,
        ),
    ),
    # CR 613.1e - "Layer 5: Color-changing effects are applied."
    (
        "layer 5 colour change",
        re.compile(r"\b(?:is|are) (?:all colors|colorless|the chosen color)\b", re.IGNORECASE),
    ),
)


def missed_layer_shape(text: str) -> str | None:
    """Which continuous-effect shape `text` is, when `machines/layers.py`
    neither parses it nor flags it - or `None` if it is not one of them.

    Read `_MISSED_LAYER_SHAPES` for why this exists and why a hit is `SILENT`.
    """
    for shape, pattern in _MISSED_LAYER_SHAPES:
        if pattern.search(text):
            return shape
    return None


def _static_ability_category(printing: Card, text: str) -> str:
    """One static line of a permanent (CR 604.2, CR 113.3d), judged the way
    the battlefield sweep judges it - per line, not per card.

    Per line is the whole point. `_layer_category` asks about a card's *whole*
    oracle text, so Basking Rootwalla's activated "{1}{G}: This creature gets
    +2/+2 until end of turn" answered for its unrelated static line too, and
    23 permanents' static abilities were reported clean on the strength of a
    clause that was not theirs.

    The order is: what the engine really reads (`LAYER_EFFECTS`, then
    `parsed_layer_effects`, then `machines/cost.cost_modifier_effect`), then
    what the engine really flags (`looks_like_unparsed_layer_effect`, then
    `looks_like_unparsed_cost_modifier`), then this tool's own near-miss table
    for the shapes the engine misses entirely (`missed_layer_shape`), and only
    then the honest `STATIC_UNAUDITED` unknown.

    The two cost-modifier calls are here because `Game.total_cost_for` really
    does run every battlefield permanent's own static lines through exactly
    those two functions, recording a `CostModifierNotice` for a line it cannot
    read - so a cost-modifier static that fails closed there is a `NOTICE`
    here, not an unknown.

    The one optimistic step left is `printing.name in LAYER_EFFECTS`: a
    name-keyed row cannot be attributed to a particular line, so it credits
    every static line on that card. This plan's Task 1.3 moves those rows to
    text shapes, which removes the ambiguity at the source.
    """
    if printing.name in LAYER_EFFECTS or parsed_layer_effects(text, card_name=printing.name):
        return HANDLED
    if cost_modifier_effect(text) is not None:
        return HANDLED
    if looks_like_unparsed_layer_effect(text, static_only=True, card_name=printing.name):
        return NOTICE
    if looks_like_unparsed_cost_modifier(text):
        return NOTICE
    if missed_layer_shape(text) is not None:
        return SILENT
    return STATIC_UNAUDITED


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


#: CR 107.3a's X, substituted into a card's own text before classification so
#: an X-bounded clause (Green Sun's Zenith's "mana value X or less", Fiend
#: Artisan's activated ability of the same shape) is judged on what it does
#: in a real game rather than on the untouched literal "X" no numeric parser
#: matches. Two values, deliberately, not one: 0 is CR 107.3a's own floor and
#: a legal choice a caster can make (Green Sun's Zenith for X=0 is a real,
#: legal cast that finds nothing per CR 701.23b -
#: `test_x_zero_is_a_legal_search_that_finds_nothing_above_its_own_bound`), so
#: probing only 0 would wrongly read a clause whose only readable shape needs
#: X>0 as silent, and probing only a nonzero value would miss the reverse.
#: 3 is an arbitrary nonzero probe: large enough that a small "or less"/"or
#: greater" bound is exercised meaningfully, small enough to stay a plausible
#: value nobody would mistake for anything else. `classify_card`'s own "best
#: outcome wins" rule (CR 608.2n) picks whichever probe a real dispatcher can
#: read, so trying both never scores a card worse than trying one.
_X_PROBE_VALUES: tuple[int, ...] = (0, 3)


def _x_candidates(cost_or_mana_cost: str | None) -> tuple[int | None, ...]:
    """Every X value `classify_card` should try for one clause.

    Mirrors `models/game.py`'s own gate for a real resolution
    (`"{X}" in (spell.mana_cost or "")` for a spell, `"{X}" in ability.ability.cost`
    for an activated ability): `None` - leave a bare "X" in the text alone,
    the same as a card that defines its own X in its rules text (CR 107.3f)
    rather than in its cost (CR 107.3a) - unless the cost that actually pays
    for this clause carries `{X}`, in which case every value in
    `_X_PROBE_VALUES` is tried.
    """
    if cost_or_mana_cost and "{X}" in cost_or_mana_cost:
        return _X_PROBE_VALUES
    return (None,)


class SpellFace(NamedTuple):
    """One face a real cast could put on the stack, with the characteristics
    that face brings with it (CR 712.8a/712.8d/712.8f).

    `is_permanent` is what tells a missing resolution effect from a gap: a
    permanent spell has no resolution text to run (CR 608.3a - "it becomes a
    permanent and enters the battlefield under the control of the spell's
    controller"; CR 301.2/302.2/303.2/306.2 say the same per type), so
    `effect_for` returning `None` for one is correct and must not be counted
    as a dead clause. On an instant or a sorcery the same `None` is exactly
    the bug this sweep exists to find.
    """

    name: str
    text: str
    mana_cost: str | None
    is_permanent: bool


def _spell_faces(printing: Card) -> list[SpellFace]:
    """The faces `classify_card` should feed to `effect_for`, one per face a
    real cast could put on the stack with only that face's own characteristics
    (CR 712.8a/712.8d/712.8f).

    `effect_for` never splits a combined "A // B" name itself the way
    `trigger_effect_for`/`activated_effect_for` do (see their own
    docstrings), and the printing's own top-level `oracle_text`/`mana_cost`
    are `None` on real Scryfall data for a split, transform or modal-DFC card
    - reading them directly is what let Wear // Tear and Sink into Stupor //
    Soporific Springs read as silent while their own scenario tests
    (`test_split_cards.py`, `test_mdfc_spell_side.py`) already pass.

    - **Layout.SPLIT** (CR 709.3): both halves are independently castable
      (CR 709.3a), so both faces are returned, each under its own name and
      text - never the combined printing's own blank top-level fields.
    - **Layout.MODAL_DFC** (CR 712.12): a land face is played as a CR 305.1
      special action, never cast, so it is dropped here; the remaining
      face(s) are returned by their own name/text/cost the same way.
    - **everything else** (a single-faced card, or a `transform` card whose
      only directly castable face is the front, CR 712.8a): one face, using
      `front_oracle_text` (already the right fallback for a blank top-level
      field, per its own docstring) and the front face's own name/cost where
      one exists, since a resolving `CardState`'s name is never the combined
      string either (`CardState.name`'s own docstring).
    """
    faces = printing.card_faces or []
    if printing.layout is Layout.SPLIT and faces:
        return [
            SpellFace(
                face.name,
                face.oracle_text or "",
                face.mana_cost,
                bool(set(types_of(face.type_line or "")) & _PERMANENT_TYPES),
            )
            for face in faces
        ]
    if printing.layout is Layout.MODAL_DFC and faces:
        return [
            SpellFace(
                face.name,
                face.oracle_text or "",
                face.mana_cost,
                bool(set(types_of(face.type_line or "")) & _PERMANENT_TYPES),
            )
            for face in faces
            if Type.LAND not in types_of(face.type_line or "")
        ]
    front = printing.front_face
    name = front.name if front is not None else printing.name
    mana_cost = front.mana_cost if front is not None else printing.mana_cost
    type_line = (front.type_line if front is not None else None) or printing.type_line
    return [
        SpellFace(
            name,
            printing.front_oracle_text,
            mana_cost,
            bool(set(types_of(type_line or "")) & _PERMANENT_TYPES),
        )
    ]


class ClauseOutcome(NamedTuple):
    """What one clause of a card really does: its category, the printed text
    it came from, and which dispatch path answered for it."""

    category: str
    text: str
    source: str


def _best(categories: list[str]) -> str:
    """The best of several answers for the *same* clause - used only across
    the CR 107.3a `{X}` probes, where a clause a dispatcher can read at one
    legal value of X is a clause that works in a real game."""
    return max(categories, key=lambda category: _SEVERITY[category])


def classify_clauses(printing: Card) -> list[ClauseOutcome]:
    """Every clause of this card, judged on its own.

    Calls the production dispatchers - `effect_for`, `trigger_effect_for`,
    `activated_effect_for` - with the exact arguments `models/game.py` calls
    them with for a resolving spell, a resolving triggered ability and a
    resolving activated ability in turn, so this can never drift from what the
    engine actually does the way keying on registry membership did.

    The top-level spell dispatch runs once per `_spell_faces` entry - both
    halves of a split card, the non-land face(s) of a modal DFC, or just the
    one face everything else has - rather than once against the combined
    printing, and every clause whose paying cost carries CR 107.3a's `{X}`
    (a spell's own mana cost, or an activated ability's own cost) is tried at
    every value in `_x_candidates`/`_X_PROBE_VALUES` rather than left with
    the literal, unsubstituted "X" no numeric parser matches. Those probes are
    the one place a *best* answer is taken (`_best`): they are several askings
    of one clause, not several clauses.

    Five things never reach a dispatcher and are read directly instead:

    - a **land** (`Card.is_land`, CR 305.1) is played as a special action and
      never goes on the stack at all (`Game.play_land`), so `effect_for` is
      never called for one in a real game either.
    - a **permanent spell's resolution** (CR 608.3a: "it becomes a permanent
      and enters the battlefield under the control of the spell's
      controller"). There is no resolution text to run, so a `None` from
      `effect_for` is correct and is dropped rather than recorded as a dead
      clause - the permanent's own abilities are judged below, one by one. A
      permanent face that *does* get an effect keeps it: the credit is real.
    - a **mana ability** (CR 605.1a) never goes on the stack at all
      (`Game.activate_ability`), so it is skipped rather than misreported as
      silent - the keyword/mana report already covers it.
    - a **triggered ability whose condition `machines/triggers.py` does not
      recognise** (`event is None`) never triggers in a real game either
      (`matches_condition`'s own docstring: "a condition this module cannot
      read never fires"), so it is counted silent directly rather than asked
      about, because asking would wrongly credit a card with a mechanism that
      never runs.
    - a **permanent's static ability** (CR 604.2, CR 113.3d) is a continuous
      effect, not a resolution: `_static_ability_category` judges it line by
      line against `machines/layers.py`.
    """
    clauses: list[ClauseOutcome] = []
    is_permanent = bool(set(printing.types) & _PERMANENT_TYPES)

    if not printing.is_land:
        for face in _spell_faces(printing):
            categories = [
                _dispatch_category(effect_for(face.name, face.text, x_value=x_value), printing)
                for x_value in _x_candidates(face.mana_cost)
            ]
            category = _best(categories)
            if face.is_permanent and category not in (HANDLED, NOTICE):
                # CR 608.3a - a permanent spell's resolution has no text to
                # run, so "no effect" is the correct answer for one and is not
                # a clause at all. Its own abilities are judged below. A
                # permanent face that *does* produce an effect or a notice
                # keeps the credit: that part is real.
                continue
            clauses.append(ClauseOutcome(category, face.text, "spell"))

    activated_index = 0
    for ability in parse_abilities(printing):
        if isinstance(ability, ActivatedAbility):
            index = activated_index
            activated_index += 1
            if ability.mana is not None and ability.loyalty is None:
                continue
            if ability.class_level_target is not None:
                # CR 716.2a: "[Cost]: Level N" means "this Class's level
                # becomes N", and that is the whole ability - the bar has no
                # effect body for `activated_effect_for` to return, because
                # the mechanic lives in `Game.activate_ability`
                # (models/game.py:2543) and the level gating in
                # `CardState`'s CR 716.2a reader. Asking the effect registry
                # about it scored four Class cards SILENT for a mechanic that
                # is fully implemented. The abilities the level unlocks are
                # separate clauses and are judged on their own below.
                clauses.append(ClauseOutcome(HANDLED, ability.text, "activated"))
                continue
            categories = [
                _dispatch_category(
                    activated_effect_for(printing.name, index, ability.effect, x_value=x_value),
                    printing,
                )
                for x_value in _x_candidates(ability.cost)
            ]
            clauses.append(ClauseOutcome(_best(categories), ability.text, "activated"))
        elif isinstance(ability, TriggeredAbility):
            if ability.event is None:
                clauses.append(ClauseOutcome(SILENT, ability.text, "triggered (unread condition)"))
                continue
            effect = trigger_effect_for(printing.name, ability.event, ability.effect)
            clauses.append(
                ClauseOutcome(_dispatch_category(effect, printing), ability.text, "triggered")
            )
        elif ability.kind is AbilityKind.STATIC and is_permanent:
            clauses.append(
                ClauseOutcome(
                    _static_ability_category(printing, ability.text), ability.text, "static"
                )
            )

    return clauses


def classify_card(printing: Card) -> tuple[str, str]:
    """The real outcome of playing this card, and the clause the answer came
    from.

    **The worst clause wins.** This used to report the best outcome seen
    anywhere on the card, on the reading that CR 608.2n leaves an ability with
    no effect still having gone on the stack, so a card was only dead if
    *nothing* on it did anything. That is a defensible thing to measure and it
    is not the thing this tool is for: it let Territorial Kavu's dead
    characteristic-defining ability hide behind its working attack trigger,
    Obsidian Charmaw's dead cost reduction hide behind its working ETB, and
    Engineered Explosives' dead sunburst hide behind its working activation -
    and 20 agents read all three as covered on the same day.

    `classify_clauses` has each clause's own answer if a caller wants the
    whole picture rather than the summary.
    """
    clauses = classify_clauses(printing)
    if not clauses:
        # Nothing `parse_abilities` calls a clause, but the card's own text
        # still reads as a continuous effect (`has_rules_text`'s own last
        # resort) - answer with that rather than inventing a silent clause.
        return _layer_category(printing) or SILENT, ""
    worst = min(clauses, key=lambda clause: _SEVERITY[clause.category])
    return worst.category, worst.text


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
    """Sort every clause of every card with rules text into handled / notice /
    static_unaudited / silent, and print the two buckets that are not
    coverage: the dead clauses, and the static abilities nothing here audits.

    A vanilla creature (no rules text at all) is not asked about - it is
    correct for one to have no effect, and `has_rules_text` is the same gate
    `classify_card` itself is meaningless without.

    The counts are **per card, by its worst clause** (`classify_card`), and
    the dead-clause list names the clause, so a card that is 90% working and
    10% dead is listed with the 10% rather than counted as fine.
    """
    with_text = [name for name in names if has_rules_text(card(name))]
    counts: dict[str, int] = {HANDLED: 0, NOTICE: 0, STATIC_UNAUDITED: 0, SILENT: 0}
    silent: list[tuple[str, str]] = []
    unaudited: list[tuple[str, str]] = []
    for name in with_text:
        category, detail = classify_card(card(name))
        counts[category] += 1
        if category == SILENT:
            silent.append((name, detail))
        elif category == STATIC_UNAUDITED:
            unaudited.append((name, detail))

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

    print(
        f"\n  {len(silent)} of {len(with_text)} cards with rules text have a clause that does "
        f"nothing and logs nothing\n  ({counts[HANDLED]} handled by a registry row or a parser, "
        f"{counts[NOTICE]} fail closed with a notice, "
        f"{counts[STATIC_UNAUDITED]} rest on a static ability nobody here audits)"
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
        print("\n  clause outcomes:")
        for clause in classify_clauses(printing):
            print(f"    {clause.category:<17} [{clause.source}] {clause.text[:60]}")
        category, detail = classify_card(printing)
        print(f"\n  outcome (worst clause): {category}" + (f" - {detail[:70]}" if detail else ""))
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
