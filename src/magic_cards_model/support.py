"""What the engine supports on a card, clause by clause - the support oracle.

`card_support(card)` is `scripts/sweep_pool.py`'s own per-card verdict as a
library call: it runs the real dispatchers - `effect_for`,
`trigger_effect_for`, `activated_effect_for`, the layer and replacement
readers, and every keyword machine - with the arguments `models/game.py`
calls them with, and sorts each clause of the card into handled / notice /
static_unaudited / silent (plus the two sub-silent findings,
unmatchable_condition and quoted_effect). The sweep script reports on the
fixture pool through this module, so the two can never disagree; any other
consumer (a deck checker warning that a card may not be fully supported)
asks the same question of any `Card` built from a Scryfall printing.

It never changes game behaviour and never touches a live game: probing a
trigger condition or an "enters" replacement builds a throwaway `Game` of its
own, and every probe runs with a fresh uuid4 id allocator installed, so a
caller inside a game's deterministic `_id_allocator_scope()` does not have
ids minted out of that game's sequence (`ids.py`).

The historical record of why each rule below exists is in the docstrings,
moved here verbatim from the sweep; the measurement defects they describe
are pinned by `tests/test_sweep_pool.py` and `tests/test_card_support.py`.
"""

import json
import operator
import re
import threading
from collections import defaultdict
from collections.abc import Callable
from functools import cache
from pathlib import Path
from typing import Literal, NamedTuple
from uuid import uuid4

from pydantic import ConfigDict

from magic_cards_model import __version__
from magic_cards_model.ids import install_id_allocator, reset_id_allocator
from magic_cards_model.machines import keywords as keyword_machine
from magic_cards_model.machines.abilities import (
    AbilityKind,
    ActivatedAbility,
    TriggeredAbility,
    _strip_reminder,
    keyword_abilities,
    parse_abilities,
    parse_mana_abilities,
)
from magic_cards_model.machines.abilities import (
    self_normalized_effect_text as _self_normalized_effect_text,
)
from magic_cards_model.machines.casting import (
    ADDITIONAL_COST_KEYWORDS,
    TARGET_LEGALITY_KEYWORDS,
    TIMING_KEYWORDS,
    adventure_face,
    conditional_flash_condition,
    has_split_second,
    hexproof_abilities_in,
    keyword_cast_options,
    player_keyword_grant_of_line,
    reads_as_graveyard_cast_permission_line,
    reads_mandatory_additional_cost_line,
    reads_or_pay_additional_cost_line,
    reads_printed_zone_permission_line,
)
from magic_cards_model.machines.casting_restrictions import (
    _CANT_BE_COUNTERED_RE,
    _CONDITIONAL_CANT_BE_COUNTERED_RE,
    reads_player_rule_static_line,
)
from magic_cards_model.machines.combat import (
    Keyword,
    is_attack_cost_line,
    is_attack_requirement_line,
    is_blocked_by_at_most_one_line,
    is_group_attack_restriction_line,
    is_self_card_count_restriction_line,
    is_self_control_count_restriction_line,
    reads_self_combat_restriction_line,
)
from magic_cards_model.machines.companion import reads_companion_line
from magic_cards_model.machines.connive import is_connive_replacement_line, mentions_connive
from magic_cards_model.machines.cost import (
    additional_cost_phrases,
    cost_announces_x,
    cost_modifier_effect,
    looks_like_unparsed_cost_modifier,
    static_free_cast_grant,
    waterbend_mana_cost,
)
from magic_cards_model.machines.counter_effects import (
    parse_resolution_text as counter_resolution_text,
)
from magic_cards_model.machines.effects import (
    _YOU_AND_GROUP_SUBJECT_RE,
    _compose_layer_effect_with_remainder_for_ability_mode,
    _parse_counter_then_recruit_by_mana_value_pair,
    _parse_endure_clause,
    _parse_explores_clause,
    _parse_explores_then_conditional_mass_destroy,
    _parse_goad_clause,
    _parse_mode_with_shared_verb_fallback,
    _parse_monstrosity_clause,
    _parse_recruit_clause,
    _parse_referent_object_clause,
    _parse_where_x_is_continuous_effect,
    activated_effect_for,
    create_continuous_effect,
    create_continuous_effect_of_ability,
    effect_for,
    modal_trigger_profile,
    mode_effect_body,
    parse_clause_effect,
    parse_mixed_effect,
    parse_mode_effect,
    reads_as_transforms_line,
    resolve_modal_spell,
    split_effect_clauses,
    trigger_effect_for,
)
from magic_cards_model.machines.keyword_counters import (
    conditional_group_keyword_grant_of_line,
    enters_with_counters_pronoun_fallback,
)
from magic_cards_model.machines.layers import (
    LAYER_EFFECTS,
    additional_land_plays_of_line,
    looks_like_unparsed_layer_effect,
    off_battlefield_characteristics,
    parsed_layer_effects,
    plays_lands_from_graveyard_line,
)
from magic_cards_model.machines.modes import modal_profile, substitute_x
from magic_cards_model.machines.objects_as_costs import has_improvise
from magic_cards_model.machines.opening_hand import OpeningHandAction, read_opening_hand_line
from magic_cards_model.machines.replacement import (
    ENTERS_KINDS,
    ReplacementKind,
    _self_enters_modifiers,
    enters_as_copy_outcome,
    parse_replacement_effects,
    performed_static_replacement_line,
    performs_static_line,
    reads_cant_enter_line,
    self_enters_effects_read,
    strip_reminder_text,
)
from magic_cards_model.machines.spell_grants import reads_spell_keyword_grant_line
from magic_cards_model.machines.triggers import (
    _ENTERS_TAPPED_RE as _CONDITION_ENTERS_TAPPED_RE,
)
from magic_cards_model.machines.triggers import (
    _ENTERS_UNTAPPED_RE as _CONDITION_ENTERS_UNTAPPED_RE,
)
from magic_cards_model.machines.triggers import (
    _ENTERS_WITH_COUNTER_RE as _CONDITION_ENTERS_WITH_COUNTER_RE,
)
from magic_cards_model.machines.triggers import (
    _POWER_OR_TOUGHNESS_QUALIFIER as _CONDITION_POWER_OR_TOUGHNESS_QUALIFIER_RE,
)
from magic_cards_model.machines.triggers import (
    _STATE_COUNTER_TRIGGER_RE,
    GameEvent,
    TriggerEvent,
    _unread_trigger_events,
    condition_matches,
    is_additional_trigger_line,
    is_batched_attack_condition,
    total_power_attack_threshold,
    triggers_only_off_the_stack,
)
from magic_cards_model.machines.triggers import (
    _required_entering_subtype as _condition_required_entering_subtype,
)
from magic_cards_model.machines.triggers import (
    _required_subtype as _condition_required_subtype,
)
from magic_cards_model.machines.triggers import (
    _required_types as _condition_required_types,
)
from magic_cards_model.models import CardState, Game, Player, Zone
from magic_cards_model.models.card import (
    Card,
    Layout,
    Legality,
    Supertype,
    Type,
    types_of,
)
from magic_cards_model.models.card_state import Counters, TargetRef
from magic_cards_model.models.game import (
    condition_is_readable,
    conditional_additional_land_plays_of_line,
    is_player_rules_static_line,
    reads_activation_rule_line,
    reads_self_cost_reduction_line,
)
from magic_cards_model.models.player import reads_maximum_hand_size_line
from magic_cards_model.numbers import parse_count
from magic_cards_model.snapshot import EngineModel

#: The package's own real Scryfall printings (`data/printings`), used only as
#: probe material: a trigger condition naming "a Mountain" or "an artifact" is
#: tested against genuine printings of that kind (`_probe_cards`). Built the
#: same way `tests/cards.pool` builds its index - sorted by file, each
#: multifaced card reachable under its front face's name too - so the probe
#: order, and with it every verdict, is identical to the sweep's.
_PRINTINGS_DIR = Path(__file__).parent / "data" / "printings"


@cache
def _probe_pool() -> dict[str, Card]:
    cards: dict[str, Card] = {}
    for path in sorted(_PRINTINGS_DIR.glob("*.json")):
        card_data = Card.model_validate(json.loads(path.read_text()))
        cards[card_data.name] = card_data
        cards.setdefault(card_data.name.split("//")[0].strip(), card_data)
    return cards


def in_target_formats(printing: Card) -> bool:
    """Whether this printing exists in at least one of the three formats this
    engine targets (`CLAUDE.md`: "Legality is clamped to standard, pioneer,
    and modern").

    **Banned counts as existing.** A banned card was legal once, was printed
    into that format's card pool, and a banned-but-printed card can still be
    played in a non-sanctioned pod running the format's card list (and may be
    unbanned) - CR 100.6's list of "banned" and "restricted" is Wizards
    tournament policy, not a rule about which cards a format's rules text
    ever has to execute. `Legality.NOT_LEGAL` is the only status this
    treats as "never printed for this format" (`Legalities`'s own docstring:
    Scryfall's fourth status, `restricted`, applies only to Vintage, which
    this model does not track at all). So the check is simply "not
    not_legal, in any of the three", not "legal".

    This is the sweep's own honesty gate, not an engine rule: it decides
    which cards the coverage reports hold the engine to account for, per the
    owner rule that every card legal in Modern, Pioneer or Standard must be
    fully supported - never silently excused because a coverage report
    happened to stop asking about it.
    """
    legalities = printing.legalities
    return any(
        legality is not Legality.NOT_LEGAL
        for legality in (legalities.modern, legalities.pioneer, legalities.standard)
    )


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
        # CR 702.124a (verified 2026-09-23, `mise run rules:find 702.124a`):
        # "Partner abilities are keyword abilities that modify the rules for
        # deck construction in the Commander variant (see rule 903), and they
        # function before the game begins. ... The partner abilities are:
        # partner, partner-[text], partner with [name], choose a Background,
        # and Doctor's companion." Both entries below are that same family:
        # inert outside a Commander deck's construction step, and this
        # engine targets Modern/Pioneer/Standard only (`in_target_formats`
        # above), none of which is Commander. Neither reported card (Sakashima
        # of a Thousand Faces, Silas Renn, Seeker Adept, Gut, True-Soul
        # Zealot) is legal in any of the three anyway, so this is a
        # documentation choice, not a live gap - see F5 in the flow-2 brief.
        "partner",
        "choose a background",
    }
)

#: CR 207.2c (verified 2026-09-23, `mise run rules:find 207.2c`; local CR
#: copy effective 2026-09-25): "An ability word appears in italics at the
#: beginning of some abilities. Ability words are similar to keywords in that
#: they tie together cards that have similar functionality, but they have no
#: special rules meaning and no individual entries in the Comprehensive
#: Rules." This is that list, verbatim and complete (60 entries) - not the
#: eight this sweep happened to see on the pool one day, which is how the
#: list went stale before: `converge`, `revolt`, `undergrowth`, `domain` and
#: `threshold` were added only after they were individually reported as
#: ignored *keywords*, and every one of those reports was this table's own
#: false positive, not a real gap.
#:
#: A card carrying an ability word is not carrying an unexecuted keyword, so
#: listing one here is never a coverage claim - the clause under the word is
#: judged on its own by `classify_card`, exactly like any other. Three of the
#: original four have their clause read by a real parser today
#: (`_parse_converge_exile_by_colors_spent`, `Game.revolt_active_for` with
#: `_parse_revolt_destroy_or_exile_clause`, and
#: `_parse_undergrowth_pump_and_fight_clause`); Territorial Kavu's domain
#: characteristic-defining ability still reports as a dead clause below
#: rather than disappearing with the word, which is the point - membership
#: here only silences the *keyword* report, never `classify_card`.
#:
#: Two entries need normalising before a lookup matches Scryfall's own
#: spelling, both handled by `_normalized_ability_word` below rather than by
#: listing every variant here: CR prints "descend 4" and "descend 8" as two
#: separate list entries (the two counts a card can actually print,
#: Akawalli's own "Descend 8" among them), collapsed to one `descend` entry
#: here with the trailing count stripped at lookup time; and CR's own
#: `council's dilemma` uses a straight apostrophe while Scryfall's printed
#: keyword line uses a curly one, normalised the same way.
ABILITY_WORDS = frozenset(
    {
        "adamant",
        "addendum",
        "alliance",
        "battalion",
        "bloodrush",
        "celebration",
        "channel",
        "chroma",
        "cohort",
        "constellation",
        "converge",
        "council's dilemma",
        "coven",
        "delirium",
        "descend",
        "disappear",
        "domain",
        "eerie",
        "eminence",
        "enrage",
        "fateful hour",
        "fathomless descent",
        "ferocious",
        "flurry",
        "formidable",
        "grandeur",
        "hellbent",
        "heroic",
        "imprint",
        "infusion",
        "inspired",
        "join forces",
        "kinship",
        "landfall",
        "lieutenant",
        "magecraft",
        "metalcraft",
        "morbid",
        "opus",
        "pack tactics",
        "paradox",
        "parley",
        "radiance",
        "raid",
        "rally",
        "renew",
        "repartee",
        "revolt",
        "secret council",
        "spell mastery",
        "strive",
        "survival",
        "sweep",
        "tempting offer",
        # fra-final-audit batch A item 2: Reality Fracture's "Threshold —
        # <condition>." (Barbarian Ring, Werebear, Loot the Anomaly, Null
        # Summoner, Proft Sinister Mastermind). `machines/casting.py`'s own
        # `_CANNOT_CAST_UNLESS_RE` comment: "The ability word ('Threshold')
        # carries no rules meaning of its own (CR 207.2c) and is not part
        # of the match; the restriction is the sentence after it." The
        # labelled clause is a cast restriction, an "Activate only if"
        # activation gate, or a static conditional pump depending on the
        # card - each already read by its own unrelated, generic parser,
        # not by any code keyed on the word "Threshold" itself.
        "threshold",
        "undergrowth",
        "valiant",
        "vivid",
        "void",
        "will of the council",
    }
)


