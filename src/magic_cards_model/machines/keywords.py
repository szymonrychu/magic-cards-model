"""Keyword abilities that are neither combat nor a way to cast a card.

`machines/combat.py` executes the keywords that change what happens in combat and
`machines/casting.py` executes the ones that change where or when a card may be
cast. This module is the third pile: keywords that are shorthand for an
*activated*, *triggered*, or *replacement* ability that the rest of the engine
has no way to reach.

Two structural facts shape everything here.

**An activated ability need not be an ability of a permanent.** CR 602.1a says
an activated ability is written `[Cost]: [Effect.]`, and says nothing about the
battlefield; cycling (CR 702.29a) and transmute (CR 702.53a) function in a
player's *hand*. `Game.begin_activating` refuses anything that is not on the
battlefield, so `KeywordActivation` below is the general form: it names the zone
the ability functions in and works from there.

**A keyword's ability is not printed as an ability.** `Cycling {U}` and
`Equip {1}{R}` parse as `KeywordAbility`, not `ActivatedAbility`, because that
is how they are printed. The rule text is what expands them - CR 702.29a's
"'Cycling [cost]' means "[Cost], Discard this card: Draw a card."" and
CR 702.6a's "'Equip [cost]' means "[Cost]: Attach this permanent to target
creature you control. Activate only as a sorcery."" - so each expansion is
written out here, once, against the rule it came from.

Every CR number in this module was looked up with `knowledge_search` in the
session that wrote it. What is *not* here is listed in
`docs/engine-coverage.md`.
"""

import random
import re
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from enum import StrEnum
from typing import Any, NamedTuple
from uuid import UUID

from pydantic import ConfigDict, Field

from magic_cards_model.phrases import with_indefinite_article

from ..data.subtypes import canonical_subtype
from ..models.card import Card, Color, Supertype, Type
from ..models.card_state import (
    CardState,
    Counter,
    ExileAnnotation,
    ExileMarker,
    FaceDownCharacteristics,
    TargetRef,
)
from ..models.mana import ManaCost, ManaSpend
from ..models.zone import Zone
from ..numbers import parse_count
from ..snapshot import EngineModel
from .abilities import (
    AbilityKind,
    ActivatedAbility,
    Cost,
    CostKind,
    KeywordAbility,
    StaticAbility,
    TriggeredAbility,
    TriggerEvent,
    TriggerWord,
    keyword_abilities,
    parse_abilities,
    target_cost_reduction_amount,
)
from .attached_restrictions import attached_crew_refusal
from .combat import has_keyword
from .cost import (
    ComponentKind,
    CostModifierNotice,
    CostPayment,
    CostStep,
    TotalCost,
    cumulative_upkeep_cost,
    discard_cost,
    exile_cost,
    remove_counters_cost,
    return_to_hand_cost,
    tap_cost,
    total_cost_for_phrase,
)
from .cost.abilities import KEYWORD_KINDS, ability_cost_adjustment, cycling_costs_nothing
from .crew_saddle_statics import contribution, station_amount, total_contribution
from .decisions import Decision, DecisionKind, source_id_of
from .delayed import anaphoric_delayed_trigger
from .designations import designation_holds, split_as_long_as
from .equip_block_statics import (
    attach_refusal,
    crew_activation_key,
    crew_once_each_turn,
    equip_activation_key,
    equip_once_each_turn,
)
from .layers import (
    ComputedBoard,
    ContinuousEffect,
    Duration,
    Layer,
    Sublayer,
    _only,
    add_type,
    grant_ability,
    modify_power_toughness,
    only_this_incarnation,
)
from .legacy_keywords import LEGACY_EXPANSIONS
from .objects_as_costs import (
    ObjectAction,
    ObjectOffer,
    crew_number,
    crew_offer,
    has_crew_loyalty_alternative,
)
from .soulbond import soulbond_effect
from .triggers import (
    AbilityOnStack,
    ExtraTriggerEvent,
    GameEvent,
    activated_abilities_of,
    triggers_for,
)
from .turn import DayNight
from .zone_grants import effective_card


class KeywordRule(StrEnum):
    """The CR number each keyword this module executes is read from.

    Spelled out rather than written inline so a reader can see, in one place,
    exactly which rules this module claims to implement.
    """

    CYCLING = "CR 702.29a"
    TYPECYCLING = "CR 702.29e"
    EQUIP = "CR 702.6a"
    WARD = "CR 702.21a"
    PROWESS = "CR 702.108a"
    CASCADE = "CR 702.85a"
    STORM = "CR 702.40a"
    CASUALTY = "CR 702.153a"
    PERSIST = "CR 702.79a"
    UNDYING = "CR 702.93a"
    DREDGE = "CR 702.52a"
    MOBILIZE = "CR 702.181a"
    MADNESS = "CR 702.35a"
    SCAVENGE = "CR 702.97a"
    MIRACLE = "CR 702.94a"
    MORPH = "CR 702.37a"
    DISGUISE = "CR 702.168a"
    MANIFEST = "CR 701.40a"
    INDESTRUCTIBLE = "CR 702.12b"
    EXERT = "CR 701.43a"
    REBOUND = "CR 702.88a"
    HIDEAWAY = "CR 702.75a"
    CREW = "CR 702.122a"
    SADDLE = "CR 702.171a"
    STATION = "CR 702.184a"
    NINJUTSU = "CR 702.49a"
    EVOKE = "CR 702.74a"
    UNEARTH = "CR 702.84a"
    TRANSMUTE = "CR 702.53a"
    PARADIGM = "CR 702.192a"
    IMPENDING = "CR 702.176a"
    BATTLE_CRY = "CR 702.91a"
    OUTLAST = "CR 702.107a"
    POWER_UP = "CR 702.193a"
    PARTNER_WITH = "CR 702.124j"
    ANNIHILATOR = "CR 702.86a"
    RENOWN = "CR 702.112a"
    CRAFT = "CR 702.167a"
    FLANKING = "CR 702.25a"
    VANISHING = "CR 702.63a"
    DECAYED = "CR 702.147a"


def executes(keyword: str) -> bool:
    """Whether this module acts on a keyword, by its Scryfall spelling.

    `scripts/sweep_pool.py` reads this, so a keyword that is added here stops
    being reported as ignored - and one that is taken out starts again.

    Every `[type]cycling` counts, because CR 702.29f says so in as many words:
    "Typecycling abilities are cycling abilities, and typecycling costs are
    cycling costs." Scryfall lists the umbrella names `Typecycling` and
    `Landcycling` beside the concrete `Forestcycling` a card actually prints,
    the same way it lists `Landwalk` beside `Swampwalk`.
    """
    lowered = keyword.lower()
    if lowered.endswith("cycling"):
        return True
    return lowered in {
        "equip",
        "ward",
        "prowess",
        # CR 702.118b: an evasion restriction `machines/combat.block_refusal`
        # enforces.
        "skulk",
        # CR 702.13b: an evasion restriction `machines/combat.block_refusal`
        # enforces.
        "intimidate",
        # CR 702.36b: likewise, fear in `block_refusal`.
        "fear",
        # CR 702.101a: `_extort_ability` (`_TRIGGER_EXPANSIONS`).
        "extort",
        # CR 702.95a: `_soulbond_abilities` (`_TRIGGER_EXPANSIONS`), resolved
        # by `machines/soulbond.soulbond_effect`.
        "soulbond",
        # CR 702.191a: `_increment_ability` (`_TRIGGER_EXPANSIONS`); its
        # intervening "if" is `machines/triggers.intervening_if_answer`'s.
        "increment",
        # CR 702.54a: an "enters with" replacement (CR 614.1c),
        # `machines/replacement._bloodthirst_entering_counters`.
        "bloodthirst",
        # CR 702.136a: an "enters with"/"enters ..." replacement (CR 614.1c)
        # asking its controller, `machines/replacement._riot_modifiers` (the
        # haste half is `Game.enter_the_battlefield`'s `event.grants_haste`).
        "riot",
        "cascade",
        "storm",
        # CR 702.153a: the additional cost is `machines/casting.Casting.
        # pay_casualty`, the trigger `casualty_triggered_abilities`/
        # `_casualty_effect` here, one per casualty cost paid (CR 702.153b).
        "casualty",
        # CR 702.78a: the additional cost is `machines/casting.Casting.
        # pay_conspire`, the trigger `conspire_triggered_abilities`/
        # `_conspire_effect` here, one per conspire cost paid.
        "conspire",
        "persist",
        # CR 702.93a: `_undying_ability` (`_TRIGGER_EXPANSIONS`), resolved by
        # `_undying_effect`.
        "undying",
        # CR 702.43a: the dying half is `_modular_ability`/`_modular_effect` here,
        # the "enters with" half `machines/replacement/enters.
        # _modular_entering_counters`.
        "modular",
        "dredge",
        "mobilize",
        "indestructible",
        "exert",
        "rebound",
        "hideaway",
        "crew",
        # CR 702.171a: `saddle_activation`/`_saddle_effect` here; the saddled
        # designation is `CardState.saddled` (CR 702.171b).
        "saddle",
        # CR 701.60a and CR 701.49a: keyword *actions* embedded in effect
        # text, read by `machines/effects.py`'s `_parse_suspect_clause` and
        # `_parse_venture_clause` (the dungeon itself is `machines/dungeon.py`).
        "suspect",
        "venture into the dungeon",
        "station",
        "ninjutsu",
        "commander ninjutsu",
        # CR 111.10j-r's Role family. The keyword line itself is Scryfall's
        # "Role token"; the ability it stands for - "Create a(n) [Role] Role
        # token attached to [X]." - is a clause `machines/effects.py`'s
        # `_parse_create_role_token_clause` reads off the card's own printed
        # text, not something this module dispatches.
        "role token",
        # CR 702.192a: "Exile this spell" is `machines/replacement.py`'s
        # `_stack_replacements` entry, the delayed copy-and-cast is
        # `machines/delayed.ParadigmCopyAndCast`, and both are wired up from
        # `models/game.py`'s `resolve_top`.
        "paradigm",
        # CR 701.42a: `machines/meld.py`'s clause parsers, wired into
        # `machines/effects.py`'s `_ability_effect_or_notice` (activated and
        # triggered) and `machines/triggers.intervening_if_holds`
        # (triggered), and `models/game.py`'s `Game.meld` is the mechanism.
        "meld",
        # CR 702.74a. Two abilities, executed in two places: the static half is
        # an alternative cost and belongs to `machines/casting.py`
        # (`keyword_cast_options`), the triggered half - "When this permanent
        # enters, if its evoke cost was paid, its controller sacrifices it" -
        # is `_evoke_ability`/`_evoke_effect` here.
        "evoke",
        # CR 702.167a: `craft_activation`/`_craft_effect` here.
        "craft",
        # CR 702.119a: the alternative cost is `machines/casting.py`'s
        # `keyword_cast_options`, the reduction `Casting._use_keyword`.
        "emerge",
        # CR 702.176a. Four abilities in four places: the alternative cost is
        # `machines/casting.py`'s `keyword_cast_options`, the entering time
        # counters are `machines/replacement._impending_entering_counters`, the
        # "it's not a creature" is `machines/layers._impending_not_a_creature`,
        # and the end step trigger is `_impending_ability`/`_impending_effect`
        # here.
        "impending",
        # CR 702.94a. A static ability linked to a triggered one (CR 603.11,
        # CR 607.2h): the reveal-as-drawn question is `Game._offer_miracle_
        # reveal`, asked from `Game.draw_cards`; the linked trigger is
        # `_miracle_ability`/`_miracle_effect` here, and the cast it makes is
        # `Game.cast_during_resolution` with the miracle cost as the
        # alternative cost (CR 608.2g, CR 118.9).
        "miracle",
        # CR 702.73a. A characteristic-defining ability that works in every
        # zone (CR 604.3): off the battlefield it is `CardState.subtypes`
        # (`models/card.with_every_creature_type`), on the battlefield it is
        # `machines/layers._changeling_effects`, a layer 4 CDA (CR 613.1d)
        # applied before every other type-changing effect (CR 613.3).
        "changeling",
        # CR 702.189a. The triggered half is `_firebending_ability` above
        # (`_TRIGGER_EXPANSIONS`), and `machines/effects._parse_firebending_
        # add_mana` reads the "add N {R}" effect it puts on the stack.
        "firebending",
        # CR 702.25a/b: `_flanking_ability` above (`_TRIGGER_EXPANSIONS`) -
        # the "without flanking" qualifier is `machines/triggers.condition_
        # matches`'s own `BLOCKS` branch, and "the blocking creature" is
        # `machines/effects._parse_event_subject_pump_clause`'s existing
        # event-subject reader.
        "flanking",
        # CR 702.115a: `_ingest_ability` above (`_TRIGGER_EXPANSIONS`).
        "ingest",
        # CR 702.45a, CR 702.135a, CR 702.134a: `_bushido_ability` above and
        # `machines/legacy_keywords.LEGACY_EXPANSIONS` (`_TRIGGER_EXPANSIONS`).
        "bushido",
        "afterlife",
        "mentor",
        "graft",
        "backup",
        "champion",
        # CR 701.45a: assemble is the keyword action `Game.assembling_count` asks
        # the replacement layer about (Steamflogger Boss doubles it).
        "assemble",
        # CR 701.29a / CR 701.30b: the keyword actions `legacy_keywords.fateseal`
        # and `legacy_keywords.clash`, read by the clause rungs in
        # `machines/effects` (`_SCRY_RE`'s fateseal twin, `_parse_clash_clause`).
        "fateseal",
        "clash",
        # CR 702.145b / CR 702.145e. Static abilities driven by the game's
        # day/night designation (CR 731): `apply_daybound_nightbound` below
        # transforms and sets the designation, `enters_transformed_at_night`
        # is read by `Game.enter_the_battlefield`, and `CardState.transform`
        # refuses any other transform of a permanent carrying either keyword.
        "daybound",
        "nightbound",
        # CR 702.175a. The same two-places shape as evoke just above: the
        # additional-cost half is `machines/casting.py`'s `Casting.
        # pay_offspring` (`ADDITIONAL_COST_KEYWORDS`), the triggered half -
        # "When this permanent enters, if its offspring cost was paid,
        # create a token that's a copy of it, except it's 1/1" - is
        # `_offspring_ability` here.
        "offspring",
        # CR 702.51a and CR 702.66a. Static abilities that function while the
        # spell is on the stack and change *how* one symbol of its already
        # determined total cost is paid - executed by
        # `machines/objects_as_costs.py` against an open `CostPayment`, not
        # here, because neither is an ability this module can put on the stack.
        "convoke",
        "delve",
        # CR 701.66a. A CR 701 keyword *action* embedded in another ability's
        # effect text, not a CR 702 keyword ability printed on its own - so
        # its clause parser lives in `machines/effects.py`
        # (`_parse_earthbend_clause`), not here. Listed explicitly so the pool
        # sweeper reports it as executed rather than silently ignored.
        "earthbend",
        # CR 701.65a, the same shape as earthbend above: a CR 701 keyword
        # action embedded in another ability's effect text. The exile itself is
        # `machines/effects.py`'s clause to perform; the half executed here is
        # what the exiled card may do afterwards - `machines/casting.
        # marker_cast_options` reads `ExileMarker.AIRBENT` back into the {2}
        # cast CR 701.65a grants its owner.
        "airbend",
        # CR 701.47a, the same shape again: `machines/effects.amass` is what
        # performs it, reached through `_parse_amass_clause` from inside
        # another ability's effect text (Orcish Bowmasters' "Then amass Orcs
        # 1."). Listed here for the same reason the two above are.
        "amass",
        # CR 701.54a, the same shape once more: `models/game.Game.ring_tempts`
        # performs it (the emblem, the Ring-bearer choice, the count), reached
        # through `machines/effects._parse_ring_tempts_you_clause` from inside
        # another ability's or spell's effect text.
        "the ring tempts you",
        # CR 701.16a, the same shape once more: `machines/effects.investigate`
        # performs it, reached through `_parse_investigate_clause` from
        # inside another ability's effect text.
        "investigate",
        # CR 701.71a, Reality Fracture's own keyword action, the same shape
        # once more: `machines/effects.empower_jace` performs it, reached
        # through `_parse_empower_jace_clause`. Scryfall tags every fra
        # printing's `keywords` with "Empower Jace" (CR 701.71a), lowercased
        # "empower jace"; the bare "empower" is kept for the keyword's own
        # name.
        "empower",
        "empower jace",
        # CR 701.48a, the same shape once more: `machines/effects.learn`
        # performs both halves, discard-to-draw and the Lesson reveal from
        # outside the game, reached through `_parse_learn_clause`.
        "learn",
        # CR 701.19a, the same shape once more: `machines/effects.
        # regenerate_ability_targets`/`_parse_regenerate_self_clause`
        # perform it (`Game.regenerate` creates the shield), reached from
        # whichever clause parser read the sentence that names it.
        "regenerate",
        # CR 701.69a. Every printing in the pool that carries this word
        # carries it inside regeneration's own reminder text ("... heal all
        # damage on it"), never as a standalone instruction - and
        # `machines/replacement._regeneration_effects` already removes the
        # marked damage as part of CR 701.19a's own shield
        # (`Game.regenerate`), proved by `test_regenerate.py`'s own
        # `damage == 0` assertions. Listed so the sweep credits work that
        # already happens rather than reporting a second, separate gap.
        "heal",
        # CR 701.59a. `machines/cost.py`'s `ComponentKind.COLLECT_EVIDENCE`
        # (`collect_evidence_cost`, matched by `_PHRASE_COLLECT_EVIDENCE`)
        # already reads "Collect evidence N" as a real payable cost
        # component wherever it is printed - Detective's Phoenix's own
        # `Bestow-{R}, Collect evidence 6` - so this is a bookkeeping
        # credit, not new behaviour.
        "collect evidence",
        # CR 701.40a and CR 701.62a, the same shape once more:
        # `machines/effects.manifest`/`manifest_dread` perform them, reached
        # through `_parse_manifest_top_card_clause`/`_parse_manifest_dread_
        # clause` from inside another ability's effect text.
        "manifest",
        "manifest dread",
        # CR 701.14a, and the same shape once more: `machines/effects._fight`
        # is what performs it, reached from whichever clause parser read the
        # sentence that names it (Kraul Harpooner's own undergrowth shape,
        # Bridgeworks Battle's "It fights up to one target creature you don't
        # control.").
        "fight",
        # CR 702.91a-b. A triggered ability, "Whenever this creature attacks,
        # each other attacking creature gets +1/+0 until end of turn.", each
        # printed instance triggering separately (CR 702.91b) through the
        # same per-instance loop every other `_TRIGGER_EXPANSIONS` entry
        # already shares - `_battle_cry_ability`/`_battle_cry_effect` below.
        "battle cry",
        # CR 702.107a. An activated ability the keyword line expands to -
        # "[Cost], {T}: Put a +1/+1 counter on this creature. Activate only
        # as a sorcery." - through the same synthetic-`KeywordActivation`
        # shape equip and cycling already use: `outlast_activation`/
        # `_outlast_effect` below.
        "outlast",
        # CR 702.193a-b. Unlike every keyword above, Power-up's own line
        # already parses as an ordinary printed `ActivatedAbility` (CR
        # 602.1's "[Cost]: [Effect]" shape, with "Power-up" read as the
        # em-dash prefix the same way Exhaust's is) and its effect clause
        # already resolves through the generic activated-ability path - what
        # was missing is CR 702.193a's own "Activate this ability only once"
        # and CR 702.193b's entered-this-turn cost reduction, both read off
        # `ActivatedAbility.power_up` by `Game.why_cannot_activate`,
        # `Game.activate_ability` and `Game.activation_cost`
        # (`machines/abilities.py`, `models/game.py`).
        "power-up",
        # CR 702.24a: `_cumulative_upkeep_ability` writes the trigger out and
        # `_cumulative_upkeep_effect` adds the age counter and asks the one
        # pay-or-sacrifice question.
        "cumulative upkeep",
        # CR 702.30a: `_echo_ability` writes the upkeep trigger out (from the
        # keyword line, or from a "<this> has echo {X}, where X is ..." static
        # line, `self_echo_lines`) and `_echo_effect` asks the one
        # pay-or-sacrifice question.
        "echo",
        # CR 701.57a-c, the same shape once more: `machines/keywords.discover`
        # performs it (cascade's own exile-until/free-cast/random-bottom
        # machinery, CR 702.85a, parameterised by N instead of the cascading
        # spell's own mana value), reached through `machines/effects.
        # _parse_discover_clause` from inside another ability's or spell's
        # effect text.
        "discover",
        # CR 702.124j: "'Partner with [name]' represents two abilities" -
        # a deck-construction half (CR 702.124a, inert here; see
        # `scripts/sweep_pool.py`'s `NEEDS_NO_CODE` "partner" entry, the same
        # rule) and a triggered half this module does execute:
        # `_partner_with_ability`/`_TRIGGER_EXPANSIONS` below write out the
        # "When this permanent enters, target player may search their
        # library for a card named [name], reveal it, put it into their
        # hand, then shuffle" ability, with `[name]` read off the card's own
        # printed line (`KeywordAbility.parameter`), never a name table.
        # Distinct from plain "partner" (`NEEDS_NO_CODE`): CR 702.124f says
        # the two are different abilities that "cannot be combined", so
        # crediting one keyword must never silence the other.
        "partner with",
        # CR 702.86a: "Annihilator N" means "Whenever this creature attacks,
        # defending player sacrifices N permanents." `_annihilator_ability`/
        # `_annihilator_effect` below, printed (Ulamog's Crusher's
        # "Annihilator 2") or granted by a static ability with a variable N
        # (Ulamog, the Defiler's "annihilator X, where X is ...").
        "annihilator",
        # CR 702.112a: `_renown_ability` below (`_TRIGGER_EXPANSIONS`); its
        # effect, "put N +1/+1 counters on it and it becomes renowned", is
        # `machines/effects._parse_renown_clause`, and the designation is
        # `CardState.renowned` (CR 702.112b).
        "renown",
        # CR 702.63a. Three abilities in two places: the entering time
        # counters (numbered vanishing only, CR 702.63b) are `machines/
        # replacement._vanishing_entering_counters`, and the upkeep tick plus
        # the last-counter sacrifice are `_vanishing_abilities`/
        # `_vanishing_effect` below (`_TRIGGER_EXPANSIONS`).
        "vanishing",
        # CR 702.147a: two abilities, one per machine. The static "can't
        # block" half is `machines/combat.block_refusal`'s own `has_keyword`
        # check (credited to "machines/combat.py" first, since `printing.
        # keywords` is walked against `combat.Keyword` before this set is
        # ever asked); the triggered "sacrifice it at end of combat" half is
        # `_decayed_ability` below (`_TRIGGER_EXPANSIONS`), whose effect text
        # `machines/effects._parse_delayed_single_clause` reads.
        "decayed",
        # CR 702.87a: `machines/level_up.level_up_activation`/`_level_up_
        # effect`; the level symbols it counts toward (CR 711.2) are
        # `level_up.level_symbol_effects`, read off each striation.
        "level up",
        # CR 702.151a/b: `machines/reconfigure.reconfigure_attach_activation`/
        # `reconfigure_unattach_activation`/`_reconfigure_effect`, and the
        # attached not-a-creature `reconfigure_not_a_creature` (layer 4).
        "reconfigure",
        # CR 702.92a, CR 702.163a, CR 702.182a: the "create a token, then
        # attach this Equipment to it" triggers, written out by
        # `machines/attach_keywords.py` into `_TRIGGER_EXPANSIONS`; CR 702.67a:
        # `attach_keywords.fortify_activation`/`_fortify_effect`.
        "living weapon",
        "for mirrodin!",
        "job select",
        "fortify",
    }


def _keyword(card: Card, *names: str) -> KeywordAbility | None:
    wanted = {name.lower() for name in names}
    for ability in keyword_abilities(card):
        if ability.canonical.lower() in wanted:
            return ability
    return None


def _keyword_cost(ability: KeywordAbility, payer: str) -> TotalCost | None:
    """Read a keyword's printed cost into something payable (CR 702.1a).

    `Cycling {U}` prints mana; `Cycling—Pay 2 life.` prints a sentence. The
    parser already told the two apart with `cost_is_mana`, so this only has to
    send each to the right reader.
    """
    printed = ability.cost or ""
    if not printed:
        return TotalCost()
    if ability.cost_is_mana:
        mana = ManaCost.try_parse(printed)
        return None if mana is None else TotalCost.of(mana).assign_payer(payer)
    read = total_cost_for_phrase(printed, payer)
    return None if read is None else read.assign_payer(payer)


# --------------------------------------------------------------------------
# Keywords that are triggered abilities (CR 603.1)
# --------------------------------------------------------------------------
#
# `machines/triggers.py` turns a game event into triggered abilities by reading
# the *printed* ones off a card - a line beginning When, Whenever or At. Five
# keywords in this pool are triggered abilities that are never printed as such:
# the card says one word and the rule says what the word means.
#
# Each was looked up separately in this session, because they are not all the
# same kind of ability and guessing would have got two of them wrong:
#
# - **Ward** (CR 702.21a) - "Ward is a triggered ability." One ability.
# - **Prowess** (CR 702.108a) - "Prowess is a triggered ability." One, and
#   CR 702.108b makes multiple instances trigger separately.
# - **Cascade** (CR 702.85a) - "Cascade is a triggered ability *that functions
#   only while the spell with cascade is on the stack*", which is why the source
#   asked is the spell and not a permanent.
# - **Persist** (CR 702.79a) - "Persist is a triggered ability", and its "if it
#   had no -1/-1 counters on it" is an intervening *if* (CR 603.4).
# - **Undying** (CR 702.93a) - "Undying is a triggered ability", persist's
#   mirror: "if it had no +1/+1 counters on it" is the intervening *if*.
# - **Mobilize** (CR 702.181a) - "Mobilize is a triggered ability."
#
# For contrast, and to make the point that this list is read rather than
# assumed: morph is a *static* ability (CR 702.37a), indestructible is a static
# ability (CR 702.12a), suspend is three abilities - one static plus two
# triggered (CR 702.62a) - and madness is two, "a static ability that functions
# while the card with madness is in a player's hand" plus "a triggered ability
# that functions when the first ability is applied" (CR 702.35a).


def _expansion(
    ability: KeywordAbility,
    *,
    keyword: str,
    word: TriggerWord,
    condition: str,
    effect: str,
    event: TriggerEvent | None,
    intervening_if: str | None = None,
) -> TriggeredAbility:
    """One keyword line written out as the triggered ability the rule says it is.

    `raw` and `face` come from the printed line, so the ability still points at
    where it came from; `text` is the rule's own wording, because that is the
    only place the ability is written down.
    """
    return TriggeredAbility(
        raw=ability.raw,
        text=f"{word.value.capitalize()} {condition}, {effect}",
        reminder=ability.reminder,
        face=ability.face,
        word=word,
        condition=condition,
        intervening_if=intervening_if,
        effect=effect,
        event=event,
        keyword=keyword,
    )


def _ward_ability(ability: KeywordAbility) -> TriggeredAbility:
    """CR 702.21a: "Ward [cost]" means "Whenever this permanent becomes the
    target of a spell or ability an opponent controls, counter that spell or
    ability unless that player pays [cost].""
    """
    printed = ability.cost or ability.parameter or ""
    return _expansion(
        ability,
        keyword="ward",
        word=TriggerWord.WHENEVER,
        condition="this permanent becomes the target of a spell or ability an opponent controls",
        effect=f"counter that spell or ability unless that player pays {printed}".strip(),
        event=TriggerEvent.BECOMES_TARGET,
    )


def _prowess_ability(ability: KeywordAbility) -> TriggeredAbility:
    """CR 702.108a: "Prowess" means "Whenever you cast a noncreature spell,
    this creature gets +1/+1 until end of turn.""
    """
    return _expansion(
        ability,
        keyword="prowess",
        word=TriggerWord.WHENEVER,
        condition="you cast a noncreature spell",
        effect="this creature gets +1/+1 until end of turn",
        event=TriggerEvent.CAST_SPELL,
    )


def _cascade_ability(ability: KeywordAbility) -> TriggeredAbility:
    """CR 702.85a: "Cascade" means "When you cast this spell, exile cards from
    the top of your library until you exile a nonland card whose mana value is
    less than this spell's mana value. ...""
    """
    return _expansion(
        ability,
        keyword="cascade",
        word=TriggerWord.WHEN,
        condition="you cast this spell",
        effect=(
            "exile cards from the top of your library until you exile a nonland card whose "
            "mana value is less than this spell's mana value. You may cast that card without "
            "paying its mana cost if the resulting spell's mana value is less than this "
            "spell's mana value. Then put all cards exiled this way that weren't cast on the "
            "bottom of your library in a random order"
        ),
        event=TriggerEvent.CAST_SPELL,
    )


def _ripple_ability(ability: KeywordAbility) -> TriggeredAbility:
    """CR 702.60a: "Ripple N" means "When you cast this spell, you may reveal
    the top N cards of your library, or, if there are fewer than N cards in
    your library, you may reveal all the cards in your library. If you reveal
    cards from your library this way, you may cast any of those cards with the
    same name as this spell without paying their mana costs, then put all
    revealed cards not cast this way on the bottom of your library in any
    order." CR 702.60b: each instance triggers separately."""
    count = ability.count if ability.count is not None else 1
    return _expansion(
        ability,
        keyword="ripple",
        word=TriggerWord.WHEN,
        condition="you cast this spell",
        effect=(
            f"you may reveal the top {count} cards of your library. You may cast any of "
            "those cards with the same name as this spell without paying their mana costs. "
            "Put all revealed cards not cast this way on the bottom of your library in any order"
        ),
        event=TriggerEvent.CAST_SPELL,
    )


def _storm_ability(ability: KeywordAbility) -> TriggeredAbility:
    """CR 702.40a: "Storm" means "When you cast this spell, copy it for each
    other spell that was cast before it this turn. If the spell has any
    targets, you may choose new targets for the copies.""
    """
    return _expansion(
        ability,
        keyword="storm",
        word=TriggerWord.WHEN,
        condition="you cast this spell",
        effect=(
            "copy it for each other spell that was cast before it this turn. If the spell "
            "has any targets, you may choose new targets for the copies"
        ),
        event=TriggerEvent.CAST_SPELL,
    )


def _replicate_ability(ability: KeywordAbility) -> TriggeredAbility:
    """CR 702.56a: "Replicate" means "... and 'When you cast this spell, if a
    replicate cost was paid for it, copy it for each time its replicate cost
    was paid. If the spell has any targets, you may choose new targets for
    any of the copies.'"

    The intervening *if* is what keeps an *un*replicated cast of the same
    card from copying itself zero times as though it were storm's unrelated
    count - `machines/triggers.intervening_if_holds`'s "a replicate cost was
    paid for it" clause reads `CastRecord.replicated` the same way kicker's
    own "if it was kicked" reads `CastRecord.kicked`.
    """
    return _expansion(
        ability,
        keyword="replicate",
        word=TriggerWord.WHEN,
        condition="you cast this spell",
        intervening_if="a replicate cost was paid for it",
        effect=(
            "copy it for each time its replicate cost was paid. If the spell has any "
            "targets, you may choose new targets for any of the copies"
        ),
        event=TriggerEvent.CAST_SPELL,
    )


def _casualty_ability(ability: KeywordAbility) -> TriggeredAbility:
    """CR 702.153a's second ability: "When you cast this spell, if a casualty
    cost was paid for it, copy it. If the spell has any targets, you may
    choose new targets for the copy."

    Not in `_TRIGGER_EXPANSIONS`: CR 702.153b says each instance "triggers
    based on the payments made for it, not any other instance of casualty",
    so the triggers a spell has are one per casualty cost actually paid
    (`casualty_triggered_abilities`), read off its `CastRecord`, never one
    per printed or granted instance - an unpaid instance's intervening *if*
    would only ever have stopped it anyway.
    """
    return _expansion(
        ability,
        keyword="casualty",
        word=TriggerWord.WHEN,
        condition="you cast this spell",
        intervening_if="a casualty cost was paid for it",
        effect="copy it. If the spell has any targets, you may choose new targets for the copy",
        event=TriggerEvent.CAST_SPELL,
    )


def casualty_triggered_abilities(paid: int) -> list[TriggeredAbility]:
    """CR 702.153a/b: one casualty trigger for each casualty cost paid."""
    line = KeywordAbility(
        raw="Casualty", text="Casualty", face="", keyword="Casualty", canonical="Casualty"
    )
    return [_casualty_ability(line) for _ in range(max(paid, 0))]


def _conspire_ability(ability: KeywordAbility) -> TriggeredAbility:
    """CR 702.78a's second ability: "When you cast this spell, if its
    conspire cost was paid, copy it. If the spell has any targets, you may
    choose new targets for the copy."

    Like casualty, one per conspire cost actually paid
    (`conspire_triggered_abilities`), read off the spell's `CastRecord`.
    """
    return _expansion(
        ability,
        keyword="conspire",
        word=TriggerWord.WHEN,
        condition="you cast this spell",
        intervening_if="its conspire cost was paid",
        effect="copy it. If the spell has any targets, you may choose new targets for the copy",
        event=TriggerEvent.CAST_SPELL,
    )


def conspire_triggered_abilities(paid: int) -> list[TriggeredAbility]:
    """CR 702.78a: one conspire trigger for each conspire cost paid."""
    line = KeywordAbility(
        raw="Conspire", text="Conspire", face="", keyword="Conspire", canonical="Conspire"
    )
    return [_conspire_ability(line) for _ in range(max(paid, 0))]


def printed_conspire_count(card: Card) -> int:
    """How many "Conspire" keyword lines `card` prints (CR 702.78a)."""
    return sum(1 for ability in keyword_abilities(card) if ability.canonical.lower() == "conspire")


#: "Casualty X. The copy isn't legendary and has starting loyalty X." (Ob
#: Nixilis, the Adversary): a casualty instance whose N is the X its caster
#: announces as the spell is cast (CR 107.3a, CR 702.153a), plus - on that
#: printing - what the casualty copy is (CR 707.2's copiable values).
_CASUALTY_X_LINE_RE = re.compile(
    r"^casualty x\.(?P<copy> the copy isn't legendary and has starting loyalty x\.)?$",
    re.IGNORECASE,
)


def casualty_x_instances(card: Card) -> int:
    """How many "Casualty X" lines `card` prints (CR 702.153a)."""
    return sum(
        1
        for ability in parse_abilities(card)
        if isinstance(ability, StaticAbility)
        and _CASUALTY_X_LINE_RE.fullmatch((ability.text or "").strip())
    )


def casualty_copy_is_nonlegendary_with_x_loyalty(card: Card) -> bool:
    """Whether the card's casualty line says "The copy isn't legendary and has
    starting loyalty X"."""
    return any(
        isinstance(ability, StaticAbility)
        and (match := _CASUALTY_X_LINE_RE.fullmatch((ability.text or "").strip())) is not None
        and match.group("copy") is not None
        for ability in parse_abilities(card)
    )


def printed_casualty_numbers(card: Card, x_value: int | None = None) -> list[int]:
    """The N of every "Casualty N" `card` prints, in printed order (CR
    702.153a). A "Casualty X" instance counts as `x_value` once its caster has
    announced it (CR 107.3a), and is left out until then - nothing can be
    sacrificed for an X nobody has chosen."""
    numbers: list[int] = []
    for ability in keyword_abilities(card):
        if ability.canonical.lower() != "casualty":
            continue
        if ability.count is not None:
            numbers.append(ability.count)
    if x_value is not None:
        numbers.extend(x_value for _ in range(casualty_x_instances(card)))
    return numbers


def _persist_ability(ability: KeywordAbility) -> TriggeredAbility:
    """CR 702.79a: "Persist" means "When this permanent is put into a graveyard
    from the battlefield, if it had no -1/-1 counters on it, return it to the
    battlefield under its owner's control with a -1/-1 counter on it.""

    The "if" is an intervening *if* (CR 603.4), so it is checked when the event
    occurs and again on resolution (CR 608.2a) - which is what stops a persisted
    creature persisting for ever.
    """
    return _expansion(
        ability,
        keyword="persist",
        word=TriggerWord.WHEN,
        condition="this permanent is put into a graveyard from the battlefield",
        intervening_if="it had no -1/-1 counters on it",
        effect=(
            "return it to the battlefield under its owner's control with a -1/-1 counter on it"
        ),
        event=TriggerEvent.DIES,
    )


def _modular_ability(ability: KeywordAbility) -> TriggeredAbility:
    """CR 702.43a's second half: "Modular N" means "This permanent enters with
    N +1/+1 counters on it" (`machines/replacement/enters.py`) and "When this
    permanent is put into a graveyard from the battlefield, you may put a +1/+1
    counter on target artifact creature for each +1/+1 counter on this
    permanent.""
    """
    return _expansion(
        ability,
        keyword="modular",
        word=TriggerWord.WHEN,
        condition="this permanent is put into a graveyard from the battlefield",
        effect=(
            "you may put a +1/+1 counter on target artifact creature for each "
            "+1/+1 counter on this permanent"
        ),
        event=TriggerEvent.DIES,
    )


def _undying_ability(ability: KeywordAbility) -> TriggeredAbility:
    """CR 702.93a: "Undying" means "When this permanent is put into a graveyard
    from the battlefield, if it had no +1/+1 counters on it, return it to the
    battlefield under its owner's control with a +1/+1 counter on it.""

    Persist's mirror (`_persist_ability`): the intervening *if* (CR 603.4) is
    checked as it dies and again on resolution (CR 608.2a), which is what stops
    a creature that came back with its counter from coming back again.
    """
    return _expansion(
        ability,
        keyword="undying",
        word=TriggerWord.WHEN,
        condition="this permanent is put into a graveyard from the battlefield",
        intervening_if="it had no +1/+1 counters on it",
        effect=(
            "return it to the battlefield under its owner's control with a +1/+1 counter on it"
        ),
        event=TriggerEvent.DIES,
    )


def _evoke_ability(ability: KeywordAbility) -> TriggeredAbility:
    """CR 702.74a's second half: "Evoke [cost]" means "You may cast this card by
    paying [cost] rather than paying its mana cost" *and* "When this permanent
    enters, if its evoke cost was paid, its controller sacrifices it."

    The first half is an alternative cost (CR 118.9) and is executed by
    `machines/casting.py`; only the second half is an ability that goes on the
    stack, so only the second half is expanded here.

    "If its evoke cost was paid" is an intervening *if* (CR 603.4): a hardcast
    incarnation's ability does not trigger at all, rather than triggering and
    doing nothing. `machines/triggers.intervening_if_holds` answers it from
    `CastRecord.keyword`, which `machines/casting.Casting.cast` records at
    CR 601.2b announcement time - the only place that knows an alternative cost
    was the one chosen.

    The sacrifice is *not* a delayed triggered ability (CR 603.7): nothing
    creates it during a resolution and it has no stated later timing. It is an
    ordinary enters-the-battlefield trigger (CR 603.6a), which is why it can be
    responded to - the evoked creature is on the battlefield with the trigger on
    the stack, and an opposing player gets priority there.
    """
    return _expansion(
        ability,
        keyword="evoke",
        word=TriggerWord.WHEN,
        condition="this permanent enters",
        intervening_if="its evoke cost was paid",
        effect="its controller sacrifices it",
        event=TriggerEvent.ENTERS_THE_BATTLEFIELD,
    )


