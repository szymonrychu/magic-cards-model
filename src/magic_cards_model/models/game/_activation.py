import re
from collections.abc import Sequence
from functools import cache
from typing import TYPE_CHECKING, Any

from ...machines.abilities import (
    AbilityKind,
    ActivatedAbility,
    CostKind,
    TriggerEvent,
    one_named_color,
    parse_abilities,
    resolve_mana_count_expression,
    self_normalized_effect_text,
    self_reference_names,
)
from ...machines.casting import (
    split_second_restriction_source,
)
from ...machines.casting_restrictions import (
    combat_lockdown_restriction_source,
    loyalty_activation_restriction,
)
from ...machines.combat import (
    Keyword,
    has_keyword,
)
from ...machines.cost import (
    ComponentKind,
    CostModifierNotice,
    CostPayment,
    CostStep,
    TotalCost,
    activated_ability_group_discount_effect,
    among_colors,
    announce_count,
    announce_reveal,
    cost_announces_x,
    cost_component_for_phrase,
    discard_cost,
    exile_cost,
    increase,
    is_creature_source,
    is_treasure_source,
    loyalty_cost,
    sacrifice_cost,
    spend_restriction,
    tap_cost,
    total_cost_for_phrase,
    untap_cost,
)
from ...machines.cost.abilities import ability_cost_adjustment
from ...machines.decisions import (
    source_id_of,
)
from ...machines.effects import (
    devotion_to,
    modal_trigger_profile,
)
from ...machines.ep02_r1_counter_amounts import counters_self_reference_normalised
from ...machines.equip_block_statics import additional_loyalty_cost, loyalty_activation_limit
from ...machines.keywords import (
    ACTIVATED_EXHAUST_FACT,
    exhaust_reactivation_allowed,
    morph_ability,
    turn_face_up_ban,
    turn_face_up_cost,
    why_cannot_turn_face_up,
)
from ...machines.layers import (
    CANT_ACTIVATE_ABILITIES_TEXT,
)
from ...machines.modes import (
    substitute_x,
    x_restriction_refusal,
)
from ...machines.replacement import (
    replace_mana_production,
)
from ...machines.special_actions import (
    unlock_cost,
    why_cannot_turn_face_up_as,
    why_cannot_unlock_door,
    why_cannot_unlock_door_as,
)
from ...machines.targeting import (
    profile_for_text,
)
from ...machines.triggers import (
    AbilityOnStack,
    ExtraTriggerEvent,
    GameEvent,
    activated_abilities_from_lines,
    activated_abilities_of,
    added_ability_lines,
    granted_activated_abilities_of,
    mana_ability_activated_event,
    mana_added_event,
    rewritten_ability_lines,
    tapped_for_mana_event,
)
from ...machines.turn import (
    MAIN_PHASES,
    Phase,
    Step,
)
from ...numbers import MULTIPLIER, parse_multiplier
from ..card import (
    Color,
    Supertype,
    Type,
)
from ..card_state import (
    CardState,
    ChoiceKind,
    Counter,
    TargetRef,
)
from ..mana import ManaCost, ManaSpend, ManaSpendEffect
from ..zone import Zone
from .records import ActivationInstructions, ActivationProhibition

if TYPE_CHECKING:
    from . import Game


_SACRIFICE_OR_DISCARD = re.compile(
    r"^sacrifice (?P<sacrifice>[\w ,]+?) or discard (?P<discard>[\w ,]+)$", re.IGNORECASE
)

#: "Sacrifice a Swamp and a Forest" (Jarad, Golgari Lich Lord): one cost
#: piece naming two objects of different qualities - two sacrifices, each
#: paid by an object with its own quality (CR 118.3).
_SACRIFICE_A_AND_A = re.compile(
    r"^sacrifice (?P<first>(?:an?|one) [\w-]+) and (?P<second>(?:an?|one) [\w-]+)$",
    re.IGNORECASE,
)


#: CR 602.1b: activation instructions "may state which players can activate
#: that ability, may restrict when a player can activate the ability, or may
#: define some aspect of the activation cost". Each instruction sentence opens
#: with who may activate ("Only your opponents may activate this ability",
#: "Any player may activate this ability") or with "Activate [this ability]"
#: itself, and then lists its restrictions joined by "and"/"but".
_WHO_MAY_ACTIVATE = re.compile(
    r"(?P<who>only your opponents|any player) may activate this ability(?P<rest>.*)",
    re.IGNORECASE,
)
#: CR 602.1b's "may define some aspect of the activation cost": Heirloom Epic's
#: "For each mana in this ability's activation cost, you may tap an untapped
#: creature you control rather than pay that mana." The tap is an alternative
#: way to pay each mana of the cost (CR 601.2h via CR 602.2b), made while the
#: ability is activated (`CostPayment.tap_creatures_for_mana`).
_TAP_CREATURES_FOR_MANA = re.compile(
    r"for each mana in this ability's activation cost, you may tap an untapped creature "
    r"you control rather than pay that mana",
    re.IGNORECASE,
)
_ACTIVATE_LEAD = re.compile(
    r"activate (?:this ability )?(?P<rest>(?:only|no more than)\b.*)", re.IGNORECASE
)
#: Where one restriction of a sentence ends and the next begins: "... and only
#: once each turn", "... but only if ...".
_RESTRICTION_JOIN = re.compile(r",?\s*\b(?:and|but)\s+(?=(?:only|no more than)\b)", re.IGNORECASE)
_RESTRICTION_PER_TURN = re.compile(
    rf"(?:only|no more than) (?P<times>{MULTIPLIER}) each turn", re.IGNORECASE
)
_RESTRICTION_ONCE = re.compile(r"only once", re.IGNORECASE)
_RESTRICTION_SORCERY = re.compile(
    r"only (?:as a sorcery|any time you could cast a sorcery)", re.IGNORECASE
)
#: CR 602.5e: "Activate only as an instant" means only that the player must
#: have priority - true of every activation this engine offers.
_RESTRICTION_INSTANT = re.compile(
    r"only (?:as an instant|any time you could cast an instant)", re.IGNORECASE
)
_RESTRICTION_IF = re.compile(r"only if (?P<condition>.+)", re.IGNORECASE)
_RESTRICTION_DURING = re.compile(r"only during (?P<window>.+)", re.IGNORECASE)

#: The steps an "Activate only during ... step" instruction names, by the name
#: CR 500.1's turn structure gives them.
_STEP_NAMES: dict[str, Step] = {
    "untap": Step.UNTAP,
    "upkeep": Step.UPKEEP,
    "draw": Step.DRAW,
    "beginning of combat": Step.BEGINNING_OF_COMBAT,
    "declare attackers": Step.DECLARE_ATTACKERS,
    "declare blockers": Step.DECLARE_BLOCKERS,
    "combat damage": Step.COMBAT_DAMAGE,
    "end of combat": Step.END_OF_COMBAT,
    "end": Step.END_STEP,
    "cleanup": Step.CLEANUP,
}
_ACTIVATION_WINDOW = re.compile(
    r"(?:(?P<whose>your|an opponent's|each opponent's|each player's|each|the) )?"
    r"(?:(?P<turn>turn)|(?P<combat>combat)"
    r"|(?:(?P<main>precombat|postcombat) )?(?P<main_phase>main phase)"
    rf"|(?P<step>{'|'.join(sorted(_STEP_NAMES, key=len, reverse=True))})(?: step)?)",
    re.IGNORECASE,
)


@cache
def read_activation_instructions(instructions: str | None) -> ActivationInstructions:
    """`instructions` (`ActivatedAbility.instructions`, CR 602.1b) read into
    `ActivationInstructions`. Text only - a condition's truth is asked later,
    against a game, by `Game.activation_instruction_refusal`."""
    who = "controller"
    sorcery = once = taps_creatures_for_mana = False
    per_turn: int | None = None
    per_turn_text: str | None = None
    windows: list[str] = []
    conditions: list[str] = []
    unread: list[str] = []
    for sentence in re.split(r"(?<=\.)\s+", (instructions or "").strip()):
        sentence = sentence.strip().rstrip(".").strip()
        if not sentence:
            continue
        rest: str
        if _TAP_CREATURES_FOR_MANA.fullmatch(sentence):
            taps_creatures_for_mana = True
            continue
        if match := _WHO_MAY_ACTIVATE.fullmatch(sentence):
            who = "opponents" if match.group("who").lower() == "only your opponents" else "any"
            rest = match.group("rest")
        elif match := _ACTIVATE_LEAD.fullmatch(sentence):
            rest = match.group("rest")
        else:
            unread.append(sentence)
            continue
        for piece in _RESTRICTION_JOIN.split(rest.strip()):
            piece = piece.strip()
            if not piece:
                continue
            if limit := _RESTRICTION_PER_TURN.fullmatch(piece):
                per_turn = parse_multiplier(limit.group("times")) or 1
                per_turn_text = piece
            elif _RESTRICTION_ONCE.fullmatch(piece):
                once = True
            elif _RESTRICTION_SORCERY.fullmatch(piece):
                sorcery = True
            elif _RESTRICTION_INSTANT.fullmatch(piece):
                pass
            elif during := _RESTRICTION_DURING.fullmatch(piece):
                if _ACTIVATION_WINDOW.fullmatch(during.group("window")) is None:
                    unread.append(f"Activate {piece}")
                else:
                    windows.append(during.group("window"))
            elif only_if := _RESTRICTION_IF.fullmatch(piece):
                conditions.append(only_if.group("condition").strip())
            else:
                unread.append(f"Activate {piece}")
    return ActivationInstructions(
        who=who,
        sorcery=sorcery,
        per_turn=per_turn,
        per_turn_text=per_turn_text,
        once=once,
        windows=tuple(windows),
        conditions=tuple(conditions),
        taps_creatures_for_mana=taps_creatures_for_mana,
        unread=tuple(unread),
    )


def _activation_home_zone(card: CardState) -> Zone:
    """The zone an activated ability with no zone of its own functions in (CR
    113.6): "Abilities of an instant or sorcery spell usually function only while
    that object is on the stack. Abilities of all other objects usually function
    only while that object is on the battlefield." (Lightning Storm's discard
    ability.)"""
    if card.zone is not Zone.BATTLEFIELD and {Type.INSTANT, Type.SORCERY} & set(card.card.types):
        # Off the battlefield only: a modal double-faced card's land face is a permanent
        # whose printed front face is a sorcery (Shatterskull Smashings).
        return Zone.STACK
    return Zone.BATTLEFIELD


#: "You may activate loyalty abilities of `<subject>` on any player's turn
#: any time you could cast an instant." printed as a permanent's own static
#: ability (CR 604.2) - Teferi, Master of Time's own self-reference. The
#: identical sentence `machines.effects._LOYALTY_INSTANT_SPEED_RE` reads for
#: a *resolving* grant (Jace's Machinations); this is that same wording read
#: directly off the battlefield instead, since a static ability needs no
#: resolution record at all.
_LOYALTY_INSTANT_SPEED_STATIC_RE = re.compile(
    r"you may activate loyalty abilities of (?P<subject>.+?) on any player'?s turn any time "
    r"you could cast an instant",
    re.IGNORECASE,
)
#: The same permission printed with a pronoun for its own subject and, on The
#: Wandering Emperor, a condition in front: "As long as The Wandering Emperor
#: entered this turn, you may activate her loyalty abilities any time you could
#: cast an instant." Read off the permanent's own static line after its name
#: has become "this permanent" (`self_normalized_effect_text`), so the
#: condition is one `Game.condition_holds` already reads ("this permanent
#: entered this turn", `_CONDITION_SELF_ENTERED_THIS_TURN`). "her/his/its/
#: their" is the permanent itself (CR 606.3 is per permanent), never another.
_SELF_LOYALTY_INSTANT_SPEED_RE = re.compile(
    r"^(?:as long as (?P<condition>[^,]+), )?you may activate (?:her|his|its|their) loyalty "
    r"abilities (?:on any player'?s turn )?any time you could cast an instant\.?$",
    re.IGNORECASE,
)


#: Urza, Planeswalker's own static, read once its name has become "this
#: permanent" (`self_normalized_effect_text`).
_LOYALTY_TWICE_RE = re.compile(
    r"^you may activate the loyalty abilities of (?:this permanent|\w+) twice each turn "
    r"rather than only once\.?$",
    re.IGNORECASE,
)


def _activation_condition(instructions: str) -> str | None:
    """The condition of an "Activate only if <condition>" restriction (CR
    602.5b), without a trailing "and only as a sorcery"-style second
    restriction, or None when the ability prints none - wherever in the
    sentence the "only if" sits ("Activate only once each turn and only if
    ...", "Any player may activate this ability but only if ...")."""
    found = read_activation_instructions(instructions).conditions
    return found[0] if found else None


#: A static ability that stops other permanents' activated abilities from being
#: activated at all - Karn, the Great Creator's "Activated abilities of artifacts
#: your opponents control can't be activated."
#:
#: CR 611.1: "A continuous effect modifies characteristics of objects, modifies
#: control of objects, or affects players or **the rules of the game**, for a
#: fixed or indefinite period." This shape is the last of those three: it changes
#: no characteristic, so `machines/layers.py` has nothing to write - CR 613's
#: layers are for characteristics, control, and copiable values - and the effect
#: is felt where the rules ask whether an activation is legal, which is CR 602.5:
#: "A player can't begin to activate an ability that's prohibited from being
#: activated." CR 604.2 and CR 611.3b bound it to while its source is on the
#: battlefield, which is why `_activation_prohibition` reads the battlefield
#: fresh every time rather than caching anything (CR 611.3a: not "locked in").
#:
#: The optional "unless they're mana abilities" tail is Damping Matrix's
#: wording. Pithing Needle and Disruptor Flute print the same tail but name the
#: ability's *source by chosen name* rather than by quality, which is
#: `_CHOSEN_NAME_PROHIBITION_RE`'s shape below.
_ACTIVATION_PROHIBITION_RE = re.compile(
    r"^activated abilities of (?P<subjects>[a-z, ]+?)"
    r"(?P<opponents> your opponents control)?"
    r" can't be activated(?P<mana_exempt> unless they're mana abilities)?\.?$",
    re.IGNORECASE,
)

#: A sentence that prohibits activation but is not the shape above - matched
#: only to fail closed with a notice rather than let it read as permission.
_LOOKS_LIKE_ACTIVATION_PROHIBITION_RE = re.compile(
    r"^activated abilities of .+ can't be activated", re.IGNORECASE
)


#: "You may activate abilities of creatures you control as though those
#: creatures had haste." - Tyvar, Jubilant Brawler's and Shang-Chi, Master of
#: Kung Fu's shared static, the two printings carrying this sentence in the
#: pool. Read as a shape, not by name.
#:
#: CR 609.4: "Some effects state that a player may do something 'as though'
#: some condition were true or a creature can do something 'as though' some
#: condition were true. This applies only to the stated effect. For purposes
#: of that effect, treat the game exactly as if the stated condition were
#: true. For all other purposes, treat the game normally." The stated effect
#: here is *activating abilities*, so exactly one of haste's two clauses is
#: borrowed - CR 702.10c, "its controller can activate its activated abilities
#: whose cost includes the tap symbol or the untap symbol even if that creature
#: hasn't been controlled by that player continuously since their most recent
#: turn began" - and CR 702.10b's attacking clause is not. The creature does
#: not gain the haste keyword either, so `machines/combat.py`'s `has_keyword`
#: reads nothing new off the computed board and `can_attack` still refuses.
#:
#: Like `_ACTIVATION_PROHIBITION_RE` this is a continuous effect that affects
#: the rules of the game rather than any object's characteristics (CR 611.1),
#: so `machines/layers.py` has nothing to write for it (CR 613.11) and the
#: battlefield is rescanned on every call instead of the answer being cached
#: (CR 611.3a: not "locked in").
#:
#: "Creatures you control" is the whole subject vocabulary read here, with
#: CR 613's usual "other" exclusion allowed for. A qualified subject - a
#: subtype, a colour, a count gate - is a subject reader this file does not
#: have (`machines/layers.py` owns that one, for anthems, and its selectors
#: are written against a computed `Board` rather than a single permanent), so
#: such a sentence fails closed through
#: `_LOOKS_LIKE_HASTE_ACTIVATION_PERMISSION_RE` below with a `LayerNotice`
#: rather than being granted to every creature its controller has.
_HASTE_ACTIVATION_PERMISSION_RE = re.compile(
    r"^you may activate abilities of (?P<other>other )?creatures you control "
    r"as though (?:those creatures|they) had haste\.?$",
    re.IGNORECASE,
)

#: A sentence that grants activation "as though ... haste" but is not the shape
#: above - matched only to fail closed with a notice rather than let it read as
#: silence, the mirror of `_LOOKS_LIKE_ACTIVATION_PROHIBITION_RE`. A permission
#: this engine cannot read costs a legal activation rather than allowing an
#: illegal one, which is why it is recorded instead of guessed at.
_LOOKS_LIKE_HASTE_ACTIVATION_PERMISSION_RE = re.compile(
    r"^you may activate\b.*\bas though\b.*\bhaste\b", re.IGNORECASE
)


#: Pithing Needle's, Disruptor Flute's and Phyrexian Revoker's "Activated
#: abilities of sources with the chosen name can't be activated [unless they're
#: mana abilities]." - the subject named by CR 614.12a's recorded choice
#: (`CardState.choice`, a card name per CR 201.4) rather than by a quality.
#: CR 109.2c: "source" means a source "in any zone", so unlike the card-type
#: shape above this one reaches a named card's cycling in a hand too.
_CHOSEN_NAME_PROHIBITION_RE = re.compile(
    r"^activated abilities of sources with the chosen name can't be activated"
    r"(?P<mana_exempt> unless they're mana abilities)?\.?$",
    re.IGNORECASE,
)

#: Scheming Fence's "Activated abilities of the chosen permanent can't be
#: activated." - the subject named by an "as this enters, you may choose a
#: nonland permanent" choice (`ChoiceKind.OBJECT`, the permanent's id).
_CHOSEN_PERMANENT_PROHIBITION_RE = re.compile(
    r"^activated abilities of the chosen permanent can't be activated\.?$", re.IGNORECASE
)

#: Any other "the chosen ..." subject names a choice this reader does not
#: record; it is left to the reader that owns that choice rather than guessed
#: at here.
_CHOSEN_NAME_SUBJECT_RE = re.compile(r"\bthe chosen\b", re.IGNORECASE)