def _normalized_ability_word(word: str) -> str:
    """`word` (a Scryfall `keywords` entry, or a flavor-word label read off a
    printed ability line) prepared for a lookup in `ABILITY_WORDS` - CR
    207.2c's own spelling, lowercased, with the two mismatches
    `ABILITY_WORDS`'s own docstring names resolved: a curly apostrophe
    swapped for the straight one CR's plain text uses (`council's dilemma`),
    and a trailing printed count stripped so `descend 4`/`descend 8` both
    reach the collapsed `descend` entry (CR 207.2c lists the two counts
    separately; the count is descend's own designated amount, CR 700.11, not
    part of the ability word's name).
    """
    normalized = word.strip().lower().replace("’", "'")
    return re.sub(r"\s+\d+$", "", normalized)


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
            # Hexproof: `Game.hexproof_refusal`, reached from
            # `TargetingProfile.check` for spells and abilities alike.
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

    # Tiered (CR 702.183a: "Choose one. As an additional cost to cast this
    # spell, pay the cost associated with that mode.") is a CR 700.2h modal
    # keyword: its reminder text ("Choose one additional cost.") and each
    # tier's own printed cost are both read by `machines/modes.modal_profile`
    # into `Mode.cost`, the same field Spree below fills. Conditioned on the
    # profile actually parsing (`profile.understood`) *and* on some mode
    # actually carrying a cost, never on the bare keyword name alone: a
    # Tiered card this parser could not read leaves nothing for
    # `Casting.choose_modes` to act on, and reporting it executed anyway
    # would be exactly the false "registry membership" claim this sweep
    # exists to catch. `tests/scenarios/test_tiered.py` proves it live.
    if (
        profile is not None
        and profile.understood
        and any(mode.cost is not None for mode in profile.modes)
        and any(k.lower() == "tiered" for k in printing.keywords)
    ):
        found["tiered"] = "machines/modes.py (tiered modal profile, CR 702.183a)"

    # Spree (CR 702.172a: "Choose one or more modes. As an additional cost to
    # cast this spell, pay the costs associated with those modes.") is the
    # identical CR 700.2h shape as Tiered, read by the same
    # `modal_profile`/`Mode.cost` pair - only the keyword name and the "+"
    # bullet (CR 702.172b) differ. Same per-card gate as Tiered above.
    # `tests/scenarios/test_spree_bullets.py` proves it live.
    if (
        profile is not None
        and profile.understood
        and any(mode.cost is not None for mode in profile.modes)
        and any(k.lower() == "spree" for k in printing.keywords)
    ):
        found["spree"] = "machines/modes.py (spree modal profile, CR 702.172a)"

    # Waterbend (CR 701.67a: "'Waterbend [cost]' means 'Pay [cost]. For each
    # generic mana in that cost, you may tap an untapped artifact or creature
    # you control rather than pay that mana.'") is an action word introducing
    # an *ability's* cost, not a modal spell shape - `waterbend_mana_cost`
    # (`machines/cost.py`) is the reader, `Game.activation_cost`'s own
    # `CostKind.OTHER` fold-in is what turns the phrase into a payable total,
    # and `machines/objects_as_costs.waterbend` is CR 701.67b's alternate tap
    # method against an open `CostPayment`. Conditioned on some ability's own
    # printed cost actually matching the "Waterbend [cost]" shape, never on
    # the bare keyword name alone - the same per-card discipline Endure and
    # Recruit above use. `tests/scenarios/test_waterbend.py` proves it live,
    # including CR 701.67b's own bound and CR 701.67c's "whenever you
    # waterbend" trigger (`ExtraTriggerEvent.WATERBENDS`, `machines/
    # triggers.py`).
    if any(k.lower() == "waterbend" for k in printing.keywords):
        for ability in parse_abilities(printing):
            cost = getattr(ability, "cost", None)
            if cost is not None and waterbend_mana_cost(cost) is not None:
                found["waterbend"] = (
                    "machines/objects_as_costs.py (waterbend), "
                    "models/game.py (Game.activation_cost, CR 701.67a)"
                )
                break

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

    # Monstrosity (CR 701.37a: "'Monstrosity N' means 'If this permanent
    # isn't monstrous, put N +1/+1 counters on it and it becomes
    # monstrous.'") is a keyword *action* read straight out of an activated
    # ability's own effect text by `_parse_monstrosity_clause`, the same way
    # Endure and Adapt are above - never a `KeywordCastOption` (it changes
    # nothing about how the ability is cast) and never one of `machines/
    # keywords.py`'s cost:effect expansions (its cost is whatever the card
    # prints, not derived from the keyword name). `substitute_x(..., 1)`
    # mirrors what `activated_effect_for` does with a real announced X at
    # runtime, so a "Monstrosity X" printing (Polukranos, World Eater) reads
    # as registered the same way a fixed "Monstrosity N" one does.
    if any(k.lower() == "monstrosity" for k in printing.keywords):
        for ability in parse_abilities(printing):
            effect_text = getattr(ability, "effect", None)
            if effect_text is None:
                continue
            if _parse_monstrosity_clause(substitute_x(effect_text, 1)) is not None:
                found["monstrosity"] = "machines/effects.py (_parse_monstrosity_clause, CR 701.37a)"
                break

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

    # Compleated (CR 702.150a) is the identical "read off the keyword, not a
    # parsed sentence" shape as Sunburst just above - a planeswalker's own
    # entering-loyalty replacement, read by `machines/replacement.py`'s
    # `_self_enters_modifiers`/`_compleated_modifier`. `ABILITY_WORDS` used to
    # carry "Compleated" too (CR 207.2c's list does not - it is a keyword
    # ability, CR 702.150), which silently satisfied this same check for the
    # wrong reason; named here by hand now that it is a real one.
    if any(k.lower() == "compleated" for k in printing.keywords):
        found["compleated"] = "machines/replacement.py (_compleated_modifier, CR 702.150a)"

    # Tribute (CR 702.104a) is the same "read off the keyword" entering
    # replacement as Sunburst and Compleated: `_tribute_modifier` asks the
    # chosen opponent and places the counters as theirs (CR 702.104b's "if
    # tribute wasn't paid" reads that back).
    if any(k.lower() == "tribute" for k in printing.keywords):
        found["tribute"] = "machines/replacement.py (_tribute_modifier, CR 702.104a)"

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

    # fra-final-audit batch A item 2: four more keywords with real, named
    # machinery of their own that no branch above happens to ask about -
    # named here by hand, the same way suspend/fuse/companion are above.

    # Prepared (CR 722, Reality Fracture) is a permanent's own designation,
    # not a `KeywordCastOption` or an additional cost: `Game.become_prepared`/
    # `become_unprepared` track the exile copy and the cast permission it
    # grants (CR 722.3d), off `machines/replacement.py`'s `ENTERS_PREPARED`
    # replacement effect. `tests/scenarios/test_prepare.py` proves it live.
    if any(k.lower() == "prepared" for k in printing.keywords):
        found["prepared"] = "models/game.py (become_prepared/become_unprepared, CR 722)"

    # Behold (CR 701.4a) is a keyword action used inside an additional
    # cost's own printed phrase ("behold a Jace"), not a `KeywordCastOption`
    # either - `machines/cost.py`'s `behold_cost`/`_PHRASE_BEHOLD` is the
    # real machinery, reached through `Casting`'s ordinary additional-cost
    # reading rather than through anything this sweep otherwise asks about.
    # `tests/scenarios/test_behold.py` proves it live.
    if any(k.lower() == "behold" for k in printing.keywords):
        found["behold"] = "machines/cost.py (behold_cost, CR 701.4a)"

    # Exhaust (CR 702.177a) is "activate only once", enforced by
    # `Game.exhausted` gating `activate_ability`/`legal_actions` off
    # `ActivatedAbility.exhaust` - a runtime restriction with no
    # `KeywordCastOption`/`ADDITIONAL_COST_KEYWORDS`/`TIMING_KEYWORDS` shape
    # at all. `tests/scenarios/test_exhaust.py` proves it live.
    if any(k.lower() == "exhaust" for k in printing.keywords):
        found["exhaust"] = "models/game.py (Game.exhausted, ActivatedAbility.exhaust, CR 702.177a)"

    # Proliferate (CR 701.34a) is a keyword action read off a spell's,
    # trigger's, or activated ability's own resolution text by
    # `machines/effects._parse_proliferate_clause`, dispatched the ordinary
    # way through `effect_for`/`trigger_effect_for`/`activated_effect_for` -
    # but this sweep's keyword report never asked that dispatch chain about
    # a keyword *name*, only about a fixed set of machine-specific branches,
    # so a card whose only rules text is the bare word "Proliferate." (or
    # whose clause is otherwise fully read) still reported the keyword
    # itself as unexecuted. `tests/scenarios/test_proliferate.py` proves it
    # live.
    if any(k.lower() == "proliferate" for k in printing.keywords):
        found["proliferate"] = "machines/effects.py (_parse_proliferate_clause, CR 701.34a)"

    # Shroud (CR 702.18a: "This permanent or player can't be the target of
    # spells or abilities.") has no printed parameter of its own to parse -
    # unlike endure/recruit below, the keyword name *is* the whole ability,
    # so the keyword's presence is already the fact the machinery reads:
    # `Game.shroud_refusal` and `TargetingProfile._check_shroud` both read it
    # straight off `has_keyword`, the same computed-board reader every other
    # keyword check in `models/game.py` already uses. Not a
    # `TARGET_LEGALITY_KEYWORDS` entry like Hexproof: shroud has no
    # controller exception (CR 702.18b), so it is refused at the *target*
    # rather than at announcement, through a different function.
    # `tests/scenarios/test_shroud.py` proves it live.
    if any(k.lower() == "shroud" for k in printing.keywords):
        found["shroud"] = (
            "models/game.py (Game.shroud_refusal), "
            "machines/targeting.py (TargetingProfile._check_shroud, CR 702.18a)"
        )

    # Hexproof from (CR 702.11d: "This permanent can't be the target of
    # [quality] spells your opponents control or abilities your opponents
    # control from [quality] sources.") is enforced by `Game.hexproof_refusal`
    # - the one hexproof check `TargetingProfile.check`, the live candidate
    # lists and `Game.legal_target`'s CR 608.2b recheck all ask. It is
    # registered only when the printed text really carries a quality the
    # reader splits out (`hexproof_abilities_in`), never on the keyword
    # alone. `tests/scenarios/test_hexproof_abilities.py` proves it live.
    if any(k.lower() == "hexproof from" for k in printing.keywords):
        _, qualities = hexproof_abilities_in(
            printing.front_oracle_text.splitlines(), keyword_lines_only=False
        )
        if qualities:
            found["hexproof from"] = "models/game.py (Game.hexproof_refusal, CR 702.11d)"

    # Split second (CR 702.61a: "As long as this spell is on the stack,
    # players can't cast other spells or activate abilities that aren't mana
    # abilities.") is the identical shape to shroud above: no printed
    # parameter, so the keyword's presence is the whole fact -
    # `has_split_second` (`machines/casting.py`) is the canonical reader
    # `split_second_restriction_source` itself calls.
    # `tests/scenarios/test_split_second.py` proves it live.
    if has_split_second(printing):
        found["split second"] = "machines/casting.py (split_second_restriction_source, CR 702.61a)"

    # Endure (CR 701.63a: "... that permanent's controller creates an N/N
    # white Spirit creature token unless they put N +1/+1 counters on that
    # permanent.") *does* have a printed parameter (the count), so - unlike
    # shroud/split second above - presence of the keyword proves nothing
    # about whether *this* card's own clause is the shape
    # `machines/effects._parse_endure_clause` actually reads: substituting a
    # probe value for a bare "X" (`substitute_x`, the same CR 107.3a
    # substitution `classify_clauses` already performs) mirrors what the real
    # engine does before ever trying the parser, and only a real match
    # registers the keyword. `tests/scenarios/test_endure.py` proves it live.
    if any(k.lower() == "endure" for k in printing.keywords):
        for ability in parse_abilities(printing):
            text = getattr(ability, "effect", None) or ability.text
            if _parse_endure_clause(substitute_x(text, 1)) is not None:
                found["endure"] = "machines/effects.py (_parse_endure_clause, CR 701.63a)"
                break

    # Recruit (CR 701.70a: "Draw a card, then discard a card. If you
    # discarded a nonland card this way, create a 1/1 white Human Soldier
    # creature token.") is most often the bare-word keyword-action shape
    # ("Recruit."), read by `machines/effects._parse_recruit_clause` off
    # whichever ability's own text carries it - gated on that parser actually
    # matching *this* card's clause, the same per-card discipline endure
    # above uses, not on the keyword name by itself. Sound the Trumpets'
    # own "Counter target spell. If that spell's mana value was 2 or less,
    # recruit." is the second shape (CR 400.7 anaphora gating the same
    # keyword action), read by `_parse_counter_then_recruit_by_mana_value_
    # pair` as a clause *pair* rather than a lone clause, so it needs its own
    # check. `tests/scenarios/test_recruit.py` proves both live.
    if any(k.lower() == "recruit" for k in printing.keywords):
        for ability in parse_abilities(printing):
            text = getattr(ability, "effect", None) or ability.text
            if _parse_recruit_clause(text, for_spell=False) is not None:
                found["recruit"] = "machines/effects.py (_parse_recruit_clause, CR 701.70a)"
                break
            clauses = split_effect_clauses(text)
            for_spell = ability.kind is AbilityKind.STATIC
            if any(
                _parse_counter_then_recruit_by_mana_value_pair(
                    clauses[index], clauses[index + 1], for_spell=for_spell
                )
                is not None
                for index in range(len(clauses) - 1)
            ):
                found["recruit"] = (
                    "machines/effects.py "
                    "(_parse_counter_then_recruit_by_mana_value_pair, CR 701.70a)"
                )
                break

    # Goad (CR 701.15a) is a keyword action with three printed subjects - a
    # target phrase and a creature group (`machines/effects._parse_goad_
    # clause`), or an object anaphor after an earlier sentence ("Goad it.",
    # `_parse_referent_object_clause`). Gated on one of those actually
    # reading one of *this* card's clauses, the same per-card discipline
    # endure/recruit above use. `tests/scenarios/test_goad.py` proves it live,
    # the CR 508.1d attack requirement included.
    if any(k.lower() == "goad" for k in printing.keywords):
        for ability in parse_abilities(printing):
            text = getattr(ability, "effect", None) or ability.text
            for_spell = ability.kind is AbilityKind.STATIC
            if any(
                clause.lower().startswith("goad")
                and (
                    _parse_goad_clause(clause, for_spell=for_spell) is not None
                    or _parse_referent_object_clause(clause) is not None
                )
                for clause in split_effect_clauses(text)
            ):
                found["goad"] = "machines/effects.py (_parse_goad_clause, CR 701.15a)"
                break

    # Ascend (CR 702.131a/b: "If [any time] you control ten or more
    # permanents and you don't have the city's blessing, you get the city's
    # blessing for the rest of the game.") has no printed parameter either -
    # the same shape as shroud/split second above, so the keyword's presence
    # is already what `machines/keywords.py`'s own `has_ascend`/
    # `_has_computed_ascend` (a permanent) and `ascend_as_a_spell_resolves`
    # (a spell, called from `models/game.py`) act on.
    #
    # This is the sweep-truth rewrite's own finding, not part of the brief's
    # planned six: `ABILITY_WORDS` used to carry a bare, uncited "ascend"
    # entry - unlike every other pre-existing entry there, which cites the
    # `knowledge_search` finding of no CR number and the parser that reads
    # its clause - and replacing that list with CR 207.2c's verbatim text
    # (which has no "ascend" in it at all) surfaced it as a false "ignored
    # keyword" the moment the bogus entry was gone. It is the identical
    # false-positive shape this sweep already warns about, just pointed the
    # other way: a stale table hid a real, already-built CR 702.131 keyword
    # ability instead of flagging a fake gap. `tests/scenarios/test_ascend.py`
    # proves it live.
    if any(k.lower() == "ascend" for k in printing.keywords):
        found["ascend"] = (
            "machines/keywords.py (has_ascend, _has_computed_ascend, "
            "ascend_as_a_spell_resolves, CR 702.131)"
        )

    # Storied (CR 702.195a) is ascend's twin: a static ability granting the
    # enduring story designation (CR 702.195b), which every "as long as you
    # have an enduring story" rider reads (`machines/designations.py`).
    if any(k.lower() == "storied" for k in printing.keywords):
        found["storied"] = "machines/keywords.py (grant_enduring_stories, CR 702.195)"

    # Explore (CR 701.44a: "Certain spells and abilities instruct a
    # permanent to explore.") is the bare-word keyword-action shape, read by
    # `machines/effects._parse_explores_clause` off whichever triggered,
    # activated, or spell text carries it - the generic "<subject>
    # explores[, then it explores again]" shape, registered once in
    # `_parse_mixed_clause` so all three contexts reach it. Gated on that
    # parser (or Amalia Benavides Aguirre's own dedicated whole-sentence one,
    # tried in the same order the real dispatch chain tries it) actually
    # matching *this* card's own text, the same per-card discipline
    # endure/recruit above use, not on the keyword name by itself.
    # `tests/scenarios/test_explore.py` proves it live.
    if any(k.lower() == "explore" for k in printing.keywords):
        candidates: list[tuple[str, bool]] = [
            (
                getattr(ability, "effect", None) or ability.text,
                ability.kind is not AbilityKind.STATIC,
            )
            for ability in parse_abilities(printing)
        ]
        profile = modal_profile(printing)
        if profile is not None and profile.understood:
            # A modal spell's own mode text (Over the Edge's second bullet)
            # never shows up in `parse_abilities` at all - modes are read by
            # `machines/modes.py`, not `machines/abilities.py` - so this asks
            # the same place the real dispatch chain (`resolve_modal_spell`
            # -> `parse_mode_effect`) reads each chosen mode's text from.
            for mode in profile.modes:
                mode_text, _ = strip_reminder_text(mode_effect_body(mode))
                candidates.append((mode_text, False))
        elif not candidates:
            # A non-modal spell (Enter the Unknown) has no `parse_abilities`
            # entry either - its own resolution text is the printed oracle
            # text as a whole, the same thing `effect_for` reads.
            text, _ = strip_reminder_text(printing.oracle_text or "")
            candidates.append((text, False))
        for text, is_ability in candidates:
            if _parse_explores_then_conditional_mass_destroy(text) is not None:
                found["explore"] = (
                    "machines/effects.py "
                    "(_parse_explores_then_conditional_mass_destroy, CR 701.44a)"
                )
                break
            if _parse_explores_clause(text, for_spell=not is_ability) is not None:
                found["explore"] = "machines/effects.py (_parse_explores_clause, CR 701.44a-d)"
                break
            if is_ability and _parse_explores_clause(text, for_spell=True) is not None:
                # A targeted/"each ... you control" clause on a triggered or
                # activated ability (Miner's Guidewing's death trigger) reads
                # the same either way `for_spell` goes - only the self-only
                # subjects are gated on it - so this catches that shape too
                # without the ability/spell classification above having to
                # be exact.
                found["explore"] = "machines/effects.py (_parse_explores_clause, CR 701.44a-d)"
                break

    # Connive (CR 701.50a) is the same bare-word keyword-action shape as
    # explore: `machines/connive.parse_connive_clause`, registered once in
    # `_parse_mixed_clause`, gated on it matching this card's own text.
    # `tests/scenarios/test_connive.py` proves it live.
    if any(k.lower() == "connive" for k in printing.keywords):
        texts = [
            getattr(ability, "effect", None) or ability.text
            for ability in parse_abilities(printing)
            if ability.kind is not AbilityKind.STATIC
        ]
        if not texts:
            text, _ = strip_reminder_text(printing.oracle_text or "")
            texts.append(text)
        normalized = [
            _self_normalized_effect_text(
                printing.name, text, legendary=Supertype.LEGENDARY in printing.supertypes
            )
            for text in texts
        ]
        if mentions_connive(normalized):
            found["connive"] = "machines/connive.py (parse_connive_clause, CR 701.50a-f)"

    # Boast (CR 702.142a) adds "Activate only if this creature attacked this
    # turn and only once each turn" to the activated ability behind it, which
    # `Game.why_cannot_activate` enforces off the parsed ability word.
    if any(
        (getattr(ability, "ability_word", None) or "").lower() == "boast"
        for ability in parse_abilities(printing)
        if ability.kind is AbilityKind.ACTIVATED
    ):
        found["boast"] = "models/game.py (why_cannot_activate, CR 702.142a)"

    return found