def _offspring_ability(ability: KeywordAbility) -> TriggeredAbility:
    """CR 702.175a's second half: "Offspring [cost]" means "You may pay an
    additional [cost] as you cast this spell" and "When this permanent
    enters, if its offspring cost was paid, create a token that's a copy of
    it, except it's 1/1."

    The first half is an additional cost (CR 118.8a) and is executed by
    `machines/casting.py`'s `Casting.pay_offspring`; only the second half is
    an ability that goes on the stack, so only the second half is expanded
    here - the same evoke-shaped split `_evoke_ability` above documents.

    "If its offspring cost was paid" is an intervening *if* (CR 603.4),
    answered by `machines/triggers.intervening_if_holds` off
    `CastRecord.offspring_paid`, mirroring evoke's own `CastRecord.keyword`
    read exactly.
    """
    return _expansion(
        ability,
        keyword="offspring",
        word=TriggerWord.WHEN,
        condition="this permanent enters",
        intervening_if="its offspring cost was paid",
        effect="create a token that's a copy of it, except it's 1/1",
        event=TriggerEvent.ENTERS_THE_BATTLEFIELD,
    )


def _impending_ability(ability: KeywordAbility) -> TriggeredAbility:
    """CR 702.176a's fourth ability: "At the beginning of your end step, if this
    permanent's impending cost was paid and it has a time counter on it,
    remove a time counter from it."

    The other three are the alternative cost (`machines/casting.py`), the
    entering counters (`machines/replacement.py`) and the layer 4 "it's not a
    creature" (`machines/layers.py`); only this one goes on the stack.

    The *if* is an intervening *if* (CR 603.4), answered by
    `machines/triggers.intervening_if_holds` off `CardState.cast_with_keyword`
    and the time counter count - so a hardcast Overlord, a blinked one, and one
    whose last counter is already gone never trigger at all.
    """
    return _expansion(
        ability,
        keyword="impending",
        word=TriggerWord.AT,
        condition="the beginning of your end step",
        intervening_if="this permanent's impending cost was paid and it has a time counter on it",
        effect="remove a time counter from it",
        event=TriggerEvent.BEGINNING_OF_STEP,
    )


def _partner_with_ability(ability: KeywordAbility) -> TriggeredAbility:
    """CR 702.124j's second half: "'Partner with [name]' represents two
    abilities. ... and 'When this permanent enters the battlefield, target
    player may search their library for a card named [name], reveal it, put
    it into their hand, then shuffle their library.'"

    Only this triggered half runs during a game. The first half -
    designating two legendary cards as a Commander deck's two commanders -
    is CR 702.124a's own deck-construction rule ("modify the rules for deck
    construction in the Commander variant ... and function before the game
    begins"): this engine targets Modern, Pioneer, and Standard only
    (`CLAUDE.md`), none of which is Commander, so there is nothing for it to
    execute - `scripts/sweep_pool.py`'s `NEEDS_NO_CODE` documents plain
    "partner" on the same rule, and this keyword's deck-construction half is
    inert for the identical reason.

    `[name]` is `ability.parameter`: `machines/abilities.py`'s keyword-line
    parser already reads "Partner with Jacob Frye" off the card's own
    printed line as `KeywordAbility(canonical="Partner with",
    parameter="Jacob Frye")`, so the name this ability searches for comes
    from whichever printing carries it, never a card-name table
    (`CLAUDE.md`'s "target the mechanic, never the card").

    Current printings shorten the *reminder* text for space - "target player
    may put [name] into their hand from their library, then shuffle" omits
    "search" and "reveal" - but the WotC ruling on Evie Frye (2024-07-05,
    fetched fresh this session) is explicit that both still happen: "Note
    that the target player searches their library (which may be affected by
    effects such as that of Stranglehold) and that the card they find is
    revealed, even though these words aren't included in the ability's
    reminder text." This writes out the rule's fuller wording, not the
    printed shorthand, so `machines/effects.py`'s ordinary
    search-reveal-shuffle clause parser reads it unchanged.
    """
    name = (ability.parameter or "").strip()
    return _expansion(
        ability,
        keyword="partner with",
        word=TriggerWord.WHEN,
        condition="this permanent enters",
        effect=(
            f"target player may search their library for a card named {name}, "
            "reveal it, put it into their hand, then shuffle"
        ),
        event=TriggerEvent.ENTERS_THE_BATTLEFIELD,
    )


def _extort_ability(ability: KeywordAbility) -> TriggeredAbility:
    """CR 702.101a: "Extort is a triggered ability. "Extort" means "Whenever
    you cast a spell, you may pay {W/B}. If you do, each opponent loses 1 life
    and you gain life equal to the total life lost this way.""

    CR 702.101b: "If a permanent has multiple instances of extort, each
    triggers separately" - one expansion per printed instance, as every
    `_TRIGGER_EXPANSIONS` entry gives. The effect is read off this text by
    `machines/effects.py`'s pay-then-drain reader.
    """
    return _expansion(
        ability,
        keyword="extort",
        word=TriggerWord.WHENEVER,
        condition="you cast a spell",
        effect=(
            "you may pay {W/B}. If you do, each opponent loses 1 life and you gain life "
            "equal to the total life lost this way."
        ),
        event=TriggerEvent.CAST_SPELL,
    )


#: CR 702.191a's intervening "if", as `_increment_ability` writes it out.
INCREMENT_CONDITION = (
    "this permanent is a creature and the amount of mana spent to cast that spell is "
    "greater than this creature's power or this creature's toughness"
)


def _increment_ability(ability: KeywordAbility) -> TriggeredAbility:
    """CR 702.191a: "Increment is a triggered ability. 'Increment' means
    'Whenever you cast a spell, if this permanent is a creature and the
    amount of mana spent to cast that spell is greater than this creature's
    power or this creature's toughness, put a +1/+1 counter on this
    creature.'"

    CR 702.191b: multiple instances trigger separately - one expansion per
    printed instance, as every `_TRIGGER_EXPANSIONS` entry gives. The
    intervening "if" (CR 603.4) is answered by `machines/triggers.
    intervening_if_answer` from the cast spell's `CastRecord.mana_spent`
    (CR 601.2h).
    """
    return _expansion(
        ability,
        keyword="increment",
        word=TriggerWord.WHENEVER,
        condition="you cast a spell",
        effect="put a +1/+1 counter on this creature",
        event=TriggerEvent.CAST_SPELL,
        intervening_if=INCREMENT_CONDITION,
    )


def _battle_cry_ability(ability: KeywordAbility) -> TriggeredAbility:
    """CR 702.91a: "Battle cry" means "Whenever this creature attacks, each
    other attacking creature gets +1/+0 until end of turn.""

    CR 702.91b: "If a creature has multiple instances of battle cry, each
    triggers separately" - the same per-printed-instance shape ward,
    prowess and every other `_TRIGGER_EXPANSIONS` entry already have for
    free, since `keyword_triggered_abilities` builds one `TriggeredAbility`
    per `KeywordAbility` this module found (one per printed line), not one
    per card.
    """
    return _expansion(
        ability,
        keyword="battle cry",
        word=TriggerWord.WHENEVER,
        condition="this creature attacks",
        effect="each other attacking creature gets +1/+0 until end of turn",
        event=TriggerEvent.ATTACKS,
    )


def _annihilator_ability(ability: KeywordAbility) -> TriggeredAbility:
    """CR 702.86a: "Annihilator N" means "Whenever this creature attacks,
    defending player sacrifices N permanents."

    N stays on the printed line (`raw`), which `_annihilator_effect` reads as
    the trigger resolves - a number, or an X with its "where X is ..."
    definition, counted then (CR 608.2h). CR 702.86b's "each triggers
    separately" is `keyword_triggered_abilities`' one ability per instance.
    """
    count = ability.count if ability.count is not None else "X"
    return _expansion(
        ability,
        keyword="annihilator",
        word=TriggerWord.WHENEVER,
        condition="this creature attacks",
        effect=f"defending player sacrifices {count} permanents",
        event=TriggerEvent.ATTACKS,
    )


def _renown_ability(ability: KeywordAbility) -> TriggeredAbility:
    """CR 702.112a: "Renown N" means "When this creature deals combat damage
    to a player, if it isn't renowned, put N +1/+1 counters on it and it
    becomes renowned."

    "If it isn't renowned" is an intervening *if* (CR 603.4), read by
    `machines/conditions/objects.py` off `CardState.renowned`; CR 702.112c's
    "each triggers separately" for several instances is
    `keyword_triggered_abilities`' one ability per printed line - the first
    to resolve makes the creature renowned, and the others are then removed
    by CR 608.2a's recheck."""
    count = ability.count if ability.count is not None else 1
    return _expansion(
        ability,
        keyword="renown",
        word=TriggerWord.WHEN,
        condition="this creature deals combat damage to a player",
        intervening_if="it isn't renowned",
        effect=f"put {count} +1/+1 counters on it and it becomes renowned",
        event=TriggerEvent.DEALS_DAMAGE,
    )


def _soulbond_abilities(ability: KeywordAbility) -> list[TriggeredAbility]:
    """CR 702.95a: soulbond is two triggered abilities, both "you may pair"
    (`machines/soulbond.py` resolves them)."""
    return [
        _expansion(
            ability,
            keyword="soulbond",
            word=TriggerWord.WHEN,
            condition="this creature enters",
            effect="you may pair this creature with another unpaired creature you control",
            event=TriggerEvent.ENTERS_THE_BATTLEFIELD,
        ),
        _expansion(
            ability,
            keyword="soulbond",
            word=TriggerWord.WHENEVER,
            condition="another creature you control enters",
            effect="you may pair that creature with this creature",
            event=TriggerEvent.ENTERS_THE_BATTLEFIELD,
        ),
    ]


def _flanking_ability(ability: KeywordAbility) -> TriggeredAbility:
    """CR 702.25a: "Flanking is a triggered ability that triggers during the
    declare blockers step. (See rule 509, 'Declare Blockers Step.') 'Flanking'
    means 'Whenever this creature becomes blocked by a creature without
    flanking, the blocking creature gets -1/-1 until end of turn.'"

    CR 702.25b's "each triggers separately" for several printed instances is
    `keyword_triggered_abilities`'s own one-`TriggeredAbility`-per-line shape,
    the same free ride ward, prowess and battle cry already get. CR 509.3d's
    "becomes blocked by a creature" already triggers once per blocking pair -
    `Game.declare_blockers` emits one `TriggerEvent.BLOCKS` event per blocker,
    `subject_id` always the blocker - so a creature with flanking blocked by
    several creatures needs no extra machinery here either: the "without
    flanking" qualifier is read off that same event's blocker by
    `machines/triggers.condition_matches`'s `BLOCKS` branch, and "the blocking
    creature" in the effect is `machines/effects._parse_event_subject_pump_
    clause`'s existing "event's own subject" pump, which already reads
    `AbilityOnStack.event.subject_id` - the blocker, once again - rather than
    the ability's own source.
    """
    return _expansion(
        ability,
        keyword="flanking",
        word=TriggerWord.WHENEVER,
        condition="this creature becomes blocked by a creature without flanking",
        effect="the blocking creature gets -1/-1 until end of turn",
        event=TriggerEvent.BLOCKS,
    )


def _exalted_ability(ability: KeywordAbility) -> TriggeredAbility:
    """CR 702.83a: "Exalted" means "Whenever a creature you control attacks
    alone, that creature gets +1/+1 until end of turn." CR 702.83b: each
    instance of exalted on a permanent triggers separately, which is
    `keyword_triggered_abilities`' one ability per instance (a granted one
    included, so two Slivers granted exalted are two instances)."""
    return _expansion(
        ability,
        keyword="exalted",
        word=TriggerWord.WHENEVER,
        condition="a creature you control attacks alone",
        effect="that creature gets +1/+1 until end of turn",
        event=TriggerEvent.ATTACKS,
    )


def _frenzy_ability(ability: KeywordAbility) -> TriggeredAbility:
    """CR 702.68a: "Frenzy N" means "Whenever this creature attacks and isn't
    blocked, it gets +N/+0 until end of turn." CR 702.68b: multiple instances
    each trigger."""
    count = ability.count if ability.count is not None else 1
    return _expansion(
        ability,
        keyword="frenzy",
        word=TriggerWord.WHENEVER,
        condition="this creature attacks and isn't blocked",
        effect=f"it gets +{count}/+0 until end of turn",
        event=TriggerEvent.ATTACKS_UNBLOCKED,
    )


def _bushido_ability(ability: KeywordAbility) -> TriggeredAbility:
    """CR 702.45a: "Bushido N" means "Whenever this creature blocks or becomes
    blocked, it gets +N/+N until end of turn." CR 702.45b: multiple instances
    each trigger."""
    count = ability.count if ability.count is not None else 1
    return _expansion(
        ability,
        keyword="bushido",
        word=TriggerWord.WHENEVER,
        condition="this creature blocks or becomes blocked",
        # "this creature", not "it": the event's subject is the *other* creature
        # of the blocking pair when this one becomes blocked.
        effect=f"this creature gets +{count}/+{count} until end of turn",
        event=TriggerEvent.BLOCKS,
    )


def _decayed_ability(ability: KeywordAbility) -> TriggeredAbility:
    """CR 702.147a: "Decayed represents a static ability and a triggered
    ability. 'Decayed' means 'This creature can't block' and 'When this
    creature attacks, sacrifice it at end of combat.'"

    Only the triggered half is written out here. The static "can't block"
    half (CR 509.1b) is read directly off the keyword by `machines/combat.
    block_refusal` (`has_keyword`), the same way flying/reach's own combat
    rule is read there rather than as parsed ability-line text - so it needs
    no `TriggeredAbility` of its own.

    "Sacrifice it" is self-referential: `machines/effects.py`'s own
    `_parse_delayed_single_clause` reads it off the ATTACKS event's own
    `subject_id` (CR 508.1a), which for this ability is always this
    creature, and creates the CR 603.7 delayed trigger that fires "at end of
    combat" (CR 511.2).
    """
    return _expansion(
        ability,
        keyword="decayed",
        word=TriggerWord.WHEN,
        condition="this creature attacks",
        effect="sacrifice it at end of combat",
        event=TriggerEvent.ATTACKS,
    )


#: The N on an annihilator line: "Annihilator 2", or "Annihilator X, where X
#: is the number of +1/+1 counters on it" (the line Ulamog, the Defiler's
#: static ability grants it).
_ANNIHILATOR_COUNT_RE = re.compile(
    r"^annihilator\s+(?P<n>\d+|x)\b(?:\s*,\s*where x is (?P<expr>[^.(]+))?",
    re.IGNORECASE,
)


def _annihilator_effect(game: Any, ability: AbilityOnStack) -> None:
    """CR 702.86a's effect: "defending player sacrifices N permanents."

    **Defending player** is CR 508.5's: the player the creature is attacking
    (or that planeswalker's controller, or that battle's protector), read off
    the attack event's own `defender` through `combat.defending_player`, so
    it still answers once the creature has left combat.

    **N** is read off the keyword line: a number, or X counted now, as the
    trigger resolves (CR 608.2h), with "it" the creature itself - or its last
    known information once it has left the battlefield. An X this engine
    cannot count fails closed with an `UnmodeledTriggerEffectNotice` rather
    than sacrificing a guessed number.

    **Which permanents** is the defending player's own choice (CR 701.21a),
    the same edict body every "sacrifices N `<permanents>` of their choice"
    clause shares: fewer than N sacrifices all of them, and nobody is asked a
    question with only one answer.
    """
    from .combat import defending_player
    from .effects import (
        UnmodeledTriggerEffectNotice,
        _sacrifice_of_choice_clause_effect,
        amount_expression,
    )

    printed = ability.ability
    raw = printed.raw if isinstance(printed, TriggeredAbility) else ""
    match = _ANNIHILATOR_COUNT_RE.match((raw or "").strip())
    count: int | None = None
    if match is not None:
        if match.group("n").lower() != "x":
            count = int(match.group("n"))
        elif match.group("expr") is not None:
            reader = amount_expression(match.group("expr"))
            if reader is not None:
                source = ability.source(game)
                if source is None or source.zone is not Zone.BATTLEFIELD:
                    source = ability.source_last_known
                count = reader(game, ability.controller, source, 0)
    if count is None:
        game.unmodeled_trigger_effect_notices.append(
            UnmodeledTriggerEffectNotice(
                source_id=ability.source_id,
                source_name=ability.source_name,
                text=raw or "annihilator",
            )
        )
        return
    event = ability.event
    if count <= 0 or event is None or event.defender is None:
        return
    username = defending_player(game, event.defender)
    if username is None:
        return
    sacrifice = _sacrifice_of_choice_clause_effect(
        "permanent", count, "a permanent" if count == 1 else f"{count} permanents"
    )
    sacrifice(game, game.player(username), ability.source_name, source_id_of(ability))


def _cumulative_upkeep_ability(ability: KeywordAbility) -> TriggeredAbility:
    """CR 702.24a: "'Cumulative upkeep [cost]' means 'At the beginning of your
    upkeep, if this permanent is on the battlefield, put an age counter on this
    permanent. Then you may pay [cost] for each age counter on it. If you
    don't, sacrifice it.'"

    [cost] is the printed one, verbatim: the space form ("Cumulative upkeep
    {1}", `KeywordAbility.cost`), the em-dash form ("Cumulative upkeep-Discard
    a card.", `.cost` too) and the choice form ("Cumulative upkeep {G} or
    {W}", which the keyword parser leaves in `.parameter`).
    `_cumulative_upkeep_effect` reads it back out of the effect text.

    CR 702.24b: each printed instance is its own ability, and
    `keyword_triggered_abilities` already yields one per instance.
    """
    printed = (ability.cost or ability.parameter or "").strip().rstrip(".")
    return _expansion(
        ability,
        keyword="cumulative upkeep",
        word=TriggerWord.AT,
        condition="the beginning of your upkeep",
        intervening_if="this permanent is on the battlefield",
        effect=(
            f"put an age counter on this permanent. Then you may pay {printed} for each age "
            "counter on it. If you don't, sacrifice it"
        ),
        event=TriggerEvent.BEGINNING_OF_STEP,
    )


#: CR 702.30a's own intervening "if", written out by `_echo_ability` and read
#: by `machines/triggers/conditions.intervening_if_answer` through
#: `Game.came_under_control_since_last_upkeep`.
ECHO_INTERVENING_IF = (
    "this permanent came under your control since the beginning of your last upkeep"
)


def _echo_ability(ability: KeywordAbility) -> TriggeredAbility:
    """CR 702.30a: "'Echo [cost]' means 'At the beginning of your upkeep, if
    this permanent came under your control since the beginning of your last
    upkeep, sacrifice it unless you pay [cost].'"

    [cost] is the printed one: the space form ("Echo {2}{R}{R}",
    `KeywordAbility.cost`) and the em-dash form ("Echo-Discard a card.",
    `.cost` or `.parameter`), plus a "where X is `<expr>`" tail a static
    "has echo {X}, where X is ..." line carries (`self_echo_lines`), which
    `_echo_effect` evaluates as the cost is paid.
    """
    printed = (ability.cost or ability.parameter or "").strip().rstrip(".")
    return _expansion(
        ability,
        keyword="echo",
        word=TriggerWord.AT,
        condition="the beginning of your upkeep",
        intervening_if=ECHO_INTERVENING_IF,
        effect=f"sacrifice it unless you pay {printed}",
        event=TriggerEvent.BEGINNING_OF_STEP,
    )


#: "This creature has echo {X}, where X is your life total." (Volcano
#: Hellion) - a static ability whose whole content is the keyword (CR 702.30a)
#: on its own object, with CR 107.3's X defined by the text; the cost is a
#: mana cost, the "where X is" tail kept on it for `_echo_effect`.
_SELF_ECHO_LINE_RE = re.compile(
    r"^this (?:creature|permanent) has echo (?P<cost>(?:\{[^}]+\})+)"
    r"(?P<where>, where X is [^.]+)?\.?$",
    re.IGNORECASE,
)


def self_echo_lines(card: Card) -> list[KeywordAbility]:
    """Every "`<this>` has echo `<cost>`[, where X is `<expr>`]" line of `card`,
    as the keyword ability it states - read off the printed text since the
    keyword parser sees a sentence, not a keyword line."""
    found: list[KeywordAbility] = []
    for line in (card.oracle_text or "").splitlines():
        text = line.split("(")[0].strip()
        match = _SELF_ECHO_LINE_RE.fullmatch(text)
        if match is None:
            continue
        cost = match.group("cost") + (match.group("where") or "")
        found.append(
            KeywordAbility(
                raw=line,
                text=text,
                face=card.name,
                keyword="Echo",
                canonical="Echo",
                cost=cost,
                cost_is_mana=True,
            )
        )
    return found


def is_self_echo_line(text: str) -> bool:
    """Whether a static line is `_SELF_ECHO_LINE_RE`'s shape whose cost
    `_echo_effect` can read - asked by `support._static_ability_category`."""
    match = _SELF_ECHO_LINE_RE.fullmatch(text.split("(")[0].strip())
    if match is None:
        return False
    printed = match.group("cost") + (match.group("where") or "")
    return _echo_cost(printed, None, None, None) is not None


def _mobilize_ability(ability: KeywordAbility) -> TriggeredAbility:
    """CR 702.181a: "Mobilize N" means "Whenever this creature attacks, create N
    1/1 red Warrior creature tokens. Those tokens enter tapped and attacking.
    Sacrifice them at the beginning of the next end step.""
    """
    count = ability.count if ability.count is not None else "X"
    return _expansion(
        ability,
        keyword="mobilize",
        word=TriggerWord.WHENEVER,
        condition="this creature attacks",
        effect=(
            f"create {count} 1/1 red Warrior creature tokens. Those tokens enter tapped and "
            f"attacking. Sacrifice them at the beginning of the next end step"
        ),
        event=TriggerEvent.ATTACKS,
    )


#: The count on a mobilize line: "Mobilize 2", or "Mobilize X, where X is the
#: number of creature cards in your graveyard" (Avenger of the Fallen).
_MOBILIZE_COUNT_RE = re.compile(
    r"^mobilize\s+(?P<n>\d+|x)\b(?:\s*,\s*where x is (?P<expr>[^.(]+))?",
    re.IGNORECASE,
)


def _mobilize_effect(game: Any, ability: AbilityOnStack) -> None:
    """CR 702.181a's effect: "create N 1/1 red Warrior creature tokens. Those
    tokens enter tapped and attacking. Sacrifice them at the beginning of the
    next end step."

    **N** is read off the keyword line the ability came from, not off its
    reminder text or the card: a number, or CR 608.2h's "where X is ..."
    counted once, now, through `machines/effects.count_expression`. An X this
    engine cannot count fails closed with an `UnmodeledTriggerEffectNotice`
    rather than creating a guessed number of tokens.

    **What each token attacks** is CR 508.4: "its controller chooses which
    defending player, planeswalker a defending player controls, or battle a
    defending player protects it's attacking as it enters the battlefield",
    and mobilize specifies nothing. With one thing to attack there is nothing
    to ask; with more, the controller is asked once per token as it enters,
    with the object the mobilizing creature is attacking offered first (and
    so the default). CR 506.3b is `create_tokens`' own: a token whose
    controller is not an attacking player enters but never attacks.

    **"Sacrifice them"** is one delayed triggered ability (CR 603.7) about
    every token this made - `delayed.SacrificeEach` - so one object goes on
    the stack at the next end step, and CR 603.7c is applied token by token.
    """
    from ..models.card import Color
    from ..models.token import TokenDefinition, create_tokens
    from .combat import attackable_defenders
    from .delayed import DelayedTrigger, SacrificeEach
    from .effects import UnmodeledTriggerEffectNotice, count_expression
    from .turn import Step

    printed = ability.ability
    raw = printed.raw if isinstance(printed, TriggeredAbility) else ""
    controller = game.controller_of(ability).username
    count: int | None = None
    match = _MOBILIZE_COUNT_RE.match((raw or "").strip())
    if match is not None:
        if match.group("n").lower() != "x":
            count = int(match.group("n"))
        elif match.group("expr") is not None:
            measure = count_expression(match.group("expr"))
            if measure is not None:
                count = measure(game, controller)
    if count is None:
        game.unmodeled_trigger_effect_notices.append(
            UnmodeledTriggerEffectNotice(
                source_id=ability.source_id,
                source_name=ability.source_name,
                text=raw or "mobilize",
            )
        )
        return
    if count <= 0:
        return

    mobilizing = next(
        (
            attack.defender
            for attack in game.combat.attacks
            if attack.attacker_id == ability.source_id
        ),
        None,
    )

    def choose_defender(token: CardState) -> TargetRef | None:
        if token.controller != game.active_player.username:
            return None  # CR 506.3b: it enters, but never attacking.
        candidates = attackable_defenders(game, controller)
        if mobilizing in candidates:
            candidates.remove(mobilizing)
            candidates.insert(0, mobilizing)
        if len(candidates) <= 1:
            return candidates[0] if candidates else None
        chosen = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_TARGETS,
                player=controller,
                prompt=(
                    f"choose which player, planeswalker or battle this {token.name} "
                    "is attacking (CR 508.4)"
                ),
                source=ability.source_name,
                source_id=source_id_of(ability),
                targets=tuple(candidates),
                target_minimum=1,
                target_maximum=1,
            )
        )
        return TargetRef.coerce(chosen[0])

    warrior = TokenDefinition(
        types=(Type.CREATURE,),
        subtypes=("Warrior",),
        colors=(Color.RED,),
        power=1,
        toughness=1,
    )
    created = create_tokens(
        game, warrior, controller, count, tapped=True, attacking=choose_defender
    )
    on_battlefield = [token for token in created if token.zone is Zone.BATTLEFIELD]
    if not on_battlefield:
        return
    game.create_delayed_trigger(
        DelayedTrigger(
            text="Sacrifice them at the beginning of the next end step.",
            effect=SacrificeEach(
                subjects=tuple((token.id, token.zone_change_stamp) for token in on_battlefield)
            ),
            event=TriggerEvent.BEGINNING_OF_STEP,
            step=Step.END_STEP,
            controller=controller,
            source_id=ability.source_id,
            source_name=ability.source_name,
        )
    )


def _firebending_ability(ability: KeywordAbility) -> TriggeredAbility:
    """CR 702.189a: "Firebending is a triggered ability. 'Firebending N' means
    'Whenever this creature attacks, add N {R}. Until end of combat, you don't
    lose this mana as steps and phases end.'"
    """
    if ability.count is not None:
        amount, tail = str(ability.count), ""
    else:
        # "X, where X is this creature's power" - CR 608.2h reads the number
        # as the ability resolves, so the definition is carried through into
        # the effect text verbatim rather than resolved here.
        parameter = (ability.parameter or "X").strip()
        head, _, where = parameter.partition(",")
        amount = head.strip() or "X"
        tail = f", {where.strip()}" if where.strip() else ""
    return _expansion(
        ability,
        keyword="firebending",
        word=TriggerWord.WHENEVER,
        condition="this creature attacks",
        effect=(
            f"add {amount} {{R}}{tail}. Until end of combat, you don't lose this mana "
            "as steps and phases end"
        ),
        event=TriggerEvent.ATTACKS,
    )


def _madness_ability(ability: KeywordAbility) -> TriggeredAbility:
    """CR 702.35a's *second* ability. Madness is two abilities, not one.

    "Madness is a keyword that represents two abilities. The first is a static
    ability that functions while the card with madness is in a player's hand.
    The second is a triggered ability that functions when the first ability is
    applied." The first is the discard replacement - `madness_replaces_discard`
    below - and this is the second: "When this card is exiled this way, its
    owner may cast it by paying [cost] rather than paying its mana cost. If that
    player doesn't, they put this card into their graveyard."
    """
    printed = ability.cost or ""
    return _expansion(
        ability,
        keyword="madness",
        word=TriggerWord.WHEN,
        condition="this card is exiled this way",
        effect=(
            f"its owner may cast it by paying {printed} rather than paying its mana cost. "
            f"If that player doesn't, they put this card into their graveyard"
        ),
        event=TriggerEvent.EXILED,
    )


def _miracle_ability(ability: KeywordAbility) -> TriggeredAbility:
    """CR 702.94a's *second* ability. Miracle is a static ability linked to a
    triggered one (CR 603.11, CR 607.2h).

    "'Miracle [cost]' means 'You may reveal this card from your hand as you
    draw it if it's the first card you've drawn this turn. When you reveal
    this card this way, you may cast it by paying [cost] rather than its mana
    cost.'" The static half is the reveal question `Game.draw_cards` asks;
    this is the trigger it links to, which functions in the hand
    (`machines/triggers.zones_ability_functions_in`) and fires only off the
    reveal that static ability made (`ExtraTriggerEvent.
    REVEALED_FOR_MIRACLE`).
    """
    printed = ability.cost or ""
    return _expansion(
        ability,
        keyword="miracle",
        word=TriggerWord.WHEN,
        condition="you reveal this card this way",
        effect=f"you may cast it by paying {printed} rather than its mana cost",
        event=None,
    )


def _hideaway_ability(ability: KeywordAbility) -> TriggeredAbility:
    """CR 702.75a: "Hideaway N" means "When this permanent enters, look at the
    top N cards of your library. Exile one of them face down and put the rest
    on the bottom of your library in a random order.""

    CR 702.75b: pre-rules-change printings fixed N at four and entered
    tapped; the modern template prints both `N` and "This land enters
    tapped." explicitly, so nothing here assumes either - `ability.count` is
    read off the actual printed line, defaulting to four only if a printing
    somehow omits it.
    """
    count = ability.count if ability.count is not None else 4
    return _expansion(
        ability,
        keyword="hideaway",
        word=TriggerWord.WHEN,
        condition="this permanent enters",
        effect=(
            f"look at the top {count} cards of your library. Exile one of them face down "
            "and put the rest on the bottom of your library in a random order"
        ),
        event=TriggerEvent.ENTERS_THE_BATTLEFIELD,
    )


def _suspend_abilities(ability: KeywordAbility) -> list[TriggeredAbility]:
    """CR 702.62a's *second and third* abilities. Suspend is three abilities.

    "Suspend is a keyword that represents three abilities. The first is a
    static ability that functions while the card with suspend is in a
    player's hand. The second and third are triggered abilities that function
    in the exile zone. 'Suspend N-[cost]' means 'If you could begin to cast
    this card by putting it onto the stack from your hand, you may pay [cost]
    and exile it with N time counters on it. This action doesn't use the
    stack,' and 'At the beginning of your upkeep, if this card is suspended,
    remove a time counter from it,' and 'When the last time counter is
    removed from this card, if it's exiled, you may play it without paying
    its mana cost if able. If you don't, it remains exiled. If you cast a
    creature spell this way, it gains haste until you lose control of the
    spell or the permanent it becomes.'"

    The first ability is the CR 116.2f special action and belongs to
    `machines/casting.MarkedExile.suspend`, not here: it does not use the
    stack, so it is not a triggered ability at all.

    The other two are, and until this existed neither had a dispatcher.
    `machines/triggers.triggers_for` reads `triggered_abilities_of(source.
    card)`, and Lotus Bloom's only text matching "at the beginning of your
    upkeep" is the reminder text in parentheses - which is not an ability -
    so no `TriggeredAbility` object existed to find and a suspended card's
    time counters came off only when a caller reached in and removed one by
    hand. Both are keyed by `TriggeredAbility.keyword`, and
    `machines/triggers.zones_ability_functions_in` reads the same field for
    the rule's own "function in the exile zone".

    The third carries `event=None`: no `machines/abilities.TriggerEvent`
    names "the last time counter is removed", so it is matched from its
    printed condition through `machines/triggers._unread_condition_matches`
    against `ExtraTriggerEvent.LAST_TIME_COUNTER_REMOVED`, the same shape
    Caged Sun's and Wan Shi Tong's unread conditions already take.
    """
    return [
        _expansion(
            ability,
            keyword="suspend",
            word=TriggerWord.AT,
            condition="the beginning of your upkeep",
            intervening_if="this card is suspended",
            effect="remove a time counter from it",
            event=TriggerEvent.BEGINNING_OF_STEP,
        ),
        _expansion(
            ability,
            keyword="suspend",
            word=TriggerWord.WHEN,
            condition="the last time counter is removed from this card",
            intervening_if="it's exiled",
            effect=(
                "you may play it without paying its mana cost if able. If you don't, it "
                "remains exiled. If you cast a creature spell this way, it gains haste "
                "until you lose control of the spell or the permanent it becomes"
            ),
            event=None,
        ),
    ]


def _vanishing_abilities(ability: KeywordAbility) -> list[TriggeredAbility]:
    """CR 702.63a's *second and third* abilities. Vanishing is three abilities,
    the same shape suspend is (`_suspend_abilities` above), over a battlefield
    permanent instead of an exiled card.

    "Vanishing is a keyword that represents three abilities. 'Vanishing N'
    means 'This permanent enters with N time counters on it,' 'At the
    beginning of your upkeep, if this permanent has a time counter on it,
    remove a time counter from it,' and 'When the last time counter is removed
    from this permanent, sacrifice it.'" CR 702.63b: vanishing printed with no
    number is only these two triggered abilities - the first, entering-counters
    ability is never part of it - which is exactly why `KeywordAbility.count`
    being `None` is `machines/replacement._vanishing_entering_counters`'s own
    signal to write nothing, not something read here.

    The first ability is the CR 614.1c replacement effect
    (`machines/replacement._vanishing_entering_counters`); it is not a
    triggered ability at all, so it does not appear in this list.

    Both abilities below function on the battlefield, the CR 113.6 default
    `machines/triggers.zones_ability_functions_in` already applies when
    neither the condition nor an intervening *if* names another zone - unlike
    suspend's identical shape, nothing here has to widen `Game.emit`'s source
    list, because a battlefield permanent is already offered for every
    `TriggerEvent.BEGINNING_OF_STEP` event.

    The third carries `event=None`, matched through `machines/triggers.
    _unread_condition_matches` against `ExtraTriggerEvent.
    LAST_TIME_COUNTER_REMOVED` - the same shape suspend's own third ability
    takes, and `_LAST_TIME_COUNTER_CONDITION` accepts both "this card" and
    "this permanent" so the one pattern serves both keywords.
    """
    return [
        _expansion(
            ability,
            keyword="vanishing",
            word=TriggerWord.AT,
            condition="the beginning of your upkeep",
            intervening_if="this permanent has a time counter on it",
            effect="remove a time counter from it",
            event=TriggerEvent.BEGINNING_OF_STEP,
        ),
        _expansion(
            ability,
            keyword="vanishing",
            word=TriggerWord.WHEN,
            condition="the last time counter is removed from this permanent",
            effect="sacrifice it",
            event=None,
        ),
    ]


def _single(
    build: Callable[[KeywordAbility], TriggeredAbility],
) -> Callable[[KeywordAbility], list[TriggeredAbility]]:
    """Adapt a keyword whose expansion is exactly one triggered ability.

    CR 702.1 calls a keyword "shorthand for one or more abilities", and
    suspend (CR 702.62a) is the pool's first keyword whose shorthand covers
    *two* triggered abilities at once - so the registry below answers with a
    list. Every other entry answers with a list of one, and this is what says
    so without rewriting ten one-line expansions to build a list each.
    """
    return lambda ability: [build(ability)]


#: The keyword lines this module can write out as triggered abilities, by the
#: Scryfall spelling of the keyword. A keyword missing from here is a keyword
#: `machines/triggers.py` still cannot produce.
def _ingest_ability(ability: KeywordAbility) -> TriggeredAbility:
    """CR 702.115a: 'Ingest' means 'Whenever this creature deals combat damage
    to a player, that player exiles the top card of their library.'"""
    return _expansion(
        ability,
        keyword="ingest",
        word=TriggerWord.WHENEVER,
        condition="this creature deals combat damage to a player",
        effect="that player exiles the top card of their library",
        event=TriggerEvent.DEALS_DAMAGE,
    )


def _poisonous_ability(ability: KeywordAbility) -> TriggeredAbility:
    """CR 702.70a: "Poisonous N" means "Whenever this creature deals combat
    damage to a player, that player gets N poison counters." CR 702.70b's
    "each triggers separately" is one ability per instance, printed or
    granted ("All Sliver creatures have poisonous 1.", "Enchanted creature
    has poisonous 3.")."""
    count = ability.count if ability.count is not None else 1
    noun = "poison counter" if count == 1 else "poison counters"
    return _expansion(
        ability,
        keyword="poisonous",
        word=TriggerWord.WHENEVER,
        condition="this creature deals combat damage to a player",
        effect=f"that player gets {count} {noun}",
        event=TriggerEvent.DEALS_DAMAGE,
    )


_TRIGGER_EXPANSIONS: dict[str, Callable[[KeywordAbility], list[TriggeredAbility]]] = {
    "ward": _single(_ward_ability),
    "prowess": _single(_prowess_ability),
    "cascade": _single(_cascade_ability),
    "ripple": _single(_ripple_ability),
    "storm": _single(_storm_ability),
    "replicate": _single(_replicate_ability),
    "persist": _single(_persist_ability),
    "undying": _single(_undying_ability),
    "modular": _single(_modular_ability),
    "mobilize": _single(_mobilize_ability),
    "offspring": _single(_offspring_ability),
    "firebending": _single(_firebending_ability),
    "evoke": _single(_evoke_ability),
    "madness": _single(_madness_ability),
    "miracle": _single(_miracle_ability),
    "hideaway": _single(_hideaway_ability),
    "suspend": _suspend_abilities,
    "impending": _single(_impending_ability),
    "vanishing": _vanishing_abilities,
    "battle cry": _single(_battle_cry_ability),
    "cumulative upkeep": _single(_cumulative_upkeep_ability),
    "echo": _single(_echo_ability),
    "partner with": _single(_partner_with_ability),
    "annihilator": _single(_annihilator_ability),
    "renown": _single(_renown_ability),
    "soulbond": _soulbond_abilities,
    "extort": _single(_extort_ability),
    "increment": _single(_increment_ability),
    "flanking": _single(_flanking_ability),
    "exalted": _single(_exalted_ability),
    "frenzy": _single(_frenzy_ability),
    "bushido": _single(_bushido_ability),
    "ingest": _single(_ingest_ability),
    "poisonous": _single(_poisonous_ability),
    "decayed": _single(_decayed_ability),
}
_TRIGGER_EXPANSIONS.update(LEGACY_EXPANSIONS)


#: God-Eternal Kefnet's whole line - the static "You may reveal the first card
#: you draw each turn as you draw it" and the trigger linked to it (CR 603.11,
#: CR 607.2h). The reduction is the number of generic mana the copy costs
#: less (CR 601.2f, CR 118.7).
_FIRST_DRAW_REVEAL_LINE_RE = re.compile(
    r"^You may reveal the first card you draw each turn as you draw it\.\s*"
    r"Whenever you reveal an instant or sorcery card this way, "
    r"copy that card and you may cast the copy\.\s*"
    r"That copy costs \{(?P<less>\d+)\} less to cast\.?$"
)


#: Keranos, God of Storms' line - the same static reveal, but mandatory and
#: only on the controller's own turns, with one linked trigger per kind of
#: card revealed: "Reveal the first card you draw on each of your turns.
#: Whenever you reveal a land card this way, draw a card. Whenever you reveal
#: a nonland card this way, <name> deals 3 damage to any target." (CR 121.2,
#: CR 701.20a, CR 603.11, CR 607.2h.)
_MANDATORY_FIRST_DRAW_REVEAL_LINE_RE = re.compile(
    r"^Reveal the first card you draw on each of your turns\.\s*"
    r"(?P<triggers>(?:Whenever you reveal an? (?:land|nonland) card this way, [^.]+\.?\s*)+)$"
)
_MANDATORY_REVEAL_TRIGGER_RE = re.compile(
    r"Whenever you reveal an? (?P<kind>land|nonland) card this way, (?P<effect>[^.]+)\.?"
)


