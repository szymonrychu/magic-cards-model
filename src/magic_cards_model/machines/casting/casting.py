import re
from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import contextmanager
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import ConfigDict, Field

from ...models.card import Card, Color, Layout, Type, types_of
from ...models.card_state import (
    CardState,
    Counter,
    Counters,
    ExileAnnotation,
    ExileMarker,
    TargetRef,
)
from ...models.mana import ManaCost, ManaSpend
from ...models.zone import Zone
from ...numbers import VariableX, parse_amount, parse_count
from ...phrases import with_indefinite_article
from ...snapshot import EngineModel
from ..abilities import (
    AbilityKind,
    TriggerEvent,
    parse_granted_ability_lines,
)
from ..casting_restrictions import (
    CastingRuleKind,
    combat_lockdown_restriction_source,
    has_sorcery_speed_flash_grant,
    own_play_prohibition_source,
    restricted_from_noncreature_casting,
    sorcery_speed_restriction_source,
    targeted_cant_cast_restriction,
    zone_cast_prohibition_source,
)
from ..cleave import cleaved_text
from ..cost import (
    TEAMWORK_TAP,
    CardRequirement,
    ComponentKind,
    CostComponent,
    CostPayment,
    CostStep,
    StaticFreeCastGrant,
    TotalCost,
    additional_cost_phrases,
    alternative_cost_offers,
    announce_reveal,
    apply_modifications,
    behold_cost,
    cost_announces_x,
    cost_component_for_phrase,
    mana_value_cap_for,
    pay_life_cost,
    per_object_exile_cost_reduction,
    per_object_sacrifice_cost_reduction,
    place_counters_cost,
    static_free_cast_grant,
    take_from_pool,
    tap_cost,
    total_cost_for_phrase,
)
from ..cost.abilities import ability_cost_adjustment, foretell_any_turn
from ..cost.statics import object_quality
from ..cost.text import printed_cost_total
from ..decisions import source_id_of
from ..keywords import (
    casualty_x_instances,
    enchant_restrictions,
    face_down_characteristics,
    why_cannot_enchant,
)
from ..modes import ModalProfile, Mode, modal_profile, substitute_x, x_restriction_refusal
from ..objects_as_costs import power_of
from ..spell_grants import (
    casualty_numbers,
    conspire_count,
    granted_affinity_reductions,
    granted_zone_keyword_lines,
    replicate_costs,
)
from ..targeting import (
    TargetingProfile,
    face_spell_profile,
    kicked_instead_target_text,
    per_kick_target_text,
    profile_for_modes,
    profile_for_modes_with_owners,
    profile_for_text,
    spell_profile_for_text,
    targeting_profile,
    targeting_trigger_text,
    with_face_aura_target,
)
from ..teamwork import teamwork_ability, teamwork_instead_target_text, teamwork_payment_refusal
from ..triggers import ExtraTriggerEvent, GameEvent
from ..turn import Step
from ..zone_grants import effective_card
from .granted_life_costs import GrantedLifeCost, granted_life_costs
from .options import AlternativeCostOption, CastTiming, KeywordCastOption
from .permissions import GrantedCastOption, PlayPermission


def _why_not_in_own_declare_blockers_step(
    game: Any, caster: str, option: KeywordCastOption
) -> str | None:
    """CR 702.190a's window: "Any time you could cast an instant during your
    declare blockers step".

    Three conditions, one per word: **your** (the caster is the active
    player), **declare blockers step** (`Step.DECLARE_BLOCKERS`, not the
    declare attackers step before it nor the combat damage step after), and
    **any time you could cast an instant** (CR 117.1a: "any time they have
    priority", so the stack need not be empty). CR 611.1's "can cast spells
    only any time they could cast a sorcery" (Teferi, Time Raveler) takes the
    instant half away as well, so it refuses here too.
    """
    turn = getattr(game, "turn", None)
    if turn is None:
        return None
    if turn.active_player != caster or turn.step is not Step.DECLARE_BLOCKERS:
        return (
            f"{option.keyword} can only be used during {caster}'s own declare blockers "
            f"step ({option.rule})"
        )
    if not turn.grants_priority:
        return (
            f"{option.keyword} can only be used when {caster} could cast an instant "
            f"({option.rule}, CR 117.1a)"
        )
    restricting_source = sorcery_speed_restriction_source(game, caster)
    if restricting_source is not None:
        return (
            f"{restricting_source} restricts {caster} to casting spells only any time "
            f"they could cast a sorcery, and it is not (CR 117.1a, CR 611.1)"
        )
    return None


def why_cannot_cast_from(
    spell: CardState,
    caster: str,
    zone: Zone,
    game: Any = None,
    *,
    library_top: bool | None = None,
    cost_paid: bool = False,
) -> str | None:
    """CR 601.3: why this card cannot be cast from where it is, or None.

    A card in hand needs no permission - that is where the rules cast from by
    default (CR 302.1, 601.3). Anywhere else, some keyword has to allow it -
    printed on the card, granted to it where it lies by somebody's static
    ability (CR 611.3d, Iroh's flashback grant), or carried by the pile of
    exile it is sitting in rather than by anything printed on it (CR 701.65a's
    airbend - `marker_cast_options`) - or some effect has to have handed out a
    `PlayPermission`, and that grant's own conditions have to hold.
    """
    only_from = printed_cast_only_zones(spell.card)
    if only_from is not None and zone not in only_from:
        where = " or ".join(only_zone.value for only_zone in only_from)
        return (
            f"{spell.name} may be cast only from the {where}, not from the {zone.value} (CR 601.3)"
        )
    if zone is Zone.HAND:
        return None
    if usable_play_permission(game, spell, caster) is not None:
        return None
    options = (
        castable_from(spell.card, zone)
        + [option for option in marker_cast_options(spell) if option.zone is zone]
        + [
            granted.option
            for granted in granted_cast_options(game, spell, caster, zone, library_top=library_top)
        ]
    )
    reasons = [
        option.why_not(spell, caster, game, origin=zone, cost_paid=cost_paid) for option in options
    ]
    if any(reason is None for reason in reasons):
        return None
    granted = play_permissions_on(game, spell)
    if granted:
        # A permission was handed out for this object and does not apply - say
        # why it does not (expired, wrong player, cast-not-play) rather than
        # the generic "nothing allows this", which would be a lie.
        return granted[0].why_not(spell, caster, game)
    if not options:
        return f"nothing allows {caster} to cast {spell.name} from the {zone.value} (CR 601.3)"
    return next(reason for reason in reasons if reason is not None)


# --------------------------------------------------------------------------
# Whether a card is a spell at all (CR 305.1, CR 300.2a)
# --------------------------------------------------------------------------


def why_cannot_cast_a_land(spell: CardState) -> str | None:
    """CR 305.1: a land is never a spell, so it can never be cast - not even
    together with another card type that ordinarily could be (CR 300.2a).

    CR 305.1's own closing sentence: "Since the land doesn't go on the
    stack, it is never a spell, and players can't respond to it with
    instants or activated abilities." CR 300.2a: "An object that's both a
    land and another card type (for example, an artifact land) can only be
    played as a land. It can't be cast as a spell."

    Checked ahead of every other refusal in `Casting.model_post_init`, so a
    land is refused *before* CR 601.2a would otherwise move it to the
    stack - a land was never a spell to begin with, so there is nothing for
    CR 601.2a's own opening sentence ("To propose the casting of a spell...")
    to be about. Without this, `why_cannot_cast_now`'s CR 117.1a reading
    passes a land straight through: that check is purely about *when* a
    cast is timed, never about *what* can be cast at all, so a land sitting
    in the active player's own main phase with an empty stack satisfies
    `Game.can_cast_sorcery` exactly the way a real spell would. Left
    unguarded, `Casting` would go on to build a real announcement - and
    `Game.cast` would then refuse deep inside cost determination with
    `_refuse_unless_mana_cost_payable`'s CR 118.6 message, which is a lie
    for a land: a land's blank mana-cost corner is not an *unpayable cost*
    CR 118.6a's alternative-cost escape hatch (Suspend, say) could ever
    make payable - a land was never a spell whose cost that rule could speak
    to in the first place.
    """
    if Type.LAND in spell.card.types:
        return (
            f"{spell.name} is a land (CR 305.1); a land never goes on the stack, is "
            f"never a spell, and cannot be cast"
        )
    return None


# --------------------------------------------------------------------------
# When a card may be cast (CR 117.1a, CR 702.8a)
# --------------------------------------------------------------------------

#: Keywords that change *when* a card may be cast rather than from where.
#: `scripts/sweep_pool.py` reads this to tell an executed timing keyword from an
#: ignored one.
TIMING_KEYWORDS = frozenset({"flash"})

#: Keywords that change whether a permanent may be *chosen* as a target
#: (CR 601.2c). `Casting.choose_targets` refuses the announcement for these.
TARGET_LEGALITY_KEYWORDS = frozenset({"hexproof"})


#: "This spell costs {1} more to cast for each target beyond the first."
#: (Fireball, Launch the Fleet's identically-worded "Strive —" clause) -
#: read generically off the amount rather than assuming {1}, though every
#: real printing of this shape uses it.
_COST_INCREASE_PER_TARGET_RE = re.compile(
    r"costs (?P<amount>\{[^}]+\}(?:\{[^}]+\})*) more to cast for each target beyond the first",
    re.IGNORECASE,
)

#: Keywords that are an optional additional cost on a spell being cast
#: (CR 118.8a). `Casting.pay_kicker` charges these.
ADDITIONAL_COST_KEYWORDS = frozenset(
    {
        "kicker",
        "multikicker",
        "replicate",
        "offspring",
        "blight",
        "gift",
        "teamwork",
        "bargain",
        "casualty",
        "conspire",
    }
)


def face_being_cast(card: Card, face_name: str | None) -> Any:
    """The `CardFace` a cast has named, or None when it named none (CR 709.3,
    CR 715.3).

    A plain name lookup over `card_faces`, so a name that matches no face -
    or no name at all - is simply "no face chosen" rather than an error: this
    is asked on the enumeration path (`machines/legal_actions.py`) as well as
    on the announcement path, and the enumeration hands back whatever
    `Action.spell_face` it built the row from.

    Deliberately layout-blind. The two layouts that name a face do so under
    rules with the same shape (CR 709.3 for a split card's half, CR 715.3 for
    an adventurer card's Adventure), and `Casting.face` already carries both -
    the name is the discriminator, not the layout; a modal double-faced
    card's nonland back face (CR 712.11b) is named the same way. A
    card whose face is never named (a transforming card, an Omen, a modal
    double-faced card cast as its front) reaches here with `face_name=None`
    and gets the card's own characteristics.
    """
    if face_name is None:
        return None
    for face in card.card_faces or []:
        if face.name == face_name:
            return face
    return None


def types_being_cast(card: Card, face_name: str | None = None) -> tuple[Type, ...]:
    """The card types evaluated to decide whether this cast is legal (CR
    709.3a, CR 715.3a).

    CR 709.3a: "Only the chosen half is evaluated to see if it can be cast.
    Only that half is considered to be put onto the stack." CR 715.3a says it
    again for an adventurer card: "When casting an adventurer card as an
    Adventure, only the alternative characteristics are evaluated to see if it
    can be cast." CR 601.3e is the general rule both are instances of, and it
    is explicit about what the substitution means: "Some rules and effects
    state that an alternative set of characteristics or a subset of
    characteristics are considered to determine if a card or copy of a card is
    legal to cast. **These alternative characteristics replace the object's
    characteristics for this determination.**"

    `Card.types` cannot answer this. It reads `Card.front_type_line`, which
    splits `type_line` on `//` and keeps the **left** half, so for a split or
    adventurer card it is always the front face's types - and CR 709.4/709.4c
    ("in every zone except the stack, the characteristics of a split card are
    those of its two halves combined... each card type specified on either of
    its halves") is not that either. Both readings answer a different question
    from the one CR 709.3a asks, and using either for a cast decided a chosen
    half's timing by whichever half happened to be printed on the left:
    **Replicate, the Sorcery half of Repudiate // Replicate (`Instant //
    Sorcery`), was castable during an upkeep step**, and Incongruity, the
    Instant half of Incubation // Incongruity (`Sorcery // Instant`), was
    refused during one.

    Falls back to `card.types` with no face named, which is every
    single-faced card and every cast that never chose a half.
    """
    face = face_being_cast(card, face_name)
    if face is not None and face.type_line:
        return tuple(types_of(face.type_line))
    return tuple(card.types)


def flash_grant_sources(game: Any, spell: CardState, caster: str) -> list[str]:
    """The permanents whose static alternative cost lets `caster` cast `spell`
    "as though it had flash" when it is paid (Primal Prayers' "If you cast a
    spell this way, you may cast it as though it had flash"), given it can be
    paid for this spell now (CR 118.9, CR 601.3)."""
    if game is None:
        return []
    return [
        name
        for name, grant in static_free_cast_grants(game, caster)
        if grant.grants_flash
        and static_free_cast_refusal(game, caster, spell, spell.zone, name, grant) is None
    ]


def flash_by_alternative_cost(game: Any, spell: CardState, caster: str) -> bool:
    return bool(flash_grant_sources(game, spell, caster))


def _keyword_option_answers_timing(option: KeywordCastOption) -> bool:
    """Whether `option` decides its own timing in `KeywordCastOption.why_not`
    rather than leaving the card's own CR 117.1a timing in force.

    Madness is the one `CastTiming.ANY` keyword that does: CR 702.35a's cast
    happens while its triggered ability resolves (CR 608.2g), timing ignored;
    the engine models that window as the card sitting in its madness pile."""
    if option.timing is not CastTiming.ANY:
        return True
    return option.marker is ExileMarker.MADNESS


def why_cannot_cast_now(
    spell: CardState,
    caster: str,
    game: Any = None,
    *,
    face: str | None = None,
    without_alternative_flash: bool = False,
    without_keyword_timing: bool = False,
) -> str | None:
    """Why the timing rules refuse this cast right now, or None (CR 117.1a).

    `without_keyword_timing` drops the last exemption - an option for the
    card's zone that carries a timing of its own - so `Casting` can hold the
    refusal until the keyword is announced and ask whether the option used is
    that one (CR 117.1a follows the option the cast actually uses).

    CR 117.1a is the whole rule in two sentences: "A player may cast an instant
    spell any time they have priority. A player may cast a noninstant spell
    during their main phase any time they have priority and the stack is empty."
    The per-type rules say the same thing card type by card type - CR 304.1 for
    instants, CR 307.1 for sorceries, CR 302.1 for creatures, CR 301.1 for
    artifacts, CR 306.1 for planeswalkers, CR 310.1 for battles - and CR 505.6a
    restates that the main phase is the only phase the noninstants go in.

    Flash is the exception that makes the rule worth enforcing (CR 702.8a):
    with it, a creature is cast on the sorcery-speed rule's *other* side.

    Answered against the game because it is a question about the turn: without
    one there is nothing to ask, and the answer is None.

    **Teferi, Time Raveler's two halves, checked in the right order.** His
    static, "Each opponent can cast spells only any time they could cast a
    sorcery," removes *every* instant-speed exception - CR 304.1's instant
    permission and CR 702.8a's flash both - for an opponent, so it is read
    before either of them, but only once sorcery-speed timing has already
    failed: a restricted opponent whose own main phase it is, with an empty
    stack, needs no exception at all (CR 611.1 does not add a *second*
    restriction on top of ordinary permission). His +1, "Until your next
    turn, you may cast sorcery spells as though they had flash," is the
    opposite direction and touches only its own controller: a sorcery this
    caster could not otherwise cast at instant speed is let through the same
    way `has_flash` already lets an instant-speed creature through.

    **An `immediate` `PlayPermission` (CR 702.62a's suspend, the third
    ability) skips this whole rule rather than answering it.** CR 117.1's own
    preamble: "**Unless a spell or ability is instructing a player to take an
    action**, which player can take actions at any given time is determined
    by a system of priority." CR 117.2e: "Resolving spells and abilities may
    instruct players to make choices or take actions... Even if a player is
    doing so, no player has priority while a spell or ability is resolving."
    A card cast under a live `immediate` grant is being cast *as* the
    resolving ability's own instruction, not through the priority system
    CR 117.1a governs - which is why a suspended sorcery can be cast during
    an upkeep step that is never anyone's main phase. This does not apply to
    Ugin, Eye of the Storms' or Ragavan, Nimble Pilferer's grants: both print
    "**Until end of turn**, you may cast", an explicit standing permission
    used through the ordinary priority system afterward, where CR 117.1a
    still applies in full - see `PlayPermission.immediate`'s own docstring.

    **`face` is the half being cast** (CR 709.3a, CR 715.3a): with one named,
    every card-type question below is asked of that face's own type line
    rather than of `spell.card.types`, which is the *front* face's. See
    `types_being_cast` for the two printings that measured the difference.
    `has_flash` is left reading the whole printing's Scryfall `keywords`,
    which carry no face attribution. **Brazen Borrower // Petty Theft does
    print flash on one half only** - it is on the creature front face, not on
    Petty Theft - so the earlier claim in this docstring that no such printing
    exists was simply wrong, and was corrected by sweeping every `split`/
    `adventure` printing in the pool for the keyword. It is still
    unobservable: the half that does not print flash is an Instant, which
    CR 304.1 already lets its controller cast at any time, so the card-level
    read reaches the right answer for both halves. The reading that *would*
    be wrong - a card-level flash granting instant speed to a **noninstant**
    half that prints none - has no printing in the pool to prove it on, and
    `CLAUDE.md` is explicit that generality is demonstrated on a real card
    rather than asserted, so a per-face keyword read is not built here.
    """
    if game is not None and game.is_over:
        return game.why_game_is_over()
    if game is None:
        return None
    types = spell.types_as_a_spell(types_being_cast(spell.card, face))
    permission = usable_play_permission(game, spell, caster)
    if permission is not None and permission.immediate:
        return None
    if game.can_cast_sorcery(caster):
        return None
    restricting_source = sorcery_speed_restriction_source(game, caster)
    if restricting_source is not None:
        return (
            f"{restricting_source} restricts {caster} to casting spells only any time "
            f"they could cast a sorcery, and it is not (CR 117.1a, CR 611.1)"
        )
    if Type.INSTANT in types:
        return None  # CR 304.1
    if has_flash(effective_card(game, spell)):
        return None  # CR 702.8a (printed, or granted off the battlefield, CR 613.1f)
    if Type.SORCERY in types and has_sorcery_speed_flash_grant(game, caster):
        return None  # Teferi, Time Raveler's +1
    condition = conditional_flash_condition(spell.oracle_text or "")
    if condition is not None and cast_condition_holds(game, caster, condition, spell):
        return None  # Bard's Company's own conditional flash grant
    if flash_surcharge(spell.oracle_text or "") is not None:
        return None  # Asinine Antics: flash if the extra cost is paid (`_own_flash_surcharge`)
    if has_quality_flash_grant(game, caster, spell):
        return None  # Vivien, Champion of the Wilds' "creature spells ... flash"
    if game.has_first_spell_flash_grant(caster, spell):
        return None  # Radagast of Rhosgobel's own first-creature-spell flash grant
    if not without_alternative_flash and flash_by_alternative_cost(game, spell, caster):
        return None  # Primal Prayers: flash while paying its alternative cost
    if (
        not without_keyword_timing
        and spell.zone is not Zone.HAND
        and any(
            _keyword_option_answers_timing(option)
            for option in [
                *(o for o in castable_from(spell.card, spell.zone) if not o.casts_transformed),
                *marker_cast_options(spell),
                *(
                    granted.option
                    for granted in granted_cast_options(game, spell, caster, spell.zone)
                ),
            ]
        )
    ):
        # Only an option carrying a timing of its own answers here - plot's
        # "only as a sorcery" (CR 702.170a), sneak's declare blockers window
        # (CR 702.190a), a pile's "as though it had flash" (CR 702.8a) - and
        # `KeywordCastOption.why_not` asks it. `CastTiming.ANY` is the card's
        # own timing (flashback CR 702.34a, escape CR 702.138a, disturb CR
        # 702.146a change the zone and cost, never when): CR 117.1a, above.
        # It answers for the proposal only: `Casting` holds the strict refusal
        # in `timing_refusals_unless_keyword_timing` and raises it at `cast()`
        # unless the option used is one of these.
        return None
    return (
        f"{face or spell.name} is not an instant and has no flash, so {caster} can only cast "
        f"it during their own main phase with the stack empty (CR 117.1a, CR 702.8a)"
    )


#: A spell's own printed casting gate - "Threshold — You can't cast this
#: spell unless there are seven or more cards in your graveyard." (Proft,
#: Sinister Mastermind). The ability word ("Threshold") carries no rules
#: meaning of its own (CR 207.2c) and is not part of the match; the
#: restriction is the sentence after it. No other printed card uses this
#: exact sentence (checked via full-text Scryfall search this session), so
#: the shape's generality rests on `condition_holds`, the shared reader
#: "Activate only if <condition>" (CR 602.5b) already uses across many
#: unrelated cards, rather than on a second card proving this exact gate.
#: "Cast this spell only if <condition>." (Hewed Stone Retainers, Talara's
#: Battalion) is CR 601.3's same prohibition worded as a permission; "only
#: during ..." timing restrictions are read elsewhere and never match.
_CANNOT_CAST_UNLESS_RE = re.compile(
    r"(?:you can'?t cast this \w+ unless|cast this spell only if) (?P<condition>[^.]+)\.",
    re.IGNORECASE,
)


def _legendary_instant_or_sorcery_refusal(spell: CardState, caster: str, game: Any) -> str | None:
    """CR 205.4e: a legendary instant or sorcery spell can't be cast unless its caster controls
    a legendary creature or a legendary planeswalker (read off the computed board, CR 613.5)."""
    from ...models.card import Supertype

    card = spell.card
    if Supertype.LEGENDARY not in card.supertypes or not (
        Type.INSTANT in card.types or Type.SORCERY in card.types
    ):
        return None
    board = game.computed_board()
    for permanent in game.battlefield:
        chars = board.of(permanent)
        if (
            chars.controller == caster
            and Supertype.LEGENDARY in chars.supertypes
            and (Type.CREATURE in chars.types or Type.PLANESWALKER in chars.types)
        ):
            return None
    return (
        f"{spell.name} is a legendary {'instant' if Type.INSTANT in card.types else 'sorcery'}, "
        f"so {caster} can't cast it without controlling a legendary creature or a legendary "
        "planeswalker (CR 205.4e)"
    )


def why_cannot_cast_self_restriction(spell: CardState, caster: str, game: Any = None) -> str | None:
    """CR 601.2e: "The game checks to see if the proposed spell can legally
    be cast. If the proposed spell is illegal, the game returns to the
    moment before the casting of that spell was proposed" - a spell's own
    printed "You can't cast this spell unless <condition>." is exactly such
    an illegality, checked the moment the cast is proposed rather than left
    to be discovered on resolution.

    The condition is handed to `Game.condition_holds`, unread there is
    refused rather than allowed unchecked - the same fail-closed default
    `Game.why_cannot_activate`'s own "Activate only if" gives an unread
    condition (CR 602.5b), not "no rule to check" treated as "no
    restriction"."""
    if game is None:
        return None
    from ..static_cast_bans import self_normalized_oracle, self_turn_gate_reason

    gate = self_turn_gate_reason(spell, caster, game)
    if gate is not None:
        return gate
    legendary = _legendary_instant_or_sorcery_refusal(spell, caster, game)
    if legendary is not None:
        return legendary
    match = _CANNOT_CAST_UNLESS_RE.search(self_normalized_oracle(spell))
    if match is None:
        return None
    condition = match.group("condition").strip()
    held = game.condition_holds(caster, condition, source=spell)
    if held is None:
        return (
            f'{spell.name}\'s casting restriction "{condition}" is not read by this engine, '
            "so the cast is refused rather than allowed unchecked (CR 601.2e)"
        )
    if not held:
        return f"{spell.name} can't be cast: {condition} is not true right now (CR 601.2e)"
    return None


def why_cannot_cast_restriction(
    spell: CardState, caster: str, game: Any = None, *, face: str | None = None
) -> str | None:
    """CR 611.1: why a rules-modifying continuous effect refuses this cast
    outright, or None.

    Distinct from `why_cannot_cast_now`'s timing question: Ranger-Captain of
    Eos's "Your opponents can't cast noncreature spells this turn" is a flat
    prohibition that holds at any timing, so it is checked separately rather
    than folded into the sorcery-speed logic above.

    **`face` is the half being cast**, and both type-reading prohibitions
    below are asked of *that* face's types (CR 601.3e, with CR 709.3a and
    CR 715.3a as its two instances here). `spell.card.types` reads
    `Card.front_type_line`, so an adventurer card's front creature answered
    for its Adventure half: measured live, **Stomp was cast freely under
    "your opponents can't cast noncreature spells this turn"**, and again out
    of a graveyard under Soulless Jailer's "Players can't cast noncreature
    spells from graveyards or exile". Both are noncreature spells; the card
    they are printed on is not.

    Nothing else here is type-scoped. `targeted_cant_cast_restriction` is
    Orim's Chant's "can't cast spells at all", and a zone prohibition with no
    type word (Grafdigger's Cage) catches every spell whichever face is named,
    so neither can disagree with itself across the halves of one card.
    """
    if game is None:
        return None
    if game.player(caster).cannot_cast_spells_for_rest_of_game:
        return (
            f"{caster} can't cast spells for the rest of the game because a spell with epic "
            f"they controlled resolved (CR 702.50a, CR 702.50b)"
        )
    # CR 702.61a: checked before `spell` has moved to the stack (CR 601.2a
    # runs after every refusal in this chain), so a split-second spell
    # already on the stack always counts as an "other" spell here - even one
    # sharing this one's name, which is the correct read: nothing in
    # CR 702.61a exempts a second copy of the same card.
    split_second_source = split_second_restriction_source(game)
    if split_second_source is not None:
        return (
            f"{split_second_source} has split second: as long as it is on the stack, "
            f"players can't cast other spells (CR 702.61a)"
        )
    combat_lockdown_source = combat_lockdown_restriction_source(game)
    if combat_lockdown_source is not None:
        return f"{combat_lockdown_source} says players can't cast spells during combat (CR 506.1)"
    types = spell.types_as_a_spell(types_being_cast(spell.card, face))
    restriction = restricted_from_noncreature_casting(game, caster)
    if restriction is not None and Type.CREATURE not in types:
        return (
            f"{restriction.source_name} says {caster} can't cast noncreature spells "
            f"this turn (CR 611.1)"
        )
    targeted = targeted_cant_cast_restriction(
        game, caster, spell_types=types, spell_subtypes=spell.subtypes
    )
    if targeted is not None and targeted.kind == CastingRuleKind.SPELL_COUNT_CANT_CAST:
        return (
            f"{targeted.source_name} says {caster} can't cast more than {targeted.amount} "
            f"such spell(s) each turn, and that many were already cast (CR 601.3, CR 101.2)"
        )
    if targeted is not None:
        which = "noncreature spells" if targeted.noncreature_only else "spells"
        return f"{targeted.source_name} says {caster} can't cast {which} this turn (CR 611.1)"
    own_ban = own_play_prohibition_source(game, caster, zone=spell.zone, land=False)
    if own_ban is not None:
        return (
            f"{own_ban} says {caster} can't cast spells from their {spell.zone.value} "
            f"(CR 601.3, CR 101.2)"
        )
    prohibited_from = zone_cast_prohibition_source(game, spell.card, spell.zone, types=types)
    if prohibited_from is not None:
        # Grafdigger's Cage's "Players can't cast spells from graveyards or
        # libraries." and Soulless Jailer's "Players can't cast noncreature
        # spells from graveyards or exile." CR 601.3 needs both halves - "a
        # rule or effect allows that player to cast it **and no rule or effect
        # prohibits** that player from casting it" - and this is the second
        # one: it beats the very permission that put the card in reach
        # (flashback, an exile grant), because CR 101.2 makes "can't" win over
        # "can". Asked of `spell.zone` rather than of a `Casting.origin_zone`
        # this function never sees, which is the same zone: the card has not
        # moved yet when the announcement is refused.
        return (
            f"{prohibited_from} prohibits casting {spell.name} from the "
            f"{spell.zone.value} (CR 601.3, CR 101.2)"
        )
    from ..static_cast_bans import spell_ban_reason

    return spell_ban_reason(game, spell, caster, face, types)


def why_mana_cost_unpayable(
    name: str, base_cost: ManaCost, alternative_cost: TotalCost | None = None
) -> str | None:
    """CR 118.6: a card with no printed mana cost has an unpayable cost, or None.

    "Some objects have no mana cost. This represents an unpayable cost." This
    is not the same thing as a printed {0}: CR 118.5a's "{0}" is a real, if
    empty, cost that "must still be cast the same way as one with a cost
    greater than zero", so it parses to one generic symbol worth zero
    (`ManaCost.parse("{0}").symbols` is non-empty). A card with no mana
    symbols at all - Living End's blank corner, `Card.mana_cost == ""` with
    no `card_faces` to fall back to - parses to no symbols at all, and
    CR 118.6 says that cost cannot be paid, full stop.

    CR 118.6a is the escape hatch: "If an alternative cost is applied to an
    unpayable cost, including an effect that allows a player to cast a spell
    without paying its mana cost, ... the cost becomes payable." - which is
    what `alternative_cost is not None` reports: CR 118.9's alternative cost
    machinery having actually run (`Casting.alternative_cost`), or a `CAST`
    action `legal_actions` already knows is not paying the base cost at all.

    Pure over `(name, base_cost, alternative_cost)` on purpose: `Casting.
    _refuse_unless_mana_cost_payable` and `legal_actions._cast_action` both
    ask this identical question - one before raising to unwind an
    announcement, the other before ever building one - and sharing the one
    implementation is what keeps a `CAST` action's own `Affordability.NO`
    from ever disagreeing with what `Game.cast` would actually refuse.
    """
    if alternative_cost is not None:
        return None
    if base_cost.symbols:
        return None
    return (
        f"{name} has no mana cost, which CR 118.6 makes an unpayable "
        f"cost - it cannot be cast this way. Some alternative or additional cost "
        f"permission (a keyword like Suspend, or a resolving effect's permission "
        f"to cast it without paying its mana cost) must apply instead (CR 118.6a)."
    )


#: The one condition this engine can answer: Mindbreak Trap's "an opponent cast
#: three or more spells this turn", counted off `Game.spells_cast_this_turn`.
#: Anything else the sentence could say is left unread, and the offer it gates
#: is reported unavailable rather than quietly granted.
_OPPONENT_SPELL_COUNT_CONDITION = re.compile(
    r"^an opponent cast (?P<count>[\w-]+) or more spells this turn$", re.IGNORECASE
)


#: "X can't be greater than <bound>." - Soul Immolation's cap on its blight X.
_X_CAP = re.compile(r"\bX can't be greater than (?P<bound>[^.]+)\.", re.IGNORECASE)
#: The one bound read: the greatest power or toughness among creatures the
#: caster controls.
_GREATEST_AMONG_CREATURES = re.compile(
    r"^the greatest (?P<stat>power|toughness) among creatures you control$", re.IGNORECASE
)


class CastingStep(StrEnum):
    PROPOSED = "proposed"
    MODES = "modes"
    TARGETS = "targets"
    COST_DETERMINED = "cost_determined"
    PAYING = "paying"
    CAST = "cast"
    CANCELLED = "cancelled"


CASTING_ORDER: tuple[CastingStep, ...] = (
    CastingStep.PROPOSED,
    CastingStep.MODES,
    CastingStep.TARGETS,
    CastingStep.COST_DETERMINED,
    CastingStep.PAYING,
    CastingStep.CAST,
)