#: CR 207.2d: "flavor words appear in italics at the beginning of some
#: abilities ... [and] have no special rules meaning". Scryfall lists a
#: mode's label as a keyword (Flash Thompson's "\u2022 Heckle \u2014 Tap target
#: creature."), but there is nothing for any machine to execute.
_FLAVOR_WORD_LABEL = re.compile(r"^\u2022\s*(?P<word>[^\u2014\n]+?)\s+\u2014\s+", re.MULTILINE)

#: CR 207.2d's *other* shape: an ability line labelled `<Label> \u2014 <text>`
#: with no bullet at all - Mister Negative's "Darkforce Inversion \u2014 When
#: Mister Negative enters, ..." and its like below. The em dash must have real
#: whitespace on both sides, which is deliberately what keeps this from ever
#: matching a printed keyword-reminder line: CR 702 keywords with a colon-like
#: printed cost use the em dash with **no** surrounding space at all
#: (Vexing Sphinx's "Cumulative upkeep\u2014Discard a card."), so that shape
#: never reaches this regex to begin with, on top of `CR_KEYWORD_NAMES`
#: catching it below a second time.
_FLAVOR_WORD_LINE = re.compile(r"^(?P<word>[^\u2014\n]+?)\s+\u2014\s+", re.MULTILINE)