def is_first_draw_reveal_line(text: str) -> bool:
    """Whether `text` is one of the first-draw reveal lines' whole shape - asked
    by `static_audit/cost_modification`."""
    stripped = text.split("(")[0].strip()
    return (
        _FIRST_DRAW_REVEAL_LINE_RE.fullmatch(stripped) is not None
        or _MANDATORY_FIRST_DRAW_REVEAL_LINE_RE.fullmatch(stripped) is not None
    )


def first_draw_reveal_lines(card: Card) -> list[str]:
    """Each printed line of `card` that is a first-draw reveal shape - the
    static reveal ability and its linked trigger(s) in one line."""
    return [
        line for line in (card.oracle_text or "").splitlines() if is_first_draw_reveal_line(line)
    ]


def first_draw_reveal_is_mandatory(card: Card) -> bool:
    """Whether the reveal is not a "may" (Keranos) - CR 701.20a."""
    return any(
        _MANDATORY_FIRST_DRAW_REVEAL_LINE_RE.fullmatch(line.split("(")[0].strip())
        for line in first_draw_reveal_lines(card)
    )


def first_draw_reveal_own_turns_only(card: Card) -> bool:
    """Whether the reveal happens only on its controller's turns ("on each of
    your turns") rather than on each turn (Kefnet's "each turn")."""
    return first_draw_reveal_is_mandatory(card)


def has_first_draw_reveal(card: Card) -> bool:
    """Whether `card` lets its controller reveal the turn's first draw as it
    is drawn (God-Eternal Kefnet) - asked by `Game._offer_first_draw_reveals`
    and `support._static_ability_category`."""
    return bool(first_draw_reveal_lines(card))


def first_draw_reveal_abilities(card: Card) -> list[TriggeredAbility]:
    """The triggered half of each `first_draw_reveal_lines` line, written out
    as the ability it is: "Whenever you reveal an instant or sorcery card this
    way, copy that card and you may cast the copy. That copy costs {N} less to
    cast." It fires only off a reveal the static half made
    (`ExtraTriggerEvent.REVEALED_FIRST_DRAW`)."""
    built: list[TriggeredAbility] = []
    for line in first_draw_reveal_lines(card):
        stripped = line.split("(")[0].strip()
        mandatory = _MANDATORY_FIRST_DRAW_REVEAL_LINE_RE.fullmatch(stripped)
        if mandatory is not None:
            for trigger in _MANDATORY_REVEAL_TRIGGER_RE.finditer(mandatory.group("triggers")):
                kind_condition = f"you reveal a {trigger.group('kind')} card this way"
                built.append(
                    TriggeredAbility(
                        raw=line,
                        text=f"Whenever {kind_condition}, {trigger.group('effect')}",
                        face=card.name,
                        word=TriggerWord.WHENEVER,
                        condition=kind_condition,
                        effect=trigger.group("effect"),
                        event=None,
                    )
                )
            continue
        match = _FIRST_DRAW_REVEAL_LINE_RE.fullmatch(stripped)
        assert match is not None
        condition = "you reveal an instant or sorcery card this way"
        effect = (
            "copy that card and you may cast the copy. "
            f"That copy costs {{{match.group('less')}}} less to cast"
        )
        built.append(
            TriggeredAbility(
                raw=line,
                text=f"Whenever {condition}, {effect}",
                face=card.name,
                word=TriggerWord.WHENEVER,
                condition=condition,
                effect=effect,
                event=None,
            )
        )
    return built


def keyword_triggered_abilities(card: Card) -> list[TriggeredAbility]:
    """Every triggered ability this card has that is printed as a keyword (CR 702.1).

    CR 702.1: a keyword ability is "shorthand for one or more abilities", and
    for the five keywords above the ability it is shorthand for is a triggered
    one. `machines/triggers.triggered_abilities_of` adds these to the abilities
    it read off the printed lines, so from CR 603.2's point of view there is no
    difference between a trigger a card spells out and one it abbreviates.

    In printed order, and one per printed instance - CR 702.108b and CR 702.85c
    both say multiple instances trigger separately, so a card printing prowess
    twice yields two abilities here.
    """
    built: list[TriggeredAbility] = []
    for ability in [*keyword_abilities(card), *self_echo_lines(card)]:
        expand = _TRIGGER_EXPANSIONS.get(ability.canonical.lower())
        if expand is not None:
            built.extend(expand(ability))
    built.extend(first_draw_reveal_abilities(card))
    return built


#: One keyword line as a *grant* writes it - "Evoke {4}", "Ward {2}", the
#: keyword and, when the rule takes one, a mana cost. Deliberately narrower
#: than the printed-line parser in `machines/abilities.py`: the only lines
#: that ever reach `granted_keyword_triggered_abilities` are lines this engine
#: wrote itself (`machines/casting.py` stamps the keyword it announced onto
#: `CardState.granted_ability_texts`), so anything more elaborate than
#: keyword-plus-mana is not a shape that can arrive here, and matching it
#: loosely would only let an ordinary granted *sentence* be mistaken for a
#: keyword.
_GRANTED_KEYWORD_LINE_RE = re.compile(
    r"^(?P<keyword>[A-Za-z][A-Za-z'-]*)(?:\s+(?P<cost>\{[^:]*\}))?\.?$"
)
#: A granted keyword that takes a number rather than a cost - the line
#: `machines/layers._self_has_counted_trigger_keyword_builder` writes for a
#: static "`<this>` has annihilator X, where X is ..." (Ulamog, the Defiler):
#: "Annihilator 2" or "Annihilator X, where X is `<expr>`".
_GRANTED_COUNTED_KEYWORD_LINE_RE = re.compile(
    r"^(?P<keyword>[A-Za-z][A-Za-z'-]*)\s+(?P<count>\d+|X)(?:,\s*where X is [^.]+)?\.?$"
)


#: A granted keyword whose cost is a sentence rather than mana, joined by
#: CR 702.21a's em dash - "Ward—Pay 2 life." as Hexing Squelcher's
#: "Other creatures you control have "Ward—Pay 2 life."" and Winter, Cursed
#: Rider's "Artifacts you control have "Ward—Pay 2 life."" grant it, the
#: same line a printed non-mana ward is. The cost is read by the same
#: `total_cost_for_phrase` a printed one goes through (`_keyword_cost`).
_GRANTED_DASH_COST_KEYWORD_LINE_RE = re.compile(
    r"^(?P<keyword>[A-Za-z][A-Za-z'-]*)\s*—\s*(?P<cost>[^{—][^—]*?)\.?$"
)


def writes_triggered_ability(keyword: str) -> bool:
    """Whether this module writes `keyword` out as a triggered ability (CR
    702.1) - asked by `machines/layers.py` before it grants one to an object,
    so a grant only ever hands out a keyword that will actually do something."""
    return keyword.lower() in _TRIGGER_EXPANSIONS


def granted_keyword_ability(text: str) -> KeywordAbility | None:
    """One `CardState.granted_ability_texts` line read back as a CR 702 keyword.

    None for a line that is not a bare keyword, and None for a keyword this
    module writes no triggered ability for - a grant nothing here can expand
    hands out nothing rather than a guessed ability.
    """
    counted = _GRANTED_COUNTED_KEYWORD_LINE_RE.match(text.strip())
    if counted is not None:
        keyword = counted.group("keyword")
        if keyword.lower() not in _TRIGGER_EXPANSIONS:
            return None
        count = counted.group("count")
        return KeywordAbility(
            raw=text.strip(),
            text=text.strip(),
            face="",
            keyword=keyword,
            canonical=keyword,
            count=None if count.upper() == "X" else int(count),
        )
    dashed = _GRANTED_DASH_COST_KEYWORD_LINE_RE.match(text.strip())
    if dashed is not None:
        keyword = dashed.group("keyword")
        if keyword.lower() not in _TRIGGER_EXPANSIONS:
            return None
        return KeywordAbility(
            raw=text,
            text=text.strip(),
            face="",
            keyword=keyword,
            canonical=keyword,
            cost=dashed.group("cost").strip(),
            cost_is_mana=False,
        )
    match = _GRANTED_KEYWORD_LINE_RE.match(text.strip())
    if match is None:
        return None
    keyword = match.group("keyword")
    if keyword.lower() not in _TRIGGER_EXPANSIONS:
        return None
    cost = match.group("cost")
    return KeywordAbility(
        raw=text,
        text=text.strip(),
        face="",
        keyword=keyword,
        canonical=keyword,
        cost=cost,
        cost_is_mana=cost is not None,
    )


def granted_keyword_triggered_abilities(texts: Sequence[str]) -> list[TriggeredAbility]:
    """`CardState.granted_ability_texts`' keyword lines, written out as the
    triggered abilities CR 702.1 says they are shorthand for.

    The granted twin of `keyword_triggered_abilities`, and the reason a
    *granted* evoke sacrifices the creature it was paid for. CR 702.74a makes
    evoke two abilities - an alternative cost and "When this permanent enters,
    if its evoke cost was paid, its controller sacrifices it" - and a permanent
    that gained the keyword as it was cast keeps the second one: CR 400.7b,
    "effects from static abilities that grant an ability to a permanent spell
    that functions on the battlefield continue to apply to the permanent that
    spell becomes", with CR 611.3d adding that such an ability "lasts
    indefinitely unless some other duration is stated". So killing the granting
    permanent in response changes nothing, which is exactly what this makes
    observable: the keyword is on the *object*, not on the grantor.

    Callers append this to the printed list rather than replacing it, the same
    convention `granted_activated_abilities_of` documents for its own half.
    """
    built: list[TriggeredAbility] = []
    for text in texts:
        ability = granted_keyword_ability(text)
        if ability is None:
            continue
        expand = _TRIGGER_EXPANSIONS.get(ability.canonical.lower())
        if expand is not None:
            built.extend(expand(ability))
    return built


# --------------------------------------------------------------------------
# Activating an ability, from whichever zone it functions in (CR 602.1a)
# --------------------------------------------------------------------------


def statically_priced(activation: "KeywordActivation") -> "KeywordActivation":
    """`activation` with every ability cost modifier in play applied to its
    mana (`machines/cost/abilities.py`: "Abilities you activate that aren't
    mana abilities cost {2} less", "Activated abilities of creature cards in
    your graveyard cost {1} less", ...). Equip and ninjutsu price themselves
    (their builders know the target and the returned creature), and an
    activation built from `Game.activation_cost` is already priced."""
    game = activation.game
    if game is None:
        return activation
    kind = activation.keyword.lower()
    adjusted = ability_cost_adjustment(
        game,
        activation.player,
        activation.card,
        activation.cost.mana,
        kind=kind if kind in KEYWORD_KINDS else "",
        from_zone=activation.card.zone,
    )
    if adjusted != activation.cost.mana:
        activation.cost = TotalCost(mana=adjusted, components=activation.cost.components)
    return activation


class KeywordActivation(EngineModel):
    """One activation of a keyword's activated ability (CR 602.2).

    "To activate an ability is to put it onto the stack and pay its costs, so
    that it will eventually resolve and have its effect."

    The same three-step shape as `Casting` and `MarkedExile`: open the payment,
    pay it, then finish. `resolve` is here too, because CR 608.2n removes the
    ability from the stack and `machines/effects.py` is keyed by *card name* -
    a generic keyword has no card name to be keyed under, so the effect lives
    with the keyword instead.

    `activate` links the activation onto the `AbilityOnStack` it puts up, so
    `keyword_effect_for` can find the effect from the ability alone. Once a
    resolver consults that, `resolve` stops applying the effect itself: `applied`
    is what tells the two apart, so the effect happens exactly once either way.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    card: CardState
    player: str
    keyword: str
    rule: str
    zone: Zone
    """The zone this ability functions in (CR 702.29a's hand, CR 702.6a's
    battlefield). CR 602.5 refuses the activation from anywhere else."""
    cost: TotalCost
    ability: ActivatedAbility
    sorcery_only: bool = False
    """CR 602.1b timing, as printed in the rule the keyword expands to."""
    forecast: bool = False
    """CR 702.57b's own timing, mirrored from `ability.forecast` rather than
    read off printed instruction text the way `sorcery_only` is - Forecast's
    "only during the upkeep step of the card's owner and only once each
    turn" is the keyword's own meaning, never printed on the card. Checked in
    `why_not` and recorded in `_activate_impl` via `Game.forecast_activations`."""
    targets: list[TargetRef] = Field(default_factory=list)
    game: Any = Field(default=None, exclude=True, repr=False)
    """The live `Game` this activation acts on. Reset to `None` by a round
    trip and relinked from the outside by `Game.model_post_init`, which walks
    `self.stack` and `self.pending_triggers` for exactly this field the same
    way it already relinks every `Player.game` - see that method's own
    comment. Nothing in this module needs it to already be set for a decoded
    `AbilityOnStack.keyword_activation`: `run_effect` has not been called yet
    (see `result` below), and `Game._effect_of` only reaches
    `keyword_effect_for` - and so `run_effect` - after the ability is back on
    a real, live `Game`'s stack."""
    payment: CostPayment | None = None
    on_stack: AbilityOnStack | None = Field(default=None, exclude=True, repr=False)
    """The `AbilityOnStack` this activation put on the stack - a link back to
    the very object that, when this activation survives a round trip at all,
    holds it as `AbilityOnStack.keyword_activation`. Keeping this edge on
    serialisation would dump forever (`self -> on_stack -> keyword_activation
    -> self -> ...`), so it is `exclude=True` here and `AbilityOnStack.
    model_post_init` re-wires it from the other side after a decode - the one
    direction that does not reopen the loop."""
    applied: bool = False
    """True once this keyword's effect has happened (CR 608.2).

    Set by `run_effect`, whoever calls it. It exists so the effect cannot happen
    twice when both the resolver and `resolve` know how to run it."""
    result: Any = Field(default=None, exclude=True, repr=False)
    """Whatever the effect returned, kept for the caller that asked."""
    free_equip_from: str | None = None
    """The permanent whose "you may pay {0} rather than pay the equip cost of
    the first equip ability you activate ..." this equip activation took
    (`free_first_equip_source`, CR 118.9), or None for the printed cost."""
    craft_materials: tuple[UUID, ...] = ()
    """CR 702.167a: the materials this craft activation exiles, recorded on the
    returned card as `CardState.crafted_with` (CR 702.167c's "the exiled cards
    used to craft it")."""
    x_value: int = 0
    """CR 107.3a's X, announced with this activation (CR 602.2b) and carried to
    the `AbilityOnStack` - Roaring Earth's Channel "{X}{G}{G}, Discard this
    card: Put X +1/+1 counters ...". Zero when the cost carries no `{X}`."""
    generic_effect: bool = False
    """True for a printed, non-keyword activated ability (CR 602.1) whose
    effect is whatever `machines/effects.py` already makes of its own text -
    the ordinary path a battlefield activation of the same ability reaches.

    Channel and its P9 siblings (`docs/engine-coverage.md`) have no fixed rules
    meaning the way cycling's "draw a card" does: the text after the colon is
    arbitrary, card by card, and this module has no business guessing at it.
    Set this instead of adding a `KEYWORD_EFFECTS` row, and `activate` leaves
    `AbilityOnStack.keyword_activation` unset so `Game._effect_of` falls
    through past `keyword_effect_for` to its own `ActivatedAbility` branch -
    `_activated_index` finds the ability by its printed text regardless of
    which zone it was activated from (CR 113.7a: the ability on the stack is
    independent of its source), and `activated_effect_for` resolves it exactly
    the way it would from the battlefield."""

    def run_effect(self) -> Any:
        """Apply this keyword's effect, once (CR 608.2).

        The entry point a resolver uses through `keyword_effect_for`. Calling it
        again does nothing, which is what makes it safe for `resolve` to call it
        as a fallback.
        """
        if self.applied:
            return self.result
        self.applied = True
        effect = keyword_activation_effect(self.keyword)
        self.result = effect(self) if effect is not None else None
        return self.result

    def why_not(self) -> str | None:
        """Why this activation is prohibited right now, or None (CR 602.5).

        "A player can't begin to activate an ability that's prohibited from
        being activated."
        """
        if self.card.zone is not self.zone:
            return (
                f"{self.card.name}'s {self.keyword} ability functions in the "
                f"{self.zone.value}, but it is in the {self.card.zone.value} ({self.rule})"
            )
        if self.zone is Zone.BATTLEFIELD and self.card.controller not in (None, self.player):
            return f"{self.player} does not control {self.card.name}"
        if self.game is not None:
            # CR 602.5: a keyword's activated ability is an activated ability
            # like any printed one, so Clarion Conqueror stops equip and crew
            # and Pithing Needle naming a card stops its cycling in a hand
            # (CR 109.2c's "source" in any zone). None of these is a mana
            # ability (CR 605.1a).
            prohibited = self.game.activation_prohibition(self.card, is_mana=False)
            if prohibited is not None:
                return prohibited
            from .attached_restrictions import enchanted_player_activation_prohibition

            barred = enchanted_player_activation_prohibition(
                self.game, self.player, is_mana=False, is_loyalty=False
            )
            if barred is not None:
                return barred
        if (
            self.zone is Zone.BATTLEFIELD
            and self.game is not None
            and any(
                component.kind is ComponentKind.TAP and self.card in component.cards
                for component in self.cost.components
            )
            and not self.game.can_activate_tap_ability(self.card)
        ):
            # CR 602.5a / 302.6: a `{T}` in the activation cost needs the
            # permanent to have been controlled since its controller's most
            # recent turn began - the same restriction `Game.why_cannot_
            # activate` already enforces for a printed activated ability, read
            # here because a `KeywordActivation`'s own cost (outlast's own
            # "[Cost], {T}") never reaches that method at all.
            return (
                f"{self.card.name} has not been under {self.player}'s control since their "
                f"most recent turn began, so its {self.keyword} ability cannot be activated "
                "(CR 602.5a, CR 302.6)"
            )
        if self.zone is not Zone.BATTLEFIELD and self.game is not None:
            if self.zone in self.game.shared_zones:
                # CR 406 (via `Game.shared_zones`): exile is one shared pile,
                # not a per-player list the way a hand or graveyard is - the
                # `self.card.zone is self.zone` check above already proves the
                # card is physically there, so what is left to check is *whose*
                # ability this is (CR 109.4: an object with no controller is
                # activated by its owner - the same player `annotate_exile`
                # already records as a suspended card's `exile_annotation.
                # owner`).
                if self.card.owner is not None and self.card.owner != self.player:
                    return (
                        f"{self.player} does not own {self.card.name}, so cannot "
                        f"activate its ability from the {self.zone.value}"
                    )
            else:
                owner = self.game.player(self.player)
                if self.card not in owner.cards_in(self.zone):
                    return f"{self.card.name} is not in {self.player}'s {self.zone.value}"
        if (
            self.keyword.lower() == "reconfigure"
            and self.ability is not None
            and self.ability.effect == RECONFIGURE_UNATTACH_EFFECT
            and self.game is not None
            and (unattach_refusal := reconfigure_unattach_refusal(self.game, self.card))
        ):
            # CR 702.151a's unattach: "Activate only if this permanent is
            # attached to a creature" (CR 602.5b).
            return unattach_refusal
        if self.rule == "CR 702.62b" and not self.card.is_suspended:
            # Greater Gargadon's own "Activate only if this card is
            # suspended" (CR 602.5b): being in exile is necessary but not
            # sufficient - CR 702.62b's "suspended" also asks for the suspend
            # marker and at least one time counter, which `CardState.
            # is_suspended` reads directly rather than re-deriving here.
            return (
                f"{self.card.name}'s {self.keyword} ability can only be activated while "
                f"it is suspended (CR 702.62b, CR 602.5b)"
            )
        if (
            self.keyword == "Equip"
            and self.game is not None
            and equip_once_each_turn(self.card)
            and self.game.activations.get(equip_activation_key(self.card), 0) > 0
        ):
            return (
                f"{self.card.name}'s equip ability can be activated only once each turn "
                f"({self.rule}, CR 602.5b)"
            )
        if (
            self.keyword == "Crew"
            and self.game is not None
            and crew_once_each_turn(self.card)
            and self.game.activations.get(crew_activation_key(self.card), 0) > 0
        ):
            return (
                f"{self.card.name}'s crew ability can be activated only once each turn "
                f"({self.rule}, CR 602.5b)"
            )
        if (
            self.sorcery_only
            and self.game is not None
            and not self.game.can_cast_sorcery(self.player)
            and not (self.keyword == "Equip" and equip_at_instant_speed(self.game, self.player))
        ):
            # CR 307.5: "only as a sorcery" means priority, own main phase,
            # empty stack - and nothing about actually casting a sorcery.
            return (
                f"{self.card.name}'s {self.keyword} ability can only be activated as a "
                f"sorcery: {self.player}'s main phase, with the stack empty "
                f"({self.rule}, CR 307.5)"
            )
        if self.forecast and self.game is not None:
            # CR 702.57b: "A forecast ability may be activated only during
            # the upkeep step of the card's owner and only once each turn."
            # Not read off `ability.instructions` the way `sorcery_only`'s
            # printed "Activate only as a sorcery" is below - Forecast never
            # prints this restriction, it *is* the restriction, so it is
            # checked directly against the turn machine instead. By this
            # point `self.player` is already proven to own `self.card` (the
            # zone checks above), which is exactly CR 702.57b's own "the
            # card's owner".
            from .turn import Step

            turn = self.game.turn
            if (
                turn is None
                or turn.in_pregame
                or turn.step is not Step.UPKEEP
                or turn.active_player != self.player
            ):
                return (
                    f"{self.card.name}'s forecast ability may be activated only during "
                    f"{self.player}'s upkeep step (CR 702.57b)"
                )
            forecast_key = f"{self.card.id}:{self.card.zone_change_stamp}"
            if forecast_key in self.game.forecast_activations:
                return (
                    f"{self.card.name}'s forecast ability has already been activated "
                    "this turn (CR 702.57b)"
                )
        if self.game is not None:
            # CR 602.1b's activation instructions apply here exactly as they
            # do to a battlefield activation - `Game.activation_instruction_
            # refusal` is the one reader of them both go through: "Activate
            # only if <condition>" (Grim Repriser's graveyard-functioning
            # "... an opponent has been dealt noncombat damage this turn"),
            # "Activate only as a sorcery" (Expendable Lackey's), "Activate
            # only during your upkeep" (Grim Reminder's) - each once read
            # nowhere on this entry point, so allowed at any time. An
            # instruction nothing reads is refused rather than allowed
            # unchecked.
            refusal = self.game.activation_instruction_refusal(self.ability, self.card, self.player)
            if refusal is not None:
                return refusal
        return None

    def begin_paying(self) -> CostPayment:
        """CR 602.2a-b: announce the activation and open its cost."""
        if self.game is not None:
            self.game._refuse_if_over()  # CR 104.1
        refusal = self.why_not()
        if refusal is not None:
            raise ValueError(refusal)
        if self.payment is None:
            self.payment = CostPayment.for_total(
                self.cost.assign_payer(self.player), game=self.game, payer=self.player
            )
            self.payment.paying_for = "ability"
            self.payment.paying_for_keyword = None if self.generic_effect else self.keyword.lower()
        return self.payment

    def activate(self) -> AbilityOnStack:
        """Put the ability on the stack, its cost paid (CR 602.2).

        Not a mana ability, so it uses the stack and can be responded to
        (CR 605.1a is what would take it off).

        Run under `Game._id_allocator_scope` whenever there is a game to
        install it on: `_activate_impl` mints this activation's own
        `AbilityOnStack` id, and `put_triggers_on_stack` mints one more per
        trigger that has been waiting - both persisted, both minted only
        here. The api reaches this directly from `cycle_card` and
        `crew_vehicle`, so it cannot lean on an outer scope. The no-game path
        (a `KeywordActivation` built without one) has no `Game` to install an
        allocator on and needs none: nothing it does is replayed.
        """
        if self.game is None:
            return self._activate_impl()
        with self.game._id_allocator_scope():
            return self._activate_impl()

    def _activate_impl(self) -> AbilityOnStack:
        """The rest of `activate` - see its own docstring for why it is split out."""
        # Deliberately not `begin_paying`: CR 602.5 is checked once, as the
        # activation is announced. By now the cost has been paid, and cycling's
        # cost is discarding the card itself - so re-asking "is it in your
        # hand?" would refuse an activation that already happened.
        if self.payment is None or self.payment.step is not CostStep.PAID:
            raise ValueError(f"{self.card.name}'s {self.keyword} cost has not been paid")
        if self.on_stack is not None:
            raise ValueError(f"{self.card.name}'s {self.keyword} ability is already on the stack")

        self.on_stack = AbilityOnStack(
            kind=AbilityKind.ACTIVATED,
            ability=self.ability,
            source_id=self.card.id,
            source_name=self.card.name,
            controller=self.player,
            targets=list(self.targets),
            x_value=self.x_value,
            # The link back, so the effect is findable from the object on the
            # stack rather than only from here (CR 113.1c, CR 608.2) - unset
            # for `generic_effect`, so `Game._effect_of` reaches the ordinary
            # card-text resolution instead of asking this module for one.
            keyword_activation=None if self.generic_effect else self,
        )
        self.game.stack.append(self.on_stack)
        if self.keyword == "Equip":
            # "the first equip ability you activate each turn" counts this one
            # whichever cost it paid (`free_first_equip_source`).
            self.game.record_turn_fact(ACTIVATED_EQUIP_FACT, self.player)
            if equip_once_each_turn(self.card):
                key = equip_activation_key(self.card)
                self.game.activations[key] = self.game.activations.get(key, 0) + 1
        if self.keyword == "Crew" and crew_once_each_turn(self.card):
            key = crew_activation_key(self.card)
            self.game.activations[key] = self.game.activations.get(key, 0) + 1
        if self.forecast:
            # CR 702.57b's own once-each-turn restriction, checked back in
            # `why_not` against this same key - the card is still in `zone`
            # (revealing never moves it, CR 701.20b), so `zone_change_stamp`
            # is unchanged between the two calls.
            self.game.forecast_activations.add(f"{self.card.id}:{self.card.zone_change_stamp}")
        self._emit_activation_events()
        self.game.put_triggers_on_stack()  # CR 117.3c hands priority straight back
        return self.on_stack

    def _emit_activation_events(self) -> None:
        """What this activation is, as trigger events (CR 603.2).

        Every keyword activation is CR 602.2's "put it onto the stack and pay
        its costs" - never a mana ability (CR 605.1a) - so it always raises
        `ExtraTriggerEvent.ABILITY_ACTIVATED`. A cycling or typecycling one
        (CR 702.29f: "Typecycling abilities are cycling abilities") also
        raises `ExtraTriggerEvent.CYCLED`, CR 702.29c's "When you cycle this
        card": its cost discarded the card, and the discard's own event was
        already raised by the cost (CR 701.9a).
        """
        game = self.game
        on_battlefield = self.card.zone is Zone.BATTLEFIELD
        types = (
            tuple(game.characteristics_of(self.card).types)
            if on_battlefield
            else tuple(self.card.types)
        )
        game.emit(
            GameEvent(
                event=ExtraTriggerEvent.ABILITY_ACTIVATED,
                subject_id=self.card.id,
                subject_name=self.card.name,
                subject_controller=self.player,
                subject_card=self.card.card,
                subject_types=types,
                origin_zone=self.zone,
                player=self.player,
                # "Whenever you activate a ninjutsu ability" (Satoru Umezawa)
                keyword_action=self.keyword.lower(),
            )
        )
        if self.rule in (str(KeywordRule.CYCLING), str(KeywordRule.TYPECYCLING)):
            game.emit(
                GameEvent(
                    event=ExtraTriggerEvent.CYCLED,
                    subject_id=self.card.id,
                    subject_name=self.card.name,
                    subject_card=self.card.card,
                    player=self.player,
                )
            )

    def resolve(self) -> Any:
        """Resolve the ability and run the keyword's own effect (CR 608.2).

        The ability leaves the stack through `Game.resolve_top`, which is
        CR 608.2n. Whether the effect happens there or here depends on whether
        the resolver knows to ask `keyword_effect_for`: if it does, `applied` is
        already true by the time `resolve_top` returns and the fallback below
        does nothing. If it does not, the effect is applied here, which is the
        state of things today - see `docs/engine-coverage.md`.
        """
        if self.on_stack is None:
            raise ValueError(f"{self.card.name}'s {self.keyword} ability is not on the stack")
        if self.game.stack and self.game.stack[-1] is not self.on_stack:
            raise ValueError(
                f"{self.card.name}'s {self.keyword} ability is not on top of the stack"
            )
        self.game.resolve_top()  # CR 608.2n
        return self.run_effect()

    def cancel(self) -> None:
        """Rewind the cost, leaving everything where it was (CR 733.1).

        Run under `Game._id_allocator_scope` whenever there is a game to
        install it on: `CostPayment.rewind` puts back a card the cost
        sacrificed, discarded, exiled or milled, and every one of those moves
        mints a fresh `zone_change_stamp` (CR 400.7). The api reaches this on
        the rewind path the same way it reaches `Casting.cancel`, so it needs
        its own scope rather than an outer one.
        """
        if self.game is None:
            self._cancel_impl()
            return
        with self.game._id_allocator_scope():
            self._cancel_impl()

    def _cancel_impl(self) -> None:
        """The rest of `cancel` - see its own docstring for why it is split out."""
        if self.payment is not None:
            self.payment.rewind()


# --------------------------------------------------------------------------
# Cycling (CR 702.29) and typecycling (CR 702.29e)
# --------------------------------------------------------------------------

#: `Forestcycling`, `Landcycling`, `Mountaincycling`: the type is the keyword
#: with `cycling` taken off (CR 702.29e).
_TYPECYCLING = re.compile(r"^(?P<type>.+)cycling$", re.IGNORECASE)


def cycling_abilities(card: Card) -> list[KeywordAbility]:
    """Every cycling ability printed on this card, in printed order (CR 702.29).

    The umbrella names Scryfall lists beside a concrete one - `Typecycling`,
    `Landcycling` - are not printed lines, so they never appear here; only what
    the card actually says does.
    """
    return [
        ability
        for ability in keyword_abilities(card)
        if ability.canonical.lower().endswith("cycling")
        and ability.canonical.lower() not in {"typecycling", "landcycling"}
    ]


def cycling_activation(
    game: Any, card: CardState, player: str, index: int = 0
) -> KeywordActivation:
    """Build the activation for a card's cycling ability (CR 702.29a).

    "Cycling is an activated ability that functions only while the card with
    cycling is in a player's hand. 'Cycling [cost]' means "[Cost], Discard this
    card: Draw a card.""

    CR 702.29b is why the zone is checked rather than the card: "Although the
    cycling ability can be activated only if the card is in a player's hand, it
    continues to exist while the object is on the battlefield and in all other
    zones."
    """
    printed = cycling_abilities(effective_card(game, card))
    if index >= len(printed):
        raise ValueError(
            f"{card.name} has no cycling ability number {index} ({KeywordRule.CYCLING})"
        )
    ability = printed[index]

    cost = _keyword_cost(ability, player)
    if cost is None:
        raise ValueError(
            f"{card.name}'s {ability.keyword} cost {ability.cost!r} could not be read, "
            f"so it cannot be paid"
        )
    if game is not None and cycling_costs_nothing(game, player):
        # CR 118.9: "you may pay {0} rather than pay cycling costs".
        cost = TotalCost()
    # CR 702.29a: discarding the card is part of the activation cost, not the
    # effect - which is what makes a cycled card findable in the graveyard by
    # the time the draw happens.
    cost = TotalCost(
        mana=cost.mana,
        components=[
            *cost.components,
            discard_cost(card, payer=player, required=1, description="Discard this card"),
        ],
    )

    typed = _typecycling_type(ability.canonical)
    return statically_priced(
        KeywordActivation(
            card=card,
            player=player,
            keyword=ability.canonical,
            rule=str(KeywordRule.TYPECYCLING if typed else KeywordRule.CYCLING),
            zone=Zone.HAND,
            cost=cost,
            ability=_synthetic_ability(
                ability,
                cost_text=f"{ability.cost or ''}, Discard this card".strip(", "),
                effect=(
                    "Search your library for "
                    f"{with_indefinite_article(f'{typed} card')}, reveal it, "
                    f"and put it into your hand. "
                    f"Then shuffle."
                    if typed
                    else "Draw a card."
                ),
            ),
            game=game,
        )
    )


def _typecycling_type(canonical: str) -> str | None:
    """The type a typecycling ability searches for, or None for plain cycling."""
    match = _TYPECYCLING.match(canonical)
    if match is None:
        return None
    named = match.group("type")
    return None if not named else named.capitalize()


def _synthetic_ability(keyword: KeywordAbility, cost_text: str, effect: str) -> ActivatedAbility:
    """The activated ability a keyword is shorthand for (CR 702.1, CR 602.1).

    Built from the rule's own expansion rather than parsed off the card,
    because the card does not print it - `Cycling {U}` is one line and the
    ability it means is another.
    """
    return ActivatedAbility(
        raw=keyword.raw,
        text=f"{cost_text}: {effect}",
        reminder=keyword.reminder,
        face=keyword.face,
        cost=cost_text,
        costs=[Cost(kind=CostKind.OTHER, text=cost_text)],
        effect=effect,
    )


def _cycling_effect(activation: KeywordActivation) -> list[CardState]:
    """Cycling's effect: draw a card, or search for one (CR 702.29a, 702.29e)."""
    typed = _typecycling_type(activation.keyword)
    game = activation.game
    with game._id_allocator_scope():  # noqa: SLF001
        if typed is None:
            return game.draw_cards(activation.player, 1, cycled=activation.card)
        # CR 702.29e: "Search your library for a [type] card, reveal it, and put
        # it into your hand. Then shuffle your library."
        return _search_reveal_to_hand_and_shuffle(
            activation, lambda state: _matches_type(state, typed)
        )


def _search_reveal_to_hand_and_shuffle(
    activation: KeywordActivation, matches: Callable[[CardState], bool]
) -> list[CardState]:
    """Typecycling's and transmute's shared resolution, in the order both
    printed expansions state it (CR 702.29e, CR 702.53a).

    The search is `Game.search_library`'s single CHOOSE_CARDS question over
    every matching card (CR 701.23a), asked inexact because both name a stated
    quality - a type, or a mana value - which CR 701.23b says the player "isn't
    required to find". The found card is revealed while still in the library
    (CR 701.20a-b), put into the hand, and only then is the library shuffled
    (CR 701.24a) - `Game.search_and_put`, the funnel every printed
    search-reveal-put goes through.
    """
    game = activation.game
    return game.search_and_put(
        game.player(activation.player),
        matches,
        destination=Zone.HAND,
        reveal=True,
        source=activation.card.name,
        source_id=source_id_of(activation.card),
    )


def _matches_type(state: CardState, named: str) -> bool:
    """Whether a card is of the type a typecycling ability names (CR 702.29e).

    "This type is usually a subtype (as in "mountaincycling") but can be any
    card type, subtype, supertype, or combination thereof (as in "basic
    landcycling")." So every word named has to be one of the card's own
    supertypes (CR 205.4a), card types (CR 205.2a) or subtypes (CR 205.3) -
    "basic land" is a basic *and* a land, never a land with a basic land type.
    """
    words = named.lower().split()
    if not words:
        return False
    own = {
        *(supertype.value for supertype in state.supertypes),
        *(card_type.value for card_type in state.types),
        *(subtype.lower() for subtype in state.subtypes),
    }
    return all(word in own for word in words)


def cycle(
    game: Any,
    card: CardState,
    player: str,
    payment_hook: Callable[[CostPayment], None] | None = None,
    index: int = 0,
) -> Any:
    """Activate and resolve a cycling ability, when nobody responds.

    `payment_hook` is handed the open `CostPayment` so a caller can tap for the
    mana the cost needs; a cost that needs no mana needs no hook.

    The long way round - `cycling_activation`, `begin_paying`, `activate`,
    `resolve` - is the one to reach for when the scenario is about the window in
    between, because a cycling ability uses the stack and can be responded to.
    """
    activation = cycling_activation(game, card, player, index)
    payment = activation.begin_paying()
    if payment_hook is not None:
        payment_hook(payment)
    payment.pay()
    activation.activate()
    return activation.resolve()


# --------------------------------------------------------------------------
# Unearth (CR 702.84)
# --------------------------------------------------------------------------


def unearth_abilities(card: Card) -> list[KeywordAbility]:
    """Every unearth ability printed on this card, in printed order (CR 702.84)."""
    return [
        ability for ability in keyword_abilities(card) if ability.canonical.lower() == "unearth"
    ]


def unearth_abilities_of(game: Any, card: CardState) -> list[KeywordAbility]:
    """The unearth abilities `card` has right now: printed, plus any a static
    grants (Mishra, Tamer of Mak Fawa), and none while a static strips graveyard
    cards of their abilities (Yixlid Jailer) - except a grant stamped after
    that static (CR 613.7a), which survives it."""
    from .graveyard_statics import graveyard_abilities_lost_by, unearth_grants_surviving_removal
    from .zone_grants import effective_card

    if card.zone is Zone.GRAVEYARD and graveyard_abilities_lost_by(game) is not None:
        return unearth_grants_surviving_removal(game, card)
    return unearth_abilities(effective_card(game, card))


def unearth_activation(
    game: Any, card: CardState, player: str, index: int = 0
) -> KeywordActivation:
    """Build the activation for a card's unearth ability (CR 702.84a).

    "Unearth is an activated ability that functions while the card with
    unearth is in a graveyard. 'Unearth [cost]' means '[Cost]: Return this
    card from your graveyard to the battlefield. It gains haste. Exile it at
    the beginning of the next end step. If it would leave the battlefield,
    exile it instead of putting it anywhere else. Activate only as a
    sorcery.'"

    The same `cycling_activation`/`_synthetic_ability` shape as cycling
    (CR 702.29a) - the card prints only "Unearth [cost]", never the sentence
    it expands to, so the ability run on the stack is built from the rule's
    own wording rather than parsed off the printing.

    The delayed "exile it at the beginning of the next end step" half is
    `_unearth_effect`'s business, not this builder's: CR 602.2's activation
    only puts the ability on the stack and takes its cost, and the delayed
    trigger is created when the ability *resolves* (CR 603.7a), which for
    every other delayed-creating ability in this engine happens inside the
    effect, not the activation (`_parse_delayed_reanimate_haste_exile_
    clauses`, `machines/casting.exile_warped`).
    """
    printed = unearth_abilities_of(game, card)
    if index >= len(printed):
        from .graveyard_statics import graveyard_abilities_lost_by

        jailer = graveyard_abilities_lost_by(game) if card.zone is Zone.GRAVEYARD else None
        if jailer is not None and not printed:
            raise ValueError(
                f"{card.name} has no unearth ability: {jailer} makes cards in graveyards "
                f"lose all abilities ({KeywordRule.UNEARTH})"
            )
        raise ValueError(
            f"{card.name} has no unearth ability number {index} ({KeywordRule.UNEARTH})"
        )
    ability = printed[index]

    cost = _keyword_cost(ability, player)
    if cost is None:
        raise ValueError(
            f"{card.name}'s {ability.keyword} cost {ability.cost!r} could not be read, "
            f"so it cannot be paid"
        )
    return statically_priced(
        KeywordActivation(
            card=card,
            player=player,
            keyword=ability.canonical,
            rule=str(KeywordRule.UNEARTH),
            zone=Zone.GRAVEYARD,
            cost=cost,
            sorcery_only=True,
            ability=_synthetic_ability(
                ability,
                cost_text=ability.cost or "",
                effect=(
                    "Return this card from your graveyard to the battlefield. It gains haste. "
                    "Exile it at the beginning of the next end step."
                ),
            ),
            game=game,
        )
    )