class Casting(EngineModel):
    """One spell on its way to the stack.

    Created with the card being cast. Walk it through the steps in order, then
    `cast()` to finish, or `cancel()` to rewind the whole announcement.

    `game` is optional. Without it the announcement still works and targets are
    still checked against whatever objects the caller passed in; with it, costs
    that move cards or change a life total can actually be paid.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    spell: CardState
    caster: str
    game: Any = Field(default=None, exclude=True, repr=False)
    step: CastingStep = CastingStep.PROPOSED
    origin_zone: Zone = Zone.HAND
    chosen_modes: list[str] = Field(default_factory=list)
    """The text of each mode announced, in the order it was announced."""
    chosen_mode_numbers: list[int] = Field(default_factory=list)
    """Those same modes as their 1-based position on the card (CR 700.2)."""
    entwined: bool = False
    """CR 702.42a: the entwine cost is being paid, so every mode was chosen."""
    targets: list[TargetRef] = Field(default_factory=list)
    division: list[int] | None = None
    """CR 601.2d's announced division, one share per entry of `targets` in
    order - set by `announce_division`, `None` until then (and `None` stays
    the answer for a spell that never calls it, so `machines/effects.py`'s
    divided-damage effect falls back to splitting as evenly as it goes, the
    behaviour every existing scenario that never announces a division already
    relies on)."""
    mode_target_slices: list[list[TargetRef]] = Field(default_factory=list)
    """CR 700.2f: `self.targets`, the same announcement, bucketed one list per
    chosen mode instance instead of flattened - set by `choose_targets`, and
    parallel to `chosen_mode_numbers` (a mode chosen twice, where the card
    allows it, gets two entries here, one per instance)."""
    x_value: int = 0
    x_value_at_targets: int | None = None
    """The value `x_value` held the moment `choose_targets` ran, or None if it
    has not run yet. `choose_modes` and `determine_cost` are two independent
    setters of `x_value` (CR 107.3a's X is fixed once for the whole spell, but
    nothing before this stopped a caller from calling only one of them) - a
    caller that announces targets under one X and then changes it before
    `cast()` would count a mode's "up to X target ..." against the X it had
    when targets were chosen, not the X the spell actually resolves with.
    `cast()` compares this against the final `x_value` and refuses loudly
    rather than let that mismatch through silently."""
    locked_amount: int | None = None
    """The count a "where X is `<count>` as you cast this spell" definition
    fixed while this spell was being cast (Jaws of Stone, Monstrous Onslaught),
    or None when its text prints no such definition. CR 601.2d needs the total
    to announce a division, so it is read once, at the first CR 601.2 choice
    that wants it (`_lock_cast_amount`), kept here, and recorded as the cast's
    X (`CastRecord.x_value`) for resolution to read back rather than recount."""
    face: str | None = None
    """The name of the face being cast, for a card with more than one (CR 715.3)."""
    face_cast_refusals: dict[str, str] = Field(default_factory=dict)
    """Why CR 601.3 refuses this proposal for each face, keyed by face name.

    CR 601.3 is the umbrella - "A player can begin to cast a spell only if a
    rule or effect allows that player to cast it and no rule or effect
    prohibits that player from casting it" - and two independent questions
    live under it: CR 117.1a's timing (`why_cannot_cast_now`) and CR 611.1's
    rules-modifying prohibitions (`why_cannot_cast_restriction`). Both read
    card types, and CR 601.3e makes that a per-face read: "Some rules and
    effects state that an alternative set of characteristics or a subset of
    characteristics are considered to determine if a card or copy of a card
    is legal to cast. These alternative characteristics replace the object's
    characteristics for this determination." CR 709.3a and CR 715.3a are its
    two instances here, and CR 709.3/715.3 both put the choice of face
    **before** the card goes onto the stack.

    This engine drives CR 601.2 a step at a time, so a caller reaches
    `cast_as_split_half`/`cast_as_adventure` only after `model_post_init` has
    already run CR 601.2a's move - at which point CR 307.1's "when the stack
    is empty" is false because of this very spell, and `spell.zone` is the
    stack rather than the zone a zone-prohibition (Soulless Jailer) must be
    asked about. Neither question can be asked honestly from there. So both
    are asked once, at the proposal, for every option `castable_faces`
    offers, and the answers are frozen here for whichever face the caller
    goes on to name.

    Only the refused faces are stored; a face absent from this dict is one
    CR 601.3 allows. `""` is the key for "no face named" - the card's own
    characteristics, which is how a single-faced card and an adventurer
    card's own creature half are cast. No printed face is named `""`.

    A proposal is refused outright only when *every* option is refused
    (`model_post_init`): Incubation // Incongruity is `Sorcery // Instant`,
    so at instant speed the front half is illegal and the back half legal,
    and refusing the proposal on the front half's answer would put Incongruity
    - a plain Instant - out of reach. The same holds for a restriction: under
    "your opponents can't cast noncreature spells this turn", Bonecrusher
    Giant's creature half is legal while Stomp is not.
    """
    timing_refusals_unless_flash_grant: dict[str, str] = Field(default_factory=dict)
    """CR 117.1a refusals set aside at the proposal because an alternative cost
    grants flash (`flash_grant_sources`), keyed like `face_cast_refusals`;
    `cast()` raises them unless that alternative cost is the one paid."""
    flash_surcharge_owed: bool = False
    """Whether the spell's own "cast this spell as though it had flash if you pay
    {2} more" is what lets it be cast now: judged at the proposal, before CR 601.2a
    puts the spell on the stack and the stack stops being empty (`_own_flash_surcharge`)."""
    timing_refusals_unless_window: dict[str, str] = Field(default_factory=dict)
    """CR 117.1a refusals `model_post_init` set aside because a keyword whose
    own timing is a window (`CastTiming.OWN_DECLARE_BLOCKERS`, CR 702.190a's
    sneak) is open right now, keyed like `face_cast_refusals`.

    The window is permission for *that* keyword's cast only: a sorcery with
    sneak is castable during its caster's declare blockers step by sneak and
    by nothing else. The keyword is not announced until `use_keyword`, after
    the proposal, so the refusal is held here and `cast()` raises it unless
    the keyword actually used was the one that opened the window."""
    timing_refusals_unless_keyword_timing: dict[str, str] = Field(default_factory=dict)
    """CR 117.1a refusals set aside at the proposal because some option for
    the card's zone carries a timing of its own (`_keyword_option_answers_
    timing`: plot, sneak, a pile's flash, madness, a sorcery-timed graveyard
    grant), keyed like `face_cast_refusals`. Another option for the same card
    - flashback beside Kess, Dissident Mage's grant - keeps the card's own
    timing, so `cast()` raises the refusal unless the option used is one that
    answers timing itself (`keyword_answers_timing`)."""
    keyword_answers_timing: bool = False
    """Whether `keyword_used`'s option decides its own timing in
    `KeywordCastOption.why_not` - what lets `cast()` drop a held
    `timing_refusals_unless_keyword_timing` entry."""
    extra_mana_counters: int = 0
    """The amount of mana paid as "any amount of mana" for that many +1/+1
    counters (`pay_extra_mana_for_counters`), copied onto
    `CastRecord.extra_mana_counters`."""
    keyword_snow_any_color: bool = False
    """The claimed option's `KeywordCastOption.snow_any_color`: mana from snow
    sources pays the cost as though it were any color (CR 609.4b)."""
    keyword_enters_with_counters: tuple[str, ...] = ()
    """The claimed option's `KeywordCastOption.enters_with_counters`, copied
    onto `CastRecord.enters_with_counters` as the spell becomes cast."""
    announced_library_top: bool | None = None
    """Whether the card was the top card of its caster's library when the
    cast was proposed - CR 601.2a has moved it by the time a "from the top of
    your library" permission is asked about it, so the answer is kept here.
    None for a cast from anywhere else."""
    announced_library_index: int | None = None
    """Where in its owner's library the card sat when the cast was proposed,
    so a rewound cast (CR 601.6, CR 733.1: "the spell returns to the zone it
    came from") puts it back in the same place - a library is ordered (CR
    401.2), and a card cast off the top that comes back to the bottom is a
    different game."""
    keyword_opens_window: bool = False
    """Whether `keyword_used`'s option carries a timing window of its own
    (`CastTiming.OWN_DECLARE_BLOCKERS`) - what lets `cast()` drop a held
    `timing_refusals_unless_window` entry."""
    returned_mana_value: int = 0
    """The mana value of the creature chosen to be returned for web-slinging
    (CR 702.188a), read as it is chosen (CR 601.2b) and copied onto
    `CastRecord.returned_mana_value`."""
    returned_creature_defender: TargetRef | None = None
    """The player, planeswalker or battle the creature returned to pay a
    sneak cost was attacking (CR 702.190b), read as the creature is chosen
    (CR 601.2b) - once CR 601.2h's return has moved it, it is out of combat
    (CR 506.4) and `Combat.attack_by` has nothing left to say. Copied onto
    `CastRecord.sneak_defender` as the spell becomes cast."""
    transformed: bool = False
    """True once `cast_transformed` has announced a nonmodal double-faced
    card cast "transformed" (CR 712.11a): the spell is put on the stack with
    its back face up and has only that face's characteristics (CR 712.8c)."""
    fuse: bool = False
    """True once `cast_fused` has announced both halves of a split card with
    fuse as one spell (CR 702.102a). `self.face` still names the left half
    while this is set - see `cast_fused`'s own docstring."""
    keyword_normal_face_only: bool = False
    """The claimed option's `KeywordCastOption.normal_face_only` (CR 715.3d),
    set by `use_keyword` alongside `keyword_used`."""
    keyword_face_only: str | None = None
    """The claimed option's `KeywordCastOption.face_only` (CR 702.127a's
    aftermath half), set by `use_keyword` alongside `keyword_used`."""
    keyword_used: str | None = None
    """The keyword this spell is being cast with, if any (CR 601.2b).

    Set by `use_keyword`. Kept on the casting because several keywords have a
    second half that fires afterwards - evoke's sacrifice trigger (CR 702.74a),
    flashback's exile replacement (CR 702.34a), warp's delayed trigger
    (CR 702.185a) - and none of them can be applied without knowing the spell
    was cast that way.
    """
    keyword_cost_paid: bool = False
    """Whether the cost `keyword_used` names was paid, rather than the mana cost.

    Warp hands out two options under one keyword: the warp cost from hand and,
    for a warped card in exile, a cast for its own mana cost. CR 702.185a's
    delayed exile applies only "If this spell's warp cost was paid", so the
    keyword alone cannot answer it (battle report B6-04). Set by `use_keyword`
    from the option's `pays_mana_cost`.
    """
    permission_used: PlayPermission | None = None
    """The `PlayPermission` this spell is being cast under, if any (CR 601.3).

    Set by `use_permission`. Kept for the same reason `keyword_used` is: it is
    what `cast()` checks to know the CR 601.3 permission was actually claimed,
    rather than inferred after the fact from the zone the card happened to be
    in."""
    keyword_exiles_instead: bool = False
    """The keyword option `use_keyword` chose carries CR 614.1a's "If a spell
    cast this way would be put into a graveyard, exile it instead." - copied
    onto `CastRecord.exile_instead_of_graveyard` by `cast()`."""
    keyword_pays_life_for_mana_value: bool = False
    """The claimed option's `KeywordCastOption.pays_life_for_mana_value`:
    `total_cost` adds the life equal to the spell's mana value."""
    keyword_once_per_turn_key: str | None = None
    keyword_any_type_mana: bool = False
    """The claimed option's CR 609.4b \"mana of any type can be spent\"."""
    """The once-each-turn grant the chosen option spends
    (`KeywordCastOption.once_per_turn_key`), recorded as used when `cast()`
    completes - not before, since CR 601.6 can still rewind the announcement."""
    keyword_any_color: bool = False
    """The claimed option's `KeywordCastOption.any_color` (CR 609.4b)."""
    treasure_mana_only: bool = False
    """The chosen alternative cost says "Spend only mana produced by Treasures
    to cast it this way." (Security Rhox) - `determine_cost` hands it to the
    payment's `ManaSpend`."""
    alternative_cost: TotalCost | None = None
    free_cast_source: str | None = None
    """The permanent whose static ability applied CR 118.9's alternative cost
    of nothing to this spell - Omniscience. Set by `use_alternative_cost` on
    an `AlternativeCostSource.STATIC` option, and kept for the same reason
    `keyword_used` is: an empty `alternative_cost` on its own cannot say
    whether it came from the spell's own text or from somebody's board."""
    additional_costs: list[TotalCost] = Field(default_factory=list)
    sacrificing: list[CardState] = Field(default_factory=list)
    """The permanents chosen to pay a printed "sacrifice ..." additional cost.

    CR 601.2b is when they are chosen ("the player announces their intentions
    to pay any or all of those costs", CR 118.8a) and CR 601.2h is when they
    are actually sacrificed, so they sit here from announcement until
    `determine_cost` folds them into `additional_costs`. Leaving the list short
    builds a cost that correctly refuses to be paid (CR 118.3) rather than one
    that cannot be built - the same shape `Game.activation_cost` already uses
    for an activated ability's object costs, and the same vocabulary.
    """
    discarding: list[CardState] = Field(default_factory=list)
    """The cards chosen to pay a printed "discard ..." additional cost."""
    exiling: list[CardState] = Field(default_factory=list)
    """The cards chosen to pay a printed "exile ..." additional cost."""
    tapping: list[CardState] = Field(default_factory=list)
    """The permanents chosen to pay a printed "tap ..." additional cost -
    Swallow Whole's "tap an untapped creature you control"."""
    beholding: list[CardState] = Field(default_factory=list)
    """The card or permanent chosen to pay a printed "behold ..." additional
    cost (CR 701.4a) - a hand card to reveal or a battlefield permanent to
    choose, told apart at payment time by `component.cards[0].zone`."""
    revealing: list[CardState] | None = None
    """The cards chosen to pay a printed "reveal ... from your hand" additional
    cost (CR 118.8a, CR 701.20a) - Living Destiny's "reveal a creature card
    from your hand". `None` is "not named", and CR 601.2f then asks the caster
    which cards to reveal (`Game.choose_cards_to_reveal`); an empty list is an
    answer of its own."""
    spliced_card_ids: list[UUID] = Field(default_factory=list)
    """The cards revealed from the caster's hand to splice onto this spell
    (CR 702.47a), in the order they were announced.

    Ids rather than `CardState`s, because a spliced card never moves: it is
    revealed and stays in hand, and this list only has to say which cards were
    revealed - CR 702.47b's "You can't splice any one card onto the same spell
    more than once" is the one question asked of it afterwards."""

    spliced_text: list[str] = Field(default_factory=list)
    """The rules text each spliced card adds, in announcement order (CR
    702.47c, CR 612.10). Written onto `CardState.spliced_text` by `cast()`,
    not before: until the announcement is complete CR 601.6/CR 733.1 can still
    reverse the whole thing, and a rewound casting must leave no text behind.
    """

    printed_additional_costs_charged: bool = False
    """Whether the card's own "As an additional cost to cast this spell, ..."
    sentences have already been folded into `additional_costs` (CR 601.2f).
    Once, and only once: `determine_cost` can be reached more than one way."""
    cost_increases: list[ManaCost] = Field(default_factory=list)
    cost_reductions: list[ManaCost] = Field(default_factory=list)
    self_reduction: ManaCost | None = None
    """The spell's own CR 601.2f discount, as it stood when the total cost was
    determined - `Game.cost_reduction_for`'s answer, frozen by
    `determine_cost`. None until then, and `total_cost` reads the live board
    while it is None, because CR 601.2f is the moment the reduction is
    computed and CR 601.2f is also the moment it stops moving ("Then the
    resulting total cost becomes 'locked in.' If effects would change the
    total cost after this time, they have no effect")."""
    kicked: int = 0
    """How many times this spell's kicker cost was paid (CR 702.33d).

    "If a spell's controller declares the intention to pay any of that spell's
    kicker costs, that spell has been 'kicked.'" Kept as a count rather than a
    flag because CR 702.33c's multikicker may be paid any number of times.
    """
    replicated: int = 0
    """How many times this spell's replicate cost was paid (CR 702.56a).

    "'Replicate [cost]' means 'As an additional cost to cast this spell, you
    may pay [cost] any number of times.'" `pay_replicate` is `pay_kicker`'s
    own shape - always the "multi" branch, since CR 702.56a has no
    plain-kicker-style single-payment restriction the way CR 702.33a/c
    distinguishes kicker from multikicker.
    """
    granted_life_paid: list[GrantedLifeCost] = Field(default_factory=list)
    """The optional life costs other permanents grant this spell that were
    announced (CR 118.8b), set by `pay_granted_life_cost`."""
    colored_only_reductions: list[Color] = Field(default_factory=list)
    """The colours whose `{C}` reduction a paid granted life cost applies to
    the spell's mana cost - and only if the cost has such a coloured symbol
    (CR 118.7a, the Defilers' "reduces only the amount of ... mana you pay")."""
    casualty_paid: int = 0
    """How many of this spell's casualty instances were paid (CR 702.153a,
    CR 702.153b: "each is paid separately"), set by `pay_casualty`."""
    casualty_x: int | None = None
    """The X announced for a "Casualty X" instance (CR 107.3a), or None."""
    conspire_paid: int = 0
    """How many of this spell's conspire instances were paid (CR 702.78a),
    set by `pay_conspire`."""
    offspring_paid: bool = False
    """Whether this spell's offspring cost was paid (CR 702.175a), set by
    `pay_offspring`. A flag rather than `kicked`'s count: offspring has no
    "multi" variant to pay more than once."""
    blight_paid: bool = False
    """Whether this spell's blight cost was paid (CR 701.68a), set by
    `pay_blight` - read by whatever linked ability the card's own printed
    text carries ("If this spell's additional cost was paid, ...")."""
    teamwork_paid: bool = False
    """Whether this spell's Teamwork cost was paid, set by `pay_teamwork` -
    `machines/teamwork.py`'s own additional cost, CR 601.2b's optional kind.
    A flag rather than a count: every printing in the pool reads "If this
    spell was cast using teamwork", never a per-payment variant the way
    kicker's own "if it was kicked with its [quality] kicker" (CR 702.33f,
    not in this pool either) would need a count for."""
    paying_life_for_additional_cost: frozenset[int] = Field(default_factory=frozenset)
    """Which of CR 601.2b's "[cost] or pay [mana]" additional-cost sentences
    (`_OR_PAY_TAIL`, indexed the same way `additional_cost_phrases` orders
    them) the caster is paying with a life-total primary instead of the mana
    alternative - Redirect Lightning's own "pay 5 life or pay {2}".

    `_additional_cost_primary_alternatives` otherwise infers which side is
    being paid from whether objects were nominated for the primary's own
    `ComponentKind` pool (`sacrificing`, `discarding`, ...) - the same way
    `sacrificing=[...]` already says "pay Fling's plain sacrifice cost" with
    no separate flag. A life payment has no object to nominate at all, so
    that inference always saw an empty pool and silently fell through to
    the mana half no matter what the caster wanted - the payer could not
    choose. This is `ComponentKind.PAY_LIFE`'s own explicit twin of that
    object-pool inference, read the identical way `blight_paid` already
    flags a choice with no object behind it either.
    """
    gift_promised: bool = False
    """Whether this spell's gift was promised (CR 702.174k), set by
    `pay_gift`."""
    kicker_costs_paid: list[str] = Field(default_factory=list)
    """Which kicker costs were paid, each as printed (CR 702.33b, CR 702.33f),
    in announcement order - `pay_kicker` appends one per payment."""
    bargained: bool = False
    """Whether this spell's bargain cost was paid (CR 702.166b), set by
    `pay_bargain`."""
    evidence_collected: bool = False
    """Whether evidence was collected for an optional "you may collect
    evidence N" additional cost (CR 701.59a, CR 701.59c), set by
    `collect_evidence`."""
    revealed_for_cost: bool = False
    """Whether a card was revealed for an optional "you may reveal a
    <quality> card from your hand" additional cost (CR 118.8b), set by
    `reveal_for_cost`."""
    beheld_for_cost: bool = False
    """Whether a plain, unrestricted "you may behold a <quality>" additional
    cost (CR 118.8b, CR 701.4a) was paid - Dispelling Exhale's own "you may
    behold a Dragon", set by `behold_for_cost`. Distinct from `behold_
    chosen_type_paid`: this cost's quality is fixed by the card's own
    printed text, never chosen as the spell is cast."""
    waterbend_paid: bool = False
    """Whether a printed "you may waterbend {N}" additional cost was announced
    and charged (CR 118.8b, CR 701.67a), set by `pay_waterbend`. Read by the
    generic "if this spell's additional cost was paid" (`CastRecord.
    optional_additional_cost_paid`) and by CR 701.67c's "whenever you
    waterbend" event, raised as the spell becomes cast."""
    sacrificed_for_cost_reduction: int = 0
    """How many objects were sacrificed for an optional "you may sacrifice
    any number of <quality>. This spell costs <amount> less to cast for
    each <noun> sacrificed this way." additional cost (CR 118.7a, CR
    118.8b), set by `sacrifice_for_cost_reduction` - Rottenmouth Viper's
    own. Zero (the default) both before the cost is announced and when the
    caster announced it but chose to sacrifice nothing, so this alone never
    answers "was the cost paid" the way `evidence_collected`'s bare boolean
    does; nothing printed in the pool needs that distinction yet."""
    exiled_for_cost_reduction: int = 0
    """How many cards were exiled from hand for an optional "you may exile any
    number of <quality> cards from your hand. This spell costs <amount> less
    to cast for each card exiled this way." additional cost (CR 118.7a, CR
    118.8b), set by `exile_for_cost_reduction` - March of Wretched Sorrow's
    own. Zero both before the cost is announced and when none were exiled."""
    gift_chosen_player: str | None = None
    """The opponent chosen when the gift was promised (CR 702.174a's own
    additional cost, "you may choose an opponent") - who "the chosen player"
    (CR 702.174d-i) refers to."""
    behold_chosen_type_paid: bool = False
    """Whether an optional "you may choose a creature type and behold [N]
    creatures of that type" additional cost (CR 118.8b, 701.4a) was paid -
    Celestial Reunion's own, set by `behold_chosen_type_for_cost`."""
    chosen_creature_type_for_cost: str | None = None
    """The creature type named paying `behold_chosen_type_paid` (CR 607.2d) -
    lowercased, set alongside it by `behold_chosen_type_for_cost`."""
    payment: CostPayment | None = None
    announced_zone: Zone | None = None
    """The zone this cast was announced from, recorded as CR 601.2a moved the
    card to the stack. None when no move was made (no game, or a card that was
    not where the announcement said it was)."""
    announced_stamp: UUID | None = None
    """The card's CR 400.7 identity stamp before that move - what a
    `PlayPermission` recorded against the object it granted still names
    (CR 400.7h)."""
    announced_exile_annotation: ExileAnnotation | None = None
    """The exile pile the card was in before that move (CR 406.5): plot,
    foretell, madness and warp all cast out of a *particular* pile, and the
    move to the stack drops the annotation."""
    announced_granted_ability_texts: tuple[str, ...] = ()
    """The keyword lines the card was granted before that move (a madness it
    was discarded with, CR 702.35a): CR 400.7 clears them on the move, and the
    cast option they name is asked of `_as_announced`."""
    announced_counters: Counters | None = None
    """The counters the card carried before that move (CR 122.1; CR 122.2 and
    CR 400.7 strip them as CR 601.2a moves it to the stack): Draugr
    Necromancer's "cards in exile ... with ice counters on them", Evelyn, the
    Covetous's "with a collection counter on it" and Grolnok's "cards you own
    in exile with croak counters on them" are judged as the cast is proposed
    (CR 601.3), so a grant asked about the announced card still has to see
    them."""
    announced_discarded_by: str | None = None
    """Who had discarded the card before that move (CR 701.9a), and"""
    announced_discarded_on_turn: int | None = None
    """which turn they discarded it on - `CardState.discarded_by` and
    `discarded_on_turn`, kept for the same reason the exile annotation above is.
    Mayhem's own "as long as you discarded this card this turn" (CR 702.187b) is
    a question about the card as it sat in the graveyard, and CR 601.2a's move
    to the stack has already made it a new object that nobody discarded."""

    def model_post_init(self, _context: object) -> None:
        """CR 305.1: a land is refused outright, before anything else, because
        it was never a spell to begin with; then CR 601.3: the announcement
        is refused if the timing does not allow it; then CR 601.2a: the card
        moves to the stack the moment it is not.

        "A player can begin to cast a spell only if a rule or effect allows that
        player to cast it and no rule or effect prohibits that player from
        casting it." The timing rules of CR 117.1a are such a prohibition, so
        they are checked here rather than after the cost has been paid - but
        both of those questions presuppose a spell in the first place
        (`why_cannot_cast_a_land`'s own docstring is why that check runs
        first, not after).

        Then CR 601.2a runs: "To propose the casting of a spell, a player first
        moves that card (or that copy of a card) from where it is to the stack.
        It becomes the topmost object on the stack." CR 112.1 says the same
        thing from the object's side, and CR 405.1 from the stack's. It is the
        *first* step, five steps ahead of CR 601.2f's cost determination, which
        is why a spell counting its controller's graveyard does not count
        itself - and why announcing a cast empties the zone the card came from
        straight away.

        **CR 709.3 puts the choice of half before all of this**: "A player
        chooses which half of a split card they are casting before putting it
        onto the stack", and CR 715.3 says the same for an adventurer card.
        CR 709.3a/715.3a then evaluate only that chosen half to see if it can
        be cast - CR 117.1a's timing and CR 611.1's prohibitions both
        included, since CR 601.3e makes the chosen face's characteristics
        *replace* the object's for exactly this determination. This is
        therefore the only moment either question can be asked honestly for
        each half: once CR 601.2a's move below has run, CR 307.1's "when the
        stack is empty" is false because of this very spell, and `spell.zone`
        is the stack rather than the zone Soulless Jailer must be asked
        about.

        So both are asked here for every option `castable_faces` offers and
        the answers are frozen onto `face_cast_refusals`, which
        `cast_as_split_half`, `cast_as_adventure` and `cast` then read. The
        proposal itself is refused only when **every** option is refused: a
        `Sorcery // Instant` split card at instant speed has one illegal half
        and one legal one, and refusing on the front half's answer would put
        the legal half out of reach entirely.
        """
        refusal = why_cannot_cast_a_land(self.spell)
        if refusal is not None:
            raise ValueError(refusal)
        self.flash_surcharge_owed = (
            self.game is not None
            and flash_surcharge(self.spell.oracle_text or "") is not None
            and not self.game.can_cast_sorcery(self.caster)
            and Type.INSTANT not in self.spell.types_as_a_spell(types_being_cast(self.spell.card))
        )
        options = castable_faces(self.spell.card) if self.face is None else (self.face,)
        refusals: dict[str, str] = {}
        # CR 712.11c: a card cast transformed is evaluated as its back face.
        back_face = self.spell.card.back_face if self.transformed else None
        for option in options:
            evaluated = back_face.name if back_face is not None and option is None else option
            timing = why_cannot_cast_now(self.spell, self.caster, self.game, face=evaluated)
            if timing is None:
                strict = why_cannot_cast_now(
                    self.spell,
                    self.caster,
                    self.game,
                    face=evaluated,
                    without_alternative_flash=True,
                )
                if strict is not None:
                    # Allowed only because an alternative cost grants flash
                    # (Primal Prayers): `cast()` raises `strict` unless that
                    # cost is the one this cast pays.
                    self.timing_refusals_unless_flash_grant[option or ""] = strict
                strictest = why_cannot_cast_now(
                    self.spell,
                    self.caster,
                    self.game,
                    face=evaluated,
                    without_alternative_flash=True,
                    without_keyword_timing=True,
                )
                if strictest is not None and strict is None:
                    # Allowed (at least) because an option with its own timing
                    # exists: `cast()` raises `strictest` unless the option
                    # used is such an option - or, when an alternative cost
                    # grants flash too, unless that cost is paid.
                    self.timing_refusals_unless_keyword_timing[option or ""] = strictest
                    if (
                        why_cannot_cast_now(
                            self.spell,
                            self.caster,
                            self.game,
                            face=evaluated,
                            without_keyword_timing=True,
                        )
                        is None
                    ):
                        self.timing_refusals_unless_flash_grant[option or ""] = strictest
            if timing is not None:
                window_refusal = self._timing_window_refusal()
                if window_refusal is None:
                    # A timing window is open (CR 702.190a); `cast()` raises
                    # `timing` unless that window's own keyword is used.
                    self.timing_refusals_unless_window[option or ""] = timing
                    timing = None
                elif window_refusal:
                    timing = f"{timing}; and {window_refusal}"
            reason = (
                timing
                or why_cannot_cast_restriction(self.spell, self.caster, self.game, face=evaluated)
                or why_cannot_cast_self_restriction(self.spell, self.caster, self.game)
                or aftermath_face_refusal(self.spell.card, evaluated, self.origin_zone)
            )
            if reason is not None:
                refusals[option or ""] = reason
        if len(refusals) == len(options):
            raise ValueError(next(iter(refusals.values())))
        self.face_cast_refusals = refusals
        if self.game is None:
            # No game to hold a stack, no `_id_allocator_scope` to open - see
            # `_move_to_the_stack`'s own early return for this same case.
            self._move_to_the_stack()
        else:
            # CR 601.2a's move mints `self.spell`'s new `zone_change_stamp`
            # (`CardState.move_to`), so it has to run with `Game._allocate_id`
            # installed - `Game.objects_created`'s own docstring is why every
            # mutating public entry point needs this, and constructing a
            # `Casting` with a `game` is exactly that: it is this whole
            # machine's own CR 601.2a moment, reached before any explicit
            # method call on the object the caller gets back.
            with self.game._id_allocator_scope():
                self._move_to_the_stack()

    def _timing_window_refusal(self) -> str | None:
        """Whether a keyword with its own timing window lets this card be cast
        right now though CR 117.1a would not: None if one does, the first
        window keyword's own refusal if none does, and `""` if the card has no
        such keyword at all.

        Asked at the proposal, before CR 601.2a's move, which is the moment
        CR 601.3 asks its question about.
        """
        windows = [
            option
            for option in keyword_cast_options(self.spell.card)
            if option.timing is CastTiming.OWN_DECLARE_BLOCKERS and option.zone is self.origin_zone
        ]
        if not windows:
            return ""
        reasons = [
            option.why_not(self.spell, self.caster, self.game, origin=self.origin_zone)
            for option in windows
        ]
        if any(reason is None for reason in reasons):
            return None
        return next(reason for reason in reasons if reason is not None)

    # -- CR 601.2a: the card is on the stack from here on ------------------

    def _move_to_the_stack(self) -> None:
        """Put the card on the stack as the proposal begins (CR 601.2a).

        Skipped without a game to hold a stack, and skipped when the card is
        not where the announcement says it is coming from - that mismatch is
        its own refusal further down (CR 604.6), and moving first would erase
        the evidence for it.

        What the card was when it was announced is kept in `announced_zone`,
        `announced_stamp` and `announced_exile_annotation`, because CR 400.7
        makes the object on the stack a *new* object and several of this
        machine's own questions are about the old one: which zone the cast is
        coming from (CR 604.6, a keyword's own zone clause), and whether an
        effect's `PlayPermission` still names it. CR 400.7h is the rule that
        keeps the second one true across the move - "If an effect allows a
        nonland card to be cast, other parts of that effect can find the new
        object that card becomes after it moves to the stack as a result of
        being cast this way" - and CR 400.7g says the same for a granted
        castability ability. `_as_announced` is the view every one of those
        questions is asked of.
        """
        game = self.game
        if game is None or self.spell.zone is not self.origin_zone:
            return
        self.announced_zone = self.spell.zone
        self.announced_stamp = self.spell.zone_change_stamp
        self.announced_exile_annotation = self.spell.exile_annotation
        self.announced_counters = self.spell.counters.model_copy(deep=True)
        self.announced_granted_ability_texts = self.spell.granted_ability_texts
        self.announced_discarded_by = self.spell.discarded_by
        self.announced_discarded_on_turn = self.spell.discarded_on_turn
        if self.spell.zone is Zone.LIBRARY:
            self.announced_library_top = is_top_of_library(game, self.spell, self.caster)
            library = game.player(self.spell.owner or self.caster).library
            if self.spell in library:
                self.announced_library_index = library.index(self.spell)
        self._lift_out_of_every_zone()
        self.spell.move_to(Zone.STACK)
        self.spell._announced_from = self.announced_zone
        # CR 712.11a: `move_to` turns a card leaving for the stack front face
        # up; one cast transformed goes there back face up.
        self.spell.transformed = self.transformed
        game.stack.append(self.spell)
        from ..text_changes import sync_text_changes

        sync_text_changes(game)  # CR 612.1: a spell's text is changed from the stack on

    def _lift_out_of_every_zone(self) -> None:
        """Take the card out of whatever list is holding it, shared zones
        included - exile and the command zone are not any one player's."""
        for player in getattr(self.game, "players", []):
            for zone_cards in player.zones.values():
                if self.spell in zone_cards:
                    zone_cards.remove(self.spell)
        for zone_cards in getattr(self.game, "shared_zones", {}).values():
            if self.spell in zone_cards:
                zone_cards.remove(self.spell)

    def _refusing(self, run: "Callable[[], Any]") -> Any:
        """Run one announcement step, rewinding the whole proposal if it is
        refused (CR 601.6, CR 733.1).

        "If a player can't legally cast the spell, the game returns to the
        moment before the casting was proposed." That used to be free, because
        nothing had moved yet; CR 601.2a has since put the card on the stack,
        so a refusal has something to undo. `cancel` is the same rewind a
        caller can ask for by hand, and it puts the card back where it came
        from with the identity it had (CR 400.7).
        """
        try:
            return run()
        except ValueError:
            if not self.is_settled:
                self.cancel()
            raise

    @contextmanager
    def _as_of_the_proposal(self) -> "Iterator[None]":
        """Ask a timing question as of the moment the cast was proposed.

        CR 117.1a and CR 307.5's "the stack is empty" are conditions on
        *beginning* to cast (CR 601.3), which happens before CR 601.2a moves
        the card onto the stack. With the card already there, asking
        `Game.can_cast_sorcery` would find a non-empty stack and refuse every
        sorcery-timing keyword - plot's "Plot only as a sorcery" (CR 702.170a)
        - on the strength of the very spell being proposed. Inside this block
        the spell is off the stack list again, which is the state the question
        is really about.
        """
        stack = getattr(self.game, "stack", None)
        present = stack is not None and self.spell in stack
        if present:
            index = stack.index(self.spell)
            stack.remove(self.spell)
        try:
            yield
        finally:
            if present:
                stack.insert(index, self.spell)

    @property
    def _as_announced(self) -> CardState:
        """The spell as it was when the cast was proposed (CR 601.2a).

        A copy carrying the zone, the CR 400.7 identity stamp and the exile
        annotation the card had before CR 601.2a moved it, so every question
        about *where this cast is coming from* keeps its answer once the card
        is on the stack. The copy is read-only as far as this machine is
        concerned: nothing is paid or moved through it.
        """
        if self.announced_zone is None:
            return self.spell
        return self.spell.model_copy(
            update={
                "zone": self.announced_zone,
                "zone_change_stamp": self.announced_stamp,
                "exile_annotation": self.announced_exile_annotation,
                "granted_ability_texts": self.announced_granted_ability_texts,
                **(
                    {"counters": self.announced_counters}
                    if self.announced_counters is not None
                    else {}
                ),
                "discarded_by": self.announced_discarded_by,
                "discarded_on_turn": self.announced_discarded_on_turn,
            }
        )

    @property
    def is_settled(self) -> bool:
        return self.step in {CastingStep.CAST, CastingStep.CANCELLED}

    @property
    def base_cost(self) -> ManaCost:
        """The printed mana cost of the spell.

        CR 118.9c: an alternative cost does not change this. It only changes
        what the caster has to pay, which is `total_cost`.

        A split card prints both halves in one `mana_cost` string,
        `{2}{R} // {1}{R}`, so the face being cast decides which half applies.
        CR 715.3 puts that choice on the caster for an adventurer card and
        CR 715.3a evaluates only the chosen face's characteristics.

        A transform or modal DFC is different again: Scryfall leaves the
        top-level `mana_cost` blank for those and puts each face's own cost on
        `card_faces` instead, because CR 712.8a only grants the card "the
        characteristics of its front face" outside the battlefield or stack -
        there is no combined cost to fall back to the way a split card has
        one. No face is ever explicitly chosen for these (`Casting.cast_as_adventure`
        is Adventure-only, CR 715.3), so the front face is the only one this
        reaches for.

        CR 702.102c/709.4b: a **fused** split spell's cost is both halves'
        mana costs added together, not either one alone - `ManaCost.plus`
        combines them symbol for symbol the same way a cost increase does.
        """
        if self.fuse and self.spell.card.card_faces:
            left, right = self.spell.card.card_faces[0], self.spell.card.card_faces[1]
            return ManaCost.parse(left.mana_cost or "").plus(ManaCost.parse(right.mana_cost or ""))
        face = self.chosen_face
        if face is not None:
            return ManaCost.parse(face.mana_cost or "")
        if self.spell.prepare_spell_face:
            # CR 722.3c: this object's own normal characteristics are its
            # prepare spell's - `card_faces[1]`, the inset frame - never the
            # front permanent's cost the two-face fallback below would
            # otherwise read (`CardState.mana_cost` already reads the same
            # face; this mirrors it for the announcement's own base cost).
            back_face = self.spell.card.back_face
            if back_face is not None:
                return ManaCost.parse(back_face.mana_cost or "")
        printed = self.spell.card.mana_cost or ""
        if "//" in printed and self.spell.card.card_faces:
            return ManaCost.parse(self.spell.card.card_faces[0].mana_cost or "")
        if not printed and self.spell.card.card_faces:
            return ManaCost.parse(self.spell.card.card_faces[0].mana_cost or "")
        return ManaCost.parse(printed)

    @property
    def chosen_face(self) -> Any:
        """The `CardFace` being cast, when the caster named one (CR 715.3)."""
        if self.face is None:
            return None
        for face in self.spell.card.card_faces or []:
            if face.name == self.face:
                return face
        raise ValueError(f"{self.spell.name} has no face called {self.face}")

    def cast_transformed(self) -> CastingStep:
        """CR 712.11a: "If a double-faced card ... is cast as a spell
        'transformed' ..., it's put on the stack with its back face up."
        CR 712.8c: it then has only its back face's characteristics, its mana
        value still calculated from the front face's mana cost. Only an
        effect that says so casts a card this way (a Siege's defeat trigger,
        CR 310.12b), so this is announced before CR 601.2a's move."""
        if self.spell.card.back_face is None:
            raise ValueError(f"{self.spell.name} has no back face to cast transformed (CR 712.11a)")
        self.transformed = True
        if self.spell.zone is Zone.STACK:
            self.spell.transformed = True
        return self.step

    def cast_as_adventure(self) -> CastingStep:
        """CR 715.3: cast the Adventure half of an adventurer card.

        CR 715.3b: "While on the stack as an Adventure, the spell has only its
        alternative characteristics." `CardState.face_played` records which
        face was chosen once `cast()` runs, and `CardState.up_face` reads it
        for the whole time the spell is on the stack; `base_cost`/
        `chosen_face` charge that face's cost, and `targeting` reads that
        face's own text for CR 601.2c (CR 715.3a: "only the alternative
        characteristics are evaluated to see if it can be cast").

        CR 715.3a is also why both CR 601.3 questions are asked of Stomp's
        own type line rather than the card's. Stomp is an `Instant -
        Adventure` printed on a Creature card, so reading Bonecrusher Giant's
        front-face Creature type refused it at instant speed (CR 117.1a) and
        let it through under "your opponents can't cast noncreature spells
        this turn" (CR 611.1) and under Soulless Jailer's "Players can't cast
        noncreature spells from graveyards or exile". `model_post_init` froze
        both answers per face (`face_cast_refusals`) before CR 601.2a's move,
        and this is where they are spent. The refusal leaves the proposal open for the caller to
        `cancel` (CR 601.6, CR 733.1), exactly as every other refusal in this
        machine does.
        """
        face = adventure_face(self.spell.card)
        if face is None:
            raise ValueError(f"{self.spell.name} has no Adventure (CR 715.1)")
        refusal = self.face_cast_refusals.get(face.name) or self._normal_face_only_refusal(
            face.name
        )
        if refusal is not None:
            raise ValueError(refusal)
        self._enter_modes()
        self.face = face.name
        return self.step

    def cast_as_split_half(self, face_name: str) -> CastingStep:
        """CR 709.3: choose which half of a split card to cast.

        "A player chooses which half of a split card they are casting before
        putting it onto the stack." Unlike `cast_as_adventure`, there is no
        modal structure to enter first - CR 709 names no bulleted choice, just
        the one face. `self.face` already drives `base_cost`/`chosen_face`
        (shared with Adventure); what is new here is recording the choice onto
        `self.spell` itself once cast (see `cast`), which `CardState.up_face`
        then reads for the whole time the spell sits on the stack (CR 709.3b) -
        Adventure's own equivalent gap is a separate, still-open limitation
        (`docs/engine-coverage.md`).

        Fuse (CR 702.102) - casting *both* halves as one spell - is
        `cast_fused` instead: this always names exactly one.

        **CR 709.3a's whole evaluation belongs to the half just named.**
        "Only the chosen half is evaluated to see if it can be cast" - and
        CR 117.1a's timing and CR 611.1's prohibitions are both part of that
        evaluation, CR 601.3e being the rule that substitutes the face's
        characteristics for the object's. `why_cannot_cast_now` used to be asked once,
        in `model_post_init`, before any half existed to name, where it could
        only read `Card.types` - i.e. the *front* face's type line. Measured
        live, that let Replicate, the **Sorcery** half of Repudiate //
        Replicate (`Instant // Sorcery`), be announced during an upkeep step,
        and refused Incongruity, the **Instant** half of Incubation //
        Incongruity (`Sorcery // Instant`), during one. `model_post_init` now
        freezes the answer per half (`face_cast_refusals`) before CR 601.2a
        moves the card - which is also the only moment a zone prohibition can
        be asked about the zone the cast actually comes from, since the move
        makes `spell.zone` the stack - and this is where it is spent; a refusal leaves the
        proposal open for the caller to `cancel` (CR 601.6, CR 733.1), the
        same as every other refusal in this machine.
        """
        # CR 712.11b: a modal double-faced card's caster chooses its face the
        # same way, before it goes on the stack - "Only the face that will be
        # face up on the stack is evaluated to determine if it can be cast"
        # (CR 712.11c) is CR 709.3a's own test. Only a back face that is not a
        # land is named here (`modal_dfc_spell_back_faces`);
        # the front is the default cast, with no face named at all.
        if self.spell.card.layout is Layout.MODAL_DFC:
            faces = list(modal_dfc_spell_back_faces(self.spell.card))
        elif self.spell.card.layout is Layout.SPLIT:
            faces = list(self.spell.card.card_faces or [])
        else:
            raise ValueError(f"{self.spell.name} is not a split card (CR 709)")
        for face in faces:
            if face.name == face_name:
                refusal = self.face_cast_refusals.get(face_name)
                if refusal is None and self.keyword_face_only not in (None, face_name):
                    refusal = aftermath_face_only_refusal(
                        self.spell.name, self.keyword_face_only, face_name
                    )
                if refusal is not None:
                    raise ValueError(refusal)
                self.face = face_name
                return self.step
        raise ValueError(f"{self.spell.name} has no half called {face_name}")

    def cast_fused(self) -> CastingStep:
        """CR 702.102a: cast both halves of a split card with fuse as one spell.

        "Fuse is a static ability found on some split cards ... that applies
        while the card with fuse is in a player's hand. If a player casts a
        split card with fuse from their hand, the player may choose to cast
        both halves of that split card rather than choose one half. This
        choice is made before putting the split card with fuse onto the
        stack. The resulting spell is a fused split spell."

        Sets `self.face` to the **left** half (CR 702.102d orders its own
        resolution "the left half and then ... the right half", so "left"
        is not an arbitrary choice of which name to keep) and `self.fuse`,
        which `base_cost`/`targeting` below and `cast()`'s own
        `CardState.fused` stamp all read. Unlike `cast_as_split_half`, both
        `card_faces` entries are in play at once - CR 702.102b: "A fused
        split spell has the combined characteristics of its two halves."
        """
        if self.spell.card.layout is not Layout.SPLIT:
            raise ValueError(f"{self.spell.name} is not a split card (CR 709)")
        faces = self.spell.card.card_faces or []
        if len(faces) != 2:
            raise ValueError(f"{self.spell.name} does not have two halves to fuse")
        if _keyword(self.spell.card, "fuse") is None:
            raise ValueError(f"{self.spell.name} does not have fuse (CR 702.102a)")
        self.face = faces[0].name
        self.fuse = True
        return self.step

    @property
    def modal(self) -> ModalProfile | None:
        """This card's modal structure, or None if it is not modal (CR 700.2)."""
        return modal_profile(self.spell.card)

    @property
    def chosen_mode_objects(self) -> tuple[Mode, ...]:
        """The announced modes, resolved back to the card's own bullets."""
        modal = self.modal
        if modal is None:
            return ()
        return tuple(modal.mode(number) for number in self.chosen_mode_numbers)

    @property
    def targeting(self) -> TargetingProfile:
        """What this spell must target given whether its gift was promised
        (CR 702.174m): `_printed_targeting` with the gift-conditional
        requirements resolved."""
        return self._printed_targeting().for_gift_promise(self.gift_promised)

    def _printed_targeting(self) -> TargetingProfile:
        """What this spell is allowed to target, read off its oracle text.

        For a modal spell this is the profile of the *chosen* modes (CR 700.2c),
        which is why it can only be asked once the modes are announced. Before
        that, and for a modal card whose modes were never announced, it is the
        card-wide profile, which says `understood=False`.

        A split card (CR 709) reads its *chosen* half's own text once
        `cast_as_split_half` has named one - `targeting_profile(card)` reads
        the printing's front half otherwise (`Card.front_oracle_text`), which
        is CR 709.3b's wrong answer for a spell that has "only the
        characteristics of the half being cast".

        **An Adventure reads its own face the same way** (CR 715.3a: "only
        the alternative characteristics are evaluated to see if it can be
        cast"; CR 715.3b: "while on the stack as an Adventure, the spell has
        only its alternative characteristics"). That is word for word CR
        709.3a/709.3b's test, and this branch used to be scoped to
        `Layout.SPLIT` alone, which left the identical rule unimplemented for
        the other layout that names a face: Stomp, announced against
        Bonecrusher Giant's whole printing, had **zero** target requirements,
        so a targetless Stomp was cast happily and resolved dealing no damage
        while a targeted one was refused for "too many targets". Two rules
        with the same words and one of them implemented is the silent-default
        shape `memory/silent-default-dispatch-tables.md` is about.

        The discriminator is therefore `self.face`, not the layout - the same
        choice `face_being_cast` makes, and nothing sets `face` for a layout
        that names no face (CR 712.8a's double-faced cards are cast as their
        front, and `castable_faces` offers them nothing else).

        A **non-modal** card whose own mana cost has `{X}` (Postmortem
        Lunge's own "target creature card with mana value X") reads its text
        with X already substituted (CR 107.3a: X is announced before targets,
        so it is always known here). `profile_for_modes` already does the
        equivalent substitution for a *modal* card's chosen mode text; this is
        the same idea for the plain, unmoded case, which had no substitution
        at all before - `targeting_profile(card)` takes only the card, never
        an X, so "mana value X" came back an unresolvable bare X forever, at
        both announcement and `Game.legal_target`'s CR 608.2b recheck.
        """
        if self.modal is None or not self.chosen_mode_numbers:
            if self.fuse and self.spell.card.card_faces:
                # CR 702.102b/709.4b: a fused spell's characteristics are
                # both halves combined, so it may need targets for *both* -
                # Wear // Tear fused needs one artifact and one enchantment,
                # not just Wear's own. `understood` is the conjunction: a
                # spell this cannot fully read for *either* half is not one
                # CR 601.2c can safely check announced targets against.
                left, right = self.spell.card.card_faces[0], self.spell.card.card_faces[1]
                left_profile = profile_for_text(left.oracle_text or "")
                right_profile = profile_for_text(right.oracle_text or "")
                combined = TargetingProfile(
                    requirements=(*left_profile.requirements, *right_profile.requirements),
                    understood=left_profile.understood and right_profile.understood,
                )
                return self._with_bestowed_target(combined)
            if self.face is not None:
                face = self.chosen_face
                if face is not None:
                    return self._with_bestowed_target(
                        face_spell_profile(
                            face, substitute_x(face.oracle_text or "", self.x_value or None)
                        )
                    )
            if self.spell.prepare_spell_face:
                # CR 722.3c again: `self.spell.oracle_text` already reads
                # `CardState.up_face` - the prepare spell's own text, Seed
                # Suture's "Put a +1/+1 counter on target creature" rather
                # than Emergency Phytomedic's targetless "This creature
                # enters prepared" the plain `targeting_profile(self.spell.
                # card)` fallback below would read instead.
                return self._with_bestowed_target(
                    profile_for_text(substitute_x(self.spell.oracle_text, self.x_value or None))
                )
            if (self.keyword_used or "").lower() == "cleave":
                # CR 702.148a: a spell cast for its cleave cost has the bracketed
                # words removed, so "target [Human] creature" is any creature.
                return self._with_bestowed_target(
                    spell_profile_for_text(
                        cleaved_text(substitute_x(self.spell.oracle_text, self.x_value or None)),
                        self.spell.card,
                    )
                )
            per_kick = per_kick_target_text(self.spell.oracle_text or "", self.kicked)
            if per_kick is not None:
                # CR 601.2c: the kicker is paid first (CR 601.2b), so how many
                # targets the spell takes is known - one, and one more for each
                # time it was kicked (Comet Storm).
                if "{X}" in (self.spell.mana_cost or ""):
                    per_kick = substitute_x(per_kick, self.x_value)
                return self._with_bestowed_target(spell_profile_for_text(per_kick, self.spell.card))
            # `self.modal is None` matters as much as the `{X}`: a MODAL card
            # with an X in its cost (Kozilek's Command, `{X}{C}{C}`) reaches
            # here whenever its modes have not been announced yet, and reading
            # its text whole would count the targets of every bullet - three,
            # for a card that will only ever need the targets of the two modes
            # actually chosen (CR 700.2c). CR 601.2c enforcement downstream
            # then refuses the cast for "too few targets" before the caster is
            # ever asked which modes they want. Modal stays `understood=False`
            # until `choose_modes` runs, which is what the fallthrough gives.
            if self.modal is None and (
                "{X}" in (self.spell.mana_cost or "")
                # CR 107.3a: an X announced through an additional cost
                # ("discard X cards", Nahiri's Wrath) bounds "up to X
                # targets" exactly as a `{X}` in the mana cost does.
                or any(
                    cost_announces_x(phrase)
                    for phrase in additional_cost_phrases(self.spell.card, face=self.face)
                )
            ):
                # Spell-scoped, not `profile_for_text`: that one reads text
                # whole because it exists for an ability's own words, and a
                # creature spell with an activated ability that targets
                # (Walking Ballista's "It deals 1 damage to any target") would
                # otherwise look like a spell requiring a target (CR 113.1c).
                return self._with_bestowed_target(
                    spell_profile_for_text(
                        substitute_x(self.spell.oracle_text, self.x_value), self.spell.card
                    )
                )
            kicked_alternative = kicked_instead_target_text(self.spell.oracle_text or "")
            if kicked_alternative is not None:
                # CR 601.2c: kicker (announced at CR 601.2b) decides which
                # targets are chosen - "If this spell was kicked, instead
                # choose ..." (The Eagles Are Coming!).
                return self._with_bestowed_target(
                    profile_for_text(kicked_alternative[1 if self.kicked else 0])
                )
            teamwork_alternative = teamwork_instead_target_text(self.spell.oracle_text or "")
            if teamwork_alternative is not None:
                # The identical CR 601.2c shape, for Teamwork's own
                # additional cost (Too Evil to Stay Dead's own "If this
                # spell was cast using teamwork, instead choose ...").
                return self._with_bestowed_target(
                    profile_for_text(teamwork_alternative[1 if self.teamwork_paid else 0])
                )
            if self.spell.transformed and self.spell.card.back_face is not None:
                # CR 712.11a/712.11c: cast transformed, only the back face's
                # own characteristics are evaluated - a Siege's own CR
                # 310.12b cast (`Game.cast_during_resolution(transformed=
                # True)`). `targeting_profile(Card)` is cached off `front_
                # oracle_text` alone and has no notion of a *runtime*
                # `CardState.transformed` flag to read instead, so a
                # back face with its own target requirement (Awaken the
                # Maelstrom's "target player"/"target permanent") was
                # always announced with zero targets, and both of its
                # targeted clauses silently resolved to nothing - the same
                # family of defect `targeting_profile`'s own docstring
                # already fixed for a transform/modal DFC's blank top-level
                # `oracle_text` field, one layer further in.
                back_face = self.spell.card.back_face
                return self._with_bestowed_target(
                    with_face_aura_target(back_face, profile_for_text(back_face.oracle_text or ""))
                )
            return self._with_bestowed_target(targeting_profile(self.spell.card))
        return self._with_bestowed_target(
            profile_for_modes(self.spell.card, self.chosen_mode_objects, self.x_value)
        )

    def _with_bestowed_target(self, profile: TargetingProfile) -> TargetingProfile:
        """CR 702.103b's target, which no printed line of the card carries.

        "As a spell cast bestowed is put onto the stack, it becomes an Aura
        enchantment and gains enchant creature." CR 303.4a then makes that
        enchant ability the spell's target - "an Aura spell requires a target,
        which is defined by its enchant ability" - so a creature spell that
        printed no target at all requires one the moment bestow is announced.

        `targeting_profile` reads the *printed* card, where the Phoenix is a
        plain Enchantment Creature with neither the Aura subtype nor an
        enchant keyword, so the enchant target it prepends for every other
        Aura is not reachable from there. This prepends it from the
        announcement instead, in the same position and for the same reason
        (`targeting._with_aura_target`): the enchant target comes first, and
        anything the card's own text targets follows it.
        """
        profile = with_keyword_spell_ability_target(profile, self.keyword_used)
        if not self.spell.bestowed:
            return profile
        enchant = profile_for_text("target creature")
        if not enchant.understood or not enchant.requirements:
            return profile
        return profile.model_copy(
            update={"requirements": (*enchant.requirements, *profile.requirements)}
        )

    # -- CR 601.2b: modes, alternative costs, additional costs -------------

    def choose_modes(
        self,
        modes: Sequence[int | str | Mode],
        x_value: int | None = None,
        entwined: bool = False,
    ) -> CastingStep:
        """CR 601.2b: announce the mode choice, before targets and before costs.

        CR 700.2a puts the choice here, as part of casting, and CR 700.2c makes
        it decide what the spell targets - so an announcement that is not legal
        has to be refused now: an unknown mode, a mode chosen twice where the
        card does not allow it (CR 700.2d), or the wrong number of modes.

        A mode may be named by its 1-based number, by its text, or by a `Mode`
        read off `self.modal`. A card that is not modal accepts only an empty
        list, since it has no modes to choose.

        `entwined` is CR 702.42a: "'Entwine [cost]' means "You may choose all
        modes of this spell instead of just the number specified. **If you do,
        you pay an additional [cost].**"" Both halves happen here - every mode is
        opened *and* the cost is charged as an additional cost (CR 118.8a), so
        an entwined spell cannot be announced without paying for it.

        `x_value` is the value the caster chose for X (CR 107.3a). It is
        accepted here because a mode can read "up to X target cards", and that
        cannot be counted at CR 601.2c without it. It is the same value
        `determine_cost` locks into the total cost.
        """
        self._enter_modes()
        modal = self.modal

        if modal is None:
            if modes:
                raise ValueError(f"{self.spell.name} is not a modal spell (CR 700.2)")
            self.chosen_modes = []
            self.chosen_mode_numbers = []
        elif not modal.understood:
            # The card is modal but its instruction could not be read. Record
            # what was asked for and check nothing, rather than reject a legal
            # choice on the strength of a failed parse.
            chosen = [modal.mode(spec) for spec in modes]
            self.chosen_modes = [mode.text for mode in chosen]
            self.chosen_mode_numbers = [mode.number for mode in chosen]
        else:
            chosen = list(
                modal.resolve(
                    modes, entwined=entwined, alternative=self._alternative_mode_count(modal)
                )
            )
            self.chosen_modes = [mode.text for mode in chosen]
            self.chosen_mode_numbers = [mode.number for mode in chosen]
            self._charge_mode_costs(chosen)

        if entwined and not self.entwined:
            self._charge_entwine(modal)
        self.entwined = entwined
        if x_value is not None:
            self.x_value = x_value
        return self.step

    def _alternative_mode_count(self, modal: ModalProfile) -> bool:
        """Whether `modal`'s "If ..., choose N instead" holds as this spell is
        cast (CR 601.2b), read by `Game.modal_alternative_applies`.

        "This spell was kicked" (Inscription of Abundance, CR 702.33d) is
        answered from `self.kicked` directly rather than through `Game.
        condition_holds`'s own reading of it: that reads the *finalized*
        `CastRecord`, which `cast()` only writes once announcement is
        complete, but CR 601.4's own worked example for this exact card is
        that the modal choice may look ahead to a kicker payment "normally
        made later in that rule's instructions" - `self.kicked` is exactly
        that still-in-progress count, live while modes are being chosen.
        """
        if self.game is None:
            return False
        override = None
        condition = (modal.alternative_condition or "").strip().rstrip(".").strip().lower()
        if condition == "this spell was kicked":
            override = self.kicked > 0
        elif condition == "this spell was cast using teamwork":
            # Same shape as kicker's own override just above: `self.
            # teamwork_paid` is this cast's still-in-progress flag, live
            # while modes are being chosen (CR 601.2b), not the finalized
            # `CastRecord` `Game.condition_holds` would otherwise read.
            override = self.teamwork_paid
        return self.game.modal_alternative_applies(
            modal,
            self.caster,
            self.spell.id,
            self.spell.name,
            self.spell,
            condition_override=override,
        )

    def _charge_entwine(self, modal: ModalProfile | None) -> None:
        """CR 702.42a: "If you do, you pay an additional [cost]."

        An *additional* cost (CR 118.8a), so the printed mana cost is still paid
        on top of it - the difference from an alternative cost, and the reason
        an entwined Tooth and Nail costs {7}{G}{G} rather than {2}.
        """
        if modal is None or modal.entwine_cost is None:
            raise ValueError(f"{self.spell.name} has no entwine cost (CR 702.42a)")
        cost = total_cost_for_phrase(modal.entwine_cost, self.caster)
        if cost is None:
            raise ValueError(
                f"{self.spell.name}'s entwine cost {modal.entwine_cost!r} could not be "
                f"read, so it cannot be paid"
            )
        self.additional_costs.append(cost.assign_payer(self.caster))

    def _charge_mode_costs(self, chosen: Sequence[Mode]) -> None:
        """CR 700.2h: a chosen mode's own printed cost is a mandatory
        additional cost, paid as the spell is cast (CR 601.2b, CR 601.2f-h) -
        unlike kicker or escalate, there is no separate "may pay" step: the
        cost is owed the instant the mode is chosen, so it is charged here,
        the same way `_charge_entwine` charges CR 702.42a's cost.
        """
        for mode in chosen:
            if mode.cost is None:
                continue
            cost = total_cost_for_phrase(mode.cost, self.caster)
            if cost is None:
                raise ValueError(
                    f"{self.spell.name}'s mode {mode.number} cost {mode.cost!r} could not "
                    f"be read, so it cannot be paid (CR 700.2h)"
                )
            self.add_additional_cost(cost)

    def choose_alternative_cost(self, cost: TotalCost | ManaCost | None) -> CastingStep:
        """CR 118.9: pay this instead of the spell's mana cost.

        Only one alternative cost may ever apply to a spell (CR 118.9a), so
        announcing a second one is an error rather than a second discount.
        Additional costs, increases, and reductions still apply on top of it
        (CR 118.9d).
        """
        if self.alternative_cost is not None:
            raise ValueError("only one alternative cost can be applied to a spell")
        self._enter_modes()
        total = cost if isinstance(cost, TotalCost) else TotalCost.of(cost)
        self.alternative_cost = total.assign_payer(self.caster)
        return self.step

    @property
    def cast_options(self) -> list[KeywordCastOption]:
        """The keyword options that would cast this spell out of its origin
        zone - the card's own, and any another permanent grants it right now
        (CR 610.5)."""
        return (
            castable_from(self.spell.card, self.origin_zone)
            # CR 701.65a's airbend and anything else whose permission is the
            # pile of exile itself, filtered to the zone this cast is coming
            # from the same way the printed options above are.
            + [
                option
                for option in marker_cast_options(self._as_announced)
                if option.zone is self.origin_zone
            ]
            + [granted.option for granted in self.granted_cast_options]
        )

    @property
    def granted_cast_options(self) -> list[GrantedCastOption]:
        """CR 610.5's grants, as they stand at this announcement."""
        return granted_cast_options(
            self.game,
            # As of the proposal (CR 601.3): the pile of exile the card sat in
            # and the zone it left are what a grant asks about, and CR 601.2a
            # has already moved the card itself.
            self._as_announced,
            self.caster,
            self.origin_zone,
            library_top=self.announced_library_top,
        )

    def splice(self, name: str) -> CastingStep:
        """CR 702.47a: reveal a card with splice from hand and add it to this spell.

        "Splice is a static ability that functions while a card is in your
        hand. 'Splice onto [quality] [cost]' means 'You may reveal this card
        from your hand as you cast a [quality] spell. If you do, add this
        card's rules text to that spell and pay its splice cost.'"

        Three things happen, in that order:

        - The card is **revealed** and stays in hand. Nothing moves it; CR
          701.20a's reveal is the whole of what happens to the card itself,
          and `spliced_card_ids` is the record.
        - Its splice cost becomes an **additional cost** of this spell, folded
          into `additional_costs` exactly as a printed "As an additional cost
          to cast this spell" sentence is. CR 601.2h then pays it with
          everything else.
        - Its rules text is **added to the spell**, after the spell's own (CR
          702.47c, CR 612.10). That is written onto the spell by `cast()`, so
          a casting reversed under CR 601.6/CR 733.1 leaves no text behind,
          and `CardState.move_to` takes it away again when the spell leaves
          the stack (CR 702.47e).

        Refused when the main spell is not of the quality the splice ability
        names, when the named card is not in the caster's hand, when it has no
        splice ability, when it has already been spliced onto this spell
        (CR 702.47b: "You can't splice any one card onto the same spell more
        than once"), and when its rules text would require choices this
        announcement cannot make - CR 702.47b's first sentence, "You can't
        choose to use a splice ability if you can't make the required choices
        (targets, etc.) for that card's rules text", read fail-closed: a
        spliced card that targets is refused rather than spliced on with its
        targets unannounced.
        """
        return self._refusing(lambda: self._splice(name))

    def splice_by_id(self, card_id: UUID) -> CastingStep:
        """CR 702.47a's splice, named by id rather than by name.

        The id-keyed twin of `splice(name)`, for a caller that has to name
        *which* copy of a card to reveal - `splice(name)`'s lookup takes
        whichever matching card happens to sit first in hand, which cannot
        distinguish two copies of the same splice card. This is what
        `Game.cast`'s `splice` parameter drives, matching `Action.
        splice_options`' own `SpliceOption.card_id`: this library's actions
        are ids only (see the module docstring), never names, and splice is
        no exception.

        Same three effects, same refusals, as `splice(name)` - see that
        docstring - except "not in the caster's hand" and "already spliced"
        are judged against the id, not the name.
        """
        return self._refusing(lambda: self._splice_by_id(card_id))

    def _splice(self, name: str) -> CastingStep:
        if self.game is None:
            raise ValueError("splicing needs a game to find the card in hand")
        hand = self.game.player(self.caster).hand
        candidates = [
            card for card in hand if card.name == name and card.id not in self.spliced_card_ids
        ]
        if not candidates:
            already = any(card.id in self.spliced_card_ids for card in hand if card.name == name)
            if already:
                # CR 702.47b's second sentence.
                raise ValueError(f"{name} is already spliced onto {self.spell.name}")
            raise ValueError(f"{self.caster} has no {name} in hand to splice")
        return self._splice_card(candidates[0])

    def _splice_by_id(self, card_id: UUID) -> CastingStep:
        if self.game is None:
            raise ValueError("splicing needs a game to find the card in hand")
        hand = self.game.player(self.caster).hand
        card = next((candidate for candidate in hand if candidate.id == card_id), None)
        if card is None:
            raise ValueError(f"{self.caster} has no card {card_id} in hand to splice")
        if card_id in self.spliced_card_ids:
            # CR 702.47b's second sentence.
            raise ValueError(f"{card.name} is already spliced onto {self.spell.name}")
        return self._splice_card(card)

    def _splice_card(self, card: CardState) -> CastingStep:
        name = card.name
        splice = _keyword(card.card, "Splice")
        if splice is None:
            raise ValueError(f"{name} has no splice ability")
        quality, cost = _splice_parameter(splice)
        if quality is None or cost is None:
            raise ValueError(f"{name}'s splice ability could not be read: {splice.parameter}")
        if not _matches_splice_quality(self.spell, quality):
            raise ValueError(f"{self.spell.name} is not {quality}, so {name} cannot splice onto it")
        text = _spliced_rules_text(card.card)
        if not text:
            raise ValueError(f"{name} has no rules text to splice onto {self.spell.name}")
        profile = profile_for_text(text)
        if profile.understood and profile.requirements:
            # CR 702.47b: the choices for the spliced card's own text cannot be
            # made here, so the splice is refused rather than announced half.
            raise ValueError(
                f"{name}'s rules text requires targets, which cannot be chosen for a "
                "spliced card yet (CR 702.47b)"
            )
        self.spliced_card_ids.append(card.id)
        self.spliced_text.append(text)
        self.additional_costs.append(TotalCost.of(cost).assign_payer(self.caster))
        self.payment = None  # the total cost has changed; re-determine it
        return self.step

    def use_keyword(self, keyword: str, *, choosing: list[CardState] | None = None) -> CastingStep:
        """CR 601.2b: announce that this spell is being cast using a keyword.

        This is the announcement, not the payment: it settles which zone the
        spell is coming from and what replaces its mana cost, and leaves the
        paying to `determine_cost`/`begin_paying` like any other cost.

        `choosing` fills in the objects a keyword cost needs - the black card
        evoke exiles, the Mountain Lava Dart's flashback sacrifices - because
        CR 601.2b is where those are chosen and CR 601.2h is where they are
        spent. They are handed to the cost's components in order.

        Raises when neither the card nor anybody's static ability offers the
        keyword, when the spell is in the wrong zone for it, when the exile
        pile is wrong, or when the timing is (CR 601.3). A keyword whose
        printed cost this engine could not read also raises rather than being
        quietly charged nothing.

        A keyword *granted* by another permanent (CR 610.5, Ashling, the
        Limitless's "Elemental permanent spells you cast from your hand gain
        evoke {4} as you cast them") is offered here alongside the card's own,
        because the two are the same announcement: CR 601.2b does not care
        where the keyword came from.
        """
        return self._refusing(lambda: self._use_keyword(keyword, choosing))

    def _use_keyword(
        self,
        keyword: str,
        choosing: list[CardState] | None,
        prefer: TotalCost | None = None,
    ) -> CastingStep:
        printed_options = keyword_cast_options(self.spell.card)
        marker_options = marker_cast_options(self._as_announced)
        granted_options = [granted.option for granted in self.granted_cast_options]
        options = [
            option
            for option in printed_options + marker_options + granted_options
            if option.keyword.lower() == keyword.lower()
        ]
        if not options:
            raise ValueError(f"{self.spell.name} has no {keyword} ability that casts it")

        with self._as_of_the_proposal():
            reasons = [
                option.why_not(self._as_announced, self.caster, self.game, origin=self.origin_zone)
                for option in options
            ]
        usable = [option for option, reason in zip(options, reasons, strict=True) if reason is None]
        if not usable:
            # A keyword can hand out more than one option - warp casts from hand
            # and from exile - so report the one that was actually being tried,
            # which is the option for the zone the card is in.
            for option, reason in zip(options, reasons, strict=True):
                if option.zone is self.origin_zone and reason is not None:
                    raise ValueError(reason)
            raise ValueError(next(reason for reason in reasons if reason is not None))

        # A once-each-turn grant is spent by using it, so an unlimited grant
        # for the same cast is the one to claim when both apply. `prefer` is
        # the cost of the one instance the caster named (`use_alternative_
        # cost` by index or source): a card with two sneak abilities, one
        # printed and one granted, may use either (Ninja Teen's ruling).
        option = min(
            usable,
            key=lambda candidate: (
                prefer is not None and candidate.cost != prefer,
                candidate.once_per_turn_key is not None,
            ),
        )
        self._enter_modes()
        self.keyword_used = option.keyword
        self.keyword_normal_face_only = option.normal_face_only
        self.keyword_face_only = option.face_only
        self.keyword_exiles_instead = option.exile_instead_of_graveyard
        self.keyword_enters_with_counters = option.enters_with_counters
        self.keyword_snow_any_color = option.snow_any_color
        self.keyword_once_per_turn_key = option.once_per_turn_key
        self.keyword_any_color = option.any_color
        self.keyword_any_type_mana = option.any_type_mana
        self.keyword_cost_paid = not option.pays_mana_cost
        self.keyword_pays_life_for_mana_value = option.pays_life_for_mana_value
        self.keyword_opens_window = option.timing is CastTiming.OWN_DECLARE_BLOCKERS
        self.keyword_answers_timing = (
            not option.casts_transformed and _keyword_option_answers_timing(option)
        )
        if option.casts_transformed:
            # CR 712.11a: disturb casts the card back face up (CR 702.146a).
            self.cast_transformed()
        if option.keyword.lower() == "bestow":
            # CR 702.103b: "As a spell cast bestowed is put onto the stack, it
            # becomes an Aura enchantment and gains enchant creature." CR 601.2a
            # has already put it there, so this is the moment - and it is the
            # object that changes, not the announcement, which is why the flag
            # lives on `CardState`. A refused announcement rewinds the card to
            # its origin zone, and `CardState.move_to` clears the flag on the
            # way (CR 400.7).
            self.spell.bestowed = True
        if option.keyword.lower() == "prototype":
            # CR 718.3b: the spell (and the permanent it becomes) has only the
            # alternative power, toughness and mana cost.
            self.spell.prototyped = True
        # CR 610.5's grant happens "at the time the player proposes the
        # casting", and CR 400.7b keeps it on the permanent the spell becomes.
        # Recorded on the object rather than left implicit in the grantor's
        # static ability, because by the time the keyword's battlefield half
        # matters the grantor may be in a graveyard - which is the whole point
        # of CR 400.7b, and of CR 611.3d's "lasts indefinitely unless some
        # other duration is stated".
        if option.granted_line is not None and (
            option.granted_line not in self.spell.granted_ability_texts
        ):
            self.spell.granted_ability_texts = (
                *self.spell.granted_ability_texts,
                option.granted_line,
            )

        if option.additional_cost is not None:
            # CR 601.2f: "by paying 3 life in addition to paying their other
            # costs" - an additional cost the permission itself charges.
            # "by removing three counters from among creatures you control"
            # takes its permanents from `choosing` (CR 601.2b), or by
            # `cost.fill_from_among`'s default when none are named.
            from ..cost import fill_from_among

            extra = option.additional_cost.model_copy(deep=True)
            named = list(choosing or [])
            for component in extra.components:
                if component.from_among:
                    fill_from_among(component, self.game, self.caster, named or None)
                elif component.required and not component.cards:
                    # "by discarding a card" / "by sacrificing a creature": the
                    # cards the caster names fill the components in printed
                    # order (CR 601.2b), the way an alternative cost's do.
                    component.cards = named[: component.required]
                    named = named[component.required :]
            self.add_additional_cost(extra)
        if option.pays_mana_cost:
            # Warp's second half: the card is cast from exile for its own mana
            # cost, so there is no alternative cost to announce (CR 702.185b).
            return self.step

        cost = option.cost.model_copy(deep=True) if option.cost is not None else TotalCost()
        if option.keyword.lower() == "dash" and option.cost is not None and self.game is not None:
            # "Dash costs you pay cost {2} less" (`machines/cost/abilities.py`).
            cost = TotalCost(
                mana=ability_cost_adjustment(
                    self.game,
                    self.caster,
                    self.spell,
                    cost.mana,
                    kind="dash",
                    from_zone=self.origin_zone,
                ),
                components=cost.components,
            )
        remaining = list(choosing or [])
        for component in cost.components:
            if component.required and not component.cards:
                component.cards = remaining[: component.required]
                remaining = remaining[component.required :]
        self.choose_alternative_cost(cost)
        if option.returns_unblocked_creature:
            self._note_returned_creature_defender(option)
        if option.returns_tapped_creature:
            self._check_returned_tapped_creature(option)
        if option.beam_me_up:
            self._check_beamed_up_creature(option)
        if option.emerge_quality is not None:
            self._reduce_by_emerged_permanent(option)
        return self.step

    def _check_beamed_up_creature(self, option: KeywordCastOption) -> None:
        """CR 702.196a/b: the creature chosen (CR 601.2b) to return for beam
        me up must be a creature the caster controls that can be beamed up -
        checked now, so a wrong choice is refused with its own reason."""
        assert self.alternative_cost is not None
        component = next(
            component
            for component in self.alternative_cost.components
            if component.kind is ComponentKind.RETURN_TO_HAND
        )
        if not component.cards:
            raise ValueError(
                f"{option.keyword} needs a creature {self.caster} controls chosen to return "
                f"to its owner's hand ({option.rule})"
            )
        chosen = component.cards[0]
        if chosen.zone is not Zone.BATTLEFIELD or not (
            self.game.characteristics_of(chosen).is_creature
        ):
            raise ValueError(
                f"{chosen.name} is not a creature on the battlefield, so it cannot be "
                f"returned for {option.keyword} ({option.rule})"
            )
        reason = component.why_not(self.game) or beam_refusal(
            self.game, chosen, option.unbeamable_ids
        )
        if reason is not None:
            raise ValueError(reason)

    def _check_returned_tapped_creature(self, option: KeywordCastOption) -> None:
        """CR 702.188a: the creature chosen (CR 601.2b) to return for
        web-slinging must be a tapped creature the caster controls - checked
        now, so a wrong choice is refused with its own reason."""
        assert self.alternative_cost is not None
        component = next(
            component
            for component in self.alternative_cost.components
            if component.kind is ComponentKind.RETURN_TO_HAND
        )
        if not component.cards:
            raise ValueError(
                f"{option.keyword} needs a tapped creature {self.caster} controls chosen to "
                f"return to its owner's hand ({option.rule})"
            )
        chosen = component.cards[0]
        is_creature = (
            self.game.characteristics_of(chosen).is_creature
            if self.game is not None and chosen.zone is Zone.BATTLEFIELD
            else chosen.is_creature
        )
        if chosen.zone is not Zone.BATTLEFIELD or not is_creature or not chosen.tapped:
            raise ValueError(
                f"{chosen.name} is not a tapped creature, so it cannot be returned for "
                f"{option.keyword} ({option.rule})"
            )
        reason = component.why_not(self.game)
        if reason is not None:
            raise ValueError(reason)
        self.returned_mana_value = int(self.game.characteristics_of(chosen).mana_value)

    def _reduce_by_emerged_permanent(self, option: KeywordCastOption) -> None:
        """CR 702.119a's second ability: the total cost is reduced by an
        amount of generic mana equal to the sacrificed permanent's mana value.

        CR 702.119c chooses the permanent now (CR 601.2b) and sacrifices it at
        CR 601.2h, so it is checked now as well - a permanent of the right
        quality (CR 702.119b), one the caster controls (CR 701.21a) - and
        refused with its own reason rather than at payment. The reduction is
        an ordinary CR 601.2f cost reduction: generic mana only, never below
        {0} (CR 118.7d).
        """
        assert self.alternative_cost is not None
        component = next(
            component
            for component in self.alternative_cost.components
            if component.kind is ComponentKind.SACRIFICE
        )
        quality = option.emerge_quality or "creature"
        if not component.cards:
            raise ValueError(
                f"{self.spell.name}'s {option.keyword} cost needs "
                f"{with_indefinite_article(quality)} {self.caster} controls chosen to "
                f"sacrifice ({option.rule}, CR 702.119c)"
            )
        chosen = component.cards[0]
        if chosen.zone is not Zone.BATTLEFIELD:
            raise ValueError(
                f"{chosen.name} is not a permanent, so it cannot be sacrificed (CR 701.21a)"
            )
        controller = (
            self.game.controller_of(chosen).username if self.game is not None else chosen.controller
        )
        if controller != self.caster:
            raise ValueError(
                f"{self.caster} does not control {chosen.name}, so cannot sacrifice it (CR 701.21a)"
            )
        requirement = component.requirement
        mismatch = (
            requirement.why_not(chosen, self.game, self.caster) if requirement is not None else None
        )
        if mismatch is not None:
            raise ValueError(
                f"{chosen.name} is not {with_indefinite_article(quality)} to sacrifice for "
                f"{self.spell.name}'s {option.keyword} cost ({option.rule}): {mismatch}"
            )
        mana_value = int(
            self.game.characteristics_of(chosen).mana_value
            if self.game is not None
            else chosen.mana_value
        )
        if mana_value > 0:
            self.reduce_cost(ManaCost(generic=mana_value))

    def _note_returned_creature_defender(self, option: KeywordCastOption) -> None:
        """CR 702.190a/b: check the creature chosen to return, and remember
        what it is attacking before paying the cost takes it out of combat.

        CR 601.2b is where the chosen object is named and CR 601.2h where it
        is returned; the defender has to be read between the two, which is
        here. The creature is checked now as well so a wrong choice is refused
        with its own reason rather than at payment.
        """
        assert self.alternative_cost is not None
        component = next(
            component
            for component in self.alternative_cost.components
            if component.kind is ComponentKind.RETURN_TO_HAND
        )
        if not component.cards:
            raise ValueError(
                f"{option.keyword} needs an unblocked creature {self.caster} controls chosen "
                f"to return to its owner's hand ({option.rule})"
            )
        reason = component.why_not(self.game)
        if reason is not None:
            raise ValueError(reason)
        attack = self.game.combat.attack_by(component.cards[0].id)
        self.returned_creature_defender = attack.defender

    def use_triggered_alternative_cost(self, keyword: str, cost: TotalCost) -> CastingStep:
        """CR 601.2b: announce the alternative cost a resolving triggered
        ability offers - miracle's "you may cast it by paying [cost] rather
        than its mana cost" (CR 702.94a).

        Not `use_keyword`: that is for a keyword whose *static* ability lets
        the card be cast whenever its timing allows, and miracle offers its
        cost only while its own trigger resolves (CR 608.2g) - there is no
        `KeywordCastOption` for it to find, on purpose, so the cost is never on
        offer at priority. The trigger hands the cost in; this records it the
        way `use_keyword` records a keyword's (`keyword_used`,
        `keyword_cost_paid`) and announces it through `choose_alternative_cost`
        (CR 118.9, one alternative cost only - CR 118.9a).
        """
        return self._refusing(lambda: self._use_triggered_alternative_cost(keyword, cost))

    def _use_triggered_alternative_cost(self, keyword: str, cost: TotalCost) -> CastingStep:
        self.choose_alternative_cost(cost.model_copy(deep=True))
        self.keyword_used = keyword
        self.keyword_cost_paid = True
        return self.step

    def use_permission(self) -> CastingStep:
        """CR 601.2b: announce that this spell is being cast under a
        `PlayPermission` some effect handed out (CR 601.3).

        The twin of `use_keyword` for the dynamic half of CR 601.3: it settles
        that the permission is what allows this cast, and - when the permission
        says "without paying its mana cost" - announces the empty alternative
        cost that replaces the printed one (CR 118.9, CR 107.3b).

        Raises when no live permission covers this player, this object and this
        zone, carrying the permission's own reason: the wrong player, a card
        that has moved since (CR 400.7), a turn that has ended (CR 514.2), or a
        permission that says *play* against a card being cast.
        """
        return self._refusing(self._use_permission)

    def _use_permission(self) -> CastingStep:
        announced = self._as_announced
        permission = usable_play_permission(self.game, announced, self.caster)
        if permission is None:
            granted = play_permissions_on(self.game, announced)
            if granted:
                raise ValueError(granted[0].why_not(announced, self.caster, self.game))
            raise ValueError(
                f"nothing allows {self.caster} to cast {self.spell.name} from the "
                f"{self.origin_zone.value} (CR 601.3)"
            )
        self._enter_modes()
        self.permission_used = permission
        if not permission.pays_mana_cost:
            # CR 118.9's alternative cost, with nothing in it - "without paying
            # its mana cost" is not a discount on the printed cost (CR 118.9c),
            # it is a different thing paid in its place, and CR 107.3b keeps
            # "no cost at all" distinct from "some other cost".
            self.choose_alternative_cost(TotalCost())
        return self.step

    def _claim_zone_permission_if_unannounced(self) -> None:
        """CR 601.2b's announcement, made at CR 601.2f for a caller that never
        made it, when a `PlayPermission` is the only thing allowing this cast.

        `_refuse_unless_allowed_from_its_zone` already lets such a cast
        through: a live permission **is** CR 601.3's "a rule or effect allows
        that player to cast it" the moment a resolving effect hands it out, so
        unlike a keyword there is nothing further for CR 601.2b to name. That
        leniency was one-sided, and the asymmetry was the defect (owner's
        report, Ugin, Eye of the Storms' −11): the cast was legal under the
        permission and *priced* without it, because `total_cost` reads
        `alternative_cost`, which only `use_permission` ever set. Anything
        driving `Casting` by hand - as opposed to `Game.cast` and
        `magic_cards_model_api.engine_api.cast_card`, which both read
        `play_permission_for` before CR 601.2a's move and call
        `use_permission()` - paid the printed mana cost for a spell the
        granting effect said costs nothing.

        CR 118.9b is what makes claiming it for the caster right rather than
        presumptuous: "Alternative costs are generally optional. An effect
        that allows you to cast a spell may require a certain alternative cost
        to be paid." Ugin's −11 allows the cast only "without paying their
        mana costs", so paying the printed cost instead was never one of the
        options that ability granted - declining the waiver would leave
        nothing permitting the cast at all. That is also exactly where this
        stops: Omniscience's CR 604.2 static grant (`static_free_cast_grant`)
        is an ordinary optional alternative cost, because casting from your
        hand is already legal without it, so it is left to
        `use_alternative_cost` and this returns at the `Zone.HAND` guard.

        Nothing else about the cost is touched. CR 118.9d: "If an alternative
        cost is being paid to cast a spell, any additional costs, cost
        increases, and cost reductions that affect that spell are applied to
        that alternative cost" - `total_cost` applies all three to whatever
        `base` is, so a tax and a printed "as an additional cost" sentence are
        owed on a free cast exactly as they are on a paid one.

        A permission whose `pays_mana_cost` is true (Ragavan's "you may cast
        that card", warp's own second half) announces nothing at all here
        beyond `permission_used`: the printed mana cost is the right cost, and
        CR 118.9 never entered into it.

        The step machine is deliberately not rewound to CR 601.2b for this.
        `use_permission` goes through `_enter_modes`, which refuses once
        targets have been announced (CR 601.2c) - the ordinary order for a
        caller that reaches CR 601.2f at all - so the two fields are set
        directly. CR 118.9a's "only one alternative cost" is upheld by the
        guards above rather than by `choose_alternative_cost`: this runs only
        when no keyword, permission or alternative cost was announced.
        """
        if self.origin_zone is Zone.HAND:
            return
        if self.keyword_used is not None or self.permission_used is not None:
            return
        if self.alternative_cost is not None:
            return
        permission = usable_play_permission(self.game, self._as_announced, self.caster)
        if permission is None:
            return
        self.permission_used = permission
        if not permission.pays_mana_cost:
            # CR 118.9 / CR 107.3b: an alternative cost with nothing in it,
            # which is not the same object as a cost of {0}.
            self.alternative_cost = TotalCost().assign_payer(self.caster)

    def use_pitch_cost(
        self, *, x_value: int | None = None, choosing: list[CardState] | None = None
    ) -> CastingStep:
        """CR 118.9's alternative cost, read straight off the card's own
        printed text rather than a named keyword - Force of Will's "You may
        pay 1 life and exile a blue card from your hand rather than pay this
        spell's mana cost." `_option_from_keyword` never sees this: nothing
        here names a keyword ability the way Evoke or Flashback does.

        Mirrors `use_keyword`: which card(s) pay a component (the blue card
        exiled, here) is chosen now (CR 601.2b), and paying happens later
        through the ordinary `CostPayment` path once `begin_paying` opens.

        `x_value` announces the X in an X-keyed pitch cost - Disrupting
        Shoal's "You may exile a blue card with mana value X from your hand
        rather than pay this spell's mana cost." CR 107.3a: "If a spell ... has
        a mana cost, alternative cost, additional cost, and/or activation cost
        with an {X}, [-X], or X in it, and the value of X isn't defined by the
        text of that spell ..., the value ... is chosen" as it is cast
        (CR 601.2b). It is recorded on the casting like any other announced X,
        so the *same* value reaches the spell's other clause - CR 107.3i: "all
        instances of X on an object have the same value at any given time" -
        and it is substituted into the printed phrase before that phrase is
        read into a payable cost.

        Raises when the card prints no such offer, when its printed cost
        could not be read, or - Force of Negation's and Force of Vigor's own
        gate - when it is only offered "if it's not your turn" and it is.
        """
        return self._refusing(lambda: self._use_pitch_cost(x_value, choosing))

    def _use_pitch_cost(self, x_value: int | None, choosing: list[CardState] | None) -> CastingStep:
        if x_value is not None:
            self.x_value = x_value
        printed = [
            option
            for option in self.alternative_costs
            if option.source is AlternativeCostSource.PRINTED
        ]
        if not printed:
            raise ValueError(f"{self.spell.name} has no inline alternative cost to pay (CR 118.9)")
        return self._announce_alternative(printed[0], choosing)

    # -- CR 118.9: finding an alternative cost, and announcing it ----------

    @property
    def alternative_costs(self) -> list[AlternativeCostOption]:
        """Every CR 118.9 alternative cost that could apply to this spell, in
        a single list, whether or not it can be announced right now.

        CR 118.9: "An alternative cost is a cost listed in a spell's text, or
        applied to it from another effect, that its controller may pay rather
        than paying the spell's mana cost." All four of this engine's origins
        are gathered here - the spell's own printed offer (CR 604.6), a
        keyword that replaces the mana cost, a `PlayPermission` granted
        "without paying its mana cost", and another permanent's static
        ability (Omniscience) - because a seat driving the engine has no other
        way to *discover* that an alternative cost exists. Announcing one is
        `use_alternative_cost`.

        Only one of these may ever actually be paid (CR 118.9a); listing them
        all is what makes that a choice rather than a guess.
        """
        options: list[AlternativeCostOption] = []

        for offer in alternative_cost_offers(self.spell.card):
            # CR 107.3a's X, announced at CR 601.2b, substituted before the
            # phrase is read: Disrupting Shoal's "exile a blue card with mana
            # value X from your hand" only names a payable cost once X has a
            # value. `machines/modes.substitute_x` is the same substitution a
            # mode's own text gets, so the two agree by construction.
            phrase = substitute_x(offer.phrase, self.x_value)
            cost = _printed_alternative_total_cost(phrase, payer=self.caster)
            unavailable: str | None = None
            if cost is None:
                unavailable = f"{self.spell.name}'s alternative cost {phrase!r} could not be read"
            elif offer.requires_not_your_turn and not self._is_not_my_turn():
                unavailable = (
                    f"{self.spell.name}'s alternative cost can only be paid on an opponent's turn"
                )
            elif self._as_announced.zone is not self.origin_zone:
                unavailable = (
                    f"{self.spell.name} is in the {self._as_announced.zone.value}, not the "
                    f"{self.origin_zone.value} it is being cast from (CR 604.6)"
                )
            options.append(
                AlternativeCostOption(
                    index=len(options),
                    source=AlternativeCostSource.PRINTED,
                    rule="CR 118.9",
                    source_name=self.spell.name,
                    description=phrase,
                    cost=cost,
                    requires=sum(component.required for component in cost.components)
                    if cost
                    else 0,
                    unavailable=unavailable,
                    treasure_only=offer.treasure_only,
                )
            )

        for conditional in conditional_alternative_cost_offers(self.spell.oracle_text or ""):
            cost = _printed_alternative_total_cost(conditional.phrase, payer=self.caster)
            unavailable = None
            if cost is None:
                unavailable = f"{self.spell.name}'s alternative cost could not be read"
            elif self._as_announced.zone is not self.origin_zone:
                unavailable = (
                    f"{self.spell.name} is in the {self._as_announced.zone.value}, not the "
                    f"{self.origin_zone.value} it is being cast from (CR 604.6)"
                )
            else:
                unavailable = self._condition_refusal(conditional.condition)
            options.append(
                AlternativeCostOption(
                    index=len(options),
                    source=AlternativeCostSource.PRINTED,
                    rule="CR 118.9",
                    source_name=self.spell.name,
                    description=f"{conditional.phrase} (if {conditional.condition})",
                    cost=cost,
                    requires=sum(component.required for component in cost.components)
                    if cost
                    else 0,
                    unavailable=unavailable,
                )
            )

        free_condition = conditional_free_cast_condition(self.spell.oracle_text or "")
        if free_condition is not None:
            options.append(
                AlternativeCostOption(
                    index=len(options),
                    source=AlternativeCostSource.PRINTED,
                    rule="CR 118.9",
                    source_name=self.spell.name,
                    description=f"nothing (if {free_condition})",
                    cost=None,
                    unavailable=conditional_free_cast_unavailable(
                        self.game,
                        self.caster,
                        self._as_announced,
                        self.origin_zone,
                        free_condition,
                    ),
                )
            )

        keyword_options: list[tuple[str, KeywordCastOption]] = [
            (self.spell.name, option)
            for option in keyword_cast_options(self.spell.card)
            + marker_cast_options(self._as_announced)
        ]
        # CR 610.5: a keyword another permanent grants as this spell is cast is
        # an alternative cost like any other, and the option carries the
        # *granting* card's name so a seat can see where it came from.
        keyword_options.extend(
            (granted.source_name, granted.option) for granted in self.granted_cast_options
        )
        for offering_card, keyword_option in keyword_options:
            if keyword_option.pays_mana_cost:
                # Warp's second half and flashback's from-graveyard permission
                # that still charges a cost are CR 601.3 permissions, not
                # CR 118.9 alternative costs - only the ones that *replace*
                # the mana cost belong in this listing.
                continue
            cost = keyword_option.cost
            options.append(
                AlternativeCostOption(
                    index=len(options),
                    source=AlternativeCostSource.KEYWORD,
                    rule=keyword_option.rule,
                    source_name=offering_card,
                    keyword=keyword_option.keyword,
                    description=str(cost) if cost is not None else "nothing",
                    cost=cost,
                    requires=sum(component.required for component in cost.components)
                    if cost
                    else 0,
                    unavailable=keyword_option.why_not(
                        self._as_announced, self.caster, self.game, origin=self.origin_zone
                    ),
                )
            )

        for permission in play_permissions_on(self.game, self._as_announced):
            if permission.pays_mana_cost:
                continue
            options.append(
                AlternativeCostOption(
                    index=len(options),
                    source=AlternativeCostSource.PERMISSION,
                    rule=permission.rule,
                    source_name=permission.source_name,
                    # CR 107.3b keeps "no cost at all" apart from a cost of
                    # {0}, so this says nothing rather than {0}.
                    description="nothing",
                    cost=None,
                    unavailable=permission.why_not(self._as_announced, self.caster, self.game),
                )
            )

        # "The next <quality> spell you cast this turn can be cast without
        # paying its mana cost" (World War Hulk) - `machines/next_spell.py`.
        next_spell_grants = getattr(self.game, "next_spell_free_cast_grants_for", None)
        for free_grant in next_spell_grants(self.spell, self.caster) if next_spell_grants else []:
            options.append(
                AlternativeCostOption(
                    index=len(options),
                    source=AlternativeCostSource.STATIC,
                    rule="CR 118.9",
                    source_name=free_grant.source_name,
                    description="nothing",
                    cost=None,
                )
            )

        for source_name, grant in self._static_free_cast_grants():
            options.append(
                static_grant_option(
                    len(options),
                    source_name,
                    grant,
                    self.game,
                    self.caster,
                    self._as_announced,
                    self.origin_zone,
                    self.caster,
                )
            )

        return options

    def _static_free_cast_grants(self) -> list[tuple[str, StaticFreeCastGrant]]:
        """Omniscience's shape: a permanent the caster controls whose static
        ability applies CR 118.9's alternative cost of nothing to their spells.

        Ported to `static_free_cast_grants` below so `Game.alternative_costs_for`
        can ask this same pure question before any `Casting` exists - it reads
        only `game.battlefield`/`caster`, nothing an in-flight announcement
        knows that a `(game, caster)` pair does not already say.
        """
        return static_free_cast_grants(self.game, self.caster)

    def _spell_is_type(self, type_word: str) -> bool:
        """Whether the spell has the card type a static grant names
        (CR 205.2b: a card with more than one type has all of them)."""
        return spell_has_type_word(self.spell.card, type_word)

    def use_alternative_cost(
        self,
        which: int | str | None = None,
        *,
        choosing: list[CardState] | None = None,
    ) -> CastingStep:
        """CR 601.2b: announce that this spell is being cast for an
        alternative cost, chosen out of `alternative_costs`.

        `which` is the option's `index`, or its `keyword`/`source_name` if
        naming it reads better. Passing nothing takes the only *available*
        option and refuses when there is more than one, because CR 118.9a
        allows exactly one alternative cost per spell and guessing which one a
        seat meant is the wrong kind of help.

        `choosing` fills the objects the cost needs - the blue card Force of
        Will exiles, the two Mountains Fireblast sacrifices - because CR 601.2b
        is where they are chosen and CR 601.2h is where they are actually
        spent.

        Raises with the option's own reason when it cannot be announced: the
        wrong turn, the wrong zone, a keyword's timing, an expired permission.
        """
        options = self.alternative_costs
        if not options:
            raise ValueError(
                f"nothing offers {self.caster} an alternative cost for {self.spell.name} (CR 118.9)"
            )

        if which is None:
            usable = [option for option in options if option.available]
            if not usable:
                raise ValueError(options[0].unavailable or "")
            if len(usable) > 1:
                names = ", ".join(f"{option.index}: {option.description}" for option in usable)
                raise ValueError(
                    f"{self.spell.name} has more than one alternative cost available and "
                    f"only one may be paid (CR 118.9a) - name it: {names}"
                )
            chosen = usable[0]
        elif isinstance(which, int):
            if which < 0 or which >= len(options):
                raise ValueError(
                    f"{self.spell.name} has {len(options)} alternative cost(s), "
                    f"so there is no option {which}"
                )
            chosen = options[which]
        else:
            wanted = which.lower()
            matches = [
                option
                for option in options
                if wanted in {(option.keyword or "").lower(), option.source_name.lower()}
            ]
            if not matches:
                raise ValueError(
                    f"{self.spell.name} has no alternative cost named {which!r} (CR 118.9)"
                )
            chosen = next((option for option in matches if option.available), matches[0])

        return self._announce_alternative(chosen, choosing)

    def _announce_alternative(
        self, option: AlternativeCostOption, choosing: list[CardState] | None
    ) -> CastingStep:
        """Settle one `AlternativeCostOption` onto this casting (CR 601.2b)."""
        if option.unavailable is not None:
            raise ValueError(option.unavailable)

        if option.source is AlternativeCostSource.KEYWORD and option.keyword is not None:
            keyword = option.keyword
            return self._refusing(lambda: self._use_keyword(keyword, choosing, prefer=option.cost))
        if option.source is AlternativeCostSource.PERMISSION:
            return self.use_permission()

        cost = option.cost.model_copy(deep=True) if option.cost is not None else TotalCost()
        self._enter_modes()
        if option.source is AlternativeCostSource.STATIC:
            self.free_cast_source = option.source_name
            if option.once_per_turn_key is not None:
                # "Once during each of your turns": recorded as used when the
                # spell becomes cast (`cast`), not before - a cast that is
                # reversed (CR 601.6) used nothing.
                self.keyword_once_per_turn_key = option.once_per_turn_key
        remaining = list(choosing or [])
        for component in cost.components:
            if component.required and not component.cards:
                component.cards = remaining[: component.required]
                remaining = remaining[component.required :]
        self.treasure_mana_only = option.treasure_only
        self.choose_alternative_cost(cost)
        return self.step

    def _condition_refusal(self, condition: str) -> str | None:
        """Why a conditional CR 118.9 offer's printed condition does not hold
        right now, or None if it does.

        Fails closed twice over: a condition this cannot read refuses the
        offer, and so does a condition it can read but that is not met. An
        alternative cost silently granted by unparsed text is the worst of the
        three outcomes - it makes a spell free for a reason nobody checked.
        """
        match = _OPPONENT_SPELL_COUNT_CONDITION.match(condition.strip())
        if match is None:
            return printed_condition_refusal(self.game, self.caster, self.spell, condition)
        needed = parse_count(match.group("count"), article=False)
        if needed is None:
            return (
                f"{self.spell.name}'s alternative cost asks for "
                f"{match.group('count')} spells, a number this engine cannot read"
            )
        if self.game is None:
            return f"{self.spell.name}'s alternative cost needs a game to count spells cast"
        cast_this_turn = getattr(self.game, "spells_cast_this_turn", {})
        # "An opponent" is one opponent, not the table between them: the
        # counts are kept per player and each is compared on its own.
        for player in getattr(self.game, "players", []):
            if player.username == self.caster:
                continue
            if len(cast_this_turn.get(player.username, [])) >= needed:
                return None
        return (
            f"{self.spell.name}'s alternative cost is offered only if an opponent has "
            f"cast {match.group('count')} or more spells this turn, and none has"
        )

    def _is_not_my_turn(self) -> bool:
        """Force of Negation's and Force of Vigor's own condition: whoever is
        casting is not the active player right now."""
        turn = getattr(self.game, "turn", None)
        if turn is None:
            return False
        return turn.active_player != self.caster

    def pay_escalate(self, *, choosing: list[CardState] | None = None) -> CastingStep:
        """CR 702.120a: pay the escalate cost for each mode beyond the first.

        Escalate is an *additional* cost, not an alternative one (CR 118.8a), so
        the printed mana cost is still paid on top of it - the difference from
        evoke, and the reason the two are not interchangeable.

        Collective Brutality prints its cost after an em dash,
        `Escalate—Discard a card.`, so `choosing` names the cards discarded, one
        set per extra mode. The modes have to be announced first, since the
        number of them is what the cost is multiplied by.
        """
        modal = self.modal
        if modal is None or modal.escalate_cost is None:
            raise ValueError(f"{self.spell.name} has no escalate cost (CR 702.120a)")
        if not self.chosen_mode_numbers:
            raise ValueError(
                f"{self.spell.name}'s modes have to be announced before escalate can be "
                f"paid for them (CR 601.2b, CR 702.120a)"
            )

        remaining = list(choosing or [])
        for _ in range(len(self.chosen_mode_numbers) - 1):
            cost = total_cost_for_phrase(modal.escalate_cost, self.caster)
            if cost is None:
                raise ValueError(
                    f"{self.spell.name}'s escalate cost {modal.escalate_cost!r} could not "
                    f"be read, so it cannot be paid"
                )
            for component in cost.components:
                if component.required and not component.cards:
                    component.cards = remaining[: component.required]
                    remaining = remaining[component.required :]
            self.add_additional_cost(cost)
        return self.step

    def pay_kicker(
        self,
        times: int = 1,
        *,
        choosing: list[CardState] | None = None,
        which: str | None = None,
    ) -> CastingStep:
        """CR 702.33a: pay this spell's kicker cost as an additional cost.

        "Kicker is a static ability that functions while the spell with kicker
        is on the stack. 'Kicker [cost]' means "You may pay an additional [cost]
        as you cast this spell."" It is an *additional* cost (CR 118.8a), so the
        printed mana cost is still paid on top - the difference from evoke.

        CR 702.33d: paying it is what makes the spell "kicked", which is the
        condition the card's other, linked ability reads (CR 702.33e, CR 607.2i).
        `kicked` records it, because nothing else on the casting could tell a
        kicked Burst Lightning from an unkicked one.

        CR 702.33c's multikicker may be paid more than once; `times` is that.
        A card with plain kicker refuses a second payment rather than charging
        for it.

        CR 702.33b's "Kicker [cost 1] and/or [cost 2]" is two kicker costs:
        `which` names the one being paid (as printed, "{2}{U}"), each at most
        once, and `kicker_costs_paid` records it for CR 702.33f's "if it was
        kicked with its [A] kicker". A spell with two kicker costs paid both
        has been kicked twice (CR 702.33d).
        """
        ability = _keyword(self.spell.card, "kicker") or _keyword(self.spell.card, "multikicker")
        if ability is None:
            raise ValueError(f"{self.spell.name} has no kicker ability (CR 702.33a)")
        if times < 1:
            raise ValueError("kicker is paid at least once or not at all")
        multi = ability.canonical.lower() == "multikicker"
        costs = kicker_costs(self.spell.card)
        if which is None:
            if len(costs) > 1:
                raise ValueError(
                    f"{self.spell.name} has {len(costs)} kicker costs ({' and '.join(costs)}); "
                    f"name the one being paid (CR 702.33b)"
                )
            chosen = costs[0] if costs else (ability.cost or "")
        else:
            chosen = next((cost for cost in costs if cost.lower() == which.lower()), "")
            if not chosen:
                raise ValueError(
                    f"{self.spell.name} has no kicker cost {which} (its kicker costs are "
                    f"{' and '.join(costs) or 'unreadable'}, CR 702.33b)"
                )
        if not multi and len(costs) > 1 and (times > 1 or chosen in self.kicker_costs_paid):
            raise ValueError(
                f"{self.spell.name}'s kicker cost {chosen} was already paid; each kicker "
                f"cost is paid at most once (CR 702.33a, CR 702.33b)"
            )
        if not multi and len(costs) <= 1 and (times > 1 or self.kicked):
            raise ValueError(
                f"{self.spell.name} has plain kicker, which can only be paid once "
                f"(CR 702.33a; multikicker is CR 702.33c)"
            )

        remaining = list(choosing or [])
        for _ in range(times):
            cost = total_cost_for_phrase(chosen, self.caster)
            if cost is None:
                raise ValueError(
                    f"{self.spell.name}'s kicker cost {chosen!r} could not be read, "
                    f"so it cannot be paid"
                )
            for component in cost.components:
                if component.required and not component.cards:
                    component.cards = remaining[: component.required]
                    remaining = remaining[component.required :]
            self.add_additional_cost(cost)
            self.kicked += 1
            self.kicker_costs_paid.append(chosen)
        return self.step

    def pay_bargain(self, permanent: CardState) -> CastingStep:
        """CR 702.166a: "'Bargain' means 'As an additional cost to cast this
        spell, you may sacrifice an artifact, enchantment, or token.'" -
        paying it makes the spell "bargained" (CR 702.166b), which its linked
        "if it was bargained" (CR 702.166c) reads off `CastRecord.bargained`.

        The permanent is chosen now (CR 601.2b) and sacrificed with the rest
        of the total cost at CR 601.2h; it is checked now as well - on the
        battlefield, controlled by the caster (CR 701.21a), and an artifact,
        an enchantment (on the computed board, CR 613.5) or a token (CR
        111.1) - so a wrong choice is refused with its own reason.
        """
        from ..cost import sacrifice_cost

        if _keyword(self.spell.card, "bargain") is None:
            raise ValueError(f"{self.spell.name} has no bargain ability (CR 702.166a)")
        if self.bargained:
            raise ValueError(f"{self.spell.name}'s bargain cost was already paid")
        if permanent.zone is not Zone.BATTLEFIELD:
            raise ValueError(
                f"{permanent.name} is not a permanent, so it cannot be sacrificed (CR 701.21a)"
            )
        controller = (
            self.game.controller_of(permanent).username
            if self.game is not None
            else permanent.controller
        )
        if controller != self.caster:
            raise ValueError(
                f"{self.caster} does not control {permanent.name}, so cannot sacrifice it "
                f"(CR 701.21a)"
            )
        types = (
            self.game.characteristics_of(permanent).types
            if self.game is not None
            else permanent.types
        )
        if not (permanent.token or Type.ARTIFACT in types or Type.ENCHANTMENT in types):
            raise ValueError(
                f"{permanent.name} is not an artifact, enchantment, or token, so it cannot "
                f"pay {self.spell.name}'s bargain cost (CR 702.166a)"
            )
        component = sacrifice_cost(permanent, payer=self.caster, description=BARGAIN_COST)
        self.add_additional_cost(TotalCost(components=[component]))
        self.bargained = True
        return self.step

    def granted_life_costs(self) -> list[GrantedLifeCost]:
        """The optional life costs the caster's permanents grant this spell
        and that are not yet announced (`machines/casting/granted_life_costs`)."""
        offered = granted_life_costs(self.game, self.spell, self.caster)
        for paid in self.granted_life_paid:
            if paid in offered:
                offered.remove(paid)
        return offered

    def pay_granted_life_cost(self, grant: GrantedLifeCost) -> CastingStep:
        """CR 118.8b / 601.2b: announce a granted optional "you may pay N
        life" additional cost, and with it the reduction "if you paid life
        this way" (CR 601.2f). The life is paid with the rest of the total
        cost at CR 601.2h and must be payable now (CR 119.4)."""
        if grant not in self.granted_life_costs():
            raise ValueError(
                f"{grant.source_name} grants {self.spell.name} no unpaid life cost (CR 118.8b)"
            )
        if self.game is not None and self.game.player(self.caster).life < grant.life:
            raise ValueError(
                f"{self.caster} cannot pay {grant.life} life with only "
                f"{self.game.player(self.caster).life} life (CR 119.4)"
            )
        self.add_additional_cost(
            TotalCost(
                components=[
                    pay_life_cost(
                        grant.life,
                        payer=self.caster,
                        description=f"pay {grant.life} life ({grant.source_name})",
                    )
                ]
            )
        )
        self.granted_life_paid.append(grant)
        self.colored_only_reductions.append(grant.color)
        return self.step

    def casualty_numbers(self) -> list[int]:
        """The N of every casualty instance this spell has as it is cast
        (CR 702.153a): printed, then granted ("Each instant and sorcery spell
        you cast has casualty 1.", `machines/spell_grants.py`)."""
        return casualty_numbers(
            self.game, self.spell, self.caster, self.origin_zone, self.casualty_x
        )

    def announce_casualty_x(self, value: int) -> CastingStep:
        """CR 107.3a: the caster of a spell with "Casualty X" chooses and
        announces X as part of casting it; while the spell is on the stack that
        X is its value (`x_value`, which the casualty copy's starting loyalty
        reads back off the cast record)."""
        if not casualty_x_instances(self.spell.card):
            raise ValueError(f"{self.spell.name} has no 'Casualty X' to announce (CR 702.153a)")
        if value < 0:
            raise ValueError("X cannot be negative (CR 107.1b)")
        self.casualty_x = value
        self.x_value = value
        return self.step

    def pay_casualty(self, creature: CardState) -> CastingStep:
        """CR 702.153a: "As an additional cost to cast this spell, you may
        sacrifice a creature with power N or greater."

        Each instance is paid separately (CR 702.153b), one creature each -
        the ruling: "You may sacrifice only one creature to pay a spell's
        casualty cost". The creature is chosen now (CR 601.2b) and sacrificed
        with the rest of the total cost at CR 601.2h, and it is checked now:
        a creature on the battlefield the caster controls (CR 701.21a) whose
        power (CR 613.5's computed board) meets the next unpaid instance's N.
        The instances are taken in order - the lowest N the creature meets
        first would change nothing, since every paid instance triggers the
        same one copy.
        """
        from ..cost import sacrifice_cost

        numbers = self.casualty_numbers()
        if not numbers:
            raise ValueError(f"{self.spell.name} has no casualty ability (CR 702.153a)")
        if self.casualty_paid >= len(numbers):
            raise ValueError(
                f"every casualty cost {self.spell.name} has was already paid - each instance "
                "is paid with one creature (CR 702.153b)"
            )
        if creature.zone is not Zone.BATTLEFIELD:
            raise ValueError(
                f"{creature.name} is not a permanent, so it cannot be sacrificed (CR 701.21a)"
            )
        controller = (
            self.game.controller_of(creature).username
            if self.game is not None
            else creature.controller
        )
        if controller != self.caster:
            raise ValueError(
                f"{self.caster} does not control {creature.name}, so cannot sacrifice it "
                "(CR 701.21a)"
            )
        chars = self.game.characteristics_of(creature) if self.game is not None else creature
        if not chars.is_creature:
            raise ValueError(f"{creature.name} is not a creature (CR 702.153a)")
        if any(
            component.cards and creature in component.cards
            for extra in self.additional_costs
            for component in extra.components
        ):
            raise ValueError(f"{creature.name} is already paying another cost of this spell")
        needed = numbers[self.casualty_paid]
        power = power_of(creature, self.game)
        if power < needed:
            raise ValueError(
                f"{creature.name} has power {power}, and {self.spell.name}'s casualty "
                f"{needed} needs a creature with power {needed} or greater (CR 702.153a)"
            )
        component = sacrifice_cost(
            creature, payer=self.caster, description=casualty_cost_phrase(needed)
        )
        self.add_additional_cost(TotalCost(components=[component]))
        self.casualty_paid += 1
        return self.step

    def conspire_count(self) -> int:
        """How many conspire instances this spell has as it is cast (CR
        702.78a): printed, then granted ("Each noncreature spell you cast
        has conspire.", `machines/spell_grants.py`)."""
        return conspire_count(self.game, self.spell, self.caster, self.origin_zone)

    def conspire_candidates(self) -> list[CardState]:
        """The untapped creatures the caster controls that share a colour
        with this spell - what CR 702.78a's cost may tap."""
        if self.game is None:
            return []
        spell_colors = set(self.spell.colors)
        board = self.game.computed_board()
        return [
            state
            for state in self.game.permanents_controlled_by(self.caster)
            if board.of(state).is_creature
            and not state.tapped
            and spell_colors & set(board.of(state).colors)
        ]

    def pay_conspire(self, creatures: list[CardState]) -> CastingStep:
        """CR 702.78a: "As an additional cost to cast this spell, you may tap
        two untapped creatures you control that each share a color with it."

        The two are chosen now (CR 601.2b) and tapped with the rest of the
        total cost at CR 601.2h. Each instance is paid with its own two
        creatures; a creature already paying another cost of this spell
        cannot pay this one too.
        """
        from ..cost import tap_cost

        if self.conspire_paid >= self.conspire_count():
            raise ValueError(f"{self.spell.name} has no unpaid conspire ability (CR 702.78a)")
        if len(creatures) != 2 or creatures[0] is creatures[1]:
            raise ValueError("conspire taps exactly two creatures (CR 702.78a)")
        spell_colors = set(self.spell.colors)
        for creature in creatures:
            if creature.zone is not Zone.BATTLEFIELD:
                raise ValueError(f"{creature.name} is not a permanent (CR 702.78a)")
            controller = (
                self.game.controller_of(creature).username
                if self.game is not None
                else creature.controller
            )
            if controller != self.caster:
                raise ValueError(f"{self.caster} does not control {creature.name} (CR 702.78a)")
            chars = self.game.characteristics_of(creature) if self.game is not None else creature
            if not chars.is_creature:
                raise ValueError(f"{creature.name} is not a creature (CR 702.78a)")
            if creature.tapped:
                raise ValueError(
                    f"{creature.name} is tapped, and conspire taps untapped creatures (CR 118.3)"
                )
            if not spell_colors & set(chars.colors):
                raise ValueError(
                    f"{creature.name} does not share a color with {self.spell.name} (CR 702.78a)"
                )
            if any(
                component.cards and creature in component.cards
                for extra in self.additional_costs
                for component in extra.components
            ):
                raise ValueError(f"{creature.name} is already paying another cost of this spell")
        component = tap_cost(*creatures, payer=self.caster, description=CONSPIRE_COST)
        self.add_additional_cost(TotalCost(components=[component]))
        self.conspire_paid += 1
        return self.step

    def _optional_sentence(self, pattern: re.Pattern[str], what: str, rule: str) -> str:
        """The cost of the card's own "As an additional cost to cast this
        spell, you may <cost>" sentence matching `pattern` (CR 118.8b)."""
        for phrase in additional_cost_phrases(self.spell.card, face=self.face):
            match = pattern.match(phrase)
            if match is not None:
                return match.group("cost")
        raise ValueError(f"{self.spell.name} has no optional {what} additional cost ({rule})")

    def collect_evidence(self, cards: Sequence[CardState] | None = None) -> CastingStep:
        """Pay a printed "you may collect evidence N" as the optional additional
        cost it is (CR 118.8b): CR 701.59a's "exile any number of cards from
        your graveyard with total mana value N or greater", checked and paid
        with the rest of the total cost at CR 601.2h. `cards` names the cards;
        left out, the payment picks them (`CostComponent._evidence_to_exile`).
        `evidence_collected` is what the linked "if evidence was collected"
        (CR 701.59c) reads."""
        if self.evidence_collected:
            raise ValueError(f"{self.spell.name}'s evidence was already collected")
        phrase = self._optional_sentence(
            _OPTIONAL_COLLECT_EVIDENCE, "collect evidence", "CR 701.59a"
        )
        component = cost_component_for_phrase(phrase, self.caster)
        if component is None:
            raise ValueError(f"{self.spell.name}'s {phrase!r} could not be read (CR 701.59a)")
        if cards:
            component.cards = list(cards)
        if self.game is not None:
            refusal = component.why_not(self.game)
            if refusal is not None:
                raise ValueError(refusal)
        self.add_additional_cost(TotalCost(components=[component]))
        self.evidence_collected = True
        return self.step

    def pay_waterbend(self) -> CastingStep:
        """Pay a printed "you may waterbend {N}" as the optional additional cost
        it is (CR 118.8b, CR 601.2b): CR 701.67a's "Pay [cost]", added to the
        total cost (CR 601.2f) as mana. The permission it carries - tap an
        untapped artifact or creature you control for each generic mana of
        it - is applied against the open payment
        (`machines/objects_as_costs.waterbend`), and CR 701.67b bounds it to
        this cost's own generic through `TotalCost.waterbend_generic`, which
        `total_cost` carries onto the payment. An X in the printed cost takes
        the X already announced (CR 107.3a)."""
        if self.waterbend_paid:
            raise ValueError(f"{self.spell.name}'s waterbend cost was already announced")
        phrase = self._optional_sentence(_OPTIONAL_WATERBEND, "waterbend", "CR 701.67a")
        if re.search(r"\{X\}", phrase, re.IGNORECASE):
            if self.x_value is None:
                raise ValueError(
                    f"{self.spell.name}'s {phrase!r} needs X announced first (CR 107.3a)"
                )
            phrase = substitute_x(phrase, self.x_value)
        cost = total_cost_for_phrase(phrase, self.caster)
        if cost is None or cost.waterbend_generic is None:
            raise ValueError(f"{self.spell.name}'s {phrase!r} could not be read (CR 701.67a)")
        self.add_additional_cost(cost)
        self.waterbend_paid = True
        return self.step

    def reveal_for_cost(self, card: CardState) -> CastingStep:
        """Pay a printed "you may reveal a <quality> card from your hand" as the
        optional additional cost it is (CR 118.8b, CR 701.20a) - Orator of
        Ojutai's "a Dragon card". The card must be in the caster's hand and
        have the quality; it is revealed at CR 601.2h and stays in hand.
        `revealed_for_cost` is what "if you revealed a Dragon card" reads."""
        if self.revealed_for_cost:
            raise ValueError(f"{self.spell.name}'s reveal cost was already paid")
        phrase = self._optional_sentence(_OPTIONAL_REVEAL, "reveal", "CR 701.20a")
        component = cost_component_for_phrase(phrase, self.caster)
        if component is None:
            raise ValueError(f"{self.spell.name}'s {phrase!r} could not be read (CR 701.20a)")
        component.cards = [card]
        component.required = 1
        component.source = self.spell.name
        if card.zone is not Zone.HAND or card.owner != self.caster:
            raise ValueError(
                f"{card.name} is not in {self.caster}'s hand, so it cannot be revealed"
            )
        if self.game is not None:
            refusal = component.why_not(self.game)
            if refusal is not None:
                raise ValueError(refusal)
        self.add_additional_cost(TotalCost(components=[component]))
        self.revealed_for_cost = True
        return self.step

    def behold_for_cost(self, card: CardState) -> CastingStep:
        """Pay a printed plain "you may behold a <quality>" as the optional
        additional cost it is (CR 118.8b, CR 701.4a) - Dispelling Exhale's
        own "a Dragon". `card` is the object beheld: a matching card in the
        caster's hand (revealed, CR 701.4a) or a matching permanent on the
        battlefield the caster controls, the same choice `_PHRASE_BEHOLD`'s
        own `ComponentKind.BEHOLD` component already checks. `beheld_for_cost`
        is what "if a Dragon was beheld" (`cast_record._beheld`) reads."""
        if self.beheld_for_cost:
            raise ValueError(f"{self.spell.name}'s behold cost was already paid")
        phrase = self._optional_sentence(_OPTIONAL_BEHOLD, "behold", "CR 701.4a")
        component = cost_component_for_phrase(phrase, self.caster)
        if component is None:
            raise ValueError(f"{self.spell.name}'s {phrase!r} could not be read (CR 701.4a)")
        component.cards = [card]
        component.required = 1
        component.source = self.spell.name
        if self.game is not None:
            refusal = component.why_not(self.game)
            if refusal is not None:
                raise ValueError(refusal)
        self.add_additional_cost(TotalCost(components=[component]))
        self.beheld_for_cost = True
        return self.step

    def exile_for_cost_reduction(self, cards: Sequence[CardState] = ()) -> CastingStep:
        """Pay a printed "you may exile any number of <quality> cards from your
        hand" as the optional additional cost it is (CR 118.8b), and apply the
        linked "This spell costs <amount> less to cast for each card exiled
        this way" reduction (CR 118.7a) - March of Wretched Sorrow's own.

        The exile twin of `sacrifice_for_cost_reduction`: `cards` is CR
        601.2b's one choice of everything exiled this way, an empty sequence
        is a legal answer (CR 107.1c), and the reduction is exactly
        `len(cards)` times the card's own generic amount, floored at the
        generic part of the cost by `reduce_cost`.
        """
        if self.exiled_for_cost_reduction:
            raise ValueError(f"{self.spell.name}'s exile cost was already paid")
        phrase = self._optional_sentence(
            _OPTIONAL_EXILE_ANY_NUMBER_FROM_HAND, "exile any number", "CR 118.8b"
        )
        chosen = list(cards)
        component = cost_component_for_phrase(phrase, self.caster)
        if component is None:
            raise ValueError(f"{self.spell.name}'s {phrase!r} could not be read (CR 118.8b)")
        component.cards = chosen
        component.required = len(chosen)
        component.source = self.spell.name
        if self.game is not None and chosen:
            refusal = component.why_not(self.game)
            if refusal is not None:
                raise ValueError(refusal)
        if chosen:
            per_card = per_object_exile_cost_reduction(self.spell.card, face=self.face)
            if per_card is None:
                raise ValueError(
                    f"{self.spell.name} prints no per-card cost reduction to apply (CR 118.7a)"
                )
            self.add_additional_cost(TotalCost(components=[component]))
            self.reduce_cost(ManaCost(generic=per_card.generic * len(chosen)))
        self.exiled_for_cost_reduction = len(chosen)
        return self.step

    def sacrifice_for_cost_reduction(self, cards: Sequence[CardState] = ()) -> CastingStep:
        """Pay a printed "you may sacrifice any number of <quality>" as the
        optional additional cost it is (CR 118.8b), and apply the linked
        "This spell costs <amount> less to cast for each <noun> sacrificed
        this way" reduction (CR 118.7a) - Rottenmouth Viper's own.

        `cards` is CR 601.2b's own choice, made once, of everything
        sacrificed this way; an empty sequence is a legal answer (CR 107.1c:
        "any number of" includes zero), which pays the cost for nothing and
        reduces nothing. Unlike `collect_evidence`'s threshold, every named
        card really is sacrificed (CR 601.2h), so the reduction is exactly
        `len(cards)` times the card's own per-object amount.
        """
        if self.sacrificed_for_cost_reduction:
            raise ValueError(f"{self.spell.name}'s sacrifice cost was already paid")
        phrase = self._optional_sentence(
            _OPTIONAL_SACRIFICE_ANY_NUMBER, "sacrifice any number", "CR 118.8b"
        )
        chosen = list(cards)
        component = cost_component_for_phrase(phrase, self.caster)
        if component is None:
            raise ValueError(f"{self.spell.name}'s {phrase!r} could not be read (CR 118.8b)")
        component.cards = chosen
        component.required = len(chosen)
        component.source = self.spell.name
        if self.game is not None and chosen:
            refusal = component.why_not(self.game)
            if refusal is not None:
                raise ValueError(refusal)
        if chosen:
            self.add_additional_cost(TotalCost(components=[component]))
        if chosen:
            per_object = per_object_sacrifice_cost_reduction(self.spell.card, face=self.face)
            if per_object is None:
                raise ValueError(
                    f"{self.spell.name} prints no per-object cost reduction to apply (CR 118.7a)"
                )
            self.reduce_cost(ManaCost(generic=per_object.generic * len(chosen)))
        self.sacrificed_for_cost_reduction = len(chosen)
        return self.step

    def behold_chosen_type_for_cost(
        self, creature_type: str, creatures: Sequence[CardState]
    ) -> CastingStep:
        """Pay a printed "you may choose a creature type and behold [N]
        creatures of that type" as the optional additional cost it is (CR
        118.8b, CR 701.4a) - Celestial Reunion's own.

        `creature_type` is CR 607.2d's own choice: recorded on the record
        this cast writes (`Game.cast_record(...).chosen_creature_type`) so
        the spell's own "the chosen type" reads the same answer back at
        resolution. `creatures` are beheld to pay it - checked the same way
        an ordinary printed "behold a [quality]" checks its own fixed
        quality (`CostComponent._why_not_behold`), just against a quality
        this cast is choosing rather than one the card prints.
        """
        if self.behold_chosen_type_paid:
            raise ValueError(f"{self.spell.name}'s behold-chosen-type cost was already paid")
        phrase = None
        for candidate in additional_cost_phrases(self.spell.card):
            if _OPTIONAL_BEHOLD_CHOSEN_TYPE.match(candidate):
                phrase = candidate
                break
        if phrase is None:
            raise ValueError(
                f"{self.spell.name} has no optional choose-a-creature-type-and-behold "
                "additional cost (CR 701.4a)"
            )
        match = _OPTIONAL_BEHOLD_CHOSEN_TYPE.match(phrase)
        assert match is not None
        count = parse_count(match.group("count"), article=False)
        if count is None:
            raise ValueError(
                f"{self.spell.name}'s behold count {match.group('count')!r} could not be read"
            )
        if len(creatures) != count:
            raise ValueError(
                f"{self.spell.name}'s additional cost needs {count} creature(s) beheld, "
                f"{len(creatures)} given"
            )
        component = behold_cost(*creatures, payer=self.caster, required=count, description=phrase)
        component.requirement = CardRequirement(
            types=[Type.CREATURE], subtypes=[creature_type], description=f"{creature_type} creature"
        )
        if self.game is not None:
            refusal = component.why_not(self.game)
            if refusal is not None:
                raise ValueError(refusal)
        self.add_additional_cost(TotalCost(components=[component]))
        self.behold_chosen_type_paid = True
        self.chosen_creature_type_for_cost = creature_type.lower()
        return self.step

    def pay_teamwork(self, creatures: Sequence[CardState]) -> CastingStep:
        """Pay this spell's Teamwork cost as an optional additional cost
        (CR 601.2b, CR 118.8a/b): tap any number of untapped creatures the
        caster controls with total power N or more, where N is the printed
        `Teamwork N` (see `machines/teamwork.py`'s own module docstring for
        why no single CR 702 number governs the keyword itself).

        `creatures` is the whole offer, chosen once - unlike multikicker or
        replicate there is no repeat count, because the cost is not "pay
        this again"; it is "however many creatures reach the threshold",
        settled by which creatures are named. `CastRecord.cast_using_
        teamwork` is what the card's own "if this spell was cast using
        teamwork" rider (`machines/triggers.intervening_if_holds`) and the
        "choose both instead"/"choose N instead" modal alternative
        (`Game.modal_alternative_applies`) both read afterwards.
        """
        ability = teamwork_ability(self.spell.card)
        if ability is None:
            raise ValueError(f"{self.spell.name} has no teamwork ability")
        if self.teamwork_paid:
            raise ValueError(f"{self.spell.name}'s teamwork cost was already paid")
        threshold = ability.count or 0
        chosen = list(creatures)
        refusal = teamwork_payment_refusal(self.game, self.caster, threshold, chosen)
        if refusal is not None:
            raise ValueError(f"{self.spell.name}'s teamwork cost cannot be paid: {refusal}")
        component = CostComponent(
            kind=ComponentKind.TAP,
            cards=chosen,
            required=len(chosen),
            minimum_total_power=threshold,
            payer=self.caster,
            description=f"{TEAMWORK_TAP} (Teamwork {threshold})",
        )
        self.additional_costs.append(TotalCost(components=[component]).assign_payer(self.caster))
        self.teamwork_paid = True
        return self.step

    def pay_replicate(
        self,
        times: int = 1,
        *,
        choosing: list[CardState] | None = None,
        which: str | None = None,
    ) -> CastingStep:
        """CR 702.56a: pay this spell's replicate cost as an additional cost,
        any number of times.

        "Replicate is a keyword that represents two abilities. The first is a
        static ability that functions while the spell with replicate is on
        the stack ... 'Replicate [cost]' means 'As an additional cost to cast
        this spell, you may pay [cost] any number of times' and 'When you
        cast this spell, if a replicate cost was paid for it, copy it for
        each time its replicate cost was paid. If the spell has any targets,
        you may choose new targets for any of the copies.'"

        Structurally `pay_kicker`'s own "multi" branch (CR 702.33c) with no
        plain-kicker restriction to enforce, since CR 702.56a's own "any
        number of times" is unconditional. The count this records is read
        back by `machines/triggers.intervening_if_holds`'s "a replicate cost
        was paid for it" clause and by `machines/keywords._replicate_effect`,
        the same way `kicked` is read by "if it was kicked".
        """
        costs = replicate_costs(self.game, self.spell, self.caster, self.origin_zone)
        if not costs:
            raise ValueError(f"{self.spell.name} has no replicate ability (CR 702.56a)")
        if which is not None and which not in costs:
            raise ValueError(f"{self.spell.name} has no replicate cost {which!r} (CR 702.56a)")
        replicate_cost = which if which is not None else costs[0]
        if times < 1:
            raise ValueError("replicate is paid at least once or not at all")

        remaining = list(choosing or [])
        for _ in range(times):
            cost = total_cost_for_phrase(replicate_cost, self.caster)
            if cost is None:
                raise ValueError(
                    f"{self.spell.name}'s replicate cost {replicate_cost!r} could not be read, "
                    f"so it cannot be paid"
                )
            for component in cost.components:
                if component.required and not component.cards:
                    component.cards = remaining[: component.required]
                    remaining = remaining[component.required :]
            self.add_additional_cost(cost)
            self.replicated += 1
        return self.step

    def pay_offspring(self) -> CastingStep:
        """CR 702.175a: pay this spell's offspring cost as an additional cost.

        "Offspring [cost]" means "You may pay an additional [cost] as you
        cast this spell" and "When this permanent enters, if its offspring
        cost was paid, create a token that's a copy of it, except it's
        1/1."" The first half is this method, an ordinary CR 118.8a
        additional cost exactly like kicker's own `pay_kicker` above; the
        second is `machines/keywords._offspring_ability`'s triggered-ability
        expansion, reached through `CastRecord.offspring_paid` the same way
        evoke's own intervening *if* reads `CastRecord.keyword`.

        CR 702.175b's "multiple instances of offspring" (each paid and
        triggering separately) is not modelled - no pool printing carries
        two - so this refuses a second payment rather than silently
        recharging the same cost.
        """
        ability = _keyword(self.spell.card, "offspring")
        if ability is None:
            raise ValueError(f"{self.spell.name} has no offspring ability (CR 702.175a)")
        if self.offspring_paid:
            raise ValueError(f"{self.spell.name}'s offspring cost was already paid")
        cost = total_cost_for_phrase(ability.cost or "", self.caster)
        if cost is None:
            raise ValueError(
                f"{self.spell.name}'s offspring cost {ability.cost!r} could not be read, "
                f"so it cannot be paid"
            )
        self.add_additional_cost(cost)
        self.offspring_paid = True
        return self.step

    def pay_extra_mana_for_counters(self, amount: int) -> CastingStep:
        """CR 118.8 / CR 601.2b: pay "any amount of mana" as an optional
        additional cost to cast this creature spell, so that it enters with
        that many additional +1/+1 counters (CR 614.1c) - Chorus of the
        Conclave.

        The amount is generic mana added to the total cost like any other
        additional cost; paying 0 is the same as not paying. Refused unless
        the spell is a creature spell and its caster controls a permanent
        that offers the cost.
        """
        from ..keyword_counters import controls_extra_mana_counters_offer

        if amount < 0:
            raise ValueError("an amount of mana cannot be negative")
        if Type.CREATURE not in self.spell.card.types:
            raise ValueError(
                f"{self.spell.name} is not a creature spell, so no permanent offers it the "
                f"additional cost 'pay any amount of mana' (CR 601.2b)"
            )
        if self.game is None or not controls_extra_mana_counters_offer(self.game, self.caster):
            raise ValueError(
                f"{self.caster} controls no permanent offering the additional cost 'pay any "
                f"amount of mana' to cast {self.spell.name} (CR 601.2b)"
            )
        if self.extra_mana_counters:
            raise ValueError("the additional cost 'pay any amount of mana' was already paid")
        if amount:
            self.add_additional_cost(ManaCost(generic=amount))
            self.extra_mana_counters = amount
        return self.step

    def pay_blight(self, creature: CardState) -> CastingStep:
        """CR 701.68a: put N -1/-1 counters on a creature you control, as
        this spell's optional additional cost.

        Printed inline ("As an additional cost to cast this spell, you may
        blight 1.") rather than as a keyword-cost line, so `_charge_printed_
        additional_costs` reads the sentence but - per CR 118.8b, matched by
        `_OPTIONAL_ADDITIONAL_COST` - never charges it on its own; this is
        the explicit opt-in, the same shape `pay_kicker`/`pay_offspring`
        already are for their own optional costs.

        `place_counters_cost` is CR 118.3's general put-a-counter-on-as-a-
        cost primitive (Devoted Druid's self-referential "-1/-1 counter:
        untap this creature" already uses it); CR 701.68a's own "a creature
        you control" is enforced the same way any other object cost is -
        `CostComponent._why_not_controlled` - once a real `creature` is
        passed in, rather than by the phrase parser, which only reads the
        self-referential "this creature" shape.
        """
        phrase = next(
            (p for p in additional_cost_phrases(self.spell.card) if _BLIGHT_PHRASE.match(p)),
            None,
        )
        if phrase is None:
            raise ValueError(f"{self.spell.name} has no blight cost (CR 701.68a)")
        if self.blight_paid:
            raise ValueError(f"{self.spell.name}'s blight cost was already paid")
        if not creature.is_creature:
            raise ValueError(f"{creature.name} is not a creature, so it cannot be blighted")
        match = _BLIGHT_PHRASE.match(phrase)
        assert match is not None
        amount = parse_amount(match.group("n"))
        if amount is None:
            raise ValueError(f"{self.spell.name}'s blight count {match.group('n')!r} is unread")
        component = place_counters_cost(
            creature,
            0 if isinstance(amount, VariableX) else amount,
            counter_kind=Counter.MINUS_ONE,
            payer=self.caster,
            description=phrase,
        )
        # CR 107.3a: "blight X" puts the X announced at CR 601.2f
        # (`_announce_blight_x`), not a number known yet.
        component.variable_count = isinstance(amount, VariableX)
        self.add_additional_cost(TotalCost(components=[component]))
        self.blight_paid = True
        return self.step

    def pay_gift(self, opponent: str) -> CastingStep:
        """CR 702.174a: "The first ability is always 'As an additional cost
        to cast this spell, you may choose an opponent.'"

        The whole cost is the choice itself - CR 118.8a's additional cost
        with no resource behind it at all, unlike kicker/offspring/blight,
        which is why this neither reads a keyword cost nor touches
        `additional_costs`: there is nothing for `CostPayment` to pay.
        `opponent` must actually be an opponent (CR 102.2) once a `game` is
        attached; a caller building a `Casting` with no `game` (a unit test)
        is trusted, the same way `crew_activation`'s own no-game path is.
        """
        ability = _keyword(self.spell.card, "gift")
        if ability is None:
            raise ValueError(f"{self.spell.name} has no gift ability (CR 702.174a)")
        if self.gift_promised:
            raise ValueError(f"{self.spell.name}'s gift was already promised")
        if self.game is not None and (
            opponent == self.caster
            or opponent not in (p.username for p in self.game.players_in_game)
        ):
            raise ValueError(f"{opponent} is not an opponent of {self.caster} (CR 102.2)")
        self.gift_promised = True
        self.gift_chosen_player = opponent
        return self.step

    def pay_harmonize(self, creature: CardState | None) -> CastingStep:
        """CR 702.180a's second ability, and CR 702.180b's own choice: "You
        choose which creature to tap as you choose to pay a spell's
        harmonize cost ... and then tap that creature as you pay the total
        cost."

        "Up to one" (CR 702.180a) is why `creature` may be `None` - reducing
        by nothing rather than refusing. The discount lands now, at CR 601.2f
        (`reduce_cost`, applied before `determine_cost` locks the total
        cost); the tap itself is deferred to `CostPayment.pay()` through an
        ordinary `tap_cost` component, exactly as CR 702.180b's own "and then
        tap" orders the two.

        Only callable once `use_keyword("harmonize")` has already announced
        the harmonize cast (`self.keyword_used`) - the discount is the
        keyword's *second* static ability and has no meaning against a plain
        cast of the same card.
        """
        if (self.keyword_used or "").lower() != "harmonize":
            granted = (
                usable_play_permission(self.game, self._as_announced, self.caster)
                if self.permission_used is None and self.game is not None
                else self.permission_used
            )
            if granted is None or not granted.harmonize:
                raise ValueError(
                    f"{self.spell.name} is not being cast using harmonize (CR 702.180a)"
                )
            if self.permission_used is None:
                self.use_permission()  # a granted harmonize is announced like any permission
        if creature is None:
            return self.step
        if not creature.is_creature or creature.tapped or creature.zone is not Zone.BATTLEFIELD:
            raise ValueError(f"{creature.name} is not an untapped creature")
        if self.game is not None and self.game.controller_of(creature).username != self.caster:
            raise ValueError(f"{creature.name} is not controlled by {self.caster}")
        amount = power_of(creature, self.game)
        if amount > 0:
            self.reduce_cost(ManaCost(generic=amount))
        self.add_additional_cost(TotalCost(components=[tap_cost(creature, payer=self.caster)]))
        return self.step

    def add_additional_cost(self, cost: TotalCost | ManaCost) -> CastingStep:
        """CR 118.8a: any number of additional costs may be applied to a spell.

        Kicker is the mana-only case; "as an additional cost to cast this
        spell, sacrifice a creature" is the other kind. Both land here.
        """
        self._enter_modes()
        total = cost if isinstance(cost, TotalCost) else TotalCost.of(cost)
        self.additional_costs.append(total.assign_payer(self.caster))
        return self.step

    def increase_cost(self, amount: ManaCost | str) -> CastingStep:
        """An effect that makes this spell cost more (CR 601.2f)."""
        self._enter_modes()
        self.cost_increases.append(_as_mana(amount))
        return self.step

    def reduce_cost(self, amount: ManaCost | str) -> CastingStep:
        """An effect that makes this spell cost less (CR 601.2f, 118.7)."""
        self._enter_modes()
        self.cost_reductions.append(_as_mana(amount))
        return self.step

    # -- CR 601.2c: targets ------------------------------------------------

    def _lock_cast_amount(self) -> int | None:
        """Fix, once, the count this spell's text defines "as you cast this
        spell" (see `locked_amount`)."""
        if self.locked_amount is None and self.game is not None:
            from ..effects.amounts import locked_amount_as_cast

            self.locked_amount = locked_amount_as_cast(
                self.game, self.spell.oracle_text or "", self.caster
            )
        return self.locked_amount

    def choose_targets(self, targets: Iterable[Any]) -> CastingStep:
        """CR 601.2c: announce a legal object or player for each target.

        Each entry may be a `TargetRef`, a `CardState` or its id, or a player
        or their username; `TargetRef.coerce` reads which was meant.

        An illegal choice raises: a target of the wrong kind, in a zone the
        spell cannot reach, controlled by the wrong player, or more targets
        than the spell takes. Announcing *fewer* targets than the spell
        requires is not rejected, which is a known gap - existing scenarios
        cast a targeted spell with no target chosen to prove the effect finds
        nothing. `self.targeting.min_targets` says what would be required.

        A card whose text the target parser cannot read is not checked at all,
        because refusing a target the parser merely failed to understand would
        be worse than not checking.

        A modal spell has to have its modes announced first (CR 601.2b, and
        CR 700.2c: which targets it needs follows from which modes were
        chosen), so reaching this step without them is an error rather than an
        unchecked cast.
        """
        modal = self.modal
        if modal is not None and modal.understood and not self.chosen_mode_numbers:
            raise ValueError(
                f"{self.spell.name} is modal: its modes must be announced before its "
                f"targets (CR 601.2b, CR 700.2c)"
            )

        self._lock_cast_amount()  # "as you cast this spell" counts, before any division
        chosen = list(targets)
        try:
            placement = self._check_targets(chosen)
        except ValueError:
            # CR 601.6: "If a player can't legally cast the spell, the game
            # returns to the moment before the casting was proposed" - which,
            # now that CR 601.2a has already moved the card to the stack, means
            # putting it back. Nothing else about the announcement is kept
            # either: the proposal is over, not merely amended.
            self.cancel()
            raise
        self._advance_to(CastingStep.TARGETS)
        self.targets = [TargetRef.coerce(target) for target in chosen]
        if placement is not None and len(placement) == len(self.targets):
            # CR 601.2c: remember which requirement each target filled, so
            # resolution can tell a spell's sources from its victim.
            self.targets = [
                ref.model_copy(update={"slot": slot})
                for ref, slot in zip(self.targets, placement, strict=True)
            ]
        if self.modal is not None and self.modal.understood and self.chosen_mode_numbers:
            # Only a modal spell's target *count* can depend on X (CR 700.2c's
            # "up to X target ..."), so only here does a later change to X
            # actually invalidate what was just announced - a non-modal X
            # spell (Prismatic Ending's mana-value comparison, Fireball's
            # damage total) is untouched by this and keeps announcing targets
            # and determining its cost in either order, as before.
            self.x_value_at_targets = self.x_value
        self._slice_targets_by_mode(chosen)
        return self.step

    def _check_targets(self, chosen: list[Any]) -> list[int | None] | None:
        """CR 601.2c's legality check on one announced set of targets.

        The game is handed over because some restrictions are not
        characteristics (CR 109.3) and cannot be read off the permanent -
        "target attacking creature" lives on `Game.combat` (CR 508.1k).

        CR 115.5 is checked here too - "A spell or ability on the stack is an
        illegal target for itself" - and it has to be, now that CR 601.2a puts
        the spell on the stack before its targets are chosen: without it, a
        Counterspell would find itself among the legal spells on the stack.
        """
        for target in chosen:
            if isinstance(target, CardState) and target.id == self.spell.id:
                raise ValueError(f"{self.spell.name} is an illegal target for itself (CR 115.5)")
            if isinstance(target, TargetRef) and target.card_id == self.spell.id:
                raise ValueError(f"{self.spell.name} is an illegal target for itself (CR 115.5)")
        # CR 702.11b/702.11d: hexproof is judged inside `check`, with this
        # spell as the source whose quality "hexproof from" asks about.
        try:
            placement = self.targeting.check(chosen, self.caster, game=self.game, source=self.spell)
        except ValueError as refusal:
            raise self._trigger_targets_not_cast_targets(chosen, refusal) from None
        for target in chosen:
            refusal = self._enchant_refusal(target)
            if refusal is not None:
                raise ValueError(refusal)
        return placement

    def _trigger_targets_not_cast_targets(
        self, chosen: list[Any], refusal: ValueError
    ) -> ValueError:
        """Turn a bare "too many targets" refusal into the real reason, when
        the real reason is that the "target" the caster is reading belongs to
        a triggered ability, not to this spell (CR 115.1a vs CR 115.1d).

        `self.targeting.check` above already raised because the spell's own
        profile takes zero targets (CR 601.2c: a spell with no targeting text
        requires none) and some were chosen anyway. That refusal is correct,
        but its "too many targets: N chosen where the spell takes at most 0"
        does not say *why* the card prints the word "target" if the spell
        itself does not use it - which is exactly what a caster who typed
        Ulamog, the Ceaseless Hunger's cast trigger's targets straight onto
        the cast, or Ravenous Chupacabra's ETB targets the same way, is
        missing. `targeting_trigger_text` reads the card's own triggered
        abilities (cast and ETB alike - CR 603.2/603.2g both put a trigger's
        targets on the same CR 603.3d footing) the way `Game.
        why_cannot_target_with_trigger` does, and names whichever one prints
        the word.

        Left untouched for every other case: a spell that genuinely takes
        targets and was given too many (`self.targeting.max_targets` is
        `None` or nonzero), a cast with no targets chosen at all (`chosen` is
        empty - there is no "target" to blame on a trigger), a card with no
        targeting trigger at all (`targeting_trigger_text` returns `None`),
        and any refusal that is not this "too many targets" one to begin with
        (CR 115.5 self-targeting, protection, shroud, hexproof, phased-out -
        none of those become "true" just because a targeting trigger exists).
        """
        if (
            not chosen
            or self.targeting.max_targets != 0
            or not str(refusal).startswith("too many targets:")
        ):
            return refusal
        trigger_text = targeting_trigger_text(self.spell.card)
        if trigger_text is None:
            return refusal
        return ValueError(
            f"{self.spell.name} as a spell takes no targets (CR 601.2c); "
            f'"target" is in its triggered ability "{trigger_text}", whose targets are '
            "chosen when that ability is put on the stack (CR 603.3d, 115.1d) - cast "
            "without targets and answer its choose_targets decision then"
        )

    def _slice_targets_by_mode(self, chosen: list[Any]) -> None:
        """CR 700.2f: bucket `chosen` by which chosen mode instance each entry
        belongs to, into `self.mode_target_slices` - the structural piece
        resolution needs to dispatch each mode against only its own targets.

        A non-modal spell, or a modal spell whose modes were never announced
        or whose profile this parser could not read, gets no slices at all;
        `machines/effects.py`'s per-mode dispatch treats a missing slice as
        "no targets known for this mode instance" rather than an error.
        """
        modal = self.modal
        if modal is None or not modal.understood or not self.chosen_mode_numbers:
            self.mode_target_slices = []
            return
        profile, owners = profile_for_modes_with_owners(
            self.spell.card, self.chosen_mode_objects, self.x_value
        )
        if not profile.understood:
            self.mode_target_slices = []
            return
        assignment = profile.assign_to_owners(owners, chosen, self.caster, game=self.game)
        self.mode_target_slices = [
            [TargetRef.coerce(target) for target in assignment.get(index, [])]
            for index in range(len(self.chosen_mode_numbers))
        ]

    def announce_division(self, shares: Iterable[int]) -> None:
        """CR 601.2d: announce how a divided effect is split among the
        targets already chosen - Electrolyze's 2 damage as 1 and 1 (or all 2
        on one target), Shatterskull Smashing's X (or twice X) split however
        the caster likes.

        Targets must already be announced (`choose_targets`): `shares` is one
        entry per entry of `self.targets`, in that same order, and CR 115.7f
        then keeps this fixed if a target is later changed. For a variable
        (X) division, `self.x_value` must already reflect CR 107.3a's
        announced X - `determine_cost` sets that - since the total to divide
        is not known before then; the doubling condition, if the card has
        one, is applied here from `TargetingProfile.division.
        doubled_if_x_at_least`.

        A card whose text carries no division at all raises, the same way
        `choose_targets` refuses an illegal target rather than silently doing
        nothing.
        """
        profile = self.targeting
        if profile.division is None:
            raise ValueError(f"{self.spell.name} does not divide anything to announce (CR 601.2d)")
        resolved_shares = [int(share) for share in shares]
        amount = profile.division.amount
        if amount is None:
            locked = self._lock_cast_amount()
            amount = self.x_value if locked is None else locked
            threshold = profile.division.doubled_if_x_at_least
            if threshold is not None and amount >= threshold:
                amount = 2 * amount
        profile.check_division(resolved_shares, self.targets, amount=amount)
        self.division = resolved_shares

    def _enchant_refusal(self, target: Any) -> str | None:
        """Why enchant stops this Aura spell targeting that, or None (CR 702.5a).

        "The enchant ability restricts what an Aura spell can target and what an
        Aura can enchant." An Aura spell targets what it will enchant (CR 303.4b),
        so the restriction has to be applied at announcement, not discovered on
        resolution.

        Only an Aura is asked, because enchant is written on Auras.
        """
        if "Aura" not in self.spell.card.subtypes:
            return None
        if not enchant_restrictions(self.spell.card):
            return None
        return why_cannot_enchant(self.spell, target, self.caster, self.game)

    def _hexproof_refusal(self, target: Any) -> str | None:
        """Why hexproof stops this spell targeting that, or None (CR 702.11).

        Delegates to `Game.hexproof_refusal`, the one hexproof vocabulary every
        targeting path shares - a spell's announcement, an activated or
        triggered ability's, and CR 608.2b's recheck - with this spell as the
        object whose quality CR 702.11d judges ("[quality] spells your
        opponents control"). `TargetingProfile.check` already calls the same
        method during `_check_targets`; this stays as the direct question for
        a caller holding a `Casting`. A `Casting` without a game cannot say who
        controls the target, so nothing is checked there.
        """
        if self.game is None:
            return None
        return self.game.hexproof_refusal(target, self.caster, self.spell)

    # -- CR 601.2f-h: the total cost, and paying it ------------------------

    @property
    def total_cost(self) -> TotalCost:
        """The whole thing that has to be paid, X included (CR 601.2f).

        Built from the printed cost, or from the alternative cost if one was
        announced, with every additional cost added and every increase and
        reduction applied.

        When a game is attached, board-wide static cost increases *and*
        decreases (Sphere of Resistance's "Spells cost {1} more to cast",
        Trinisphere's floor, the Medallion cycle's/Ral, Monsoon Mage's own
        color- or type-scoped discount) are folded in here too, via
        `Game.static_cost_modifiers_for` - this is the step every ordinary
        cast reaches (`begin_paying` -> `determine_cost` -> this property), so
        nothing extra has to be called for them to apply.

        The spell's **own** discount - Leyline Binding's domain sentence,
        Emrakul's card-type count, Mystical Dispute's "if it targets a blue
        spell", affinity - is folded in here as well, from
        `Game.cost_reduction_for`. It used to be reachable only through the
        opt-in `Game.determine_total_cost`, which no ordinary cast calls: a
        Leyline Binding with all five basic land types out was measured asking
        for `{5}{W}` through `begin_paying()` while `determine_total_cost`
        answered `{W}` on the same board. CR 601.2f makes no such distinction -
        "Some effects may increase or reduce the cost to pay" is one step of
        casting, and every effect that applies at it applies at it - so a
        reduction the game can compute is charged on every cast, exactly like
        the increases already were. CR 118.7a keeps a generic reduction off the
        coloured pips (the `{W}` survives), and CR 118.9d applies it to an
        alternative cost when one was announced, which is what
        `apply_modifications` does with whatever `base` is.

        `Game.determine_total_cost` still appends that same reduction to
        `cost_reductions` before locking the cost in, so one entry equal to the
        freshly computed self-reduction is dropped from the list before the
        arithmetic: CR 601.2f determines *the* total cost once, and a discount
        counted from both directions would be counted twice.

        Read live only until `determine_cost` runs. From then on
        `self_reduction` holds the value that was in force at CR 601.2f and
        this reads that instead, because CR 601.2f locks the total cost in:
        "If effects would change the total cost after this time, they have no
        effect." A graveyard that grows after the cost was determined is worth
        nothing to the spell already being paid for.
        """
        base = self.alternative_cost.mana if self.alternative_cost else self.base_cost
        # CR 118.8a's printed additional costs are part of the total cost
        # whether or not CR 601.2f has been reached yet, so a caller asking
        # what a Fling would cost before `determine_cost` is told about the
        # sacrifice too. `determine_cost` folds the very same objects into
        # `additional_costs` for good; until it does, they are built here and
        # thrown away, so reading this property changes nothing.
        extras = [
            *self.additional_costs,
            *([] if self.printed_additional_costs_charged else self._printed_additional_costs()),
        ]
        increases = [
            *self.cost_increases,
            # CR 107.3a: an {X} in an additional cost (Thieving Skydiver's
            # "Kicker {X}") is the X announced for the spell.
            *(extra.mana.with_x(self.x_value) for extra in extras),
            self._own_cost_increase_for_targets(),
            self._own_flash_surcharge(),
            *(
                [self.permission_used.cost_increase]
                if self.permission_used is not None and self.permission_used.cost_increase
                else []
            ),
        ]
        reductions = list(self.cost_reductions)
        floor: int | None = None
        if self.game is not None:
            board_increases, board_reductions, floor = self.game.static_cost_modifiers_for(
                self.spell,
                self.caster,
                origin_zone=self.origin_zone,
                targets=self.targets,
                casting=self,
            )
            increases = increases + board_increases
            reductions = reductions + board_reductions
            # CR 702.41a via CR 604.2: affinity another permanent grants this
            # spell ("Instant and sorcery spells you cast have affinity for
            # creatures.", `machines/spell_grants.py`), one reduction per
            # granted instance - applied at CR 601.2f like a printed one.
            reductions = reductions + granted_affinity_reductions(
                self.game, self.spell, self.caster, self.origin_zone
            )
        for color in self.colored_only_reductions:
            # CR 118.7a: "reduces only the amount of <colour> mana you pay" -
            # nothing to take off when the cost has no such symbol, so the
            # reduction never spills into generic (CR 118.7b).
            symbol = ManaCost.parse(f"{{{color.value}}}")
            taken = sum(reduction.colored.get(color, 0) for reduction in reductions)
            if base.with_x(self.x_value).colored.get(color, 0) > taken:
                reductions.append(symbol)
        own = self.self_reduction if self.self_reduction is not None else self._own_cost_reduction()
        if own.symbols:
            if own in reductions:
                reductions.remove(own)
            reductions = reductions + [own]
        mana = apply_modifications(base.with_x(self.x_value), increases, reductions, floor=floor)

        components = list(self.alternative_cost.components) if self.alternative_cost else []
        if self.keyword_pays_life_for_mana_value or (
            self.permission_used is not None and self.permission_used.pays_life_for_mana_value
        ):
            # CR 118.9b's required alternative cost: life equal to the spell's
            # mana value as it will be on the stack (CR 202.3e: X counts).
            components.append(
                pay_life_cost(
                    self.base_cost.with_x(self.x_value).converted,
                    payer=self.caster,
                    description="pay life equal to its mana value",
                )
            )
        for extra in extras:
            components.extend(extra.components)
        if self.game is not None:
            # CR 118.8: a life cost another permanent's static ability adds to
            # the spell (Terror of the Peaks), keyed on the announced targets.
            for life, source_name in self.game.static_life_costs_for(
                self.spell, self.caster, self.targets
            ):
                components.append(
                    pay_life_cost(
                        life,
                        payer=self.caster,
                        description=f"pay {life} life ({source_name})",
                    )
                )
        # CR 701.67b: the tap method reaches only the waterbend cost's own
        # generic, summed over every waterbend cost among the additional ones
        # (`pay_waterbend`) - never the rest of the total cost's generic.
        bounds = [
            extra.waterbend_generic for extra in extras if extra.waterbend_generic is not None
        ]
        return TotalCost(
            mana=mana, components=components, waterbend_generic=sum(bounds) if bounds else None
        )

    def _own_cost_increase_for_targets(self) -> ManaCost:
        """ "This spell costs [N] more to cast for each target beyond the
        first." (CR 601.2f), Fireball's own printed shape - and, unnamed by
        the card that first printed it but the same sentence word for word,
        Launch the Fleet's "Strive — This spell costs {1} more to cast for
        each target beyond the first." CR 207.2c: an ability word "has no
        special rules meaning and no individual entries in the Comprehensive
        Rules" - "strive" is one (CR 207.2c's own list), so the em-dash
        prefix changes nothing about what the sentence after it means, and
        the two cards' identical clauses are the same mechanic rather than
        two.

        CR 601.2's own targets-before-cost order - CR 601.2c announces
        targets before CR 601.2f prices the spell - is what makes this
        askable at all: `self.targets` is already announced by the time this
        runs, so "beyond the first" of *however many targets were actually
        chosen* is simply `len(self.targets) - 1`, floored at zero for a
        spell targeting one thing or fewer. Dragonfire Blade's/Warrior's
        Blades' own per-target equip discount (`machines/keywords.
        equip_activation`) relies on the identical order for an *activated*
        ability instead, which CR 602.2b makes CR 601.2b-i's own order for
        casting a spell.
        """
        match = _COST_INCREASE_PER_TARGET_RE.search(self.spell.oracle_text or "")
        if match is None:
            return ManaCost()
        extra_targets = max(0, len(self.targets) - 1)
        if extra_targets == 0:
            return ManaCost()
        per_target = ManaCost.try_parse(match.group("amount"))
        if per_target is None:
            raise ValueError(
                f"{self.spell.name}'s per-target cost increase "
                f"{match.group('amount')} is not a mana cost this engine can read; the spell "
                "is refused rather than cast without it (CR 601.2f)"
            )
        return ManaCost(symbols=per_target.symbols * extra_targets)

    def _own_flash_surcharge(self) -> ManaCost:
        """ "You may cast this spell as though it had flash if you pay {2} more to
        cast it." (CR 702.8a, CR 601.2f): the extra cost is owed exactly when the
        cast needs the flash - the spell is not an instant and the caster could
        not cast a sorcery right now - and never at sorcery timing."""
        text = flash_surcharge(self.spell.oracle_text or "")
        if text is None or not self.flash_surcharge_owed:
            return ManaCost()
        return ManaCost.parse(text)

    def _own_cost_reduction(self) -> ManaCost:
        """What this spell's own text takes off its own cost right now
        (CR 601.2f), or nothing at all without a game to ask.

        `Game.cost_reduction_for` is the reader; `Casting.targets` is handed to
        it because one of the shapes it reads - Mystical Dispute's "if it
        targets a blue spell" - is a question about CR 601.2c's announcement
        rather than about the board.
        """
        if self.game is None:
            return ManaCost()
        return self.game.cost_reduction_for(self.spell, self.caster, targets=self.targets)

    def _charge_printed_additional_costs(self) -> None:
        """CR 601.2f: fold the card's own "As an additional cost to cast this
        spell, ..." sentences into the total cost.

        This is the step that makes a printed additional cost cost anything.
        CR 118.8a: "Any number of additional costs may be applied to a spell as
        it's being cast ... The controller of the spell or ability announces
        their intentions to pay any or all of those costs as described in rule
        601.2b", and CR 601.2f is where those announcements become the total
        cost. Without it Fling was announced for `{1}{R}`, sacrificed nothing,
        and dealt nothing - a card doing the wrong thing rather than a missing
        feature.

        The objects come from `sacrificing`/`discarding`/`exiling`/`tapping`,
        announced at CR 601.2b, and are handed to the components in the order
        the sentences print. An empty list is not an error: the component is
        built asking for its count and refuses to be paid until the cards are
        there (CR 118.3), which is what lets a Fling with no creature rewind
        cleanly rather than fail at announcement.

        Three shapes are deliberately left uncharged:

        - An **optional** cost - "you may exile any number of white cards from
          your hand" (March of Otherworldly Light) - because CR 118.8b says
          "some additional costs are optional" and not paying one is a legal
          announcement. It is skipped rather than refused.
        - X, which is substituted first (CR 107.3a, via `substitute_x`), so
          Toxic Deluge's "pay X life" is charged as the life the caster
          announced.
        - Nothing else. A mandatory sentence this engine cannot read raises,
          because CR 118.3 does not let the spell be cast without paying it -
          charging nothing would be the very bug this method exists to fix.
        """
        self._announce_blight_x()
        if self.printed_additional_costs_charged:
            return
        self.printed_additional_costs_charged = True
        built = self._printed_additional_costs()
        self.additional_costs.extend(built)
        if self.game is None:
            return
        for extra in built:
            for component in extra.components:
                if component.kind is not ComponentKind.REVEAL:
                    continue
                # CR 601.2h pays the reveal the caster chose, so a reveal
                # nobody named is asked about here, and cards that cannot pay
                # it are refused before anything is spent (CR 118.3).
                if self.revealing is None:
                    self.game.choose_cards_to_reveal(
                        component,
                        self.caster,
                        source=self.spell.name,
                        source_id=source_id_of(self.spell),
                        x_value=self.x_value,
                    )
                refusal = component.why_not(self.game)
                if refusal is not None:
                    raise ValueError(refusal)

    def _announce_blight_x(self) -> None:
        """CR 107.3a and CR 601.2b for "blight X": the counters a paid blight
        puts are the X announced, and the printed cap on X - Soul Immolation's
        "X can't be greater than the greatest toughness among creatures you
        control" - is checked now. A cap this cannot read refuses the cast
        rather than allow an X the card forbids (CR 118.3)."""
        variable = [
            component
            for cost in self.additional_costs
            for component in cost.components
            if component.kind is ComponentKind.PLACE_COUNTERS and component.variable_count
        ]
        if not variable:
            return
        cap = _X_CAP.search(self.spell.card.oracle_text or "")
        if cap is not None:
            bound = _GREATEST_AMONG_CREATURES.match(cap.group("bound").strip())
            if bound is None or self.game is None:
                raise ValueError(
                    f"{self.spell.name}'s X is capped by {cap.group(0)!r}, which this engine "
                    "cannot read, so the cast is refused (CR 107.3a)"
                )
            stat = bound.group("stat").lower()
            values = [
                getattr(self.game.characteristics_of(state), stat) or 0
                for state in self.game.permanents_controlled_by(self.caster)
                if self.game.characteristics_of(state).is_creature
            ]
            greatest = max(values, default=0)
            if self.x_value > greatest:
                raise ValueError(
                    f"X of {self.x_value} is greater than the greatest {stat} among creatures "
                    f"{self.caster} controls ({greatest}), which {self.spell.name} forbids "
                    "(CR 601.2b)"
                )
        for component in variable:
            component.amount = self.x_value

    def _additional_cost_primary_alternatives(
        self, pools: dict[ComponentKind, list[CardState]]
    ) -> dict[int, int]:
        """Which of CR 601.2b's "[cost] or [cost]" additional-cost sentences
        (`or_additional_cost_halves`) the caster is paying with their
        non-default half, and which of its alternatives, inferred from whether
        objects were nominated for it - the same way `sacrificing=[...]`
        already says "pay Fling's plain sacrifice cost" without a separate
        flag. A phrase with no matching objects in any pool defaults to its
        mana (or life) half, exactly like an unblighted "blight N or pay {M}"
        already defaults to the mana (`blighted`).

        A `ComponentKind.PAY_LIFE` primary (Redirect Lightning's own "pay 5
        life or pay {2}") has no object to nominate at all, so the pool
        inference alone could never choose it - `paying_life_for_additional_
        cost`'s own explicit index set is read here too, and either one
        picks the life half.

        Blight's own "or pay" sentences are excluded: they are resolved by
        `blight_paid`/`pay_blight`, never by this.
        """
        chosen: dict[int, int] = {}
        for index, printed in enumerate(additional_cost_phrases(self.spell.card, face=self.face)):
            if _BLIGHT_PHRASE.match(printed) is not None:
                continue
            halves = or_additional_cost_halves(substitute_x(printed, self.x_value))
            if halves is None:
                continue
            for pick, part in enumerate(_primary_alternatives_of(halves[0])):
                component = cost_component_for_phrase(part, self.caster)
                if component is None:
                    continue
                if pools.get(component.kind) or (
                    component.kind is ComponentKind.PAY_LIFE
                    and index in self.paying_life_for_additional_cost
                ):
                    chosen[index] = pick
                    break
        return chosen

    def _printed_additional_costs(self) -> list[TotalCost]:
        """The card's own additional costs as payable `TotalCost`s, built fresh
        and charged to nothing - see `_charge_printed_additional_costs`, which
        is the half that puts them on the casting.

        Separate from that so `total_cost` can report them before CR 601.2f has
        run: a caller asking what a Fling would cost before determining the
        cost is asking about the sacrifice too.
        """
        built: list[TotalCost] = []
        pools: dict[ComponentKind, list[CardState]] = {
            ComponentKind.SACRIFICE: list(self.sacrificing),
            ComponentKind.DISCARD: list(self.discarding),
            ComponentKind.EXILE: list(self.exiling),
            ComponentKind.TAP: list(self.tapping),
            ComponentKind.BEHOLD: list(self.beholding),
        }
        for cost in mandatory_additional_costs(
            self.spell,
            self.caster,
            self.x_value,
            blighted=self.blight_paid,
            primary_alternatives=self._additional_cost_primary_alternatives(pools),
            face=self.face,
        ):
            for component in cost.components:
                if component.kind is ComponentKind.REVEAL:
                    filled = announce_reveal(
                        component, self.revealing, self.x_value, self.spell.name
                    )
                    component.cards, component.required = filled.cards, filled.required
                    component.source = filled.source
                    continue
                pool = pools.get(component.kind)
                if pool is not None:
                    take_from_pool(component, pool)
            built.append(cost.assign_payer(self.caster))
        return built

    def _lock_in_own_reduction(self) -> None:
        """CR 601.2f: freeze the self-discount as the total cost is determined.

        `Game.determine_total_cost` appends the very same reduction to
        `cost_reductions` on its way here, so one entry equal to it is taken
        back out - the two paths must agree on one discount, not stack into
        two. Anything else in `cost_reductions` is somebody else's effect
        (`reduce_cost`) and is left where it is.
        """
        own = self._own_cost_reduction()
        if own.symbols and own in self.cost_reductions:
            self.cost_reductions.remove(own)
        self.self_reduction = own

    def determine_cost(
        self,
        x_value: int | None = None,
        additional: ManaCost | None = None,
        choices: list[int | None] | None = None,
    ) -> CostPayment:
        """CR 601.2f: lock in the total cost, X included, and open a payment.

        The total cost is locked here and does not change afterwards, even if
        something would alter it mid-payment (CR 601.8).

        An additional cost is combined with the printed one symbol for symbol
        by `ManaCost.plus`, so a hybrid, Phyrexian, or snow symbol survives it.

        `choices` pins how each symbol of the finished total cost is paid, one
        index into that symbol's options per symbol (CR 118.13a) - which half
        of a hybrid, or whether a Phyrexian symbol takes mana or life.

        Passing no `x_value` keeps whatever the caster already announced -
        `choose_modes` takes one, because a mode can read "up to X target
        cards" and CR 601.2c has to be able to count it. X is 0 if nobody ever
        said otherwise.
        """
        return self._refusing(lambda: self._determine_cost(x_value, additional, choices))

    def _x_restriction_text(self) -> str:
        """The text whose "X can't be 0" binds this cast's X (CR 107.3a).

        A keyword cost line's own restriction - Thieving Skydiver's "Kicker
        {X}. X can't be 0." - bounds the X of that cost only, so it binds
        only when the kicker is paid (CR 702.33a, CR 702.33d): an unkicked
        Skydiver has no X to announce and is cast with X 0."""
        text = self.spell.oracle_text or ""
        if self.kicked:
            return text
        ability = _keyword(self.spell.card, "kicker")
        if ability is None or ability.count_minimum is None:
            return text
        return "\n".join(line for line in text.split("\n") if line.strip() != ability.raw)

    def _determine_cost(
        self,
        x_value: int | None,
        additional: ManaCost | None,
        choices: list[int | None] | None,
    ) -> CostPayment:
        self._claim_zone_permission_if_unannounced()
        self._advance_to(CastingStep.COST_DETERMINED)
        if x_value is not None:
            self.x_value = x_value
        x_refusal = x_restriction_refusal(self._x_restriction_text(), self.x_value)
        if x_refusal is not None:
            raise ValueError(f"{self.spell.name}: {x_refusal}")
        if additional is not None:
            self.additional_costs.append(TotalCost.of(additional).assign_payer(self.caster))
        self._charge_printed_additional_costs()
        self._refuse_unless_mana_cost_payable()
        self._lock_in_own_reduction()

        payable_total = self.total_cost.assign_payer(self.caster)
        if (
            self.keyword_any_type_mana
            or (self.permission_used is not None and self.permission_used.any_type_mana)
        ) and payable_total.mana.symbols:
            # "... and mana of any type can be spent to cast it/that spell."
            # CR 202.3b: the spell's own printed/reduced mana cost is
            # unchanged everywhere else (`self.total_cost` itself, `Action.
            # cost`, mana value) - this only changes what the *payment* is
            # judged against, collapsing every colored and generic symbol
            # into one count (`ManaCost.converted`, CR 202.3) so any color in
            # the pool satisfies it.
            payable_total = TotalCost(
                mana=ManaCost.parse(f"{{{payable_total.mana.converted}}}"),
                components=payable_total.components,
                waterbend_generic=payable_total.waterbend_generic,
            ).assign_payer(self.caster)

        self.payment = CostPayment.for_total(
            payable_total,
            game=self.game,
            payer=self.caster,
            # CR 106.6: the payment has to know what it is paying for, or mana
            # carrying a spend restriction cannot be judged against it. This is
            # a *cast*, which is what tells Cavern of Souls's mana apart from
            # Shang-Chi's - the latter pays for no spell at all.
            #
            # `origin_zone` and not `self.spell.zone`: CR 601.2a moved the card
            # to the stack five steps ago, so the stack is the only answer the
            # object itself still has, and Interdimensional Web Watch's "cast
            # spells from exile" asks about where the cast *started*.
            spend=ManaSpend.casting(
                self.spell,
                zone=self.origin_zone,
                x_value=self.x_value,
                snow_any_color=self.keyword_snow_any_color,
            ).model_copy(
                update={
                    "treasure_only": self.treasure_mana_only,
                    "color_rule": (
                        None if self.game is None else self.game.mana_color_rule(self.caster)
                    ),
                    # CR 609.4b: Chromatic Orrery, Oath of Nissa, Case File
                    # Auditor - "spend mana as though it were mana of any color".
                    "any_color": self.keyword_any_color
                    or (self.permission_used is not None and self.permission_used.any_color_mana)
                    or (
                        self.game is not None
                        and self.game.spends_mana_as_any_color_for_spell(self.spell, self.caster)
                    ),
                    "any_type": self.game is not None
                    and self.game.spends_mana_of_any_type_for_spell(self.spell, self.caster),
                }
            ),
        )
        self.payment.paying_for = "spell"
        self.payment.paying_for_keyword = (self.keyword_used or "").lower() or None
        if not self.keyword_any_type_mana and (
            self.permission_used is None or not self.permission_used.any_type_mana
        ):
            # "Spend only black mana on X." (Consume Spirit): X's share of the
            # cost (`x_count * X`, CR 107.3a) is payable only with that colour,
            # unless mana of any type may be spent (CR 609.4b).
            self.payment.restrict_x_from_text(
                self.spell.oracle_text or "", self.base_cost.x_count, self.x_value
            )
        if choices is not None:
            self.payment.choose(choices)
        return self.payment

    def begin_paying(self, choices: list[int | None] | None = None) -> CostPayment:
        """CR 601.2g: mana abilities may be activated now, and only now.

        `choices` pins how each symbol is paid, as in `determine_cost`.
        """
        if self.payment is None:
            self.determine_cost(choices=choices)
        elif choices is not None:
            self.payment.choose(choices)
        self._advance_to(CastingStep.PAYING)
        assert self.payment is not None
        return self.payment

    def _refuse_unless_targets_announced(self) -> None:
        """CR 601.2c: a target the spell requires must actually be announced.

        "The player announces their choice of an appropriate object or player
        for each target the spell requires." `choose_targets` already refuses
        too few targets - but only when it is *called*, and a caller can skip
        it entirely, leaving `self.targets` empty. That is not a targeted
        spell cast at nothing; it is an announcement (CR 601.2c) that was
        never completed, so CR 601.2e makes the proposal illegal and CR 733.1
        reverses it. This is the one place every casting path passes through
        on the way to the stack, which is where it has to be caught.

        Left unchecked when the target parser could not read the spell's text
        (`understood is False`), for the same reason `TargetingProfile.check`
        skips it: refusing a target the parser merely failed to understand
        would be worse than not checking. CR 700.2c is handled by reading
        `self.targeting`, which is already narrowed to the chosen modes - a
        mode that targets nothing requires nothing.
        """
        profile = self.targeting
        if profile is None or not profile.understood:
            return
        required = profile.min_targets
        if required and len(self.targets) < required:
            raise ValueError(
                f"too few targets: {len(self.targets)} announced where "
                f"{self.spell.name} requires {required} (CR 601.2c)"
            )

    def _refuse_unless_modes_satisfied(self) -> None:
        """CR 700.2a/601.2b: modes are chosen as part of casting, not optional.

        `choose_modes` already rejects an out-of-range, duplicate, or unknown
        choice the moment it is called (via `ModalProfile.resolve`) - but a
        caller can skip calling it altogether, leaving `chosen_mode_numbers`
        at its empty default. That is not a spell cast with no chosen modes;
        it is a spell whose announcement (CR 601.2b) was never completed, so
        CR 601.2e/601.6 make the whole cast illegal. This is the one place
        every casting path passes through on the way to the stack, so it is
        where that illegality is finally caught, however it was reached.

        A card that is modal but whose instruction this parser could not read
        (`modal.understood is False`) is deliberately left unchecked, per
        `ModalProfile`'s own contract of refusing to guess. Elder Gargaroth's
        modal *triggered* ability likewise never reaches here, because
        `self.modal` only reads a *spell's* modal profile off the card - the
        creature spell itself is not modal.
        """
        modal = self.modal
        if modal is None or not modal.understood:
            return
        minimum, maximum = modal.allowed_range(
            entwined=self.entwined, alternative=self._alternative_mode_count(modal)
        )
        chosen = len(self.chosen_mode_numbers)
        if minimum <= chosen <= maximum:
            return
        listing = "; ".join(str(mode) for mode in modal.modes)
        requirement = f"exactly {minimum}" if minimum == maximum else f"{minimum} to {maximum}"
        raise ValueError(
            f"{self.spell.name} is modal (CR 700.2a, CR 601.2b) and requires "
            f"{requirement} mode(s) chosen, but {chosen} were chosen. Modes: {listing}"
        )

    def _refuse_if_x_changed_since_targets(self) -> None:
        """CR 107.3a/CR 107.3c: X is fixed once for the whole spell - it does
        not get to mean one thing when targets were counted and another when
        the spell resolves.

        `choose_modes(x_value=...)` and `determine_cost(x_value=...)` are two
        independent setters of `self.x_value`: nothing before this stopped a
        caller from announcing targets under one value and then changing X
        with the other setter before `cast()`. That mismatch used to be
        silent - a mode reading "up to X target cards" would be *counted*
        against the X in force when `choose_targets` ran, then *resolve*
        against whatever X ended up being, which can create more targets than
        were ever legally announced for it. Loud beats silent here: refuse the
        cast outright rather than let the two disagree.
        """
        if self.x_value_at_targets is None:
            return
        if self.x_value_at_targets == self.x_value:
            return
        raise ValueError(
            f"{self.spell.name}: X was {self.x_value_at_targets} when targets were "
            f"chosen but is now {self.x_value} (CR 107.3a). Announce X once, before "
            f"choosing targets - via choose_modes's own x_value, or determine_cost "
            f"before choose_targets - and do not change it afterward."
        )

    def _refuse_unless_mana_cost_payable(self) -> None:
        """CR 118.6: a card with no printed mana cost has an unpayable cost.

        `self.alternative_cost` is set exactly when CR 118.9's alternative
        cost machinery ran - `use_keyword` (Suspend's own free cast, once its
        last time counter comes off), `use_permission` (Shardless Agent's
        cascade hit), or `use_pitch_cost` - so this only refuses the *plain*
        hardcast CR 601.2b never grants Living End on its own: no black
        source on the battlefield, no alternative cost, no announcement. See
        `why_mana_cost_unpayable`, which does the actual check - shared with
        `legal_actions._cast_action`, which asks the identical question
        before any `Casting` exists, so a `CAST` action's own `Action.
        affordable` can never disagree with what this would raise.
        """
        refusal = why_mana_cost_unpayable(self.spell.name, self.base_cost, self.alternative_cost)
        if refusal is not None:
            raise ValueError(refusal)

    def _refuse_unless_allowed_from_its_zone(self) -> None:
        """CR 601.3: a spell cast from anywhere but the hand needs permission -
        and CR 601.2b's announcement has to have actually *claimed* it.

        "A player can begin to cast a spell only if a rule or effect allows
        that player to cast it and no rule or effect prohibits that player from
        casting it." The hand is where the rules cast from by default
        (CR 302.1, CR 601.3); every other zone needs a keyword's static grant
        or an effect's `PlayPermission`. Two separate questions follow from
        that one sentence, and both have to clear:

        1. **Could anything allow this** (`why_cannot_cast_from`) - CR 601.3's
           existence question, left exactly as it was: three scenario tests
           (`test_flashback.py`, `test_madness.py`, `test_play_from_exile.py`)
           call it directly with that meaning, and it is still the right
           refusal-reason string when nothing at all applies.
        2. **Did this announcement claim it.** CR 702.34a's flashback (and
           mayhem CR 702.187b, plot CR 702.170d, foretell CR 702.143a, madness
           CR 702.35a, a printed CR 604.6 zone permission, and a CR 610.5/
           CR 611.3d granted keyword option) each read as one clause tying a
           zone permission to a specific cost that replaces the mana cost -
           the graveyard permission does not exist apart from flashback's own
           cost. CR 601.2b makes choosing to pay that cost a *previously made
           choice* the player announces, and CR 118.9a lets only one
           alternative cost apply to a spell, which presupposes the player
           choosing one rather than the engine picking the sole option that
           happens to be available. So `keyword_used`/`permission_used` has
           to be set - the mere *existence* of a `KeywordCastOption` for this
           zone is not the same as announcing it, and treating it as such is
           exactly the live-game defect this closes: Faithful Mending
           (mana cost `{W}{U}`, Flashback `{1}{W}{U}`) charged and recast from
           the graveyard for `{W}{U}` forever, because nothing ever checked
           that `Flashback` had actually been named.

        Question 2 is skipped when a live `PlayPermission` is what makes
        question 1 answer "yes" (`usable_play_permission`): such a permission
        already **is** CR 601.3's claimed grant the moment a resolving effect
        hands it out (Ugin's −11, Ragavan's trigger, cascade, suspend), and
        removing that leniency would refuse every live-play caller that never
        calls `use_permission()` explicitly. Warp's second half and CR 715.3d's
        Adventure are two `KeywordCastOption`s where `pays_mana_cost=True`
        (the printed mana cost is the *right* cost, not an undercharge) but
        the zone permission is still tied to the keyword, so they still need
        `keyword_used` set - `use_keyword("Warp")`/`use_keyword("Adventure")`
        - rather than the `PlayPermission` leniency, which does not apply to
        them at all.

        Bare CR 118.9 alternative costs cast from the hand - evoke
        (CR 702.74a), dash (CR 702.109a), morph/megamorph/disguise
        (CR 702.37a, CR 702.37c), bestow (CR 702.103a's "you may choose"),
        warp from hand (CR 702.185a) - never reach question 2 at all: this
        method returns immediately for `origin_zone is Zone.HAND`, which is
        exactly where the rules already cast from by default and where none
        of those five need to prove anything more than question 1.

        Checked here rather than at announcement because `Casting` is driven
        step by step: a scenario legitimately constructs the machine for a card
        in the graveyard and *then* discovers, through `use_keyword`, that
        nothing allows it. This is the last point before the spell reaches the
        stack, and CR 601.6/CR 733.1 rewind the whole thing anyway, so refusing
        here refuses the same action - it just lets the earlier steps say their
        own, more specific "no" first.
        """
        if self.origin_zone is Zone.HAND:
            return
        with self._as_of_the_proposal():
            # The permission and its timing are questions about the moment the
            # cast was proposed (CR 601.3), which is before CR 601.2a's move -
            # so the spell itself does not count against a keyword's own
            # "with the stack empty" (CR 702.170a, CR 307.5).
            refusal = why_cannot_cast_from(
                self._as_announced,
                self.caster,
                self.origin_zone,
                self.game,
                library_top=self.announced_library_top,
                cost_paid=True,
            )
            if refusal is not None:
                raise ValueError(refusal)
            refusal = self._normal_face_only_refusal(self.face)
            if refusal is not None:
                raise ValueError(refusal)
            if self.keyword_face_only is not None and self.face != self.keyword_face_only:
                raise ValueError(
                    aftermath_face_only_refusal(self.spell.name, self.keyword_face_only, self.face)
                )
            if self.keyword_used is not None or self.permission_used is not None:
                return
            if usable_play_permission(self.game, self._as_announced, self.caster) is not None:
                return
            raise ValueError(self._unclaimed_zone_permission_message())

    def _refuse_unless_flash_grant_claimed(self) -> None:
        """CR 117.1a's refusal, set aside at the proposal because an alternative
        cost grants flash (`flash_grant_sources`), comes back unless that
        alternative cost is the one this cast pays."""
        refusal = self.timing_refusals_unless_flash_grant.get(self.face or "")
        if refusal is None or self.game is None:
            return
        if self._flash_grant_claimed():
            return
        if self.keyword_answers_timing and (self.face or "") in (
            self.timing_refusals_unless_keyword_timing
        ):
            return
        raise ValueError(refusal)

    def _flash_grant_claimed(self) -> bool:
        """Whether this cast pays the alternative cost that grants flash."""
        if self.game is None:
            return False
        sources = flash_grant_sources(self.game, self._as_announced, self.caster)
        return self.free_cast_source in sources

    def _refuse_unless_keyword_timing_claimed(self) -> None:
        """CR 117.1a's refusal, set aside at the proposal because an option
        with its own timing exists for the card's zone, comes back unless the
        option this cast used is such an option (or the flash-granting
        alternative cost lifted it too and is the one paid)."""
        key = self.face or ""
        refusal = self.timing_refusals_unless_keyword_timing.get(key)
        if refusal is None or self.keyword_answers_timing:
            return
        if key in self.timing_refusals_unless_flash_grant and self._flash_grant_claimed():
            return
        raise ValueError(refusal)

    def _refuse_unless_timing_window_claimed(self) -> None:
        """CR 117.1a's refusal, set aside at the proposal because a timing
        window was open (`timing_refusals_unless_window`), comes back unless
        the keyword that opened it is the one this cast used - the same
        "permission has to be claimed" reading `_refuse_unless_allowed_from_
        its_zone` makes of a zone permission."""
        if self.keyword_opens_window:
            return
        refusal = self.timing_refusals_unless_window.get(self.face or "")
        if refusal is not None:
            raise ValueError(refusal)

    def _normal_face_only_refusal(self, face: str | None) -> str | None:
        """CR 715.3d's "It can't be cast as an Adventure this way": the
        claimed option (`keyword_normal_face_only`) covers the card's normal
        characteristics only, so any face named on top of it is refused."""
        if not self.keyword_normal_face_only or face is None:
            return None
        return (
            f"{self.spell.name} may be cast from the {self.origin_zone.value} with "
            f"{self.keyword_used} only as its normal face, not as {face}: "
            f"it can't be cast as an Adventure this way (CR 715.3d)"
        )

    def _unclaimed_zone_permission_message(self) -> str:
        """Name what CR 601.2b needed this announcement to claim, the way
        `use_alternative_cost` already names its own options ("name it: ...")
        when more than one applies.

        Driven off `self.cast_options` - the same option machinery
        `why_cannot_cast_from` and `use_keyword` both already read off the
        card's printed keywords, the pile of exile it sits in, and whatever
        another permanent grants it - never off a table of card names.
        """
        usable = [
            option
            for option in self.cast_options
            if option.why_not(self._as_announced, self.caster, self.game, origin=self.origin_zone)
            is None
        ]
        names = ", ".join(
            f"{option.keyword} {_describe_keyword_cost(option)} ({option.rule})"
            for option in usable
        )
        if not names:
            # Reached only if a live `PlayPermission` supplied question 1's
            # "yes" and was somehow not already caught by the leniency check
            # above - kept as an honest fallback rather than an assertion, so
            # an unanticipated permission shape fails loud instead of raising
            # out of an empty join.
            return (
                f"{self.spell.name} can be cast from the {self.origin_zone.value} only by "
                f"claiming the permission that allows it (CR 601.2b)"
            )
        return (
            f"{self.spell.name} can be cast from your {self.origin_zone.value} only by "
            f"announcing a keyword that allows it: {names}"
        )

    def _refuse_unless_face_cast_allowed(self) -> None:
        """CR 709.3a/715.3a: refuse at CR 601.2i if the face this cast ended
        up on is one CR 601.3 never allowed - CR 117.1a's timing or CR 611.1's
        prohibitions alike.

        `cast_as_split_half` and `cast_as_adventure` each check the face they
        name, but a caller can also name **none**: propose Incubation //
        Incongruity during an upkeep step (allowed, because Incongruity is an
        Instant), then finish the cast without ever choosing a half, and the
        spell would go through as Incubation - a Sorcery, at instant speed.
        `face_cast_refusals` holds that answer under `""`, frozen at the
        proposal, so this is the one place it can be spent.

        A **fused** split spell (CR 702.102b, CR 709.4d) has both halves'
        characteristics combined rather than the left half's alone, even
        though `cast_fused` sets `face` to the left half - so it is judged by
        the no-face answer too. Every printed fuse card has the same card type
        on both halves (Wear // Tear is `Instant // Instant`, Beck // Call is
        `Sorcery // Sorcery`), which is what makes that reading exact here
        rather than merely close.
        """
        refusal = self.face_cast_refusals.get("" if self.fuse else (self.face or ""))
        if refusal is not None:
            raise ValueError(refusal)

    def _granted_flashback_keyword(self) -> str | None:
        """ "Flashback", if this cast was made under a granted-flashback
        `PlayPermission` (`PlayPermission.flashback`), else `None`.

        CR 702.34a's exile-instead-of-anywhere-else half is written entirely
        off `CastRecord.keyword` by `machines/replacement.py`'s
        `_stack_replacements`, which has no notion of a `PlayPermission` at
        all - a printed flashback sets `keyword_used` and reaches that check
        for free, so a granted one has to arrive the same way.
        """
        if self.permission_used is not None and self.permission_used.flashback:
            return "Flashback"
        if self.permission_used is not None and self.permission_used.harmonize:
            return "Harmonize"  # CR 702.180a's third ability reads the same record
        return None

    def cast(self) -> CardState:
        """Finish casting: the cost is paid and the spell is on the stack.

        Run under `Game._id_allocator_scope` whenever there is a game to
        install it on: `_cast_impl` moves the spell's face-down turn and
        stack placement (`CardState.move_to` mints a fresh
        `zone_change_stamp`) and, once on the stack, may put ward's own
        trigger there too (`_emit_becomes_target`) - both persisted ids, both
        minted only here. The no-game path (`Casting` driven as a pure
        announcement machine, see `_move_to_the_stack`'s own docstring) has
        no `Game` to install an allocator on and needs none: nothing it does
        is replayed.
        """
        if self.game is None:
            return self._cast_impl()
        with self.game._id_allocator_scope():
            return self._cast_impl()

    def _cast_impl(self) -> CardState:
        """The rest of `cast` - see its own docstring for why it is split out."""
        if self.payment is None or self.payment.step is not CostStep.PAID:
            raise ValueError("cannot finish casting before the cost is paid")
        self._refuse_unless_modes_satisfied()
        self._refuse_unless_face_cast_allowed()
        self._refuse_unless_targets_announced()
        self._refuse_if_x_changed_since_targets()
        self._refuse_unless_allowed_from_its_zone()
        self._refuse_unless_timing_window_claimed()
        self._refuse_unless_keyword_timing_claimed()
        self._refuse_unless_flash_grant_claimed()

        self._advance_to(CastingStep.CAST)
        self._turn_face_down_if_cast_that_way()
        if self.spell.zone is not Zone.STACK:
            # CR 601.2a already moved it for every announcement that had a game
            # to move it in; this is the no-game path, where `Casting` is driven
            # as a pure announcement machine and the card is moved at the end.
            self.spell.move_to(Zone.STACK)
        if self.transformed:
            self.spell.transformed = True  # CR 712.11a
        # The spell carries its targets with it, so resolution knows what it hits.
        self.spell.targets = list(self.targets)
        # CR 601.2d: the announced division, if any, travels with the spell
        # the same way its targets do - `None` when `announce_division` was
        # never called, which `deal_divided_damage` reads as "fall back to
        # splitting the total as evenly as it goes" rather than an error.
        self.spell.division = list(self.division) if self.division is not None else None
        if self.spell.card.layout in (Layout.SPLIT, Layout.ADVENTURE, Layout.MODAL_DFC):
            # CR 709.3b: "While on the stack, only the characteristics of the
            # half being cast exist", CR 712.8f's modal double-faced twin
            # (the face CR 712.11b chose), and CR 715.3b's Adventure equivalent:
            # "While on the stack as an Adventure, the spell has only its
            # alternative characteristics." `CardState.face_played` is what
            # `up_face` reads for the whole time this spell sits on the stack.
            #
            # Assigned *unconditionally*, not only when `self.face` is set:
            # `CardState.move_to` never clears `face_played`, so an adventurer
            # exiled by CR 715.3d and then recast as its creature half would
            # otherwise still be carrying the Adventure face it was cast with
            # the first time, and resolve as an Instant. `None` here is the
            # CR 715.4 answer - "while on the stack not as an Adventure, an
            # adventurer card has only its normal characteristics."
            self.spell.face_played = self.face
            self.spell.fused = self.fuse
        if self.game is not None:
            self._emit_becomes_target()
            # CR 601.2b announced the keyword, the face and the modes, and
            # CR 601.2h paid the cost, and the `CardState` that reaches the
            # stack carries none of it. Several rules ask afterwards:
            # flashback's "exile this card instead" (CR 702.34a), warp's
            # delayed trigger, which exists only if the warp cost was paid
            # (CR 702.185a), Adventure's exile on resolution (CR 715.3d), which
            # targets a modal spell has (CR 700.2c, rechecked by CR 608.2b),
            # what mana was spent to pay the total cost (CR 601.2h), and
            # whether a kicker cost was among the costs paid (CR 702.33d).
            # `Game.note_cast` is where every answer is kept.
            # CR 702.47c/CR 612.10: the spliced cards' rules text is added to
            # the spell, following its own. Written here, at the end of a
            # completed announcement, because CR 601.6 can still reverse
            # everything up to this point and a rewound casting must leave the
            # card's text unchanged. CR 702.47e takes it off again, in
            # `CardState.move_to`, whenever the spell leaves the stack.
            self.spell.spliced_text = tuple(self.spliced_text)
            self.game.note_cast(
                self.spell,
                keyword=self.keyword_used
                if self.keyword_used is not None
                else self._granted_flashback_keyword(),
                keyword_cost_paid=self.keyword_cost_paid,
                exile_instead_of_graveyard=bool(
                    self.permission_used and self.permission_used.exile_instead_of_graveyard
                )
                or self.keyword_exiles_instead,
                origin_zone=self.origin_zone,
                face=self.face,
                modes=list(self.chosen_mode_numbers),
                mode_targets=[list(slice_) for slice_ in self.mode_target_slices],
                x_value=self.x_value if self._lock_cast_amount() is None else self.locked_amount,
                mana_spent=(
                    dict(self.payment.mana_payment.spend)
                    if self.payment is not None and self.payment.mana_payment is not None
                    else {}
                ),
                # CR 106.6: the mana that just paid this cost may carry an
                # additional effect on the spell it was spent on. Which mana
                # paid is only knowable here, at CR 601.2h, and only from the
                # settled payment - the pool has already been debited.
                spend_effects=[
                    tagged.effect.text
                    for tagged in (
                        self.payment.mana_payment.spend_effects_spent
                        if self.payment is not None and self.payment.mana_payment is not None
                        else []
                    )
                ],
                treasure_mana_spent=(
                    sum(self.payment.mana_payment.treasure_spent.values())
                    if self.payment is not None and self.payment.mana_payment is not None
                    else 0
                ),
                kicked=self.kicked,
                replicated=self.replicated,
                casualty_paid=self.casualty_paid,
                conspire_paid=self.conspire_paid,
                offspring_paid=self.offspring_paid,
                blight_paid=self.blight_paid,
                cast_using_teamwork=self.teamwork_paid,
                # CR 702.150a (compleated): read off the settled payment,
                # only at CR 601.2h like `mana_spent` just above it - the
                # payment is the one place the actual choice of resource per
                # symbol survives.
                phyrexian_life_symbols_paid=(
                    self.payment.phyrexian_life_symbols_paid if self.payment is not None else 0
                ),
                gift_promised=self.gift_promised,
                gift_chosen_player=self.gift_chosen_player,
                behold_chosen_type_paid=self.behold_chosen_type_paid,
                chosen_creature_type=self.chosen_creature_type_for_cost,
                # CR 400.7 makes the spell a new object the moment CR 601.2a
                # moves it off the exile pile, so the annotation that pile
                # carried is gone by now - `announced_exile_annotation` is the
                # copy taken before that move. Foretell is what needs it:
                # CR 702.143a's "that card gains 'Foretell [cost]'" is paid
                # from exile, and Lupine Harbingers counts "the number of turns
                # you've begun since it was foretold" off `turn_exiled`, a
                # number nothing else on the record can answer for.
                exile_annotation=self.announced_exile_annotation,
                sneak_defender=self.returned_creature_defender,
                enters_with_counters=list(self.keyword_enters_with_counters),
                kicker_costs_paid=list(self.kicker_costs_paid),
                controlled_subtypes_as_cast=self._controlled_subtypes(),
                controlled_modified_creature_as_cast=self._controls_modified_creature(),
                bargained=self.bargained,
                evidence_collected=self.evidence_collected,
                revealed_for_cost=self.revealed_for_cost,
                beheld_for_cost=self.beheld_for_cost,
                waterbend_paid=self.waterbend_paid,
                # CR 106.3's source of the mana spent (a creature) and CR
                # 107.4h's snow source, read off the settled payment at CR
                # 601.2h like `treasure_mana_spent`.
                creature_mana_spent=(
                    sum(self.payment.mana_payment.creature_spent.values())
                    if self.payment is not None and self.payment.mana_payment is not None
                    else 0
                ),
                cave_mana_spent=(
                    sum(self.payment.mana_payment.cave_spent.values())
                    if self.payment is not None and self.payment.mana_payment is not None
                    else 0
                ),
                returned_mana_value=self.returned_mana_value,
                extra_mana_counters=self.extra_mana_counters,
                convoked=(
                    sum(1 for entry in self.payment.substitutions if entry.keyword == "convoke")
                    if self.payment is not None
                    else 0
                ),
                snow_mana_spent=(
                    dict(self.payment.mana_payment.snow_spent)
                    if self.payment is not None and self.payment.mana_payment is not None
                    else {}
                ),
                additional_cost_cards=[
                    card.id
                    for extra in self.additional_costs
                    for component in extra.components
                    for card in component.cards
                ],
                additional_cost_kinds=[
                    component.kind.value
                    for extra in self.additional_costs
                    for component in extra.components
                    for _card in component.cards
                ],
            )
            if self.waterbend_paid:
                # CR 701.67c: "An ability that triggers whenever a player
                # waterbends triggers whenever that player pays a waterbend
                # cost, regardless of how they paid that cost." One event for
                # the one waterbend cost paid at CR 601.2h - mana, taps or a
                # mix - the same event `Game.activate_ability` raises.
                self.game.record_turn_fact("waterbent", self.caster)
                self.game.emit(
                    GameEvent(
                        event=ExtraTriggerEvent.WATERBENDS,
                        subject_id=self.spell.id,
                        subject_name=self.spell.name,
                        subject_controller=self.caster,
                        subject_card=self.spell.card,
                        player=self.caster,
                    )
                )
            if self.keyword_once_per_turn_key is not None:
                # "Once during each of your turns": this cast is the once.
                self.game.once_per_turn_cast_permissions_used[self.keyword_once_per_turn_key] = 1
            if self.permission_used is not None:
                self.game.spend_play_permission_choice(self.permission_used)
        return self.spell

    def _controls_modified_creature(self) -> bool:
        """CR 601.2i / CR 700.9: whether the caster controls a modified creature
        as the spell becomes cast - "If you controlled a modified creature as
        you cast this spell"."""
        from ..conditions.board import controls_modified_creature

        return self.game is not None and controls_modified_creature(self.game, self.caster)

    def _controlled_subtypes(self) -> tuple[str, ...]:
        """CR 601.2i: every subtype among the permanents the caster controls as
        the spell becomes cast, lowercased and sorted, off the computed board
        (CR 613.5) - "or controlled a Dragon as you cast this spell"."""
        if self.game is None:
            return ()
        board = self.game.computed_board()
        return tuple(
            sorted(
                {
                    subtype.lower()
                    for state in self.game.permanents_controlled_by(self.caster)
                    for subtype in board.of(state).subtypes
                }
            )
        )

    def _turn_face_down_if_cast_that_way(self) -> None:
        """CR 708.4: a card cast face down is turned face down before it is cast.

        "Objects that are cast face down are turned face down before they are
        put onto the stack, so effects that care about the characteristics of a
        spell will see only the face-down spell's characteristics."

        Which characteristics those are is listed by the keyword that allowed it
        (CR 708.2): CR 702.37c for morph and megamorph, CR 702.168b for
        disguise.
        """
        if self.keyword_used is None:
            return
        if self.keyword_used.lower() not in ("morph", "megamorph", "disguise"):
            return
        characteristics = face_down_characteristics(self.spell.card)
        if characteristics is not None:
            self.spell.turn_face_down(characteristics)

    def _emit_becomes_target(self) -> None:
        """CR 702.21a: the objects this spell targeted have become targets.

        Ward is a *triggered* ability, so this is an event like any other and
        `Game.emit` works out what it fired. It is raised as the announcement
        finishes because that is when the targets are settled (CR 601.2c) and
        the spell exists on the stack for the trigger to counter (CR 601.2i);
        `Game.put_on_stack` then flushes it alongside the cast triggers, which
        is CR 603.3's "the next time a player would receive priority".

        Permanents and spells on the stack are asked: CR 702.21a says
        "whenever **this permanent** becomes the target" (an object that is
        not on the battlefield is not a permanent, CR 110.1), and a spell
        targeted by a counterspell is an object a "creature spell you control
        becomes the target of ..." condition (Surrak, Elusive Hunter) watches.
        """
        for target in self.targets:
            if target.username is not None and not target.is_card:
                # CR 115.1: a player can be targeted too ("you or another
                # permanent you control becomes the target of ...").
                self.game.emit(
                    GameEvent(
                        event=TriggerEvent.BECOMES_TARGET,
                        subject_name=target.username,
                        subject_controller=target.username,
                        targeted_by=self.spell.id,
                        player=self.caster,
                    )
                )
                continue
            if not target.is_card or target.card_id is None:
                continue
            targeted = self.game.find_by_id(target.card_id)
            if targeted is None or targeted.zone not in (Zone.BATTLEFIELD, Zone.STACK):
                continue
            self.game.emit(
                GameEvent(
                    event=TriggerEvent.BECOMES_TARGET,
                    subject_id=targeted.id,
                    subject_name=targeted.name,
                    subject_controller=(
                        targeted.controller
                        if targeted.zone is Zone.BATTLEFIELD
                        else self.game.controller_of(targeted).username
                    ),
                    subject_card=targeted.card,
                    targeted_by=self.spell.id,
                    player=self.caster,
                )
            )

    def cancel(self) -> None:
        """Rewind the announcement, undoing every payment already made.

        CR 733.1: the entire action is reversed and any payments already made
        are cancelled. The spell goes back where it came from, since a spell
        that cannot be cast legally was never cast at all (CR 601.6).

        Run under `Game._id_allocator_scope` whenever there is a game to
        install it on: `_cancel_impl` mints a fresh `zone_change_stamp`
        putting `self.spell` back in `self.origin_zone` (`CardState.move_to`),
        and `_undo_the_move_to_the_stack` mints another restoring it to
        `announced_zone` through `Player.add` (immediately overwritten there
        with the original `announced_stamp`, but the mint still has to come
        from the installed allocator for `objects_created`'s count to stay
        deterministic across a replay). The no-game path mirrors `cast()`'s
        own no-game branch: this is the hottest of the six sites this
        docstring is one of - the api's `rewind_unfinished` calls it on every
        refused or dry-run cast attempt, most of which never had a game to
        hold a stack in the first place.
        """
        if self.game is None:
            self._cancel_impl()
            return
        with self.game._id_allocator_scope():
            self._cancel_impl()

    def _cancel_impl(self) -> None:
        """The rest of `cancel` - see its own docstring for why it is split out."""
        if self.is_settled:
            raise ValueError(f"casting is already {self.step}")
        if self.payment is not None:
            self.payment.rewind()
        annotation = self.spell.exile_annotation
        self.spell.move_to(self.origin_zone)
        if self.origin_zone is Zone.EXILE:
            # It never left, so its pile is still its pile (CR 406.4).
            self.spell.exile_annotation = annotation
        self._undo_the_move_to_the_stack()
        self.step = CastingStep.CANCELLED

    def _undo_the_move_to_the_stack(self) -> None:
        """Put the card back where CR 601.2a took it from (CR 601.6, 733.1).

        "The entire action is reversed" - which includes the move itself, so
        the CR 400.7 identity stamp and the exile pile it had are restored
        too: an announcement that was rewound never happened, and an effect's
        `PlayPermission` (or a delayed trigger watching that exact object)
        must still name the same card afterwards.
        """
        if self.announced_zone is None or self.game is None:
            return
        self._lift_out_of_every_zone()
        if self.announced_zone in getattr(self.game, "shared_zones", {}):
            self.game.shared_zones[self.announced_zone].append(self.spell)
        else:
            owner = self.game.player(self.spell.owner or self.caster)
            owner.add(self.spell, self.announced_zone)
            if self.announced_zone is Zone.LIBRARY and self.announced_library_index is not None:
                # CR 401.2: the library keeps its order, so the card goes back
                # where it was rather than wherever `Player.add` appended it.
                owner.library.remove(self.spell)
                owner.library.insert(self.announced_library_index, self.spell)
        # Written last, because `Player.add` moves the card itself and a move
        # is a new object (CR 400.7) with a fresh stamp - and this rewind is
        # precisely the claim that no move ever happened.
        self.spell.zone = self.announced_zone
        self.spell.zone_change_stamp = self.announced_stamp
        self.spell.exile_annotation = self.announced_exile_annotation
        self.spell.granted_ability_texts = self.announced_granted_ability_texts
        self.spell.discarded_by = self.announced_discarded_by
        self.spell.discarded_on_turn = self.announced_discarded_on_turn
        self.announced_zone = None

    def _enter_modes(self) -> None:
        """CR 601.2b happens once, before targets are chosen."""
        if self.is_settled:
            raise ValueError(f"casting is already {self.step}")
        if self.step is CastingStep.PROPOSED:
            self.step = CastingStep.MODES
        elif self.step is not CastingStep.MODES:
            raise ValueError(f"cannot go back to {CastingStep.MODES} from {self.step}")

    def _advance_to(self, target: CastingStep) -> None:
        """Steps run in order and none may be repeated or skipped backwards."""
        if self.is_settled:
            raise ValueError(f"casting is already {self.step}")
        if CASTING_ORDER.index(target) <= CASTING_ORDER.index(self.step):
            raise ValueError(f"cannot go back to {target} from {self.step}")
        self.step = target


def _as_mana(amount: ManaCost | str) -> ManaCost:
    return ManaCost.parse(amount) if isinstance(amount, str) else amount


# --------------------------------------------------------------------------
# CR 118.9's PERMISSION and STATIC alternative-cost sources, pure over
# `(game, caster, card)` - used by both `Casting.alternative_costs` (an
# in-flight announcement) and `Game.alternative_costs_for` (before any
# `Casting` exists). Neither branch reads anything an in-flight proposal
# knows that the plain `game`/`caster`/`card` triple does not already say:
# `play_permissions_on` is keyed off the object's own CR 400.7 identity, and
# `static_free_cast_grants` is a board read gated on `caster` alone.
# --------------------------------------------------------------------------


def static_free_cast_grants(game: Any, caster: str) -> list[tuple[str, StaticFreeCastGrant]]:
    """Omniscience's shape: a permanent `caster` controls whose static
    ability applies CR 118.9's alternative cost of nothing to their spells.

    Read line by line and only from a genuine `AbilityKind.STATIC` line
    (CR 604.1), the same way `Game.static_cost_modifiers_for` reads a
    board-wide cost modifier - a sentence inside an activated ability's
    effect is gated on that ability being activated and is not a static
    ability at all (CR 602.1).

    Read off the permanent's *computed* ability list (`Characteristics.
    abilities`, CR 613.1f), not its printed oracle text - a granting static
    ability layer 6 already stripped no longer applies, the same fix
    `granted_cast_options` above needs for CR 610.5's grant.
    """
    if game is None:
        return []
    found: list[tuple[str, StaticFreeCastGrant]] = []
    # One board, hoisted out of the loop: `computed_board()` recomputes the
    # whole battlefield every call (CR 613.5).
    board = game.computed_board()
    for permanent in getattr(game, "battlefield", []):
        yours = permanent.controller == caster
        if not yours and not any(
            "each player casts" in line for line in board.of(permanent).abilities
        ):
            # Only a grant that names every player reaches past its controller.
            continue
        static_lines = {
            ability.raw.strip()
            for ability in parse_granted_ability_lines(board.of(permanent).abilities)
            if ability.kind is AbilityKind.STATIC
        }
        for line in static_lines:
            grant = static_free_cast_grant(line)
            if grant is not None and (yours or grant.first_spell_each_players_turn):
                grant = grant.model_copy(update={"source_id": permanent.id})
                if grant.once_each_of_your_turns or grant.once_each_turn:
                    grant = grant.model_copy(
                        update={"once_per_turn_key": once_per_turn_key(permanent)}
                    )
                found.append((permanent.card.name, grant))
    return found


def static_grant_option(
    index: int,
    source_name: str,
    grant: StaticFreeCastGrant,
    game: Any,
    caster: str,
    card: CardState,
    origin_zone: Zone,
    payer: str | None = None,
) -> AlternativeCostOption:
    """The CR 118.9 option one static grant makes of casting `card`: nothing
    at all (Omniscience), or the cost the grant prints (Fist of Suns' five
    colours, Kentaro's mana value, Conspiracy Unraveler's collected evidence)."""
    cost: TotalCost | None = None
    description = "nothing"
    unavailable = static_free_cast_refusal(game, caster, card, origin_zone, source_name, grant)
    if grant.cost_phrase is not None:
        if grant.cost_is_mana_value:
            cost = TotalCost.of(ManaCost.parse(f"{{{int(card.mana_value)}}}"))
        else:
            cost = printed_cost_total(grant.cost_phrase, payer)
        if cost is None and unavailable is None:
            unavailable = f"{source_name}'s alternative cost {grant.cost_phrase!r} is not read"
        description = str(cost) if cost is not None else grant.cost_phrase
    return AlternativeCostOption(
        index=index,
        source=AlternativeCostSource.STATIC,
        rule="CR 118.9",
        source_name=source_name,
        description=description,
        cost=cost,
        requires=sum(component.required for component in cost.components) if cost else 0,
        unavailable=unavailable,
        once_per_turn_key=grant.once_per_turn_key,
    )


def static_free_cast_refusal(
    game: Any,
    caster: str,
    card: CardState,
    origin_zone: Zone,
    source_name: str,
    grant: StaticFreeCastGrant,
) -> str | None:
    """Why `grant` (an Omniscience- or Zaffai-shaped static free cast, CR
    118.9) does not apply to `card` cast by `caster` from `origin_zone`
    right now, or None when it does.

    The one answer both `Casting.alternative_costs` and `Game.
    alternative_costs_for` give, so the listing a seat reads and the cast it
    makes agree: the zone the grant names (the top card of the library too,
    for "or the top of your library"), the card type it names (CR 205.2b's
    any-of-them), a mana value cap, and for "Once during each of your turns"
    whose turn it is and whether that permanent's one use this turn is gone.
    """
    in_zone = grant.any_zone or grant.zone is None or origin_zone is grant.zone
    if not in_zone and grant.also_top_of_library and origin_zone is Zone.LIBRARY:
        library = game.player(caster).library if game is not None else []
        in_zone = bool(library) and library[0] is card
    if not in_zone:
        return (
            f"{source_name} only applies to spells cast from your "
            f"{grant.zone.value if grant.zone else 'hand'} (CR 118.9)"
        )
    if grant.quality_phrase:
        quality = object_quality(grant.quality_phrase)
        if quality is None or not quality(game, card):
            return f"{source_name} only applies to {grant.quality_phrase} spells (CR 118.9)"
    if grant.max_mana_value_counters:
        source = game.find_by_id(grant.source_id) if grant.source_id is not None else None
        counters = source.counter_count(grant.max_mana_value_counters) if source is not None else 0
        if card.mana_value > counters:
            return (
                f"{source_name} only applies to spells with mana value {counters} or less, "
                f"and {card.name} is {card.mana_value}"
            )
    if grant.type_word and not spell_has_type_word(card.card, grant.type_word):
        return f"{source_name} only applies to {grant.type_word} spells, and {card.name} is not one"
    if grant.max_mana_value is not None or grant.max_mana_value_quality is not None:
        cap = mana_value_cap_for(grant, game, caster)
        if cap is None:
            return (
                f"{source_name}'s mana value cap ({grant.max_mana_value_quality!r}) is not read "
                "by this engine (CR 118.9)"
            )
        if card.mana_value > cap:
            return (
                f"{source_name} only applies to spells with mana value {cap} or less, and "
                f"{card.name} is {card.mana_value}"
            )
    if grant.first_spell_each_players_turn:
        turn = getattr(game, "turn", None)
        if turn is None or turn.active_player != caster:
            return f"{source_name} applies only during your own turn (CR 118.9)"
        if game.spells_cast_this_turn.get(caster):
            return f"{source_name} only applies to the first spell you cast this turn (CR 118.9)"
    if grant.once_each_turn:
        used = getattr(game, "once_per_turn_cast_permissions_used", {})
        if grant.once_per_turn_key in used:
            return f"{source_name} was already used once this turn"
    if grant.once_each_of_your_turns:
        turn = getattr(game, "turn", None)
        if turn is None or turn.active_player != caster:
            return f"{source_name} applies only during your turns (CR 118.9)"
        used = getattr(game, "once_per_turn_cast_permissions_used", {})
        if grant.once_per_turn_key in used:
            return f"{source_name} was already used once this turn"
    return None


def spell_has_type_word(card: Card, type_word: str) -> bool:
    """Whether `card` has the card type a static grant names (CR 205.2b: a
    card with more than one type has all of them). "instant or sorcery" is
    CR 205.1's type list read as the disjunction it is - either will do."""
    type_line = (card.type_line or "").lower()
    words = [word for word in re.split(r"\s+(?:or|and)\s+", type_word.lower()) if word]
    return any(word in type_line for word in words)


# --------------------------------------------------------------------------
# Exiling a card now to cast it later (CR 116.2, CR 406.4)
# --------------------------------------------------------------------------


def annotate_exile(
    card: CardState, marker: ExileMarker, owner: str | None = None, game: Any = None
) -> CardState:
    """Record which pile of exile a card is in (CR 406.4).

    The turn number is taken from the game because every keyword that casts out
    of exile is gated on "a later turn" than the one the card arrived on -
    CR 702.170d says so for plot in as many words.
    """
    if card.zone is not Zone.EXILE:
        raise ValueError(f"{card.name} is in the {card.zone.value}, not in exile")
    card.exile_annotation = ExileAnnotation(
        marker=marker, owner=owner or card.controller, turn_exiled=_turn_number(game)
    )
    return card


def _marked_exile_cost(
    game: Any, card: CardState, player: str, cost: TotalCost, kind: str
) -> TotalCost:
    """`cost` after "Foretelling cards from your hand costs {1} less" and its
    plot twin (`machines/cost/abilities.py`, CR 601.2f)."""
    if game is None:
        return cost
    return TotalCost(
        mana=ability_cost_adjustment(game, player, card, cost.mana, kind=kind, from_zone=Zone.HAND),
        components=cost.components,
    )


class MarkedExile(EngineModel):
    """One of CR 116.2's exile-it-now, cast-it-later special actions.

    Three of them are modelled: plot (CR 116.2k, CR 702.170b), foretell
    (CR 116.2h, CR 702.143b), and suspend (CR 116.2f, CR 702.62a). All three
    pay a cost, move a card from hand to exile, and leave it in a named pile
    that a later `Casting` reads.

    CR 116.1: special actions do not use the stack, so nothing here touches it
    and nobody gets priority in the middle. The cost is still a cost, so it is
    paid through `CostPayment` and rewinds the same way (CR 733.1).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    card: CardState
    player: str
    marker: ExileMarker
    cost: TotalCost
    rule: str
    face_down: bool = False
    game: Any = Field(default=None, exclude=True, repr=False)
    payment: CostPayment | None = None
    taken: bool = False
    granted_ability_texts: tuple[str, ...] = ()
    """Foretell only: the "Foretell {cost}" line a static ability gave the card
    in hand (CR 702.143a - Dream Devourer's grant), stamped on it in exile so
    the later cast finds the cost it was given."""
    time_counters: int | None = None
    """Suspend only (CR 702.62a): the N of "Suspend N-[cost]", put on the card
    as `Counter.TIME` once it reaches exile. `None` for plot and foretell,
    which exile a card with no counters at all."""

    @classmethod
    def plot(cls, game: Any, card: CardState, player: str) -> "MarkedExile":
        """CR 116.2k: exile a card with plot from hand, paying its plot cost.

        CR 702.170a puts the timing on it - "Any time you have priority during
        your main phase while the stack is empty" - which is the same window as
        casting a sorcery, so `Game.can_cast_sorcery` answers it.
        """
        ability = _keyword(card.card, "plot")
        granted = library_top_plot_cost(game, card, player)
        if granted is not None:
            # CR 702.170f: the top card's granted plot functions from the
            # library, for its mana cost.
            printed = granted
        elif ability is None:
            raise ValueError(f"{card.name} has no plot ability (CR 702.170a)")
        elif card.zone is not Zone.HAND:
            raise ValueError(
                f"{card.name} is in the {card.zone.value}; plot exiles a card from "
                f"its owner's hand (CR 702.170a, CR 702.170f)"
            )
        else:
            printed = ability.cost or ""
        if game is not None and not game.can_cast_sorcery(player):
            raise ValueError(
                f"{player} can only plot during their own main phase with the stack "
                f"empty (CR 116.2k, CR 702.170a)"
            )
        cost = total_cost_for_phrase(printed) or TotalCost()
        cost = _marked_exile_cost(game, card, player, cost, "plot")
        return cls(
            card=card,
            player=player,
            marker=ExileMarker.PLOTTED,
            cost=cost.assign_payer(player),
            rule="CR 116.2k",
            game=game,
        )

    @classmethod
    def foretell(cls, game: Any, card: CardState, player: str) -> "MarkedExile":
        """CR 116.2h: pay {2} and exile a card with foretell from hand, face down.

        The {2} is the special action's cost, not the card's foretell cost -
        that one is what the card is later cast for (CR 702.143a). Getting the
        two the wrong way round would make Lupine Harbingers cost {4}{G}{G} to
        put away and {2} to cast.

        CR 116.2h allows it "any time they have priority during their turn", so
        unlike plot it is not restricted to a main phase or an empty stack.
        """
        granted = tuple(granted_zone_keyword_lines(game, card, "foretell"))
        if _keyword(card.card, "foretell") is None and not granted:
            raise ValueError(f"{card.name} has no foretell ability (CR 702.143a)")
        if (
            game is not None
            and game.turn is not None
            and game.turn.active_player != player
            and not foretell_any_turn(game, player)
        ):
            raise ValueError(f"{player} can only foretell during their own turn (CR 116.2h)")
        return cls(
            card=card,
            player=player,
            marker=ExileMarker.FORETOLD,
            cost=_marked_exile_cost(
                game, card, player, TotalCost.of(ManaCost.parse("{2}")), "foretell"
            ).assign_payer(player),
            rule="CR 116.2h",
            face_down=True,
            game=game,
            granted_ability_texts=() if _keyword(card.card, "foretell") else granted[:1],
        )

    @classmethod
    def suspend(
        cls, game: Any, card: CardState, player: str, x_value: int | None = None
    ) -> "MarkedExile":
        """CR 116.2f: exile a card with suspend from hand, paying its suspend cost.

        "'Suspend N-[cost]' means 'If you could begin to cast this card by
        putting it onto the stack from your hand, you may pay [cost] and
        exile it with N time counters on it. This action doesn't use the
        stack.'" (CR 702.62a). Unlike plot and foretell, the suspend cost
        *is* what is paid here - there is no separate cast-time cost the way
        foretell's {2} is distinct from its own printed cost, because CR
        702.62a's third ability later casts the card "without paying its mana
        cost" outright.

        CR 702.62c: "While determining if you could begin to cast a card with
        suspend, take into consideration any effects that would prohibit that
        card from being cast" - `why_cannot_cast_now`/`why_cannot_cast_
        restriction` are exactly that question (CR 117.1a's timing, CR
        611.1's flat prohibitions), and deliberately not CR 118.6's unpayable
        cost: CR 118.6 itself says "attempting to cast a spell ... that has
        an unpayable cost is a legal action" - only *paying* an unpayable
        cost is illegal - so Living End's blank mana cost does not block
        being suspended, which is the whole reason the special action exists
        for a card like it at all.
        """
        ability = _keyword(card.card, "suspend")
        if ability is None:
            raise ValueError(f"{card.name} has no suspend ability (CR 702.62a)")
        if card.zone is not Zone.HAND:
            raise ValueError(f"{card.name} is in the {card.zone.value}, not in hand (CR 116.2f)")
        refusal = why_cannot_cast_now(card, player, game) or why_cannot_cast_restriction(
            card, player, game
        )
        if refusal is not None:
            raise ValueError(
                f"{card.name} could not begin to be cast right now, so it cannot be "
                f"suspended: {refusal} (CR 116.2f, CR 702.62c)"
            )
        counters = ability.count
        if ability.count_is_x:
            # "Suspend X—{X}{3}{U}. X can't be 0.": the player announces X as
            # they suspend (CR 107.3a); it is the number of time counters and
            # the X in the cost (CR 107.3b).
            if x_value is None:
                raise ValueError(f"announce X to suspend {card.name} (CR 107.3a, CR 702.62a)")
            if x_value < (ability.count_minimum or 0):
                raise ValueError(f"{card.name}'s suspend X can't be 0 (CR 702.62a)")
            counters = x_value
        if counters is None:
            raise ValueError(f"{card.name}'s suspend count could not be read (CR 702.62a)")
        cost = total_cost_for_phrase(ability.cost or "") if ability.cost else TotalCost()
        if cost is None:
            raise ValueError(f"{card.name}'s suspend cost could not be read (CR 702.62a)")
        if ability.count_is_x:
            cost = cost.model_copy(update={"mana": cost.mana.with_x(counters)})
        return cls(
            card=card,
            player=player,
            marker=ExileMarker.SUSPENDED,
            cost=cost.assign_payer(player),
            rule="CR 116.2f",
            game=game,
            time_counters=counters,
        )

    def begin_paying(self) -> CostPayment:
        """Open the payment for the special action's cost (CR 601.2h shape)."""
        if self.payment is None:
            self.payment = CostPayment.for_total(
                self.cost,
                game=self.game,
                payer=self.player,
                # CR 106.6: foretelling's {2} is a spend a restriction may name.
                spend=ManaSpend.foretelling(self.card)
                if self.marker is ExileMarker.FORETOLD
                else None,
            )
        return self.payment

    def take(self) -> CardState:
        """Perform the action: the cost is paid, so the card goes to exile.

        CR 406.3: exiled cards are face up by default; foretell says face down,
        which is what `face_down` carries.

        Run under `Game._id_allocator_scope`: `_take_impl` mints
        `self.card`'s new `zone_change_stamp` (`CardState.move_to`, CR 400.7),
        which needs `self.game` and is always present by the time this runs -
        unlike `Casting.cast()`/`.cancel()`, nothing above dereferences
        `self.game` without a null check, so there is no pure-announcement
        path to branch on here.
        """
        with self.game._id_allocator_scope():
            return self._take_impl()

    def _take_impl(self) -> CardState:
        """The rest of `take` - see its own docstring for why it is split out."""
        payment = self.begin_paying()
        if payment.step is not CostStep.PAID:
            raise ValueError("the special action's cost has not been paid yet")
        if self.taken:
            raise ValueError(f"{self.card.name} has already been exiled")

        # CR 400.1: `self.card.zone` is whatever zone the special action names
        # (a hand for foretell and plot, and `SuspendActivation` can name the
        # battlefield), so the lift-out has to look in the shared zones too -
        # `Player.cards_in` covers only the player's own three and now refuses
        # a shared one outright rather than answering with an empty pile.
        self.game._take_out_of_every_zone(self.card)  # noqa: SLF001
        self.card.move_to(Zone.EXILE)
        self.game.exile.append(self.card)
        if self.face_down:
            self.card.turn_face_down()
        annotate_exile(self.card, self.marker, self.player, self.game)
        if self.granted_ability_texts:
            self.card.granted_ability_texts = self.granted_ability_texts
        if self.marker is ExileMarker.FORETOLD:
            # CR 702.143c: "foretelling a card" is this special action.
            self.game.emit(
                GameEvent(
                    event=ExtraTriggerEvent.FORETOLD,
                    subject_id=self.card.id,
                    subject_name=self.card.name,
                    subject_card=self.card.card,
                    player=self.player,
                )
            )
        if self.time_counters is not None:
            # CR 702.62a: "... exile it with N time counters on it."
            self.game.add_counters(self.card, Counter.TIME, self.time_counters)
        self.taken = True
        return self.card

    def cancel(self) -> None:
        """Rewind the cost, leaving the card where it was (CR 733.1).

        Run under `Game._id_allocator_scope` whenever there is a game:
        `CostPayment.rewind` can itself move a real card - undoing a
        sacrifice, discard, exile, or mill component's own `pay` - which
        mints that card's `zone_change_stamp` the same way `take`'s move
        does. `self.game` can be `None` here even though `take` never
        reaches this state with one missing, because a caller may build a
        `MarkedExile` and cancel it before ever calling `take`.
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


def remove_suspend_time_counter(game: Any, card: CardState) -> int:
    """CR 702.62a's second ability: "At the beginning of your upkeep, if this
    card is suspended, remove a time counter from it."

    CR 702.62b: "suspended" means "in the exile zone, has suspend, and has a
    time counter on it" - the intervening *if*. A card that fails any part of
    that (already cast, already left exile some other way, or already at
    zero counters) is left untouched and this returns its current count
    rather than raising, the same "the *if* was false, do nothing" shape
    `persist_return` already returns `None` for.

    **This is the resolution of a real triggered ability now, not a hand-driven
    helper.** `machines/keywords._suspend_abilities` writes CR 702.62a's second
    ability out as a `TriggeredAbility`, `Game.emit` offers every suspended
    card in exile as a source, and `_suspend_effect` calls this when the
    ability resolves. Both checks below therefore run for the third time by
    then - CR 603.4 refused the trigger if the card was not suspended, CR
    608.2a refused the resolution if it had stopped being - and they are kept
    because this is still callable directly: Greater Gargadon's printed
    "Sacrifice an artifact, creature, or land: Remove a time counter from this
    card" is an activated ability that takes one off outside any upkeep, and
    `machines/effects.py` calls straight in for it.

    Taking the *last* counter off raises CR 702.62a's own third trigger
    condition (`ExtraTriggerEvent.LAST_TIME_COUNTER_REMOVED`), so the free
    cast is offered from whichever of the two routes emptied the card - the
    upkeep trigger or Gargadon's sacrifice - rather than only from a caller
    that remembered to ask.
    """
    if not card.is_suspended:
        return card.counter_count(Counter.TIME)
    card.remove_counters(Counter.TIME, 1)
    remaining = card.counter_count(Counter.TIME)
    game.emit(
        GameEvent(
            event=ExtraTriggerEvent.TIME_COUNTER_REMOVED,
            subject_id=card.id,
            subject_name=card.name,
            subject_card=card.card,
            player=card.owner,
        )
    )
    if remaining == 0:
        game.emit(
            GameEvent(
                event=ExtraTriggerEvent.LAST_TIME_COUNTER_REMOVED,
                subject_id=card.id,
                subject_name=card.name,
                subject_card=card.card,
                player=card.owner,
            )
        )
    return remaining


def finish_suspend(game: Any, card: CardState) -> CardState | None:
    """CR 702.62a's third ability: once the last time counter comes off a
    suspended card, its owner may cast it without paying its mana cost.

    "'When the last time counter is removed from this card, if it's exiled,
    you may play it without paying its mana cost if able. If you don't, it
    remains exiled. If you cast a creature spell this way, it gains haste
    until you lose control of the spell or the permanent it becomes.'" The
    player that "you" names is the card's **owner** (CR 108.3): CR 109.5 says
    "you" on an object with no controller is its owner, and a card in exile
    has no controller at all, so a card another player exiled with time
    counters (Suspended Sentence) still comes off suspend into its owner's
    hands. `ExileAnnotation.owner` is only the fallback.

    The intervening *if* ("if it's exiled") is read against the card's
    *current* zone (CR 603.10). The cast is made while this ability resolves
    (CR 608.2g, CR 702.62d's alternative cost) through `Game.
    may_cast_during_resolution`, labelled "Suspend" so CR 702.62a's haste is
    granted as the creature enters (`Game._create_resolution_delayed_triggers`).
    Declining, or a cast that is not legal, is "If you don't, it remains
    exiled." Returns the spell cast, or `None`.
    """
    if card.zone is not Zone.EXILE:
        return None
    if not card.has_suspend:
        # CR 702.62b is broader than the suspend special action's own marker:
        # a card exiled with time counters by something else has the ability.
        return None
    if card.counter_count(Counter.TIME) > 0:
        return None
    annotation = card.exile_annotation
    owner = card.owner or (annotation.owner if annotation else None) or game.active_player.username
    return game.may_cast_during_resolution(
        card,
        owner,
        prompt=f"cast {card.name} without paying its mana cost (suspend)",
        source=card.name,
        source_id=source_id_of(card),
        source_name=f"{card.name}'s suspend",
        rule="CR 702.62a",
        keyword="Suspend",
    )


def exile_warped(game: Any, permanent: CardState) -> CardState:
    """Perform warp's delayed triggered ability by hand (CR 702.185a, CR 603.7).

    "Warp represents two static abilities that function while the card with warp
    is on the stack, one of which may create a delayed triggered ability." That
    delayed ability exiles the permanent at the beginning of the next end step,
    and CR 702.185b then calls it a warped card in exile.

    Delayed triggered abilities are not modelled (CR 603.7), so nothing fires
    this on its own. A scenario calls it, the way scenarios call the combat
    turn-based actions the turn machine does not perform.
    """
    game.exile_permanent(permanent)
    return annotate_exile(permanent, ExileMarker.WARPED, permanent.controller, game)


def exile_adventured(game: Any, spell: CardState, owner: str | None = None) -> CardState:
    """Perform CR 715.3d by hand: exile a resolved Adventure instead of binning it.

    "Instead of putting a spell that was cast as an Adventure into its owner's
    graveyard as it resolves, its controller exiles it. For as long as that card
    remains exiled, that player may play it."

    A replacement effect on resolution, and `Game.resolve_top` has no hook for
    one, so a scenario applies it itself.
    """
    with game._id_allocator_scope():  # noqa: SLF001
        player = game.player(owner or spell.controller)
        # Both halves of what this used to spell out by hand, and shared-zone
        # safe: `Player.cards_in(spell.zone)` refuses a shared zone now
        # (CR 400.1), and a resolving Adventure is on the stack, which is one.
        game._take_out_of_every_zone(spell)  # noqa: SLF001
        spell.move_to(Zone.EXILE)
        game.exile.append(spell)
        return annotate_exile(spell, ExileMarker.ADVENTURED, player.username, game)


from ..aftermath import aftermath_face_only_refusal, aftermath_face_refusal  # noqa: E402
from ..face_down_keywords import library_top_plot_cost  # noqa: E402
from ._common import (  # noqa: E402
    _BLIGHT_PHRASE,
    _OPTIONAL_BEHOLD,
    _OPTIONAL_BEHOLD_CHOSEN_TYPE,
    _OPTIONAL_COLLECT_EVIDENCE,
    _OPTIONAL_EXILE_ANY_NUMBER_FROM_HAND,
    _OPTIONAL_REVEAL,
    _OPTIONAL_SACRIFICE_ANY_NUMBER,
    _OPTIONAL_WATERBEND,
    BARGAIN_COST,
    CONSPIRE_COST,
)
from .options import (  # noqa: E402
    AlternativeCostSource,
    _describe_keyword_cost,
    _keyword,
    _matches_splice_quality,
    _primary_alternatives_of,
    _printed_alternative_total_cost,
    _splice_parameter,
    _spliced_rules_text,
    _turn_number,
    beam_refusal,
    casualty_cost_phrase,
    conditional_alternative_cost_offers,
    keyword_cast_options,
    kicker_costs,
    mandatory_additional_costs,
    marker_cast_options,
    or_additional_cost_halves,
    printed_condition_refusal,
    with_keyword_spell_ability_target,
)
from .permissions import (  # noqa: E402
    adventure_face,
    cast_condition_holds,
    castable_faces,
    castable_from,
    conditional_flash_condition,
    conditional_free_cast_condition,
    conditional_free_cast_unavailable,
    flash_surcharge,
    granted_cast_options,
    has_flash,
    has_quality_flash_grant,
    is_top_of_library,
    modal_dfc_spell_back_faces,
    once_per_turn_key,
    play_permissions_on,
    printed_cast_only_zones,
    split_second_restriction_source,
    usable_play_permission,
)