#: CR 701's keyword actions and CR 702's keyword abilities, every numbered
#: section's own heading transcribed verbatim (verified 2026-09-23, `mise run
#: rules:find 701` and `rules:find 702`; local CR copy effective 2026-09-25),
#: skipping only each section's unnumbered introductory paragraph (701.1,
#: 702.1), which names no ability. Two CR headings each name a *pair* of
#: keywords joined by "and" ("Tap and Untap", "Daybound and Nightbound");
#: both the whole heading and its two halves are kept, since Scryfall prints
#: "Daybound" and "Nightbound" as two separate keyword-line labels, never the
#: combined CR heading.
#:
#: This is the second half of CR 207.2d's own test for a flavor word: a
#: flavor word "look[s] like" an ability word or keyword but "ha[s] no
#: special rules meaning" of its own, so the generalized flavor-word rule
#: below (`_FLAVOR_WORD_LINE`) must never fire on a label that actually *is*
#: one of these - Aerial Doombot's "Power-up \u2014 {5}{U}: ..." is CR
#: 702.193's own keyword line, not a flavor word, even though its shape
#: (label, space, em dash, space, text) is identical to Darkforce Inversion's.
_CR_KEYWORD_HEADINGS: tuple[str, ...] = (
    "Activate",
    "Attach",
    "Behold",
    "Cast",
    "Counter",
    "Create",
    "Destroy",
    "Discard",
    "Double",
    "Triple",
    "Exchange",
    "Exile",
    "Fight",
    "Goad",
    "Investigate",
    "Mill",
    "Play",
    "Regenerate",
    "Reveal",
    "Sacrifice",
    "Scry",
    "Search",
    "Shuffle",
    "Surveil",
    "Tap and Untap",
    "Transform",
    "Convert",
    "Fateseal",
    "Clash",
    "Planeswalk",
    "Set in Motion",
    "Abandon",
    "Proliferate",
    "Detain",
    "Populate",
    "Monstrosity",
    "Vote",
    "Bolster",
    "Manifest",
    "Support",
    "Meld",
    "Exert",
    "Explore",
    "Assemble",
    "Adapt",
    "Amass",
    "Learn",
    "Venture into the Dungeon",
    "Connive",
    "Open an Attraction",
    "Roll to Visit Your Attractions",
    "Incubate",
    "The Ring Tempts You",
    "Face a Villainous Choice",
    "Time Travel",
    "Discover",
    "Cloak",
    "Collect Evidence",
    "Suspect",
    "Forage",
    "Manifest Dread",
    "Endure",
    "Harness",
    "Airbend",
    "Earthbend",
    "Waterbend",
    "Blight",
    "Heal",
    "Recruit",
    "Empower Jace",
    "Deathtouch",
    "Defender",
    "Double Strike",
    "Enchant",
    "Equip",
    "First Strike",
    "Flash",
    "Flying",
    "Haste",
    "Hexproof",
    "Indestructible",
    "Intimidate",
    "Landwalk",
    "Lifelink",
    "Protection",
    "Reach",
    "Shroud",
    "Trample",
    "Vigilance",
    "Ward",
    "Banding",
    "Rampage",
    "Cumulative Upkeep",
    "Flanking",
    "Phasing",
    "Buyback",
    "Shadow",
    "Cycling",
    "Echo",
    "Horsemanship",
    "Fading",
    "Kicker",
    "Flashback",
    "Madness",
    "Fear",
    "Morph",
    "Amplify",
    "Provoke",
    "Storm",
    "Affinity",
    "Entwine",
    "Modular",
    "Sunburst",
    "Bushido",
    "Soulshift",
    "Splice",
    "Offering",
    "Ninjutsu",
    "Epic",
    "Convoke",
    "Dredge",
    "Transmute",
    "Bloodthirst",
    "Haunt",
    "Replicate",
    "Forecast",
    "Graft",
    "Recover",
    "Ripple",
    "Split Second",
    "Suspend",
    "Vanishing",
    "Absorb",
    "Aura Swap",
    "Delve",
    "Fortify",
    "Frenzy",
    "Gravestorm",
    "Poisonous",
    "Transfigure",
    "Champion",
    "Changeling",
    "Evoke",
    "Hideaway",
    "Prowl",
    "Reinforce",
    "Conspire",
    "Persist",
    "Wither",
    "Retrace",
    "Devour",
    "Exalted",
    "Unearth",
    "Cascade",
    "Annihilator",
    "Level Up",
    "Rebound",
    "Umbra Armor",
    "Infect",
    "Battle Cry",
    "Living Weapon",
    "Undying",
    "Miracle",
    "Soulbond",
    "Overload",
    "Scavenge",
    "Unleash",
    "Cipher",
    "Evolve",
    "Extort",
    "Fuse",
    "Bestow",
    "Tribute",
    "Dethrone",
    "Hidden Agenda",
    "Outlast",
    "Prowess",
    "Dash",
    "Exploit",
    "Menace",
    "Renown",
    "Awaken",
    "Devoid",
    "Ingest",
    "Myriad",
    "Surge",
    "Skulk",
    "Emerge",
    "Escalate",
    "Melee",
    "Crew",
    "Fabricate",
    "Partner",
    "Undaunted",
    "Improvise",
    "Aftermath",
    "Embalm",
    "Eternalize",
    "Afflict",
    "Ascend",
    "Assist",
    "Jump-Start",
    "Mentor",
    "Afterlife",
    "Riot",
    "Spectacle",
    "Escape",
    "Companion",
    "Mutate",
    "Encore",
    "Boast",
    "Foretell",
    "Demonstrate",
    "Daybound and Nightbound",
    "Disturb",
    "Decayed",
    "Cleave",
    "Training",
    "Compleated",
    "Reconfigure",
    "Blitz",
    "Casualty",
    "Enlist",
    "Read Ahead",
    "Ravenous",
    "Squad",
    "Space Sculptor",
    "Visit",
    "Prototype",
    "Living Metal",
    "More Than Meets the Eye",
    "For Mirrodin!",
    "Toxic",
    "Backup",
    "Bargain",
    "Craft",
    "Disguise",
    "Solved",
    "Plot",
    "Saddle",
    "Spree",
    "Freerunning",
    "Gift",
    "Offspring",
    "Impending",
    "Exhaust",
    "Max Speed",
    "Start Your Engines!",
    "Harmonize",
    "Mobilize",
    "Job Select",
    "Tiered",
    "Station",
    "Warp",
    "\u221e (Infinity)",
    "Mayhem",
    "Web-slinging",
    "Firebending",
    "Sneak",
    "Increment",
    "Paradigm",
    "Power-up",
    "Teamwork",
    "Storied",
)

CR_KEYWORD_NAMES = frozenset(
    piece.strip().lower()
    for heading in _CR_KEYWORD_HEADINGS
    for piece in ((heading, *heading.split(" and ", 1)) if " and " in heading else (heading,))
)


def _oracle_texts(printing: Card) -> list[str]:
    """Every block of oracle text on this printing worth scanning for a
    flavor-word label - the top-level text when the printing has one, plus
    every face's own text for a split/transform/modal-DFC/prepare card, since
    a keyword can sit on a face that never reaches the (null) top-level
    `oracle_text` at all: Sephiroth, Fabled SOLDIER's Super Nova is on the
    back (transform) face only.
    """
    texts = [printing.oracle_text] if printing.oracle_text else []
    texts.extend(face.oracle_text for face in printing.card_faces or [] if face.oracle_text)
    return texts


def _is_flavor_word_label(printing: Card, label: str) -> bool:
    """Whether `label` (an em-dash-labelled line's own leading text) is CR
    207.2d's other flavor-word shape rather than a real keyword or ability
    word wearing the same "Label \u2014 text" clothing.

    Three conditions, all required: the label has to actually be one of this
    printing's own Scryfall `keywords` (never an arbitrary noun phrase this
    regex happened to catch), and it must be neither a CR 701/702 keyword
    name (`CR_KEYWORD_NAMES` - Power-up, Cumulative upkeep, a Ward label)
    nor a CR 207.2c ability word (`ABILITY_WORDS`).
    """
    lowered = label.strip().lower()
    if lowered not in {keyword.lower() for keyword in printing.keywords}:
        return False
    if lowered in CR_KEYWORD_NAMES:
        return False
    return _normalized_ability_word(label) not in ABILITY_WORDS


def flavor_words(printing: Card) -> frozenset[str]:
    """The words this printing uses only as a flavor-word label (CR 207.2d) -
    a mode's bulleted label, or an ordinary ability line labelled
    `<Label> \u2014 <text>` whose label is not a real keyword or ability word
    in disguise. See `_is_flavor_word_label` for the generalized shape's own
    guard.
    """
    found: set[str] = set()
    for text in _oracle_texts(printing):
        found.update(
            match.group("word").strip().lower() for match in _FLAVOR_WORD_LABEL.finditer(text)
        )
        for match in _FLAVOR_WORD_LINE.finditer(text):
            label = match.group("word").strip()
            if _is_flavor_word_label(printing, label):
                found.add(label.lower())
    return frozenset(found)


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
            or _normalized_ability_word(keyword) in ABILITY_WORDS
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
        "damage_then_group_grant_notice_only",
        "control_replacement_notice_only",
        "search_description_notice_only",
        "layer_effect_with_remainder_notice",
    }
)


def _leaves_you_and_group_player_half_unread(text: str) -> bool:
    """Whether `text` carries `_parse_you_and_group_gain_clause`'s own
    compound-subject shape (`machines/effects._YOU_AND_GROUP_SUBJECT_RE`) -
    "You and `<group>` you control gain `<keyword(s)>` until end of turn",
    Veil of Summer's own third sentence - with a player half that reader
    still cannot apply.

    That parser grants the group half for real, and (since flow 1 T12) also
    hands the player half ("You `<predicate>`") to `parse_clause_effect`,
    the same reader `_PLAYER_GAINS_HEXPROOF_RE` already proved reads "You
    gain hexproof from blue and from black until end of turn". When that
    reader understands the predicate too, both halves apply and this
    function must not downgrade the card - unlike `_NOTICE_STAND_IN_NAMES`
    above, this is not a permanent stand-in, only a fallback for whatever
    predicate shape the player-clause reader does not (yet) cover, still
    recorded as a `PlayerSubjectSplitNotice` rather than silently applied or
    dropped (see that model's own docstring). The dispatcher this clause
    goes through (`parse_mixed_effect_for_spell`/`parse_mixed_effect`)
    composes every clause of a mixed-effect card into one anonymous closure
    before handing it back, so an unread player half has no distinct
    `__name__` for `_dispatch_category`'s name check to see on its own - a
    card carrying this sentence would otherwise read `HANDLED` outright even
    when a whole sentence of it never runs.

    Split the same way `split_effect_clauses` splits a card's raw text for
    the real dispatchers, since the guard that keeps this subject whole as
    one clause (`_PLAYER_GROUP_SUBJECT_AND_RE`) only fires on exactly that
    shape - reading the unsplit text directly would miss it whenever the
    clause is not the whole card.
    """
    for clause in split_effect_clauses(text):
        match = _YOU_AND_GROUP_SUBJECT_RE.fullmatch(clause.strip())
        if match is None:
            continue
        player_text = f"You {match.group('predicate').strip()}"
        if parse_clause_effect(player_text) is None:
            return True
    return False


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


#: "..., where X is the amount of mana spent to cast that spell." - Aberrant
#: Manawurm's and Shantotto, Tactician Magician's own cast-trigger pump: CR
#: 601.2h's mana spent on the spell that *triggered* the ability, never CR
#: 107.3a's announced kind, so `_etb_x_candidates` never probes it and
#: `ability_text` reaches `_layer_category` unsubstituted. The exact same
#: strip-then-substitute `machines/effects._cast_trigger_mana_spent_x_
#: ability_text` runs at real resolution, mirrored here with a placeholder
#: value so this static sweep judges the shape the same way the engine does.
_CAST_TRIGGER_MANA_SPENT_WHERE_X_RE = re.compile(
    r",?\s*where x is the amount of mana spent to cast that spell", re.IGNORECASE
)


def _mana_spent_x_pump_probe_text(text: str | None) -> str | None:
    """`text` with `_CAST_TRIGGER_MANA_SPENT_WHERE_X_RE`'s own definition
    substituted for a placeholder value and dropped, or `None` when `text`
    carries no such definition (the common case, left for the caller's
    ordinary reading)."""
    if text is None or _CAST_TRIGGER_MANA_SPENT_WHERE_X_RE.search(text) is None:
        return None
    return substitute_x(_CAST_TRIGGER_MANA_SPENT_WHERE_X_RE.sub("", text), 1)