def _unearth_effect(activation: KeywordActivation) -> CardState | None:
    """CR 702.84a's effect: return the card, grant it haste, and create the
    delayed trigger that exiles it again.

    `game.put_onto_battlefield` is the same primitive `machines/effects.
    _parse_delayed_reanimate_haste_exile_clauses` already uses for Postmortem
    Lunge and Goryo's Vengeance's own "return ... It gains haste. Exile it at
    the beginning of the next end step." shape - unearth is that same
    template, expanded from a keyword instead of read off a printed
    sentence, so it is built the identical way: haste through a
    `only_this_incarnation`-scoped `ContinuousEffect` (CR 611.2a's default
    duration, since nothing states one), and the delayed exile through
    `anaphoric_delayed_trigger`/`Game.create_delayed_trigger` (CR 603.7a).

    The last sentence, "If it would leave the battlefield, exile it instead
    of putting it anywhere else", is `replacement.exile_instead_of_leaving`'s
    stored replacement bound to this one object (CR 614.1a).
    """
    from .replacement import exile_instead_of_leaving  # replacement imports this module's siblings

    game = activation.game
    card = activation.card
    if game is None or card.zone is not Zone.GRAVEYARD:
        return None
    with game._id_allocator_scope():  # noqa: SLF001
        entered = game.put_onto_battlefield(card, activation.player, tapped=False)
        if entered.zone is not Zone.BATTLEFIELD:
            return entered  # CR 614.6: a replacement sent it elsewhere.
        store = game.continuous_effects
        timestamp = store.tick()
        store.add(
            ContinuousEffect(
                description=f"{entered.name}: unearth grants haste (CR 702.84a)",
                layer=Layer.ABILITY,
                timestamp=timestamp,
                selector=only_this_incarnation(entered, entered.zone_change_stamp),
                modification=grant_ability("Haste"),
            )
        )
        # CR 702.84a's last replacement sentence: bound to this object only.
        exile_instead_of_leaving(
            game,
            entered,
            controller=activation.player,
            source_id=entered.id,
            source_name=entered.name,
        )
        trigger = anaphoric_delayed_trigger(
            "Exile it at the beginning of the next end step.",
            subject=entered,
            controller=activation.player,
            source_id=entered.id,
            source_name=entered.name,
            game=game,
        )
        if trigger is not None:
            game.create_delayed_trigger(trigger)
        return entered


# --------------------------------------------------------------------------
# Craft (CR 702.167)
# --------------------------------------------------------------------------


def craft_abilities(card: Card) -> list[KeywordAbility]:
    """Every craft ability printed on this card, in printed order (CR 702.167)."""
    return [ability for ability in keyword_abilities(card) if ability.canonical.lower() == "craft"]


#: "Craft with [materials] [cost]" as `KeywordAbility.parameter` carries it:
#: "with artifact {2}{W}", "with two creatures {5}{B}", "with one or more {5}".
_CRAFT_PARAMETER = re.compile(r"^with (?P<materials>.+?) (?P<cost>(?:\{[^}]+\})+)$", re.IGNORECASE)
#: "one or more [quality]": at least one (CR 702.167a's "one or more other
#: permanents you control and/or cards from your graveyard").
_CRAFT_AT_LEAST_ONE = re.compile(r"^one or more(?: (?P<rest>.+))?$", re.IGNORECASE)


class CraftMaterials(NamedTuple):
    """What a craft ability exiles besides itself (CR 702.167a)."""

    count: int
    at_least: bool
    """"one or more": `count` or more, not exactly `count`."""
    quality: str | None
    """The noun phrase each material must fit (CR 702.167b), None for any
    permanent or card at all."""
    printed: str
    """The materials as printed ("two creatures"), for a refusal's reason."""


def craft_materials(ability: KeywordAbility) -> tuple[CraftMaterials, str] | None:
    """The materials and the mana cost of a "Craft with [materials] [cost]"
    line, or None when either is not read."""
    match = _CRAFT_PARAMETER.fullmatch((ability.parameter or "").strip())
    if match is None:
        return None
    materials = match.group("materials").strip()
    count, at_least, quality = 1, False, materials
    at_least_one = _CRAFT_AT_LEAST_ONE.fullmatch(materials)
    if at_least_one is not None:
        at_least, quality = True, at_least_one.group("rest")
    else:
        first, _, rest = materials.partition(" ")
        counted = parse_count(first) if rest else None
        if counted is not None:
            count, quality = counted, rest
    return (
        CraftMaterials(count=count, at_least=at_least, quality=quality, printed=materials),
        match.group("cost"),
    )


def _craft_material_refusal(
    game: Any,
    crafter: CardState,
    player: str,
    materials: Sequence[CardState],
    wanted: CraftMaterials,
) -> str | None:
    """Why `materials` cannot pay this craft's "Exile [materials]", or None
    (CR 702.167a/b). Checked as the activation is announced (CR 602.2b), so a
    wrong choice is refused with its own reason rather than at payment."""
    from ..models.game import _permanent_quality

    described = wanted.printed
    if len(materials) != len({id(material) for material in materials}):
        return f"a material was chosen twice for {crafter.name}'s craft ({KeywordRule.CRAFT})"
    if len(materials) < wanted.count or (not wanted.at_least and len(materials) != wanted.count):
        return (
            f"{crafter.name}'s craft exiles {described} as materials, not {len(materials)} "
            f"({KeywordRule.CRAFT})"
        )
    fits = _permanent_quality(wanted.quality) if wanted.quality else (lambda _chars: True)
    if fits is None:
        return (
            f"{crafter.name}'s craft materials ({wanted.quality}) cannot be read, so it is not "
            f"activated unchecked ({KeywordRule.CRAFT})"
        )
    for material in materials:
        if material is crafter:
            return (
                f"{crafter.name} is exiled by its own craft cost, not as one of its materials "
                f"({KeywordRule.CRAFT})"
            )
        if material.zone is Zone.BATTLEFIELD:
            if game.controller_of(material).username != player:
                return (
                    f"{player} does not control {material.name}, so it is not a craft material "
                    f"({KeywordRule.CRAFT}: permanents you control)"
                )
            characteristics: Any = game.characteristics_of(material)
        elif material.zone is Zone.GRAVEYARD:
            if material not in game.player(player).graveyard:
                return (
                    f"{material.name} is not in {player}'s graveyard, so it is not a craft "
                    f"material ({KeywordRule.CRAFT})"
                )
            characteristics = material
        else:
            return (
                f"{material.name} is in the {material.zone.value}: craft materials are "
                f"permanents you control and cards in your graveyard ({KeywordRule.CRAFT})"
            )
        if not fits(characteristics):
            return (
                f"{material.name} is not {wanted.quality}, so it is not a material for "
                f"{crafter.name}'s craft ({KeywordRule.CRAFT}, CR 702.167b)"
            )
    return None


def craft_activation(
    game: Any,
    card: CardState,
    player: str,
    materials: Sequence[CardState],
    index: int = 0,
) -> KeywordActivation:
    """Build the activation for a permanent's craft ability (CR 702.167a).

    "'Craft with [materials] [cost]' means '[Cost], Exile this permanent,
    Exile [materials] from among permanents you control and/or cards in your
    graveyard: Return this card to the battlefield transformed under its
    owner's control. Activate only as a sorcery.'" The same synthetic
    `KeywordActivation` shape as outlast: the cost is the printed mana plus
    two exile components - the permanent itself, and `materials`, one
    component per zone they come from (CR 406.2). The materials are checked
    now (CR 702.167b's type-or-card reading, `_craft_material_refusal`).
    """
    printed = craft_abilities(card.card)
    if index >= len(printed):
        raise ValueError(f"{card.name} has no craft ability number {index} ({KeywordRule.CRAFT})")
    ability = printed[index]
    read = craft_materials(ability)
    if read is None:
        raise ValueError(
            f"{card.name}'s {ability.text!r} could not be read, so it cannot be activated "
            f"({KeywordRule.CRAFT})"
        )
    wanted, mana = read
    refusal = _craft_material_refusal(game, card, player, list(materials), wanted)
    if refusal is not None:
        raise ValueError(refusal)
    on_battlefield = [m for m in materials if m.zone is Zone.BATTLEFIELD]
    in_graveyard = [m for m in materials if m.zone is Zone.GRAVEYARD]
    components = [exile_cost(card, payer=player, zone=Zone.BATTLEFIELD)]
    if on_battlefield:
        components.append(exile_cost(*on_battlefield, payer=player, zone=Zone.BATTLEFIELD))
    if in_graveyard:
        components.append(exile_cost(*in_graveyard, payer=player, zone=Zone.GRAVEYARD))
    cost = TotalCost(mana=ManaCost.parse(mana), components=components)
    return statically_priced(
        KeywordActivation(
            card=card,
            player=player,
            keyword=ability.canonical,
            rule=str(KeywordRule.CRAFT),
            zone=Zone.BATTLEFIELD,
            cost=cost,
            sorcery_only=True,
            ability=_synthetic_ability(
                ability,
                cost_text=f"{mana}, Exile this permanent, Exile the materials",
                effect="Return this card to the battlefield transformed under its owner's control.",
            ),
            craft_materials=tuple(material.id for material in materials),
            game=game,
        )
    )


def _craft_effect(activation: KeywordActivation) -> CardState | None:
    """CR 702.167a's effect: "Return this card to the battlefield transformed
    under its owner's control" - the card the cost exiled, from exile.
    CR 712.14a: a card that is not double-faced stays in exile."""
    game = activation.game
    card = activation.card
    if game is None or card.zone is not Zone.EXILE or card.card.back_face is None:
        return None
    with game._id_allocator_scope():  # noqa: SLF001
        returned = game.put_onto_battlefield(
            card, card.owner or activation.player, transformed=True
        )
    # CR 702.167c: the returned card remembers what was exiled to craft it.
    returned.crafted_with = activation.craft_materials
    return returned


# --------------------------------------------------------------------------
# Transmute (CR 702.53)
# --------------------------------------------------------------------------


def transmute_abilities(card: Card) -> list[KeywordAbility]:
    """Every transmute ability printed on this card, in printed order (CR 702.53)."""
    return [
        ability for ability in keyword_abilities(card) if ability.canonical.lower() == "transmute"
    ]


def transmute_activation(
    game: Any, card: CardState, player: str, index: int = 0
) -> KeywordActivation:
    """Build the activation for a card's transmute ability (CR 702.53a).

    "Transmute is an activated ability that functions only while the card
    with transmute is in a player's hand. 'Transmute [cost]' means '[Cost],
    Discard this card: Search your library for a card with the same mana
    value as the discarded card, reveal that card, and put it into your
    hand. Then shuffle your library. Activate only as a sorcery.'"

    Structurally cycling's own typecycling variant (CR 702.29e) with a
    different search predicate - "the same mana value as the **discarded**
    card" rather than a named type - so the discard is folded into the cost
    exactly the way `cycling_activation` folds discarding the cycled card
    into *its* cost, and `_transmute_effect` reads the mana value off the
    just-discarded `CardState` rather than off `card` (CR 707.3: a discarded
    card is a new object once it changes zones, but its own mana value is a
    copiable characteristic that never depended on being in hand).
    """
    printed = transmute_abilities(card.card)
    if index >= len(printed):
        raise ValueError(
            f"{card.name} has no transmute ability number {index} ({KeywordRule.TRANSMUTE})"
        )
    ability = printed[index]

    cost = _keyword_cost(ability, player)
    if cost is None:
        raise ValueError(
            f"{card.name}'s {ability.keyword} cost {ability.cost!r} could not be read, "
            f"so it cannot be paid"
        )
    cost = TotalCost(
        mana=cost.mana,
        components=[
            *cost.components,
            discard_cost(card, payer=player, required=1, description="Discard this card"),
        ],
    )
    return statically_priced(
        KeywordActivation(
            card=card,
            player=player,
            keyword=ability.canonical,
            rule=str(KeywordRule.TRANSMUTE),
            zone=Zone.HAND,
            cost=cost,
            sorcery_only=True,
            ability=_synthetic_ability(
                ability,
                cost_text=f"{ability.cost or ''}, Discard this card".strip(", "),
                effect=(
                    "Search your library for a card with the same mana value as the discarded "
                    "card, reveal that card, and put it into your hand. Then shuffle your library."
                ),
            ),
            game=game,
        )
    )


def _transmute_effect(activation: KeywordActivation) -> CardState | None:
    """CR 702.53a's search: a library card whose mana value equals the
    mana value of the card transmute just discarded.

    The discarded card is `activation.card` - `_activate_impl` already
    charged the discard as part of paying the cost before this ever runs
    (CR 602.2b/CR 118.8a), so by the time the effect resolves `activation.
    card.zone` is the graveyard, exactly what CR 702.53a's own "the
    discarded card" refers to. The search, reveal and shuffle are the ones
    typecycling uses (`_search_reveal_to_hand_and_shuffle`): the player
    chooses among every card of that mana value, or finds nothing.
    """
    game = activation.game
    target_value = activation.card.mana_value
    with game._id_allocator_scope():  # noqa: SLF001
        found = _search_reveal_to_hand_and_shuffle(
            activation, lambda state: state.mana_value == target_value
        )
    return found[0] if found else None


# --------------------------------------------------------------------------
# Equip (CR 702.6)
# --------------------------------------------------------------------------


#: CR 702.6a's expansion of "Equip [cost]", after the colon. CR 115.1e: the
#: target lives in the keyword's rule, not in printed text, so this is the
#: text every equip target is announced and checked against.
EQUIP_EFFECT = "Attach this permanent to target creature you control."


def has_equip(card: Card) -> bool:
    """Whether this card prints an equip ability (CR 702.6a)."""
    return _keyword(card, "equip") is not None


def equip_quality_refusal(game: Any, quality: str | None, target: Any) -> str | None:
    """Why `target` lacks an "Equip [quality]" ability's quality, or None
    (CR 702.6c).

    Read on the computed board (CR 613.5) while the creature is on the
    battlefield. "worthy" is CR 700.16's "legendary, isn't a Villain, and is
    red and/or white"; otherwise each word is a supertype ("legendary"), a
    card type ("planeswalker"), "token", or a subtype ("Knight"), with an
    optional trailing "creature". A word this does not read refuses, so an
    unread restriction never widens what the ability may target."""
    if quality is None:
        return None
    if not isinstance(target, CardState):
        return f"Equip {quality} can only target a creature (CR 702.6c)"
    chars = game.characteristics_of(target) if target.zone is Zone.BATTLEFIELD else target
    subtypes = {subtype.lower() for subtype in chars.subtypes}
    words = quality.strip().lower().split()
    if words and words[-1] == "creature":
        words = words[:-1]
    if words == ["worthy"]:
        worthy = (
            Supertype.LEGENDARY in chars.supertypes
            and "villain" not in subtypes
            and bool({Color.RED, Color.WHITE} & set(chars.colors))
        )
        if worthy:
            return None
        return (
            f"{target.name} is not worthy - it must be legendary, not a Villain, and red "
            f"and/or white (CR 700.16, CR 702.6c)"
        )
    if not words:
        return None
    for word in words:
        if word == "legendary":
            holds = Supertype.LEGENDARY in chars.supertypes
        elif word == "token":
            holds = bool(getattr(target, "is_token", False))
        elif word == "planeswalker":
            holds = Type.PLANESWALKER in chars.types
        else:
            subtype = canonical_subtype(word)
            if subtype is None:
                return f"Equip {quality}: the quality {word!r} is not read (CR 702.6c)"
            holds = subtype.lower() in subtypes
        if not holds:
            return f"Equip {quality} cannot target {target.name}, which is not {word} (CR 702.6c)"
    return None


def _equip_quality_of(raw: str) -> str | None:
    """The "[quality]" of a printed "Equip [quality] [cost]" line, or None."""
    match = re.match(r"^Equip (?P<quality>[^{}.:(]+?) (?:\{[^}]+\})+", raw.strip())
    return match.group("quality").strip() if match else None


#: "You may pay {0} rather than pay the equip cost of the first equip ability
#: you activate each turn." (Bruenor Battlehammer; Kili the Resourceful behind
#: its enduring-story gate) and "... during each of your turns." (Forge
#: Anew) - an alternative cost for an activated ability (CR 118.9's "You may
#: [action] rather than pay ...", here the equip ability's CR 702.6a
#: "[Cost]"), once per turn.
_FREE_FIRST_EQUIP_RE = re.compile(
    r"^you may pay \{0\} rather than pay the equip cost of the first equip ability you "
    r"activate (?P<when>each turn|during each of your turns)\.?$",
    re.IGNORECASE,
)

#: `Game.turn_facts`' key for "has activated an equip ability this turn" -
#: what "the first equip ability you activate each turn" counts, whichever
#: cost that activation paid.
ACTIVATED_EQUIP_FACT = "activated_equip"


def _free_first_equip_match(line: str) -> "tuple[re.Match[str], str | None] | None":
    text = line.strip()
    condition: str | None = None
    gated = split_as_long_as(text)
    if gated is not None:
        condition, text = gated
    match = _FREE_FIRST_EQUIP_RE.fullmatch(text)
    return None if match is None else (match, condition)


def is_free_first_equip_line(line: str) -> bool:
    """Whether a static line is `_FREE_FIRST_EQUIP_RE`'s permission, gated or
    not - what `support.py` counts handled."""
    return _free_first_equip_match(line) is not None


#: "During your turn, you may activate equip abilities any time you could cast
#: an instant." (Forge Anew): CR 702.6a's "Activate only as a sorcery" lifted by
#: a static ability (CR 604.2), the permission itself gated on whose turn it is.
_INSTANT_SPEED_EQUIP_RE = re.compile(
    r"^(?P<your_turn>during your turn, )?you may activate equip abilities any time you could "
    r"cast an instant\.?$",
    re.IGNORECASE,
)


#: "During your turn, as long as you haven't activated an exhaust ability this
#: turn, you may activate exhaust abilities as though they haven't been
#: activated." (Elvish Refueler): CR 702.177a's "activate only once", lifted once
#: a turn by a static ability (CR 604.2).
_EXHAUST_REACTIVATION_RE = re.compile(
    r"^during your turn, as long as you haven'?t activated an exhaust ability this turn, "
    r"you may activate exhaust abilities as though they haven'?t been activated\.?$",
    re.IGNORECASE,
)

#: `Game.turn_facts`' key for "has activated an exhaust ability this turn".
ACTIVATED_EXHAUST_FACT = "activated_exhaust"


def is_exhaust_reactivation_line(line: str) -> bool:
    """Whether a static line is `_EXHAUST_REACTIVATION_RE`'s permission."""
    return _EXHAUST_REACTIVATION_RE.fullmatch(line.strip()) is not None


def exhaust_reactivation_allowed(game: Any, player: str) -> bool:
    """Whether `player` may activate an exhaust ability that was already
    activated right now: a permanent they control has the permission on the
    computed board (CR 613.5), it is their turn, and they have activated no
    exhaust ability yet this turn (`ACTIVATED_EXHAUST_FACT`). Re-read at every
    question (CR 611.3a)."""
    if game.turn is None or game.turn.active_player != player:
        return False
    if game.turn_fact_holds(ACTIVATED_EXHAUST_FACT, player):
        return False
    board = game.computed_board()
    return any(
        is_exhaust_reactivation_line(line)
        for permanent in game.permanents_controlled_by(player)
        for line in board.of(permanent).abilities
    )


def is_instant_speed_equip_line(line: str) -> bool:
    """Whether a static line is `_INSTANT_SPEED_EQUIP_RE`'s permission - what the
    static audit counts handled."""
    return _INSTANT_SPEED_EQUIP_RE.fullmatch(line.strip()) is not None


def equip_at_instant_speed(game: Any, player: str) -> bool:
    """Whether a static ability `player` controls lets them activate equip
    abilities whenever they could cast an instant right now. Read off the
    computed board (CR 613.5), so a permanent that lost the ability grants
    nothing, and re-read at every question (CR 611.3a)."""
    board = game.computed_board()
    for permanent in game.permanents_controlled_by(player):
        for line in board.of(permanent).abilities:
            match = _INSTANT_SPEED_EQUIP_RE.fullmatch(line.strip())
            if match is None:
                continue
            if match["your_turn"] and (game.turn is None or game.turn.active_player != player):
                continue
            return True
    return False


def free_first_equip_source(game: Any, player: str) -> CardState | None:
    """The permanent whose "you may pay {0} rather than pay the equip cost of
    the first equip ability you activate ..." applies to `player`'s next
    equip activation right now, or None.

    None once `player` has activated any equip ability this turn
    (`ACTIVATED_EQUIP_FACT`); a "during each of your turns" permission only
    on `player`'s own turn; a designation gate (`machines/designations.py`)
    only while `player` holds it. Read off the computed board (CR 613.5), so
    a permanent that lost the ability grants nothing.
    """
    if game.turn_fact_holds(ACTIVATED_EQUIP_FACT, player):
        return None
    board = game.computed_board()
    for permanent in game.permanents_controlled_by(player):
        for line in board.of(permanent).abilities:
            found = _free_first_equip_match(line)
            if found is None:
                continue
            match, condition = found
            if condition is not None and not designation_holds(condition, game.player(player)):
                continue
            if match["when"].lower() == "during each of your turns" and (
                game.turn is None or game.turn.active_player != player
            ):
                continue
            return permanent
    return None


#: "Equip abilities you activate that target this creature cost `{N}` less
#: to activate." - Dwarven Mauler's own static, a discount granted by a
#: *different* permanent than the Equipment whose equip ability it reduces
#: (CR 601.2f via CR 602.2b), the templated sibling of `Fervent Champion`'s
#: identically-worded off-set printing (`{3}` in place of `{2}`).
_EQUIP_ABILITIES_TARGETING_THIS_COST_LESS_RE = re.compile(
    r"^equip abilities you activate that target this creature cost "
    r"\{(?P<amount>\d+)\} less to activate\.?$",
    re.IGNORECASE,
)


def is_equip_discount_for_this_line(line: str) -> bool:
    """Whether one printed static line is `_EQUIP_ABILITIES_TARGETING_THIS_
    COST_LESS_RE`'s discount, which `machines/cost/abilities.py`
    applies to every equip activation aimed at this creature - `support.py`'s
    credit for it."""
    return _EQUIP_ABILITIES_TARGETING_THIS_COST_LESS_RE.fullmatch(line.strip()) is not None


_ATTACHED_ONLY_TO_RE = re.compile(
    r"can be attached only to (?:an? )?(?P<quality>[a-z ]+?)(?:\.|$)", re.IGNORECASE | re.MULTILINE
)


def attach_only_quality(card: Card) -> str | None:
    """The quality in a "`<name>` can be attached only to a <quality>." line
    (Konda's Banner: "legendary creature", CR 702.6c), or None."""
    match = _ATTACHED_ONLY_TO_RE.search(card.oracle_text or "")
    return None if match is None else match["quality"].lower()


def attach_restriction_refusal(game: Any, equipment: CardState, target: CardState) -> str | None:
    """Why `target` is not a thing `equipment` can be attached to, or None."""
    from .layers.group_grants import group_selector, parse_group

    quality = attach_only_quality(equipment.card)
    if quality is None:
        return None
    spec = parse_group(quality)
    if spec is None:
        return f"{equipment.name} can be attached only to a {quality}, which cannot be read"
    board = game.computed_board()
    if group_selector({**spec, "scope": "any"}, equipment)(board.of(target), board.characteristics):
        return None
    return (
        f"{equipment.name} can be attached only to a {quality}; "
        f"{target.name} is not one (CR 702.6c)"
    )


def _equip_ability_price(ability: KeywordAbility) -> float:
    """The mana value of an equip ability's cost, for CR 702.6c's choice."""
    try:
        return float(ManaCost.parse(ability.cost or "").converted)
    except Exception:  # an unreadable cost sorts last, as before
        return float("inf")


def equip_activation(
    game: Any,
    equipment: CardState,
    target: CardState,
    player: str,
    *,
    pay_zero: bool = True,
) -> KeywordActivation:
    """Build the activation for an Equipment's equip ability (CR 702.6a).

    "Equip is an activated ability of Equipment cards. 'Equip [cost]' means
    "[Cost]: Attach this permanent to target creature you control. Activate
    only as a sorcery.""

    CR 301.5b is why this is needed at all: "Equipment enter the battlefield
    like other artifacts. They don't enter the battlefield attached to a
    creature. The equip keyword ability attaches" it.

    The target is announced and checked here (CR 601.2c, via CR 602.2b), the
    way `off_battlefield_activation` checks its own: an opponent's creature or
    a noncreature is refused before anything is paid. `_equip_effect` still
    rechecks on resolution (CR 608.2b) for a target that became illegal since.

    **CR 602.2b's own order is targets (CR 601.2c) before cost (CR 601.2f)**,
    which is why the target is announced and checked *before* the reduction
    below is computed: Warrior's Blades' and Dragonfire Blade's own "This
    ability costs [N] less to activate for each [quality] ... it targets"
    (`ActivationCostReduction.target_quality`) needs to know the target to
    price the activation at all, and could not be read correctly if this
    method priced the cost first the way `unannounced_equip_activation`
    (asked with no target yet, for `legal_actions`) necessarily still does.
    """
    from .targeting import profile_for_text

    # CR 702.6c: a card may print more than one equip ability ("Equip Knight
    # {1}" and "Equip {3}"); the first, in printed order, whose quality the
    # target has is the one activated.
    candidates = [
        ability
        for ability in keyword_abilities(effective_card(game, equipment))
        if ability.canonical.lower() == "equip"
    ]
    refusals = [equip_quality_refusal(game, ability.parameter, target) for ability in candidates]
    # CR 702.6c: the player picks which equip ability to activate, so of the
    # abilities whose quality the target has, the cheapest (printed order
    # breaking ties) is the one a granted "equip {1}" is for.
    usable = [
        ability for ability, refusal in zip(candidates, refusals, strict=True) if refusal is None
    ]
    chosen = min(usable, key=_equip_ability_price, default=None)
    if candidates and chosen is None:
        raise ValueError(next(refusal for refusal in refusals if refusal is not None))
    if (why := attach_refusal(game, equipment, target)) is not None:
        raise ValueError(why)
    activation = unannounced_equip_activation(
        game, equipment, player, ability=chosen, pay_zero=pay_zero, target=target
    )
    profile_for_text(EQUIP_EFFECT).check([target], player, game, source_id=equipment.id)
    refusal = attach_restriction_refusal(game, equipment, target)
    if refusal is not None:
        raise ValueError(refusal)
    # CR 702.16b: the equip ability is "from a source with the stated quality"
    # whenever the Equipment has it, and a bare-text profile carries no source
    # card to ask - so the protection half of the target check is made here.
    refusal = _protection_refusal_for_attachment(game, equipment, target)
    if refusal is not None:
        raise ValueError(refusal)
    activation.targets = [TargetRef.to_card(target)]
    ability = chosen or _keyword(equipment.card, "equip")
    reduction = ability.cost_reduction if ability is not None else None
    if activation.free_equip_from is not None:
        # CR 118.9: the alternative cost replaces the printed cost whole, so
        # there is nothing left for a "costs [N] less" to reduce.
        reduction = None
    if reduction is not None and reduction.target_quality is not None:
        amount = target_cost_reduction_amount(reduction, target, game)
        if amount is None:
            already_noticed = any(
                notice.source_id == equipment.id for notice in game.cost_modifier_notices
            )
            if not already_noticed:
                game.cost_modifier_notices.append(
                    CostModifierNotice(
                        source_id=equipment.id, source_name=equipment.name, text=ability.raw
                    )
                )
        else:
            reduced_by = reduction.amount * amount
            if reduced_by:
                activation.cost = TotalCost(
                    mana=activation.cost.mana.minus(ManaCost.parse(f"{{{reduced_by}}}")),
                    components=activation.cost.components,
                )
    return activation


_GRANTED_EQUIP_RE = re.compile(r"^equip (?P<cost>(?:\{[^}]+\})+)$", re.IGNORECASE)


def _cheaper_granted_equip_cost(game: Any, equipment: CardState, printed: TotalCost) -> TotalCost:
    """An Equipment with several equip abilities is equipped through whichever
    the player picks (CR 702.6c, CR 113.2c), so a mana-only "Equip {N}" granted
    to it in layer 6 (CR 613.1f; Puresteel Paladin's metalcraft "Equipment you
    control have equip {0}") competes with the printed one on cost. Read off
    the computed board, so it exists only while the grant does (CR 611.3a)."""
    best = printed
    for line in game.computed_board().of(equipment).abilities:
        match = _GRANTED_EQUIP_RE.fullmatch(line.strip())
        if match is None:
            continue
        granted = TotalCost(mana=ManaCost.parse(match.group("cost")))
        if granted.mana.converted < best.mana.converted:
            best = granted
    return best


def unannounced_equip_activation(
    game: Any,
    equipment: CardState,
    player: str,
    *,
    ability: KeywordAbility | None = None,
    pay_zero: bool = True,
    target: CardState | None = None,
) -> KeywordActivation:
    """An equip activation with no target announced yet: its cost, timing and
    rule, for a caller that asks about the activation before choosing
    (`legal_actions`). Never put this on the stack; `equip_activation` is the
    one that announces a target. `ability` picks one of several printed equip
    abilities (CR 702.6c); the first printed one otherwise.

    `pay_zero` is the player's "you may" on a `free_first_equip_source`
    permission (CR 118.9's alternative cost): taken by default whenever one
    applies, `False` to pay the printed cost instead."""
    ability = ability or _keyword(effective_card(game, equipment), "equip")
    if ability is None:
        raise ValueError(f"{equipment.name} has no equip ability ({KeywordRule.EQUIP})")
    cost = _keyword_cost(ability, player)
    if cost is None:
        raise ValueError(
            f"{equipment.name}'s equip cost {ability.cost!r} could not be read, "
            f"so it cannot be paid"
        )
    if game is not None:
        cost = _cheaper_granted_equip_cost(game, equipment, cost)
    free_from = free_first_equip_source(game, player) if pay_zero and game is not None else None
    if free_from is not None:
        cost = TotalCost(mana=ManaCost.parse("{0}"))
    elif game is not None:
        # "Equip abilities you activate cost {1} less" and its siblings
        # (`machines/cost/abilities.py`, CR 601.2f via CR 602.2b); the
        # alternative cost above replaces the cost whole (CR 118.9), so there
        # is nothing left for them to change.
        cost = TotalCost(
            mana=ability_cost_adjustment(
                game,
                player,
                equipment,
                cost.mana,
                kind="equip",
                targets=(target,) if target is not None else (),
            ),
            components=cost.components,
        )
    return KeywordActivation(
        card=equipment,
        player=player,
        keyword="Equip",
        rule=str(KeywordRule.EQUIP),
        zone=Zone.BATTLEFIELD,
        cost=cost,
        sorcery_only=game is None or not equip_at_instant_speed(game, player),
        ability=_synthetic_ability(ability, cost_text=ability.cost or "", effect=EQUIP_EFFECT),
        game=game,
        free_equip_from=free_from.name if free_from is not None else None,
    )


def _equip_effect(activation: KeywordActivation) -> CardState | None:
    """Attach the Equipment to its target (CR 702.6a, CR 701.3a).

    The target is rechecked here because CR 608.2b does: a creature that has
    left the battlefield, or changed controller out from under "creature you
    control", is no longer a legal target and the ability does nothing.

    The Equipment itself is re-read off `game` by id rather than mutated
    through `activation.card` directly, which matters only once
    `AbilityOnStack.keyword_activation` can survive a dump-and-decode round
    trip: `activation.card` is then a decoded `CardState` with the same id as,
    but not the same identity as, the one actually sitting in `game`'s zones,
    and `attach_to` writes onto `self.attachment` - mutating the decoded copy
    would leave the real battlefield Equipment looking unattached forever, a
    plausible-looking wrong game with no error anywhere. `game.find_by_id`
    finds the real object in the ordinary, non-decoded case too (there it *is*
    `activation.card`, so this changes nothing there), and falls back to
    `activation.card` only if the id is not on this `game` at all (CR 113.7a:
    the ability still resolves after its source is gone, and attaching a
    permanent that exists nowhere the game can see is indistinguishable from
    doing nothing).

    "Creature" is read off the computed board (CR 613.5), not off
    `CardState.is_creature`'s printed type line: CR 613.1d puts type-changing
    effects in layer 4, so a land animated by earthbend (CR 701.66a) is a
    creature "in addition to its other types" (CR 205.1b) and a legal host,
    which the printed read would refuse forever since a land's own type line
    never says creature. One target only, so no board is hoisted here - the
    hoisting rule is for a loop over the whole battlefield, and this loop is
    over `activation.targets`, which CR 601.2c already narrowed to at most one.
    """
    game = activation.game
    equipment = game.find_by_id(activation.card.id)
    if not isinstance(equipment, CardState):
        equipment = activation.card
    for target in activation.targets:
        creature = game.resolve_target(target)
        if not isinstance(creature, CardState):
            continue
        if creature.zone is not Zone.BATTLEFIELD:
            continue
        try:
            is_creature = game.characteristics_of(creature).is_creature
        except (AttributeError, KeyError):
            is_creature = creature.is_creature
        if not is_creature:
            continue  # CR 301.5: an Equipment can't legally be attached to a noncreature
        if game.controller_of(creature).username != activation.player:
            continue
        if equip_quality_refusal(game, _equip_quality_of(activation.ability.raw), creature):
            # CR 702.6c / CR 608.2b: the target no longer has the quality this
            # equip ability asked for, so it is illegal and nothing moves.
            continue
        if attach_refusal(game, equipment, creature) is not None:
            continue  # CR 301.5: it can't be equipped by this Equipment
        if _protection_refusal_for_attachment(game, equipment, creature) is not None:
            # CR 608.2b's recheck of a target that gained protection in
            # response, and CR 301.5b: "If an effect attempts to attach an
            # Equipment to an object that can't be equipped by it, the
            # Equipment doesn't move."
            continue
        equipment.attach_to(creature)
        return creature
    return None


def _protection_refusal_for_attachment(game: Any, attached: CardState, host: Any) -> str | None:
    """Why `host`'s protection keeps `attached` off it, or None.

    CR 702.16c: "A permanent or player with protection can't be enchanted by
    Auras that have the stated quality." CR 702.16d: "A permanent with
    protection can't be equipped by Equipment that have the stated quality or
    fortified by Fortifications that have the stated quality." Both are the
    same question - does the host have protection from a quality the attached
    permanent has - asked through `Game.protection_quality_against`, so a
    printed and a layer-6-granted protection answer alike. A host that is not
    a card on the battlefield (a player, or nothing) is not asked here.
    """
    if not isinstance(host, CardState) or host.zone is not Zone.BATTLEFIELD:
        return None
    quality = game.protection_quality_against(host, attached)
    if quality is None:
        return None
    from .protection_statics import aura_exempts_itself

    if aura_exempts_itself(game, attached, host, quality):
        return None
    return (
        f"{host.name} has protection from {quality}, so {attached.name} "
        f"cannot be attached to it (CR 702.16c, CR 702.16d)"
    )


# --------------------------------------------------------------------------
# Outlast (CR 702.107)
# --------------------------------------------------------------------------

#: CR 702.107a's expansion of "Outlast [cost]", after the colon.
OUTLAST_EFFECT = "Put a +1/+1 counter on this creature."


def has_outlast(card: Card) -> bool:
    """Whether this card prints an outlast ability (CR 702.107a)."""
    return _keyword(card, "outlast") is not None


def outlast_abilities(card: Card) -> list[KeywordAbility]:
    """Every outlast ability printed on this card, in printed order (CR 702.107a)."""
    return [
        ability for ability in keyword_abilities(card) if ability.canonical.lower() == "outlast"
    ]


def outlast_activation(
    game: Any, creature: CardState, player: str, index: int = 0
) -> KeywordActivation:
    """Build the activation for a creature's outlast ability (CR 702.107a).

    "Outlast is an activated ability. 'Outlast [cost]' means '[Cost], {T}:
    Put a +1/+1 counter on this creature. Activate only as a sorcery.'" The
    same synthetic-`KeywordActivation` shape equip and cycling already use
    (`_synthetic_ability`): `_keyword_cost` reads the keyword's own printed
    cost parameter - mana only, the only shape outlast is ever printed with -
    and the `{T}` half of "[Cost], {T}" is appended here the same way
    cycling appends its own "Discard this card" cost piece (CR 702.29a).

    CR 602.5a's summoning-sickness half - a creature with `{T}` in an
    activation cost can't activate it unless it has been controlled since
    its controller's most recent turn began - is not one of `KeywordActivation.
    why_not`'s own checks: equip's and cycling's costs never carry `{T}`, so
    nothing before outlast ever exercised that gap. `why_not` now reads it
    generally, off any battlefield-zone activation whose cost taps its own
    card, through `Game.can_activate_tap_ability` - the same method
    `Game.why_cannot_activate` already calls for a printed `{T}` ability.
    """
    printed = outlast_abilities(effective_card(game, creature))
    if index >= len(printed):
        raise ValueError(
            f"{creature.name} has no outlast ability number {index} ({KeywordRule.OUTLAST})"
        )
    ability = printed[index]
    cost = _keyword_cost(ability, player)
    if cost is None:
        raise ValueError(
            f"{creature.name}'s outlast cost {ability.cost!r} could not be read, "
            f"so it cannot be paid"
        )
    cost = TotalCost(
        mana=cost.mana,
        components=[*cost.components, tap_cost(creature, payer=player, description="{T}")],
    )
    return statically_priced(
        KeywordActivation(
            card=creature,
            player=player,
            keyword=ability.canonical,
            rule=str(KeywordRule.OUTLAST),
            zone=Zone.BATTLEFIELD,
            cost=cost,
            sorcery_only=True,
            ability=_synthetic_ability(
                ability, cost_text=f"{ability.cost or ''}, {{T}}".strip(", "), effect=OUTLAST_EFFECT
            ),
            game=game,
        )
    )


def _outlast_effect(activation: KeywordActivation) -> int | None:
    """CR 702.107a's effect: "Put a +1/+1 counter on this creature."

    `Game.add_counters` is CR 122.1/122.6's own replaceable event (a
    Doubling Season doubles this the same way it doubles any other counter
    placement), so this needs no counter-placement logic of its own.
    """
    game = activation.game
    creature = activation.card
    if creature.zone is not Zone.BATTLEFIELD:
        return None
    return game.add_counters(creature, Counter.PLUS_ONE, 1)


# --------------------------------------------------------------------------
# Crew (CR 702.122) and Vehicles (CR 301.7)
# --------------------------------------------------------------------------