def reads_activation_rule_line(
    text: str, card_name: str | None = None, *, legendary: bool = True
) -> bool:
    """Whether a permanent's static line is one of the activation-legality
    shapes this module reads (CR 602.5, CR 609.4, CR 609.4b, CR 606.3): an
    activation prohibition by card type or by chosen name, an "as though ...
    haste" activation permission, a loyalty-timing permission, or a "spend
    mana as though it were mana of any color to activate" permission - the
    line `support.py` credits as handled only because one of these readers
    actually enforces it. `card_name` lets a self-named line (The Wandering
    Emperor's) be read the way `Game._self_loyalty_instant_speed` reads it."""
    line = text.strip()
    if card_name is not None:
        normalized = self_normalized_effect_text(card_name, line, legendary=legendary)
        if _SELF_LOYALTY_INSTANT_SPEED_RE.match(normalized):
            match = _SELF_LOYALTY_INSTANT_SPEED_RE.match(normalized)
            condition = match.group("condition") if match is not None else None
            return condition is None or condition_is_readable(condition)
    if (
        _CHOSEN_NAME_PROHIBITION_RE.match(line)
        or _CHOSEN_PERMANENT_PROHIBITION_RE.match(line)
        or _parse_activation_prohibition(line)
    ):
        return True
    if _HASTE_ACTIVATION_PERMISSION_RE.match(line):
        return True
    if _LOYALTY_INSTANT_SPEED_STATIC_RE.search(line) or _SELF_LOYALTY_INSTANT_SPEED_RE.match(line):
        return True
    sentences = [part for part in re.split(r"(?<=\.)\s+", line) if part]
    return bool(sentences) and all(
        _SPEND_AS_ANY_COLOR_TO_ACTIVATE_RE.match(sentence)
        or _SPEND_AS_ANY_COLOR_STATIC_RE.match(sentence)
        for sentence in sentences
    )


def _parse_activation_prohibition(text: str) -> ActivationProhibition | None:
    """Read one static ability sentence as an activation prohibition, or None.

    The subject list is a plain "A, B, and C" of card-type plurals; anything
    else - a chosen name, a quality that is not a card type - comes back None
    and is recorded rather than guessed at.
    """
    match = _ACTIVATION_PROHIBITION_RE.match(text.strip())
    if match is None:
        return None
    subjects = match.group("subjects").lower().replace(" and ", ", ")
    words = [word.strip() for word in subjects.split(",") if word.strip()]
    if not words:
        return None
    if words == ["permanents"]:
        qualities: tuple[Type, ...] = ()
    else:
        types = [_card_type_named(word) for word in words]
        if any(card_type is None for card_type in types):
            return None
        qualities = tuple(card_type for card_type in types if card_type is not None)
    return ActivationProhibition(
        qualities=qualities,
        opponents_only=match.group("opponents") is not None,
        mana_abilities_exempt=match.group("mana_exempt") is not None,
    )


def _mana_list_spelling(text: str) -> str:
    """`{G}, {W}, or {U}` and `{G} or {W} or {U}` as one spelling."""
    return text.replace(", or ", " or ").replace(", ", " or ")


