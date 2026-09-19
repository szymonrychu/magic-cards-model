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
from collections.abc import Callable
from functools import cache
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
from magic_cards_model.machines.combat import Keyword, is_attack_requirement_line  # noqa: E402
from magic_cards_model.machines.cost import (  # noqa: E402
    cost_announces_x,
    cost_modifier_effect,
    looks_like_unparsed_cost_modifier,
)
from magic_cards_model.machines.effects import (  # noqa: E402
    activated_effect_for,
    create_continuous_effect,
    create_continuous_effect_of_ability,
    effect_for,
    modal_trigger_profile,
    mode_effect_body,
    parse_mixed_effect,
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
from magic_cards_model.machines.objects_as_costs import has_improvise  # noqa: E402
from magic_cards_model.machines.targeting import profile_for_text  # noqa: E402
from magic_cards_model.machines.triggers import (  # noqa: E402
    _ENTERS_TAPPED_RE as _CONDITION_ENTERS_TAPPED_RE,
)
from magic_cards_model.machines.triggers import (  # noqa: E402
    _ENTERS_UNTAPPED_RE as _CONDITION_ENTERS_UNTAPPED_RE,
)
from magic_cards_model.machines.triggers import (  # noqa: E402
    _ENTERS_WITH_COUNTER_RE as _CONDITION_ENTERS_WITH_COUNTER_RE,
)
from magic_cards_model.machines.triggers import (  # noqa: E402
    _STATE_COUNTER_TRIGGER_RE,
    GameEvent,
    TriggerEvent,
    _unread_trigger_events,
    condition_matches,
)
from magic_cards_model.machines.triggers import (  # noqa: E402
    _required_entering_subtype as _condition_required_entering_subtype,
)
from magic_cards_model.machines.triggers import (  # noqa: E402
    _required_subtype as _condition_required_subtype,
)
from magic_cards_model.machines.triggers import (  # noqa: E402
    _required_types as _condition_required_types,
)
from magic_cards_model.models import CardState, Game, Player, Zone  # noqa: E402
from magic_cards_model.models.card import Card, Layout, Type, types_of  # noqa: E402
from magic_cards_model.models.card_state import Counters  # noqa: E402

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

    # Fuse (CR 702.102a) is a choice made *before* announcing which half of a
    # split card to cast, not a `KeywordCastOption` (it grants no new zone or
    # cost, just a different `Casting.cast_as_split_half` step -
    # `Casting.cast_fused`) - so it never shows up in `keyword_cast_options`
    # output either. Named here by hand, the same way suspend is above.
    if any(k.lower() == "fuse" for k in printing.keywords):
        found["fuse"] = "machines/casting.py (Casting.cast_fused, CR 702.102)"

    # Unearth (CR 702.84a) and transmute (CR 702.53a) are activated abilities
    # that function off the battlefield (CR 113.6j/113.6m), same as cycling -
    # `machines/keywords.off_zone_abilities` is the one index space all three
    # share (`ACTIVATE_OFF_ZONE`'s own seat-facing entry point), so it is read
    # directly here instead of the weaker "any unrelated activated ability
    # plus this keyword name" heuristic further down, which never actually
    # asked whether *this* keyword's own ability existed.
    for entry in keyword_machine.off_zone_abilities(printing):
        if entry.keyword is not None:
            found[entry.keyword.lower()] = (
                f"machines/keywords.py (off_zone_abilities: {entry.family})"
            )

    # Sunburst (CR 702.44a) is a replacement effect that applies as the
    # object is *entering* the battlefield, not a resolution instruction, so
    # it is read off the keyword by `machines/replacement.py`'s
    # `_self_enters_modifiers`/`_sunburst_modifier` alongside every other
    # CR 614.1c "enters with N counters" clause - a different module from
    # every other keyword this sweep already knows how to find.
    if any(k.lower() == "sunburst" for k in printing.keywords):
        found["sunburst"] = "machines/replacement.py (_sunburst_modifier, CR 702.44a)"

    # Affinity (CR 702.41a) is a cost *reduction* read off the spell's own
    # text ("Affinity for [text]") - `Game.cost_reduction_for`'s `_AFFINITY_RE`
    # counts matching permanents and folds the result into `Casting.
    # total_cost` for every ordinary cast, so nothing in `keyword_cast_options`
    # (a *way to cast*, not a discount) or `ADDITIONAL_COST_KEYWORDS` (an
    # additional cost, not a reduction) was ever going to name it. Named here
    # by hand, the same way suspend is above.
    if any(k.lower() == "affinity" for k in printing.keywords):
        found["affinity"] = "models/game.py (Game.cost_reduction_for, CR 702.41a)"

    # Improvise (CR 702.126a) changes *what pays* {1} of an already-determined
    # total cost - the same "not an additional or alternative cost" shape as
    # convoke/delve (`machines/keywords.executes`), except improvise's own
    # machinery lives in `machines/objects_as_costs.py`, a module this sweep
    # otherwise never asks about. `Game.cast(improvise=...)` and `Game.
    # object_cost_offers["improvise"]` are the two seat-facing entry points
    # (`tests/scenarios/test_improvise.py` exercises both end to end).
    if has_improvise(printing):
        found["improvise"] = "machines/objects_as_costs.py (improvise)"

    # Splice (CR 702.47a) is a static ability of a card sitting in *hand*,
    # revealed while casting a *different* spell - so it never shows up on
    # its own `keyword_cast_options` (it grants nothing to spliced-onto card
    # itself) and it is not an additional cost of the card that carries it
    # either. `Casting.splice`/`.splice_by_id` and `Game.cast(splice=...)`
    # are the real machinery; named here for the same reason suspend is.
    if any(k.lower() == "splice" for k in printing.keywords):
        found["splice"] = "machines/casting.py (Casting.splice, splice_candidates)"

    # Companion (CR 702.139a) functions outside the game, not as a
    # `KeywordCastOption` either: the deck-legality condition is
    # `machines/companion.py`'s own read of the printed "Companion—
    # [Condition]." line, and the in-game half is CR 116.2g's special action
    # (`Game.why_cannot_bring_companion_to_hand`/`begin_bringing_companion_
    # to_hand`/`bring_companion_to_hand`), so neither shows up in
    # `keyword_cast_options` output and both are named here by hand.
    if any(k.lower() == "companion" for k in printing.keywords):
        found["companion"] = "machines/companion.py, models/game.py (bring_companion_to_hand)"

    return found


#: CR 207.2d: "flavor words appear in italics at the beginning of some
#: abilities ... [and] have no special rules meaning". Scryfall lists a
#: mode's label as a keyword (Flash Thompson's "\u2022 Heckle \u2014 Tap target
#: creature."), but there is nothing for any machine to execute.
_FLAVOR_WORD_LABEL = re.compile(r"^\u2022\s*(?P<word>[^\u2014\n]+?)\s+\u2014\s+", re.MULTILINE)


def flavor_words(printing: Card) -> frozenset[str]:
    """The words this printing uses only as a mode's flavor-word label."""
    return frozenset(
        match.group("word").strip().lower()
        for match in _FLAVOR_WORD_LABEL.finditer(printing.oracle_text or "")
    )


def ignored_keywords(printing: Card) -> list[str]:
    """Keywords on this printing that nothing in the engine acts on."""
    executed = executed_keywords(printing)
    flavor = flavor_words(printing)
    ignored = []
    for keyword in printing.keywords:
        lowered = keyword.lower()
        if (
            lowered in executed
            or lowered in NEEDS_NO_CODE
            or lowered in ABILITY_WORDS
            or lowered in flavor
        ):
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
        "search_description_notice_only",
        "layer_effect_with_remainder_notice",
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

#: A triggered ability whose `event` parsed cleanly but whose printed
#: *condition* `machines/triggers.condition_matches` can never satisfy for any
#: real, reachable permanent - Weapons Manufacturing's own "a nontoken
#: artifact you control enters", inverted by a substring bug into "must be a
#: token". Distinct from `SILENT` on purpose (see `_condition_can_fire`'s own
#: docstring): a card that never triggers at all is a different bug from one
#: that triggers and does nothing, and the two are tracked separately so
#: neither hides behind the other in the report.
UNMATCHABLE_CONDITION = "unmatchable_condition"

#: A clause whose dispatcher answer is a real, non-`None` effect only because
#: a regex read into a *quoted* span of the clause's own text - Weapons
#: Manufacturing's granted-ability quote, not its own clause, is what
#: `_DAMAGE_TARGET_RE`'s unanchored `.*` prefix actually matched. A wrong
#: parse wearing a correct-looking result, so it must not read `HANDLED`
#: either.
QUOTED_EFFECT = "quoted_effect"

#: Worst first. `classify_card` returns the worst outcome on the card, so a
#: dead clause can never hide behind a working one. The two new buckets sit
#: below `SILENT`: a clause that can never fire, or whose only "effect" is a
#: misparse, is at least as broken as one that fires and does nothing.
_SEVERITY: dict[str, int] = {
    UNMATCHABLE_CONDITION: 0,
    QUOTED_EFFECT: 1,
    SILENT: 2,
    STATIC_UNAUDITED: 3,
    NOTICE: 4,
    HANDLED: 5,
}


def _worse(a: str, b: str) -> str:
    """The more severe of two clause categories - `_best`'s mirror image,
    used to fold the quoted-text finding into whatever `_dispatch_category`
    already decided without ever raising it back to `HANDLED`."""
    return min((a, b), key=lambda category: _SEVERITY[category])


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
    if is_attack_requirement_line(text, printing.name):
        # CR 508.1d: `Game.declare_attackers` enforces it.
        return HANDLED
    return STATIC_UNAUDITED


def _modal_category(printing: Card) -> str:
    """Handled/notice/silent for a modal spell, mirroring `resolve_modal_spell`
    mode by mode: it runs whichever chosen mode's text `parse_mode_effect`
    reads and appends a `ModeNotice` for one it cannot, per mode.

    **The worst mode wins**, the identical rule `classify_card` already
    applies across a whole card's clauses (see its own docstring): CR 700.2a
    lets a player choose *any* mode, with no rule that the chosen one has to
    be the readable one, so a card is only genuinely `HANDLED` when *every*
    one of its modes would actually do something if chosen - Vraska's Final
    Mercy's own mode 2 ("lose 2 life. Empower Jace 6.") is a legal choice
    that currently does nothing, and scoring the card `HANDLED` on the
    strength of mode 1 alone hid that the same way Territorial Kavu's
    working attack trigger used to hide its own dead characteristic-defining
    ability. A card where *no* mode reads is still `NOTICE` rather than
    `SILENT`, because choosing any mode of it leaves a `ModeNotice` behind.
    An unrecognised modal structure (`understood=False`) never reaches
    `resolve_modal_spell`'s per-mode loop at all and is silent with no
    notice.
    """
    modal = modal_profile(printing)
    if modal is None or not modal.understood or not modal.modes:
        return SILENT
    if all(parse_mode_effect(mode, 0) is not None for mode in modal.modes):
        return HANDLED
    return NOTICE


def _modal_trigger_category(effect_text: str) -> str | None:
    """`_modal_category`'s own worst-mode rule, for a modal *triggered*
    ability's "choose one/one or both -" tail (CR 700.2, CR 603.3c -
    Fateshaper Aspirant, Yuriko, Hope from the Shadows) rather than a modal
    spell's.

    `None` when `effect_text` is not this shape at all - `_dispatch_
    category`'s cue to fall through to its ordinary identity-based
    dispatch. `_resolve_modal_triggered_ability_clause`'s own closure has no
    fixed identity to compare against the way `resolve_modal_spell` does (a
    fresh closure is built on every call), so without this a modal
    triggered ability's *whole* ability fell to `_dispatch_category`'s
    default `HANDLED` the moment `trigger_effect_for` returned any non-`None`
    callable at all - true the instant *one* mode read, wrong for every
    other mode beside it, the identical "best mode wins" defect
    `_modal_category` itself was fixed for.
    """
    profile = modal_trigger_profile(effect_text)
    if profile is None:
        return None
    if all(parse_mixed_effect(mode_effect_body(mode)) is not None for mode in profile.modes):
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


# ---------------------------------------------------------------------------
# The condition-matching closure (docs/2026-09-08-trigger-findings.md, "The
# sweeper's blind spot, which matters beyond this card"). `classify_clauses`
# used to ask only whether `trigger_effect_for` produced a callable, never
# whether `machines/triggers.condition_matches` (CR 603.2) could ever be
# satisfied by a real permanent. Weapons Manufacturing's "a nontoken artifact
# you control enters" scored `handled` this way: its event parses, and a
# fallback parser (see the quoted-text closure below) produced a callable,
# but the substring guard `condition_matches` uses for "one or more tokens
# you control enter" also matches "nontoken", inverting the restriction, so
# no real nontoken artifact entering ever fires it.
#
# `_condition_can_fire` answers by building a real, throwaway board and
# asking the production `condition_matches` about it - never by re-deriving
# what the condition is supposed to mean and comparing, which would just
# mirror whatever `condition_matches` itself gets wrong. The one place this
# module *does* read the condition text on its own is `_intended_token_
# requirement`, and deliberately: `condition_matches`'s own "token" in
# lowered check is exactly the known bug, so trusting it to build the very
# permanent used to test it would hide the bug instead of catching it.
# ---------------------------------------------------------------------------

#: The event kinds this closure knows how to build a synthetic occurrence
#: for: every one of them asks about a *permanent* (the source itself, or
#: another one under some controller), so a real `CardState` on a real
#: battlefield is all `condition_matches` needs to answer honestly. Every
#: other `TriggerEvent` (a cast, a draw, damage, life change, a step
#: beginning...) needs a player- or spell-shaped event this closure does not
#: attempt to synthesize - `_condition_can_fire` abstains (`None`) for those
#: rather than guess.
_SYNTHESIZABLE_EVENTS = frozenset(
    {
        TriggerEvent.ENTERS_THE_BATTLEFIELD,
        TriggerEvent.DIES,
        TriggerEvent.IS_SACRIFICED,
        TriggerEvent.ATTACKS,
        TriggerEvent.BLOCKS,
        TriggerEvent.BECOMES_TAPPED,
        TriggerEvent.BECOMES_UNTAPPED,
    }
)

_NONTOKEN_WORD_RE = re.compile(r"\bnontoken\b")
_TOKEN_WORD_RE = re.compile(r"\btokens?\b")


def _intended_token_requirement(condition: str) -> bool | None:
    """What `condition`'s own printed text says about whether its subject
    must (CR 111.1) be a token, or must not - read independently of
    `machines/triggers.condition_matches`'s own `"token" in lowered` check,
    which does not special-case "nontoken" and so ends up demanding the
    *opposite* of what a "nontoken" condition prints (Weapons Manufacturing,
    Miirym, Sentinel Wyrm; `docs/2026-09-08-trigger-findings.md`). `None`
    when the condition names neither word, meaning tokenhood is not
    restricted at all - a synthetic permanent may be built either way.
    """
    lowered = condition.lower()
    if _NONTOKEN_WORD_RE.search(lowered):
        return False
    if _TOKEN_WORD_RE.search(lowered):
        return True
    return None


@cache
def _cards_by_subtype() -> dict[str, tuple[Card, ...]]:
    """A handful of real printings for each subtype the pool has any of, so a
    condition naming one ("a Mountain you control enters", "another Dragon
    you control enters") can be tested against a genuine example rather than
    only the printing under test."""
    index: dict[str, list[Card]] = defaultdict(list)
    for printing in pool().values():
        for subtype in printing.subtypes:
            if len(index[subtype]) < 5:
                index[subtype].append(printing)
    return {subtype: tuple(cards) for subtype, cards in index.items()}


@cache
def _cards_by_type() -> dict[Type, tuple[Card, ...]]:
    """The same idea as `_cards_by_subtype`, keyed by card type."""
    index: dict[Type, list[Card]] = defaultdict(list)
    for printing in pool().values():
        for card_type in printing.types:
            if len(index[card_type]) < 5:
                index[card_type].append(printing)
    return {card_type: tuple(cards) for card_type, cards in index.items()}


def _probe_cards(printing: Card, condition: str, *, entering: bool) -> list[Card] | None:
    """Real printings plausible enough to stand in for whatever permanent
    `condition` names, or `None` when this closure has no probe for a named
    restriction and must abstain rather than guess at reachability.

    `printing` itself is always tried first - the twin of a self-referential
    condition ("another Dragon you control", printed on a Dragon) is always
    correct by construction, since it shares every real characteristic the
    source has. A named subtype or required card type pulls in genuinely
    different real printings on top of that, from `_cards_by_subtype`/
    `_cards_by_type`, so a restriction the source itself does not satisfy
    (Weapons Manufacturing's own "artifact" - it is an Enchantment) is still
    tested against something that could.
    """
    required, forbidden = _condition_required_types(condition)
    candidates: list[Card] = [printing]
    subtype = (
        _condition_required_entering_subtype(condition)
        if entering
        else _condition_required_subtype(condition)
    )
    if subtype is not None:
        found = [c for c in _cards_by_subtype().get(subtype, ()) if not forbidden & set(c.types)]
        if not found and subtype.lower() not in {s.lower() for s in printing.subtypes}:
            return None
        candidates.extend(found)
    for card_type in required:
        found = [c for c in _cards_by_type().get(card_type, ()) if not forbidden & set(c.types)]
        if not found and card_type not in printing.types:
            return None
        candidates.extend(found)
    seen: set[str] = set()
    unique: list[Card] = []
    for candidate in candidates:
        if candidate.name in seen:
            continue
        seen.add(candidate.name)
        unique.append(candidate)
    return unique


def _entering_tapped_choices(condition: str) -> list[bool]:
    """Which `tapped` states (CR 603.6d) a synthetic entering permanent
    should be tried at, read off `condition`'s own printed "enters tapped" /
    "enters untapped" qualifier with the same regexes `machines/triggers.
    _entry_qualifier_matches` reads it with - safe to reuse, unlike the
    "token" substring check: this is not the known bug, and *not* trying the
    qualifier's own required state is exactly what let Amulet of Vigor's own
    "enters tapped" condition read as unmatchable when a real tapped-entering
    permanent satisfies it every day."""
    lowered = condition.lower()
    if _CONDITION_ENTERS_TAPPED_RE.search(lowered) is not None:
        return [True]
    if _CONDITION_ENTERS_UNTAPPED_RE.search(lowered) is not None:
        return [False]
    return [False, True]


def _entering_counter_kind(condition: str) -> str | None:
    """The counter kind an "enters with a/an ... counter on it" qualifier
    (CR 603.6d) names, or `None` when the condition names none."""
    match = _CONDITION_ENTERS_WITH_COUNTER_RE.search(condition.lower())
    return match.group("kind").strip() if match else None


def _synthetic_permanent(
    card: Card, *, controller: str, token: bool, tapped: bool, counter_kind: str | None
) -> CardState:
    """One real, honestly-labelled permanent for the synthetic battlefield -
    never characteristics this closure invented to make a condition pass,
    only ones it was told the condition itself names."""
    return CardState(
        card=card,
        zone=Zone.BATTLEFIELD,
        controller=controller,
        owner=controller,
        token=token,
        tapped=tapped,
        counters=Counters({counter_kind: 1}) if counter_kind is not None else Counters(),
    )


def _condition_can_fire(printing: Card, ability: TriggeredAbility) -> bool | None:
    """Whether some real, reachable permanent could satisfy `ability`'s own
    parsed condition through the production `condition_matches` (CR 603.2) -
    or `None` when this closure has no synthetic occurrence to try, in which
    case the caller must not change its verdict on the strength of this
    answer either way.

    `False` is the finding this closure exists to make possible: an event
    that parses but a condition that can never be satisfied by any real
    permanent is a trigger that never fires in a real game, which is a
    different, more fundamental defect than an effect that fires and does
    nothing (`SILENT`) - see `UNMATCHABLE_CONDITION`'s own docstring.

    Every axis this module varies - controller, token state, entry
    qualifier - is tried in every combination and the answers are OR'd
    together: `False` only when *no* combination this closure knows to try
    satisfies `condition_matches`, never because one particular combination
    happened to fail.
    """
    if ability.event not in _SYNTHESIZABLE_EVENTS:
        return None
    entering = ability.event is TriggerEvent.ENTERS_THE_BATTLEFIELD
    probes = _probe_cards(printing, ability.condition, entering=entering)
    if probes is None:
        return None
    token_requirement = _intended_token_requirement(ability.condition)
    token_choices = [token_requirement] if token_requirement is not None else [False, True]
    tapped_choices = _entering_tapped_choices(ability.condition) if entering else [False]
    counter_kind = _entering_counter_kind(ability.condition) if entering else None

    game = Game(
        players=[Player(username="sweep_you"), Player(username="sweep_opp")],
        schema_version=Game.CURRENT_SCHEMA_VERSION,
    )
    states: list[CardState] = []
    for probe in probes:
        for controller_name in ("sweep_you", "sweep_opp"):
            for token in token_choices:
                for tapped in tapped_choices:
                    state = _synthetic_permanent(
                        probe,
                        controller=controller_name,
                        token=token,
                        tapped=tapped,
                        counter_kind=counter_kind,
                    )
                    state.bind_to_game(game)
                    game.battlefield.append(state)
                    states.append(state)

    source_variants = [
        _synthetic_permanent(
            printing, controller="sweep_you", token=False, tapped=tapped, counter_kind=counter_kind
        )
        for tapped in tapped_choices
    ]
    for source in source_variants:
        source.bind_to_game(game)
        game.battlefield.append(source)
    source = source_variants[0]
    controller = "sweep_you"

    def event_for(subject: CardState | None, *, player: str | None = None) -> GameEvent:
        return GameEvent(
            event=ability.event,
            subject_id=subject.id if subject is not None else None,
            subject_controller=subject.controller if subject is not None else None,
            subject_types=tuple(subject.types) if subject is not None else None,
            subject_subtypes=tuple(subject.subtypes) if subject is not None else None,
            related_id=subject.id if subject is not None else None,
            player=player,
        )

    for host in source_variants:
        # A truly self-referential condition ("when this permanent enters
        # tapped") needs `event.subject_id == source.id` *exactly* - tried
        # against each tapped variant of the literal host object, not a twin.
        if condition_matches(game, ability, host, controller, event_for(host)):
            return True
    for subject in states:
        if condition_matches(game, ability, source, controller, event_for(subject)):
            return True
    # CR 508.3d's own playerwide "you attack" event - no subject at all.
    return ability.event is TriggerEvent.ATTACKS and condition_matches(
        game, ability, source, controller, event_for(None, player=controller)
    )


# ---------------------------------------------------------------------------
# The quoted-text closure. `parse_mixed_effect`/`parse_mixed_effect_for_spell`
# read a clause's raw oracle text, quotes and all, and a card that creates a
# token or grants an ability with a *quoted* payload can have its own clause
# misread as whatever shape the quoted text happens to look like -
# `_DAMAGE_TARGET_RE`'s unanchored `.*` prefix reads "deals 2 damage to any
# target" out of Weapons Manufacturing's quoted Munitions text, not anything
# its own clause says, and returns a real callable that "handles" nothing the
# card actually does.
# ---------------------------------------------------------------------------

#: A quoted span, replaced rather than deleted - see `_blank_quoted_spans`.
_QUOTED_SPAN_RE = re.compile(r'"[^"]*"')


#: `machines/effects.py`'s `_compose_layer_effect_with_remainder*` family
#: names its two closures identically across all four of its spell/ability/
#: mode variants - see `_is_sentinel_effect`'s own note on why they join the
#: sentinel set below rather than being asked the quoted-text question.
_LAYER_COMPOSED_NAMES = frozenset(
    {"layer_and_remainder_effect", "layer_effect_with_remainder_notice"}
)


def _is_sentinel_effect(effect: object) -> bool:
    """Whether `effect` is one of `_dispatch_category`'s three named stand-
    ins (`create_continuous_effect`, `create_continuous_effect_of_ability`,
    `resolve_modal_spell`), whose real verdict is read back off the card's
    *whole* printed text (`_layer_category`) or its modes (`_modal_category`)
    - never off whatever raw text happened to produce the sentinel. Hydro-Man,
    Fluid Felon's "becomes a land and gains '{T}: Add {U}.'" dispatches to
    `create_continuous_effect_of_ability`; blanking its quote changes what
    `trigger_effect_for` itself returns for that one string, but not the
    independent, whole-card verdict `_dispatch_category` actually reports -
    so the quoted-text closure must never ask about a sentinel's own
    dispatch answer, only ever about an ordinary callable's.

    A closure `_compose_layer_effect_with_remainder`/its three siblings
    build - `layer_and_remainder_effect` or `layer_effect_with_remainder_
    notice`, named by `_LAYER_COMPOSED_NAMES` - is the identical situation
    one level up: its own layer half is still the same `create_continuous_
    effect`/`_of_ability` sentinel underneath, whose verdict on a quoted span
    is `_layer_category`'s to give, and its composed remainder half (an
    ordinary clause, never one carrying its own quoted ability text in this
    pool) does not depend on the layer sentence's quote either. Matched by
    name rather than identity, since a fresh closure is built on every call.
    """
    if effect in (
        create_continuous_effect,
        create_continuous_effect_of_ability,
        resolve_modal_spell,
    ):
        return True
    return getattr(effect, "__name__", "") in _LAYER_COMPOSED_NAMES


def _blank_quoted_spans(text: str) -> str:
    """`text` with every quoted span's own content swapped for a neutral,
    non-empty placeholder, rather than removed outright.

    Removed outright would misfire on every legitimate "gains '<ability>'" /
    "with '<ability>'" grant in the pool (CR 113.10, Urza's Saga among
    others): `_GAINS_ABILITY_RE` and its siblings correctly read the whole of
    a quote as an opaque payload and refuse an *empty* one, so blanking to
    nothing breaks them exactly the way an accidental match inside the quote
    breaks Weapons Manufacturing - both would stop producing an effect, and
    this closure could not tell a real bug from its own false positive.
    A placeholder that is present but means nothing keeps every parser that
    only checks *for content* satisfied, while a parser that read *into* the
    quote for its own match - the damage regex reading a target and an
    amount out of the granted ability's text - loses exactly the words it
    was matching and stops matching.
    """
    return _QUOTED_SPAN_RE.sub('"Redacted reminder text"', text)


def _effect_matched_inside_quotes(dispatch: Callable[[str], object], text: str) -> bool:
    """Whether `dispatch(text)` - a real effect dispatcher, called the same
    way `classify_clauses` calls it - produced a non-`None` effect only
    because of a quoted span inside `text`.

    `False` whenever `text` carries no quote at all, or `dispatch` already
    answers `None` for it (nothing to flag - some other bucket already has
    it), or blanking the quote does not change the answer (a legitimate
    quote-reading parser, or an effect that never touched the quote to begin
    with).
    """
    if '"' not in text:
        return False
    if dispatch(text) is None:
        return False
    return dispatch(_blank_quoted_spans(text)) is None


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
    (`machines/cost.cost_announces_x` on the cost that pays for the clause):
    `None` - leave a bare "X" in the text alone, the same as a card that
    defines its own X in its rules text (CR 107.3f) rather than in its cost
    (CR 107.3a) - unless that cost has an X in it, `{X}` or Martyr of Sands's
    bare "Reveal X white cards", in which case every value in
    `_X_PROBE_VALUES` is tried.
    """
    if cost_or_mana_cost and cost_announces_x(cost_or_mana_cost):
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
            x_candidates = _x_candidates(face.mana_cost)
            effects = [
                effect_for(face.name, face.text, x_value=x_value) for x_value in x_candidates
            ]
            categories = [_dispatch_category(effect, printing) for effect in effects]
            category = _best(categories)
            # The quoted-text closure only asks about the one dispatch `_best`
            # could have picked from unambiguously - a face carrying both CR
            # 107.3a's `{X}` and a quoted span is not in this pool, so that
            # combination is left untested rather than guessed at.
            if (
                x_candidates == (None,)
                and category == HANDLED
                and not _is_sentinel_effect(effects[0])
                and _effect_matched_inside_quotes(
                    lambda text, name=face.name: effect_for(name, text), face.text
                )
            ):
                category = QUOTED_EFFECT
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
            x_candidates = _x_candidates(ability.cost)
            activated_effects = [
                activated_effect_for(printing.name, index, ability.effect, x_value=x_value)
                for x_value in x_candidates
            ]
            categories = [_dispatch_category(effect, printing) for effect in activated_effects]
            category = _best(categories)
            if (
                x_candidates == (None,)
                and category == HANDLED
                and not _is_sentinel_effect(activated_effects[0])
                and _effect_matched_inside_quotes(
                    lambda text, i=index: activated_effect_for(printing.name, i, text),
                    ability.effect,
                )
            ):
                category = QUOTED_EFFECT
            clauses.append(ClauseOutcome(category, ability.text, "activated"))
        elif isinstance(ability, TriggeredAbility) and is_permanent:
            # Gated on `is_permanent` the same way the static branch below
            # already is, and for the identical reason: `trigger_effect_for`
            # is called from exactly one place in the real engine,
            # `Game._effect_of`, and only for an `AbilityOnStack` - which only
            # a *permanent's* own triggered ability ever becomes (CR 603.2,
            # CR 113.6). A non-permanent card's printed "When/Whenever/At ..."
            # paragraph (the Pact cycle's own "At the beginning of your next
            # upkeep, pay [cost]. If you don't, you lose the game.") is never
            # put on the stack as its own object - it is part of the spell's
            # *resolution text*, already read whole (both paragraphs) by the
            # `effect_for`/"[spell]" clause above, which is what
            # `machines/effects._parse_delayed_pay_or_lose_clauses` and
            # `Game.create_delayed_trigger` actually answer to in a real game.
            # Asking `trigger_effect_for` about it anyway found no row keyed
            # under a permanent's own dispatch (there is none: nothing here
            # is ever an `AbilityOnStack`) and reported Summoner's Pact and
            # Pact of Negation SILENT for a mechanism that plays correctly -
            # `tests/scenarios/test_pact_delayed_upkeep_cost.py` already
            # proves it end to end. This is the same "measured the wrong
            # dispatcher" shape as the two entries above it in this loop.
            # `ability.event is None` is not on its own "nobody can ever fire
            # this" - `triggers.triggered_abilities_of` keeps such an ability
            # anyway when `_unread_trigger_events` can still read its printed
            # condition (CR 603.1b), and `_state_trigger_abilities` keeps one
            # whose condition is CR 603.8's own shape
            # (`_STATE_COUNTER_TRIGGER_RE`). Both routes reach
            # `condition_matches`/`_state_condition_holds` and go on the stack
            # in a real game, so asking only about `event` here reported
            # Murktide Regent and eight other cards' triggers SILENT for a
            # measurement gap, not an engine one.
            if (
                ability.event is None
                and not _unread_trigger_events(ability.condition)
                and _STATE_COUNTER_TRIGGER_RE.match(ability.condition.strip()) is None
            ):
                clauses.append(ClauseOutcome(SILENT, ability.text, "triggered (unread condition)"))
                continue
            effect = trigger_effect_for(printing.name, ability.event, ability.effect)
            modal_category = _modal_trigger_category(ability.effect)
            category = (
                modal_category
                if modal_category is not None
                else _dispatch_category(effect, printing)
            )
            if (
                category == HANDLED
                and not _is_sentinel_effect(effect)
                and _effect_matched_inside_quotes(
                    lambda text, event=ability.event: trigger_effect_for(
                        printing.name, event, text
                    ),
                    ability.effect,
                )
            ):
                category = QUOTED_EFFECT
            if _condition_can_fire(printing, ability) is False:
                category = UNMATCHABLE_CONDITION
            clauses.append(ClauseOutcome(category, ability.text, "triggered"))
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
    with_text = [name for name in names if has_rules_text(card(name))]
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
        category, detail = classify_card(card(name))
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
    for ability in parse_abilities(printing):
        detail = getattr(ability, "cost", None) or getattr(ability, "parameter", None) or ""
        print(f"  {ability.kind.value:<10} {ability.text[:60]}  {detail}")
    executed = executed_keywords(printing)
    print("\n  keyword execution:")
    for keyword in printing.keywords:
        where = executed.get(keyword.lower())
        if where is None and keyword.lower() in NEEDS_NO_CODE | ABILITY_WORDS | flavor_words(
            printing
        ):
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