def crew_activation(
    game: Any,
    vehicle: CardState,
    crewing: Sequence[CardState],
    player: str,
    *,
    loyalty_from: CardState | None = None,
) -> KeywordActivation:
    """Build the activation for a Vehicle's crew ability (CR 702.122a).

    "Crew is an activated ability of Vehicle cards. 'Crew N' means 'Tap any
    number of other untapped creatures you control with total power N or
    greater: This permanent becomes an artifact creature until end of turn.'"

    `crewing` is the set of creatures the player chose to tap. Three things are
    checked before the cost exists at all, because all three make the
    activation illegal rather than merely unpaid:

    - each creature is eligible (CR 702.122a's "other untapped creatures you
      control"), through the shared `crew_offer` in
      `machines/objects_as_costs.py` - CR 702.122b's "a creature crews a
      Vehicle when it's tapped to pay the cost" is what makes this a *cost*
      and so what puts it there rather than in the effect;
    - their total power reaches N, read off the computed board (CR 613.5), so a
      pumped 1/1 crews a Crew 3;
    - no creature is named twice, since it has only one untap to spend.

    Crew has **no** `{T}` symbol in its cost - the Vehicle is not what taps -
    so CR 302.6/CR 602.5a never apply to the Vehicle, and a Vehicle that
    entered this turn can be crewed. A summoning-sick *creature* can crew for
    the same reason: CR 302.6 restricts a creature's own `{T}` abilities, and
    crew is the Vehicle's ability, not the creature's. What the crewed Vehicle
    still cannot do is attack the turn it entered, because CR 508.1a asks about
    continuous control of the permanent and not about how long it has been a
    creature.
    """
    number = crew_number(effective_card(game, vehicle))
    if number is None:
        raise ValueError(f"{vehicle.name} has no crew ability ({KeywordRule.CREW})")

    if loyalty_from is not None:
        return _crew_by_loyalty_activation(game, vehicle, crewing, player, loyalty_from, number)
    chosen = list(crewing)
    offer = crew_offer(vehicle)
    seen: set[UUID] = set()
    for creature in chosen:
        refusal = offer.why_not(creature, player, game) or attached_crew_refusal(game, creature)
        if refusal is not None:
            raise ValueError(refusal)
        if creature.id in seen:
            raise ValueError(
                f"{creature.name} was chosen twice to crew {vehicle.name}, but it has "
                f"only one untap to spend ({KeywordRule.CREW}, CR 118.3)"
            )
        seen.add(creature.id)

    have = total_contribution(game, chosen, "crew")
    if have < number:
        listing = (
            ", ".join(f"{c.name} ({contribution(game, c, 'crew')})" for c in chosen) or "nothing"
        )
        raise ValueError(
            f"crewing {vehicle.name} needs total power {number} or greater, but "
            f"{listing} totals {have} ({KeywordRule.CREW})"
        )

    ability = _keyword(vehicle.card, "crew")
    assert ability is not None  # `crew_number` already found it
    cost = TotalCost(components=[offer.component(creature, player) for creature in chosen])
    return statically_priced(
        KeywordActivation(
            card=vehicle,
            player=player,
            keyword="Crew",
            rule=str(KeywordRule.CREW),
            zone=Zone.BATTLEFIELD,
            cost=cost,
            ability=_synthetic_ability(
                ability,
                cost_text=(
                    f"Tap any number of other untapped creatures you control "
                    f"with total power {number} or greater"
                ),
                effect="This permanent becomes an artifact creature until end of turn.",
            ),
            game=game,
        )
    )


def _crew_by_loyalty_activation(
    game: Any,
    vehicle: CardState,
    crewing: Sequence[CardState],
    player: str,
    planeswalker: CardState,
    number: int,
) -> KeywordActivation:
    """Heart of Kiran's "You may remove a loyalty counter from a planeswalker
    you control rather than pay [its] crew cost." (CR 118.9, CR 702.122a): the
    crew ability's cost is one loyalty counter removed from `planeswalker`
    instead of tapped creatures, so none may be named."""
    if not has_crew_loyalty_alternative(vehicle.card):
        raise ValueError(
            f"{vehicle.name} does not let its crew cost be paid by removing a loyalty counter "
            f"({KeywordRule.CREW}, CR 118.9)"
        )
    if crewing:
        raise ValueError(
            f"{vehicle.name}'s crew cost is paid by one loyalty counter or by tapping "
            "creatures, not both (CR 118.9a)"
        )
    if (
        planeswalker.zone is not Zone.BATTLEFIELD
        or Type.PLANESWALKER not in game.characteristics_of(planeswalker).types
    ):
        raise ValueError(f"{planeswalker.name} is not a planeswalker on the battlefield")
    if game.controller_of(planeswalker).username != player:
        raise ValueError(f"{player} does not control {planeswalker.name}")
    if planeswalker.counters[Counter.LOYALTY] < 1:
        raise ValueError(f"{planeswalker.name} has no loyalty counter to remove")
    ability = _keyword(vehicle.card, "crew")
    assert ability is not None
    cost = TotalCost(
        components=[
            remove_counters_cost(
                planeswalker,
                1,
                Counter.LOYALTY,
                payer=player,
                description=f"remove a loyalty counter from {planeswalker.name}",
            )
        ]
    )
    return statically_priced(
        KeywordActivation(
            card=vehicle,
            player=player,
            keyword="Crew",
            rule=str(KeywordRule.CREW),
            zone=Zone.BATTLEFIELD,
            cost=cost,
            ability=_synthetic_ability(
                ability,
                cost_text="Remove a loyalty counter from a planeswalker you control",
                effect="This permanent becomes an artifact creature until end of turn.",
            ),
            game=game,
        )
    )


def _crew_effect(activation: KeywordActivation) -> list[ContinuousEffect]:
    """The Vehicle becomes an artifact creature until end of turn (CR 702.122a).

    Two continuous effects, both in layer 4 (CR 613.1d) and both ending in the
    cleanup step (CR 514.2, CR 703.4p, via `Duration.UNTIL_END_OF_TURN`):
    artifact and creature, added rather than replacing, because a Vehicle is
    already an artifact and the rule's own wording ("becomes an artifact
    creature") keeps every other type it has - Parhelion II stays legendary.

    No layer 7 effect is created, and that is CR 301.7a/CR 301.7b read
    literally: "Each Vehicle has a printed power and toughness, but it has
    these characteristics only if it's also a creature", and "If a Vehicle
    becomes a creature, it immediately has its printed power and toughness."
    The printed values are already on the printing, so the moment layer 4 makes
    it a creature the board reports them; setting them again in layer 7b would
    overwrite an anthem or a +1/+1 counter that CR 613.4c should stack on top.

    CR 702.122e's "Whenever this Vehicle becomes crewed" is not modelled - see
    `docs/engine-coverage.md`.

    The Vehicle is re-read off `game` by id rather than through `activation.
    card` directly, the same re-resolve `_equip_effect` does and for the same
    reason: once `AbilityOnStack.keyword_activation` survives a dump-and-decode
    round trip, `activation.card` is a decoded `CardState` with the same id as,
    but not the same identity as, the object actually sitting in `game`'s
    zones. Crew goes on the stack, so an opponent gets a chance to destroy the
    Vehicle in response before this resolves; in the stateless-library world
    every priority pass is a dump/decode, and checking `activation.card.zone`
    directly reads a frozen snapshot taken when the ability was activated, not
    the Vehicle's zone now. CR 608.2h is the general rule this recheck serves:
    "If the effect requires information from a specific object ... the effect
    uses the current information of that object if it's in the public zone it
    was expected to be in; if it's no longer in that zone ... the effect uses
    the object's last known information." `game.find_by_id` gives the current
    information; falling back to `activation.card` only when the id is not on
    this `game` at all matches `_equip_effect`'s own fallback, for the same
    CR 113.7a reason (the ability still resolves after its source is gone).

    A previous pass claimed this function was "audited" and needed no fix
    because it does not mutate through `activation.card` - true, but beside
    the point: the bug here was never a wild mutation, it was reading a stale
    `.zone` off a decoded copy and creating two live `ContinuousEffect`s for a
    Vehicle that was actually already in a graveyard. `_cycling_effect` above
    is the one that was genuinely audited and is safe: it reads nothing off
    `activation.card` at all.
    """
    game = activation.game
    vehicle = game.find_by_id(activation.card.id)
    if not isinstance(vehicle, CardState):
        vehicle = activation.card
    if vehicle.zone is not Zone.BATTLEFIELD:
        # CR 608.2h / CR 400.7: a Vehicle that has left the battlefield is a
        # different object, and nothing here applies to it - the ability still
        # resolves (CR 113.7a) but does nothing.
        return []
    timestamp = game.continuous_effects.tick()
    created = [
        game.continuous_effects.add(
            ContinuousEffect(
                description=f"{vehicle.name} becomes an artifact creature until end of turn",
                layer=Layer.TYPE,
                timestamp=timestamp,
                duration=Duration.UNTIL_END_OF_TURN,
                source_id=vehicle.id,
                selector=_only(vehicle.id),
                modification=add_type(added),
            )
        )
        for added in (Type.ARTIFACT, Type.CREATURE)
    ]
    return created


# --------------------------------------------------------------------------
# Saddle (CR 702.171) and Mounts
# --------------------------------------------------------------------------


def saddle_number(card: Card) -> int | None:
    """The N of "Saddle N", or None when the card has no saddle ability (CR
    702.171a) - read off the keyword line, reminder text or not."""
    ability = _keyword(card, "saddle")
    if ability is None:
        return None
    printed = (ability.cost or ability.parameter or "").strip()
    if not printed and ability.count is not None:
        return ability.count
    return int(printed) if printed.isdigit() else None


def saddle_offer(mount: CardState) -> ObjectOffer:
    """CR 702.171a: "Tap any number of other untapped creatures you control" -
    the same object cost crew spends, keyed to saddle's own rule."""
    return ObjectOffer(
        keyword="saddle",
        rule=str(KeywordRule.SADDLE),
        action=ObjectAction.TAP,
        zone=Zone.BATTLEFIELD,
        permitted_types=frozenset({Type.CREATURE}),
        untapped_only=True,
        excluding=mount.id,
    )


def saddle_activation(
    game: Any, mount: CardState, saddling: Sequence[CardState], player: str
) -> KeywordActivation:
    """Build the activation for a Mount's saddle ability (CR 702.171a).

    "'Saddle N' means 'Tap any number of other untapped creatures you
    control with total power N or greater: This permanent becomes saddled
    until end of turn. Activate only as a sorcery.'" `saddling` are the
    creatures chosen to tap - each checked by the shared object-cost offer
    (other, untapped, a creature, yours) and their total power read off the
    computed board (CR 613.5), exactly the three checks `crew_activation`
    makes, since the cost is the same one. The Mount's own {T} is not part of
    the cost, so neither the Mount nor the creatures tapping for it are held
    back by summoning sickness (CR 302.6 restricts a creature's own {T}
    abilities)."""
    number = saddle_number(mount.card)
    if number is None:
        raise ValueError(f"{mount.name} has no saddle ability ({KeywordRule.SADDLE})")
    chosen = list(saddling)
    offer = saddle_offer(mount)
    seen: set[UUID] = set()
    for creature in chosen:
        refusal = offer.why_not(creature, player, game) or attached_crew_refusal(game, creature)
        if refusal is not None:
            raise ValueError(refusal)
        if creature.id in seen:
            raise ValueError(
                f"{creature.name} was chosen twice to saddle {mount.name}, but it has "
                f"only one untap to spend ({KeywordRule.SADDLE}, CR 118.3)"
            )
        seen.add(creature.id)
    have = total_contribution(game, chosen, "saddle")
    if have < number:
        listing = (
            ", ".join(f"{c.name} ({contribution(game, c, 'saddle')})" for c in chosen) or "nothing"
        )
        raise ValueError(
            f"saddling {mount.name} needs total power {number} or greater, but "
            f"{listing} totals {have} ({KeywordRule.SADDLE})"
        )
    ability = _keyword(mount.card, "saddle")
    assert ability is not None  # `saddle_number` already found it
    cost = TotalCost(components=[offer.component(creature, player) for creature in chosen])
    return statically_priced(
        KeywordActivation(
            card=mount,
            player=player,
            keyword="Saddle",
            rule=str(KeywordRule.SADDLE),
            zone=Zone.BATTLEFIELD,
            cost=cost,
            sorcery_only=True,
            ability=_synthetic_ability(
                ability,
                cost_text=(
                    f"Tap any number of other untapped creatures you control "
                    f"with total power {number} or greater"
                ),
                effect="This permanent becomes saddled until end of turn.",
            ),
            game=game,
        )
    )


def _saddle_effect(activation: KeywordActivation) -> CardState | None:
    """The Mount becomes saddled until end of turn (CR 702.171a/b), and each
    creature tapped to pay the cost saddled it (CR 702.171c).

    Re-read off `game` by id, as `_crew_effect` does: a Mount that left the
    battlefield in response is a new object (CR 400.7) and does not become
    saddled - the ability still resolves (CR 113.7a) and does nothing. The
    designation ends in the cleanup step (`machines/layers.ContinuousEffects.
    end_the_turn`, CR 514.2) or as the Mount leaves (`CardState.move_to`)."""
    game = activation.game
    mount = game.find_by_id(activation.card.id)
    if not isinstance(mount, CardState) or mount.zone is not Zone.BATTLEFIELD:
        return None
    if mount.zone_change_stamp != activation.card.zone_change_stamp:
        return None
    tapped = tuple(card.id for component in activation.cost.components for card in component.cards)
    mount.saddled = True
    mount.saddled_by = (*mount.saddled_by, *(i for i in tapped if i not in mount.saddled_by))
    return mount


# --------------------------------------------------------------------------
# Station (CR 702.184) and Station cards (CR 721)
# --------------------------------------------------------------------------


def station_activation(
    game: Any, permanent: CardState, tapped: CardState, player: str
) -> KeywordActivation:
    """Build the activation for a Station card's own ability (CR 702.184a).

    "Station is an activated ability. 'Station' means 'Tap another untapped
    creature you control: Put a number of charge counters on this permanent
    equal to the tapped creature's power. Activate only as a sorcery.'"

    `tapped` is the creature paying the cost, checked the same three ways
    `crew_activation` checks each of its own creatures before the cost is
    even built: it must actually be a creature (read off the computed board,
    CR 613.5, the same as `_equip_effect`'s host check - an animated land
    stations just as well as a printed creature), it must not be the Station
    permanent itself ("another"), and it must be under `player`'s control.
    `tap_cost`'s own `_why_not_tap`/`_why_not_controlled` still cover
    "untapped" and "controlled" again at payment time; the checks here are
    what make an *illegal* choice raise before a cost object is ever built,
    the same division `crew_activation`'s docstring draws.

    CR 721.2b: "Each station card has one or more station abilities, but
    each one is identical other than the station symbol." Since this pool's
    printings each carry exactly one `Station` line, this reads the sole
    `"station"` keyword rather than a numbered one - a future card with more
    than one would need `ability.count`/`.parameter` threaded through the
    same way multikicker distinguishes its own repeats.
    """
    ability = _keyword(permanent.card, "station")
    if ability is None:
        raise ValueError(f"{permanent.name} has no station ability ({KeywordRule.STATION})")
    if tapped.id == permanent.id:
        raise ValueError(
            f"{tapped.name} must be another creature, not {permanent.name} itself "
            f"({KeywordRule.STATION})"
        )
    try:
        is_creature = game.characteristics_of(tapped).is_creature
    except (AttributeError, KeyError):
        is_creature = tapped.is_creature
    if not is_creature:
        raise ValueError(
            f"{tapped.name} is not a creature, so it cannot be tapped to station "
            f"{permanent.name} ({KeywordRule.STATION})"
        )
    if game.controller_of(tapped).username != player:
        raise ValueError(f"{tapped.name} is not controlled by {player} ({KeywordRule.STATION})")
    cost = TotalCost(components=[tap_cost(tapped, payer=player)])
    return statically_priced(
        KeywordActivation(
            card=permanent,
            player=player,
            keyword="Station",
            rule=str(KeywordRule.STATION),
            zone=Zone.BATTLEFIELD,
            cost=cost,
            sorcery_only=True,
            ability=_synthetic_ability(
                ability,
                cost_text="Tap another untapped creature you control",
                effect=(
                    "Put a number of charge counters on this permanent equal to the tapped "
                    "creature's power."
                ),
            ),
            game=game,
        )
    )


def _station_effect(activation: KeywordActivation) -> CardState | None:
    """Put charge counters on the station equal to the tapped creature's
    power (CR 702.184a), read at resolution time (CR 608.2h) - a pump spell
    cast in response changes how many counters land, the same live-read
    `_equip_effect`'s target check and `_crew_effect`'s zone check already
    take, both off the current board rather than a decoded snapshot.

    Both objects are re-read off `game` by id for the identical reason those
    two functions already document: `activation.card`/`.cost` are frozen at
    the moment the ability was activated, and only `game.find_by_id` sees
    what changed on the stack in between.
    """
    game = activation.game
    permanent = game.find_by_id(activation.card.id)
    if not isinstance(permanent, CardState) or permanent.zone is not Zone.BATTLEFIELD:
        return None
    paid = activation.cost.components[0].cards
    if not paid:
        return None
    tapped = game.find_by_id(paid[0].id)
    if not isinstance(tapped, CardState):
        return None
    amount = station_amount(game, tapped)
    if amount > 0:
        game.add_counters(permanent, Counter.CHARGE, amount)
    return permanent


# --------------------------------------------------------------------------
# Ninjutsu (CR 702.49)
# --------------------------------------------------------------------------


def ninjutsu_activation(
    game: Any, card: CardState, returning: CardState, player: str
) -> KeywordActivation:
    """Build the activation for a card's ninjutsu ability (CR 702.49a).

    "Ninjutsu is an activated ability that functions only while the card
    with ninjutsu is in a player's hand. 'Ninjutsu [cost]' means '[Cost],
    Reveal this card from your hand, Return an unblocked attacking creature
    you control to its owner's hand: Put this card onto the battlefield from
    your hand tapped and attacking.'"

    CR 701.20a/b: revealing changes no game state, so only the mana and the
    return-to-hand (`return_to_hand_cost`, `_why_not_return_to_hand`) become
    real cost components - the same "reveal changes nothing" reading
    `_evoke_ability`'s own docstring and `casting.py`'s `KeywordActivation`
    module note already rely on elsewhere in this file.

    `commander ninjutsu` (CR 702.49d) reads the same way here: CR 903.10a's
    command-zone half is a deckbuilding/format rule this engine's board does
    not model, so the ordinary hand-only activation is what a real game
    reaches either way.
    """
    granted = effective_card(game, card)
    ability = _keyword(granted, "ninjutsu") or _keyword(granted, "commander ninjutsu")
    if ability is None:
        raise ValueError(f"{card.name} has no ninjutsu ability ({KeywordRule.NINJUTSU})")
    if card.zone is not Zone.HAND:
        raise ValueError(
            f"{card.name} is not in a hand, so ninjutsu cannot be activated "
            f"({KeywordRule.NINJUTSU}, CR 702.49b)"
        )
    attack = game.combat.attack_by(returning.id) if game.combat is not None else None
    if attack is None:
        raise ValueError(
            f"{returning.name} is not attacking, so it cannot pay ninjutsu's cost "
            f"({KeywordRule.NINJUTSU})"
        )
    # CR 702.49c's own defender has to be captured *now*, before the return
    # to hand takes the creature out of combat entirely - `Combat.attack_by`
    # finds nothing for an id no longer on the battlefield, which is exactly
    # what `_ninjutsu_effect` would be asking after the cost is paid.
    defender = attack.defender
    mana = _keyword_cost(ability, player)
    if mana is None:
        raise ValueError(
            f"{card.name}'s ninjutsu cost {ability.cost!r} could not be read, so it cannot be paid"
        )
    cost = TotalCost(
        mana=ability_cost_adjustment(
            game, player, card, mana.mana, kind="ninjutsu", from_zone=Zone.HAND
        ),
        components=[
            *mana.components,
            return_to_hand_cost(
                returning,
                payer=player,
                description=(
                    "Return an unblocked attacking creature you control to its owner's hand"
                ),
            ),
        ],
    )
    return KeywordActivation(
        card=card,
        player=player,
        keyword=ability.canonical,
        rule=str(KeywordRule.NINJUTSU),
        zone=Zone.HAND,
        cost=cost,
        targets=[defender],
        ability=_synthetic_ability(
            ability,
            cost_text=(
                f"{ability.cost or ''}, Reveal this card from your hand, Return an "
                f"unblocked attacking creature you control to its owner's hand"
            ).strip(", "),
            effect="Put this card onto the battlefield from your hand tapped and attacking.",
        ),
        game=game,
    )


def _ninjutsu_effect(activation: KeywordActivation) -> CardState | None:
    """Put the ninja onto the battlefield tapped and attacking the same
    player, planeswalker, or battle the returned creature was attacking
    (CR 702.49c).

    The returned creature's own attack is read off `activation.cost`'s
    return-to-hand component before the return moved it - the object is
    gone from combat now (`Combat.attack_by` finds nothing for an id that
    already left the battlefield), so what it was attacking has to be read
    at *activation* time and carried forward, not re-derived here.
    """
    game = activation.game
    card = game.find_by_id(activation.card.id)
    if not isinstance(card, CardState) or card.zone is not Zone.HAND:
        return None
    defender = activation.targets[0] if activation.targets else None
    from ..models.token import _put_onto_the_battlefield_attacking

    # The enters event is raised when the block closes (CR 603.6a), by which
    # time the ninja is already attacking: a "when this enters from your hand,
    # if it's attacking" ability (Thousand-Faced Shadow, CR 603.4) checks the
    # event's board, and CR 508.4 puts it there "attacking as it enters".
    with game.entering_together():
        permanent = game.put_onto_battlefield(card, activation.player, tapped=True)
        if permanent is None or permanent.zone is not Zone.BATTLEFIELD:
            return None
        if defender is not None:
            # CR 508.4, via the same primitive `Game._sneak_defender_of`'s caller
            # uses for sneak's identical "tapped and attacking" shape (CR
            # 702.190b): it is annotated for a `TokenState`, but everything it
            # reads - `is_creature`, `controller`, `id` - is `CardState`'s, and
            # CR 508.4 draws no distinction between a token and a card entering
            # this way.
            _put_onto_the_battlefield_attacking(game, permanent, defender)  # type: ignore[arg-type]
    return permanent


#: The subtypes CR 704.5n names, and the host each one may legally be on.
#: An Equipment attaches to a creature (CR 301.5a, CR 702.6a); a Fortification
#: attaches to a land, and CR 301.6 says "It can't legally be attached to an
#: object that isn't a land."
_ATTACHES_TO: dict[str, str] = {"Equipment": "creature", "Fortification": "land"}


def _host_is_legal_for(
    game: Any,
    attached: CardState,
    host: CardState | None,
    wanted: str,
    board: ComputedBoard | None = None,
) -> bool:
    """Whether CR 704.5n's host is a legal one for this Equipment or Fortification.

    Computed types (CR 613.5), not `host.is_creature`/`Type.LAND in host.types`'s
    printed read: CR 613.1d's layer 4 is what makes Karn, the Great Creator's
    animated noncreature artifact a legal Equipment host, and what makes an
    earthbent land (CR 701.66a) - land "in addition to" creature, CR 205.1b -
    a legal one too. `board` lets a caller looping the whole battlefield hoist
    one `computed_board()` instead of paying for a fresh one per host asked
    about here.
    """
    if host is None or host.zone is not Zone.BATTLEFIELD:
        return False
    if host.id == attached.id:
        return False  # CR 301.5c: "An Equipment can't equip itself."
    types, _subtypes = _computed_types_and_subtypes(game, host, board)
    if not (Type.CREATURE in types if wanted == "creature" else Type.LAND in types):
        return False
    # CR 702.16d: an Equipment or Fortification with a quality its host has
    # protection from is on an illegal permanent, so CR 704.5n unattaches it.
    return _protection_refusal_for_attachment(game, attached, host) is None


def equipment_state_based_actions(game: Any) -> list[CardState]:
    """CR 704.5n: an Equipment or Fortification on an illegal host becomes unattached.

    "If an Equipment or Fortification is attached to an illegal permanent or to
    a player, it becomes unattached from that permanent or player. It remains on
    the battlefield." So an equipped creature dying leaves the Equipment behind,
    which is the opposite of an Aura (CR 704.5m).

    **What this rule does *not* cover is the reason it is written this
    narrowly.** CR 704.5 has three unattachment actions and they are different
    rules with different subjects, which only a read of the whole letter list
    tells apart:

    - **CR 704.5m** - an *Aura* on an illegal object or player is put into its
      owner's graveyard, not unattached. `aura_state_based_actions`.
    - **CR 704.5n** - this one, and only for the two subtypes it names.
    - **CR 704.5p** - every *other* attached permanent, unattached
      unconditionally. `attachment_state_based_actions`.

    Checking only "is the host a creature" without first asking what the
    attached permanent *is* would unattach an Aura legally enchanting a land,
    which is CR 704.5m's business and answers "legal" there.

    Legality is read off the subtype rather than assumed: CR 301.5a and
    CR 702.6a put an Equipment on a creature, CR 301.6 puts a Fortification on
    a land, and CR 301.5c adds that an Equipment cannot equip itself.

    Both the attached permanent's own subtype and its host's types are read
    off the computed board (CR 613.5) rather than the printed line, through
    `_computed_types_and_subtypes` - the same helper `attachment_state_based_
    actions` next to this one already uses - and one `computed_board()` is
    hoisted for the whole loop rather than recomputed per permanent, since
    `characteristics_of` reruns the entire layer stack on every call.
    """
    unattached: list[CardState] = []
    board = game.computed_board()
    for permanent in list(game.battlefield):
        if permanent.attached_to is None:
            continue
        _types, subtypes = _computed_types_and_subtypes(game, permanent, board)
        wanted = next(
            (host_kind for name, host_kind in _ATTACHES_TO.items() if name in subtypes),
            None,
        )
        if wanted is None:
            continue  # CR 704.5m's Aura, or CR 704.5p's everything else.
        host = game.find_by_id(permanent.attached_to)
        host = host if isinstance(host, CardState) else None
        if not _host_is_legal_for(game, permanent, host, wanted, board) or (
            wanted == "creature" and attach_refusal(game, permanent, host) is not None
        ):
            permanent.unattach()
            unattached.append(permanent)
    return unattached


def has_ascend(card: Card) -> bool:
    """Whether this card's own printed text grants *ascend* (CR 702.131)."""
    return any(keyword.lower() == "ascend" for keyword in card.keywords)


_ASCEND_LINE = re.compile(r"^ascend\b", re.IGNORECASE)


def _has_computed_ascend(board: ComputedBoard, permanent: CardState) -> bool:
    """Whether this permanent currently has ascend (CR 613.5), off `board`
    rather than `has_ascend`'s printed keyword read.

    `Characteristics.abilities` is oracle-text lines (one per line, reminder
    text included - `machines/layers.py`'s `_ability_lines`), not the parsed
    Scryfall keyword list `has_ascend` reads, so this matches the line by its
    first word rather than by exact membership: a card removed of all
    abilities in layer 6 (CR 613.1f) - Humility, Dress Down - has no line
    starting `ascend` left to match, even though its printed keyword list
    still says it has one.
    """
    try:
        abilities = board.of(permanent).abilities
    except KeyError:
        return has_ascend(permanent.card)
    return any(_ASCEND_LINE.match(line) for line in abilities)


def grant_the_citys_blessing(game: Any) -> list[str]:
    """CR 702.131b: "Ascend on a permanent represents a static ability. It
    means 'Any time you control ten or more permanents and you don't have the
    city's blessing, you get the city's blessing for the rest of the game.'"

    **"Any time" is the timing**, and it is not a state-based action's - CR
    704.5 lists no such item. A blessing that waited for the next state-based
    check arrived too late for anything read before that check: Ocelot Pride's
    end-step trigger makes the Cat that is its controller's tenth permanent and
    then, in the same resolution, asks "if you have the city's blessing" - a
    question no state-based check can get in between (battle report B2-07).

    So `Game.emit` calls this before it matches any trigger, which is every
    time the game raises an event - a permanent entering among them - and
    CR 702.131d is why it comes first: "After a player gets the city's
    blessing, continuous effects are reapplied before the game checks to see
    if the game state or preceding events have matched any trigger
    conditions." Continuous effects here are recomputed on every
    `computed_board()` read rather than reapplied, so nothing further is owed
    to that rule. The state-based pass still calls it as well, for a change no
    event announces.

    `Player.has_citys_blessing` is CR 702.131c's designation, "no rules
    meaning other than to act as a marker" that, once set, nothing in the
    rules ever clears - so this only ever turns the flag on, and a player who
    already has it is skipped outright rather than rechecked.

    Ascend on an instant or sorcery is CR 702.131a's spell ability instead,
    `ascend_as_a_spell_resolves` below.

    Ascend is read off the computed board (`_has_computed_ascend`), not off
    `has_ascend`'s printed keyword: CR 613.5's layer 6 (CR 613.1f) can remove
    the ability, and a printed-only read would keep granting the blessing to
    a player whose only ascend permanent has had it stripped - Humility and
    Dress Down are the cards in the pool that strip it. The board is computed
    only once some player without the blessing reaches ten permanents, and
    then once for every player this checks.
    """
    blessed: list[str] = []
    board: ComputedBoard | None = None
    for player in game.players_in_game:
        if player.has_citys_blessing:
            continue
        permanents = game.permanents_controlled_by(player.username)
        if len(permanents) < 10:
            continue
        if board is None:
            board = game.computed_board()
        if not any(_has_computed_ascend(board, permanent) for permanent in permanents):
            continue
        player.has_citys_blessing = True
        blessed.append(player.username)
    return blessed


_STORIED_LINE = re.compile(r"^storied\b", re.IGNORECASE)


def _has_computed_storied(board: ComputedBoard, permanent: CardState) -> bool:
    """Whether this permanent currently has storied (CR 613.5), off `board` -
    the same first-word line match `_has_computed_ascend` makes, so a
    permanent stripped of its abilities in layer 6 (CR 613.1f) has none."""
    try:
        abilities = board.of(permanent).abilities
    except KeyError:
        return any(keyword.lower() == "storied" for keyword in permanent.card.keywords)
    return any(_STORIED_LINE.match(line) for line in abilities)


def _counts_toward_storied(board: ComputedBoard, permanent: CardState) -> bool:
    """CR 702.195a's "permanents that are artifacts, Sagas, and/or legendary",
    read off the computed characteristics - one permanent counts once however
    many of the three it is."""
    try:
        chars = board.of(permanent)
        types, subtypes, supertypes = chars.types, chars.subtypes, chars.supertypes
    except KeyError:
        types, subtypes = permanent.types, permanent.subtypes
        supertypes = permanent.card.supertypes
    return (
        Type.ARTIFACT in types
        or Supertype.LEGENDARY in supertypes
        or any(subtype.lower() == "saga" for subtype in subtypes)
    )


def grant_enduring_stories(game: Any) -> list[str]:
    """CR 702.195a: "Storied is a static ability. It means 'Any time you
    control three or more permanents that are artifacts, Sagas, and/or
    legendary and you don't have an enduring story, you have an enduring story
    for the rest of the game.'"

    Ascend's twin (`grant_the_citys_blessing`), and run from the same two
    places for the same reasons: `Game.emit` before it matches any trigger -
    CR 702.195c: "After a player gets an enduring story, continuous effects
    are reapplied before the game checks to see if the game state or
    preceding events have matched any trigger conditions" - and the
    state-based pass, for a change no event announces.

    `Player.has_enduring_story` is CR 702.195b's designation: only ever set,
    and a player who already has it is skipped. Storied and the qualifying
    types are both read off the computed board (CR 613.5), which is computed
    only once some player without the story controls three permanents.
    """
    granted: list[str] = []
    board: ComputedBoard | None = None
    for player in game.players_in_game:
        if player.has_enduring_story:
            continue
        permanents = game.permanents_controlled_by(player.username)
        if len(permanents) < 3:
            continue
        if board is None:
            board = game.computed_board()
        if not any(_has_computed_storied(board, permanent) for permanent in permanents):
            continue
        if sum(1 for permanent in permanents if _counts_toward_storied(board, permanent)) < 3:
            continue
        player.has_enduring_story = True
        granted.append(player.username)
    return granted


def ascend_as_a_spell_resolves(game: Any, spell: CardState) -> bool:
    """CR 702.131a: "Ascend on an instant or sorcery spell represents a spell
    ability. It means 'If you control ten or more permanents and you don't
    have the city's blessing, you get the city's blessing for the rest of the
    game.'"

    A spell ability is an instruction followed as the spell resolves (CR
    608.2c), and the ascend line is printed ahead of the rest of the text, so
    `Game._resolve_top` follows it before the spell's own effect runs - which
    is what lets Secrets of the Golden City's "If you have the city's
    blessing, draw three cards instead" read a blessing this same resolution
    granted. Nothing is granted while the spell only waits on the stack, and a
    spell that does not resolve (CR 608.2b) never follows it.

    Read off the printed keyword: a spell on the stack is not on the board
    `computed_board()` covers. Returns whether the blessing was granted now.
    """
    if spell.is_permanent or not has_ascend(spell.card):
        return False
    controller = game.controller_of(spell)
    if controller.has_citys_blessing:
        return False
    if len(game.permanents_controlled_by(controller.username)) < 10:
        return False
    controller.has_citys_blessing = True
    return True


#: "Awaken N—[cost]" as printed on the keyword line (CR 702.113a); the cost
#: itself is `KeywordAbility.cost`, read by `casting.options`.
_AWAKEN_LINE_RE = re.compile(r"^awaken (?P<n>\d+)\s*(?:—|-)", re.IGNORECASE | re.MULTILINE)


def awaken_count(card: Card) -> int | None:
    """The N of a printed "Awaken N—[cost]", or None."""
    match = _AWAKEN_LINE_RE.search(card.oracle_text or "")
    return None if match is None else int(match.group("n"))


def awakened(game: Any, spell: CardState) -> bool:
    """CR 702.113a's "If this spell's awaken cost was paid"."""
    if spell.is_permanent or awaken_count(spell.card) is None:
        return False
    record = game.cast_record(spell)
    return (record.keyword or "").lower() == "awaken" and record.keyword_cost_paid


_PARENTHETICAL_RE = re.compile(r"(\([^)]*\))")
_TARGET_WORD_RE = re.compile(r"\btarget\b", re.IGNORECASE)


def overloaded(game: Any, spell: CardState) -> bool:
    """CR 702.96a: whether this spell was cast by paying its overload cost."""
    if spell.is_permanent:
        return False
    record = game.cast_record_of(spell)
    return (
        record is not None and (record.keyword or "").lower() == "overload" and record.keyword_cost_paid
    )


def overload_text(text: str) -> str:
    """CR 702.96a: "change its text by replacing all instances of the word
    'target' with the word 'each.'" Reminder text and the keyword line itself
    are not the spell's rules text and keep their words."""
    lines = []
    for line in text.split("\n"):
        if re.match(r"overload\b", line, re.IGNORECASE):
            lines.append(line)
            continue
        parts = _PARENTHETICAL_RE.split(line)
        lines.append(
            "".join(
                part if part.startswith("(") else _TARGET_WORD_RE.sub("each", part)
                for part in parts
            )
        )
    return "\n".join(lines)


@contextmanager
def awaken_target_held_apart(game: Any, spell: CardState) -> Iterator[TargetRef | None]:
    """While the spell's own text resolves, its targets are only the ones that
    text names: the awaken target (CR 702.113b, chosen last - `casting.
    options.with_keyword_spell_ability_target`) belongs to the awaken spell
    ability alone, so Clutch of Currents' "Return target creature" never
    sees the land. Yields that target, or None when awaken was not paid."""
    if not awakened(game, spell) or not spell.targets:
        yield None
        return
    held = spell.targets[-1]
    spell.targets = list(spell.targets[:-1])
    try:
        yield held
    finally:
        spell.targets = [*spell.targets, held]


def awaken_as_the_spell_resolves(game: Any, spell: CardState, held: TargetRef | None) -> bool:
    """CR 702.113a's spell ability: "put N +1/+1 counters on target land you
    control. That land becomes a 0/0 Elemental creature with haste. It's
    still a land." Followed after the rest of the text (it is printed last,
    CR 608.2c). A target that is no longer legal - gone, a new object, no
    longer a land, or no longer the caster's - is skipped (CR 608.2b).

    The animation states no duration, so it lasts indefinitely (CR 611.2a),
    scoped to this incarnation of the land (CR 400.7): the creature type and
    the Elemental subtype are added in layer 4 ("It's still a land"), power
    and toughness set to 0/0 in sublayer 7b, haste granted in layer 6; the
    counters are real counters, sublayer 7c (CR 613.4)."""
    if held is None:
        return False
    count = awaken_count(spell.card)
    land = game.legal_target(spell, held)
    if count is None or not isinstance(land, CardState) or land.zone is not Zone.BATTLEFIELD:
        return False
    if held.zone_change_stamp is not None and land.zone_change_stamp != held.zone_change_stamp:
        return False
    controller = game.controller_of(spell).username
    if game.controller_of(land).username != controller:
        return False
    if Type.LAND not in game.characteristics_of(land).types:
        return False
    from .layers import add_subtype, set_power_toughness

    stamp = land.zone_change_stamp
    effects = game.continuous_effects
    for description, layer, sublayer, modification in (
        (f"awaken: {land.name} becomes a creature", Layer.TYPE, None, add_type(Type.CREATURE)),
        (f"awaken: {land.name} is an Elemental", Layer.TYPE, None, add_subtype("Elemental")),
        (
            f"awaken: {land.name} is 0/0",
            Layer.POWER_TOUGHNESS,
            Sublayer.SET,
            set_power_toughness(0, 0),
        ),
        (f"awaken: {land.name} has haste", Layer.ABILITY, None, grant_ability("Haste")),
    ):
        effects.add(
            ContinuousEffect(
                description=description,
                layer=layer,
                sublayer=sublayer,
                timestamp=effects.tick(),
                duration=Duration.INDEFINITE,
                selector=only_this_incarnation(land, stamp),
                modification=modification,
            )
        )
    game.add_counters(land, Counter.PLUS_ONE, count)
    return True


def attachment_state_based_actions(game: Any) -> list[CardState]:
    """CR 704.5p: a permanent that may not be attached to anything at all.

    "If a battle or creature is attached to an object or player, it becomes
    unattached and remains on the battlefield. Similarly, if any nonbattle,
    noncreature permanent that's neither an Aura, an Equipment, nor a
    Fortification is attached to an object or player, it becomes unattached and
    remains on the battlefield."

    Unconditional, and that is what separates it from CR 704.5n: this rule never
    asks whether the host is *legal*, only whether the attached permanent is a
    kind that may be attached at all. A creature is not, whatever it is sitting
    on - which is how CR 301.5c's "An Equipment that's also a creature can't
    equip a creature" arrives as a state-based action.

    The three subtypes it excuses are excused because the other two rules
    already police them: an Aura by CR 704.5m, an Equipment or Fortification by
    CR 704.5n.

    **Computed types, not printed ones** (CR 613.5: "the application of
    continuous effects as described by the layer system is continually and
    automatically performed by the game. All resulting changes to an object's
    characteristics are instantaneous"). The only way an attached permanent in
    this pool ever *becomes* a creature is a layer 4 effect landing on it while
    it sits there - Karn, the Great Creator's "+1: Until your next turn, up to
    one target noncreature artifact becomes an artifact creature ..." aimed at an
    equipped Equipment - and `CardState.types` reads the printed type line, so
    asking it would answer "artifact" and this rule would never fire on the one
    board that reaches it. The subtype excusals are read off the same computed
    characteristics, which is CR 301.5c's second sentence ("an Equipment that
    loses the subtype 'Equipment' can't equip anything") for free. A permanent
    the layer engine cannot answer for falls back to the printed reading.

    Dispatched by `Game._state_based_actions_once`, immediately after
    `equipment_state_based_actions`, so an ordinary state-based-action check
    performs it - CR 704.3 then repeats the check, which is what turns the
    unattachment into the start of the next round rather than a loose end.
    """
    unattached: list[CardState] = []
    for permanent in list(game.battlefield):
        if permanent.attached_to is None:
            continue
        types, subtypes = _computed_types_and_subtypes(game, permanent)
        if Type.CREATURE in types or Type.BATTLE in types:
            permanent.unattach()
            unattached.append(permanent)
            continue
        if any(name in subtypes for name in ("Aura", "Equipment", "Fortification")):
            continue
        permanent.unattach()
        unattached.append(permanent)
    return unattached