class ActivationMixin:
    def _loyalty_instant_speed_permitted(
        self: "Game", permanent: CardState, controller: str
    ) -> bool:
        """Whether something lets `controller` activate one of `permanent`'s
        loyalty abilities outside CR 606.3's ordinary sorcery-speed timing
        right now - either a resolved, possibly-bounded
        `LoyaltyInstantSpeedPermission` (Jace's Machinations' own "until end
        of turn" grant), or a permanent static ability printing the same
        sentence (Teferi, Master of Time's own self-reference - CR 604.2's
        static grant needs no resolution record at all, read straight off
        the controller's own battlefield the same way `attacker_cap_
        restriction`/`_zero_loyalty_exemption_controllers` already read
        their own static text)."""
        if self._self_loyalty_instant_speed(permanent):
            return True
        for permission in self.loyalty_instant_speed_permissions:
            if permission.player != controller:
                continue
            if permission.self_source_id is not None:
                if permission.self_source_id == permanent.id:
                    return True
                continue
            if permission.subtype is None:
                return True
            if permission.subtype.lower() in {subtype.lower() for subtype in permanent.subtypes}:
                return True
        short_name = permanent.name.split(",")[0].strip().lower()
        # CR 114.2: an emblem's own quoted ability "applies as though it
        # were printed on a permanent" (Teferi's Talent's/Teferi, Temporal
        # Archmage's own "-10/-12: You get an emblem with 'You may activate
        # loyalty abilities of planeswalkers you control ...'"). Read the
        # same way a battlefield permanent's own static text already is -
        # `Game.emblems_of` alongside `permanents_controlled_by`, not a
        # separate mechanism.
        for source in (*self.permanents_controlled_by(controller), *self.emblems_of(controller)):
            for sentence in re.findall(
                r"you may activate loyalty abilities of [^.]+?\.",
                source.class_ability_text,
                re.IGNORECASE,
            ):
                match = _LOYALTY_INSTANT_SPEED_STATIC_RE.search(sentence)
                if match is None:
                    continue
                if match.group("subject").strip().lower() == "planeswalkers you control":
                    return True
                subtype = match.group("subject").strip().lower()
                if subtype.endswith(" planeswalkers you control"):
                    if subtype[: -len(" planeswalkers you control")] in {
                        each.lower() for each in permanent.subtypes
                    }:
                        return True
                    continue
                if subtype == short_name and source.id == permanent.id:
                    return True
        return False

    def _self_loyalty_instant_speed(self: "Game", permanent: CardState) -> bool:
        """`permanent`'s own "[As long as <condition>, ]you may activate her
        loyalty abilities any time you could cast an instant." (The Wandering
        Emperor) - `_SELF_LOYALTY_INSTANT_SPEED_RE`.

        CR 604.2: the static ability applies while the permanent is on the
        battlefield and has it (`_still_has_static_line`), and its "as long
        as" condition is asked afresh every time (CR 611.3a) through
        `condition_holds` with the permanent itself as the condition's source.
        A condition that reader cannot read grants nothing and is recorded
        (`_record_unread_static_line`) rather than guessed at.
        """
        if permanent.zone is not Zone.BATTLEFIELD:
            return False
        legendary = Supertype.LEGENDARY in permanent.card.supertypes
        for line in parse_abilities(permanent.card):
            if line.kind is not AbilityKind.STATIC:
                continue
            text = (line.text or "").strip()
            normalized = self_normalized_effect_text(permanent.name, text, legendary=legendary)
            match = _SELF_LOYALTY_INSTANT_SPEED_RE.match(normalized)
            if match is None or not self._still_has_static_line(permanent, text):
                continue
            condition = match.group("condition")
            if condition is None:
                return True
            held = self.condition_holds(
                self.controller_of(permanent).username, condition, permanent
            )
            if held is None:
                self._record_unread_static_line(permanent, text)
                continue
            if held:
                return True
        return False

    def can_activate_tap_ability(self: "Game", permanent: CardState) -> bool:
        """Whether a `{T}` ability of this permanent may be activated (CR 302.6).

        Only creatures are affected: a land or an artifact taps the turn it
        arrives. Read off the computed board (CR 613.5), not the printed type
        line, so a permanent a continuous effect turned into a creature this
        turn - The Filigree Sylex after Karn, the Great Creator's +1 - is
        still held to the restriction: CR 302.6 asks how long the permanent
        has been controlled, not how long it has been a creature, so an
        artifact already on the battlefield before this turn began stays
        exempt the moment it becomes a creature, while one that entered and
        was animated in the same turn is held back. Haste turns the
        restriction off (CR 702.10c) - `has_keyword` is passed this `Game` too,
        so a haste granted by a continuous effect (layer 6) counts, not only
        one printed on the card. So does an effect that only says to treat the
        creature *as though* it had haste, without granting the keyword: see
        `activation_haste_permission` for why CR 609.4 makes that reach here
        and nowhere else.
        """
        if not self.characteristics_of(permanent).is_creature:
            return True
        if not permanent.summoning_sick or has_keyword(permanent, Keyword.HASTE, self):
            return True
        return self.activation_haste_permission(permanent) is not None

    def activation_haste_permission(self: "Game", permanent: CardState) -> str | None:
        """The permanent granting "activate ... as though it had haste", or None.

        CR 609.4: an "as though" effect applies **only to the stated effect**,
        and the stated effect on Tyvar, Jubilant Brawler and Shang-Chi, Master
        of Kung Fu is activating abilities - so this is consulted by
        `can_activate_tap_ability` (CR 302.6's first sentence, CR 702.10c) and
        by nothing else. `machines/combat.can_attack` deliberately does not
        call it: CR 302.6's second sentence and CR 702.10b are a different
        thing to be treated as true, and this sentence does not state it.

        Read off the printed static lines of everything on the battlefield on
        every call, never cached (CR 604.2, CR 611.3a), the same scan
        `_activation_prohibition` makes for the opposite direction, and gated
        on `_still_has_static_line` so a source that lost its abilities in
        layer 6 grants nothing (CR 613.1f).

        **Whose creatures.** "Creatures you control" - "you" is the *source's*
        controller (CR 109.5), so an opponent's Tyvar reaches nothing of yours.
        The subject has no "other" in it on either printing, which is why
        Shang-Chi may activate its own `{T}` the turn it arrives; the optional
        "other" is still read, because a printing that carries it would
        otherwise be granted a permission it does not print.

        A sentence of this family whose subject this file cannot read is
        recorded as a `LayerNotice` and grants nothing, rather than being
        rounded up to every creature its controller has.
        """
        for source in list(self.battlefield):
            for line in parse_abilities(source.card):
                if line.kind is not AbilityKind.STATIC:
                    continue
                text = (line.text or "").strip()
                if not _LOOKS_LIKE_HASTE_ACTIVATION_PERMISSION_RE.match(text):
                    continue
                match = _HASTE_ACTIVATION_PERMISSION_RE.match(text)
                if match is None:
                    self._record_unread_static_line(source, text)
                    continue
                if not self._still_has_static_line(source, text):
                    continue
                if self.controller_of(permanent).username != self.controller_of(source).username:
                    continue
                if match.group("other") is not None and permanent.id == source.id:
                    continue
                return source.name
        return None

    def _activated_index(self: "Game", ability: AbilityOnStack) -> int | None:
        source = ability.source(self)
        if source is None or source.card is None:
            return None
        # `self.activated_abilities` now, not `activated_abilities_of` on the
        # bare card directly - it is the one place printed and
        # `CardState.granted_ability_texts` abilities are already combined
        # (Urza's Saga chapter II's own granted token-making ability), and
        # this index has to agree with that same combined, ordered list or a
        # granted ability's index would disagree with the one `activate_
        # ability` used to put it on the stack in the first place.
        for index, printed in enumerate(self.activated_abilities(source)):
            if printed.text == ability.ability.text:
                return index
        return None

    def _ability_of_opponents_permanent(
        self: "Game", item: AbilityOnStack, player: str | None
    ) -> bool:
        """Whether `item` is an ability of a permanent an opponent of `player`
        controls - the scope of Elesh Norn's "abilities of permanents your
        opponents control"."""
        if item.source_id is None:
            return False
        source = self.find_by_id(item.source_id)
        if not isinstance(source, CardState) or source.zone is not Zone.BATTLEFIELD:
            return False
        return source.controller is not None and source.controller != player

    def unlock_door(
        self: "Game", permanent: CardState, door_name: str | None, *, controller: str | None = None
    ) -> bool:
        """CR 709.5f: give `permanent` the appropriate unlocked designation
        for the door named `door_name` (a face's own printed name).

        The one door-unlocking function every route runs through: `Game.
        enter_the_battlefield`'s own CR 709.5d (the half that was cast), CR
        709.5e's special action (`finish_unlocking_door`, after `begin_
        unlocking_door`'s payment; enumerated by `legal_actions.py` as
        `ActionKind.UNLOCK_DOOR`), and any future "unlock [it/the other
        door]" resolution effect (CR 709.5f) alike - so CR 709.5h's own
        trigger ("When you unlock this door") fires the same way regardless
        of which of those caused it. No legality check here: the special
        action's is `why_cannot_unlock_door`, and CR 709.5d/709.5f need none.

        CR 709.5c: "Otherwise, that half is said to be 'locked.'" Giving an
        already-unlocked door the designation again is a no-op - the
        permanent does not have two copies of the designation to have one
        taken away later, and CR 709.5h's trigger is for a door that is
        *given* the designation, not one that already had it.

        Returns whether the designation was actually given (False for a
        non-Room permanent, an unrecognised door name, one already
        unlocked, or a permanent not on the battlefield)."""
        if permanent.zone is not Zone.BATTLEFIELD or door_name is None:
            return False
        if "Room" not in permanent.subtypes:
            return False
        if door_name in permanent.unlocked_doors:
            return False
        permanent.unlocked_doors = (*permanent.unlocked_doors, door_name)
        self.emit(
            GameEvent(
                event=ExtraTriggerEvent.DOOR_UNLOCKED,
                subject_id=permanent.id,
                subject_name=door_name,
                player=controller or permanent.controller,
            )
        )
        return True

    # -- a Room's unlock cost (CR 709.5e, CR 116.2m) -------------------------

    def why_cannot_unlock_door(
        self: "Game", username: str, permanent: CardState, door: str
    ) -> str | None:
        """Why `username` cannot pay the unlock cost of `permanent`'s `door`
        right now (CR 709.5e), or None - legality only, never affordability
        (CR 118.6). See `machines/special_actions.why_cannot_unlock_door`."""
        return why_cannot_unlock_door(self, username, permanent, door)

    def why_cannot_unlock_door_as(
        self: "Game", username: str, permanent: CardState, door: str
    ) -> str | None:
        """`why_cannot_unlock_door` plus whether `username` can pay the
        unlock cost right now (CR 118.3) - the seat-facing refusal."""
        return why_cannot_unlock_door_as(self, username, permanent, door)

    def begin_unlocking_door(
        self: "Game", username: str, permanent: CardState, door: str
    ) -> CostPayment:
        """Announce CR 709.5e's special action and open the locked half's
        mana-cost payment. Same two-call split as `begin_bringing_companion_
        to_hand` (CR 116.1: paying can take more than one priority-free
        moment). Raises if the action is unavailable, before anything has
        been spent."""
        self._refuse_if_over()
        refusal = self.why_cannot_unlock_door(username, permanent, door)
        if refusal is not None:
            raise ValueError(refusal)
        return CostPayment.for_total(
            unlock_cost(permanent, door, self, username), game=self, payer=username
        )

    def finish_unlocking_door(
        self: "Game", username: str, permanent: CardState, door: str
    ) -> CardState:
        """Finish CR 709.5e: give `permanent` the unlocked designation for
        `door`, the cost having been paid through `begin_unlocking_door`.

        CR 116.1: a special action does not use the stack - but what it
        triggers does (CR 603.3): `unlock_door` emits the event CR 709.5h's
        "When you unlock this door" waits for, and `put_triggers_on_stack`
        puts that ability on the stack the next time a player would receive
        priority (CR 116.3: the player who took the action receives it)."""
        self._refuse_if_over()
        refusal = self.why_cannot_unlock_door(username, permanent, door)
        if refusal is not None:
            raise ValueError(refusal)
        with self._id_allocator_scope():
            self.unlock_door(permanent, door, controller=username)
        return permanent

    def become_monstrous(self: "Game", permanent: CardState, amount: int) -> bool:
        """CR 701.37a: "Monstrosity N" means "If this permanent isn't
        monstrous, put N +1/+1 counters on it and it becomes monstrous."

        Both refusals CR 701.37a states are silent no-ops, not errors - the
        activation that reads this is still legal either way (CR 701.37a is
        the *effect*, not a cost or a timing restriction; nothing in CR 602
        stops a permanent's controller activating a Monstrosity ability a
        second time): a permanent not on the battlefield any more by the
        time this resolves (CR 608.2a's own "the source is gone" case) gets
        nothing, and CR 701.37b's own second sentence - "Once a permanent
        becomes monstrous, it stays monstrous until it leaves the
        battlefield" - is what makes an already-monstrous permanent's second
        Monstrosity activation add no further counters and raise no second
        `TriggerEvent.BECOMES_MONSTROUS`, the same shape `become_prepared`
        above already gives CR 722.3a's identical "can't gain this
        designation if it already has it".

        Counters go through `Game.add_counters` (CR 122.6, replacement
        effects included - Doubling Season doubles a Monstrosity N the same
        way it doubles any other counter placement), and `monstrous`/
        `monstrous_x` are set only once the counters have actually landed,
        so a caller checking `permanent.monstrous` afterwards is checking
        the real outcome, not the printed N. CR 701.37c's own "other
        abilities of that permanent may also refer to X" is `monstrous_x`,
        read back by `_effect_for`'s own `BECOMES_MONSTROUS` branch below and
        by the emitted `GameEvent.amount` a triggered ability's own `event`
        carries.

        Returns whether the permanent became monstrous just now.
        """
        if permanent.zone is not Zone.BATTLEFIELD:
            return False
        if permanent.monstrous:
            return False
        with self._id_allocator_scope():
            if amount > 0:
                self.add_counters(permanent, Counter.PLUS_ONE, amount)
            permanent.monstrous = True
            permanent.monstrous_x = amount
            self.emit(
                GameEvent(
                    event=TriggerEvent.BECOMES_MONSTROUS,
                    subject_id=permanent.id,
                    subject_name=permanent.name,
                    subject_controller=permanent.controller,
                    subject_card=permanent.card,
                    subject_types=permanent.types,
                    subject_subtypes=permanent.subtypes,
                    player=permanent.controller,
                    amount=amount,
                )
            )
        return True

    # -- activated abilities (CR 602) --------------------------------------

    def activated_abilities(self: "Game", permanent: CardState) -> list[ActivatedAbility]:
        """Every activated ability this permanent has, printed then granted.

        CR 602.1: an activated ability is written `[Cost]: [Effect.]
        [Activation instructions (if any).]`. The index into this list is what
        `activate_ability` and `machines/effects.py` key on.

        Narrowed to the face that is up (CR 712.8d, 712.8e, 712.8f, CR 109.3):
        a transformed Ajani, Nacatl Pariah has his back face's `+2`, `0` and
        `−4` and nothing else, and Duskwatch Recruiter loses its `{2}{G}` look
        the moment it becomes Krallenhorde Howler. `_activated_index` reads the
        same face, so an ability's index stays the index of this list.

        Printed abilities come first, then `CardState.granted_ability_texts`'s
        own - Urza's Saga's chapter II grant ("This Saga gains '{2}, {T}:
        Create a 0/0 colorless Construct artifact creature token ...'") is the
        only source of these in the pool. Appending rather than interleaving
        keeps a printed ability's own index stable as more get granted.

        **CR 613.5 / CR 707.2**: when a continuous effect has rewritten the
        permanent's computed ability text away from the printed card - a layer 1
        copy effect is the only shape that does - the *computed* abilities are
        the ones it has, and the printed card is not consulted at all. A land
        that has become a copy of Sol Ring offers `{T}: Add {C}{C}` and nothing
        of its own. `rewritten_ability_lines` answers None for every permanent
        whose printed lines all survive, so an ordinary grant still appends and
        every printed ability's index stays where it was.
        """
        # Asked first: computing the board is what reconciles a conditional
        # static's quoted grant onto `granted_ability_texts` (CR 613.1f), so the
        # list is read only after it.
        rewritten = rewritten_ability_lines(self, permanent)
        granted = granted_activated_abilities_of(permanent.granted_ability_texts)
        if rewritten is not None:
            # A rewrite replaces the *printed* text, and nothing more. An
            # ability granted to this object by something that already resolved
            # is a separate continuous effect (CR 611.2) applied in layer 6
            # (CR 613.1f), which is after both layer 1's copy effects
            # (CR 613.2c) and layer 4's type changes (CR 613.1d) - so it is
            # still on the object however thoroughly the printed lines were
            # rewritten, and has to be appended here too.
            #
            # Urza's Saga under Blood Moon is the case that needs it: CR 305.7
            # sets its subtype to Mountain and takes away every ability its
            # rules text generated, leaving the computed line list as just the
            # Mountain's intrinsic "{T}: Add {R}" (CR 305.6) - but the "{T}: Add
            # {C}" and the Construct maker its chapters already granted are
            # untouched, so the land taps for {C} *or* {R} and still makes
            # tokens. Dropping the grants here made it a bare Mountain.
            base = activated_abilities_from_lines(rewritten, permanent.card, permanent.up_face_name)
            already = {ability.raw for ability in base}
            return base + [ability for ability in granted if ability.raw not in already]
        # An ability a continuous effect *added* without taking any printed one
        # away - the intrinsic "{T}: Add [mana symbol]" that comes with a basic
        # land type granted in layer 4 (CR 305.6, CR 613.1d), which is how
        # Urborg turns every land into a black source. Appended last so every
        # printed ability keeps the index it had.
        added = activated_abilities_from_lines(
            added_ability_lines(self, permanent), permanent.card, permanent.up_face_name
        )
        base = activated_abilities_of(permanent.card, permanent.up_face_name) + granted
        seen = {ability.raw for ability in base}
        return base + [ability for ability in added if ability.raw not in seen]

    def why_cannot_activate(
        self: "Game", permanent: CardState, index: int = 0, controller: str | None = None
    ) -> str | None:
        """Why this ability may not be activated right now, or None (CR 602.5).

        "A player can't begin to activate an ability that's prohibited from being
        activated." What is checked:

        - the permanent is on the battlefield and the player controls it
          (CR 602.1a, 602.2: only an object's controller may activate its
          abilities);
        - **CR 602.5a / 302.6** - a creature that has not been controlled since
          its controller's most recent turn began cannot activate an ability with
          `{T}` or `{Q}` in its cost, unless it has haste (CR 702.10c);
        - **CR 602.5b** - "Activate only once each turn" and its siblings.
        - **CR 602.5d** - "Activated abilities that read 'Activate only as a
          sorcery' mean the player must follow the timing rules for casting a
          sorcery spell, though the ability isn't actually a sorcery. The player
          doesn't actually need to have a sorcery card that they could cast."
          CR 307.5 spells out what those timing rules are: "the player must have
          priority, it must be during the main phase of their turn, and the
          stack must be empty", which is `can_cast_sorcery`.
        - **CR 606.3** - a loyalty ability carries its own, stricter timing:
          "any time they have priority and the stack is empty during a main
          phase of their turn, but only if no player has previously activated a
          loyalty ability of that permanent that turn". Same timing machinery
          as CR 307.5, but the once-per-turn half is per permanent - activating
          one of a planeswalker's loyalty abilities refuses all the others
          until the next turn.
        - **CR 606.6** - "A loyalty ability with a negative loyalty cost, taking
          into account any additional costs, can't be activated unless the
          permanent has at least that many loyalty counters on it." The
          counters are what `CardState.loyalty` reads (CR 306.5c).

        CR 602.5e's "Activate only as an instant" is not checked, because
        CR 304.5 makes it "only that the player must have priority" - which is
        already true of every activation here.

        CR 113.6's "abilities of all other objects usually function only while
        that object is on the battlefield" is the default, and an ability whose
        printed text names a different zone is refused here too - the zone
        `machines/abilities._activated_ability_zone` read off the text
        (`ActivatedAbility.zone`, with `zone_rule` naming which CR 113.6
        sub-rule put it there: CR 113.6b for "activate only from your
        graveyard", CR 113.6j for a cost that cannot be paid on the
        battlefield, CR 113.6m for an effect that moves the card out of a named
        zone). Both directions are checked: Gollum, Patient Plotter's
        graveyard-only ability is not activatable while Gollum is on the
        battlefield, and an ordinary battlefield ability is not activatable
        from anywhere else. Off-battlefield activation itself goes through
        `machines/keywords.off_battlefield_activation`, which checks the same
        zone - see `docs/engine-coverage.md`.

        A life payment in the cost is checked as well: **CR 119.4** - "If a cost
        or effect allows a player to pay an amount of life greater than 0, the
        player may do so only if their life total is greater than or equal to
        the amount of the payment" - with **CR 119.4b**'s "players can always
        pay 0 life" as the exemption. Paying down to exactly 0 is legal; losing
        the game at 0 life is a separate state-based action (CR 704.5a),
        checked when a player would next receive priority.
        """
        if self.is_over:
            return self.why_game_is_over()
        abilities = self.activated_abilities(permanent)
        if index >= len(abilities):
            return f"{permanent.name} has no activated ability number {index}"
        ability = abilities[index]
        controller = controller or self.controller_of(permanent).username

        if ability.zone is not None:
            # CR 113.6b/113.6j/113.6m, whichever `machines/abilities.py` read
            # off the printed text: an ability that functions in one named zone
            # does not exist to be activated from any other - checked before
            # the flat battlefield rule below so the refusal names the real
            # reason, "functions in the graveyard" rather than "not on the
            # battlefield", and so the battlefield itself is refused too,
            # which is DDR#970's Gollum sacrificing itself to its own
            # graveyard-only ability. The two are `elif`, not two independent
            # `if`s: once `ability.zone` names a zone, CR 113.6's flat
            # "usually only on the battlefield" default has already been
            # displaced by the sub-rule that put it somewhere else (CR
            # 113.6j/113.6m are each phrased as "functions from"/"functions
            # only in", not as an addition to the battlefield case) - so a
            # permanent correctly sitting in that zone must not *also* fail
            # the flat rule a moment later. That double gate is what made
            # Campus Crier's own "{1}, Exile this card from your graveyard:
            # Empower Jace 2." (and Seasoned Pyromancer's identically-shaped
            # ability, and Boseiju's Channel) refuse to activate through this
            # door even once `machines/abilities._activated_ability_zone`
            # correctly read their zone as the graveyard or the hand -
            # `test_self_referential_costs.py`'s own Seasoned Pyromancer and
            # Boseiju tests used to route around this gate by building and
            # paying the `TotalCost` directly instead; they no longer need to.
            # See `docs/engine-coverage.md`'s FRA S1 note (Campus Crier) -
            # this is the general fix that gap named but did not make; the
            # fix belongs here, not in one more keyword.
            if permanent.zone is not ability.zone:
                return (
                    f"{permanent.name}'s ability functions in the {ability.zone.value}, "
                    f"but it is in the {permanent.zone.value} ({ability.zone_rule})"
                )
        elif permanent.zone is not _activation_home_zone(permanent):
            home = _activation_home_zone(permanent)
            return f"{permanent.name} is in {permanent.zone.value}, not on the {home.value}"
        refused_activator = self._activator_refusal(permanent, ability, controller)
        if refused_activator is not None:
            return refused_activator
        if not self._still_has_ability(permanent, ability):
            # CR 602.2: activating is putting *its* activated ability on the
            # stack, so the object has to still have it. CR 613.1f applies
            # ability-removing effects in layer 6, and CR 613.5 has the result
            # apply instantly - a permanent that lost all abilities has nothing
            # left to activate, however plainly the card is printed.
            return (
                f"{permanent.name} no longer has that ability: it was removed by a "
                "continuous effect in layer 6 (CR 613.1f)"
            )

        prohibited = self._activation_prohibition(permanent, ability)
        if prohibited is not None:
            return prohibited
        from ...machines.attached_restrictions import enchanted_player_activation_prohibition

        barred = enchanted_player_activation_prohibition(
            self,
            controller,
            is_mana=ability.mana is not None,
            is_loyalty=ability.loyalty is not None,
        )
        if barred is not None:
            return barred

        if self.characteristics_of(permanent).has_ability(CANT_ACTIVATE_ABILITIES_TEXT):
            # A one-shot resolved effect's lock (Braided Net's own "Tap
            # another target nonland permanent. Its activated abilities
            # can't be activated for as long as it remains tapped."),
            # granted in layer 6 - distinct from `_activation_prohibition`'s
            # printed-static-text scan above, which this permanent's own
            # card may say nothing about at all (CR 602.5, CR 611.1).
            return (
                f"{permanent.name}'s activated abilities can't be activated: a resolved "
                "effect locked them (CR 602.5, CR 611.1)"
            )

        if ability.ability_word is not None and ability.ability_word.lower() == "max speed":
            # CR 702.178a: "'Max speed — [Ability]' means 'As long as your
            # speed is 4, this object has "[Ability]."'" Perilous Snare's
            # own Max speed ability, gated on the *activator's* speed
            # (CR 109.5's "you" in a static ability is the controller of the
            # object it's on) rather than a layer-6 ability grant/removal -
            # functionally the same result CR 613.1f's version would give,
            # since an object that does not have an ability cannot have it
            # activated (CR 602.5).
            from ...machines.speed import has_max_speed

            if not has_max_speed(self.player(controller)):
                return (
                    f"{permanent.name}'s Max speed ability can't be activated: "
                    f"{controller}'s speed is not 4 (CR 702.178a)"
                )

        if ability.loyalty is not None:
            from ...machines.static_cast_bans import activation_ban_reason

            locked_by_static = activation_ban_reason(self, permanent, controller, is_loyalty=True)
            if locked_by_static is not None:
                return locked_by_static
            # CR 602.5 / CR 606.3: a resolved "Your opponents can't ...
            # activate planeswalkers' loyalty abilities this turn" (Revel in
            # Silence), recorded on `casting_rule_effects` (CR 611.2c).
            locked = loyalty_activation_restriction(self, controller)
            if locked is not None:
                return (
                    f"{controller} can't activate loyalty abilities this turn: "
                    f"{locked.source_name} says so (CR 602.5, CR 606.3)"
                )

        if ability.mana is not None and ability.mana.unparsed_rider is not None:
            # CR 405.6c: "If a mana ability both produces mana and has
            # another effect, the mana is produced and the other effect
            # happens immediately." An effect this parser cannot read is not
            # one it can silently drop - the paragraph is one ability and it
            # resolves whole or not at all (see the mana ability rider row
            # in docs/engine-coverage.md), refused here, before any cost is
            # paid, rather than after `{T}` is already spent.
            return (
                f"{permanent.name}'s mana ability has an effect this engine cannot read "
                f"({ability.mana.unparsed_rider!r}), so it refuses to activate rather than "
                "silently dropping it (CR 405.6c)"
            )

        life_owed = 0
        for piece in ability.costs:
            if piece.kind is CostKind.PAY_LIFE:
                life = cost_component_for_phrase(piece.text, payer=controller)
                if life is None:
                    return (
                        f"{permanent.name}'s cost {piece.text!r} cannot be read, so it "
                        "refuses to activate rather than pay the wrong amount (CR 118.3)"
                    )
                # "Pay X life" owes 0 until X is announced (CR 119.4b), and the
                # announced amount is checked as the cost is paid.
                life_owed += life.amount
        if life_owed > 0 and (reason := game_rule_statics.life_total_cant_change(self, controller)):
            return f"{reason}, so {permanent.name}'s ability cannot be activated"
        if life_owed > 0 and self.player(controller).life < life_owed:
            # CR 119.4: an amount of life greater than 0 may be paid "only if
            # their life total is greater than or equal to the amount of the
            # payment" - CR 119.4b's "players can always pay 0 life" is why
            # only a positive amount is checked at all. Refused here, before
            # anything is announced, rather than at `CostPayment.pay` time:
            # an ability nobody can pay for is not one to offer.
            return (
                f"{controller} cannot pay {life_owed} life from a life total of "
                f"{self.player(controller).life}, so {permanent.name}'s ability "
                "cannot be activated (CR 119.4)"
            )

        for piece in ability.costs:
            # CR 118.3: "Remove an indestructible counter from Arwen" cannot be
            # paid by a permanent without one, so the ability is not offered -
            # the same check `CostPayment.pay` makes, made before announcing.
            removal = cost_component_for_phrase(piece.text, payer=controller)
            if (
                removal is None
                or removal.kind is not ComponentKind.REMOVE_COUNTERS
                or removal.from_among
                or removal.cards
                or removal.amount < 1
                or not _cost_refers_to_self(piece.text, permanent)
            ):
                continue
            refused = removal.model_copy(update={"cards": [permanent]}).why_not(self)
            if refused is not None:
                return f"{permanent.name}'s ability cannot be activated: {refused}"

        needs_tapping = any(piece.kind in {CostKind.TAP, CostKind.UNTAP} for piece in ability.costs)
        if needs_tapping and not self.can_activate_tap_ability(permanent):
            return (
                f"{permanent.name} has not been under {controller}'s control since their "
                "most recent turn began, so an ability with {T} in its cost cannot be activated"
            )

        if ability.loyalty is not None:
            # CR 606.3: "A player may activate a loyalty ability of a permanent
            # they control any time they have priority and the stack is empty
            # during a main phase of their turn, but only if no player has
            # previously activated a loyalty ability of that permanent that
            # turn." The timing half is CR 307.5's sorcery machinery; the
            # once-per-turn half is per permanent, so it is keyed by the
            # permanent alone, not by which ability was activated.
            #
            # Jace's Machinations' own "you may activate loyalty abilities of
            # Jace planeswalkers you control on any player's turn any time
            # you could cast an instant" (and Teferi, Master of Time's own
            # self-referential twin) loosens exactly this timing half, never
            # the once-per-turn one below - `_loyalty_instant_speed_permitted`
            # checked first, so a matching grant skips `can_cast_sorcery`
            # entirely rather than pretending the stack is empty when it may
            # not be.
            if not self._loyalty_instant_speed_permitted(
                permanent, controller
            ) and not self.can_cast_sorcery(controller):
                return (
                    f"{permanent.name}'s loyalty ability can only be activated during "
                    f"{controller}'s main phase, with the stack empty (CR 606.3)"
                )
            if self._loyalty_activation_count(permanent) >= max(
                self._loyalty_activations_allowed(permanent),
                loyalty_activation_limit(self, controller),
            ):
                return (
                    f"{permanent.name}'s loyalty abilities have already been activated "
                    "this turn (CR 606.3)"
                )
            removes = ability.loyalty.removes
            present = permanent.counter_count(Counter.LOYALTY)
            if removes and present < removes:
                # CR 606.6: "the permanent has at least that many loyalty
                # counters on it" - counters, not loyalty, so a planeswalker a
                # layer-4 effect made a plain creature (Kaito, Bane of
                # Nightmares on his own turn) still activates them.
                return (
                    f"{permanent.name} has {present} loyalty, not the {removes} "
                    f"its {ability.loyalty.printed} cost removes (CR 606.6)"
                )

        if ability.class_level_target is not None:
            # CR 716.2a: "[Cost]: Level N" means "[Cost]: This Class's level
            # becomes N. Activate only if this Class is level N-1 and only as
            # a sorcery" - both halves of that sentence, checked the same way
            # "Activate only as a sorcery" already is below for an ordinary
            # printed instruction, since this one is never actually printed
            # as words on the card.
            if not self.can_cast_sorcery(controller):
                return (
                    f"{permanent.name}'s Level {ability.class_level_target} bar can only be "
                    f"activated as a sorcery: {controller}'s main phase, with the stack empty "
                    "(CR 716.2a, CR 307.5)"
                )
            required = ability.class_level_target - 1
            if permanent.class_level != required:
                return (
                    f"{permanent.name} is level {permanent.class_level}, not level {required}, "
                    f"so its Level {ability.class_level_target} bar cannot be activated "
                    "(CR 716.2a)"
                )

        if (
            ability.exhaust
            and self._activation_key(permanent, index) in self.exhausted
            and not exhaust_reactivation_allowed(self, controller)
        ):
            return f"{permanent.name}'s exhaust ability has already been activated (CR 702.177a)"

        if ability.power_up:
            # CR 702.193a: "Activate this ability only once" - the exact same
            # never-cleared-per-turn restriction exhaust's own "Activate only
            # once" (CR 702.177a) already reads, so it reuses `exhausted`
            # rather than a second set (see `ActivatedAbility.power_up`),
            # widened by `_power_up_activations_used`/`_power_up_activation_
            # limit` for Wonder Man, Hollywood Hero's own "Each power-up
            # ability of permanents you control can be activated an
            # additional time."
            if self._power_up_activations_used(permanent, index) >= self._power_up_activation_limit(
                permanent
            ):
                return (
                    f"{permanent.name}'s power-up ability has already been activated (CR 702.193a)"
                )
            if self.turn.turns_taken in self.power_up_restricted_turns:
                # Kang the Conqueror's own rider: "During that turn,
                # power-up abilities can't be activated." - the turn is
                # whichever one this ability's own earlier activation
                # recorded in `power_up_restricted_turns`
                # (`_DURING_THAT_TURN_POWER_UP_RESTRICTED_RE`'s effect,
                # `machines/effects.py`), checked against the turn actually
                # under way right now.
                return (
                    f"{permanent.name}'s power-up ability can't be activated this turn "
                    "(CR 702.193a)"
                )

        if ability.mana is None:
            # CR 702.61a: "As long as this spell is on the stack, players
            # can't cast other spells or activate abilities that aren't mana
            # abilities." CR 605.1a: a mana ability's own activation is never
            # caught by this - `ability.mana` is set exactly when
            # `machines/abilities.py` read this line as one (`_ADD.match`).
            split_second_source = split_second_restriction_source(self)
            if split_second_source is not None:
                return (
                    f"{split_second_source} has split second: as long as it is on the "
                    f"stack, players can't activate abilities that aren't mana abilities "
                    "(CR 702.61a)"
                )
            combat_lockdown_source = combat_lockdown_restriction_source(self)
            if combat_lockdown_source is not None:
                return (
                    f"{combat_lockdown_source} says players can't activate abilities "
                    f"that aren't mana abilities during combat (CR 506.1)"
                )

        return self.activation_instruction_refusal(ability, permanent, controller, index=index)

    def _activator_refusal(
        self: "Game", permanent: CardState, ability: ActivatedAbility, activator: str
    ) -> str | None:
        """Why `activator` may not activate this ability at all, or None.

        CR 602.2: "Only an object's controller (or its owner, if it doesn't
        have a controller) can activate its activated ability unless the
        object specifically says otherwise", and CR 602.1b is where it says
        so - "Only your opponents may activate this ability" (Knight of the
        Holy Nimbus; "your" is the object's controller, CR 109.5) and "Any
        player may activate this ability" (Oona's Prowler).

        A card that is not a permanent or spell has no controller; CR 108.4a
        asks its owner instead - Cult Conscript's graveyard ability is its
        owner's to activate on any player's turn, not the active player's."""
        controller = (
            permanent.controller or permanent.owner or self.controller_of(permanent).username
        )
        who = read_activation_instructions(ability.instructions).who
        if who == "any":
            return None
        if who == "opponents":
            if activator == controller:
                return (
                    f"only {controller}'s opponents may activate {permanent.name}'s ability, "
                    f"and {controller} controls it (CR 602.1b)"
                )
            return None
        if controller != activator:
            return f"{activator} does not control {permanent.name}"
        return None

    def activation_instruction_refusal(
        self: "Game",
        ability: ActivatedAbility,
        source: CardState,
        activator: str,
        *,
        index: int | None = None,
    ) -> str | None:
        """Why the ability's own CR 602.1b activation instructions forbid
        `activator` from activating it right now, or None.

        Every instruction sentence is read (`read_activation_instructions`):

        - **when** - CR 602.5d/CR 307.5's "as a sorcery"; "during your turn",
          "during your upkeep", "during combat", "during the <name> step"
          (CR 602.1b "may restrict when a player can activate the ability"),
          checked against the turn machine, "your" being the activating
          player (CR 109.5);
        - **how often** - CR 602.5b's "only once each turn" / "no more than
          twice each turn", counted by `activations` per object and ability,
          and the never-reset "Activate only once", kept in `exhausted`;
        - **only if** - the condition, asked of `condition_holds` for the
          activating player.

        An instruction nothing here reads is refused with this engine's own
        reason rather than allowed unchecked, and so is a condition
        `condition_holds` cannot read. CR 602.5b: all of it "continues to
        apply to that object even if its controller changes" - which is why
        the counts are keyed by the object and ability, never the player.

        `index` is the ability's position in `activated_abilities(source)`,
        the key its per-turn and once-only counts are kept under; without it a
        counted restriction cannot be checked and is refused.
        """
        read = read_activation_instructions(ability.instructions)
        name = source.name
        for text in read.unread:
            return (
                f'{name}\'s activation instruction "{text}" is not read by this engine, so '
                "the activation is refused rather than allowed unchecked (CR 602.1b)"
            )
        if (read.per_turn is not None or read.once) and index is None:
            return (
                f"{name}'s ability is limited in how often it may be activated, and this "
                "activation has no count to check that against, so it is refused rather "
                "than allowed unchecked (CR 602.5b)"
            )
        if read.per_turn is not None and index is not None:
            # CR 602.5b: `activations` already counts every activation this
            # turn per object and ability, so the limit is only compared
            # against it. `MULTIPLIER` only matches what `parse_multiplier`
            # reads.
            count = self._activation_count(source, index)
            if read.per_turn == 1 and count:
                return f"{name}'s ability has already been activated this turn"
            if count >= read.per_turn:
                limit = _RESTRICTION_PER_TURN.fullmatch(read.per_turn_text or "")
                times = limit.group("times") if limit is not None else str(read.per_turn)
                return (
                    f"{name}'s ability has already been activated {times.lower()} this turn, "
                    f"the most {read.per_turn_text!r} allows (CR 602.5b)"
                )
        if (
            read.once
            and index is not None
            and self._activation_key(source, index) in self.exhausted
        ):
            return (
                f"{name}'s ability may be activated only once, and it already has been (CR 602.5b)"
            )
        if read.sorcery and not self.can_cast_sorcery(activator):
            return (
                f"{name}'s ability can only be activated as a sorcery: "
                f"{activator}'s main phase, with the stack empty "
                f"(CR 602.5d, CR 307.5)"
            )
        if (ability.ability_word or "").lower() == "solved" and not source.solved:
            # CR 702.169d: "Solved — [Ability text]" means "[Ability text].
            # Activate only if this Case is solved."
            return f"{name} is not solved, so its Solved ability cannot be activated (CR 702.169d)"
        if (ability.ability_word or "").lower() == "boast":
            # CR 702.142a: "Boast - [Cost]: [Effect]" means "[Cost]: [Effect].
            # Activate only if this creature attacked this turn and only once
            # each turn." The restriction is the keyword's own meaning, not
            # printed text (the reminder is stripped), so it is read off the
            # keyword here rather than off `instructions`.
            if source.id not in self.attacked_this_turn:
                return (
                    f"{name} has not attacked this turn, so its boast ability "
                    "cannot be activated (CR 702.142a)"
                )
            from ...machines.layers.attached_grants import boast_activation_limit

            if self._activation_count(source, index) >= boast_activation_limit(
                self, source, activator
            ):
                return f"{name}'s boast ability has already been activated this turn (CR 702.142a)"
        for window in read.windows:
            if not self._activation_window_holds(window, activator):
                return f"{name}'s ability can only be activated during {window.lower()} (CR 602.1b)"
        for condition in read.conditions:
            held = self.condition_holds(activator, condition, source)
            if held is None:
                return (
                    f'{name}\'s activation restriction "Activate only if {condition}" '
                    "is not read by this engine, so the activation is refused rather than "
                    "allowed unchecked (CR 602.5b)"
                )
            if not held:
                return f"{name}'s activation restriction is not met (CR 602.5b)"
        return None

    def _activation_window_holds(self: "Game", window: str, activator: str) -> bool:
        """Whether "Activate only during `window`" admits `activator` now."""
        match = _ACTIVATION_WINDOW.fullmatch(window)
        turn = self.turn
        if match is None or turn is None or turn.in_pregame:
            return False
        whose = (match.group("whose") or "").lower()
        if whose == "your" and turn.active_player != activator:
            return False
        if whose in ("an opponent's", "each opponent's") and turn.active_player == activator:
            return False
        if match.group("turn"):
            return True
        if match.group("combat"):
            return turn.phase is Phase.COMBAT
        if match.group("main_phase"):
            which = (match.group("main") or "").lower()
            if which == "precombat":
                return turn.step is Step.PRECOMBAT_MAIN
            if which == "postcombat":
                return turn.step is Step.POSTCOMBAT_MAIN
            return turn.step in MAIN_PHASES
        return turn.step is _STEP_NAMES[match.group("step").lower()]

    def unread_activation_restrictions(
        self: "Game", ability: ActivatedAbility, source: CardState
    ) -> list[str]:
        """Every CR 602.1b activation instruction of `ability` this engine does
        not read, as printed - empty when every one is read. An "Activate only
        if" condition counts as unread when `condition_holds` answers None
        for it on this game. Never raises: the support classifier asks it of
        every printing on a throwaway game."""
        try:
            read = read_activation_instructions(ability.instructions)
            unread = list(read.unread)
            controller = source.controller or source.owner
            if controller is None:
                controller = self.players[0].username if self.players else ""
            for condition in read.conditions:
                if self.condition_holds(controller, condition, source) is None:
                    unread.append(f"Activate only if {condition}")
            return unread
        except Exception as error:  # noqa: BLE001 - a probe that raises is not read
            return [f"{ability.instructions} ({type(error).__name__})"]

    def _activation_condition_holds(
        self: "Game", ability: ActivatedAbility, controller: str, source: CardState | None = None
    ) -> bool | None:
        """Whether an "Activate only if [condition]" restriction is met (CR 602.5b).

        True when the ability prints no such restriction, otherwise
        `condition_holds`' answer - which is None for a condition this engine
        does not read. `why_cannot_activate` refuses that None: a restriction
        nobody checked is not known to be met, and letting it through made
        every unread gate (Barbarian Ring's threshold, Rimewind Cryomancer's
        "snow permanents") a restriction that never restricted anything.
        """
        condition = _activation_condition(ability.instructions or "")
        if condition is None:
            return True
        return self.condition_holds(controller, condition, source)

    def _activation_prohibition(
        self: "Game", permanent: CardState, ability: ActivatedAbility
    ) -> str | None:
        """Why a static ability in play forbids this activation, or None (CR 602.5).

        "A player can't begin to activate an ability that's prohibited from
        being activated." The prohibitions read here are the ones a permanent's
        own static ability creates - CR 604.2: "Static abilities create
        continuous effects ... These effects are active as long as the permanent
        with the ability remains on the battlefield" - which is why the whole
        battlefield is re-read on every call rather than cached (CR 611.3a: a
        continuous effect from a static ability "isn't 'locked in'; it applies
        at any given moment to whatever its text indicates").

        **Whose permanents.** Karn, the Great Creator says "your opponents
        control", and "your" is the *source's* controller, not the activating
        player's - so the artifact is checked against Karn's controller. A
        permanent the source's own controller controls is never caught, which
        is the half of this rule that a one-player scenario cannot see. The
        symmetric printings of the same shape (Collector Ouphe, Clarion
        Conqueror) omit that clause and catch every permanent, their
        controller's included, which is what `opponents_only` distinguishes.

        **Which permanents.** The quality is read off the *computed* board
        (CR 613.5, `characteristics_of`), so an artifact Karn's own `+1`
        animated is still an artifact and still prohibited, and a permanent an
        effect turned into an artifact becomes prohibited the moment it does.

        A sentence that prohibits activation in a shape `_parse_activation_
        prohibition` cannot read is **not** silently treated as permission: it
        records a `LayerNotice` - the record kept for a static ability whose
        continuous effect this engine did not build - and the activation is
        left alone. That is the one direction that fails safe here; refusing
        every activation on an unreadable sentence would lock up boards the
        sentence was never about.
        """
        return self.activation_prohibition(permanent, is_mana=ability.mana is not None)

    def activation_prohibition(self: "Game", obj: CardState, *, is_mana: bool) -> str | None:
        """Why a static ability on the battlefield prohibits activating any
        ability of `obj` right now, or None (CR 602.5) - the whole of
        `_activation_prohibition`, callable for an ability that is not one of
        `activated_abilities`' printed lines: a keyword's activated ability
        (equip, crew, cycling - `machines/keywords.KeywordActivation.why_not`),
        in whatever zone it functions.

        CR 109.2: a card-type subject ("artifacts") means permanents on the
        battlefield, so those shapes are only asked of a permanent; CR 109.2c:
        "sources with the chosen name" reaches a source in any zone. `is_mana`
        is CR 605.1a's mana ability, spared by an "unless they're mana
        abilities" tail.
        """
        from ...machines.attached_restrictions import attached_activation_prohibition

        attached = attached_activation_prohibition(self, obj, is_mana=is_mana)
        if attached is not None:
            return attached
        from ...machines.static_cast_bans import activation_ban_reason

        static_ban = activation_ban_reason(self, obj, self.controller_of(obj).username)
        if static_ban is not None:
            return static_ban
        for source in list(self.battlefield):
            for line in parse_abilities(source.card):
                if line.kind is not AbilityKind.STATIC:
                    continue
                text = (line.text or "").strip()
                if not _LOOKS_LIKE_ACTIVATION_PROHIBITION_RE.match(text):
                    continue
                chosen = _CHOSEN_NAME_PROHIBITION_RE.match(text)
                if chosen is not None:
                    if not self._still_has_static_line(source, text):
                        continue
                    choice = source.choice
                    if choice is None or choice.kind is not ChoiceKind.CARD_NAME:
                        continue
                    if not _names_match(obj, choice.value):
                        continue
                    if chosen.group("mana_exempt") is not None and is_mana:
                        continue
                    return (
                        f"{obj.name}'s activated abilities can't be activated: "
                        f"{source.name} names it (CR 602.5, CR 611.1)"
                    )
                if _CHOSEN_PERMANENT_PROHIBITION_RE.match(text):
                    # "The chosen permanent" is one object, named by CR
                    # 614.12a's recorded choice (the same id comparison
                    # `enters_forms` makes for the chosen creature).
                    choice = source.choice
                    if (
                        self._still_has_static_line(source, text)
                        and choice is not None
                        and choice.kind is ChoiceKind.OBJECT
                        and obj.zone is Zone.BATTLEFIELD
                        and choice.value == str(obj.id)
                    ):
                        return (
                            f"{obj.name}'s activated abilities can't be activated: "
                            f"{source.name} says so (CR 602.5, CR 611.1)"
                        )
                    continue
                if _CHOSEN_NAME_SUBJECT_RE.search(text):
                    continue
                if obj.zone is not Zone.BATTLEFIELD:
                    continue
                permanent = obj
                prohibition = _parse_activation_prohibition(text)
                if prohibition is None:
                    self._record_unread_static_line(source, text)
                    continue
                if not self._still_has_static_line(source, text):
                    continue
                if prohibition.opponents_only and (
                    self.controller_of(permanent).username == self.controller_of(source).username
                ):
                    # "your opponents control": the source's controller's own
                    # permanents are untouched.
                    continue
                if prohibition.qualities and not any(
                    self._has_computed_type(permanent, quality) for quality in prohibition.qualities
                ):
                    continue
                if prohibition.mana_abilities_exempt and is_mana:
                    # CR 605.1a: a mana ability the sentence spares.
                    continue
                return (
                    f"{permanent.name}'s activated abilities can't be activated: "
                    f"{source.name} says so (CR 602.5, CR 611.1)"
                )
        return None

    def _still_has_ability(self: "Game", permanent: CardState, ability: ActivatedAbility) -> bool:
        """Whether the computed board still shows this ability on the permanent.

        `Characteristics.abilities` is a tuple of ability *text*, one entry per
        oracle line, because nothing here parses a static ability into anything
        richer. Layer 6 removal empties it and a grant appends to it, so
        comparing the printed line against it answers CR 613.1f.

        A permanent the layer engine has never seen - not on the battlefield, or
        computed before it arrived - is not judged, so this can only ever take
        an ability away that an effect actually removed.
        """
        if any(ability.raw == text for text in permanent.granted_ability_texts):
            # An ability *granted* to this object is a continuous effect from
            # the resolution that granted it (CR 611.2), applied in layer 6
            # (CR 613.1f) - after the layer 4 type change (CR 613.1d) whose
            # CR 305.7 clause strips the abilities generated from the land's
            # own rules text. So layer 4 taking the printed text away cannot
            # take this one, and the computed line list - which holds what
            # survived layer 4 - is not the place to look for it.
            #
            # Urza's Saga under Blood Moon is the case: chapter I's granted
            # "{T}: Add {C}." used to be found here only by accident, as a
            # substring of the printed chapter line "I - This Saga gains
            # '{T}: Add {C}.'". Blood Moon removes that printed line, and the
            # grant was refused with it.
            return True
        try:
            computed = self.characteristics_of(permanent)
        except KeyError:
            return True
        if not computed.abilities:
            # No ability lines at all is either a vanilla permanent or one that
            # lost everything. Only the second is interesting, and it is told
            # apart by the card having printed one in the first place.
            # `oracle_text` reads the up face; `card.oracle_text` is null for
            # a modal-DFC/transform permanent and would misreport it as
            # having lost every ability when it never had raw text to begin
            # with (same family as `effect_for` above).
            return not (permanent.oracle_text or "").strip()
        # A three-colour mana ability is printed "Add {G}, {W}, or {U}." while
        # the parsed ability joins every option with "or", so the two spellings
        # of the same list are compared with the separators made alike.
        # The computed lines read CR 201.5's "counters on <its own name>" as
        # "counters on this permanent"; the parsed text keeps the name it prints.
        names = self_reference_names(
            permanent.card.name, legendary=Supertype.LEGENDARY in permanent.supertypes
        )

        def spelled(line: str) -> str:
            return _mana_list_spelling(counters_self_reference_normalised(line, names))

        text = spelled(ability.text)
        return any(text in spelled(line) or spelled(line) in text for line in computed.abilities)

    def _activation_key(self: "Game", permanent: CardState, index: int) -> str:
        """The key `activations`/`exhausted` key an ability's bookkeeping by.

        `permanent.id` alone is not enough: `CardState.id` is stable across
        an ordinary zone change (the "same id, new object" approximation
        `CardState`'s own module docstring documents), so a permanent that
        leaves the battlefield and comes back is the *same* id. CR 400.7 says
        it is a *new object* all the same, so `zone_change_stamp` - the field
        that actually changes on every move (`move_to`) - is folded in too:
        `exhausted`'s own CR 702.177a/CR 702.193a "activate only once" is
        about this particular incarnation of the permanent, not the id that
        happens to persist underneath it, and `activations`' own per-turn
        count reads the same way (harmlessly, since it is cleared every turn
        regardless).
        """
        return f"{permanent.id}:{permanent.zone_change_stamp}:{index}"

    def _power_up_activation_limit(self: "Game", permanent: CardState) -> int:
        """How many times CR 702.193a lets `permanent`'s power-up ability be
        activated - 1 ordinarily, or 2 while its controller controls a
        source with Wonder Man, Hollywood Hero's own static line (see
        `_POWER_UP_EXTRA_ACTIVATION_TEXT`).

        Read off the computed board (CR 613.5) via `characteristics_of`, so
        the extra activation is not available before Wonder Man resolves and
        stops being available the moment he leaves - the same live check
        every other static grant in this engine already gets.
        """
        controller = permanent.controller
        for other in self.battlefield:
            if other.controller != controller:
                continue
            if self.characteristics_of(other).has_ability(self._POWER_UP_EXTRA_ACTIVATION_TEXT):
                return 2
        return 1

    def _power_up_activations_used(self: "Game", permanent: CardState, index: int) -> int:
        """How many of `permanent`'s power-up activations `exhausted` already
        records - `key` itself for the first (shared with `exhaust`'s own
        bookkeeping, `activate_ability`'s own comment on why), `key:power-up-
        extra` for the second Wonder Man's own extra activation allows."""
        key = self._activation_key(permanent, index)
        used = int(key in self.exhausted)
        used += int(f"{key}:power-up-extra" in self.exhausted)
        return used

    def _harness_key(self: "Game", permanent: CardState) -> str:
        """The key `harnessed` keys a permanent's own harnessed designation
        by - `_activation_key`'s own id-plus-incarnation scoping, without the
        ability index, since CR 701.64b's harnessed designation belongs to
        the *permanent*, not to any one of its abilities."""
        return f"{permanent.id}:{permanent.zone_change_stamp}"

    def is_harnessed(self: "Game", permanent: CardState) -> bool:
        """CR 701.64b: whether `permanent` is harnessed right now."""
        return self._harness_key(permanent) in self.harnessed

    def harness(self: "Game", permanent: CardState) -> None:
        """CR 701.64a: "'Harness [this permanent]' means 'If this permanent
        isn't harnessed, it becomes harnessed.'" A permanent not on the
        battlefield cannot become harnessed - CR 701.64b calls it "a
        designation permanents can have", and this keyword action is only
        ever printed as an activated ability's own effect, which already
        requires its source to still be a permanent to resolve meaningfully."""
        if permanent.zone is Zone.BATTLEFIELD:
            self.harnessed.add(self._harness_key(permanent))

    def _activation_handoff_key(self: "Game", permanent: CardState, index: int) -> str:
        """The key `begin_activating` hands an activation to `activate_ability`
        by (`announced_reveal_counts`, `_announced_targets`, `_opened_payments`).

        Not `_activation_key`: paying the cost between the two calls can move
        the permanent itself (Mogg Fanatic's "Sacrifice this creature"), which
        changes its `zone_change_stamp`, and the announced targets and paid
        cost belong to that one activation all the same (CR 602.2b).
        """
        return f"{permanent.id}:{index}"

    def _activation_count(self: "Game", permanent: CardState, index: int) -> int:
        return self.activations.get(self._activation_key(permanent, index), 0)

    def _loyalty_activations_allowed(self: "Game", permanent: CardState) -> int:
        """How often loyalty abilities of `permanent` may be activated each turn.

        CR 606.3 allows one; "You may activate the loyalty abilities of `<self>`
        twice each turn rather than only once" (Urza, Planeswalker) is a static
        ability (CR 604.2) of the permanent itself that raises that to two.
        """
        if permanent.zone is not Zone.BATTLEFIELD:
            return 1
        legendary = Supertype.LEGENDARY in permanent.card.supertypes
        for line in parse_abilities(permanent.card):
            if line.kind is not AbilityKind.STATIC:
                continue
            text = (line.text or "").strip()
            if not _LOYALTY_TWICE_RE.match(
                self_normalized_effect_text(permanent.name, text, legendary=legendary)
            ):
                continue
            if self._still_has_static_line(permanent, text):
                return 2
        return 1

    def _loyalty_activation_count(self: "Game", permanent: CardState) -> int:
        """How often any loyalty ability of this permanent was activated this turn.

        CR 606.3's once-per-turn rule is about the permanent, not the ability -
        "but only if no player has previously activated a loyalty ability of
        that permanent that turn" - so this is keyed by the permanent alone.
        """
        return self.loyalty_activations.get(str(permanent.id), 0)

    def activation_cost(
        self: "Game",
        permanent: CardState,
        index: int = 0,
        controller: str | None = None,
        *,
        sacrificing: list[CardState] | None = None,
        discarding: list[CardState] | None = None,
        exiling: list[CardState] | None = None,
        revealing: list[CardState] | None = None,
        tapping: list[CardState] | None = None,
        x_value: int = 0,
        targets: list[object] | None = None,
    ) -> TotalCost:
        """The total cost of one activation (CR 602.1a, 601.2f).

        CR 602.1a: "the activation cost is everything before the colon". Each
        comma-separated piece was classified by `machines/abilities.py`; this
        turns those pieces into the `TotalCost` that `machines/cost.py` knows how
        to pay. A piece that asks for an object - sacrifice, discard, or the
        "exile a creature card ... and pay its mana cost" shape Back from the
        Brink prints - takes the next card from `sacrificing`, `discarding`,
        or `exiling`; leaving it empty builds a cost that correctly refuses to
        be paid (CR 118.3) rather than one that cannot be built.

        `tapping` is the same idea for "Tap `<count>` untapped `<quality>` you
        control" (Persistent Petitioners' "Tap four untapped Advisors you
        control", Merchant's Dockhand's "Tap X untapped artifacts you
        control") - CR 601.2b's own choice of *which* permanents pay a named-
        quality tap cost, as distinct from the bare `{T}` symbol (CR 107.5's
        fixed "tap this permanent", no choice at all, already built with its
        own card filled in below). `machines/casting.py`'s own
        `Casting._printed_additional_costs` already fills a spell's matching
        `TAP` component this way (Swallow Whole's own additional cost); this
        is that same fill, for an activated ability's cost instead of a
        spell's.

        `x_value` is CR 107.3a's X, announced as this activation begins
        (CR 602.2b), the same moment `Casting.determine_cost` fixes X for a
        spell. `ManaCost.with_x` folds it in when the printed cost has one -
        Fiend Artisan's `{X}{B/G}` - and is a no-op otherwise, so every other
        activated ability in the pool is unaffected.
        """
        ability = self.activated_abilities(permanent)[index]
        refusal = x_restriction_refusal(ability.text, x_value)
        if refusal is not None:
            raise ValueError(f"{permanent.name}: {refusal}")
        controller = controller or self.controller_of(permanent).username
        sacrifices = list(sacrificing or [])
        discards = list(discarding or [])
        exiles = list(exiling or [])
        taps = list(tapping or [])

        mana = ManaCost()
        components = []
        waterbend_generic: int | None = None
        for piece in ability.costs:
            if piece.kind is CostKind.MANA:
                mana = increase(mana, ManaCost.parse(piece.text).with_x(x_value))
            elif piece.kind is CostKind.TAP:
                components.append(tap_cost(permanent, payer=controller, description=piece.text))
            elif piece.kind is CostKind.UNTAP:
                # CR 107.6: "The untap symbol is {Q}. The untap symbol in an
                # activation cost means 'Untap this permanent.'" The exact
                # mirror of the `{T}` branch above - "this permanent" is the
                # permanent whose ability is being activated, which a bare
                # symbol never names in words for `_cost_refers_to_self` to
                # read. CR 602.5a gates both symbols the same way for a
                # creature, and `why_cannot_activate` already checks that pair.
                components.append(untap_cost(permanent, payer=controller, description=piece.text))
            elif piece.kind is CostKind.SACRIFICE and (
                either := _SACRIFICE_OR_DISCARD.match(piece.text)
            ):
                # CR 118.1: "Sacrifice an artifact or discard a nonland card"
                # is one cost paid either way; the nominated cards pick which.
                if discards and not sacrifices:
                    components.append(
                        self._choice_cost(
                            "Discard " + either.group("discard"),
                            permanent,
                            discards,
                            controller,
                            discard_cost,
                            x_value,
                            targets,
                        )
                    )
                else:
                    components.append(
                        self._choice_cost(
                            "Sacrifice " + either.group("sacrifice"),
                            permanent,
                            sacrifices,
                            controller,
                            sacrifice_cost,
                            x_value,
                            targets,
                        )
                    )
            elif piece.kind is CostKind.SACRIFICE and (
                pair := _SACRIFICE_A_AND_A.match(piece.text)
            ):
                for half in (pair.group("first"), pair.group("second")):
                    text = "Sacrifice " + half
                    template = cost_component_for_phrase(text, payer=controller)
                    if template is None:
                        raise ValueError(f"cannot build a cost for {piece.text!r}")
                    # Each half takes the first nominated object with its own
                    # quality, whatever order they were nominated in.
                    fits = next(
                        (
                            card
                            for card in sacrifices
                            if template.model_copy(update={"cards": [card], "required": 1}).why_not(
                                self
                            )
                            is None
                        ),
                        None,
                    )
                    if fits is not None:
                        sacrifices.remove(fits)
                        sacrifices.insert(0, fits)
                    components.append(
                        self._choice_cost(
                            text,
                            permanent,
                            sacrifices,
                            controller,
                            sacrifice_cost,
                            x_value,
                            targets,
                        )
                    )
            elif piece.kind is CostKind.SACRIFICE:
                components.append(
                    self._choice_cost(
                        piece.text,
                        permanent,
                        sacrifices,
                        controller,
                        sacrifice_cost,
                        x_value,
                        targets,
                    )
                )
            elif piece.kind is CostKind.DISCARD:
                components.append(
                    self._choice_cost(
                        piece.text, permanent, discards, controller, discard_cost, x_value, targets
                    )
                )
            elif piece.kind is CostKind.PAY_LIFE:
                life = cost_component_for_phrase(piece.text, payer=controller)
                if life is None:
                    raise ValueError(f"cannot build a cost for {piece.text!r}")
                # CR 107.3a: "Pay X life" pays the X announced now.
                components.append(announce_count(life, x_value, 0))
            elif piece.kind is CostKind.LOYALTY:
                # CR 606.4: the loyalty symbol is the whole cost, and the
                # counter change it asks for is the cost itself.
                #
                # CR 107.7: "Negative loyalty symbols point downward and
                # feature a minus sign followed by a number or an X." A `−X`
                # symbol therefore has no amount of its own - the amount is the
                # X the activating player announces, which CR 602.2b puts at
                # this same moment (the whole of CR 601.2b's announcement,
                # X included). That is `x_value`, already threaded here from
                # `begin_activating`, so the cost is built from it and negated
                # for a minus symbol.
                #
                # CR 606.6 - "A loyalty ability with a negative loyalty cost
                # ... can't be activated unless the permanent has at least that
                # many loyalty counters on it" - is then enforced against the
                # *resolved* amount by `loyalty_cost`'s own payment, which is
                # what makes an announced X larger than the loyalty on the
                # permanent an unpayable cost rather than a silently clamped
                # one.
                amount = ability.loyalty.amount if ability.loyalty else None
                if amount is None:
                    if ability.loyalty is None or not _is_minus_symbol(ability.loyalty.printed):
                        # Not a readable symbol at all - not "−X", just
                        # unparsed. Refusing beats guessing an amount.
                        raise ValueError(f"cannot build a cost for {piece.text!r}")
                    amount = -x_value
                components.append(
                    loyalty_cost(permanent, amount, payer=controller, description=piece.text)
                )
                # CR 606.4: "cost an additional [+1]" (Carth the Lion) is another
                # loyalty symbol paid with the printed one.
                for _ in range(additional_loyalty_cost(self, controller)):
                    components.append(
                        loyalty_cost(permanent, 1, payer=controller, description="[+1]")
                    )
            else:
                # CostKind.OTHER: a printed cost sentence `machines/abilities.py`
                # could not classify into one of the shapes above. CR 118.3 makes
                # any of them payable in principle, and
                # `machines/cost.cost_component_for_phrase` is the reader that
                # turns the sentence into something payable - "Exert this land"
                # (CR 701.43a), "Exile a black card from your hand" (CR 118.9).
                threshold = _symbol_threshold_exile_component(piece.text, exiles, controller)
                if threshold is not None:
                    exiles.clear()  # "any number of": every card named pays it
                    components.append(threshold)
                    continue
                    # CR 201.5: Jessica Jones, Private Eye's own "Put a stun
                # counter on Jessica Jones" names itself by its printed name
                # rather than "this creature" - `cost_component_for_phrase`
                # already reads the normalized shape (`PLACE_COUNTERS`), so
                # normalizing here is what a future "self-named cost" printing
                # needs too, not only this one card.
                normalized_piece_text = self_normalized_effect_text(
                    permanent.name, piece.text, legendary=True
                )
                component = cost_component_for_phrase(normalized_piece_text, payer=controller)
                if (
                    component is not None
                    and component.requirement is not None
                    and component.requirement.excludes_source
                ):
                    # "Exile another <quality> card": `cost_component_for_
                    # phrase` reads the printed sentence alone and never sees
                    # a live board, so it cannot know which permanent
                    # "another" excludes - this is the one place that does.
                    component.requirement.source_id = permanent.id
                if component is None and _exiles_itself_by_name(piece.text, permanent):
                    # CR 201.5: "if an object's text uses its own name, it is
                    # referring to that particular object" - the same
                    # self-reference `_SELF_REFERENCE`'s bare "this" already
                    # reads, spelled with the printed name instead. The Stone
                    # Brain's own "Exile The Stone Brain" and Abstergo
                    # Entertainment's own "Exile Abstergo Entertainment" are
                    # the pool's examples: `_PHRASE_EXILE` only reads "exile
                    # this card" or a quality-and-count phrase, neither of
                    # which a bare self-name is, so it comes back `None` and
                    # is built here instead - straight from the battlefield
                    # (CR 113.6: an activated ability's source is normally
                    # there), the same empty-then-filled shape
                    # `_SELF_REFERENCE`'s branch below uses for "this".
                    component = exile_cost(
                        payer=controller,
                        required=1,
                        description=piece.text,
                        zone=Zone.BATTLEFIELD,
                    )
                if component is None:
                    # A printed cost sentence that is *mana* wearing an action
                    # word - "Waterbend {3}" is CR 701.67a's "Pay [cost]", and
                    # the permission it carries (tap an untapped artifact or
                    # creature for each generic mana) is CR 701.67b's alternate
                    # payment method, which belongs to an open `CostPayment`
                    # rather than to the total cost. `cost_component_for_phrase`
                    # only ever builds non-mana components, so it cannot answer
                    # for one; `total_cost_for_phrase` reads the whole sentence
                    # and hands back both halves.
                    whole = total_cost_for_phrase(piece.text, controller)
                    if whole is not None and whole.mana.symbols:
                        mana = increase(mana, whole.mana.with_x(x_value))
                        components.extend(whole.components)
                        if whole.waterbend_generic is not None:
                            # CR 701.67b: this ability's own waterbend
                            # budget is the sum of whatever `total_cost_for_
                            # phrase` read as waterbend-sourced generic
                            # across every comma-separated piece of the
                            # cost - `piece.text` is already one such piece,
                            # so summing across the loop is what a cost with
                            # more than one waterbend clause (CR 701.67b
                            # never forbids it, though nothing prints it)
                            # would need too.
                            waterbend_generic = (waterbend_generic or 0) + whole.waterbend_generic
                        continue
                if component is None:
                    raise ValueError(f"cannot build a cost for {piece.text!r}")
                # "Exile X cards", "Remove X counters", "Exile one or more ...":
                # the count announced now (CR 107.3a), or every card nominated.
                component = announce_count(component, x_value, len(exiles))
                if component.kind is ComponentKind.PUT_EXILED_INTO_GRAVEYARD:
                    # CR 607.2a: "this creature" names the pile's owner, not the
                    # card paid. The cards nominated (or, none named, the first
                    # card exiled with it) pay.
                    pile = self.cards_exiled_with(permanent.id, permanent.zone_change_stamp)
                    component = component.model_copy(
                        update={
                            "link_to_permanent_id": permanent.id,
                            "cards": list(exiles[: component.required])
                            if exiles
                            else pile[: component.required],
                        }
                    )
                    del exiles[: component.required]
                elif not component.cards and (
                    _cost_refers_to_self(piece.text, permanent)
                    or _exiles_itself_by_name(piece.text, permanent)
                ):
                    # "Exert **this** land": only the caller knows which
                    # permanent the ability is on, so the reader builds the
                    # component empty and it is filled in here (CR 602.1a - the
                    # ability's source is the object it is printed on).
                    component = component.model_copy(update={"cards": [permanent]})
                if not component.cards and exiles and component.kind is ComponentKind.EXILE:
                    # Back from the Brink's own shape, the exile half chosen
                    # from `exiling` the same way `_choice_cost` fills
                    # `sacrificing`/`discarding` - this component was not
                    # built through `_choice_cost` because its `CostKind` is
                    # `OTHER`, not `SACRIFICE`/`DISCARD`.
                    chosen: list[CardState] = []
                    while exiles and len(chosen) < component.required:
                        chosen.append(exiles.pop(0))
                    component = component.model_copy(update={"cards": chosen})
                if not component.cards and taps and component.kind is ComponentKind.TAP:
                    # "Tap `<count>` untapped `<quality>` you control"
                    # (Persistent Petitioners, Merchant's Dockhand): the same
                    # fill as the `EXILE` branch immediately above, from
                    # `tapping` rather than `exiling`. This component's own
                    # `CostKind` is `OTHER` too - the bare `{T}` symbol is
                    # what the `CostKind.TAP` branch above already built with
                    # `[permanent]` filled in, so this never double-fills it.
                    chosen_taps: list[CardState] = []
                    if component.minimum_total_power is not None:
                        # CR 208.1: "any number ... with total power N": every
                        # creature named is tapped, and their sum must reach N.
                        component = component.model_copy(update={"required": len(taps)})
                    while taps and len(chosen_taps) < component.required:
                        chosen_taps.append(taps.pop(0))
                    component = component.model_copy(update={"cards": chosen_taps})
                if component.kind is ComponentKind.REVEAL:
                    # CR 701.20a's reveal from hand: the cards named in
                    # `revealing` pay it, and for CR 107.3a's X their number
                    # is the X announced (`announce_reveal`).
                    component = announce_reveal(component, revealing, x_value, permanent.name)
                if component.pay_mana_cost_of_chosen:
                    # CR 118.9's own alternative-cost shape, aimed at the just
                    # -chosen card's *own* printed mana cost rather than a
                    # fixed one - only known now that a card was chosen.
                    for card in component.cards:
                        printed = card.card.mana_cost or ""
                        if printed:
                            mana = increase(mana, ManaCost.parse(printed))
                components.append(component)

        if ability.power_up and self._entered_this_turn(permanent):
            # CR 702.193a-b: "If this permanent entered this turn, this
            # ability's cost is reduced by this permanent's mana cost."
            # CR 702.193b/118.7: generic mana in the permanent's mana cost
            # reduces generic mana in the activation cost, colored/colorless
            # mana reduces mana of the same type with any excess spilling
            # into generic - exactly what `ManaCost.minus` already implements
            # (CR 118.7a-d), so the permanent's own printed mana cost is
            # simply subtracted, unreduced by anything else that might also
            # be discounting it (CR 601.2f's reductions are cumulative, not
            # exclusive of one another).
            mana = mana.minus(ManaCost.for_card(permanent.card))

        if ability.cost_reduction is not None:
            # CR 601.2f, applied to an activated ability's own cost via CR
            # 602.2b: "This ability costs [N] less to activate for each
            # [quality] you control" - read structurally off
            # `ActivatedAbility.cost_reduction` (`machines/abilities.py`
            # already split it from the effect as its own static ability, not
            # a clause of it - see `ActivationCostReduction`'s docstring).
            mana = mana.minus(self.activation_cost_reduction_for(permanent, ability, controller))

        if ability.power_up:
            mana = mana.minus(self._power_up_group_discount(permanent, controller))
        mana = mana.minus(self._activation_target_cost_reduction(permanent, ability, targets))
        mana = self._activated_ability_group_discount(permanent, controller, mana)
        from ...machines.attached_restrictions import activation_cost_increase

        mana = increase(mana, activation_cost_increase(self, permanent))
        # EP-01 T7: "Equip abilities you activate cost {1} less", "Boast
        # abilities ...", "Activated abilities cost {2} more" and the rest of
        # `machines/cost/abilities.py`'s grammar (CR 601.2f via CR 602.2b).
        mana = ability_cost_adjustment(
            self,
            controller,
            permanent,
            mana,
            kind="exhaust"
            if ability.exhaust
            else "boast"
            if (ability.raw or "").lower().startswith("boast")
            else "",
            is_mana=ability.mana is not None,
            is_loyalty=ability.loyalty is not None,
            targets=tuple(targets or ()),
            from_zone=permanent.zone,
        )

        return TotalCost(
            mana=mana, components=components, waterbend_generic=waterbend_generic
        ).assign_payer(controller)

    def _power_up_group_discount(self: "Game", permanent: CardState, controller: str) -> ManaCost:
        """CR 601.2f/602.2b's own group discount on *another* permanent's
        power-up ability - Hulk, Gamma Goliath's own static (`_POWER_UP_
        GROUP_DISCOUNT_RE`), which never discounts its own power-up cost
        ("other creatures"). Summed across every source of the text the
        controller has, the same "reductions are cumulative" posture CR
        601.2f already takes and `activation_cost`'s own docstring already
        notes for the entered-this-turn/`cost_reduction` pair above it.
        Read off the computed board (CR 613.5) via `characteristics_of`.
        """
        total = 0
        for other in self.battlefield:
            if other.controller != controller or other.id == permanent.id:
                continue
            for line in self.characteristics_of(other).abilities:
                match = self._POWER_UP_GROUP_DISCOUNT_RE.fullmatch(line.strip())
                if match is not None:
                    total += int(match.group("amount"))
        return ManaCost.parse(f"{{{total}}}") if total else ManaCost()

    def _activated_ability_group_discount(
        self: "Game", permanent: CardState, controller: str, mana: ManaCost
    ) -> ManaCost:
        """`mana` reduced by every "activated abilities of `<group>` you
        control cost `{N}` less to activate" static the controller has in
        play (CR 601.2f via CR 602.2b) - Mutagen Man, Living Ooze's own
        "artifact tokens", generalised the way `activated_ability_group_
        discount_effect` reads any group phrase rather than that one.

        Unlike `_power_up_group_discount`, a source's own ability is not
        excluded from its own group discount ("other" is not part of this
        template the way Hulk's own "other creatures" is) - the Mutagen
        token's `{1}` sacrifice ability is discounted by Mutagen Man's static
        exactly as any other artifact token's is, since CR 601.2f draws no
        such line and the printed line names none either.

        The floor ("This effect can't reduce the mana in that cost to less
        than one mana" - Forensic Gadgeteer, Training Grounds, Heartstone) is
        applied once, against `mana` as handed in (already reduced by every
        earlier step `activation_cost` has applied): a reduction is clamped
        so the cost this static discounts never drops below one mana, but
        only when `mana` itself already carried at least that much - CR
        601.2f's own "It can't be reduced to less than {0}" is the ordinary
        floor for every other reduction, unaffected by a static that names no
        floor of its own.
        """
        total = 0
        floor_one = False
        already_noticed = {notice.source_id for notice in self.cost_modifier_notices}
        for other in self.battlefield:
            if other.controller != controller:
                continue
            for line in self.characteristics_of(other).abilities:
                effect = activated_ability_group_discount_effect(line.strip())
                if effect is None:
                    continue
                qualifies = self._permanent_matches_group_quality(permanent, effect.quality)
                if qualifies is None:
                    if other.id not in already_noticed:
                        already_noticed.add(other.id)
                        self.cost_modifier_notices.append(
                            CostModifierNotice(
                                source_id=other.id, source_name=other.name, text=line.strip()
                            )
                        )
                    continue
                if not qualifies:
                    continue
                total += effect.amount
                floor_one = floor_one or effect.floor_one
        if not total:
            return mana
        reduced = mana.minus(ManaCost.parse(f"{{{total}}}"))
        if floor_one and mana.converted > 0 and reduced.converted < 1:
            reduced = mana.minus(ManaCost.parse(f"{{{max(mana.converted - 1, 0)}}}"))
        return reduced

    def _activation_target_cost_reduction(
        self: "Game", permanent: CardState, ability: ActivatedAbility, targets: list[object] | None
    ) -> ManaCost:
        """`_ABILITY_COSTS_LESS_IF_TARGETS_POWER_RE`'s reduction, read off
        every static-kind sentence this ability's own raw text carries
        (CR 604.1's one-sentence-per-ability convention does not apply
        within a single activated ability's own paragraph the way it does
        between separate abilities, so this simply searches the whole raw
        text) - `None` when the ability names no such sentence, `targets` is
        empty, or the chosen target does not qualify.
        """
        if not targets:
            return ManaCost()
        match = self._ABILITY_COSTS_LESS_IF_TARGETS_POWER_RE.search(ability.raw or "")
        if match is None:
            return ManaCost()
        try:
            wanted_type = Type(match.group("quality").lower())
        except ValueError:
            return ManaCost()
        at_most = match.group("cmp").lower() == "less"
        bound = int(match.group("power"))
        for target in targets:
            state = target if isinstance(target, CardState) else self.find_by_id(target)
            if not isinstance(state, CardState):
                continue
            if wanted_type not in state.types:
                continue
            power = self.power_of(state)
            if power is None:
                continue
            if (power <= bound) if at_most else (power >= bound):
                return ManaCost.parse(f"{{{match.group('n')}}}")
        return ManaCost()

    def activation_cost_reduction_for(
        self: "Game", permanent: CardState, ability: ActivatedAbility, controller: str
    ) -> ManaCost:
        """What `ability`'s own "costs [N] less to activate for each [quality]
        you control" sentence takes off its cost right now (CR 601.2f via CR
        602.2b) - the activated-ability twin of `cost_reduction_for`, which
        only ever reads a *spell's* own self-discount.

        The quality is read generically, off its own words - a CR 205.4a
        supertype ("legendary"), a CR 205.2a card type ("creature"), or both -
        the same way `_activation_condition_holds`'s "Activate only if you
        control ..." already counts a quality, so a future card printing this
        exact sentence with a different quality needs no table row either.
        CR 613.5: read off the computed board, not the printed
        `state.card.types`/`.supertypes` - a clone (`BecomeACopy`, CR 707.2,
        707.4) that has become a legendary creature is one only there.

        A quality this cannot read at all records a `CostModifierNotice`
        rather than quietly reducing by nothing - the same "unreadable is not
        the same as no effect" rule `static_cost_modifiers_for` already keeps
        for a permanent's *other* static cost text (DDR#978).

        `reduction.self_counter_kind` (SOS's Diary of Dreams: "... for each
        page counter on this artifact.") is a different sentence shape
        entirely - a count on the ability's own source rather than a quality
        among permanents its controller controls - answered directly off
        `permanent.counter_count` (CR 122.1 leaves the counter kind open, the
        same read every other counter-kind check in this codebase already
        takes) before this reaches the "quality" reading below at all.
        `reduction.target_quality` (Dragonfire Blade's, Warrior's Blades' own
        equip-cost shape) is `machines/keywords.py`'s own equip-activation
        path to read, never this one - equip costs are priced through
        `unannounced_equip_activation`, not `Game.activation_cost`, so this
        function is never actually asked about a `target_quality` reduction
        in practice; it answers no reduction rather than crashing on the
        `quality`-only reading below if that invariant is ever broken.
        """
        reduction = ability.cost_reduction
        if reduction is None:
            return ManaCost()

        if reduction.self_counter_kind is not None:
            amount = reduction.amount * permanent.counter_count(reduction.self_counter_kind)
            return ManaCost.parse(f"{{{amount}}}") if amount else ManaCost()

        if reduction.graveyard_quality is not None:
            counted = graveyard_count_expression(
                f"{reduction.graveyard_quality} cards in your graveyard"
            )
            amount = 0 if counted is None else reduction.amount * counted(self, controller)
            return ManaCost.parse(f"{{{amount}}}") if amount else ManaCost()

        if reduction.quality is None:
            return ManaCost()

        words = reduction.quality.strip().lower().split()
        supertypes: list[Supertype] = []
        types: list[Type] = []
        subtypes: list[str] = []
        for word in words:
            singular = word.removesuffix("s")
            try:
                supertypes.append(Supertype(singular))
                continue
            except ValueError:
                pass
            try:
                types.append(Type(singular))
                continue
            except ValueError:
                pass
            # CR 205.3: anything else in the quality is a subtype ("Equipment").
            subtypes.append(singular)
        if not types and not subtypes:
            already_noticed = any(
                notice.source_id == permanent.id for notice in self.cost_modifier_notices
            )
            if not already_noticed:
                self.cost_modifier_notices.append(
                    CostModifierNotice(
                        source_id=permanent.id,
                        source_name=permanent.name,
                        text=ability.raw,
                    )
                )
            return ManaCost()

        board = self.computed_board()
        count = sum(
            1
            for state in self.permanents_controlled_by(controller)
            if state.zone is Zone.BATTLEFIELD
            and all(t in board.of(state).types for t in types)
            and all(s in board.of(state).supertypes for s in supertypes)
            and all(sub in {have.lower() for have in board.of(state).subtypes} for sub in subtypes)
        )
        amount = reduction.amount * (min(count, 1) if reduction.if_you_control else count)
        return ManaCost.parse(f"{{{amount}}}") if amount else ManaCost()

    def begin_turning_face_up(
        self: "Game",
        permanent: CardState,
        controller: str | None = None,
        *,
        procedure: str | None = None,
    ) -> CostPayment:
        """Announce turning a face-down morph creature face up, and open its
        payment (CR 702.37e).

        "Any time you have priority, you may turn a face-down permanent you
        control with a morph ability face up. This is a special action; it
        doesn't use the stack. To do this, show all players what the
        permanent's morph cost would be if it were face up, pay that cost,
        then turn the permanent face up." Mirrors `begin_activating`'s own
        two-call split (open the payment, then finish the action) for
        exactly the same reason: paying can take more than one priority-free
        moment (tapping several lands), and CR 116.1 lets a special action
        be taken any time its controller could take one, not only once the
        whole cost is already in hand.

        `procedure` (`"morph"` or `"manifest"`) picks which of CR 701.40c-d's
        two procedures to pay when the permanent is manifested *and* has
        morph or disguise; pass the same value to `turn_face_up` below, the
        way `controller` is already passed to both. `None` keeps the old
        default preference - see `turn_face_up_cost`'s own docstring.

        Raises if the special action is unavailable at all (CR 702.37e's own
        parenthetical, or a permanent that is not face down here), before
        anything has been spent.
        """
        self._refuse_if_over()
        refusal = self.why_cannot_turn_face_up(permanent, procedure=procedure)
        if refusal is not None:
            raise ValueError(refusal)
        controller = controller or self.controller_of(permanent).username
        total = turn_face_up_cost(permanent, controller, procedure=procedure, game=self)
        assert total is not None  # `why_cannot_turn_face_up` already checked this
        return CostPayment.for_total(total, game=self, payer=controller)

    def why_cannot_turn_face_up(
        self: "Game", permanent: CardState, *, procedure: str | None = None
    ) -> str | None:
        """Why this permanent cannot be turned face up right now, or None:
        CR 702.37e's own conditions (`keywords.why_cannot_turn_face_up`, which
        also covers CR 702.168d's disguise and CR 701.40b's manifest
        procedures), then any static ban a permanent on the battlefield puts
        on it (`keywords.turn_face_up_ban` - Unable to Scream, Karlov
        Watchdog). `procedure` is CR 701.40c-d's own choice between the two
        procedures - see `keywords.why_cannot_turn_face_up`'s docstring."""
        return why_cannot_turn_face_up(permanent, procedure=procedure) or turn_face_up_ban(
            self, permanent
        )

    def why_cannot_turn_face_up_as(
        self: "Game", username: str, permanent: CardState, *, procedure: str | None = None
    ) -> str | None:
        """Why `username` specifically cannot turn `permanent` face up right
        now, or None - the seat-facing refusal `why_cannot_turn_face_up`
        above does not give, because that one never asks who is asking or
        whether they can pay. See `machines/special_actions.why_cannot_turn_
        face_up_as`'s own docstring for the three checks, in order, and for
        `procedure`."""
        return why_cannot_turn_face_up_as(self, username, permanent, procedure=procedure)

    def turn_face_up(
        self: "Game",
        permanent: CardState,
        controller: str | None = None,
        *,
        procedure: str | None = None,
    ) -> CardState:
        """Finish turning a face-down permanent face up (CR 702.37e, 708.8).

        The cost is paid by the caller through `begin_turning_face_up`; this
        is the half that actually reveals the card and fires whatever
        watches for it - Brine Elemental's own "When this creature is turned
        face up, each opponent skips their next untap step" is the only
        printing in the pool with such a trigger.

        No stack, no priority pass (CR 116): the emitted `TURNED_FACE_UP`
        event still queues an ordinary triggered ability the normal way
        (CR 603.3, `put_triggers_on_stack` puts it on the stack the next time
        a player would receive priority) - a special action skips the stack
        for *itself*, not for what it triggers.

        `procedure` mirrors whatever was passed to `begin_turning_face_up`
        for this same turn-up (CR 701.40c-d's choice, when the permanent is
        manifested *and* has morph or disguise, between paying the morph/
        disguise cost and paying the card's own mana cost). It matters here
        only for CR 702.37b: "As this permanent is turned face up, put a
        +1/+1 counter on it if its megamorph cost was paid to turn it face
        up." That is true whenever the morph/disguise procedure was the one
        actually used - `procedure == "morph"`, or `None` falling back to
        the same default `turn_face_up_cost` used to price it - and false
        for `"manifest"`, CR 701.40b's own procedure, which never touches a
        morph cost at all no matter how the card's megamorph reads.
        """
        self._refuse_if_over()
        ban = turn_face_up_ban(self, permanent)
        if ban is not None:
            raise ValueError(ban)
        with self._id_allocator_scope():
            controller = controller or self.controller_of(permanent).username
            ability = morph_ability(permanent.card)
            megamorph = (
                procedure != "manifest"
                and ability is not None
                and ability.canonical.lower() == "megamorph"
            )
            permanent.turn_face_up()
            from ...machines.replacement.enters_choices import as_turned_face_up

            as_turned_face_up(self, permanent)  # CR 614.1e, before anything triggers
            self.emit(
                GameEvent(
                    event=TriggerEvent.TURNED_FACE_UP,
                    subject_id=permanent.id,
                    subject_name=permanent.name,
                    subject_controller=permanent.controller,
                    subject_card=permanent.card,
                    player=controller,
                )
            )
            if megamorph:
                self.add_counters(permanent, Counter.PLUS_ONE, 1, putter=controller)
            return permanent

    def _activation_target_text(
        self: "Game", ability: Any, x_value: int, permanent: CardState
    ) -> str:
        """The ability's own text its targets are announced against.

        `x_value` is substituted in first when the printed cost carries an
        {X} at all (CR 107.3a: X is announced as part of CR 601.2b/602.2b,
        before targets are, CR 601.2c) - The Mycosynth Gardens' own "target
        nontoken artifact you control with mana value X" is unreadable by
        `machines/targeting.py` with a literal "X" still in it.

        A **loyalty** ability spells its X differently: CR 107.7's negative
        symbol is written "-X", not "{X}", so Tamiyo, Compleated Sage's "-X:
        Exile target nonland permanent card with mana value X from your
        graveyard" is marked by `LoyaltyCost.variable` instead.

        CR 201.5's self-reference is rewritten to "this permanent" too
        (`self_normalized_effect_text`, `machines/effects.activated_effect_
        for`'s own normalization the *effect* half already gets) - Hope of
        Ghirapur's own "target player who was dealt combat damage by Hope
        of Ghirapur this turn" is unreadable by `machines/targeting.py`
        with its own literal printed name still in the target phrase, the
        identical reason `x_value` is substituted first.
        """
        has_variable_loyalty = ability.loyalty is not None and ability.loyalty.variable
        text = (
            substitute_x(ability.text, x_value)
            if (cost_announces_x(ability.cost) or has_variable_loyalty)
            else ability.text
        )
        legendary = Supertype.LEGENDARY in permanent.card.supertypes
        text = self_normalized_effect_text(permanent.name, text, legendary=legendary)
        # Raft Security Officer's own trailing "This ability costs {1} less
        # to activate if it targets a creature with power 3 or less." reads
        # like a second targeting sentence to `machines/targeting.profile_
        # for_text`, which left the whole ability `understood=False` and so
        # silently announced no target at all (CR 601.2c) even when one was
        # given - stripped here the same way `machines/effects.
        # activated_effect_for` strips it before parsing the effect.
        return self._ABILITY_COSTS_LESS_IF_TARGETS_POWER_RE.sub("", text).strip()

    def _announce_activation_targets(
        self: "Game",
        permanent: CardState,
        controller: str,
        text: str,
        targets: list[object] | None,
    ) -> list[TargetRef] | None:
        """CR 601.2c for an activation (CR 602.2b): ask for, or check, its targets.

        `None` when the ability's text names no target this engine can read,
        so there is nothing to announce. Otherwise the announced targets,
        referenced as they are *now* - before any cost is paid (CR 601.2h) -
        so a target the cost itself moves (a source sacrificing itself) keeps
        naming the object it was when chosen, and CR 608.2b finds it gone.
        """
        profile = profile_for_text(text)
        if not (profile.understood and profile.requirements):
            return None
        if targets is None:
            # The caller supplied nothing, so this is not yet a target
            # announcement at all - ask, the same way a triggered ability's
            # own announcement is asked (`_ask_targets`, shared with
            # `_ask_trigger_targets`). An explicit list, even an empty one, is
            # a real answer already given and is checked instead.
            asked = self._ask_targets(profile, controller, permanent.id, permanent.name, text)
            if asked is None:
                # CR 601.2e, imported wholesale by CR 602.2b: a proposed
                # activation that cannot legally be completed - a mandatory
                # target (CR 601.2c) with no legal object or player to name -
                # never happens at all, the same refusal
                # `Game.cast_during_resolution` gives a spell (CR 601.2c).
                raise ValueError(
                    f"{permanent.name}'s ability requires a target, but no legal "
                    "target exists, so it cannot be activated (CR 601.2c, CR 602.2b)"
                )
            return list(asked)
        profile.check(list(targets), controller, self, source_id=permanent.id)
        return self.stamp_target_slots(
            profile, [TargetRef.coerce(target) for target in targets], controller, permanent.id
        )

    def _announce_activation_modes(
        self: "Game",
        permanent: CardState,
        controller: str,
        ability: ActivatedAbility,
        targets: list[object] | None,
    ) -> tuple[list[int], list[list[TargetRef]]] | None:
        """CR 700.2a for an activation: "The controller of a modal spell or
        activated ability chooses the mode(s) as part of casting that spell or
        activating that ability" - and CR 700.2c, only the chosen modes' own
        targets are announced. `None` when the ability is not modal.

        Reads the same bulleted "Choose one -" tail a modal triggered ability
        does (`modal_trigger_profile`), with the same exclusions: a mode that
        has no legal target can't be chosen (CR 700.2), and "choose one that
        hasn't been chosen this turn" (Kargan Intimidator) leaves out a mode
        this permanent already chose (`_announce_trigger_modes`). `targets`,
        when the caller names them, answer the first targeted mode's slice.
        """
        modal = modal_trigger_profile(ability.effect)
        if modal is None:
            return None
        announcing = AbilityOnStack(
            kind=AbilityKind.ACTIVATED,
            ability=ability,
            source_id=permanent.id,
            source_name=permanent.name,
            controller=controller,
        )
        if not self._announce_trigger_modes(announcing, modal, targets or None):
            raise ValueError(
                f"{permanent.name}'s ability has no mode that can be chosen, so it cannot be "
                "activated (CR 700.2, CR 602.2b)"
            )
        return list(announcing.modes), [list(slice_) for slice_ in announcing.mode_targets]

    def _check_activation_division(
        self: "Game",
        ability: ActivatedAbility,
        x_value: int,
        targets: list[TargetRef],
        division: list[int],
        permanent: CardState,
    ) -> list[int]:
        """Refuse an illegal CR 601.2d division of an activated ability's
        effect, or return the shares as announced.

        CR 602.2b runs CR 601.2d for an activation exactly as for a spell: one
        share per target, each at least one, adding up to the whole amount -
        the check `TargetingProfile.check_division` already makes for
        `Casting.announce_division`. An ability whose text divides nothing
        has no division to announce.
        """
        profile = profile_for_text(self._activation_target_text(ability, x_value, permanent))
        if profile.division is None:
            raise ValueError(f"{ability.text} does not divide anything to announce (CR 601.2d)")
        shares = [int(share) for share in division]
        amount = profile.division.amount if profile.division.amount is not None else x_value
        profile.check_division(shares, targets, amount=amount)
        return shares

    def begin_activating(
        self: "Game",
        permanent: CardState,
        index: int = 0,
        controller: str | None = None,
        *,
        sacrificing: list[CardState] | None = None,
        discarding: list[CardState] | None = None,
        exiling: list[CardState] | None = None,
        revealing: list[CardState] | None = None,
        tapping: list[CardState] | None = None,
        x_value: int = 0,
        targets: list[object] | None = None,
        division: Sequence[int] | None = None,
    ) -> CostPayment:
        """Announce an activation and open its payment (CR 602.2a, 602.2b).

        Raises if the ability is prohibited from being activated at all
        (CR 602.5), before anything has been spent.

        `targets` are announced here, before the payment this returns is
        paid: CR 602.2b runs CR 601.2c (targets) before CR 601.2h (paying).
        `None` asks for them. They are checked against the board as it is now,
        so Vampire Hexmage may target itself and its "Sacrifice this
        creature" cost is paid afterwards; CR 608.2b is what finds the target
        gone on resolution. `activate_ability` takes the announcement back.

        `x_value` is CR 107.3a's X, announced now (CR 602.2b puts the whole of
        CR 601.2b's announcement, X included, at this same moment) - the
        caller must hand the identical value to `activate_ability` afterward,
        the same two-call split `Casting.determine_cost`/`choose_modes` and
        `Casting.cast` already require of a spell's X.
        """
        refusal = self.why_cannot_activate(permanent, index, controller)
        if refusal is not None:
            raise ValueError(refusal)
        controller = controller or self.controller_of(permanent).username
        refusal = self._why_cannot_activate_without_priority(permanent, index, controller, targets)
        if refusal is not None:
            raise ValueError(refusal)
        total = self.activation_cost(
            permanent,
            index,
            controller,
            sacrificing=sacrificing,
            discarding=discarding,
            exiling=exiling,
            revealing=revealing,
            tapping=tapping,
            x_value=x_value,
            targets=targets,
        )
        # CR 601.2h pays the cost the player chose, so a reveal cost nobody
        # named is asked about now, before anything is spent - and refused now
        # (CR 118.3) if the cards named cannot pay it.
        key = self._activation_handoff_key(permanent, index)
        self.announced_reveal_counts.pop(key, None)
        for component in total.components:
            if component.from_among and not component.cards:
                # "Remove N counters from among creatures you control"
                # (Hopeful Initiate): the permanents that give them, taken in
                # battlefield order until the total is met (`cost.fill_from_
                # among`'s documented default).
                from ...machines.cost import fill_from_among

                fill_from_among(
                    component,
                    self,
                    controller,
                    None,
                    source=permanent.name,
                    source_id=source_id_of(permanent),
                )
                continue
            if (
                component.kind in (ComponentKind.PLACE_COUNTERS, ComponentKind.REMOVE_COUNTERS)
                and not component.cards
                and component.requirement is not None
            ):
                self._choose_permanent_for_counters(component, controller, permanent)
                continue
            if (
                component.kind is ComponentKind.RETURN_TO_HAND
                and not component.cards
                and component.requirement is not None
            ):
                self._choose_permanents_to_return(component, controller, permanent)
                continue
            if component.kind is not ComponentKind.REVEAL:
                continue
            if revealing is None:
                self.choose_cards_to_reveal(
                    component,
                    controller,
                    source=permanent.name,
                    source_id=source_id_of(permanent),
                    x_value=x_value,
                )
            refusal = component.why_not(self)
            if refusal is not None:
                raise ValueError(refusal)
            if component.variable_count:
                self.announced_reveal_counts[key] = len(component.cards)
        # CR 601.2c before CR 601.2h (both via CR 602.2b): the targets are
        # announced and checked now, while the cost is still unpaid.
        self._announced_targets.pop(key, None)
        ability = self.activated_abilities(permanent)[index]
        announced_x = x_value or self.announced_reveal_counts.get(key, 0)
        self._announced_modes.pop(key, None)
        modes = self._announce_activation_modes(permanent, controller, ability, targets)
        if modes is not None:
            self._announced_modes[key] = modes
            announced = [target for slice_ in modes[1] for target in slice_]
        else:
            announced = self._announce_activation_targets(
                permanent,
                controller,
                self._activation_target_text(ability, announced_x, permanent),
                targets,
            )
        if division is not None:
            # CR 601.2d via CR 602.2b: the division is announced right after
            # the targets, and refused now, before anything is paid.
            self._check_activation_division(
                ability, announced_x, list(announced or []), list(division), permanent
            )
        # CR 106.6: an activation is what Shang-Chi's and Eldrazi Temple's
        # mana is restricted *to*, and what Cavern of Souls's and Delighted
        # Halfling's is restricted *from*, so the payment is told which it is
        # and whose ability it belongs to (the source's characteristics are
        # what "abilities of creature sources" asks about, not the ability's).
        # ...and those characteristics are the *computed* ones (CR 613.5): a
        # land animated into a creature is a creature source, so Shang-Chi's
        # mana pays for its abilities. `permanent.card` here was the printed
        # front face, wrong for a transformed permanent even before layers.
        # `machines/legal_actions.py` asks the identical question when it
        # enumerates the same activation, and the two must not disagree.
        #
        # `Game.computed_board` only ever covers the battlefield (CR 613.1's
        # layers apply to permanents), so a CR 113.6j/113.6m ability
        # activating from a hand or a graveyard has no computed board entry
        # to ask - `characteristics_of` would raise `NotOnBoard`. `CardState`
        # itself already answers `name`/`types`/`subtypes`/`supertypes`/
        # `colors` off its own printed face (`up_face`-aware), which is the
        # right read off the battlefield: CR 613.5 only starts substituting
        # computed values once the card actually is a permanent. The same
        # split `ManaSpend.casting` already draws for a spell on the stack
        # (`Game.computed_board` does not cover that zone either).
        source_characteristics = (
            self.characteristics_of(permanent) if permanent.zone is Zone.BATTLEFIELD else permanent
        )
        payment = CostPayment.for_total(
            total,
            game=self,
            payer=controller,
            spend=ManaSpend.activating(
                source_characteristics,
                any_color=self.spends_mana_as_any_color(permanent, ability, controller),
                class_level=getattr(ability, "class_level_target", None) is not None,
            ).model_copy(update={"color_rule": self.mana_color_rule(controller, permanent)}),
        )
        payment.paying_for = "ability"
        payment.tap_creatures_for_mana = read_activation_instructions(
            ability.instructions
        ).taps_creatures_for_mana
        payment.restrict_x_from_text(
            ability.text,
            sum(
                ManaCost.parse(piece.text).x_count
                for piece in ability.costs
                if piece.kind is CostKind.MANA
            ),
            x_value,
        )
        if announced is not None or key in self._announced_modes:
            self._announced_targets[key] = (announced or [], payment)
        self._opened_payments[key] = payment
        self._activation_source_stamps[key] = permanent.zone_change_stamp
        return payment

    def _activated_source_types(self: "Game", permanent: CardState) -> tuple[Type, ...]:
        """The card types of an activated ability's source as it was
        activated (CR 603.10a's look-back for a source its own cost moved -
        "Sacrifice this artifact: ..." has left the battlefield by now)."""
        if permanent.zone is Zone.BATTLEFIELD:
            return tuple(self.characteristics_of(permanent).types)
        left = self._left_battlefield_characteristics.get(permanent.id)
        if left is not None:
            return tuple(left.types)
        return tuple(permanent.types)

    @staticmethod
    def _loyalty_removed_by(paid: Any, ability: Any, x_value: int) -> int:
        """How many loyalty counters an activation's cost removed (CR 606.4).

        Read off the paid cost's own loyalty component, which is the amount
        after any modification (CR 606.4) and combination (CR 606.5); a caller
        that never opened a payment falls back to the printed symbol."""
        if paid is not None:
            return sum(
                -component.amount
                for component in paid.components
                if component.kind is ComponentKind.LOYALTY and component.amount < 0
            )
        symbol = ability.loyalty
        if symbol is None:
            return 0
        if symbol.amount is None:
            return x_value if _is_minus_symbol(symbol.printed) else 0
        return symbol.removes

    def _why_cannot_activate_without_priority(
        self: "Game",
        permanent: CardState,
        index: int,
        controller: str,
        targets: Sequence[Any] | None,
    ) -> str | None:
        """CR 117.1b: "A player may activate an activated ability any time they
        have priority" - asked as CR 602.2 begins, before any cost is chosen or
        paid, the activation twin of `machines/casting.
        why_cannot_cast_without_priority`. Asked only once the ability was on
        the stack (`Priority.retain`), every question the activation put first
        - a cost choice, a CR 603.3b ordering of what its cost triggered - stood
        in front of a refusal that was always coming.

        A mana ability is exempt (CR 605.3a: it may also be activated while
        paying a cost or when a rule or effect asks for a mana payment), read
        by the same four CR 605.1a criteria `activate_ability` applies.
        """
        if self.priority is None:
            return None
        ability = self.activated_abilities(permanent)[index]
        if (
            ability.mana is not None
            and ability.loyalty is None
            and not targets
            and not moves_a_library_card(ability)
        ):
            return None
        return self.why_not_holding_priority(controller, "CR 117.1b")

    def activate_ability(
        self: "Game",
        permanent: CardState,
        index: int = 0,
        controller: str | None = None,
        *,
        targets: list[object] | None = None,
        color: Color | Sequence[Color] | None = None,
        x_value: int = 0,
        exiled_for_cost: CardState | None = None,
        sacrificed_for_cost: list[CardState] | None = None,
        division: Sequence[int] | None = None,
    ) -> AbilityOnStack | None:
        """Finish activating: put the ability on the stack (CR 602.2).

        `division` is CR 601.2d's announced split of a divided effect ("Distribute
        three +1/+1 counters among up to three target creatures"), one share per
        announced target in the same order - the same announcement
        `Casting.announce_division` records for a spell, which CR 602.2b imports
        for an activated ability. `None` leaves the effect's even-split fallback.

        `sacrificed_for_cost` is the sacrifice twin of `exiled_for_cost` -
        the same permanents the caller already handed to `begin_activating`'s
        `sacrificing=`, repeated here because `AbilityOnStack.
        cost_sacrificed_card_ids` is where a resolving effect that asks about
        them (Witch's Oven's "if the sacrificed creature's toughness was 4 or
        greater") can find them again. CR 602.2b pays the cost before this
        object exists, so nothing else on the ability remembers the choice.

        `exiled_for_cost` is the card chosen to pay a cost like Back from the
        Brink's own "Exile a creature card from your graveyard and pay its
        mana cost" (`machines/cost.exile_and_pay_mana_cost_cost`) - the same
        card the caller already handed to `begin_activating`'s `exiling=`,
        repeated here because `AbilityOnStack` is where the resolving effect
        can find it again (CR 601.2b's choice, remembered past the moment it
        was made). `None` for every other ability, which is most of them.

        "To activate an ability is to put it onto the stack and pay its costs, so
        that it will eventually resolve and have its effect." The cost is paid by
        the caller through `begin_activating`; this is the half that produces the
        object on the stack.

        **Mana abilities are the exception.** CR 605.1a: an activated ability is
        a mana ability if it meets all of the following criteria: it doesn't
        require a target, it could add mana to a player's mana pool when it
        resolves, it's not a loyalty ability, and its cost and effect don't move
        any card to or from a library. (The first three were the whole rule
        before the 2026-08-19 release added the library criterion.) The
        criteria are evaluated on the printed text - "Do not take into account
        replacement effects that may apply, other than self-replacement
        effects, when evaluating these criteria" - and the library criterion is
        `moves_a_library_card`. CR 605.3b: a mana ability "doesn't go on the
        stack, so it can't be targeted, countered, or otherwise responded to.
        Rather, it resolves immediately after it is activated" - so the mana
        goes into its controller's pool here and `None` comes back, meaning
        nothing was put on the stack.

        `color` is the colour picked for a mana ability offering a choice (a
        dual land, an "any color" source) - `ManaAbility.resolve` is what
        actually makes the choice and raises its own clear message when one
        is needed but missing, or when the one given is not on offer. It is
        not consulted at all for an ability with only one possible output.
        """
        self._refuse_if_over()
        with self._id_allocator_scope():
            abilities = self.activated_abilities(permanent)
            if index >= len(abilities) and permanent.zone is not Zone.BATTLEFIELD:
                # CR 602.2a/113.7a: the ability was created on the stack as it
                # was announced, and paying its cost - a granted "Sacrifice
                # this artifact" (Supper for Spiders' Food) - moved the source,
                # whose granted lines CR 400.7 has just cleared. The lines it
                # had as it left are that ability's own text.
                abilities = abilities + granted_activated_abilities_of(
                    permanent._granted_as_it_left  # noqa: SLF001
                )
            ability = abilities[index]
            controller = controller or self.controller_of(permanent).username
            # CR 107.3a: a "Reveal X ..." cost's X is the number of cards
            # `begin_activating` revealed, unless the caller announced it.
            announced = self.announced_reveal_counts.pop(
                self._activation_handoff_key(permanent, index), None
            )
            if announced is not None and not x_value:
                x_value = announced

            # CR 601.2c, via CR 602.2b: `begin_activating` announced and checked
            # the targets before the cost was paid (CR 601.2h). Paying it may
            # have made one illegal - Vampire Hexmage sacrificing itself - and
            # nothing rechecks that here; CR 608.2b does, on resolution.
            key = self._activation_key(permanent, index)
            handoff = self._activation_handoff_key(permanent, index)
            entry = self._announced_targets.pop(handoff, None)
            announced_modes = self._announced_modes.pop(handoff, None)
            opened = self._opened_payments.pop(handoff, None)
            paid = opened if opened is not None and opened.step is CostStep.PAID else None
            opened_stamp = self._activation_source_stamps.pop(handoff, None)
            source_stamp = (
                opened_stamp
                if paid is not None and opened_stamp is not None
                else permanent.zone_change_stamp
            )
            if paid is not None and paid.waterbend_generic is not None:
                # CR 701.67c: "An ability that triggers whenever a player
                # waterbends triggers whenever that player pays a waterbend
                # cost, regardless of how they paid that cost." One event
                # per waterbend cost actually paid - mana, taps
                # (`machines/objects_as_costs.waterbend`), or a mix - not one
                # per tap, since a tap is how the cost gets paid, not an
                # event of its own.
                self.record_turn_fact("waterbent", controller)
                self.emit(
                    GameEvent(
                        event=ExtraTriggerEvent.WATERBENDS,
                        subject_id=permanent.id,
                        subject_name=permanent.name,
                        subject_controller=controller,
                        subject_card=permanent.card,
                        player=controller,
                    )
                )
            # Only the announcement whose payment was paid belongs to this
            # activation; one whose payment was rewound or abandoned is stale.
            recorded = entry[0] if entry is not None and entry[1].step is CostStep.PAID else None
            if recorded is not None:
                if targets is not None and [TargetRef.coerce(t) for t in targets] != recorded:
                    raise ValueError(
                        f"{permanent.name}'s targets were already announced as it was "
                        "activated, before its cost was paid (CR 601.2c, CR 602.2b)"
                    )
                targets = list(recorded)
            else:
                # A caller that never went through `begin_activating` announces
                # here instead, against the ability's own text.
                announced_modes = self._announce_activation_modes(
                    permanent, controller, ability, targets
                )
                if announced_modes is not None:
                    targets = [target for slice_ in announced_modes[1] for target in slice_]
                else:
                    announced_targets = self._announce_activation_targets(
                        permanent,
                        controller,
                        self._activation_target_text(ability, x_value, permanent),
                        targets,
                    )
                    if announced_targets is not None:
                        targets = list(announced_targets)
            announced_division = (
                self._check_activation_division(
                    ability,
                    x_value,
                    [TargetRef.coerce(t) for t in targets or []],
                    list(division),
                    permanent,
                )
                if division is not None
                else None
            )
            self.activations[key] = self.activations.get(key, 0) + 1
            if ability.exhaust:
                self.record_turn_fact(
                    ACTIVATED_EXHAUST_FACT, self.controller_of(permanent).username
                )
                # CR 702.177a: "Activate only once" - unlike `activations`
                # above, this is never cleared on a new turn (`exhausted`
                # persists for the object's whole existence on the
                # battlefield). `key` is already `permanent.id`-scoped, so an
                # object that leaves and returns (CR 400.7's new object) gets
                # a fresh id and is not exhausted by its own past self.
                self.exhausted.add(key)
            if read_activation_instructions(ability.instructions).once:
                # CR 602.5b: the printed "Activate only once" - never reset on
                # a new turn, the same bookkeeping exhaust's own reminder
                # "Activate only once" uses just above.
                self.exhausted.add(key)
            if ability.power_up:
                # CR 702.193a's own "Activate this ability only once" - the
                # same bookkeeping as exhaust just above, reused rather than
                # duplicated (see `why_cannot_activate`'s matching check and
                # `ActivatedAbility.power_up`'s own docstring). The *first*
                # activation is recorded under the identical bare `key`
                # exhaust uses, so a power-up card with no Wonder Man on the
                # board dumps identically to before this widening; only a
                # second activation - possible at all once `_power_up_
                # activation_limit` says 2 - gets its own suffixed key, never
                # colliding with `exhaust`'s own bare one.
                if key not in self.exhausted:
                    self.exhausted.add(key)
                else:
                    self.exhausted.add(f"{key}:power-up-extra")
            if ability.loyalty is not None:
                # CR 606.3's once-per-turn rule is per permanent: having activated
                # any loyalty ability of this planeswalker this turn, the next one
                # is refused until a new turn begins.
                self.loyalty_activations[str(permanent.id)] = (
                    self.loyalty_activations.get(str(permanent.id), 0) + 1
                )
                # CR 606.2/602.2: Ajani Unrelenting's own "Whenever you
                # activate a loyalty ability" and Gideon the Oathless's
                # "Whenever an opponent activates a loyalty ability" both
                # watch this same activation, and Kiora of Salt and Sand's
                # "if you've activated a loyalty ability this turn" reads the
                # ledger it feeds.
                self.emit(
                    GameEvent(
                        event=TriggerEvent.LOYALTY_ABILITY_ACTIVATED,
                        subject_id=permanent.id,
                        subject_name=permanent.name,
                        subject_controller=controller,
                        subject_card=permanent.card,
                        player=controller,
                        loyalty_removed=self._loyalty_removed_by(paid, ability, x_value),
                    )
                )
                self.record_turn_fact("loyalty_ability_activated", controller)

            if (
                ability.mana is not None
                and ability.loyalty is None
                and not targets
                and not moves_a_library_card(ability)
            ):
                # All four of CR 605.1a's criteria, and the loyalty one is now
                # checked rather than assumed: a `0: Add {C}{C}{C}.` cost is a
                # loyalty symbol (CR 606.2), which makes the ability a loyalty
                # ability, and a loyalty ability is not a mana ability - it goes
                # on the stack like any other activated ability (CR 602.2,
                # CR 113.3b). The other three: no target announced, an "Add"
                # effect, and nothing in the printed cost or effect moves a card
                # to or from a library. CR 605.3b: no stack at all; the mana lands
                # in the pool immediately.
                land_types = self._controlled_land_types(controller)
                own_counters = frozenset(permanent.counters.counts)
                has_imprinted_card = self.card_imprinted_on(permanent.id) is not None
                # CR 700.5's devotion, for Nykthos, Shrine to Nyx's own "Add an
                # amount of mana of that color equal to your devotion to that
                # color." Counted here rather than on the `ManaAbility` because
                # only the game knows the board (`ManaAbility.
                # amount_from_devotion`'s own docstring), and counted to the
                # colour the activating player just chose, which is what "that
                # color" points back at.
                # `one_named_color` and not `isinstance(color, Color)`: the
                # colour may be named as a one-element sequence, which is what
                # a caller reading `Action.color_choice_count` (1, here) hands
                # back, and that is still one colour chosen. Reading only the
                # bare `Color` left `count` at None on that path and quietly
                # added a single mana where devotion said several.
                devotion_color = one_named_color(color)
                devotion = (
                    devotion_to(self, controller, devotion_color)
                    if ability.mana.amount_from_devotion and devotion_color is not None
                    else None
                )
                # CR 107.3's X, read off the board the moment this ability
                # resolves (CR 605.3b: immediately) - Seance Board's "the
                # number of soul counters on this artifact", Woodland
                # Weavemaster's "this creature's power". `_parse_effect`
                # already refused to build this ability at all if its own
                # "where X is ..." text were not one `resolve_mana_count_
                # expression` can answer, so this is never `None` here.
                count_expression = (
                    ability.mana.any_color_count_expression or ability.mana.for_each_expression
                )
                expression_count = (
                    resolve_mana_count_expression(
                        self,
                        controller,
                        permanent,
                        count_expression,
                        # Mage-Ring Network's counters "removed this way"
                        # (CR 107.3a's announced X) and Slobad's "the
                        # sacrificed artifact" - what this activation paid.
                        x_value,
                        _cost_moved(paid, ComponentKind.SACRIFICE) if paid is not None else (),
                        choosing=True,
                    )
                    if count_expression is not None
                    else None
                )
                # The two board-derived narrowings `ManaAbility.effective` asks
                # for. Without them this fast path resolved the ability against
                # the printed text alone, while `machines/cost.py`'s auto-tap
                # solver - which calls the same `effective` - already narrowed;
                # the two disagreed about what the very same source produces.
                #
                # CR 614.12a's chosen colour (Utopia Sprawl's "As this Aura
                # enters, choose a color", read back by "Add one mana of the
                # chosen color"), recorded on the permanent as it entered.
                chosen = permanent.choice
                chosen_color = (
                    Color(chosen.value)
                    if chosen is not None and chosen.kind is ChoiceKind.COLOR
                    else None
                )
                # CR 106.7's survey, for Reflecting Pool and Exotic Orchard.
                could_produce_colors = (
                    self._could_produce_survey(ability.mana.could_produce, controller)
                    if ability.mana.could_produce is not None
                    else None
                )
                try:
                    produced_mana = ability.mana.resolve(
                        land_types,
                        own_counters,
                        color,
                        has_imprinted_card,
                        count=devotion if devotion is not None else expression_count,
                        could_produce_colors=could_produce_colors,
                        chosen_color=chosen_color,
                        colors_among=colors_among_now(self, controller, ability.mana),
                    )
                    # CR 106.5, for the third narrowing: "of any color among legendary
                    # creatures and planeswalkers you control" (Mox Amber). The colour
                    # the activating player named has to be one the board actually
                    # defines - an empty board defines none, and an ability that would
                    # produce mana of an undefined type produces no mana instead.
                    # `machines/cost.py` already applies this on the payment path; a
                    # direct activation reached the same ability without it, so the
                    # same Mox Amber made nothing when tapped for a spell and one mana
                    # of any colour when activated on its own.
                    allowed = among_colors(ability.effect, self, controller)
                    if allowed is not None:
                        undefined = [
                            produced for produced in produced_mana if produced not in allowed
                        ]
                        if undefined:
                            raise ValueError(
                                f"{permanent.name} cannot add "
                                f"{''.join(f'{{{produced.value}}}' for produced in undefined)}: "
                                f"no permanent it surveys defines that color, so the ability "
                                f"produces no mana (CR 106.5)"
                            )
                except ValueError:
                    # The cost was already paid by the caller (`{T}` tapped the
                    # source). A refused activation returns to the moment before
                    # it began (CR 601.6 / CR 733.1 by analogy), so the source
                    # is not left tapped with no mana to show for it.
                    if paid is not None:
                        paid.rewind()
                    raise

                # CR 106.6: a "Spend this mana only to ..." sentence in this
                # ability's own effect text restricts the mana it just made. The
                # tag goes on the mana in the pool, not on `permanent` - the mana
                # ability has resolved (CR 605.3b) and the mana outlives it, so a
                # source that leaves the battlefield takes nothing back with it.
                # `permanent` is passed only to resolve "the chosen type"
                # (CR 614.12a records the answer on the object that was asked).
                # CR 106.12b: a replacement effect watching a permanent "tapped
                # for mana" modifies this production event as the ability
                # resolves - Damping Sphere's single {C}, Nyxbloom Ancient's
                # three times as much. Only a `{T}` ability is being tapped for
                # mana (CR 106.12).
                if any(piece.kind is CostKind.TAP for piece in ability.costs):
                    produced_mana = replace_mana_production(
                        self, permanent, produced_mana, tapper=controller
                    )
                restriction = spend_restriction(ability.effect, permanent)
                # CR 106.6's other clause, tagged onto the same mana and for the
                # same reason: "have an additional effect that affects the spell
                # or ability that mana is spent on". Arena of Glory's "If that
                # mana is spent on a creature spell, it gains haste until end of
                # turn." is read off the ability's own trailing text by
                # `machines/abilities.parse_mana_abilities`, so there is nothing
                # to re-parse here - the sentence only has to reach the pool.
                spend_effect = (
                    ManaSpendEffect(text=ability.mana.spend_effect)
                    if ability.mana.spend_effect
                    else None
                )
                from_treasure = is_treasure_source(permanent, self)
                from_creature = is_creature_source(permanent, self)
                for produced in produced_mana:
                    self.player(controller).mana_pool.add(
                        produced,
                        restriction=restriction,
                        spend_effect=spend_effect,
                        treasure=from_treasure,
                        creature=from_creature,
                    )
                # CR 405.6c: "If a mana ability both produces mana and has
                # another effect, the mana is produced and the other effect
                # happens immediately." `why_cannot_activate` already refused
                # this activation outright when the rider could not be read, so
                # reaching here means it is either absent or a known shape -
                # Talisman of Resilience's "This artifact deals 1 damage to
                # you." is what taught this engine the shape existed at all.
                self.apply_mana_ability_rider(ability.mana.rider, controller, permanent)
                # CR 106.12: "to 'tap [a permanent] for mana' is to activate a mana
                # ability of that permanent that includes the {T} symbol in its
                # activation cost" - so only a `{T}: ...` ability counts, not
                # Skirk Prospector's sacrifice-only one. CR 106.12a is the event
                # Leyline of Abundance and Utopia Sprawl watch for, even though
                # CR 605.3b means this ability itself never touched the stack
                # (`tapped_for_mana_event`'s own docstring is the other half of
                # this: `CostPayment.tap_for_mana` emits the same event when a
                # source pays for a spell instead of being activated directly).
                set_off: list[AbilityOnStack] = []
                if any(piece.kind is CostKind.TAP for piece in ability.costs):
                    set_off.extend(
                        self.emit(tapped_for_mana_event(permanent, self, mana_added=produced_mana))
                    )
                # CR 605.3a: a mana ability is activated like any other, only
                # without the stack - "whenever you activate an ability" sees it.
                set_off.extend(self.emit(mana_ability_activated_event(permanent, self)))
                if produced_mana:
                    # Not CR 106.12's tap event but its sibling: an ability caused
                    # this player to add mana. Caged Sun's own condition asks about
                    # the adding, not the tapping, so a mana ability with no `{T}`
                    # in its cost raises this one just the same.
                    set_off.extend(
                        self.emit(mana_added_event(permanent, self, mana_added=produced_mana))
                    )
                # CR 605.4a: a triggered mana ability "doesn't go on the stack,
                # so it can't be targeted, countered, or otherwise responded to.
                # Rather, it resolves immediately after the mana ability that
                # triggered it, without waiting for priority" - the tap's own
                # triggers (Leyline of Abundance, battle 7 B7-02) as much as the
                # adding's.
                self.resolve_triggered_mana_abilities(set_off)
                if not self._holding_mana_triggers:
                    self.put_triggers_on_stack()
                return None

            on_stack = AbilityOnStack(
                kind=AbilityKind.ACTIVATED,
                ability=ability,
                source_id=permanent.id,
                source_name=permanent.name,
                # CR 400.7: which object the source was as it was activated
                # (taken before any cost moved it), so "return this creature
                # to its owner's hand" leaves a permanent that has since left
                # and come back alone.
                source_stamp=source_stamp,
                source_times_transformed=permanent.times_transformed,
                controller=controller,
                targets=[TargetRef.coerce(target) for target in targets or []],
                modes=list(announced_modes[0]) if announced_modes is not None else [],
                mode_targets=list(announced_modes[1]) if announced_modes is not None else [],
                x_value=x_value,
                division=announced_division,
                cost_exiled_card_id=exiled_for_cost.id if exiled_for_cost is not None else None,
                # CR 602.2b: the objects the paid cost moved, read off the
                # payment itself when `begin_activating` opened one, so a
                # "`<verb>` this way" count never depends on what the caller
                # chose to repeat here.
                cost_sacrificed_card_ids=(
                    _cost_moved(paid, ComponentKind.SACRIFICE)
                    if paid is not None
                    else tuple(state.id for state in (sacrificed_for_cost or []))
                ),
                cost_exiled_card_ids=(
                    _cost_moved(paid, ComponentKind.EXILE)
                    if paid is not None
                    else ((exiled_for_cost.id,) if exiled_for_cost is not None else ())
                ),
                cost_discarded_card_ids=(
                    _cost_moved(paid, ComponentKind.DISCARD) if paid is not None else ()
                ),
                # CR 601.2h via CR 602.2b: what actually paid this activation's
                # cost, read off the settled payment the same moment the two
                # fields just above are - `CastRecord.mana_spent`'s own twin
                # for an ability, which was never cast and has no such record.
                mana_spent=(
                    dict(paid.mana_payment.spend)
                    if paid is not None and paid.mana_payment is not None
                    else {}
                ),
                treasure_mana_spent=(
                    sum(paid.mana_payment.treasure_spent.values())
                    if paid is not None and paid.mana_payment is not None
                    else 0
                ),
            )
            # CR 608.2h: what each sacrificed permanent's mana value was, taken
            # now - a sacrificed token is still in the graveyard, and ceases to
            # exist (CR 704.5d) before this ability resolves.
            on_stack.cost_sacrificed_mana_values = tuple(
                self.last_known_mana_value(card_id) for card_id in on_stack.cost_sacrificed_card_ids
            )
            on_stack.cost_discarded_mana_values = tuple(
                self.last_known_mana_value(card_id) for card_id in on_stack.cost_discarded_card_ids
            )
            on_stack.cost_sacrificed_color_counts = tuple(
                self._last_known_color_count(card_id)
                for card_id in on_stack.cost_sacrificed_card_ids
            )
            on_stack.cost_sacrificed_powers = tuple(
                self._last_known_stat(card_id, "power")
                for card_id in on_stack.cost_sacrificed_card_ids
            )
            on_stack.cost_sacrificed_toughnesses = tuple(
                self._last_known_stat(card_id, "toughness")
                for card_id in on_stack.cost_sacrificed_card_ids
            )
            on_stack.cost_sacrificed_types = tuple(
                self._last_known_types(card_id) for card_id in on_stack.cost_sacrificed_card_ids
            )
            if paid is not None:
                # CR 602.2b / CR 608.2h: the permanents tapped as part of the cost
                # (not the source's own {T}), and the power each had then.
                on_stack.cost_tapped_card_ids = tuple(
                    card_id
                    for card_id in _cost_moved(paid, ComponentKind.TAP)
                    if card_id != permanent.id
                )
                on_stack.cost_tapped_powers = tuple(
                    self._last_known_stat(card_id, "power")
                    for card_id in on_stack.cost_tapped_card_ids
                )
            self.stack.append(on_stack)
            # CR 602.2b's target announcement has settled (CR 601.2c, imported
            # wholesale), and the ability is on the stack, so anything watching
            # "becomes the target of ... an ability" now has an event to see.
            self._emit_ability_becomes_target(on_stack)
            # CR 602.2: the ability is on the stack and its costs are paid -
            # it has been activated, and it is not a mana ability (CR 605.3b
            # returned above for those). Flamescroll Celebrant's "Whenever an
            # opponent activates an ability that isn't a mana ability" and
            # Immolation Shaman's type-qualified sibling watch this;
            # `origin_zone` is where the source was (CR 109.2).
            self.emit(
                GameEvent(
                    event=ExtraTriggerEvent.ABILITY_ACTIVATED,
                    subject_id=permanent.id,
                    subject_name=permanent.name,
                    subject_controller=controller,
                    subject_card=permanent.card,
                    subject_types=self._activated_source_types(permanent),
                    subject_subtypes=tuple(
                        self.characteristics_of(permanent).subtypes
                        if permanent.zone is Zone.BATTLEFIELD
                        else permanent.subtypes
                    ),
                    # Every ability this method activates is a battlefield
                    # permanent's; `machines/keywords.KeywordActivation` is
                    # the door for one that functions in another zone.
                    origin_zone=Zone.BATTLEFIELD,
                    player=controller,
                )
            )
            # CR 117.3c hands priority straight back, so anything that triggered
            # while the cost was paid goes on the stack now - above the ability.
            self.put_triggers_on_stack()
            return on_stack


from ...machines import game_rule_statics  # noqa: E402
from ...machines.cost.payment import colors_among_now  # noqa: E402
from ...machines.ep02_r1_graveyard_counts import graveyard_count_expression  # noqa: E402
from ._common import _SPEND_AS_ANY_COLOR_STATIC_RE, _SPEND_AS_ANY_COLOR_TO_ACTIVATE_RE  # noqa: E402
from ._conditions import (  # noqa: E402
    _card_type_named,
    _is_minus_symbol,
    _names_match,
    _symbol_threshold_exile_component,
    condition_is_readable,
)
from ._costs_mana import _cost_moved, _cost_refers_to_self  # noqa: E402
from ._zones import _exiles_itself_by_name, moves_a_library_card  # noqa: E402