def _layer_category(printing: Card, ability_text: str | None = None) -> str | None:
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

    `ability_text` is the resolving ability's own, already X-substituted text
    - `machines/effects.create_continuous_effect_of_ability` passes exactly
    this to `ContinuousEffects.create` at real resolution now (Chatterfang,
    Squirrel General's "Sacrifice X Squirrels: Target creature gets +X/-X
    until end of turn", X announced in plain English rather than as a bare
    `{X}` mana symbol). Reading the card's own raw, unsubstituted text instead
    - the fallback below - cannot ever match a bare, non-numeric "X" the way
    `parsed_layer_effects` reads a pump's magnitude, so an activated ability
    with this shape scored SILENT here even once the real engine read it
    correctly; passing the same substituted text this sweep already computes
    for `activated_effect_for` keeps the two readings in step.
    """
    if ability_text is not None:
        probed = _mana_spent_x_pump_probe_text(ability_text)
        if probed is not None and parsed_layer_effects(probed, card_name=printing.name):
            return HANDLED
        if parsed_layer_effects(ability_text, card_name=printing.name):
            return HANDLED
        if looks_like_unparsed_layer_effect(
            ability_text, static_only=False, card_name=printing.name
        ):
            return NOTICE
        return None
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
    probed = _mana_spent_x_pump_probe_text(text)
    if (
        printing.name in LAYER_EFFECTS
        or parsed_layer_effects(text, card_name=printing.name)
        or (probed is not None and parsed_layer_effects(probed, card_name=printing.name))
    ):
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


def _self_enters_line_category(printing: Card, text: str) -> str | None:
    """Whether one static-ability paragraph carrying a CR 614.12 "enters"
    replacement shape (`ENTERS_KINDS` - "[this] enters with ...", "as [this]
    enters, ...", "[this] enters tapped", "... enters as a copy of ...") is
    one `machines/replacement.py`'s own `_self_enters_modifiers` really
    performs - asked of the *production* function itself, the same
    throwaway-real-permanent technique `_condition_can_fire` above already
    uses for a triggered ability's condition, rather than re-deriving what
    each shape means here and risking drifting from what the engine actually
    does. Before this, every card whose only static line was this shape came
    back `STATIC_UNAUDITED` regardless of whether the engine reads it at all
    - Walking Ballista's "This creature enters with X +1/+1 counters on it."
    and Steam Vents' "As this land enters, you may pay 2 life. If you don't,
    it enters tapped." included, both fully handled and neither credited.

    `None` when `text`'s own paragraph carries no self-referential
    `ENTERS_KINDS` clause at all - the caller falls through to its next
    check, same as every other row in `_static_ability_category`. Otherwise
    `HANDLED` when `_self_enters_modifiers`, run against one throwaway
    permanent as it enters, produces a performable entry whose own label text
    covers every self-referential `ENTERS_KINDS` sentence this paragraph
    parses into - `STATIC_UNAUDITED` (via `None`) for anything this cannot
    confirm, a board-state condition naming *other permanents*
    (`_enters_tapped_condition`'s land/subtype/life-total shapes) this
    synthetic single-permanent board cannot decide included, since inventing
    the rest of a board to force one of those true would not be honest.

    Morbid's own "if a creature died this turn" (CR 207.2c, CR 700.4 -
    Festerhide Boar) is different: it is not a fact about which permanents
    exist, it is `Game.creatures_died_this_turn`'s own running count, a
    plain per-turn history fact any real game can genuinely have - so this
    stages it true the same honest way a real game turn could, rather than
    leaving a fully-handled clause (`tests/scenarios/test_morbid.py`)
    unaudited for a synthetic board that happens to have no history yet.
    """
    effects = parse_replacement_effects(printing)
    self_kinds = [
        effect
        for effect in effects
        if effect.kind in ENTERS_KINDS
        and effect.self_replacement
        # `.raw` is "the whole ability paragraph as printed, reminder text
        # included" (`ReplacementEffect`'s own docstring), and `_static_
        # ability_category`'s own `text` argument is `parse_abilities`'s
        # line with the reminder already stripped by the identical `_strip_
        # reminder` used here - comparing the two on equal footing this way
        # is what makes a match possible at all regardless of how many
        # sentences the paragraph holds.
        #
        # Comparing against `.text` alone ("the one sentence this effect was
        # parsed from") instead broke every *multi*-sentence paragraph:
        # Blood Crypt's "As this land enters, you may pay 2 life. If you
        # don't, it enters tapped." parses into two effects, each `.text`
        # only its own half of the sentence, so neither ever equalled the
        # whole two-sentence `text` and both silently missed this match - 18
        # pool cards' worth of shocklands, Port Town, Sunken Citadel and
        # their like moved from `HANDLED` to `STATIC_UNAUDITED` this way,
        # with nothing about their actual runtime behaviour having changed.
        # Comparing against bare `.raw` (the shape before that regression)
        # broke the opposite case instead: every reminder-carrying
        # single-sentence paragraph ("enters prepared", CR 722.3a's own
        # reminder printed right after it) failed to match because `.raw`
        # still carried the reminder `text` did not. Stripping the reminder
        # off `.raw` before comparing answers both at once.
        and _strip_reminder(effect.raw)[0] == text.strip()
    ]
    if not self_kinds:
        return None
    if self_enters_effects_read(printing, self_kinds):
        # Performed whenever its own gate holds - a condition read as it
        # enters, CR 107.3m's X, a back-face land's payment - which the empty
        # board below cannot stage (`replacement.self_enters_effects_read`).
        return HANDLED
    try:
        game = Game(
            players=[Player(username="sweep_you"), Player(username="sweep_opp")],
            schema_version=Game.CURRENT_SCHEMA_VERSION,
        )
        if any(
            (effect.condition or "").strip().lower() == "a creature died this turn"
            for effect in self_kinds
        ):
            # Morbid's own condition (CR 207.2c) - a genuine per-turn history
            # fact (CR 700.4), staged true so this synthetic board can decide
            # it the same honest way a real game turn could (see this
            # function's own docstring).
            game.creatures_died_this_turn = 1
        state = _synthetic_permanent(
            printing, controller="sweep_you", token=False, tapped=False, counter_kind=None
        )
        state.bind_to_game(game)
        performable = _self_enters_modifiers(game, state)
    except Exception:
        # A printing this throwaway board cannot stage (a face this sweep's
        # own synthesis does not model, say) is left unaudited rather than
        # guessed at either way - the same fail-open-to-"don't know" posture
        # `_probe_cards` already takes.
        return None
    labels = " ".join(label for _suffix, _apply, label, _copy in performable)
    if all(effect.text.strip() in labels for effect in self_kinds):
        return HANDLED
    return None


def _enters_as_copy_line_category(printing: Card, text: str) -> str | None:
    """A static paragraph that is CR 614.1c's "enter as a copy of ...", judged
    by `machines/replacement.enters_as_copy_outcome` - the engine's own answer
    for what `_enters_as_copy` does with it - or `None` when the paragraph is
    not one (or carries a condition, which `_self_enters_modifiers` skips and
    `_self_enters_line_category` already answers for).

    Asked ahead of `missed_layer_shape` on purpose: a copy clause's "except
    it's a Cave in addition to its other types" / "and it has flying" tail is
    CR 707.9's modification of the copy itself, part of layer 1's copiable
    values, not a layer 4 or layer 6 effect a separate reader missed -
    Mockingbird and Echoing Deeps were reported `SILENT` on that tail alone.
    Equally, a copy clause whose candidate phrase the engine cannot read
    (Clever Impersonator's "any nonland permanent" before it was read) is
    `SILENT`, not credited `HANDLED` because `_self_enters_modifiers` lists
    every copy clause as performable.
    """
    copies = [
        effect
        for effect in parse_replacement_effects(printing)
        if effect.kind is ReplacementKind.ENTERS_AS_COPY
        and effect.self_replacement
        and effect.condition is None
        and _strip_reminder(effect.raw)[0] == text.strip()
    ]
    if not copies:
        return None
    outcomes = [enters_as_copy_outcome(effect) for effect in copies]
    for worst in (SILENT, NOTICE):
        if worst in outcomes:
            return worst
    return HANDLED


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
    if (
        additional_land_plays_of_line(text) is not None
        or conditional_additional_land_plays_of_line(text) is not None
        or plays_lands_from_graveyard_line(text)
    ):
        # CR 305.2 / CR 611.3d: `Game.land_allowance` and
        # `Game.graveyard_land_permission` read the line off the board.
        return HANDLED
    if keyword_machine.is_turn_face_up_ban_line(text):
        # CR 702.37e's special action refused: `keywords.turn_face_up_ban`,
        # read by `Game.why_cannot_turn_face_up` and `legal_actions`.
        return HANDLED
    if is_self_card_count_restriction_line(text):
        # CR 508.1c / 509.1b: `combat.self_card_count_restriction_refusal`
        # refuses the attack or block while the zone holds too few cards.
        return HANDLED
    if is_self_control_count_restriction_line(text):
        # CR 508.1c / 509.1b: `combat.self_control_count_restriction_refusal`
        # refuses the attack or block while you control too few of the type.
        return HANDLED
    if is_attack_cost_line(text):
        # CR 508.1h: `Game._pay_attack_costs` charges it on every declaration
        # (`combat.total_attack_cost`), gated on a designation or not.
        return HANDLED
    if reads_self_combat_restriction_line(text, printing.name):
        # CR 509.1a / 509.1b: `combat.evasion_restriction_refusal` and
        # `combat.self_block_restriction_refusal` refuse the block.
        return HANDLED
    if keyword_machine.is_equip_discount_for_this_line(text):
        # CR 601.2f via CR 602.2b: `keywords._equip_cost_reduction_for_target`
        # discounts every equip activation aimed at this creature.
        return HANDLED
    if keyword_machine.is_free_first_equip_line(text):
        # CR 118.9 / CR 702.6a: `keywords.free_first_equip_source` prices the
        # first equip activation each turn at {0}.
        return HANDLED
    if is_additional_trigger_line(text):
        # CR 603.2d: `triggers.additional_trigger_times` multiplies what an
        # entrance the cause names makes trigger.
        return HANDLED
    opening_hand = read_opening_hand_line(printing.name, text)
    if opening_hand is not None:
        # CR 103.6a/103.6b: `Game.take_opening_hand_actions` offers what reads
        # as an action and refuses, with an `OpeningHandNotice`, what does not.
        return HANDLED if isinstance(opening_hand, OpeningHandAction) else NOTICE
    if looks_like_unparsed_layer_effect(text, static_only=True, card_name=printing.name):
        return NOTICE
    if looks_like_unparsed_cost_modifier(text):
        return NOTICE
    if (
        off_battlefield_characteristics(
            text, printing.name, Supertype.LEGENDARY in printing.supertypes
        )
        is not None
    ):
        # CR 113.6c: "As long as `<this>` isn't on the battlefield, it's a
        # ..." - `CardState.types`/`.subtypes`/`.power`/`.toughness` apply it
        # in every zone but the battlefield (Grist, the Hunger Tide).
        return HANDLED
    copy_clause = _enters_as_copy_line_category(printing, text)
    if copy_clause is not None:
        return copy_clause
    if missed_layer_shape(text) is not None:
        return SILENT
    if player_keyword_grant_of_line(text) is not None:
        # CR 702.11c / CR 702.18a "or player": `Game.player_hexproof` and
        # `Game.player_has_shroud` read "You have hexproof." / "You have
        # shroud." off the battlefield on every targeting check.
        return HANDLED
    if is_attack_requirement_line(text, printing.name):
        # CR 508.1d: `Game.declare_attackers` enforces it.
        return HANDLED
    if is_group_attack_restriction_line(text):
        # CR 508.1c: `combat.group_attack_restriction_refusal` enforces it.
        return HANDLED
    if is_blocked_by_at_most_one_line(text, printing.name):
        # CR 509.1b: `combat.declaration_refusal` (via `blocked_by_at_most_
        # one_refusal`) enforces it.
        return HANDLED
    if reads_as_transforms_line(text):
        # CR 712.20: `effects.transform_permanent` applies it as it transforms.
        return HANDLED
    if reads_as_graveyard_cast_permission_line(text):
        # CR 601.3: `casting.granted_cast_options` hands out the once-each-turn
        # graveyard cast it grants (Rivaz of the Claw, Kess, Dissident Mage).
        return HANDLED
    if keyword_machine.as_enters_day_night(text, printing.name) is not None:
        # CR 731.1: "If it's neither day nor night, it becomes day as this
        # creature enters" - `keywords.apply_as_enters_day_night`, run by
        # `Game.enter_the_battlefield`.
        return HANDLED
    self_enters = _self_enters_line_category(printing, text)
    if self_enters is not None:
        return self_enters
    if reads_activation_rule_line(
        text, printing.name, legendary=Supertype.LEGENDARY in printing.supertypes
    ):
        # CR 602.5 (`Game.activation_prohibition`), CR 609.4 (`Game.
        # activation_haste_permission`), CR 606.3 (`Game._loyalty_instant_
        # speed_permitted`) and CR 609.4b (`Game.spends_mana_as_any_color`)
        # each enforce one of these where activation legality is decided.
        return HANDLED
    if performed_static_replacement_line(printing, text):
        # CR 614.1a: a replacement effect `machines/replacement.py` reads off
        # this very line and `applicable_effects` (or, for CR 106.12b's mana
        # production, `replace_mana_production`) performs from the battlefield.
        return HANDLED
    if performs_static_line(printing, text):
        # CR 614.1 / CR 615.1: a replacement or prevention effect that
        # `machines/replacement.py` compiles and `applicable_effects` applies
        # from the battlefield (Solphim's double, Crystal Barricade's
        # prevention, Mjolnir's "Double all damage ...").
        return HANDLED
    if reads_maximum_hand_size_line(text):
        # CR 402.2 / CR 613.11: `Player.cards_over_maximum_hand_size` reads
        # "Your maximum hand size is N." and "You have no maximum hand size."
        # off the battlefield, in timestamp order, for the cleanup discard.
        return HANDLED
    if is_player_rules_static_line(text):
        # CR 119.7 / CR 615.12: `Game.life_gain_prohibited` and
        # `Game.damage_cant_be_prevented` read these off the battlefield.
        return HANDLED
    if reads_player_rule_static_line(text) or reads_cant_enter_line(text):
        # CR 601.3 / 121.2b / 614.17d: `machines/casting_restrictions`'s
        # battlefield readers and `replacement._cant_enter_replacements`.
        return HANDLED
    if reads_self_cost_reduction_line(text) or reads_mandatory_additional_cost_line(text):
        # CR 601.2f / 118.8a: `Game.cost_reduction_for` and
        # `casting.mandatory_additional_costs` charge them on every cast.
        return HANDLED
    if _CANT_BE_COUNTERED_RE.match(text.strip()) or _CONDITIONAL_CANT_BE_COUNTERED_RE.match(
        text.strip()
    ):
        # CR 113.6g: `casting_restrictions.cannot_be_countered` and
        # `.conditionally_cannot_be_countered`, read by `Game.counter` at the
        # one place this ability actually functions.
        return HANDLED
    flash_condition = conditional_flash_condition(text)
    if flash_condition is not None and condition_is_readable(flash_condition):
        # CR 702.8a: `casting.why_cannot_cast_now` reads this exact line off
        # the spell's own text and asks `Game.condition_holds`.
        return HANDLED
    if reads_printed_zone_permission_line(printing, text):
        # CR 604.6: `casting._printed_zone_permissions` offers the keyword.
        return HANDLED
    if reads_companion_line(printing, text):
        # CR 702.139a: `companion.companion_condition_satisfied` reads it.
        return HANDLED
    if is_connive_replacement_line(text):
        # CR 614.1a/701.50a: `connive._replacement_draws` reads it off the
        # battlefield on every connive (Leader, Super-Genius).
        return HANDLED
    if Game.reads_enforced_static_line(text, printing.name):
        # `Game`'s own battlefield readers: look at the top card any time,
        # play lands from the top, a granted improvise, The Scarlet Witch's
        # power-scaled reduction, the power-up discount and extra activation,
        # and the legendary-count power CDA.
        return HANDLED
    flash_grant = Game.flash_grant_condition_of_line(text)
    if flash_grant is not None and (not flash_grant or condition_is_readable(flash_grant)):
        # `Game.has_static_spells_flash_grant` reads it off the battlefield
        # and asks `condition_holds` about an "as long as" condition.
        return HANDLED
    if enters_with_counters_pronoun_fallback(text) is not None:
        # `Game.enter_the_battlefield` places the counters "on him/her"
        # names when the ordinary "enters with" reader placed none.
        return HANDLED
    if conditional_group_keyword_grant_of_line(text) is not None:
        # `Game._player_static_keyword_grants` (the player half) and
        # `Game._group_keyword_grants_for` (the other creatures) read it off
        # the battlefield while the named counter is there.
        return HANDLED
    if reads_or_pay_additional_cost_line(text):
        # `casting.mandatory_additional_costs` charges either half.
        return HANDLED
    if static_free_cast_grant(text) is not None:
        # CR 118.9: "you may cast ... without paying its mana cost" off a
        # permanent (Omniscience; Zaffai and the Tempests' once each turn) -
        # `casting.static_free_cast_grants` offers it as an alternative cost
        # and `casting.static_free_cast_refusal` enforces its limits.
        return HANDLED
    if reads_spell_keyword_grant_line(text):
        # CR 604.2: "<quality> spells you cast have storm/cascade/affinity/
        # casualty" and "<quality> cards in your hand have miracle" -
        # `machines/spell_grants.py` hands the keyword to the machine that
        # executes the printed one (triggers, `Casting.total_cost`,
        # `Casting.pay_casualty`, `Game._offer_miracle_reveal`).
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
    if all(
        parse_mode_effect(mode, 0) is not None
        or _parse_mode_with_shared_verb_fallback(mode, modal.instruction) is not None
        for mode in modal.modes
    ):
        return HANDLED
    return NOTICE


def _modal_trigger_category(effect_text: str, *, card_name: str | None = None) -> str | None:
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

    Each mode is tried through the exact three-reader fallback chain
    `_resolve_modal_triggered_ability_clause` itself runs, in the same
    order - `parse_mixed_effect`, then `_compose_layer_effect_with_
    remainder_for_ability_mode`, then `_parse_where_x_is_continuous_effect`
    - not `parse_mixed_effect` alone. Yuriko, Hope from the Shadows' mode 1
    ("... where X is the number of cards in your graveyard.") is CR 107.3f's
    own X, unreadable to `parse_mixed_effect` (there is no substituted
    value for it to read) and only readable to the third fallback - calling
    just the first misreported a mode the engine genuinely runs
    (`tests/scenarios/test_modal_mode_composition.py::
    test_yuriko_mode_one_shrinks_by_the_graveyard_count`) as unhandled.
    """
    profile = modal_trigger_profile(effect_text)
    if profile is None:
        return None
    if all(
        _first_reading(mode_effect_body(mode), card_name=card_name) is not None
        for mode in profile.modes
    ):
        return HANDLED
    return NOTICE


def _first_reading(mode_text: str, *, card_name: str | None = None) -> object | None:
    """The first of `_resolve_modal_triggered_ability_clause`'s own three
    fallback readers, in its own order, that reads `mode_text` - or `None`
    when none of them do. Factored out so `_modal_trigger_category` can
    never drift from the real dispatch's fallback order.

    Tried again, once, on `card_name`'s own CR 201.5 self-normalized text
    (Gollum, Riddle Master's own "Put a +1/+1 counter on Gollum." - a bare
    legendary first-name self-reference bulleted modes print exactly the way
    an ordinary triggered ability's body would, but which none of the three
    fallback readers themselves normalize) when the raw text reads nothing -
    the identical second pass `trigger_effect_for` already gives an ordinary
    (non-modal) triggered ability's own text.
    """
    for reader in (
        counter_resolution_text,
        parse_mixed_effect,
        _compose_layer_effect_with_remainder_for_ability_mode,
        _parse_where_x_is_continuous_effect,
    ):
        result = reader(mode_text)
        if result is not None:
            return result
    if card_name is None:
        return None
    normalized = _self_normalized_effect_text(card_name, mode_text)
    if normalized == mode_text:
        return None
    for reader in (
        counter_resolution_text,
        parse_mixed_effect,
        _compose_layer_effect_with_remainder_for_ability_mode,
        _parse_where_x_is_continuous_effect,
    ):
        result = reader(normalized)
        if result is not None:
            return result
    return None


def _dispatch_category(effect: object, printing: Card, ability_text: str | None = None) -> str:
    """What actually happens if `effect` - what a real dispatcher just
    returned for this card - runs: a real effect, a fail-closed notice, or
    nothing at all. `effect` is always the literal object `effect_for`,
    `trigger_effect_for` or `activated_effect_for` returned, so this never
    re-derives what those functions already decided - it only reads the
    shape of their answer.

    `ability_text` is forwarded to `_layer_category` unchanged - see that
    function's own docstring for why an activated ability's X-substituted
    text, not the card's raw printed one, is what the real engine reads.
    """
    if effect is None:
        return SILENT
    if effect is create_continuous_effect or effect is create_continuous_effect_of_ability:
        # `_layer_category` never actually falls through to `None` from this
        # path - `looks_like_unparsed_layer_effect`'s own regex is a superset
        # of the one that routed here in the first place - but SILENT is the
        # right default if it ever did, not an optimistic HANDLED.
        return _layer_category(printing, ability_text) or SILENT
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
    for printing in _probe_pool().values():
        for subtype in printing.subtypes:
            if len(index[subtype]) < 5:
                index[subtype].append(printing)
    return {subtype: tuple(cards) for subtype, cards in index.items()}


@cache
def _cards_by_type() -> dict[Type, tuple[Card, ...]]:
    """The same idea as `_cards_by_subtype`, keyed by card type."""
    index: dict[Type, list[Card]] = defaultdict(list)
    for printing in _probe_pool().values():
        for card_type in printing.types:
            if len(index[card_type]) < 5:
                index[card_type].append(printing)
    return {card_type: tuple(cards) for card_type, cards in index.items()}


def _numeric_stat(value: str | None) -> int | None:
    """A creature's printed power/toughness (CR 208.1) as a plain int, or
    `None` for a variable one ("*", "1+*") this closure cannot compare
    numerically - Scryfall (and this engine's own `Card.power`/`.toughness`)
    keeps both as strings for exactly that reason."""
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


@cache
def _cards_by_power_or_toughness(stat: str, direction: str, threshold: int) -> tuple[Card, ...]:
    """A handful of real creature printings whose power and/or toughness
    actually satisfies this exact numeric comparison (CR 208.1) - what
    `_probe_cards` reaches for on top of `_cards_by_type`'s own capped,
    stat-blind first five creatures, which are never guaranteed to include
    one small or large enough to matter. Tetsuko Umezawa, Pursuer's own
    "with power or toughness 1 or less blocks" is not satisfied by any of
    `_cards_by_type()[Type.CREATURE]`'s first five real printings and never
    would be, since that cache is built with no stat in mind at all -
    `test_tetsuko_umezawa_pursuer_condition_now_fires` is the regression
    this closure exists to fix.
    """
    compare = operator.le if direction == "less" else operator.ge
    found: list[Card] = []
    for printing in _probe_pool().values():
        if Type.CREATURE not in printing.types:
            continue
        values = []
        if stat != "toughness":
            power = _numeric_stat(printing.power)
            if power is not None:
                values.append(power)
        if stat != "power":
            toughness = _numeric_stat(printing.toughness)
            if toughness is not None:
                values.append(toughness)
        if any(compare(value, threshold) for value in values):
            found.append(printing)
            if len(found) >= 5:
                break
    return tuple(found)


def _power_or_toughness_probe_cards(condition: str) -> list[Card]:
    """Real creature printings matching `condition`'s own "with power [or
    toughness] N or less/greater" qualifier (the same regex `machines.
    triggers._power_or_toughness_qualifier_holds` reads at resolution time),
    or an empty list when the condition names no such qualifier at all."""
    match = _CONDITION_POWER_OR_TOUGHNESS_QUALIFIER_RE.search(condition.lower())
    if match is None:
        return []
    threshold = parse_count(match.group("count"), article=False)
    if threshold is None:
        return []
    return list(
        _cards_by_power_or_toughness(match.group("stat"), match.group("direction"), threshold)
    )


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
    raw_subtype = (
        _condition_required_entering_subtype(condition)
        if entering
        else _condition_required_subtype(condition)
    )
    # `_required_entering_subtype` still returns one bare subtype string (no
    # pool printing lists more than one entering subtype yet); `_required_
    # subtype`/`_required_dying_subtype` read a comma/or-separated list (The
    # Great Goblin's own "Goblin, Orc, or Army") and so already return a
    # tuple. Normalised here so the probe below reads either the same way -
    # a real printing satisfying any one item is as good a reachability
    # witness as one satisfying all, since the condition itself is an "or".
    subtypes = (raw_subtype,) if isinstance(raw_subtype, str) else raw_subtype
    if subtypes is not None:
        found = [
            card
            for subtype in subtypes
            for card in _cards_by_subtype().get(subtype, ())
            if not forbidden & set(card.types)
        ]
        printing_subtypes = {s.lower() for s in printing.subtypes}
        if not found and not any(subtype.lower() in printing_subtypes for subtype in subtypes):
            return None
        candidates.extend(found)
    for card_type in required:
        found = [c for c in _cards_by_type().get(card_type, ()) if not forbidden & set(c.types)]
        if not found and card_type not in printing.types:
            return None
        candidates.extend(found)
    # Tetsuko Umezawa, Pursuer's own "with power or toughness 1 or less
    # blocks" needs a probe small enough to satisfy that qualifier, which
    # the plain type/subtype candidates above are never guaranteed to
    # include - see `_power_or_toughness_probe_cards`'s own docstring.
    candidates.extend(_power_or_toughness_probe_cards(condition))
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
    if ability.event is TriggerEvent.ATTACKS and is_batched_attack_condition(ability.condition):
        # "one or more <description> attack" counts a declared attack, which
        # this closure's synthetic board has none of - no occurrence to try.
        return None
    if (
        ability.event is TriggerEvent.ATTACKS
        and total_power_attack_threshold(ability.condition) is not None
    ):
        # "you attack with creatures with total power N or greater" (Desert
        # Were-Worm) is the identical subject-less CR 508.3d declaration
        # event as the batched shape just above, summed instead of
        # described - this closure's synthetic board never declares a real
        # attack either, so there is equally no occurrence to try here.
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
            # CR 506.5/506.6: a lone attacker (nothing else declared this
            # combat, and so also nothing else attacking the same defending
            # player) is an entirely ordinary board state, reachable in a
            # real game every time only one creature attacks - which is
            # exactly what every synthetic probe here already is, one
            # subject at a time. Jiang Yanggu, Alone's and Agents of
            # S.H.I.E.L.D.'s own "attacks [a player] alone" conditions would
            # otherwise never be tried true at all, since nothing here
            # simulates a whole combat to derive these two flags from.
            attacking_alone=ability.event is TriggerEvent.ATTACKS,
            attacking_player_alone=ability.event is TriggerEvent.ATTACKS,
            # Agent Maria Hill's own "becomes tapped to pay a teamwork
            # cost" (`GameEvent.tapped_for_teamwork`) - the same reasoning
            # as the two flags above: this synthetic probe never pays a
            # real cost to derive the flag from, so a `BECOMES_TAPPED`
            # occurrence is tried as though it always were one, the one way
            # the condition could ever be satisfied at all.
            tapped_for_teamwork=ability.event is TriggerEvent.BECOMES_TAPPED,
        )

    for host in source_variants:
        # A truly self-referential condition ("when this permanent enters
        # tapped") needs `event.subject_id == source.id` *exactly* - tried
        # against each tapped variant of the literal host object, not a twin.
        if condition_matches(game, ability, host, controller, event_for(host)):
            return True
    # CR 301.5a: "an equipped creature you control attacks" (Swordsman, Sharp
    # Scoundrel) is satisfied only by a subject an Equipment is attached to -
    # a real pool Equipment, moved onto each candidate in turn.
    equipment: CardState | None = None
    if ability.event is TriggerEvent.ATTACKS and "an equipped creature" in (
        ability.condition.lower()
    ):
        equipment_cards = _cards_by_subtype().get("Equipment", ())
        if equipment_cards:
            equipment = _synthetic_permanent(
                equipment_cards[0],
                controller="sweep_you",
                token=False,
                tapped=False,
                counter_kind=None,
            )
            equipment.bind_to_game(game)
            game.battlefield.append(equipment)
    # CR 303.4b/303.4m/CR 301.5a: "enchanted [object]"/"equipped creature"
    # reads `source.attached_to` (Ferocity of the Hunt's own "When enchanted
    # creature dies, ...", Hawkeye's Bow's "Whenever equipped creature
    # becomes tapped, ...", S.H.I.E.L.D. Spy Kit's "Whenever equipped
    # creature attacks alone, ..."), which nothing above ever sets - bound
    # here, one candidate at a time, so a condition naming either word is
    # tried the one way it can actually be satisfied: the subject really is
    # what this Aura/Equipment is attached to. Not narrowed to DIES any
    # more: BECOMES_TAPPED and ATTACKS both print this exact "equipped
    # creature" subject too, and `attached_to` means the identical thing to
    # `condition_matches` regardless of which event asks.
    # "an equipped creature you control attacks" is the equipment-block case
    # above - the source is not the Equipment, so it is not attached.
    attached_condition = equipment is None and (
        "enchanted" in ability.condition.lower() or "equipped" in ability.condition.lower()
    )
    for subject in states:
        if attached_condition:
            # `attached_to` is read off `attachment` (CR 301.5a) - not a
            # plain field of its own.
            source.attachment = TargetRef.to_card(subject)
        if equipment is not None:
            equipment.attachment = TargetRef.to_card(subject)
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


def _x_candidates(cost_or_mana_cost: str | None, *additional: str) -> tuple[int | None, ...]:
    """Every X value `classify_card` should try for one clause.

    Mirrors `models/game.py`'s own gate for a real resolution
    (`machines/cost.cost_announces_x` on the cost that pays for the clause):
    `None` - leave a bare "X" in the text alone, the same as a card that
    defines its own X in its rules text (CR 107.3f) rather than in its cost
    (CR 107.3a) - unless that cost has an X in it, `{X}` or Martyr of Sands's
    bare "Reveal X white cards", in which case every value in
    `_X_PROBE_VALUES` is tried.

    `additional` is zero or more further cost phrases to check the same way -
    a spell's own printed additional cost (CR 118.8a), which is not part of
    `mana_cost` at all. Soul Immolation's "As an additional cost to cast this
    spell, blight X" announces X with no `{X}` anywhere in its `{3}{R}{R}`
    mana cost; checking `mana_cost` alone scored its own damage sentence
    SILENT even once `Game.resolve_top` read the real engine's X correctly
    (`models/game.py`'s own matching widened check, right beside this one).
    """
    texts = (cost_or_mana_cost, *additional)
    if any(text and cost_announces_x(text) for text in texts):
        return _X_PROBE_VALUES
    return (None,)


def _etb_x_candidates(printing: Card, ability: TriggeredAbility) -> tuple[int | None, ...]:
    """Every X value `classify_clauses` should try for one enters-the-
    battlefield trigger's own effect text - CR 107.3m's gate, mirrored from
    `Game._effect_of` exactly: the ability's event is `ENTERS_THE_
    BATTLEFIELD`, its effect text carries a bare "X", and the permanent's
    own mana cost carries `{X}` (CR 107.3a).

    Fblthp, Knows the Way's own "search your library for up to X basic land
    cards" is unreadable to `trigger_effect_for` with a literal "X" left in
    it - the identical gap `_x_candidates` already closes for a spell face's
    own resolution text and `activated_effect_for` closes for an activated
    ability's announced X, but nothing here asked the same question of a
    triggered ability before this.

    Narrower than `_x_candidates`'s own `cost_announces_x` gate on purpose:
    a card that defines X in its own text instead (CR 107.3f - Craterhoof
    Behemoth's "where X is the number of creatures you control", Yuriko,
    Hope from the Shadows' identical shape) has no `{X}` in its own mana
    cost at all, so this never substitutes into it. `Game._effect_of`'s own
    gate is `"{X}" in (source.mana_cost or "")`, not the broader `cost_
    announces_x` an additional-cost phrase can also satisfy, because CR
    107.3m is scoped to "a value of X chosen for any of its costs" -
    exactly what a bare `{X}` in the mana cost already answers.
    """
    if (
        ability.event is TriggerEvent.ENTERS_THE_BATTLEFIELD
        and ability.effect
        and re.search(r"\bX\b", ability.effect)
        and "{X}" in (printing.mana_cost or "")
    ):
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
    - **Layout.PREPARE** (CR 722): the front face is an ordinary permanent
      and is cast normally, but the inset "prepare spell" (CR 722.2a,
      `card_faces[1]`) is never directly cast either - CR 722.3c's exile
      copy is what actually gets cast. Both are still returned here as
      probeable faces, the same as SPLIT's two castable halves: a classifier
      artifact this stream's survey flagged - reading the printing's blank
      top-level fields left the inset spell's own clause misfiled as a
      *static ability of the creature front*, so it was never dispatched as
      a spell at all and every prepare card's inset spell text read
      `static_unaudited` regardless of whether a real parser existed for it.
      The front is still an ordinary permanent (`is_permanent=True`); the
      inset spell reads its own type line, same as every other face here.
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
    if printing.layout is Layout.PREPARE and faces:
        return [
            SpellFace(
                face.name,
                face.oracle_text or "",
                face.mana_cost,
                bool(set(types_of(face.type_line or "")) & _PERMANENT_TYPES),
            )
            for face in faces
        ]
    if printing.layout is Layout.ADVENTURE and faces:
        # CR 715.1: an adventurer card's inset Adventure half (Bonecrusher
        # Giant // Stomp, Bilbo Baggins, Burglar // Take a Glance) is cast on
        # its own (CR 715.3: the player chooses to cast the card as an
        # Adventure) with only its own name, mana cost, and printed text
        # (CR 715.3b: "the spell has only its alternative characteristics"),
        # evaluating only the alternative characteristics to see if it can
        # be cast (CR 715.3a), the identical PREPARE
        # shape immediately above this branch: both faces are returned here,
        # each read off its own `card_faces` entry rather than off the
        # printing's blank top-level `oracle_text`/`mana_cost` (both `None`
        # for an adventure card's combined printing, same as every other
        # multi-faced layout `_spell_faces` already special-cases).
        #
        # Before this branch existed, an adventure card fell through to the
        # "everything else" arm below, which reads only `printing.front_
        # face` - the permanent creature half - so the Adventure half was
        # never offered to `effect_for` as a spell face at all. It still had
        # to go *somewhere*, and `parse_abilities` had already parsed its
        # printed text as a bare `AbilityKind.STATIC` line (nothing on an
        # Adventure's own sentence marks it triggered or activated) with
        # `ability.face` set to the Adventure half's name - so
        # `classify_clauses`' static-ability loop, gated only on `is_
        # permanent` (true here, since the *card* has a permanent front),
        # picked it up and judged it as though it were a static ability of
        # the creature. `_static_ability_category` cannot parse spell
        # resolution text as a layer effect, so every adventure face in the
        # pool read `static_unaudited` regardless of whether `effect_for`
        # could actually read it - Bonecrusher Giant // Stomp's own "Stomp
        # deals 2 damage to any target" included. `spell_only_face_names`
        # below (CR 712.11b's own comment) is what stops the now-correctly-
        # dispatched clause from *also* being scored a second time by that
        # static-ability loop.
        return [
            SpellFace(
                face.name,
                face.oracle_text or "",
                face.mana_cost,
                bool(set(types_of(face.type_line or "")) & _PERMANENT_TYPES),
            )
            for face in faces
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


def _other_face(printing: Card, ability: object) -> str | None:
    """The name of the face `ability` is printed on, when that is not the
    printing's front face - `None` for a front-face or single-faced ability.

    A permanent turned to its other face (CR 712.8d/712.8e) is named for that
    face, and `Game` dispatches its abilities under `CardState.name`, the up
    face's own name - "Ifrit, Warden of Inferno", not the full "Clive, Ifrit's
    Dominant // Ifrit, Warden of Inferno". CR 201.5's self-reference ("Ifrit
    fights ...") is read off that name, and a continuous effect is read off
    the ability's own text rather than the front face's (`create_continuous_
    effect_of_ability`), so this sweep asks the same way for a back-face line.
    """
    face = getattr(ability, "face", None)
    front = printing.front_face
    if not face or front is None or face == front.name or face == printing.name:
        return None
    return face


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
      controller"). There is no resolution text to run, and
      `models/game.py::_resolve_top` never calls `effect_for` for one
      (fra-final-audit batch A item 1) - so `effect_for` is never even
      *asked* about a permanent face here, and nothing it might have parsed
      is ever credited. A permanent's own abilities are judged below, one by
      one, from the battlefield.
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
    # CR 722.4: "In every zone, a preparation card has only its normal
    # characteristics" - the inset prepare spell (CR 722.2a) is never one of
    # the front permanent's own abilities. `parse_abilities(printing)` below
    # still returns a `TriggeredAbility`/`StaticAbility` for the inset face's
    # printed text (an instant or sorcery's own resolution text parses as a
    # bare `AbilityKind.STATIC` line when nothing marks it triggered or
    # activated, `machines/abilities.py`'s own default) - the other classifier
    # artifact the FRA S2 survey flagged: the inset spell's already-`handled`
    # `[spell]` clause above was being scored again here as an unaudited
    # static ability of the creature, so the card's worst-clause verdict
    # (`classify_card`) read `static_unaudited` even when every real clause
    # was `handled`.
    prepare_spell_face_name = (
        printing.prepare_spell.name if printing.prepare_spell is not None else None
    )
    # CR 712.11b: a modal double-faced card whose front is a permanent can
    # still be cast as its instant or sorcery back face (Flamescroll
    # Celebrant // Revel in Silence). That face's printed lines are its own
    # resolution text, already judged whole as its "[spell]" clause above -
    # never a static ability of the permanent front, the same classifier
    # artifact CR 722.4's prepare-spell skip below exists for.
    #
    # CR 715.1's Adventure half is the identical shape: `_spell_faces`'s own
    # `Layout.ADVENTURE` branch above already returns it as its own
    # non-permanent face, dispatched through `effect_for`/`[spell]` there -
    # this is what stops `parse_abilities`' bare `AbilityKind.STATIC` parse
    # of that same printed text from being scored a *second* time as an
    # unaudited static ability of the creature front (see that branch's own
    # docstring for the classifier artifact this closes).
    spell_only_face_names = (
        {face.name for face in _spell_faces(printing) if not face.is_permanent}
        if is_permanent and printing.layout in (Layout.MODAL_DFC, Layout.ADVENTURE)
        else set()
    )

    if not printing.is_land:
        for face in _spell_faces(printing):
            if face.is_permanent:
                # CR 608.3a - a resolving permanent spell only becomes a
                # permanent and enters the battlefield; there is no
                # resolution text to run, and `models/game.py::_resolve_top`
                # never calls `effect_for` for one (fra-final-audit batch A
                # item 1). `effect_for` is a pure text parser with no idea
                # whether the object it is reading is a permanent - it can
                # and does parse *something* out of a permanent's raw
                # printed text (a triggered ability's own body, a static
                # line) purely by shape, and crediting that parse used to
                # read as "the credit is real". It never was: the engine
                # does not run this dispatch for a permanent face at all, so
                # whatever it returns is not a clause and is always dropped.
                # The permanent's own triggered/activated/static abilities
                # are judged on their own below, from the battlefield.
                continue
            x_candidates = _x_candidates(face.mana_cost, *additional_cost_phrases(printing))
            effects = [
                effect_for(face.name, face.text, x_value=x_value) for x_value in x_candidates
            ]
            # A prepare spell (CR 722.3c: the copy that is cast "has only the
            # characteristics of that permanent's prepare spell") is judged by
            # its own face text - `_layer_category`'s fallback reads the
            # printing's *front* face, which for a prepare card is the
            # creature, never the inset spell `create_continuous_effect`
            # actually reads at resolution (Venomous Words' own pump).
            face_text = (
                face.text
                if prepare_spell_face_name is not None and face.name == prepare_spell_face_name
                else None
            )
            categories = [_dispatch_category(effect, printing, face_text) for effect in effects]
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
            # `parse_mixed_effect_for_spell` composes every clause of a mixed
            # spell into one anonymous closure, so a "you and <group>" player
            # half it fails closed on (`_leaves_you_and_group_player_half_
            # unread`'s own docstring) has no `__name__` `_dispatch_category`
            # could ever see - never raise it back to HANDLED, only ever
            # worsen an already-worse verdict.
            if _leaves_you_and_group_player_half_unread(face.text):
                category = _worse(category, NOTICE)
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
            # `legendary=` as `Game` passes it at a real activation: only a
            # legend's first-word short name is a self-reference, so a
            # nonlegendary Treasure Map's "create three Treasure tokens" must
            # not be read as "create three this permanent tokens".
            legendary = Supertype.LEGENDARY in printing.supertypes
            other_face = _other_face(printing, ability)
            dispatch_name = other_face or printing.name
            activated_effects = [
                activated_effect_for(
                    dispatch_name, index, ability.effect, x_value=x_value, legendary=legendary
                )
                for x_value in x_candidates
            ]
            # The same substituted text `create_continuous_effect_of_ability`
            # itself now passes to `ContinuousEffects.create` at a real
            # resolution (see `_layer_category`'s own docstring) - computed
            # per X candidate so a pump/keyword-grant judged here is judged
            # on the number that would actually be on the stack.
            ability_texts = [
                substitute_x(ability.text, x_value)
                if x_value is not None
                else (ability.text if other_face else None)
                for x_value in x_candidates
            ]
            categories = [
                _dispatch_category(effect, printing, text)
                for effect, text in zip(activated_effects, ability_texts, strict=True)
            ]
            category = _best(categories)
            if (
                x_candidates == (None,)
                and category == HANDLED
                and not _is_sentinel_effect(activated_effects[0])
                and _effect_matched_inside_quotes(
                    lambda text, i=index, legend=legendary, name=dispatch_name: (
                        activated_effect_for(name, i, text, legendary=legend)
                    ),
                    ability.effect,
                )
            ):
                category = QUOTED_EFFECT
            if _leaves_you_and_group_player_half_unread(ability.effect):
                category = _worse(category, NOTICE)
            clauses.append(ClauseOutcome(category, ability.text, "activated"))
        elif isinstance(ability, TriggeredAbility) and (
            is_permanent or triggers_only_off_the_stack(ability) or _is_own_cast_trigger(ability)
        ):
            # A non-permanent card's "When you discard/cycle this card"
            # (Edgar's Awakening, Choking Tethers) is the exception to the
            # permanent gate explained below: CR 113.6k makes it an ability
            # of the card in whatever zone the discard or cycle leaves it
            # in, triggered off `machines/triggers.py` and put on the stack
            # as its own object, and `effect_for` strips it off the spell's
            # own resolution text (`_strip_trailing_standalone_triggered_
            # ability`), so it is judged here or nowhere.
            if prepare_spell_face_name is not None and ability.face == prepare_spell_face_name:
                continue  # CR 722.4 - see this function's own docstring above.
            if ability.face in spell_only_face_names:
                continue  # CR 712.11b - see `spell_only_face_names` above.
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
            x_candidates = _etb_x_candidates(printing, ability)
            other_face = _other_face(printing, ability)
            dispatch_name = other_face or printing.name
            trigger_effects = [
                trigger_effect_for(dispatch_name, ability.event, ability.effect, x_value=x_value)
                for x_value in x_candidates
            ]
            effect = trigger_effects[0]
            modal_category = _modal_trigger_category(ability.effect, card_name=dispatch_name)
            if modal_category is not None:
                category = modal_category
            else:
                own_text = ability.text if other_face else None
                categories = [_dispatch_category(e, printing, own_text) for e in trigger_effects]
                category = _best(categories)
            # As with the spell face above: a trigger carrying both CR
            # 107.3m's substitution and a quoted span is not in this pool,
            # so that combination is left untested rather than guessed at.
            if (
                x_candidates == (None,)
                and category == HANDLED
                and not _is_sentinel_effect(effect)
                and _effect_matched_inside_quotes(
                    lambda text, event=ability.event, name=dispatch_name: trigger_effect_for(
                        name, event, text
                    ),
                    ability.effect,
                )
            ):
                category = QUOTED_EFFECT
            if _condition_can_fire(printing, ability) is False:
                category = UNMATCHABLE_CONDITION
            if _leaves_you_and_group_player_half_unread(ability.effect):
                category = _worse(category, NOTICE)
            clauses.append(ClauseOutcome(category, ability.text, "triggered"))
        elif ability.kind is AbilityKind.STATIC and is_permanent:
            if prepare_spell_face_name is not None and ability.face == prepare_spell_face_name:
                continue  # CR 722.4 - see this function's own docstring above.
            if ability.face in spell_only_face_names:
                continue  # CR 712.11b - see `spell_only_face_names` above.
            clauses.append(
                ClauseOutcome(
                    _static_ability_category(printing, ability.text), ability.text, "static"
                )
            )

    return clauses


def _is_own_cast_trigger(ability: TriggeredAbility) -> bool:
    """An instant's or sorcery's printed "When you cast this spell, ..."
    paragraph (Photon Blast Barrage, Show of Confidence): CR 113.6k makes it
    function on the stack, where it triggers and goes on the stack as its own
    object - `Game._effect_of` asks `trigger_effect_for` about it, so it is
    judged here, and `machines/copy_effects` strips it off the spell's own
    resolution text."""
    return ability.event is TriggerEvent.CAST_SPELL and "this spell" in ability.condition.lower()


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


# ---------------------------------------------------------------------------
# The public support oracle.
# ---------------------------------------------------------------------------

#: The four-tier verdict a consumer shows a person: `unaudited` is the
#: sweep's `static_unaudited`, and the two sub-silent findings
#: (`unmatchable_condition`, `quoted_effect`) fold into `silent` - a trigger
#: that never fires and an effect read out of the wrong words both leave the
#: printed clause doing nothing in a real game.
SupportStatus = Literal["handled", "unaudited", "notice", "silent"]

#: Which part of the card a clause is: a castable face's own resolution text,
#: an activated/triggered/static ability of the permanent, or a keyword.
ClauseKind = Literal["spell", "activated", "triggered", "static", "keyword"]

_STATUS_OF_OUTCOME: dict[str, SupportStatus] = {
    HANDLED: "handled",
    NOTICE: "notice",
    STATIC_UNAUDITED: "unaudited",
    SILENT: "silent",
    UNMATCHABLE_CONDITION: "silent",
    QUOTED_EFFECT: "silent",
}

#: Worst first, the same order `_SEVERITY` keeps for the six outcomes.
_STATUS_SEVERITY: dict[SupportStatus, int] = {
    "silent": 0,
    "unaudited": 1,
    "notice": 2,
    "handled": 3,
}

_REASONS: dict[str, str] = {
    HANDLED: "the engine reads this text and performs it",
    NOTICE: "the engine recognises this text but fails closed with a notice instead of "
    "performing it",
    STATIC_UNAUDITED: "a static ability no support check audits - not verified either way",
    SILENT: "nothing in the engine reads this text - it would do nothing and log nothing",
    UNMATCHABLE_CONDITION: "this trigger's condition can never be satisfied - it never triggers",
    QUOTED_EFFECT: "the engine's reading came from quoted text, not this clause's own words",
}
_UNREAD_CONDITION_SOURCE = "triggered (unread condition)"
_UNREAD_CONDITION_REASON = (
    "the engine does not recognise this trigger's condition - it never triggers"
)
#: `classify_clauses`'s own `source` labels, as a clause kind.
_KIND_OF_SOURCE: dict[str, ClauseKind] = {
    "spell": "spell",
    "activated": "activated",
    "triggered": "triggered",
    _UNREAD_CONDITION_SOURCE: "triggered",
    "static": "static",
}
#: The source label of the one clause `card_support` adds when a card has
#: rules text but no clause `classify_clauses` names: `classify_card`'s own
#: fallback, the card's whole text read as a continuous effect.
WHOLE_CARD_TEXT_SOURCE = "whole card text"
_NO_CODE_NEEDED = "no code needed"
_KEYWORD_IGNORED_REASON = "no machine in the engine executes this keyword"

#: Engine identity for a cache that outlives this process: the package
#: version plus `Game.CURRENT_SCHEMA_VERSION`, which moves whenever a rules
#: change alters how existing state resolves.
ENGINE_VERSION = f"{__version__}+schema{Game.CURRENT_SCHEMA_VERSION}"


class SupportClause(EngineModel):
    """One clause of a card and what the engine does with it."""

    model_config = ConfigDict(frozen=True)

    kind: ClauseKind
    #: The printed clause (a keyword's own name for a keyword clause).
    text: str
    #: The sweep's own category: handled, notice, static_unaudited, silent,
    #: unmatchable_condition or quoted_effect.
    outcome: str
    status: SupportStatus
    reason: str
    #: Which dispatch path answered, as the sweep labels it ("spell",
    #: "triggered (unread condition)", or for a keyword the machine that
    #: executes it).
    source: str


class CardSupport(EngineModel):
    """What the engine supports on one card: every clause's own verdict and
    the card's, which is its worst clause's (silent < unaudited < notice <
    handled). A card with no clauses at all (a vanilla creature) is
    `handled` - doing nothing is correct for it."""

    model_config = ConfigDict(frozen=True)

    name: str
    engine_version: str
    status: SupportStatus
    clauses: tuple[SupportClause, ...]
    #: `has_rules_text` - whether the card has anything besides keywords and
    #: mana abilities to judge.
    has_rules_text: bool
    #: The sweep's own per-card rules-text verdict (`classify_card`): the
    #: worst non-keyword outcome and the clause it came from. `None` when
    #: the card has no rules text.
    effect_outcome: str | None
    effect_detail: str


def _clause(kind: ClauseKind, text: str, outcome: str, source: str) -> SupportClause:
    reason = _UNREAD_CONDITION_REASON if source == _UNREAD_CONDITION_SOURCE else _REASONS[outcome]
    return SupportClause(
        kind=kind,
        text=text,
        outcome=outcome,
        status=_STATUS_OF_OUTCOME[outcome],
        reason=reason,
        source=source,
    )


def _keyword_clauses(printing: Card) -> list[SupportClause]:
    """One clause per printed keyword, in Scryfall's order - the same
    verdict `ignored_keywords` gives, with the machine that executes each."""
    executed = executed_keywords(printing)
    flavor = flavor_words(printing)
    found: list[SupportClause] = []
    for keyword in printing.keywords:
        lowered = keyword.lower()
        where = executed.get(lowered)
        if where is None and (
            lowered in NEEDS_NO_CODE
            or _normalized_ability_word(keyword) in ABILITY_WORDS
            or lowered in flavor
        ):
            where = _NO_CODE_NEEDED
        if where is None:
            found.append(
                SupportClause(
                    kind="keyword",
                    text=keyword,
                    outcome=SILENT,
                    status="silent",
                    reason=_KEYWORD_IGNORED_REASON,
                    source="keyword",
                )
            )
        else:
            found.append(
                SupportClause(
                    kind="keyword",
                    text=keyword,
                    outcome=HANDLED,
                    status="handled",
                    reason=where,
                    source=where,
                )
            )
    return found


def _classify(printing: Card) -> CardSupport:
    clauses: list[SupportClause] = []
    rules_text = has_rules_text(printing)
    effect_outcome: str | None = None
    effect_detail = ""
    if rules_text:
        outcomes = classify_clauses(printing)
        for outcome in outcomes:
            clauses.append(
                _clause(
                    _KIND_OF_SOURCE[outcome.source], outcome.text, outcome.category, outcome.source
                )
            )
        if outcomes:
            worst = min(outcomes, key=lambda clause: _SEVERITY[clause.category])
            effect_outcome, effect_detail = worst.category, worst.text
        else:
            # `classify_card`'s own fallback: nothing `parse_abilities` calls a
            # clause, but the card's text still reads as a continuous effect.
            effect_outcome = _layer_category(printing) or SILENT
            clauses.append(
                _clause(
                    "static", printing.front_oracle_text, effect_outcome, WHOLE_CARD_TEXT_SOURCE
                )
            )
    clauses.extend(_keyword_clauses(printing))
    status: SupportStatus = min(
        (clause.status for clause in clauses),
        key=lambda s: _STATUS_SEVERITY[s],
        default="handled",
    )
    return CardSupport(
        name=printing.name,
        engine_version=ENGINE_VERSION,
        status=status,
        clauses=tuple(clauses),
        has_rules_text=rules_text,
        effect_outcome=effect_outcome,
        effect_detail=effect_detail,
    )


_CACHE_LIMIT = 8192
_cache: dict[tuple[str, str, str], CardSupport] = {}
_cache_lock = threading.Lock()


def clear_card_support_cache() -> None:
    """Forget every memoized verdict (tests, or a process that hot-swaps the
    engine)."""
    with _cache_lock:
        _cache.clear()


def card_support(card: Card) -> CardSupport:
    """What the engine supports on `card`, clause by clause - see this
    module's docstring. Works for any `Card` built from a Scryfall printing;
    nothing here looks a card up by name.

    Deterministic and side-effect free: the answer is a frozen model, the
    probes run on throwaway boards under a fresh uuid4 id allocator, and the
    memo is keyed by `ENGINE_VERSION`, the card's oracle id (its name when
    it has none) and its full printed data, so two different printings can
    never share an answer they do not both deserve.
    """
    key = (ENGINE_VERSION, str(card.oracle_id or card.name), card.model_dump_json())
    with _cache_lock:
        hit = _cache.get(key)
    if hit is not None:
        return hit
    token = install_id_allocator(uuid4)
    try:
        support = _classify(card)
    finally:
        reset_id_allocator(token)
    with _cache_lock:
        if len(_cache) >= _CACHE_LIMIT:
            _cache.pop(next(iter(_cache)))
        _cache[key] = support
    return support