def _computed_types_and_subtypes(
    game: Any, permanent: CardState, board: ComputedBoard | None = None
) -> tuple[tuple[Type, ...], tuple[str, ...]]:
    """This permanent's card types and subtypes with the layers applied
    (CR 613.5), falling back to the printed ones when there is no layer engine
    behind `game` or it has nothing computed for this object.

    `board`, when given, is read instead of asking `game.characteristics_of`
    fresh - which reruns the whole layer stack (`Game.computed_board`'s own
    docstring on why it is not cached) - so a caller looping the battlefield
    can hoist one `computed_board()` and pass it in here per permanent rather
    than paying for a full recompute each time.
    """
    try:
        computed = board.of(permanent) if board is not None else game.characteristics_of(permanent)
    except (AttributeError, KeyError):
        return tuple(permanent.types), tuple(permanent.subtypes)
    return tuple(computed.types), tuple(computed.subtypes)


def equipped_creature(game: Any, equipment: CardState) -> CardState | None:
    """The creature this Equipment is attached to, or None (CR 301.5a)."""
    if equipment.attached_to is None:
        return None
    host = game.find_by_id(equipment.attached_to)
    return host if isinstance(host, CardState) else None


# --------------------------------------------------------------------------
# Activated abilities that function off the battlefield (CR 113.6j, 113.6m)
# --------------------------------------------------------------------------
#
# Cycling and equip are CR 702 keywords: the ability they expand to has one
# fixed meaning, the same on every card that prints it, which is why each gets
# its own hand-written effect above. Channel (Boseiju, Otawara), and the plain,
# unkeyworded abilities on World Breaker and Waker of Waves, are the opposite
# shape: `[Cost]: [Effect.]` printed like any battlefield activated ability,
# whose *effect* is arbitrary card text - the only unusual thing about them is
# where they function, which `abilities._activated_ability_zone` already read
# off the printed cost and effect while parsing (CR 113.6j: a cost that can't
# be paid on the battlefield; CR 113.6m: an effect that names the object's own
# graveyard as where it starts). `KeywordActivation` still does the work -
# CR 602.5's wrong-zone refusal is the same question whichever rule put the
# ability there - but `generic_effect=True` sends its resolution back to the
# ordinary per-card path instead of asking this module for a fixed one.


def off_battlefield_activation(
    game: Any,
    card: CardState,
    player: str,
    index: int = 0,
    *,
    targets: list[Any] | None = None,
    sacrificing: list[CardState] | None = None,
    discarding: list[CardState] | None = None,
    exiling: list[CardState] | None = None,
    x_value: int = 0,
) -> KeywordActivation:
    """Build the activation for one of this card's printed activated abilities
    that functions off the battlefield (CR 113.6j, CR 113.6m).

    `index` counts only among the abilities `abilities.parse_abilities` read a
    `zone` for, in printed order - Boseiju's `{T}: Add {G}` does not have one,
    so `index=0` is always its Channel ability even though Channel is not the
    card's first printed ability.

    `targets` is announced and checked here (CR 601.2c, via CR 602.2b's "the
    remainder of the process ... is identical to ... casting a spell"), the
    same way `Game.activate_ability` checks a battlefield activation against
    the ability's own text rather than the card's spell text (CR 113.1c) - a
    target this ability's own printed text refuses is refused just as early
    whether the ability functions on the battlefield or not.

    CR 113.7a: once this is put on the stack (`KeywordActivation.activate`),
    the ability exists independently of `card` - the discard or sacrifice a
    caller pays through `begin_paying` happens *before* `activate`, so by the
    time this ability is on the stack its own source may already have left the
    zone it was activated from (Channel's cost is discarding this very card).
    Nothing about resolving the ability depends on finding it there again.
    """
    from .targeting import profile_for_text

    candidates = [
        (source_index, ability)
        for source_index, ability in enumerate(activated_abilities_of(card.card))
        if ability.zone is not None
    ]
    if index >= len(candidates):
        raise ValueError(
            f"{card.name} has no activated ability functioning off the battlefield, number {index}"
        )
    source_index, ability = candidates[index]
    zone = ability.zone
    zone_rule = ability.zone_rule
    assert zone is not None and zone_rule is not None  # `zone` implies `zone_rule` (abilities.py)

    profile = profile_for_text(ability.text)
    if profile.understood and profile.requirements:
        profile.check(list(targets or []), player, game, source=card)

    cost = game.activation_cost(
        card,
        source_index,
        player,
        sacrificing=sacrificing,
        discarding=discarding,
        exiling=exiling,
        x_value=x_value,
    )
    return KeywordActivation(
        card=card,
        player=player,
        keyword=ability.ability_word or "activated",
        rule=zone_rule,
        zone=zone,
        cost=cost,
        ability=ability,
        targets=[TargetRef.coerce(target) for target in targets or []],
        x_value=x_value,
        generic_effect=True,
        game=game,
        forecast=ability.forecast,
    )


# --------------------------------------------------------------------------
# One index space over every off-battlefield activation
# --------------------------------------------------------------------------


class OffZoneAbility(NamedTuple):
    """One activated ability of a card that functions somewhere other than the
    battlefield, and where it sits in `off_zone_abilities`' single ordered
    pool.

    Two different engine entry points build these - `cycling_activation` for
    a CR 702.29a keyword line, `off_battlefield_activation` for a printed
    `[Cost]: [Effect]` line whose own words put it in another zone - and each
    counted its own family from zero. So "off-battlefield activation number
    0" named two different abilities on a card printing one of each, which
    made `machines/legal_actions`' own `ACTIVATE_OFF_ZONE` action
    (`models/action.Action`, "the arguments one engine entry point takes")
    ambiguous exactly where it promises not to be: a caller holding
    `(card_id, ability_index)` could not tell which entry point it meant.
    This pool is the one index space both families share, and
    `off_zone_activation` is the one call that reads it.

    `family` says which expansion built it, `index` is its position within
    that family (what `cycling_activation`/`off_battlefield_activation`
    themselves still take), `keyword` is the CR 702 keyword for a cycling
    line and the CR 207.2c ability word - `None` for a card like Waker of
    Waves, which prints neither - for a printed one.
    """

    family: str
    """`"cycling"` (CR 702.29a) or `"printed"` (CR 113.6b/113.6j/113.6m)."""
    index: int
    """Position within `family`, which is what the family's own builder takes."""
    keyword: str | None
    zone: Zone
    rule: str
    """The verified CR number that puts this ability in `zone`."""
    ability: ActivatedAbility
    """What activating this actually asks for - the card's own printed
    `ActivatedAbility` for the `"printed"` family, or the rule's own
    expansion (`_synthetic_ability`, the same one `cycling_activation`
    builds) for `"cycling"` - so a caller reading "what does this cost, what
    does it target" (`engine_api.ability_hints` is exactly that caller) does
    not have to branch on which family built the entry."""


#: A scavenge line as a grant writes it out: "Scavenge {2}{G}" - the keyword
#: and the cost `spell_grants.granted_zone_keyword_lines` computed.
_SCAVENGE_LINE_RE = re.compile(r"^Scavenge (?P<cost>\{.+\})$")

#: CR 702.97a's whole ability, as the rule spells it after the cost.
_SCAVENGE_EFFECT = (
    "Put a number of +1/+1 counters equal to the power of the card you exiled on target creature"
)


def scavenge_abilities(
    card: Card, state: CardState | None = None, game: Any = None
) -> list[KeywordAbility]:
    """Every scavenge ability `card` has (CR 702.97a): the printed ones, then -
    when `state` is the card in a game - the ones a static ability grants it
    ("Each creature card in your graveyard has scavenge. The scavenge cost is
    equal to its mana cost.", `machines/spell_grants.py`)."""
    found = [
        ability for ability in keyword_abilities(card) if ability.canonical.lower() == "scavenge"
    ]
    if state is not None and game is not None:
        from .spell_grants import granted_zone_keyword_lines

        for line in granted_zone_keyword_lines(game, state, "scavenge"):
            match = _SCAVENGE_LINE_RE.fullmatch(line)
            if match is not None:
                found.append(
                    KeywordAbility(
                        raw=line,
                        text=line,
                        face="",
                        keyword="Scavenge",
                        canonical="Scavenge",
                        cost=match.group("cost"),
                        cost_is_mana=True,
                    )
                )
    return found


def scavenge_activation(
    game: Any,
    card: CardState,
    player: str,
    index: int = 0,
    *,
    targets: list[Any] | None = None,
) -> KeywordActivation:
    """CR 702.97a: "'Scavenge [cost]' means '[Cost], Exile this card from your
    graveyard: Put a number of +1/+1 counters equal to the power of the card you
    exiled on target creature. Activate only as a sorcery.'"

    Built from the rule's own wording like unearth's (CR 702.84a), and run by
    the ordinary effect reader (`generic_effect`): the exile is a cost, so the
    power the counters are counted from is the exiled card's own."""
    from .targeting import profile_for_text

    abilities = scavenge_abilities(card.card, card, game)
    if index >= len(abilities):
        raise ValueError(
            f"{card.name} has no scavenge ability number {index} ({KeywordRule.SCAVENGE})"
        )
    ability = abilities[index]
    cost_text = f"{ability.cost}, Exile this card from your graveyard"
    cost = total_cost_for_phrase(cost_text, player)
    if cost is None:
        raise ValueError(
            f"{card.name}'s scavenge cost {ability.cost!r} could not be read, so it cannot be paid"
        )
    for component in cost.components:
        if component.kind is ComponentKind.EXILE and not component.cards:
            component.cards = [card]  # "Exile this card": the cost names itself.
    synthetic = _synthetic_ability(ability, cost_text=cost_text, effect=_SCAVENGE_EFFECT)
    profile = profile_for_text(synthetic.text)
    if profile.understood and profile.requirements:
        profile.check(list(targets or []), player, game, source=card)
    return statically_priced(
        KeywordActivation(
            card=card,
            player=player,
            keyword=ability.canonical,
            rule=str(KeywordRule.SCAVENGE),
            zone=Zone.GRAVEYARD,
            cost=cost.assign_payer(player),
            sorcery_only=True,
            ability=synthetic,
            targets=[TargetRef.coerce(target) for target in targets or []],
            generic_effect=True,
            game=game,
        )
    )


def off_zone_abilities(
    card: Card, state: CardState | None = None, game: Any = None
) -> list[OffZoneAbility]:
    """Every activated ability of `card` that functions off the battlefield,
    in one order: cycling first (CR 702.29a - "Cycling is an activated
    ability that functions only while the card with cycling is in a player's
    hand"), then each printed ability whose own cost or effect names another
    zone (CR 113.6j, CR 113.6m, read by `abilities._activated_ability_zone`).

    Cycling first, rather than in printed order across both families, so a
    card with cycling and nothing else keeps the index its own
    `cycling_activation`/`actions/cycle` caller already passes - every
    cycling printing in the pool is exactly that card.

    With the object's `state` and the `game`, what the battlefield does to the
    card is applied too: a static granting unearth to graveyard cards (Mishra,
    Tamer of Mak Fawa) adds it, and one stripping graveyard cards of their
    abilities (Yixlid Jailer) removes every graveyard-zone entry.
    """
    pool: list[OffZoneAbility] = []
    for index, kw_ability in enumerate(cycling_abilities(card)):
        typed = _typecycling_type(kw_ability.canonical)
        pool.append(
            OffZoneAbility(
                family="cycling",
                index=index,
                keyword=kw_ability.canonical,
                zone=Zone.HAND,
                rule=str(KeywordRule.TYPECYCLING if typed else KeywordRule.CYCLING),
                ability=_synthetic_ability(
                    kw_ability,
                    cost_text=f"{kw_ability.cost or ''}, Discard this card".strip(", "),
                    effect=(
                        f"Search your library for {with_indefinite_article(f'{typed} card')}, "
                        f"reveal it, and put it into your hand. Then shuffle."
                        if typed
                        else "Draw a card."
                    ),
                ),
            )
        )
    unearths = unearth_abilities(card) if state is None else unearth_abilities_of(game, state)
    for index, kw_ability in enumerate(unearths):
        pool.append(
            OffZoneAbility(
                family="unearth",
                index=index,
                keyword=kw_ability.canonical,
                zone=Zone.GRAVEYARD,
                rule=str(KeywordRule.UNEARTH),
                ability=_synthetic_ability(
                    kw_ability,
                    cost_text=kw_ability.cost or "",
                    effect=(
                        "Return this card from your graveyard to the battlefield. It gains "
                        "haste. Exile it at the beginning of the next end step."
                    ),
                ),
            )
        )
    for index, kw_ability in enumerate(transmute_abilities(card)):
        pool.append(
            OffZoneAbility(
                family="transmute",
                index=index,
                keyword=kw_ability.canonical,
                zone=Zone.HAND,
                rule=str(KeywordRule.TRANSMUTE),
                ability=_synthetic_ability(
                    kw_ability,
                    cost_text=f"{kw_ability.cost or ''}, Discard this card".strip(", "),
                    effect=(
                        "Search your library for a card with the same mana value as the "
                        "discarded card, reveal that card, and put it into your hand. Then "
                        "shuffle your library."
                    ),
                ),
            )
        )
    printed = [ability for ability in activated_abilities_of(card) if ability.zone is not None]
    for index, ability in enumerate(printed):
        assert ability.zone is not None and ability.zone_rule is not None
        pool.append(
            OffZoneAbility(
                family="printed",
                index=index,
                keyword=ability.ability_word,
                zone=ability.zone,
                rule=ability.zone_rule,
                ability=ability,
            )
        )
    # Last, so a granted scavenge appearing or going never renumbers the
    # abilities the card prints.
    for index, kw_ability in enumerate(scavenge_abilities(card, state, game)):
        pool.append(
            OffZoneAbility(
                family="scavenge",
                index=index,
                keyword=kw_ability.canonical,
                zone=Zone.GRAVEYARD,
                rule=str(KeywordRule.SCAVENGE),
                ability=_synthetic_ability(
                    kw_ability,
                    cost_text=f"{kw_ability.cost}, Exile this card from your graveyard",
                    effect=_SCAVENGE_EFFECT,
                ),
            )
        )
    # Embalm and eternalize (CR 702.128a, CR 702.129a), after scavenge so a
    # granted scavenge never renumbers them either.
    from .face_down_keywords import (
        TOKEN_COPY_KEYWORDS,
        token_copy_keyword_abilities,
        token_copy_keyword_effect_text,
    )

    for index, kw_ability in enumerate(token_copy_keyword_abilities(card)):
        pool.append(
            OffZoneAbility(
                family="token_copy",
                index=index,
                keyword=kw_ability.canonical,
                zone=Zone.GRAVEYARD,
                rule=TOKEN_COPY_KEYWORDS[kw_ability.canonical.lower()][0],
                ability=_synthetic_ability(
                    kw_ability,
                    cost_text=f"{kw_ability.cost}, Exile this card from your graveyard",
                    effect=token_copy_keyword_effect_text(kw_ability.canonical),
                ),
            )
        )
    if state is not None and state.zone is Zone.GRAVEYARD:
        from .graveyard_statics import graveyard_abilities_lost_by

        if graveyard_abilities_lost_by(game) is not None:
            # unearth entries were already filtered by `unearth_abilities_of`
            return [
                entry
                for entry in pool
                if entry.zone is not Zone.GRAVEYARD or entry.family == "unearth"
            ]
    return pool


def off_zone_activation(
    game: Any,
    card: CardState,
    player: str,
    index: int = 0,
    *,
    targets: list[Any] | None = None,
    sacrificing: list[CardState] | None = None,
    discarding: list[CardState] | None = None,
    exiling: list[CardState] | None = None,
) -> KeywordActivation:
    """Activate `off_zone_abilities(card.card)[index]`, whichever family it
    is in - the single entry point a caller holding an `ACTIVATE_OFF_ZONE`
    `Action` calls, so it never has to work out for itself whether the
    ability came from a CR 702.29a keyword or a printed CR 113.6j line.

    Refuses an index the pool does not have rather than defaulting to
    anything: a card with one off-zone ability has no number 1, and a card
    with none has no number 0.
    """
    pool = off_zone_abilities(effective_card(game, card), card, game)
    if index < 0 or index >= len(pool):
        raise ValueError(
            f"{card.name} has no activated ability functioning off the battlefield, "
            f"number {index} (it has {len(pool)})"
        )
    entry = pool[index]
    if entry.family == "cycling":
        if targets or sacrificing or discarding or exiling:
            # CR 702.29a spells the whole ability out - "[Cost], Discard this
            # card: Draw a card." - so there is nothing here for a target, a
            # sacrifice, or a second discard to be *for*. Refused rather than
            # quietly dropped, per this project's fail-closed rule for a
            # lookup that would otherwise default.
            raise ValueError(
                f"{card.name}'s {entry.keyword} ability takes no targets and no object costs "
                f"({KeywordRule.CYCLING})"
            )
        return cycling_activation(game, card, player, entry.index)
    if entry.family == "scavenge":
        if sacrificing or discarding or exiling:
            raise ValueError(
                f"{card.name}'s {entry.keyword} ability takes no object costs beyond exiling "
                f"itself ({entry.rule})"
            )
        return scavenge_activation(game, card, player, entry.index, targets=targets)
    if entry.family == "token_copy":
        if targets or sacrificing or discarding or exiling:
            # CR 702.128a / CR 702.129a spell the whole ability out: its only
            # object cost is exiling the card itself, and it targets nothing.
            raise ValueError(
                f"{card.name}'s {entry.keyword} ability takes no targets and no object costs "
                f"beyond exiling itself ({entry.rule})"
            )
        from .face_down_keywords import token_copy_keyword_activation

        return token_copy_keyword_activation(game, card, player, entry.index)
    if entry.family in ("unearth", "transmute"):
        if targets or sacrificing or discarding or exiling:
            # Same fail-closed refusal as cycling above: CR 702.84a and
            # CR 702.53a each spell their whole ability out too, so there is
            # nothing here for a target, a sacrifice, or a second discard to
            # be for.
            raise ValueError(
                f"{card.name}'s {entry.keyword} ability takes no targets and no object costs "
                f"({entry.rule})"
            )
        builder = unearth_activation if entry.family == "unearth" else transmute_activation
        return builder(game, card, player, entry.index)
    return off_battlefield_activation(
        game,
        card,
        player,
        entry.index,
        targets=targets,
        sacrificing=sacrificing,
        discarding=discarding,
        exiling=exiling,
    )


# --------------------------------------------------------------------------
# Ward (CR 702.21)
# --------------------------------------------------------------------------


class WardTrigger(EngineModel):
    """The optional payment on one ward trigger that is already on the stack.

    CR 702.21a: "Ward is a triggered ability. Ward [cost] means "Whenever this
    permanent becomes the target of a spell or ability an opponent controls,
    counter that spell or ability unless that player pays [cost].""

    **This is a view, not a second ability.** Ward being a *triggered* ability
    means its cost is paid as that ability resolves, so the thing that is paid
    has to be the thing that resolves. `Game.emit` already puts a real
    `AbilityOnStack` up when the permanent becomes a target (CR 601.2c,
    CR 603.2); `ward_triggers` finds that object and wraps it, `begin_paying`
    stores the payment on it (`AbilityOnStack.unless_payment`), and
    `_ward_effect` reads that payment back when the game resolves the ability.
    There is no second object to fall out of step with, and no way to pay a
    ward the game will not honour.

    Two things follow from ward being a trigger rather than a targeting
    restriction, and both are what the scenarios check: the spell is legally
    cast and sits on the stack while ward waits above it, and a spell that is
    countered by an unpaid ward is countered - it never resolves, and its
    controller gets no refund (CR 701.6a-b).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    ability: AbilityOnStack
    """The ward trigger this is a view onto, as it sits on the stack."""
    permanent: CardState
    """The permanent with ward that was targeted."""
    spell: Any
    """The spell or ability that targeted it (CR 113.9 allows either)."""
    cost: TotalCost
    payer: str
    """Whoever controls the targeting spell, and so whoever may pay."""
    rule: str = str(KeywordRule.WARD)
    game: Any = Field(default=None, exclude=True, repr=False)

    def begin_paying(self) -> CostPayment:
        """Open the payment for the ward cost. Paying it is optional.

        The payment is stored on the ability on the stack, which is what makes
        this a view rather than a duplicate.
        """
        if self.ability.unless_payment is None:
            self.ability.unless_payment = CostPayment.for_total(
                self.cost.assign_payer(self.payer), game=self.game, payer=self.payer
            )
        return self.ability.unless_payment

    @property
    def payment(self) -> CostPayment | None:
        return self.ability.unless_payment

    @property
    def paid(self) -> bool:
        return ward_was_paid(self.ability)


def ward_was_paid(ability: AbilityOnStack) -> bool:
    """Whether CR 702.21a's "unless that player pays [cost]" has been satisfied."""
    payment = ability.unless_payment
    return payment is not None and payment.step is CostStep.PAID


def ward_cost(card: Card, payer: str) -> TotalCost | None:
    """This printing's ward cost, or None if it has no ward (CR 702.21a)."""
    ability = _keyword(card, "ward")
    if ability is None:
        return None
    return _keyword_cost(ability, payer)


def ward_cost_of_trigger(
    ability: AbilityOnStack, permanent: CardState, payer: str
) -> TotalCost | None:
    """The cost of the one ward ability `ability` is (CR 702.21a), read off
    that ability rather than off the printing whenever it was *granted*.

    A granted ward ("becomes a 7/7 blue Giant creature with ward {3}", Hall of
    Storm Giants; "Permanents you control with counters on them have ward
    {1}", Innkeeper's Talent) is not on the permanent's printed card at all,
    so asking the card found no ward and the trigger countered the targeting
    spell without ever offering the payment. The granted line ("Ward {3}")
    is what `granted_keyword_triggered_abilities` expanded, and it is the
    ability's own `raw`; a printed ward's `raw` still carries its reminder
    text and is not a bare keyword line, so it falls back to the printing
    exactly as before - which is also where CR 702.21b's resolution-time X is
    read.
    """
    granted = granted_keyword_ability(ability.ability.raw) if ability.ability.raw else None
    if granted is not None and granted.canonical.lower() == "ward":
        return _keyword_cost(granted, payer)
    return ward_cost(permanent.card, payer)


def is_ward_trigger(item: Any) -> bool:
    """Whether a stack object is a ward ability (CR 702.21a)."""
    if not isinstance(item, AbilityOnStack):
        return False
    return getattr(item.ability, "keyword", None) == "ward"


def ward_triggers(game: Any, spell: Any) -> list[WardTrigger]:
    """The ward triggers on the stack that this spell or ability caused (CR 702.21a).

    Views onto the abilities the game has already stacked, one per trigger, so
    paying one pays the ability that will resolve. A spell that triggered no
    ward has none here - because it targeted a player or something that is not
    a permanent (CR 110.1), or because it targeted a permanent its own
    controller controls and CR 702.21a says "an opponent controls".

    The source is asked for the cost rather than the ability's own text,
    because CR 702.21b's X "is determined at the time the ability resolves, not
    locked in as the ability triggers". A source that can no longer be found at
    all (CR 113.7a lets it be destroyed while the ability waits) has no cost to
    read and so cannot be paid, and the ability counters as an unpaid ward.
    """
    payer = spell.controller or game.active_player.username
    views: list[WardTrigger] = []
    for item in game.stack:
        if not is_ward_trigger(item):
            continue
        if item.event is None or item.event.targeted_by != spell.id:
            continue
        permanent = item.source(game)
        if permanent is None:
            continue
        cost = ward_cost_of_trigger(item, permanent, payer)
        if cost is None:
            continue
        views.append(
            WardTrigger(
                ability=item,
                permanent=permanent,
                spell=spell,
                cost=cost,
                payer=payer,
                game=game,
            )
        )
    return views


# --------------------------------------------------------------------------
# Prowess (CR 702.108)
# --------------------------------------------------------------------------


def has_prowess(card: Card) -> bool:
    return any(keyword.lower() == "prowess" for keyword in card.keywords)


def prowess_triggers(game: Any, spell: CardState) -> list[CardState]:
    """The creatures whose prowess this cast triggered (CR 702.108a).

    "Prowess is a triggered ability. 'Prowess' means "Whenever you cast a
    noncreature spell, this creature gets +1/+1 until end of turn.""

    This answers the trigger half only, and is a *query*: which creatures this
    cast triggered. The trigger condition is a cast, complete once the spell is
    on the stack (CR 601.2i), so countering the spell afterwards does not undo
    it (CR 603.2g is about events that never happened; this one did).

    Nothing has to call this for prowess to work in a game. `machines/triggers`
    produces the same triggers from `_prowess_ability`'s expansion and puts them
    on the stack (CR 603.3), and `_prowess_effect` applies the +1/+1 when one
    resolves. This is the shape a test or a caller uses to ask the question
    directly.

    "Creature" is the computed board (CR 613.5), not `CardState.is_creature`'s
    printed read: a permanent animated into a creature only in layer 4
    (CR 613.1d) - a land by earthbend (CR 701.66a) - still owes prowess to
    whatever printed or granted it the ability, and the printed read would
    skip it forever. One `computed_board()` is hoisted for the whole
    `game.battlefield` scan rather than recomputed per candidate.
    """
    if Type.CREATURE in spell.types_as_a_spell(spell.card.types):
        return []
    controller = spell.controller or game.active_player.username
    board = game.computed_board()
    return [
        permanent
        for permanent in game.battlefield
        if board.of(permanent).is_creature
        and has_prowess(permanent.card)
        and game.controller_of(permanent).username == controller
    ]


#: What one prowess trigger does on resolution (CR 702.108a), applied by
#: `_prowess_effect` as a sublayer 7c continuous effect (CR 613.4c) that ends in
#: the cleanup step (CR 514.2, CR 703.4p).
prowess_bonus: tuple[int, int] = (1, 1)


# --------------------------------------------------------------------------
# "Exile cards from the top of your library until ..." - the shared process
# --------------------------------------------------------------------------


def exile_until(
    game: Any,
    owner: Any,
    stop: Callable[[CardState, list[CardState]], bool],
    *,
    source_name: str | None,
) -> list[CardState]:
    """Exile `owner`'s library from the top, one card at a time, until `stop`
    says the card just exiled ends the process - the first half every
    "exile cards from the top of your library until you exile ..." sentence
    shares: cascade's (CR 702.85a), discover's (CR 701.57a), Territorial
    Bruntar's "until you exile a nonland card" and Improvisation Capstone's
    "until you exile cards with total mana value 4 or greater".

    `stop(card, exiled)` sees the card just exiled and everything exiled so
    far (that card included, last), so a stop condition over one card and one
    over the running total are the same shape. Each card goes through CR
    406.2's door into the one shared exile zone, face up (CR 406.3), and so
    is revealed to every player on the way (CR 701.20a). A library that runs
    out first simply ends the process with everything exiled and no card
    having stopped it - nothing here raises for it.

    Returns every card exiled, in order.
    """
    exiled: list[CardState] = []
    while owner.library:
        state = owner.library[0]
        game.exile_cards([state])
        game.reveal(state, source=source_name)
        exiled.append(state)
        if stop(state, exiled):
            break
    return exiled


# --------------------------------------------------------------------------
# Cascade (CR 702.85)
# --------------------------------------------------------------------------


class CascadeResult(EngineModel):
    """What one cascade trigger exiled and what it found (CR 702.85a)."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    exiled: list[CardState] = Field(default_factory=list)
    """Everything exiled on the way, the hit included, in the order exiled."""
    hit: CardState | None = None
    """The nonland card with a lesser mana value, or None if the library ran out."""


def _is_nonland_below(state: CardState, bound: float) -> bool:
    """A nonland card whose mana value is less than `bound` - cascade's hit
    (CR 702.85a) and, with `bound` one past N, discover's (CR 701.57a)."""
    return not state.card.is_land and state.card.cmc < bound


def has_cascade(card: Card) -> bool:
    return any(keyword.lower() == "cascade" for keyword in card.keywords)


def cascade(game: Any, spell: CardState, seed: int | None = None) -> CascadeResult:
    """Perform a cascade trigger (CR 702.85a).

    "Cascade is a triggered ability that functions only while the spell with
    cascade is on the stack. 'Cascade' means "When you cast this spell, exile
    cards from the top of your library until you exile a nonland card whose
    mana value is less than this spell's mana value. You may cast that card
    without paying its mana cost if the resulting spell's mana value is less
    than this spell's mana value. Then put all cards exiled this way that
    weren't cast on the bottom of your library in a random order.""
    (verified against the current CR release; Shardless Agent's own printed
    reminder text still reads "that costs less" and has no "if the resulting
    spell's mana value..." clause - the rule, not the reminder, is what this
    reads). "If the resulting spell's mana value is less than this spell's
    mana value" is `mana_value_below`: an Adventure or split half whose own
    mana value is not less is never offered (CR 608.2d).

    This is the exiling half, the "you may cast it" half, and the bottoming
    half - all three, because a hit stranded in exile with no route back to
    any zone (never offered the choice, never bottomed when declined) is
    exactly the defect a real game hit: the trigger resolved, the exile pile
    showed the hit and nothing else, and there it stayed forever.

    **The choice** is CR 608.2d's own "the player announces these while
    applying the effect" - asked right here, synchronously, with
    `DecisionKind.MAY` (`docs/scenario-tests.md`'s "the same concession every
    optional trigger in this engine makes" is the *unscripted default*, not a
    dodge of the question: `default_answer` takes the affirmative whenever it
    is legal, so an unscripted scenario still gets offered the free cast and
    still takes it, exactly as it did before this question existed). Only
    `why_cannot_cast_restriction` (CR 611.1's flat prohibitions) gates whether
    "yes" is even a legal answer.

    - **"yes"** casts the hit right here, while this trigger resolves
      (`Game.cast_during_resolution`, CR 608.2g): "they do so by following the
      steps in rules 601.2a-i, except no player receives priority after it's
      cast. That spell becomes the topmost object on the stack". Timing
      restrictions do not apply, the caster announces the face, modes and
      targets mid-resolution, and a cast that turns out illegal (no legal
      target, CR 601.2c) leaves the hit among the cards that "weren't cast".
      Battle 8 (B8-01) found the old shape - a permission used later - let the
      opponent act first and put a sorcery hit under the stack's normal timing.
    - **"no"**, or "yes" refused because `affirmative_is_legal` was False -
      goes straight onto the bottom, in the very same random shuffle the
      misses get, exactly as CR 702.85a's single sentence says: nothing here
      leaves a hit dangling on the strength of a choice that was never really
      offered.

    The cards go to the bottom in a random order, which is a real shuffle of a
    known set rather than the library shuffle the engine does not model - not
    CR 701.24's own "shuffle", the same distinction `machines/effects.py`'s
    graveyard-bottom and hideaway clauses draw, so no shuffle trigger fires
    here either. `seed` lets a caller pin a literal value; left `None` (every
    production caller, `_cascade_effect`), the effective seed is `game.
    shuffle_seed`/`game.shuffles_performed` - the same reproducible-seed
    convention graveyard-bottom and hideaway already use, and this fell out
    of following until T10's replay invariant found it: a bare, unseeded
    `random.Random(None)` reads OS entropy, so two cascades exiling more than
    one card bottomed them in a different order every process, and a game
    replayed from its own decoded snapshot put them in an order the original
    never had.
    """

    with game._id_allocator_scope():  # noqa: SLF001
        controller = spell.controller or game.active_player.username
        owner = game.player(controller)
        threshold = spell.card.cmc

        result = CascadeResult()
        # A card bottomed below changes zones into a reordered library
        # (CR 400.7, CR 701.20d): nobody knows it any more.
        result.exiled = exile_until(
            game,
            owner,
            lambda state, _: _is_nonland_below(state, threshold),
            source_name=spell.name,
        )
        if result.exiled and _is_nonland_below(result.exiled[-1], threshold):
            result.hit = result.exiled[-1]

        cast_hit = False
        if result.hit is not None:
            castable = game.can_cast_during_resolution(
                result.hit, owner.username, mana_value_below=threshold
            )
            decision = Decision(
                kind=DecisionKind.MAY,
                player=owner.username,
                prompt=with_board_priced_cost(
                    game,
                    f"cast {result.hit.name} without paying its mana cost (cascade)",
                    result.hit,
                    owner.username,
                ),
                source=spell.name,
                source_id=source_id_of(spell),
                affirmative_is_legal=castable,
            )
            if game.ask(decision):
                # CR 608.2g: cast now, above the cascading spell, with no
                # priority in between; an illegal cast leaves it in exile.
                cast_hit = (
                    game.cast_during_resolution(
                        result.hit,
                        owner.username,
                        source_name=f"{spell.name}'s cascade",
                        rule="CR 702.85a",
                        mana_value_below=threshold,
                    )
                    is not None
                )

        bottomed = [state for state in result.exiled if not (cast_hit and state is result.hit)]
        effective_seed = (
            seed if seed is not None else f"{game.shuffle_seed}:{game.shuffles_performed}:cascade"
        )
        random.Random(effective_seed).shuffle(bottomed)  # noqa: S311
        if bottomed:
            game.shuffles_performed += 1
        for state in bottomed:
            game.exile.remove(state)
            owner.add(state, Zone.LIBRARY)  # the bottom of the library
        return result


# --------------------------------------------------------------------------
# Discover (CR 701.57a-c)
# --------------------------------------------------------------------------


class DiscoverResult(EngineModel):
    """What one "discover N" process exiled and found (CR 701.57a-c)."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    exiled: list[CardState] = Field(default_factory=list)
    """Everything exiled on the way, the hit included, in the order exiled."""
    hit: CardState | None = None
    """CR 701.57c's "discovered card": the final card exiled, if its mana
    value is `N` or less. `None` when the library ran out first."""


def discover(
    game: Any,
    controller: str,
    n: int,
    *,
    source_name: str | None = None,
    source_id: str | None = None,
    seed: int | None = None,
) -> DiscoverResult:
    """Perform "discover N" (CR 701.57a-c).

    CR 701.57a: "'Discover N' means 'Exile cards from the top of your library
    until you exile a nonland card with mana value N or less. You may cast
    that card without paying its mana cost if the resulting spell's mana
    value is less than or equal to N. If you don't cast it, put that card
    into your hand. Put the remaining exiled cards on the bottom of your
    library in a random order.'"

    Structurally `machines.keywords.cascade` (CR 702.85a) with `N` in place of
    the cascading spell's own mana value, and two differences that come
    straight from the two rules not saying the same thing:

    - **"N or less"** is not strict, unlike cascade's own "less than this
      spell's mana value" - a card costing exactly `N` is a hit. Read as
      `mana_value_below=n + 1` against `Game.can_cast_during_resolution`/
      `cast_during_resolution`, whose own bound is exclusive (`>=` is
      refused), so "at most N" becomes "strictly below N + 1" - safe because
      every real mana value is a whole number (CR 202.3).
    - **declining goes to the caster's hand, not the bottom.** Cascade's own
      "put the exiled cards on the bottom" covers a declined hit along with
      the misses; CR 701.57a instead gives the hit its own sentence - "If you
      don't cast it, put that card into your hand" - so only the cards that
      were never the hit at all (the misses this process passed over, plus
      the hit itself when it *was* cast and left through the stack instead)
      end up in `bottomed` below. A hit that stayed in exile because it was
      declined, or because `can_cast_during_resolution` found no legal way to
      cast it at all, is moved to hand by hand rather than folded into that
      list - the one place this function's shape has to diverge from
      cascade's own `bottomed = [state for state in result.exiled if not
      (cast_hit and state is result.hit)]` line.

    CR 701.57b: "A player has 'discovered' after the process described in
    rule 701.57a is complete, **even if some or all of those actions were
    impossible**" - an empty library still discovers, having exiled and found
    nothing; nothing here raises for that case, it simply returns a
    `DiscoverResult` with an empty `exiled` and a `None` hit.

    CR 107.3b: "If a player is casting a spell ... and an effect lets that
    player cast that spell while paying neither its mana cost nor an
    alternative cost that includes X, then the only legal choice for X is
    0" - `Game.cast_during_resolution` already bakes this in
    (`casting.determine_cost(x_value=0)`), the identical call cascade's own
    free cast goes through, so nothing extra is needed here for it to hold.

    `controller` is a username rather than the source object cascade itself
    takes, because unlike cascade - "a triggered ability that functions only
    while the spell with cascade is on the stack" - discover is a CR 701
    keyword *action* embedded in another ability's or spell's printed text
    (`machines/effects._parse_discover_clause`), so it has no fixed shape of
    source to read a controller off; the caller already knows who is
    discovering (CR 608.2c's "the controller of the spell or ability"; for a
    triggered or activated ability, `Game.controller_of`).

    `seed` lets a caller pin a literal value for a test; left `None` (every
    production caller), the effective seed is `game.shuffle_seed`/`game.
    shuffles_performed` - the same reproducible-seed convention cascade,
    graveyard-bottom and hideaway all already use, so a game replayed from its
    own decoded snapshot bottoms the misses in the same order the original
    game really had.
    """
    with game._id_allocator_scope():  # noqa: SLF001
        owner = game.player(controller)

        result = DiscoverResult()
        result.exiled = exile_until(
            game,
            owner,
            lambda state, _: _is_nonland_below(state, n + 1),
            source_name=source_name,
        )
        if result.exiled and _is_nonland_below(result.exiled[-1], n + 1):
            result.hit = result.exiled[-1]

        cast_hit = False
        if result.hit is not None:
            castable = game.can_cast_during_resolution(
                result.hit, controller, mana_value_below=n + 1
            )
            decision = Decision(
                kind=DecisionKind.MAY,
                player=controller,
                prompt=with_board_priced_cost(
                    game,
                    f"cast {result.hit.name} without paying its mana cost (discover {n})",
                    result.hit,
                    controller,
                ),
                source=source_name,
                source_id=source_id,
                affirmative_is_legal=castable,
            )
            if game.ask(decision):
                cast_hit = (
                    game.cast_during_resolution(
                        result.hit,
                        controller,
                        source_name=source_name or "discover",
                        rule="CR 701.57a",
                        mana_value_below=n + 1,
                    )
                    is not None
                )
            if not cast_hit:
                # CR 701.57a: "If you don't cast it, put that card into your
                # hand." - declined, or `can_cast_during_resolution` found no
                # legal way to cast it at all; either way it does not join
                # the misses on the bottom.
                game.exile.remove(result.hit)
                owner.add(result.hit, Zone.HAND)

        bottomed = [state for state in result.exiled if state is not result.hit]
        effective_seed = (
            seed if seed is not None else f"{game.shuffle_seed}:{game.shuffles_performed}:discover"
        )
        random.Random(effective_seed).shuffle(bottomed)  # noqa: S311
        if bottomed:
            game.shuffles_performed += 1
        for state in bottomed:
            game.exile.remove(state)
            owner.add(state, Zone.LIBRARY)  # the bottom of the library
        return result


# --------------------------------------------------------------------------
# Persist (CR 702.79)
# --------------------------------------------------------------------------


def has_persist(card: Card) -> bool:
    return any(keyword.lower() == "persist" for keyword in card.keywords)


def persist_return(
    game: Any, card: CardState, *, keyword_confirmed: bool = False
) -> CardState | None:
    """Perform a persist trigger (CR 702.79a).

    "Persist is a triggered ability. 'Persist' means "When this permanent is put
    into a graveyard from the battlefield, if it had no -1/-1 counters on it,
    return it to the battlefield under its owner's control with a -1/-1 counter
    on it.""

    The intervening *if* is about the permanent as it last existed, and CR 122.2
    destroyed its counters on the way out - so `last_known_counters` is what is
    read (CR 704.8, CR 603.10a). Returns the permanent, or None when the *if*
    was false, which is what stops a persisted creature persisting forever.

    `keyword_confirmed=True` is `_persist_effect`'s own promise that the
    ability resolving here is already a persist ability (CR 400.7b: a
    *granted* persist - Eirdu, Carrier of Dawn's static, Rhys, the
    Evermore's temporary "gains persist until end of turn" - "functions" the
    identical way a printed one does). `has_persist(card.card)` only ever
    reads Scryfall's own printed `keywords`, never a layer 6 grant computed
    on the board (`CardState.computed_characteristics`, gone the moment the
    card left for the graveyard, CR 400.7), so it would wrongly raise for
    exactly the granted case this parameter is for. A direct call with
    neither the keyword nor this promise keeps the original guard - the same
    "prove it before acting on it" check every other caller of this function
    still gets.
    """
    if not keyword_confirmed and not has_persist(card.card):
        raise ValueError(f"{card.name} has no persist ability ({KeywordRule.PERSIST})")
    if card.zone is not Zone.GRAVEYARD:
        raise ValueError(f"{card.name} is in the {card.zone.value}, not a graveyard")
    if card.last_known_counters[Counter.MINUS_ONE]:
        return None

    owner = game.find_owner(card) or game.player(card.controller or game.active_player.username)
    if card in owner.cards_in(Zone.GRAVEYARD):
        owner.cards_in(Zone.GRAVEYARD).remove(card)
    game.put_onto_battlefield(card, owner.username)
    game.add_counters(card, Counter.MINUS_ONE, 1)
    return card


def undying_return(game: Any, card: CardState) -> CardState | None:
    """Perform an undying trigger (CR 702.93a): return the card from its
    owner's graveyard under its owner's control with a +1/+1 counter on it.

    The counter is given as it enters (CR 122.6: "an object that's given
    counters as it enters the battlefield"), so the returned creature is never
    on the battlefield without it - an "enters" trigger that reads its power
    sees the counter. The intervening *if* was already asked twice (CR 603.4,
    CR 608.2a); this reads `last_known_counters` once more only so a direct
    call answers the same question. None when it does not return: the card
    is no longer in a graveyard (CR 603.6 - it looks only where it went), or
    it is a token, which ceased to exist as it left (CR 111.7).
    """
    if card.zone is not Zone.GRAVEYARD or card.token:
        return None
    if card.last_known_counters[Counter.PLUS_ONE]:
        return None
    owner = game.find_owner(card) or game.player(card.controller or game.active_player.username)
    if card in owner.cards_in(Zone.GRAVEYARD):
        owner.cards_in(Zone.GRAVEYARD).remove(card)
    game.put_onto_battlefield(card, owner.username, counters={Counter.PLUS_ONE: 1})
    return card


# --------------------------------------------------------------------------
# Rebound (CR 702.88)
# --------------------------------------------------------------------------


def has_suspend(card: Card) -> bool:
    """CR 702.62b's middle clause: whether this card "has suspend".

    Read off Scryfall's own `keywords` list for the same reason `has_rebound`
    is - Lotus Bloom's oracle text contains "At the beginning of your upkeep,
    remove a time counter" only inside the reminder text in parentheses, which
    is not an ability (CR 207.2), so a substring search of the text would find
    the keyword on exactly the cards a `keywords` read already finds it on and
    on some it should not.
    """
    return any(keyword.lower() == "suspend" for keyword in card.keywords)


def has_rebound(card: Card) -> bool:
    """CR 702.88a: "Rebound appears on some instants and sorceries." Read the
    same way `has_persist` reads a permanent keyword - off Scryfall's own
    `keywords` list rather than a substring search of the oracle text, so a
    card that merely *mentions* the word in reminder text elsewhere is never
    mistaken for one that prints the ability.
    """
    return any(keyword.lower() == "rebound" for keyword in card.keywords)


def has_rebound_now(card_state: CardState) -> bool:
    """Whether `card_state` has rebound *right now*, printed (`has_rebound`)
    or granted by another card's effect (`CardState.granted_rebound`, CR
    614.12: a granted static ability "functions" the same as a printed one
    for as long as it applies) - Ojer Pakpatiq, Deepest Epoch's own "Whenever
    you cast an instant spell from your hand, it gains rebound." The two
    call sites that used to ask `has_rebound(spell.card)` alone
    (`machines/replacement._stack_replacements`'s exile-instead-of-graveyard
    swap, `Game._create_rebound_delayed_trigger`'s own guard) both ask this
    instead, so a granted rebound reaches the same two effects a printed one
    does."""
    if has_rebound(card_state.card) or card_state.granted_rebound:
        return True
    game = getattr(card_state, "_board_source", None)
    if game is None or card_state.zone is not Zone.STACK:
        return False
    # CR 702.88a: "Instant and sorcery spells you control have rebound" -
    # a static ability read while the spell is on the stack (CR 611.3a).
    from .spell_grants import granted_lines_of_stack_spell

    return "Rebound" in granted_lines_of_stack_spell(game, card_state)


# --------------------------------------------------------------------------
# Paradigm (CR 702.192)
# --------------------------------------------------------------------------


def has_paradigm(card: Card) -> bool:
    """CR 702.192a: "Paradigm represents two spell abilities ... 'Exile this
    spell.'" Read off Scryfall's own `keywords` list, the same way `has_
    rebound` is - a card whose reminder text merely mentions the word is
    never mistaken for one that prints the ability.
    """
    return any(keyword.lower() == "paradigm" for keyword in card.keywords)


# --------------------------------------------------------------------------
# Dredge (CR 702.52)
# --------------------------------------------------------------------------


def dredge_count(card: Card) -> int | None:
    """The N in `Dredge N`, or None if the card has no dredge (CR 702.52a)."""
    ability = _keyword(card, "dredge")
    if ability is None:
        return None
    if ability.count is not None:
        return ability.count
    digits = re.search(r"\d+", ability.cost or ability.parameter or "")
    return int(digits.group()) if digits else None


def why_cannot_dredge(game: Any, card: CardState, player: str) -> str | None:
    """Why dredge cannot replace a draw right now, or None (CR 702.52a-b).

    "Dredge is a static ability that functions only while the card with dredge
    is in a player's graveyard. 'Dredge N' means "As long as you have at least N
    cards in your library, if you would draw a card, you may mill N cards
    instead. If you do, return this card from your graveyard to your hand.""
    CR 702.52b: "A player with fewer cards in their library than the number
    required by a dredge ability can't mill any of them this way."
    """
    count = dredge_count(effective_card(game, card))
    if count is None:
        return f"{card.name} has no dredge ability ({KeywordRule.DREDGE})"
    if card.zone is not Zone.GRAVEYARD:
        return (
            f"{card.name}'s dredge ability functions in a graveyard, but it is in "
            f"the {card.zone.value} ({KeywordRule.DREDGE})"
        )
    from .graveyard_statics import graveyard_abilities_lost_by

    jailer = graveyard_abilities_lost_by(game)
    if jailer is not None:
        return (
            f"{jailer} makes cards in graveyards lose all abilities, so {card.name} "
            f"has no dredge ({KeywordRule.DREDGE})"
        )
    library = len(game.player(player).library)
    if library < count:
        return (
            f"{player} has {library} cards in their library and dredge {count} needs "
            f"{count} (CR 702.52b)"
        )
    return None


def dredge(game: Any, card: CardState, player: str) -> list[CardState]:
    """Replace a draw with dredge, returning the cards milled (CR 702.52a).

    A replacement effect on a draw (CR 614.11a), and the draw event carries only
    a number - `Game.draw_cards` has nowhere to put an effect that replaces the
    draw with something that is not a draw. So this is the replacement performed
    by hand, the way a scenario performs the combat turn-based actions: call it
    *instead of* drawing.
    """
    with game._id_allocator_scope():  # noqa: SLF001
        refusal = why_cannot_dredge(game, card, player)
        if refusal is not None:
            raise ValueError(refusal)
        count = dredge_count(effective_card(game, card))
        assert count is not None

        owner = game.player(player)
        milled = list(owner.library[:count])
        for state in milled:
            # CR 701.17a, through `Game.put_into_graveyard` so a graveyard
            # replacement (CR 614.1a) sees each milled card, and the CR
            # 700.11/CR 400.6 arrival ledger is fed there.
            game.put_into_graveyard(state)
        owner.cards_in(Zone.GRAVEYARD).remove(card)
        owner.add(card, Zone.HAND)
        card.move_to(Zone.HAND)
        return milled


# --------------------------------------------------------------------------
# Morph (CR 702.37) and disguise (CR 702.168)
# --------------------------------------------------------------------------


def morph_ability(card: Card) -> KeywordAbility | None:
    """This card's morph or disguise ability, or None (CR 702.37a, 702.168a).

    CR 702.37b: "Megamorph is a variant of the morph ability. ... A megamorph
    cost is a morph cost", so megamorph counts here too. Disguise is a separate
    keyword with the same shape and a different set of listed characteristics.
    """
    return _keyword(card, "morph", "megamorph", "disguise")


def face_down_characteristics(card: Card) -> FaceDownCharacteristics | None:
    """What this card becomes when it is cast face down, or None (CR 702.37c).

    CR 702.37c: "It becomes a 2/2 face-down creature card with no text, no name,
    no subtypes, and no mana cost. ... These values are the copiable values of
    that object's characteristics."

    CR 702.168b lists disguise's set, which is the same plus one keyword: "a 2/2
    face-down creature card with **ward {2}**, no name, no subtypes, and no mana
    cost". Note it does *not* say "no text" - the ward is the text.
    """
    ability = morph_ability(card)
    if ability is None:
        return None
    if ability.canonical.lower() == "disguise":
        return FaceDownCharacteristics(
            keywords=("Ward",),
            oracle_text="Ward {2}",
            rule=str(KeywordRule.DISGUISE),
        )
    return FaceDownCharacteristics(rule=str(KeywordRule.MORPH))


#: CR 702.37c and CR 702.168b both charge {3}, whatever the *morph cost* on the
#: card says. The printed cost is what CR 702.37e's special action pays to turn
#: the permanent face up, and is not what it costs to cast it face down.
FACE_DOWN_CAST_COST = "{3}"


def why_cannot_turn_up_manifested(permanent: CardState) -> str | None:
    """Why CR 701.40b's own turn-up procedure is unavailable for this
    manifested permanent right now, or None.

    "Any time you have priority, you may turn a manifested permanent you
    control face up. ... To do this, show all players that the card
    representing that permanent is a creature card and what that card's mana
    cost is, pay that cost, then turn the permanent face up. **(If the card
    representing that permanent isn't a creature card or it doesn't have a
    mana cost, it can't be turned face up this way.)**" CR 701.58b prints the
    identical parenthetical for a cloaked permanent - the reason this reads
    `permanent.manifested` rather than a name check, so a future cloak
    implementation only has to set the same flag to reach here too.

    Never called on an object that is not manifested at all - that is
    `why_cannot_turn_face_up`'s own job, which only reaches this once the
    morph/disguise path has already come up empty.
    """
    if Type.CREATURE not in permanent.card.types:
        return (
            f"{permanent.card.name} is not a creature card, so the manifested permanent "
            f"cannot be turned face up this way (CR 701.40b)"
        )
    if not _manifest_front_mana_cost(permanent.card):
        return (
            f"{permanent.card.name} has no mana cost, so the manifested permanent cannot "
            f"be turned face up this way (CR 701.40b)"
        )
    return None


def _manifest_front_mana_cost(card: Card) -> str | None:
    """The mana cost CR 701.40b's/701.58b's own turn-up procedure pays -
    "the card representing that permanent[[']s] ... mana cost", read off the
    front face (CR 712.8a) for a transform or modal DFC, whose top-level
    `mana_cost` Scryfall leaves blank in favour of `card_faces`. A split or
    Adventure card keeps its combined `mana_cost` at the top level and never
    reaches the fallback.
    """
    if card.mana_cost:
        return card.mana_cost
    if card.card_faces:
        return card.card_faces[0].mana_cost or None
    return None


def manifest_turn_up_cost(permanent: CardState) -> TotalCost | None:
    """The mana cost CR 701.40b's turn-up procedure pays for a manifested
    permanent, or None when it cannot be turned up this way at all."""
    if why_cannot_turn_up_manifested(permanent) is not None:
        return None
    mana = ManaCost.try_parse(_manifest_front_mana_cost(permanent.card) or "")
    return None if mana is None else TotalCost.of(mana)


def why_cannot_turn_face_up(permanent: CardState, *, procedure: str | None = None) -> str | None:
    """Why every special action this engine turns a face-down permanent face
    up with is unavailable right now, or None: CR 702.37e's morph/megamorph
    procedure, CR 702.168d's disguise procedure (both read off the card's own
    `morph_ability`, which covers all three - see that function's docstring),
    and CR 701.40b's manifest procedure (CR 701.58b's cloak procedure once
    that keyword action exists - `docs/engine-coverage.md`).

    "Any time you have priority, you may turn a face-down permanent you control
    with a morph ability face up. This is a special action; it doesn't use the
    stack (see rule 116). To do this, show all players what the permanent's
    morph cost would be if it were face up, pay that cost, then turn the
    permanent face up. **(If the permanent wouldn't have a morph cost if it were
    face up, it can't be turned face up this way.)**"

    That last clause is why the check is against the card and not against the
    face-down object: the object has no text at all (CR 708.2), so the morph
    cost has to be read off the printing it is hiding.

    CR 701.40c-d: a card that is both manifested *and* has morph or disguise
    has both procedures available, at potentially different costs, and its
    controller picks which one to use. `procedure` is that pick - `"morph"`
    for CR 702.37e's/CR 702.168d's cost, `"manifest"` for CR 701.40b's own
    mana cost - checked instead of the default preference order below.
    `None`, every caller from before this choice existed, keeps that order:
    the morph/disguise cost when the card has one, manifest's only when it
    does not - `turn_face_up_cost`'s own docstring says the same.
    """
    if permanent.zone is not Zone.BATTLEFIELD:
        return (
            f"{permanent.card.name} is in the {permanent.zone.value}; only a permanent "
            f"can be turned face up ({KeywordRule.MORPH})"
        )
    if permanent.face_up:
        return f"{permanent.card.name} is already face up"
    ability = morph_ability(permanent.card)
    if procedure == "manifest":
        if not permanent.manifested:
            return (
                f"{permanent.card.name} is not manifested, so it has no manifest turn-up "
                f"procedure (CR 701.40b)"
            )
        return why_cannot_turn_up_manifested(permanent)
    if procedure == "morph":
        if ability is not None and ability.cost:
            return None
        return (
            f"{permanent.card.name} would have no morph cost if it were face up, so it "
            f"cannot be turned face up this way (CR 702.37e)"
        )
    if ability is not None and ability.cost:
        return None
    if permanent.manifested:
        return why_cannot_turn_up_manifested(permanent)
    return (
        f"{permanent.card.name} would have no morph cost if it were face up, so it "
        f"cannot be turned face up this way (CR 702.37e)"
    )


#: "As long as enchanted creature is face down, it can't be turned face up."
#: (Unable to Scream) - the ban an Aura or Equipment puts on what it is
#: attached to.
_ATTACHED_FACE_DOWN_CANT_TURN_UP_RE = re.compile(
    r"^as long as (?P<attachment>enchanted|equipped) (?:creature|permanent) is face down, "
    r"it can't be turned face up\.?$",
    re.IGNORECASE,
)

#: "Permanents your opponents control can't be turned face up during your
#: turn." (Karlov Watchdog) - a board-wide ban, scoped by controller and,
#: optionally, by whose turn it is.
_GROUP_CANT_TURN_UP_RE = re.compile(
    r"^(?P<subject>permanents|creatures)(?P<scope> your opponents control| you control)? "
    r"can't be turned face up(?P<your_turn> during your turn)?\.?$",
    re.IGNORECASE,
)


def is_turn_face_up_ban_line(text: str) -> bool:
    """Whether a static line is one of the two ban shapes
    `turn_face_up_ban` enforces - what `support.py` counts handled."""
    line = text.strip()
    return bool(
        _ATTACHED_FACE_DOWN_CANT_TURN_UP_RE.fullmatch(line)
        or _GROUP_CANT_TURN_UP_RE.fullmatch(line)
    )


def turn_face_up_ban(game: Any, permanent: CardState) -> str | None:
    """Which permanent's static ability forbids turning this face-down
    permanent face up right now, or None.

    CR 702.37e's special action - and any other way of turning a permanent
    face up - is what these abilities stop; the face-down permanent itself has
    no text (CR 708.2), so the ban is read off the battlefield's computed
    abilities (CR 613.5), re-asked every time (CR 611.3a): the Aura attached to
    it (Unable to Scream), or a permanent whose controller's opponents control
    it, during that controller's turn (Karlov Watchdog)."""
    if permanent.face_up or permanent.zone is not Zone.BATTLEFIELD:
        return None
    board = game.computed_board()
    active = game.turn.active_player if game.turn is not None else None
    subject_types = board.of(permanent).types
    for source in game.battlefield:
        chars = board.of(source)
        for line in chars.abilities:
            text = line.strip()
            if _ATTACHED_FACE_DOWN_CANT_TURN_UP_RE.fullmatch(text):
                if source.attached_to == permanent.id:
                    return f'{source.name} says "{text}", so it can\'t be turned face up'
                continue
            match = _GROUP_CANT_TURN_UP_RE.fullmatch(text)
            if match is None:
                continue
            owner = chars.controller
            if match["subject"].lower() == "creatures" and Type.CREATURE not in subject_types:
                continue
            scope = (match["scope"] or "").strip().lower()
            if scope == "your opponents control" and permanent.controller == owner:
                continue
            if scope == "you control" and permanent.controller != owner:
                continue
            if match["your_turn"] and active != owner:
                continue
            return f'{source.name} says "{text}", so it can\'t be turned face up'
    return None


def turn_face_up_cost(
    permanent: CardState, player: str, *, procedure: str | None = None, game: Any = None
) -> TotalCost | None:
    """The cost this permanent pays to be turned face up right now, or None.

    The morph/megamorph/disguise cost (CR 702.37e, CR 702.168d) when the card
    has one - `morph_ability` reads all three alike. Otherwise, for a
    manifested permanent (CR 701.40b) or, once printed in this pool, a cloaked
    one (CR 701.58b), the card's own mana cost.

    CR 701.40c-d: a card that is manifested *and* has morph or disguise may
    use either procedure, at whatever each one's cost comes to. `procedure`
    (`"morph"` or `"manifest"`) picks one explicitly; `None`, every caller
    from before this choice existed, keeps the old preference - the morph/
    disguise cost when the card has one, manifest's own mana cost otherwise.
    """
    ability = morph_ability(permanent.card)
    morph_cost = _keyword_cost(ability, player) if ability is not None else None
    if morph_cost is not None and game is not None and ability is not None:
        # CR 601.2f via CR 702.168d: the card's own "This cost is reduced by
        # {N} for each ..." sentence, counted when the cost is determined.
        from .face_down_keywords import face_up_cost_reduction

        reduction = face_up_cost_reduction(game, permanent, player)
        if reduction.symbols:
            morph_cost = morph_cost.model_copy(update={"mana": morph_cost.mana.minus(reduction)})
    manifest_cost = manifest_turn_up_cost(permanent) if permanent.manifested else None
    if procedure == "manifest":
        return manifest_cost
    if procedure == "morph":
        return morph_cost
    return morph_cost if morph_cost is not None else manifest_cost


# --------------------------------------------------------------------------
# Madness (CR 702.35)
# --------------------------------------------------------------------------


def madness_cost(card: Card, payer: str = "") -> TotalCost | None:
    """This card's madness cost, or None if it has no madness (CR 702.35a)."""
    ability = _keyword(card, "madness")
    if ability is None:
        return None
    return _keyword_cost(ability, payer)


def has_madness(card: Card) -> bool:
    return _keyword(card, "madness") is not None


def madness_replaces_discard(card: CardState) -> bool:
    """Whether discarding this card exiles it instead (CR 702.35a).

    "The first is a static ability that functions while the card with madness is
    in a player's hand. ... 'If a player would discard this card, that player
    discards it, but exiles it instead of putting it into their graveyard'."

    Two things the wording settles. It is the card being *discarded* that
    matters, not who discarded it or why - a discard paid as a cost is still a
    discard. And the card really is discarded: CR 702.35a says "that player
    discards it", so anything that watches for a discard sees one, and only the
    destination changes.
    """
    return card.zone is Zone.HAND and has_madness(card.card)


def discard(game: Any, card: CardState, player: str) -> CardState:
    """Discard one card, madness included (CR 701.9a, CR 702.35a).

    CR 701.9a: "To discard a card, move it from its owner's hand to that
    player's graveyard." Madness replaces where it lands and nothing else: "that
    player discards it, **but exiles it instead** of putting it into their
    graveyard". So the card is still discarded - anything watching a discard
    sees one - and the CR 702.35a trigger fires off the exiling.

    This is the whole discard for every caller that has a game to hand.
    `Player.discard` has no game and so cannot replace anything; see
    `docs/engine-coverage.md` for the hook that would send it here.
    """
    with game._id_allocator_scope():  # noqa: SLF001
        owner = game.player(player)
        if card not in owner.cards_in(Zone.HAND):
            raise ValueError(f"{card.name} is not in {player}'s hand (CR 701.9a)")

        turn = getattr(getattr(game, "turn", None), "turn_number", None)

        # CR 702.35a is a static ability of the card in hand: printed on it, or
        # granted by a static ability that gives it madness (Falkenrath
        # Gorger's "has madness. The madness cost is equal to its mana cost.").
        # The grant is read while the card is still in hand, and rides on the
        # exiled card so the trigger and the cast option find it there.
        from .spell_grants import granted_zone_keyword_lines

        granted_madness = tuple(granted_zone_keyword_lines(game, card, "madness"))
        if not (madness_replaces_discard(card) or granted_madness):
            # CR 614.1a: through `Game.put_into_graveyard`, so a graveyard
            # replacement (Rest in Peace's "from anywhere", Leyline of the
            # Void's) still gets its look at a discarded card; that also feeds
            # the CR 700.11/CR 400.6 arrival ledger.
            game.put_into_graveyard(card, discarded=True)
            if card.zone is not Zone.GRAVEYARD:
                return card
            # CR 702.187b's "as long as you discarded this card this turn", recorded
            # on the card the far side of the move because that is the object the
            # clause is about. Not a count - `Game.cards_discarded_this_turn` is
            # that, and it cannot say *which* card, which is the only thing mayhem
            # asks. `CardState.move_to` clears it again the moment the card leaves
            # the graveyard (CR 400.7).
            card.discarded_by = player
            card.discarded_on_turn = turn
            return card

        owner.cards_in(Zone.HAND).remove(card)
        card.move_to(Zone.EXILE)
        card.exile_annotation = madness_annotation(card, turn)
        if not has_madness(card.card):
            card.granted_ability_texts = granted_madness[:1]
        game.exile.append(card)

        # CR 702.35a's second ability: "When this card is exiled this way ...".
        # Asked of the exiled card directly rather than through `Game.emit`, which
        # asks the battlefield and the stack: madness is a triggered ability that
        # functions in *exile*, so the only object that could ever trigger it is the
        # card that just got there. CR 603.3 then puts it on the stack with
        # everything else, the next time a player would receive priority.
        event = GameEvent(
            event=TriggerEvent.EXILED,
            subject_id=card.id,
            subject_name=card.name,
            subject_controller=card.controller_or_owner,
            subject_card=card.card,
            player=card.owner or player,
        )
        game.pending_triggers.extend(triggers_for(game, event, [card]))
        return card


def madness_annotation(card: CardState, turn: int | None = None) -> ExileAnnotation:
    """The exile pile a madness discard lands in (CR 406.4, CR 702.35a).

    Its own pile, because the triggered ability of CR 702.35a is about "this
    card ... exiled this way" and nothing else in exile qualifies. The owner is
    recorded because CR 702.35a says **its owner** may cast it, which need not
    be whoever discarded it.
    """
    return ExileAnnotation(
        marker=ExileMarker.MADNESS,
        owner=card.controller_or_owner,
        turn_exiled=turn,
    )


# --------------------------------------------------------------------------
# Enchant (CR 702.5)
# --------------------------------------------------------------------------


def enchant_restrictions(card: Card, face_name: str | None = None) -> list[str]:
    """What every `Enchant [object or player]` line on this card demands.

    CR 702.5a: "Enchant is a static ability, written 'Enchant [object or
    player].' The enchant ability restricts what an Aura spell can target and
    what an Aura can enchant."

    CR 702.5c is why this is a list and not one string: "If an Aura has multiple
    instances of enchant, **all of them apply**. The Aura's target must follow
    the restrictions from all the instances of enchant."

    Only the face that is up counts (CR 712.8d/712.8e): Radiant Grace's front
    "Enchant creature" and its back face Radiant Restraints' "Enchant player"
    are never in force together. `face_name` is the up face (`CardState.
    up_face_name`); `None` reads the front face, the face a card has in every
    zone but the battlefield.
    """
    faces = getattr(card, "card_faces", None) or []
    wanted = face_name or (faces[0].name if faces else None)
    return [
        (ability.parameter or "").strip()
        for ability in keyword_abilities(card)
        if ability.canonical.lower() == "enchant"
        and (ability.parameter or "").strip()
        and (wanted is None or not ability.face or ability.face == wanted)
    ]


def why_cannot_enchant(aura: CardState, target: Any, caster: str, game: Any = None) -> str | None:
    """Why this Aura may not target or be attached to this thing, or None.

    CR 702.5a restricts both, in one sentence, which is why one function answers
    for the announcement (CR 601.2c) and for the attachment (CR 701.3a).

    CR 702.5d is the half that is easy to get backwards: "Auras that can enchant
    a player can target and be attached to players. Such Auras **can't target
    permanents and can't be attached to permanents**." So the restriction is
    exclusive in both directions, not a floor.

    The restriction text is read by `machines/targeting.py` as though it were a
    target phrase - "Enchant creature" asks the same question "target creature"
    does - so there is no second parser here. A restriction that parser cannot
    read is not checked, and says so.
    """
    from .targeting import profile_for_text

    restrictions = enchant_restrictions(aura.card, aura.up_face_name)
    if not restrictions and aura.bestowed:
        # CR 702.103b: "As a spell cast bestowed is put onto the stack, it
        # becomes an Aura enchantment and gains enchant creature." That grant
        # carries no printed line of its own - `enchant_restrictions` only
        # ever reads the card's own text - the identical gap `machines/
        # casting.Casting._with_bestowed_target` already closes for CR
        # 702.5a's other half (the announcement's own target requirement).
        # Left unclosed here, CR 704.5m's own state-based check read a
        # bestowed permanent as having no enchant ability at all the instant
        # after `Game.enter_the_battlefield` legally attached it, and put it
        # straight back into its owner's graveyard - Detective's Phoenix
        # never survived its own bestow, hardcast or cast from the graveyard.
        restrictions = ["creature"]
    if not restrictions:
        return f"{aura.name} has no enchant ability, so it cannot be attached (CR 702.5a)"

    for restriction in restrictions:
        profile = profile_for_text(f"target {restriction}")
        if not profile.understood or not profile.requirements:
            continue  # unread, so unchecked - see docs/engine-coverage.md
        refusal = profile.requirements[0].rejects(target, caster, game)
        if refusal is not None:
            return f"{aura.name} says 'Enchant {restriction}': {refusal} (CR 702.5a)"
    from .layers.attached_grants import cant_be_enchanted_by_other_auras_refusal

    return cant_be_enchanted_by_other_auras_refusal(game, aura, target)


def aura_state_based_actions(game: Any) -> list[CardState]:
    """CR 704.5m: an Aura attached to something illegal goes to its graveyard.

    "If an Aura is attached to an illegal object or player, or is not attached
    to an object or player, that Aura is put into its owner's graveyard." The
    opposite of an Equipment (CR 704.5n), which merely becomes unattached, and
    the reason the two need separate functions.

    Dispatched by `Game.check_state_based_actions` (see the call there for the
    CR 704.5m citation) - this docstring used to say otherwise, which was wrong
    by the time it was read.

    `permanent.attached_to` only narrows to a card (see its own docstring), so
    a player attachment - an "Enchant player" Aura, Curse of Exhaustion in the
    test pool - is read off `attachment` directly here rather than through that
    property, which would otherwise read every Aura on a player as attached to
    nothing and bin it every check.

    The "Aura" subtype check is read off the computed board (CR 613.5) through
    `_computed_types_and_subtypes` - the same helper `equipment_state_based_
    actions` uses for the same reason - rather than off `permanent.subtypes`'s
    printed line, with one `computed_board()` hoisted for the whole battlefield
    loop.
    """
    doomed: list[CardState] = []
    board = game.computed_board()
    for permanent in list(game.battlefield):
        _types, subtypes = _computed_types_and_subtypes(game, permanent, board)
        if "Aura" not in subtypes:
            continue
        attachment = permanent.attachment
        if attachment is None:
            if permanent.bestowed:
                # CR 702.103f's own unattached half: "If a bestowed Aura
                # becomes unattached, it ceases to be bestowed" - already
                # true the moment `attachment` reads None, so there is
                # nothing left to clear, and CR 702.103f's "This is an
                # exception to rule 704.5m" means this permanent (a creature
                # again, per `CardState.types`/`.subtypes` the instant
                # `bestowed` is false) is never doomed for it.
                permanent.unattach()
                continue
            doomed.append(permanent)
            continue
        if attachment.is_player:
            username = attachment.username
            host = game.player(username) if username and game.is_in_game(username) else None
        else:
            host = game.find_by_id(attachment.card_id)
        illegal = host is None or (
            isinstance(host, CardState) and host.zone is not Zone.BATTLEFIELD
        )
        if not illegal:
            controller = game.controller_of(permanent)
            illegal = (
                why_cannot_enchant(permanent, host, controller.username if controller else "", game)
                is not None
            )
        if not illegal:
            # CR 702.16c: "Such Auras attached to the permanent or player with
            # protection will be put into their owners' graveyards as a
            # state-based action" - CR 303.4c's "other applicable effects".
            illegal = _protection_refusal_for_attachment(game, permanent, host) is not None
        if illegal and permanent.bestowed:
            # CR 702.103f: "If a bestowed Aura is attached to an illegal
            # object or player, it becomes unattached and ceases to be
            # bestowed. This is an exception to rule 704.5m." - an ordinary
            # Aura in the same spot goes to its owner's graveyard below;
            # a bestowed one instead reverts to the creature (or other
            # permanent type) its own printing gives it once `unattach`
            # clears `bestowed`, and is never added to `doomed` for it.
            # Detective's Phoenix's own graveyard-cast bestow is the proof:
            # its enchanted creature dying used to send the Phoenix straight
            # to the graveyard by the ordinary 704.5m route, instead of
            # leaving it on the battlefield as the 2/2 flyer it prints.
            permanent.unattach()
            continue
        if illegal:
            doomed.append(permanent)
    return doomed


# --------------------------------------------------------------------------
# Indestructible (CR 702.12)
# --------------------------------------------------------------------------


def is_indestructible(permanent: CardState, game: Any = None) -> bool:
    """Whether this permanent has indestructible right now (CR 702.12a-b).

    CR 702.12a: "Indestructible is a static ability." CR 702.12b: "A permanent
    with indestructible can't be destroyed. Such permanents aren't destroyed by
    lethal damage, and **they ignore the state-based action that checks for
    lethal damage** (see rule 704.5g)."

    Three things follow from that wording, and all three are what
    `scenarios/test_indestructible.py` checks:

    - It is not "cannot die". Indestructible answers *destruction* only, so
      sacrificing it, exiling it, bouncing it, and CR 704.5f's toughness of 0 or
      less all still work - CR 704.5f even says so in as many words,
      "Regeneration can't replace this event."
    - Lethal damage is still *marked* on it. Nothing prevents the damage; the
      state-based action simply does not apply, so the damage sits there until
      CR 514.2 wipes it.
    - Deathtouch does not get round it either. CR 704.5h destroys, and CR 702.12b
      says a permanent with indestructible can't be destroyed.

    `game` is optional and is what makes this read the *computed* board
    (CR 613.5), so indestructible granted in layer 6 counts and indestructible
    removed by a Humility does not. Without a game it reads the printing, which
    is right for the cards in this pool that print it.
    """
    if game is None:
        return any(word.lower() == "indestructible" for word in permanent.keywords)
    return has_keyword(permanent, "indestructible", game)


def indestructible_survives_lethal_damage(permanent: CardState, game: Any = None) -> bool:
    """CR 702.12b: this creature has lethal damage and is not destroyed by it."""
    return permanent.has_lethal_damage and is_indestructible(permanent, game)


# --------------------------------------------------------------------------
# Exert (CR 701.43)
# --------------------------------------------------------------------------


def exert(permanent: CardState) -> CardState:
    """Exert a permanent (CR 701.43a).

    "To exert a permanent, you choose to have it not untap during your next
    untap step." CR 701.43b: "A permanent can be exerted even if it's not tapped
    or has already been exerted in a turn. If you exert a permanent more than
    once before your next untap step, each effect causing it not to untap
    expires during the same untap step." So exerting twice is exerting once,
    which is why this is a flag and not a count.

    CR 701.43c: "An object that isn't on the battlefield can't be exerted."
    """
    if permanent.zone is not Zone.BATTLEFIELD:
        raise ValueError(
            f"{permanent.name} is in the {permanent.zone.value}; only a permanent on the "
            f"battlefield can be exerted ({KeywordRule.EXERT})"
        )
    permanent.exerted = True
    return permanent


# --------------------------------------------------------------------------
# What each keyword's *triggered* ability does on resolution (CR 608.2)
# --------------------------------------------------------------------------
#
# `machines/effects.py` keys an ability's effect by `(card name, event)`. A
# keyword's ability belongs to no particular card, so its effect lives here and
# is looked up by the keyword instead. `TriggeredAbility.keyword` is what
# carries the key onto the stack.


def _prowess_effect(game: Any, ability: AbilityOnStack) -> None:
    """CR 702.108a's second half: "this creature gets +1/+1 until end of turn".

    A continuous effect generated by the resolution of an ability (CR 611.2),
    lasting until end of turn - which CR 500.5b and CR 514.2 put at the cleanup
    step, not the end step. It modifies power and toughness without setting
    them, so it applies in sublayer 7c (CR 613.4c), and it is timestamped now
    (CR 613.7b).

    CR 113.7a: the ability resolves even if its source has gone, but there is
    nothing left for the effect to apply to, so a creature that left the
    battlefield gets nothing.
    """
    source = ability.source(game)
    if source is None or source.zone is not Zone.BATTLEFIELD:
        return
    power, toughness = prowess_bonus
    game.continuous_effects.add(
        ContinuousEffect(
            description=f"prowess: {source.name} gets +{power}/+{toughness}",
            layer=Layer.POWER_TOUGHNESS,
            sublayer=Sublayer.MODIFY,
            timestamp=game.continuous_effects.tick(),
            duration=Duration.UNTIL_END_OF_TURN,
            source_id=source.id,
            selector=_only(source.id),
            modification=modify_power_toughness(power, toughness),
        )
    )


def _persist_effect(game: Any, ability: AbilityOnStack) -> CardState | None:
    """CR 702.79a's effect: return it with a -1/-1 counter on it.

    The intervening *if* has already been checked twice by the time this runs -
    once when it triggered (CR 603.4) and once on resolution (CR 608.2a) - so
    there is nothing left to test here.
    """
    source = ability.source(game)
    if source is None or source.zone is not Zone.GRAVEYARD:
        return None
    return persist_return(game, source, keyword_confirmed=True)


def _undying_effect(game: Any, ability: AbilityOnStack) -> CardState | None:
    """CR 702.93a's effect: return it with a +1/+1 counter on it. Printed or
    granted alike (a granted keyword functions as a printed one), so the
    keyword is not looked up again here - dispatch already says it is undying."""
    source = ability.source(game)
    if source is None:
        return None
    return undying_return(game, source)


def _modular_effect(game: Any, ability: AbilityOnStack) -> None:
    """CR 702.43a's dying half: the +1/+1 counters it had as it last existed on the
    battlefield (CR 603.10a, `last_known_counters`) go onto the target artifact
    creature, if the controller wants them. The counters are put by "a modular
    triggered ability" (Zabaz, the Glimmerwasp reads exactly that)."""
    source = ability.source(game)
    if source is None or not ability.targets:
        return
    count = source.last_known_counters[Counter.PLUS_ONE]
    target = game.resolve_target(ability.targets[0])
    if count <= 0 or not isinstance(target, CardState) or target.zone is not Zone.BATTLEFIELD:
        return
    if not game.may(
        ability.controller,
        f"put {count} +1/+1 counter(s) on {target.name} (modular)",
        source=ability.source_name,
        source_id=source_id_of(ability),
    ):
        return
    game.add_counters(target, Counter.PLUS_ONE, count, putter=ability.controller, modular=True)


def _evoke_effect(game: Any, ability: AbilityOnStack) -> CardState | None:
    """CR 702.74a's effect: "its controller sacrifices it".

    CR 701.21a's sacrifice, so `Game.sacrifice` and not a bare move: the
    permanent goes from the battlefield to its owner's graveyard, and both the
    sacrifice event and the dies event (CR 700.4) fire on the way, which is what
    lets an evoked incarnation feed a "whenever a creature dies" trigger.

    The intervening *if* has already been checked twice (CR 603.4 on the event,
    CR 608.2a on resolution), so nothing is re-tested here. What is tested is
    that the permanent is still on the battlefield: CR 608.2 resolves the
    ability with whatever is left, and a creature already killed in response is
    not a permanent to sacrifice.
    """
    source = ability.source(game)
    if source is None or source.zone is not Zone.BATTLEFIELD:
        return None
    return game.sacrifice(source)


def _cascade_effect(game: Any, ability: AbilityOnStack) -> CascadeResult | None:
    """CR 702.85a, the whole trigger: `cascade` exiles, asks, casts the hit
    during this resolution (CR 608.2g) and bottoms the rest."""
    source = ability.source(game)
    if source is None:
        return None
    return cascade(game, source)


_RIPPLE_COUNT_RE = re.compile(r"ripple\s+(?P<n>\d+)", re.IGNORECASE)


def ripple(game: Any, spell: CardState, count: int) -> list[CardState]:
    """CR 702.60a's resolution: reveal the top `count` cards of the caster's
    library (all of it when it is shorter), offer a free cast of each revealed
    card sharing `spell`'s name during this resolution (CR 608.2g), then put
    every revealed card not cast on the bottom of the library, in the order they
    were revealed (the "any order" is the caster's, and the engine keeps the
    revealed order)."""
    with game._id_allocator_scope():  # noqa: SLF001
        controller = spell.controller or game.active_player.username
        owner = game.player(controller)
        revealed = list(owner.library[:count])
        if not revealed:
            return []
        for state in revealed:
            game.reveal(state, source=spell.name)
        cast: list[CardState] = []
        for state in revealed:
            if state.name != spell.name:
                continue
            castable = game.can_cast_during_resolution(state, controller)
            decision = Decision(
                kind=DecisionKind.MAY,
                player=controller,
                prompt=f"cast {state.name} without paying its mana cost (ripple)",
                source=spell.name,
                source_id=source_id_of(spell),
                affirmative_is_legal=castable,
            )
            if game.ask(decision) and (
                game.cast_during_resolution(
                    state,
                    controller,
                    source_name=f"{spell.name}'s ripple",
                    rule="CR 702.60a",
                )
                is not None
            ):
                cast.append(state)
        for state in revealed:
            if state in cast:
                continue
            owner.cards_in(Zone.LIBRARY).remove(state)
            owner.add(state, Zone.LIBRARY)  # the bottom of the library
        return cast


def _ripple_effect(game: Any, ability: AbilityOnStack) -> list[CardState]:
    """CR 702.60a: the trigger sits above the spell that caused it (CR 603.3b),
    so `ability.source` is still that spell on the stack."""
    source = ability.source(game)
    match = _RIPPLE_COUNT_RE.search(ability.ability.raw or "")
    if source is None or match is None:
        return []
    return ripple(game, source, int(match["n"]))


def _storm_effect(game: Any, ability: AbilityOnStack) -> list[CardState]:
    """CR 702.40a's copy half.

    Storm's own trigger goes on the stack directly above the spell that
    caused it (CR 603.3b) and resolves before that spell does, so the spell
    is still on the stack (`ability.source`) when this runs - the same shape
    `_cascade_effect` already relies on. "For each other spell that was cast
    before it this turn" counts every spell any player cast this turn, not
    only the storm spell's own controller's - `Game.spells_cast_this_turn` is
    keyed by controller, so the count is the total across every player's list.
    Nothing can have been cast *between* the storm spell going on the stack
    and this trigger resolving (only casting adds to that count, and no
    priority is passed in between - CR 603.3b puts the trigger on the stack
    "before any player would receive priority"), so the storm spell itself is
    always the most recent entry and "total minus one" is exactly "how many
    were cast before it".

    CR 707.10: "To copy a spell ... means to put a copy of it onto the
    stack; a copy of a spell isn't cast" - `Game.copy_spell` already keeps a
    copy out of `spells_cast_this_turn`, so a copy's own storm trigger (it is
    still the same printed card) never fires, which is what stops the count
    from exploding.

    "If the spell has any targets, you may choose new targets for the
    copies" (CR 707.10c) is asked once per copy, reusing `Game.
    offer_new_targets_for_copy` - the same primitive Alania, Divergent
    Storm's own copy clause already uses - which is a no-op for a spell with
    no targets (Empty the Warrens) and offers a real choice for one that has
    them (Grapeshot).
    """
    source = ability.source(game)
    if source is None or source not in game.stack:
        return []
    controller = ability.controller
    total_cast_this_turn = sum(len(cast) for cast in game.spells_cast_this_turn.values())
    count = total_cast_this_turn - 1
    copies: list[CardState] = []
    for _ in range(max(count, 0)):
        copy = game.copy_spell(source, controller=controller)
        if copy is None:
            break  # CR 113.6g: this spell can't be copied.
        game.offer_new_targets_for_copy(
            copy, controller, source_name=source.name, source_id=source_id_of(source)
        )
        copies.append(copy)
    return copies


def _replicate_effect(game: Any, ability: AbilityOnStack) -> list[CardState]:
    """CR 702.56a's copy half: one copy for each time the replicate cost was
    paid.

    Same shape as `_storm_effect` - the replicate trigger sits directly above
    the spell it copies (CR 603.3b) and resolves first, so `ability.source`
    is still that spell on the stack. The count is `CastRecord.replicated`
    rather than a board-wide tally: CR 702.56a's own intervening *if*
    ("if a replicate cost was paid for it") already gated this trigger from
    firing at all when the count is zero, so by the time this runs the
    record exists and its `replicated` is what was actually paid, read the
    same way `_cast_record_for_clause`/`intervening_if_holds` already read
    it to decide whether to trigger in the first place.
    """
    source = ability.source(game)
    if source is None or source not in game.stack:
        return []
    controller = ability.controller
    record = game.cast_record_of(source)
    count = record.replicated if record is not None else 0
    copies: list[CardState] = []
    for _ in range(max(count, 0)):
        copy = game.copy_spell(source, controller=controller)
        if copy is None:
            break  # CR 113.6g: this spell can't be copied.
        game.offer_new_targets_for_copy(
            copy, controller, source_name=source.name, source_id=source_id_of(source)
        )
        copies.append(copy)
    return copies


def _casualty_effect(game: Any, ability: AbilityOnStack) -> CardState | None:
    """CR 702.153a's copy: "copy it. If the spell has any targets, you may
    choose new targets for the copy."

    The trigger sits directly above the spell that caused it (CR 603.3b),
    so `ability.source` is still that spell on the stack - `_replicate_
    effect`'s own shape, with exactly one copy per trigger.
    """
    source = ability.source(game)
    if source is None or source not in game.stack:
        return None
    copy = game.copy_spell(source, controller=ability.controller)
    if copy is None:
        return None
    if casualty_copy_is_nonlegendary_with_x_loyalty(source.card):
        # "The copy isn't legendary and has starting loyalty X" (CR 707.2:
        # these are copiable values of the copy, set by the effect that made it).
        record = game.cast_record_of(source)
        copy.card = _casualty_x_copy_of(source.card, record.x_value if record else 0)
    game.offer_new_targets_for_copy(
        copy, ability.controller, source_name=source.name, source_id=source_id_of(source)
    )
    return copy


def _casualty_x_copy_of(card: Card, x_value: int) -> Card:
    """`card` as the copy of Ob Nixilis, the Adversary's casualty has it: no
    legendary supertype and X for its printed (starting) loyalty."""
    import uuid

    return card.model_copy(
        update={
            "id": uuid.uuid5(card.id, f"casualty-copy|{x_value}"),
            "type_line": card.type_line.replace("Legendary ", "", 1),
            "loyalty": str(x_value),
        }
    )


def _ward_effect(game: Any, ability: AbilityOnStack) -> bool:
    """CR 702.21a's effect: "counter that spell or ability unless that player pays".

    CR 118.12a reads that "unless" as a question: that player may pay, and if
    they don't, the spell or ability is countered. It is asked here, as the
    ward trigger resolves, of the targeting spell's or ability's controller,
    through `Game.may_pay_unless_cost` - mana, life, a discard, a sacrifice, or
    any mix of them. CR 702.21b fixes the cost at resolution, so it is read off
    the permanent now.

    A payment already made on this very ability (`WardTrigger.begin_paying`,
    `AbilityOnStack.unless_payment`) is honoured without asking again. A cost
    that cannot be read, or a warded permanent that can no longer be found to
    read it from, cannot be paid, and the spell is countered as unpaid.

    Returns True if the targeting spell or ability survived.
    """
    if ward_was_paid(ability):
        return True
    event = ability.event
    if event is None or event.targeted_by is None:
        return True
    targeting = next(
        (item for item in game.stack if getattr(item, "id", None) == event.targeted_by), None
    )
    if targeting is None:
        # CR 608.2b is not this: the spell is simply no longer on the stack, so
        # there is nothing left to counter.
        return True
    payer = getattr(targeting, "controller", None) or game.active_player.username
    permanent = ability.source(game)
    cost = ward_cost_of_trigger(ability, permanent, payer) if permanent is not None else None
    if cost is not None and game.may_pay_unless_cost(
        payer, cost, source=ability.source_name, source_id=source_id_of(ability)
    ):
        return True
    game.counter(targeting)  # CR 701.6a
    return False


def _madness_effect(game: Any, ability: AbilityOnStack) -> CardState | None:
    """CR 702.35a's second ability, the half that can be automated.

    "Its owner **may** cast it by paying [cost] rather than paying its mana
    cost. **If that player doesn't, they put this card into their graveyard.**"

    Casting is a choice and there is nobody here to ask, so the trigger takes
    the branch that needs no answer: if the card is still sitting in its madness
    pile when the ability resolves, it goes to the graveyard. A scenario that
    wants it cast casts it and then resolves the trigger, which finds the card
    gone and does nothing - CR 400.7 has already made it a different object.

    CR 702.35c is why the graveyard branch matters at all: "if the exiled card
    wasn't cast and was moved to a public zone, effects referencing the
    discarded card can find that card" (CR 400.7k).
    """
    source = ability.source(game)
    if source is None or source.zone is not Zone.EXILE:
        return None
    annotation = source.exile_annotation
    if annotation is None or annotation.marker is not ExileMarker.MADNESS:
        return None
    if source in game.exile:
        game.exile.remove(source)
    game.put_into_graveyard(source)
    return source


def miracle_cost(card: Card, payer: str = "") -> TotalCost | None:
    """This card's miracle cost, or None if it has no miracle (CR 702.94a)."""
    ability = _keyword(card, "miracle")
    if ability is None:
        return None
    return _keyword_cost(ability, payer)


def has_miracle(card: Card) -> bool:
    return _keyword(card, "miracle") is not None


def _miracle_effect(game: Any, ability: AbilityOnStack) -> CardState | None:
    """CR 702.94a's linked trigger resolving: "you may cast it by paying
    [cost] rather than its mana cost."

    "It" is the card the static ability revealed - that object and no other
    (CR 607.2h). A card that left its owner's hand since is a new object
    (CR 400.7), so there is nothing left to cast: the trigger does nothing,
    and nobody is asked. Otherwise the controller is asked one `MAY`, and a
    yes casts the card while this trigger resolves (CR 608.2g) - timing
    ignored, the miracle cost announced as the alternative cost (CR 118.9,
    CR 601.2b), any X in it chosen then (CR 107.3a). Declining, or a cast
    that turns out illegal (no legal target, mana that cannot be paid - CR
    601.2), leaves the card in hand. Returns the spell, or None.
    """
    source = ability.source(game)
    if (
        source is None
        or source.zone is not Zone.HAND
        or source.zone_change_stamp != ability.source_stamp
    ):
        return None
    caster = ability.controller
    # CR 607.2h: the cost is the one of the miracle instance this trigger is
    # linked to - a granted "Miracle {2}" (`machines/spell_grants.py`) is
    # written out as a bare keyword line and read back here; a printed one
    # is the card's own.
    linked = granted_keyword_ability(ability.ability.raw) if ability.ability.raw else None
    if linked is not None and linked.canonical.lower() == "miracle" and linked.cost:
        cost = _keyword_cost(linked, caster)
    else:
        cost = miracle_cost(source.card, caster)
    if cost is None:
        game._note_unread_trigger(ability)  # noqa: SLF001
        return None
    return game.may_cast_during_resolution(
        source,
        caster,
        prompt=f"cast {source.name} by paying its miracle cost {cost} (CR 702.94a)",
        source=source.name,
        source_id=source_id_of(source),
        source_name=source.name,
        rule=KeywordRule.MIRACLE.value,
        keyword="Miracle",
        alternative_cost=cost,
    )


#: "the top N cards" inside `_hideaway_ability`'s own generated effect text,
#: read back to recover N without threading a second copy of it through
#: `AbilityOnStack`.
_HIDEAWAY_COUNT_RE = re.compile(r"top (?P<n>\d+) cards")


def _hideaway_effect(game: Any, ability: AbilityOnStack) -> None:
    """CR 702.75a's effect: look, exile one face down, bottom the rest.

    The exiled card is annotated `ExileMarker.HIDEAWAY`, linked back to this
    permanent's own id - the same "exiled with this permanent" shape
    `machines/effects.py`'s `_parse_imprint_clause` already uses for Ugin's
    Labyrinth (CR 207.2c: "imprint" itself has no rules meaning, so the link
    is not specific to that ability word), so a later ability naming "the
    exiled card"/"a card exiled with `<this>`" - Mosswort Bridge's own
    `{G}, {T}` ability - can find it again.

    "Exile one of them face down" is mandatory, unlike a "you may" choice, so
    this always asks `DecisionKind.CHOOSE_CARDS` for exactly one rather than
    offering a `MAY` first. The rest go to the bottom "in a random order"
    (CR 702.75a's own wording, not the caster's choice the way scry's "in any
    order" is) - the same seeded `random.Random` convention `machines/
    effects.py`'s own top-N-then-bottom shapes already use, so a scenario
    asserting on the resulting library order stays reproducible.
    """
    source = ability.source(game)
    if source is None or source.zone is not Zone.BATTLEFIELD:
        return
    with game._id_allocator_scope():  # noqa: SLF001
        printed = ability.ability
        text = printed.effect if isinstance(printed, TriggeredAbility) else ""
        match = _HIDEAWAY_COUNT_RE.search(text or "")
        count = int(match.group("n")) if match is not None else 4
        controller = game.controller_of(ability)
        looked = list(controller.library[:count])
        if not looked:
            return
        for state in looked:
            game.look(state, controller.username, source=source.name)  # CR 701.20e
        decision = Decision(
            kind=DecisionKind.CHOOSE_CARDS,
            player=controller.username,
            prompt=f"exile a card face down with {source.name} (hideaway)",
            source=source.name,
            source_id=source_id_of(source),
            amount=1,
            cards=tuple(state.id for state in looked),
        )
        chosen_ids = game.ask(decision)
        by_id = {state.id: state for state in looked}
        chosen = by_id[chosen_ids[0]]
        rest = [state for state in looked if state is not chosen]

        controller.cards_in(Zone.LIBRARY).remove(chosen)
        chosen.move_to(Zone.EXILE)
        # CR 702.75a exiles it *face down*, so it stays hidden until the ability
        # that hid it away lets its controller play it.
        chosen.face_up = False
        chosen.exile_annotation = ExileAnnotation(
            marker=ExileMarker.HIDEAWAY, owner=chosen.owner, linked_permanent_id=source.id
        )
        game.exile.append(chosen)
        # CR 406.3: a player "instructed to look at a card and then exile it
        # face down ... may continue to look at that card until it leaves the
        # exile zone" - a look against the exiled object's own stamp. CR
        # 702.75a's granted look belongs to whoever controls this permanent,
        # now and after any later control change (`Game.note_hideaway_viewers`).
        game.look(chosen, controller.username, source=source.name)
        game.note_hideaway_viewers()

        if rest:
            rng = random.Random(  # noqa: S311
                f"{game.shuffle_seed}:{game.shuffles_performed}:hideaway-{source.id}"
            )
            rng.shuffle(rest)
            for state in rest:
                controller.move(state, Zone.LIBRARY)
            game.shuffles_performed += 1


def _suspend_effect(game: Any, ability: AbilityOnStack) -> Any:
    """CR 702.62a's second and third abilities, told apart by which one this is.

    Suspend is the one keyword in this registry that is shorthand for two
    *triggered* abilities (`_suspend_abilities`), and `KEYWORD_TRIGGER_
    EFFECTS` is keyed by keyword, so this is the dispatcher between them. It
    reads the ability's own `event`, which is exactly what tells them apart:
    the upkeep one is `TriggerEvent.BEGINNING_OF_STEP` and the
    last-counter one is the unread condition, `event=None`.

    Neither branch re-tests its intervening *if*. Both have already been
    checked twice by the time this runs - CR 603.4 when the ability
    triggered, CR 608.2a again as it resolves (`Game._intervening_if_still_
    true`) - which is what makes the card leaving exile in response stop the
    tick without anything here asking.

    Both effects live in `machines/casting.py` beside CR 116.2f's special
    action that puts the counters on in the first place, and both are still
    callable by hand: Greater Gargadon's own "Sacrifice an artifact,
    creature, or land: Remove a time counter from this card" is a printed
    activated ability that removes one outside any upkeep at all.
    """
    from .casting import finish_suspend, remove_suspend_time_counter

    source = ability.source(game)
    if source is None:
        return None
    printed = ability.ability
    if isinstance(printed, TriggeredAbility) and printed.event is TriggerEvent.BEGINNING_OF_STEP:
        return remove_suspend_time_counter(game, source)
    return finish_suspend(game, source)


def _impending_effect(game: Any, ability: AbilityOnStack) -> int | None:
    """CR 702.176a's fourth ability resolving: "remove a time counter from it."

    Its intervening *if* was checked as it triggered (CR 603.4) and again as it
    resolves (CR 608.2a), which is what stops a blinked Overlord - a new object,
    CR 400.7 - losing a counter it never had. Guarded anyway against a source
    that is gone, so a direct call cannot raise on an empty count.
    """
    source = ability.source(game)
    if source is None or source.zone is not Zone.BATTLEFIELD:
        return None
    if not source.can_remove_counters(Counter.TIME):
        return None
    return source.remove_counters(Counter.TIME, 1)


def _remove_vanishing_time_counter(game: Any, source: CardState) -> int | None:
    """CR 702.63a's second ability resolving: "remove a time counter from it."

    The intervening *if* ("this permanent has a time counter on it") was
    checked as it triggered (CR 603.4) and again as it resolves (CR 608.2a) by
    `machines/triggers.intervening_if_answer`'s own clause for it, which is
    what stops the tick once the counters are gone some other way - guarded
    here too, the same defensive shape `_impending_effect` takes, so a direct
    call cannot raise on an empty count or an off-battlefield permanent.

    Taking the *last* counter off raises CR 702.63a's own third ability's
    trigger condition (`ExtraTriggerEvent.LAST_TIME_COUNTER_REMOVED`), the
    identical event `machines/casting.remove_suspend_time_counter` raises for
    suspend's own last-counter ability.
    """
    if source.zone is not Zone.BATTLEFIELD or not source.can_remove_counters(Counter.TIME):
        return None
    remaining = source.remove_counters(Counter.TIME, 1)
    if remaining == 0:
        game.emit(
            GameEvent(
                event=ExtraTriggerEvent.LAST_TIME_COUNTER_REMOVED,
                subject_id=source.id,
                subject_name=source.name,
                subject_card=source.card,
                player=source.controller or source.owner,
            )
        )
    return remaining


def _sacrifice_when_vanished(game: Any, source: CardState) -> CardState | None:
    """CR 702.63a's third ability resolving: "sacrifice it."

    No intervening *if* is printed on this one (unlike suspend's own third
    ability, which reads "if it's exiled" before its effect), so a permanent
    that already left the battlefield some other way in response to the
    trigger is not this ability breaking a rule - "sacrifice it" simply has
    nothing left to act on, the same "the instruction is now impossible"
    outcome `game.sacrifice` itself would refuse if asked to run on it.
    """
    if source.zone is not Zone.BATTLEFIELD:
        return None
    return game.sacrifice(source)


def _vanishing_effect(game: Any, ability: AbilityOnStack) -> Any:
    """CR 702.63a's second and third abilities, told apart by which one this
    is - the same dispatch `_suspend_effect` above already uses for suspend's
    identical two-triggered-abilities shape: the upkeep tick is
    `TriggerEvent.BEGINNING_OF_STEP`, the last-counter sacrifice is the
    unread condition, `event=None`.
    """
    source = ability.source(game)
    if source is None:
        return None
    printed = ability.ability
    if isinstance(printed, TriggeredAbility) and printed.event is TriggerEvent.BEGINNING_OF_STEP:
        return _remove_vanishing_time_counter(game, source)
    return _sacrifice_when_vanished(game, source)


def _battle_cry_effect(game: Any, ability: AbilityOnStack) -> None:
    """CR 702.91a's effect: "each other attacking creature gets +1/+0 until
    end of turn."

    Untargeted (CR 702.91a prints no "target"), so the set it applies to is
    fixed here, at resolution, the same way any other resolving ability's own
    continuous effect is fixed "when it begins" (CR 611.2c) - `game.
    attacking_creatures()` read *now* is exactly that set: a creature that
    left combat earlier in the same priority window is already off it, and a
    creature put onto the battlefield attacking afterwards was never part of
    it, because this only ever runs once, here. One `ContinuousEffect` per
    other attacker (the same "loop and add one per object" shape
    `_untap_and_apply_control_sentences` and friends already use for a
    multi-target sentence) rather than a shared dynamic selector, since a
    dynamic "attacking creatures" filter would incorrectly keep pumping (or
    stop pumping) a creature whose attacking status changes after this
    resolves - exactly what CR 611.2c's fixed-set rule forbids.
    """
    source = ability.source(game)
    if source is None:
        return
    store = game.continuous_effects
    timestamp = store.tick()
    for creature in game.attacking_creatures():
        if creature.id == source.id:
            continue  # CR 702.91a: "each OTHER attacking creature".
        store.add(
            ContinuousEffect(
                description=f"{source.name}'s battle cry: {creature.name} gets +1/+0",
                layer=Layer.POWER_TOUGHNESS,
                sublayer=Sublayer.MODIFY,
                timestamp=timestamp,
                duration=Duration.UNTIL_END_OF_TURN,
                selector=_only(creature.id),
                modification=modify_power_toughness(1, 0),
            )
        )


#: `_cumulative_upkeep_ability`'s own effect text, read back for its [cost].
_CUMULATIVE_UPKEEP_EFFECT_RE = re.compile(
    r"^put an age counter on this permanent\. Then you may pay (?P<cost>.+) for each age "
    r"counter on it\. If you don't, sacrifice it$"
)


def _cumulative_upkeep_effect(game: Any, ability: AbilityOnStack) -> bool | None:
    """CR 702.24a resolving: the age counter, then one pay-or-sacrifice decision.

    The counter goes on first, and the cost is then [cost] once per age counter
    on the permanent *now* - CR 702.24b: "the age counters are not connected to
    any particular ability; each cumulative upkeep ability will count the total
    number of age counters on the permanent at the time that ability resolves."

    `machines/cost.cumulative_upkeep_cost` folds the repeated cost into one
    total, one copy per counter, so each copy's choice (which card, which
    colour) is its own, and `Game.may_pay_unless_cost` asks once: the whole
    set, or nothing. CR 118.3 makes the affirmative illegal when the whole set
    cannot be paid, which leaves only the sacrifice. The mana carries
    `SpendPurpose.PAY_CUMULATIVE_UPKEEP` (`ManaSpend.paying_cumulative_upkeep`),
    so Snowfall's restricted mana pays it (CR 106.6).

    A [cost] this engine cannot read or pay mid-resolution fails closed: no
    counter, no question, no sacrifice, and an `UnmodeledTriggerEffectNotice`
    naming the text - never a sacrifice the player could have avoided.

    Returns True if paid, False if sacrificed, None if nothing happened.
    """
    source = ability.source(game)
    if source is None or source.zone is not Zone.BATTLEFIELD:
        return None
    printed = ability.ability
    match = (
        _CUMULATIVE_UPKEEP_EFFECT_RE.fullmatch(printed.effect or "")
        if isinstance(printed, TriggeredAbility)
        else None
    )
    controller = game.controller_of(source).username
    if match is None or cumulative_upkeep_cost(match.group("cost"), 1, controller) is None:
        game._note_unread_trigger(ability)  # noqa: SLF001
        return None
    game.add_counters(source, Counter.AGE, 1)
    count = source.counter_count(Counter.AGE)
    cost = cumulative_upkeep_cost(match.group("cost"), count, controller)
    assert cost is not None  # the same text read at count 1 just above
    paid = game.may_pay_unless_cost(
        controller,
        cost,
        source=ability.source_name,
        source_id=source_id_of(ability),
        spend=ManaSpend.paying_cumulative_upkeep(game.characteristics_of(source)),
        prompt=(
            f"pay {cost} for {source.name}'s cumulative upkeep ({count} age counter(s)), "
            "or sacrifice it"
        ),
    )
    if paid:
        return True
    if source.zone is Zone.BATTLEFIELD:
        game.sacrifice(source)  # CR 701.21a
    return False


#: `_echo_ability`'s own effect text, read back for its [cost] and X.
_ECHO_EFFECT_RE = re.compile(
    r"^sacrifice it unless you pay (?P<cost>.+?)(?:, where X is (?P<x>.+))?$"
)


def _echo_cost(
    printed: str, game: Any, controller: str | None, source: CardState | None
) -> TotalCost | None:
    """Echo's [cost] as one `TotalCost`, its X (CR 107.3: defined by the
    text, so not chosen) evaluated now - "as the cost is paid" - against
    `game`; `None` for a cost this engine cannot read or pay mid-resolution.
    With no game (the support probe) X is read as 0, only to check the
    shape reads."""
    match = re.fullmatch(r"(?P<cost>.+?)(?:, where X is (?P<x>.+))?", printed.strip())
    if match is None:
        return None
    cost = match.group("cost").strip()
    if match.group("x") is not None:
        from .effects import amount_expression

        reader = amount_expression(match.group("x"))
        if reader is None or "{X}" not in cost:
            return None
        value = 0 if game is None or controller is None else reader(game, controller, source, 0)
        cost = cost.replace("{X}", f"{{{max(value, 0)}}}")
    elif "{X}" in cost:
        return None
    read = total_cost_for_phrase(cost, controller)
    if read is None or any(component.variable_count for component in read.components):
        return None
    return read


#: "You may pay {0} rather than pay the echo cost for permanents you control."
#: (Thick-Skinned Goblin): CR 118.9's alternative cost applied to echo's [cost].
_ECHO_ALTERNATIVE_RE = re.compile(
    r"^you may pay (?P<cost>(?:\{[^{}]+\})+) rather than pay the echo cost for "
    r"permanents you control\.?$",
    re.IGNORECASE,
)


def echo_alternative_cost(line: str) -> TotalCost | None:
    """The cost a static "rather than pay the echo cost" line substitutes, or
    `None` when `line` is not one (CR 118.9, CR 702.30a)."""
    match = _ECHO_ALTERNATIVE_RE.match(re.sub(r"\s*\([^)]*\)", "", line).strip())
    if match is None:
        return None
    mana = ManaCost.try_parse(match.group("cost"))
    return None if mana is None else TotalCost.of(mana)


def _echo_alternative_for(game: Any, controller: str) -> TotalCost | None:
    """The alternative echo cost a permanent `controller` controls offers."""
    board = game.computed_board()
    for permanent in game.permanents_controlled_by(controller):
        for line in board.of(permanent).abilities:
            if "echo cost" not in line.lower():
                continue
            alternative = echo_alternative_cost(line)
            if alternative is not None:
                return alternative
    return None


def _echo_effect(game: Any, ability: AbilityOnStack) -> bool | None:
    """CR 702.30a resolving: "sacrifice it unless you pay [cost]" - CR
    118.12a's "unless", one `Game.may_pay_unless_cost` question, CR 118.3
    leaving only the sacrifice when the cost cannot be paid in full.

    The intervening "if" was checked as the upkeep began and is checked again
    as this resolves (CR 603.4) by the trigger machinery itself. An X in
    [cost] is evaluated now, as the cost is paid (Volcano Hellion's "where X
    is your life total"). A [cost] this engine cannot read fails closed with
    a notice - never a sacrifice the player could have avoided.

    Returns True if paid, False if sacrificed, None if nothing happened.
    """
    source = ability.source(game)
    if source is None or source.zone is not Zone.BATTLEFIELD:
        return None
    printed = ability.ability
    match = (
        _ECHO_EFFECT_RE.fullmatch(printed.effect or "")
        if isinstance(printed, TriggeredAbility)
        else None
    )
    controller = game.controller_of(source).username
    cost = (
        None
        if match is None
        else _echo_cost(
            match.group("cost") + (f", where X is {match.group('x')}" if match.group("x") else ""),
            game,
            controller,
            source,
        )
    )
    if cost is None:
        game._note_unread_trigger(ability)  # noqa: SLF001
        return None
    alternative = _echo_alternative_for(game, controller)
    if alternative is not None:
        # CR 118.9: paying the alternative cost is always the better choice
        # when it is cheaper, and the player may take it rather than the
        # printed one - {0} is never beaten.
        cost = alternative
    paid = game.may_pay_unless_cost(
        controller,
        cost,
        source=ability.source_name,
        source_id=source_id_of(ability),
        prompt=f"pay {cost} for {source.name}'s echo, or sacrifice it",
    )
    if paid:
        return True
    if source.zone is Zone.BATTLEFIELD:
        game.sacrifice(source)  # CR 701.21a
    return False


#: What one keyword's triggered ability does when it resolves, by keyword.
#: `Game._effect_of` has to consult this before the card-name registry - see
#: `docs/engine-coverage.md` for the hook.
KEYWORD_TRIGGER_EFFECTS: dict[str, Callable[[Any, AbilityOnStack], Any]] = {
    "prowess": _prowess_effect,
    "persist": _persist_effect,
    "undying": _undying_effect,
    "modular": _modular_effect,
    "cascade": _cascade_effect,
    "ripple": _ripple_effect,
    "storm": _storm_effect,
    "replicate": _replicate_effect,
    "casualty": _casualty_effect,
    # CR 702.78a's copy is casualty's own: "copy it. If the spell has any
    # targets, you may choose new targets for the copy."
    "conspire": _casualty_effect,
    "ward": _ward_effect,
    "madness": _madness_effect,
    "miracle": _miracle_effect,
    "hideaway": _hideaway_effect,
    "evoke": _evoke_effect,
    "suspend": _suspend_effect,
    "impending": _impending_effect,
    "vanishing": _vanishing_effect,
    "mobilize": _mobilize_effect,
    "battle cry": _battle_cry_effect,
    "cumulative upkeep": _cumulative_upkeep_effect,
    "echo": _echo_effect,
    "annihilator": _annihilator_effect,
    "soulbond": soulbond_effect,
}


def keyword_trigger_effect(
    ability: TriggeredAbility,
) -> Callable[[Any, AbilityOnStack], Any] | None:
    """The effect of a triggered ability that was printed as a keyword, or None."""
    if ability.keyword is None:
        return None
    return KEYWORD_TRIGGER_EFFECTS.get(ability.keyword.lower())


def keyword_effect_for(ability: AbilityOnStack) -> Callable[[Any, AbilityOnStack], Any] | None:
    """The effect of an ability that a CR 702 keyword is shorthand for, or None.

    **This is the one call a resolver needs.** `machines/effects.py` answers
    `(card name, event)` and `(card name, index)`, which cannot describe an
    ability that belongs to a keyword rather than to a card: cycling is the same
    ability on every card that prints it, and so are equip, ward, prowess,
    cascade, persist and madness.

    Both kinds are covered:

    - an **activated** one, reached through the `KeywordActivation` that put it
      on the stack (CR 602.2);
    - a **triggered** one, reached through `TriggeredAbility.keyword`
      (CR 603.2).

    Returning None means no keyword owns this ability, and the card-name
    registries are the right place to look. Asked before them, a keyword
    ability's effect runs through the ordinary CR 608.2 resolution path with
    everything that implies - CR 608.2b's target recheck, CR 608.2a's
    intervening *if*, and CR 608.2n's removal from the stack.
    """
    activation = ability.keyword_activation
    if activation is not None:
        return lambda _game, _ability: activation.run_effect()
    printed = ability.ability
    if isinstance(printed, TriggeredAbility):
        return keyword_trigger_effect(printed)
    return None


# --------------------------------------------------------------------------
# What each keyword's activated ability does on resolution
# --------------------------------------------------------------------------

KEYWORD_EFFECTS: dict[str, Callable[[KeywordActivation], Any]] = {
    "equip": _equip_effect,
    "crew": _crew_effect,
    "saddle": _saddle_effect,
    "unearth": _unearth_effect,
    "transmute": _transmute_effect,
    "station": _station_effect,
    "ninjutsu": _ninjutsu_effect,
    "commander ninjutsu": _ninjutsu_effect,
    "outlast": _outlast_effect,
    "craft": _craft_effect,
    "embalm": lambda activation: _token_copy_keyword_effect(activation),
    "eternalize": lambda activation: _token_copy_keyword_effect(activation),
}


def _token_copy_keyword_effect(activation: KeywordActivation) -> Any:
    """Embalm's and eternalize's effect (CR 702.128a, CR 702.129a) -
    `machines/face_down_keywords.token_copy_keyword_effect`."""
    from .face_down_keywords import token_copy_keyword_effect

    return token_copy_keyword_effect(activation)


def keyword_activation_effect(keyword: str) -> Callable[[KeywordActivation], Any] | None:
    """The effect a keyword's activated ability has on resolution, or None.

    Cycling and every typecycling are routed by the keyword's shape rather than
    by a row per type: CR 702.29e allows "any card type, subtype, supertype, or
    combination thereof" before "cycling", so `Wizardcycling`, `Slivercycling`
    and `Basic landcycling` are the same ability as `Islandcycling`, and a list
    of types would always be missing one.
    """
    lowered = keyword.lower()
    if lowered.endswith("cycling"):
        return _cycling_effect
    return KEYWORD_EFFECTS.get(lowered)


# -- daybound and nightbound (CR 702.145) and day/night (CR 731) ---------------

DAYBOUND = "daybound"
NIGHTBOUND = "nightbound"


def _printed_day_night_bound(permanent: CardState) -> bool:
    """Whether either face of this card prints daybound or nightbound - a
    cheap pre-filter only; `has_keyword` then asks the computed board, so a
    keyword removed in layer 6 (CR 613.1f) stops working."""
    return any(k.lower() in (DAYBOUND, NIGHTBOUND) for k in permanent.card.keywords)


def enters_transformed_at_night(game: Any, card_state: CardState) -> bool:
    """CR 702.145b's first ability: "If it is night and this permanent is
    represented by a double-faced card, it enters transformed."

    Asked while the card is still where it was, front face up, so its own
    `keywords` are the front face's - the face daybound is printed on
    (CR 702.145a)."""
    if game.day_night is not DayNight.NIGHT or card_state.card.back_face is None:
        return False
    return any(keyword.lower() == DAYBOUND for keyword in card_state.keywords)


def transform_for_day_night(game: Any) -> None:
    """Turn every permanent whose face disagrees with the designation.

    CR 702.145b: "As it becomes night, if this permanent is front face up,
    transform it"; CR 702.145c: any time a front-face-up daybound permanent
    is controlled while it's night, it transforms, immediately and not as a
    state-based action. CR 702.145e and CR 702.145f are the same for a
    back-face-up nightbound permanent and day. Each is a real transform
    (`effects.transform_permanent`), so "transforms into" (CR 701.27e) sees
    it.
    """
    from .effects import transform_permanent

    for permanent in list(game.battlefield):
        if not _printed_day_night_bound(permanent):
            continue
        if (
            game.day_night is DayNight.NIGHT
            and not permanent.transformed
            and has_keyword(permanent, DAYBOUND, game)
        ) or (
            game.day_night is DayNight.DAY
            and permanent.transformed
            and has_keyword(permanent, NIGHTBOUND, game)
        ):
            transform_permanent(game, permanent, day_night=True)


def apply_daybound_nightbound(game: Any) -> None:
    """The "any time" halves of CR 702.145, checked whenever the game looks.

    CR 702.145d: a daybound permanent while it's neither day nor night makes
    it day. CR 702.145g: a nightbound one, with no daybound permanent on the
    battlefield, makes it night. Otherwise CR 702.145c/702.145f's transforms
    (`transform_for_day_night`). `Game.set_day_night` runs those transforms
    itself as the designation changes.
    """
    bound = [p for p in game.battlefield if _printed_day_night_bound(p)]
    if not bound:
        return
    if game.day_night is None:
        if any(has_keyword(p, DAYBOUND, game) for p in bound):
            game.set_day_night(DayNight.DAY)
        elif any(has_keyword(p, NIGHTBOUND, game) for p in bound):
            game.set_day_night(DayNight.NIGHT)
        return
    transform_for_day_night(game)


def is_day_night_bound(permanent: CardState, game: Any) -> bool:
    """Whether CR 702.145b's / CR 702.145e's "This permanent can't transform
    except due to its daybound [nightbound] ability" applies to it now."""
    if not _printed_day_night_bound(permanent):
        return False
    return has_keyword(permanent, DAYBOUND, game) or has_keyword(permanent, NIGHTBOUND, game)


#: "If it's neither day nor night, it becomes day as this creature enters."
#: (Gavony Dawnguard, Brimstone Vandal, Sunstreak Phoenix, ...). The subject is
#: the permanent itself - "this `<type>`", its name, or a legendary card's
#: shortened name (CR 201.5c) - and the designation is either word, since the
#: template reads the same both ways.
_AS_ENTERS_DAY_NIGHT_RE = re.compile(
    r"^if it's neither day nor night, it becomes (?P<designation>day|night) as "
    r"(?P<subject>.+?) enters(?: the battlefield)?\.?$",
    re.IGNORECASE,
)


def as_enters_day_night(text: str, card_name: str) -> DayNight | None:
    """The designation an "if it's neither day nor night, it becomes day as
    this creature enters" line sets, or None when `text` is not that line."""
    match = _AS_ENTERS_DAY_NIGHT_RE.fullmatch(text.strip().replace("’", "'"))
    if match is None:
        return None
    subject = match.group("subject").strip().lower()
    names = {card_name.lower(), card_name.split(",")[0].strip().lower()}
    if not (re.fullmatch(r"this [a-z]+", subject) or subject in names):
        return None
    return DayNight(match.group("designation").lower())


def apply_as_enters_day_night(game: Any, permanent: CardState) -> None:
    """Apply the permanent's own "if it's neither day nor night, it becomes
    day as this creature enters" as it enters (CR 731.1: "Other effects can
    also make it day or night"). Read off its computed abilities, so a copy
    or a permanent whose abilities were removed as it entered behaves as it
    would exist on the battlefield (CR 614.12)."""
    if game.day_night is not None:
        return
    for line in game.characteristics_of(permanent).abilities:
        designation = as_enters_day_night(line, permanent.name)
        if designation is not None:
            game.set_day_night(designation)
            return


# `AbilityOnStack.keyword_activation`/`.unless_payment` (machines/triggers.py)
# carry `KeywordActivation` and `CostPayment` as string forward references,
# because `.cost` (which defines `CostPayment`) already imports names from
# `.triggers`, and this module (which defines `KeywordActivation`) imports
# `AbilityOnStack` from it too - either real import up there would be
# circular. Both real classes exist by now, so this is where the deferred
# annotations are actually resolved; `machines/__init__.py` imports `.casting`
# before anything else that touches `AbilityOnStack`, and `.casting` imports
# this module, so this always runs before an `AbilityOnStack` is built for
# real anywhere in the package.
AbilityOnStack.model_rebuild(
    _types_namespace={"KeywordActivation": KeywordActivation, "CostPayment": CostPayment}
)


# The keyword machines that live in their own modules register their
# `KEYWORD_EFFECTS` rows as they load; imported last so each can build on
# everything above.
from . import attach_keywords, blitz, level_up  # noqa: E402, F401
from .free_cast_price import with_board_priced_cost  # noqa: E402
from .reconfigure import (  # noqa: E402
    RECONFIGURE_UNATTACH_EFFECT,
    reconfigure_unattach_refusal,
)
