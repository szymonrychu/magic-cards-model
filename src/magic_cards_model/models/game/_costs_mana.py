import re
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from functools import cache
from typing import TYPE_CHECKING
from uuid import UUID

from ...data.subtypes import canonical_subtype
from ...machines import combat as combat_rules
from ...machines.abilities import (
    AbilityKind,
    ActivatedAbility,
    CouldProduce,
    ManaAbilityRider,
    granted_mana_abilities,
    parse_abilities,
    parse_mana_abilities,
)
from ...machines.casting import (
    Casting,
    PlayPermission,
    or_additional_cost_alternatives,
)
from ...machines.combat import (
    has_keyword,
)
from ...machines.cost import (
    ComponentKind,
    CostComponent,
    CostModifierEffect,
    CostPayment,
    CostStep,
    TotalCost,
    additional_cost_phrases,
    among_colors,
    mana_candidate_scan,
    plan_mana_payment,
    total_cost_for_phrase,
    why_payer_cannot_use,
)
from ...machines.decisions import (
    Decision,
    DecisionKind,
    NamedManaAbility,
    source_id_of,
)
from ...machines.layers import (
    spend_effect_effects,
)
from ...machines.modes import (
    substitute_x,
)
from ...machines.triggers import (
    added_ability_lines,
    rewritten_ability_lines,
)
from ...machines.unspent_mana import settle_mana_loss
from ..card import (
    Color,
    Type,
)
from ..card_state import (
    CardState,
    ChoiceKind,
    Counter,
    TargetRef,
)
from ..mana import ManaCost, ManaPool, ManaRetentionScope, ManaSpend, SymbolKind
from ..player import Player
from ..zone import Zone

if TYPE_CHECKING:
    from . import Game


#: A cost sentence that names the permanent its ability is printed on -
#: "Exert this land", "Sacrifice this creature". CR 602.1a: an activated
#: ability's source is the object it is printed on, so "this" is that object and
#: only the caller building the cost knows which it is.
_SELF_REFERENCE = re.compile(r"\bthis\b", re.IGNORECASE)
_OTHER_THAN_THIS = re.compile(r"\bother than this \w+", re.IGNORECASE)


def _cost_refers_to_self(text: str, permanent: CardState) -> bool:
    """Whether a printed cost sentence names *this* permanent (CR 602.1a).

    Most printings use the generic "this <type>" `_SELF_REFERENCE` already
    reads, but some (The Filigree Sylex's "{T}, Sacrifice The Filigree
    Sylex: ...", Grist, the Hunger Tide's short "Grist" before the comma)
    name the permanent's own printed name instead - CR 201.5: "Text that
    refers to the object it's on by name means just that particular object."
    Checked as a whole word, not a bare substring, so a shorter card's name
    that happens to be a prefix of another word in the cost sentence is never
    mistaken for a reference.

    `_exiles_itself_by_name` below is the same CR 201.5 self-reference,
    narrowed to the one shape `cost_component_for_phrase`'s `_PHRASE_EXILE`
    needs it exactly-matched for (The Stone Brain's "Exile The Stone Brain",
    Abstergo Entertainment's "Exile Abstergo Entertainment") - this function
    stays the general "does this cost sentence refer to `permanent` at all"
    question the `SACRIFICE`/`DISCARD` and generic `OTHER` self-reference
    fill-ins below ask.
    """
    # "other than this creature" (Mossbridge Troll) names the source only to
    # leave it out of the choice, so it is not the cost's own self-reference.
    text = _OTHER_THAN_THIS.sub("", text)
    if _SELF_REFERENCE.search(text):
        return True
    front = permanent.card.name.split("//")[0].strip()
    names = {front}
    if "," in front:
        names.add(front.split(",", 1)[0].strip())
    return any(name and re.search(rf"\b{re.escape(name)}\b", text) for name in names)


def _cost_moved(payment: CostPayment, kind: ComponentKind) -> tuple[UUID, ...]:
    """The ids of the objects a paid `payment`'s `kind` components moved -
    Corpseweft's exiled creature cards, Radiant Lotus's sacrificed
    artifacts - in payment order."""
    return tuple(
        state.id
        for component in payment.components
        if component.kind is kind
        for state in component.cards
    )


#: CR 601.2f cost reduction of the shape Emrakul, the Promised End prints.
#: Narrow on purpose: the amount, and the thing being counted, are both read
#: back out and anything else is left alone rather than guessed at.
_COSTS_LESS_PER_CARD_TYPE = re.compile(
    r"costs \{(\d+)\} less to cast for each card type among cards in your graveyard",
    re.IGNORECASE,
)

#: "This spell costs {N} less to cast for each `<quality>` card in your
#: graveyard." - The Dawning Archaic's "for each instant and sorcery card":
#: every card in the caster's graveyard that is any one of the named types
#: (CR 205.2a) counts once. The quality is read by `machines/effects.
#: _quality_matcher`, with the printed "and" meaning "or" for one card (no
#: card is both an instant and a sorcery).
_COSTS_LESS_PER_QUALITY_CARD_IN_GRAVEYARD_RE = re.compile(
    r"costs \{(\d+)\} less to cast for each (?P<quality>(?!card type)[a-z,/ ]+?) card "
    r"in your graveyard",
    re.IGNORECASE,
)

#: CR 601.2f's *other* self-referential reduction shape: "This spell costs
#: `<mana>` less to cast if it targets a(n) `<quality>` spell." - Mystical
#: Dispute's "{2} ... a blue spell", Out of Air's "{2} ... a creature spell",
#: Brush Off's "{1}{U} ... an instant or sorcery spell". Unlike Emrakul's row
#: above, the condition is not a fact about the board - it is about *this
#: spell's own announced target* (CR 601.2c), which is chosen before the cost
#: is determined (CR 601.2f is a later step), so this is read against
#: `Casting.targets` rather than the battlefield. The amount is a run of mana
#: symbols, coloured ones included, and lands on the cost by CR 118.7; the
#: quality is `machines/next_spell.spell_has_quality`'s (colour words, card
#: types, CR 205.1's "instant and sorcery" read as either). Only a *spell*
#: target qualifies - "if it targets a tapped creature" is a different shape.
_COSTS_LESS_IF_TARGETS_SPELL_RE = re.compile(
    r"costs (?P<amount>(?:\{[^{}]+\})+) less to cast if it targets an? "
    r"(?P<quality>[a-z ,]+?) spell\b",
    re.IGNORECASE,
)

#: The permanent twin of `_COSTS_LESS_IF_TARGETS_SPELL_RE`: "This spell
#: costs `<mana>` less to cast if it targets a(n) `<description>`." with any
#: description the target grammar reads - Bouncer's Beatdown's "a black
#: permanent", Ajani's Response's "a tapped creature", Hunter's Mark's "a blue
#: permanent you don't control". Read against `Casting.targets`, which CR
#: 601.2c fixes before CR 601.2f determines the cost. Tried only when the
#: spell shape above did not match.
_COSTS_LESS_IF_TARGETS_DESCRIPTION_RE = re.compile(
    r"costs (?P<amount>(?:\{[^{}]+\})+) less to cast if it targets an? "
    r"(?P<description>[^.]+?)\.",
    re.IGNORECASE,
)

#: CR 601.2f's general "if <board condition>" self reduction: "This spell
#: costs {1} less to cast if you control a legendary creature." (Wrath of the
#: Bloodmane) and "This spell costs {2} less to cast if you've cast a
#: noncreature spell this turn." (Traxos, Academy Guardian). Unlike the two
#: rows above - Emrakul's own per-card-type count and Mystical Dispute's own
#: announced-target reading - this is not a shape of its own: it hands the
#: condition straight to `condition_holds`, the same reader "Activate only if
#: <condition>" (CR 602.5b) and a modal "If <condition>, choose N instead"
#: (CR 700.2) already use, so every board condition that reader can already
#: answer works here too rather than needing its own copy. A condition
#: `condition_holds` does not recognise is read as false, the same fail-
#: closed default an activation restriction gets, rather than a reduction
#: applied on a guess.
#: "As long as" is the same gate worded as a duration - Drag to the Roots'
#: "This spell costs {2} less to cast as long as there are four or more card
#: types among cards in your graveyard." - read the same way, as the cost is
#: determined.
_COSTS_LESS_IF_CONDITION_RE = re.compile(
    r"this spell costs \{(?P<amount>\d+)\} less to cast (?:if|as long as) "
    r"(?P<condition>[^.]+)\.",
    re.IGNORECASE,
)

#: "This spell costs {X} less to cast, where X is the greatest toughness
#: among creatures you control." (Ghalta the Immovable), the power sibling
#: (Ghalta the Unstoppable). Unlike every other row here, the amount is
#: itself CR 601.2f's counted quantity rather than a printed multiplier on
#: one - the same "greatest power/toughness among creatures you control"
#: bound `machines/casting._GREATEST_AMONG_CREATURES` already reads for
#: Soul Immolation's blight-X cap, read again here for the reduction itself.
_COSTS_LESS_X_WHERE_X_IS_GREATEST_STAT_RE = re.compile(
    r"this spell costs \{x\} less to cast,? where x is the greatest "
    r"(?P<stat>power|toughness) among creatures you control",
    re.IGNORECASE,
)

#: "This spell costs {X} less to cast, where X is the total power of
#: creatures you control with flying." (The Lord of the Eagles) and Ghalta,
#: Primal Hunger's own unqualified "This spell costs {X} less to cast, where
#: X is the total power of creatures you control." - CR 601.2f's counted
#: quantity again, this time a *sum* over the caster's own creatures (all of
#: them, or a keyword-filtered subset) rather than Ghalta the Immovable's
#: single greatest stat. `combat.has_keyword` is the one place this engine
#: already answers "does this permanent have `<keyword>` right now" (CR 702,
#: CR 613.5's layers included), reused here rather than re-derived.
_COSTS_LESS_X_WHERE_X_IS_TOTAL_POWER_WITH_KEYWORD_RE = re.compile(
    r"this spell costs \{x\} less to cast,? where x is the total power of "
    r"creatures you control(?: with (?P<keyword>[a-z]+))?",
    re.IGNORECASE,
)

#: Sunderflock's own shape: "This spell costs {X} less to cast, where X is
#: the greatest mana value among Elementals you control." A general fallback
#: for whatever `_COSTS_LESS_X_WHERE_X_IS_GREATEST_STAT_RE`'s and `_COSTS_
#: LESS_X_WHERE_X_IS_TOTAL_POWER_WITH_KEYWORD_RE`'s own narrower shapes miss
#: - a subtype qualifier, a mana-value stat, or any other expression
#: `machines/effects.amount_expression` already reads for a resolution-time
#: amount - evaluated here with the identical text `cost_reduction_for`
#: already has in hand, so both readers stay in exact agreement about what
#: "the greatest `<stat>` among `<qualifier>` you control" means.
_COSTS_LESS_X_WHERE_X_IS_RE = re.compile(
    r"this spell costs \{x\} less to cast,? where x is (?P<expr>[^.\n]+)",
    re.IGNORECASE,
)

#: Shadow of Mortality's own shape: "If your life total is less than your
#: starting life total, this spell costs {X} less to cast, where X is the
#: difference." A leading CR 601.2f condition (unlike every other row here,
#: this one is never open text `condition_holds` has to read - it is always
#: this one comparison) paired with a variable amount that is the plain gap
#: between the caster's current and starting (CR 103.4) life totals - "the
#: difference" is symmetric, so `greater than` is read too rather than
#: assuming which side of the comparison a future printing states.
_COSTS_LESS_IF_LIFE_TOTAL_VS_STARTING_X_IS_DIFFERENCE_RE = re.compile(
    r"if your life total is (?P<cmp>less|greater) than your starting life total, "
    r"this spell costs \{x\} less to cast,? where x is the difference",
    re.IGNORECASE,
)

#: CR 601.2f's per-turn-history reduction: "This spell costs {2} less to cast
#: for each card you've cycled or discarded this turn." (Hollow One, text
#: confirmed with `resolve_cards` this session). Unlike Emrakul's row above,
#: what is counted is not a zone but a *history* - CR 701.9a's discards, and
#: CR 702.29a's cycling, which discards the card to pay an activation cost and
#: so is one and the same event (CR 702.29d says the pair "cycles or discards"
#: fires "only once when a card is cycled"). `Game.cards_discarded_this_turn`
#: is the counter; nothing else in the engine remembers this.
_COSTS_LESS_PER_CARD_DISCARDED_RE = re.compile(
    r"costs \{(\d+)\} less to cast for each card you'?ve cycled or discarded this turn",
    re.IGNORECASE,
)

#: The *domain* shape: "This spell costs {N} less to cast for each basic land
#: type among lands you control." (Scion of Draco at {2}, Leyline Binding at
#: {1} - both confirmed with `resolve_cards` this session). "Domain" is an
#: ability word and has no rule of its own beyond CR 207.2c ("Ability words
#: ... have no special rules meaning"), so the em-dashed word is deliberately
#: outside the match and only the sentence it labels is read. CR 305.6 fixes
#: the five types being counted: "The basic land types are Plains, Island,
#: Swamp, Mountain, and Forest."
_COSTS_LESS_PER_BASIC_LAND_TYPE_RE = re.compile(
    r"costs \{(\d+)\} less to cast for each basic land type among lands you control",
    re.IGNORECASE,
)

#: Obsidian Charmaw's own board-count shape (text confirmed with
#: `resolve_cards` this session): "This spell costs {1} less to cast for each
#: land your opponents control that could produce {C}." "Could produce" is
#: CR 106.7: "The type of mana a permanent could produce at any time includes
#: any type of mana that an ability of that permanent would produce if the
#: ability were to resolve at that time" - so this is asked of the land's mana
#: abilities, not of any mana actually made.
_COSTS_LESS_PER_OPPONENT_COLORLESS_LAND_RE = re.compile(
    r"costs \{(\d+)\} less to cast for each land your opponents control "
    r"that could produce \{C\}",
    re.IGNORECASE,
)


#: CR 702.41a's affinity, read off the keyword line rather than off its
#: reminder text (which is CR 207.2 italics with no game function): "Affinity
#: is a static ability that functions while the spell with affinity is on the
#: stack. 'Affinity for [text]' means 'This spell costs {1} less to cast for
#: each [text] you control.'" The amount is always {1} - it is fixed by the
#: rule, not printed - so unlike every other row here there is no group to
#: read it out of.
_AFFINITY_RE = re.compile(r"\baffinity for (?P<what>[A-Za-z]+)", re.IGNORECASE)


#: A printed self reduction `Game.cost_reduction_for` computes whatever the
#: board holds - the counted shapes and the announced-target one above, but
#: not `_COSTS_LESS_IF_CONDITION_RE`, whose condition `condition_holds` may
#: not read. An ability word ahead of it ("Domain - ", CR 207.2c) is only a
#: label.
_SELF_COST_REDUCTION_SHAPES = (
    _COSTS_LESS_PER_CARD_TYPE,
    _COSTS_LESS_PER_QUALITY_CARD_IN_GRAVEYARD_RE,
    _COSTS_LESS_PER_CARD_DISCARDED_RE,
    _COSTS_LESS_PER_BASIC_LAND_TYPE_RE,
    _COSTS_LESS_PER_OPPONENT_COLORLESS_LAND_RE,
    _COSTS_LESS_IF_TARGETS_SPELL_RE,
    _COSTS_LESS_X_WHERE_X_IS_GREATEST_STAT_RE,
    _COSTS_LESS_X_WHERE_X_IS_TOTAL_POWER_WITH_KEYWORD_RE,
)


#: The self-reduction sentences `machines/cost/statics.py`'s readers price
#: (CR 601.2f), each tried only for a line no earlier row in this module reads:
#: "for each <count>" (with Valiant Changeling's cap), "where X is <expr>",
#: "if <condition>" after the amount, and Avatar of Might's leading
#: "If <condition>, this spell costs ... less". The amount is a run of symbols
#: - one `{1}`-style unit or one coloured `{U}` per counted object.
_SELF_EACH_RE = re.compile(
    r"^this spell costs (?P<amount>(?:\{[^{}]+\})+) less to cast for each (?P<each>[^.]+?)\."
    r"(?: this effect can't reduce the amount of mana this spell costs by more than "
    r"(?P<cap>\{\d+\})\.)?$",
    re.IGNORECASE,
)
_SELF_WHERE_RE = re.compile(
    r"^this spell costs \{x\} less to cast,? where x is (?P<expr>[^.]+)\.$", re.IGNORECASE
)
_SELF_IF_AFTER_RE = re.compile(
    r"^this spell costs (?P<amount>(?:\{[^{}]+\})+) less to cast (?:if|as long as) "
    r"(?P<cond>[^.]+)\.$",
    re.IGNORECASE,
)
_SELF_IF_BEFORE_RE = re.compile(
    r"^if (?P<cond>[^,]+), this spell costs (?P<amount>(?:\{[^{}]+\})+) less to cast\.$",
    re.IGNORECASE,
)


def _claimed_by_earlier_self_reduction(line: str) -> bool:
    """Whether a row above already prices `line` (so `self_reduction_reader`
    must not price it a second time)."""
    if reads_self_cost_reduction_line_earlier(line):
        return True
    if _COSTS_LESS_IF_TARGETS_SPELL_RE.search(line) or _COSTS_LESS_IF_TARGETS_DESCRIPTION_RE.search(
        line
    ):
        return True
    from ...machines.vivid import COSTS_LESS_PER_COLOR_AMONG_RE

    # Vivid's own reduction, whether or not the "Vivid - " label was stripped.
    return COSTS_LESS_PER_COLOR_AMONG_RE.search(line) is not None or "vivid" in line.lower()


@cache
def self_reduction_reader(line: str):  # noqa: ANN201 - a CostContext -> ManaCost reader
    """One "This spell costs ... less to cast ..." line as a reader over a
    `CostContext`, or `None` when it is not a shape this reads (or an earlier
    row already prices it). The one entry both `Game.cost_reduction_for` (to
    price it at CR 601.2f) and the static audit (to credit it) call."""
    from ...machines.cost.statics import cost_condition, cost_count, cost_expression

    # Reminder text (CR 207.2 italics) has no game function: "(Your party
    # consists of ...)" is not part of the sentence read.
    text = re.sub(r"\s*\([^)]*\)", "", line).strip()
    if _claimed_by_earlier_self_reduction(text):
        return None
    each = _SELF_EACH_RE.match(text)
    if each is not None:
        count = cost_count(each.group("each"))
        unit = ManaCost.try_parse(each.group("amount"))
        if count is None or unit is None:
            return None
        cap = each.group("cap")
        cap_value = int(cap.strip("{}")) if cap else None

        def per_count(ctx):
            n = count(ctx)
            if cap_value is not None:
                n = min(n, cap_value // max(unit.converted, 1))
            return ManaCost.parse(each.group("amount") * n) if n > 0 else ManaCost()

        return per_count
    where = _SELF_WHERE_RE.match(text)
    if where is not None:
        expr = cost_expression(where.group("expr"))
        if expr is None:
            return None
        return lambda ctx: ManaCost.parse(f"{{{expr(ctx)}}}") if expr(ctx) > 0 else ManaCost()
    conditional = _SELF_IF_AFTER_RE.match(text) or _SELF_IF_BEFORE_RE.match(text)
    if conditional is not None:
        holds = cost_condition(conditional.group("cond"))
        unit = ManaCost.try_parse(conditional.group("amount"))
        if holds is None or unit is None:
            return None
        return lambda ctx: unit if holds(ctx) else ManaCost()
    return None


def reads_self_cost_reduction_line_earlier(text: str) -> bool:
    """Whether one printed line is wholly a "This spell costs {N} less to
    cast ..." reduction `Game.cost_reduction_for` computes (CR 601.2f) -
    `support.py`'s credit for it on a permanent card, whose line is read as a
    static (CR 604.2) rather than as part of a spell's resolution.

    Dreaded Bat-Cloud's own general "if `<condition>`"/"as long as
    `<condition>`" shape (`_COSTS_LESS_IF_CONDITION_RE`) is not in
    `_SELF_COST_REDUCTION_SHAPES` above - unlike every row there, its
    condition is open text `condition_holds` may or may not recognise, so it
    is credited here only once `condition_is_readable` has actually vouched
    for that particular condition (Morbid's own "a creature died this turn"
    among them), the same fail-closed posture `cost_modifier_effect`'s own
    "as long as" tail already takes in `machines/cost.py`.

    Sunderflock's own "This spell costs {X} less to cast, where X is the
    greatest mana value among Elementals you control." (and Hearth
    Elemental's "... where X is the number of cards in your graveyard that
    are instant cards, sorcery cards, and/or have an Adventure.") are
    `_COSTS_LESS_X_WHERE_X_IS_RE`'s own general fallback, not in
    `_SELF_COST_REDUCTION_SHAPES` for the identical reason: `expr` is open
    text, credited only once `machines/effects.amount_expression` - the exact
    reader `Game.cost_reduction_for` itself calls for this shape - actually
    returns something for it, never on the strength of the regex match alone.
    """
    line = _ABILITY_WORD_PREFIX_RE.sub("", text.strip(), count=1)
    for shape in _SELF_COST_REDUCTION_SHAPES:
        pattern = shape.pattern
        if not pattern.lower().startswith("this spell"):
            pattern = f"this spell {pattern}"
        if re.fullmatch(rf"{pattern}\.?", line, re.IGNORECASE):
            return True
    generic_where_x = re.fullmatch(
        rf"{_COSTS_LESS_X_WHERE_X_IS_RE.pattern}\.?", line, re.IGNORECASE
    )
    if generic_where_x is not None:
        from ...machines.effects import amount_expression

        return amount_expression(generic_where_x.group("expr")) is not None
    if re.fullmatch(
        rf"{_COSTS_LESS_IF_LIFE_TOTAL_VS_STARTING_X_IS_DIFFERENCE_RE.pattern}\.?",
        line,
        re.IGNORECASE,
    ):
        return True
    condition_match = _COSTS_LESS_IF_CONDITION_RE.fullmatch(line)
    return condition_match is not None and condition_is_readable(condition_match.group("condition"))


def reads_self_cost_reduction_line(text: str) -> bool:
    """`reads_self_cost_reduction_line_earlier`'s rows, plus the sentences
    `self_reduction_reader` prices - what `support.py` credits on a permanent."""
    line = _ABILITY_WORD_PREFIX_RE.sub("", text.strip(), count=1)
    return (
        reads_self_cost_reduction_line_earlier(text)
        # Swampsnare Trap's "if it targets a creature with flying": priced by
        # `cost_reduction_for` from `Casting.targets` (CR 601.2c before 601.2f).
        or (
            line.lower().startswith("this spell")
            and _COSTS_LESS_IF_TARGETS_DESCRIPTION_RE.search(line) is not None
        )
        or self_reduction_reader(line) is not None
    )


#: What "[text]" in CR 702.41a's "Affinity for [text]" can name, mapped to the
#: thing to count on the battlefield. Card types (CR 205.2a) on the left of the
#: split, basic land types (CR 305.6) on the right; anything else is left
#: unread rather than guessed at, so an affinity variant this does not know
#: reduces nothing instead of reducing wrongly.
_AFFINITY_CARD_TYPES: dict[str, Type] = {
    "artifacts": Type.ARTIFACT,
    "creatures": Type.CREATURE,
    "enchantments": Type.ENCHANTMENT,
    "lands": Type.LAND,
}
_AFFINITY_SUBTYPES: dict[str, str] = {
    "plains": "Plains",
    "islands": "Island",
    "swamps": "Swamp",
    "mountains": "Mountain",
    "forests": "Forest",
}


def _named_mana_abilities(answer: object) -> tuple[NamedManaAbility, ...]:
    """The mana abilities of any cost a `PAY_MANA` answer named (CR 605.3a),
    beside the offered source ids it may also name."""
    if not isinstance(answer, tuple):
        return ()
    return tuple(entry for entry in answer if isinstance(entry, NamedManaAbility))


def _activate_named_mana_abilities(
    game: "Game", payment: CostPayment, named: Sequence[NamedManaAbility]
) -> None:
    """Activate each mana ability a `PAY_MANA` answer named, in order, into
    `payment` (CR 605.3a, `CostPayment.activate_mana_ability`)."""
    for entry in named:
        source = game.find_by_id(entry.card_id)
        if not isinstance(source, CardState) or source.zone is not Zone.BATTLEFIELD:
            raise ValueError(
                f"{entry.card_id} is not a permanent on the battlefield whose mana "
                "ability can be activated (CR 605.3a)"
            )
        payment.activate_mana_ability(source, entry.ability_index, color=list(entry.colors) or None)


#: A sentence of the same family this engine cannot read - matched only to
#: fail closed with a notice, the way `_LOOKS_LIKE_HASTE_ACTIVATION_PERMISSION_RE`
#: does for its own family. Scoped to activation: an unscoped "You may spend
#: mana as though it were mana of any color." is a different permission (it
#: reaches spells too) and is not this reader's.
_LOOKS_LIKE_SPEND_AS_ANY_COLOR_TO_ACTIVATE_RE = re.compile(
    r"^you may spend mana as though it were mana of any \w+ to activate\b", re.IGNORECASE
)


class CostsManaMixin:
    # -- turn-based actions (CR 703) ---------------------------------------

    def empty_mana_pools(
        self: "Game", *, expiring: "frozenset[ManaRetentionScope] | None" = None
    ) -> None:
        """Empty every player's mana pool (CR 500.5, 703.4q).

        "As a step or phase ends ... any unspent mana left in a player's mana
        pool empties." A turn-based action: automatic, controlled by no player,
        and never on the stack. The player is said to lose this mana (CR 106.4).

        `expiring` is threaded straight through to `ManaPool.empty` - a
        firebending or Photon, Mighty Marvel style "you don't lose this mana
        as steps and phases end" tag keeps mana past this ordinary call and
        only empties at its own named point (CR 500.5a's end of the combat
        phase, passed here by `_advance_past_checks`/`advance_to`; CR
        500.5b/514.2's cleanup step, passed by `cleanup_step`). Left out, no
        scope expires and every retained tag survives, exactly as an ordinary
        mid-phase boundary should leave it. A permanent's own static that
        replaces the loss - "If you would lose unspent mana, that mana becomes
        <colour> instead", "You don't lose unspent <colour> mana as steps and
        phases end" - is read by `machines/unspent_mana`, not tagged on the
        mana: it holds only while its source is on the battlefield.
        """
        scopes = expiring or frozenset()
        for player in self.players:
            # CR 106.4/614.1a: the player is said to *lose* this mana, and a
            # static that replaces that loss ("If you would lose unspent
            # mana, that mana becomes black instead", "You don't lose unspent
            # red mana as steps and phases end") decides what stays -
            # `machines/unspent_mana.settle_mana_loss`, CR 616.1 order and all.
            keep, becomes = settle_mana_loss(
                self, player.username, player.mana_pool, frozenset(scopes)
            )
            player.mana_pool.empty(expiring=scopes, keep=keep, becomes=becomes)

    def spends_mana_as_any_color(
        self: "Game", permanent: CardState, ability: ActivatedAbility, controller: str
    ) -> bool:
        """Whether `controller` may spend mana as though it were mana of any
        color to activate this ability of `permanent` (CR 609.4b).

        Read off every battlefield permanent's printed static lines on every
        call (CR 604.2, CR 611.3a), gated on `_still_has_static_line` (CR
        613.1f), and only for the source's own controller - "you control" and
        "you may" are both the source's controller (CR 109.5).

        - "... to activate abilities of creatures you control" reaches any
          ability of a permanent that is, on the computed board (CR 613.5), of
          one of the named card types and controlled by that player.
        - "... to activate those abilities" reaches only the abilities the
          sentence just before it grants - `layers.all_activated_abilities_
          grant` read again here, so the two cannot disagree about which
          abilities "those" are.
        """
        if permanent.zone is not Zone.BATTLEFIELD:
            return False
        if self.controller_of(permanent).username != controller:
            return False
        if any(scope is None for _source, scope in self._spend_as_any_color_grants(controller)):
            # An unscoped sentence (Chromatic Orrery, Mycosynth Lattice)
            # reaches abilities as well as spells.
            return True
        for source in list(self.battlefield):
            if self.controller_of(source).username != controller:
                continue
            for line in parse_abilities(source.card):
                if line.kind is not AbilityKind.STATIC:
                    continue
                text = (line.text or "").strip()
                sentences = [part for part in re.split(r"(?<=\.)\s+", text) if part]
                for position, sentence in enumerate(sentences):
                    if not _LOOKS_LIKE_SPEND_AS_ANY_COLOR_TO_ACTIVATE_RE.match(sentence):
                        continue
                    match = _SPEND_AS_ANY_COLOR_TO_ACTIVATE_RE.match(sentence)
                    if match is None:
                        self._record_unread_static_line(source, text)
                        continue
                    if not self._still_has_static_line(source, text):
                        continue
                    if match.group("those") is not None:
                        if self._granted_by_preceding_sentence(
                            source, sentences[:position], permanent, ability
                        ):
                            return True
                        continue
                    if match.group("other") is not None and permanent.id == source.id:
                        continue
                    words = [
                        word.strip()
                        for word in match.group("subjects")
                        .lower()
                        .replace(" and ", ", ")
                        .split(",")
                        if word.strip()
                    ]
                    types = [_card_type_named(word) for word in words]
                    if not types or any(kind is None for kind in types):
                        self._record_unread_static_line(source, text)
                        continue
                    if any(
                        kind is not None and self._has_computed_type(permanent, kind)
                        for kind in types
                    ):
                        return True
        return False

    def _spend_as_any_color_grants(
        self: "Game", player: str
    ) -> Iterator[tuple[CardState, str | None]]:
        """Every battlefield permanent's CR 609.4b sentence ("You may spend
        mana as though it were mana of any color[ to cast <quality> spells].",
        or its "Players may" form) that applies to `player`, as `(source,
        scope quality or None)`. Gated on `_still_has_static_line` (CR 613.1f)."""
        for source in list(self.battlefield):
            mine = self.controller_of(source).username == player
            for line in parse_abilities(source.card):
                if line.kind is not AbilityKind.STATIC:
                    continue
                text = (line.text or "").strip()
                for sentence in (part for part in re.split(r"(?<=\.)\s+", text) if part):
                    match = _SPEND_AS_ANY_COLOR_STATIC_RE.match(sentence)
                    if match is None:
                        continue
                    if match.group("who").lower() == "you" and not mine:
                        continue
                    if not self._still_has_static_line(source, text):
                        continue
                    yield source, (match.group("scope") or None)

    def spends_mana_as_any_color_for_spell(self: "Game", spell: CardState, caster: str) -> bool:
        """Whether `caster` may spend mana as though it were mana of any color
        to cast `spell` (CR 609.4b): an unscoped permission always, a scoped
        one when `spell` has the quality it names ("planeswalker", "Case")."""
        from ...machines.casting import linked_exile_play_grant
        from ...machines.next_spell import spell_has_quality

        for _source, scope in self._spend_as_any_color_grants(caster):
            if scope is None or spell_has_quality(spell, scope.lower()):
                return True
        # Rogue Class's and Evelyn's "... and you may spend mana as though it
        # were mana of any color to cast those spells / it": the cards of the
        # pile the same sentence opens to play.
        grant = linked_exile_play_grant(self, spell, caster, land=False)
        return grant is not None and grant.line.any_color

    @staticmethod
    def _resulting_mana_value(card: CardState, option: str | None) -> int:
        """The mana value the spell would have on the stack cast as `option`
        with X of 0 (CR 202.3d, CR 202.3e): the named half's or Adventure's own
        mana cost (CR 709.3b, CR 715.3b), otherwise the card's."""
        if option is not None:
            for face in card.card.card_faces or []:
                if face.name == option:
                    return ManaCost.parse(face.mana_cost or "").converted
        return int(card.card.cmc or 0)

    def _cost_candidates(
        self: "Game", component: CostComponent, caster: str
    ) -> list[CardState] | None:
        """The objects `caster` could choose to pay one cost component, or
        `None` for a component that names no objects. A sacrificed or tapped
        permanent is one `caster` controls (CR 701.21a, CR 107.5), a discard
        comes from their hand (CR 701.9a), an exile from the zone the cost
        names (CR 406.2), each narrowed by what the cost says (CR 118.3)."""
        player = self.player(caster)
        if component.kind is ComponentKind.SACRIFICE:
            pool = list(self.permanents_controlled_by(caster))
        elif component.kind is ComponentKind.TAP:
            pool = [state for state in self.permanents_controlled_by(caster) if not state.tapped]
        elif component.kind is ComponentKind.DISCARD:
            pool = list(player.hand)
        elif component.kind is ComponentKind.EXILE:
            pool = (
                list(player.cards_in(component.zone))
                if component.zone in (Zone.HAND, Zone.GRAVEYARD, Zone.LIBRARY)
                else []
            )
        elif component.kind is ComponentKind.BEHOLD:
            # CR 701.4a: a hand card to reveal, or a battlefield permanent to
            # choose - the same "either zone" pool `_behold_or_tapped`
            # (`machines/replacement.py`) builds for the ETB shape of the
            # same choice.
            pool = list(player.hand) + list(self.permanents_controlled_by(caster))
        else:
            return None
        if component.requirement is not None:
            pool = [
                state
                for state in pool
                if component.requirement.why_not(state, self, caster) is None
            ]
        return pool

    def _cost_objects_available(
        self: "Game", cost: TotalCost, caster: str, taken: set[UUID]
    ) -> bool:
        """CR 118.3 for a cost's objects and life: enough of each, not
        counting objects already chosen for another cost in `taken`."""
        life = self.player(caster).life
        for component in cost.components:
            if component.kind is ComponentKind.PAY_LIFE:
                life -= component.amount
                if life < 0 or (component.amount > 0 and component.why_not(self) is not None):
                    return False
                continue
            pool = self._cost_candidates(component, caster)
            if pool is None or not component.required or component.cards:
                continue
            if len([state for state in pool if state.id not in taken]) < component.required:
                return False
        return True

    def or_cost_choices_for_judging(self: "Game", card: CardState, caster: str) -> dict[int, int]:
        """Which alternative of each CR 601.2b "[cost] or [cost]" additional cost
        to judge `card`'s castability by. An object alternative that can be
        paid is chosen over a mana default - it adds no mana, so it is never
        harder to afford (Deadly Precision with a creature and a single Swamp)
        - and over a life default only when the life cannot be paid (Bitter
        Triumph at 2 life judged by its discard). A sentence no alternative of
        which is payable keeps its default, so the judgement fails on it.
        """
        chosen: dict[int, int] = {}
        taken: set[UUID] = set()
        for index, printed in enumerate(additional_cost_phrases(card.card)):
            alternatives = or_additional_cost_alternatives(substitute_x(printed, 0))
            if alternatives is None:
                continue
            costs = [total_cost_for_phrase(alt, caster) for alt in alternatives]
            default = costs[-1]
            if (
                not alternatives[-1].startswith("{")
                and default is not None
                and self._cost_objects_available(default, caster, taken)
            ):
                continue
            for pick, option in enumerate(costs[:-1]):
                if option is not None and self._cost_objects_available(option, caster, taken):
                    chosen[index] = pick
                    break
        return chosen

    def _cost_payable_on_top_of(
        self: "Game", casting: Casting, extra: TotalCost, caster: str, taken: set[UUID]
    ) -> bool:
        """Whether `extra` can be paid on top of what the cast already owes:
        its objects (`_cost_objects_available`) and the mana of both together
        from the caster's untapped mana sources (CR 118.3, CR 608.2g)."""
        if not self._cost_objects_available(extra, caster, taken):
            return False
        mana = casting.total_cost.mana.plus(extra.mana)
        if not mana.symbols:
            return True
        sources = self._mana_sources_while_resolving(self.player(caster))
        return plan_mana_payment(mana, sources, game=self, payer=caster) is not None

    def _pay_resolution_cast_mana(
        self: "Game", casting: Casting, payment: CostPayment, card: CardState, caster: str
    ) -> None:
        """CR 601.2g-h inside CR 608.2g: mana still owed on a cast made during
        resolution - an additional cost (kicker) or a cost increase applied to
        "without paying its mana cost" (CR 118.9d, Disruptor Flute's {3}) - is
        paid by activating mana abilities now (CR 117.1d, CR 608.2g's first
        sentence). Asked as the same `PAY_MANA` question an "unless ... pays"
        is, offering the caster's untapped mana sources; declining, or a cost
        those sources cannot pay (CR 118.3), makes the cast illegal (CR 601.2)."""
        payer = self.player(caster)
        mana = casting.total_cost.mana
        sources = self._mana_sources_while_resolving(payer)
        payable = plan_mana_payment(mana, sources, game=self, payer=caster) is not None
        answer = self.ask(
            Decision(
                kind=DecisionKind.PAY_MANA,
                player=caster,
                prompt=f"pay {mana} to cast {card.name}",
                source=card.name,
                source_id=source_id_of(card),
                amount=mana.converted,
                affirmative_is_legal=payable,
                mana_sources=tuple(state.id for state in sources),
            )
        )
        if answer is False:
            raise ValueError(f"{caster} did not pay {mana} to cast {card.name} (CR 601.2h)")
        chosen = (
            sources if answer is True else [state for state in sources if state.id in set(answer)]
        )
        _activate_named_mana_abilities(self, payment, _named_mana_abilities(answer))
        payment.auto_tap(chosen)

    def _offer_additional_cost(
        self: "Game",
        casting: Casting,
        card: CardState,
        caster: str,
        label: str,
        extra: TotalCost,
        taken: set[UUID],
    ) -> bool:
        """One CR 601.2b "announces their intentions to pay" question for an
        optional additional cost (CR 118.8a, 118.8b): a `MAY`, legal only when
        the cost can be paid on top of the rest (CR 118.3, CR 608.2d)."""
        payable = self._cost_payable_on_top_of(casting, extra, caster, taken)
        return bool(
            self.ask(
                Decision(
                    kind=DecisionKind.MAY,
                    player=caster,
                    prompt=f"pay {label} {extra} as you cast {card.name}",
                    source=card.name,
                    source_id=source_id_of(card),
                    affirmative_is_legal=payable,
                )
            )
        )

    def mana_pool_receiving(self: "Game", username: str) -> ManaPool:
        """The pool mana `username` adds goes into right now (CR 106.4).

        An open payment's working pool while one is being paid (CR 601.2g:
        mana abilities are activated during the payment, and what they make is
        spent from it), else the player's own.
        """
        pool = self.open_payment_pools.get(username)
        return pool if pool is not None else self.player(username).mana_pool

    @property
    def mana_hints_planned(self: "Game") -> bool:
        """Whether the colour hints now in force are a payment plan's."""
        return self._mana_hints_planned

    def take_mana_color_hints(self: "Game", colors: Sequence[Color]) -> bool:
        """Consume every one of `colors` from the hints when all are there,
        else consume nothing; True when they were taken."""
        remaining = list(self._mana_color_hints)
        for color in colors:
            if color not in remaining:
                return False
            remaining.remove(color)
        if colors:
            self._mana_color_hints = tuple(remaining)
        return bool(colors)

    def take_mana_color_hint(self: "Game", options: Sequence[Color]) -> Color | None:
        """Consume the first hinted colour that is one of `options`, if any."""
        for index, color in enumerate(self._mana_color_hints):
            if color in options:
                self._mana_color_hints = (
                    self._mana_color_hints[:index] + self._mana_color_hints[index + 1 :]
                )
                return color
        return None

    @contextmanager
    def paying_cost_of(
        self: "Game", what: str | None, keyword: str | None, payer: str | None
    ) -> Iterator[None]:
        """While a spell's (CR 601.2h) or an ability's (CR 602.2b) total cost
        is paid, every event raised is marked as happening during that
        payment (`GameEvent.during_cost_of`) - what a trigger event's own
        "while casting a spell with emerge" qualifier asks (CR 603.2). `what`
        None is a payment for neither, and marks nothing."""
        if what is None:
            yield
            return
        outer = self._paying_cost
        self._paying_cost = (what, keyword, payer)
        try:
            yield
        finally:
            self._paying_cost = outer

    def _apply_mana_spend_effects(self: "Game", permanent: CardState) -> None:
        """CR 106.6's additional effect, applied to the permanent that spell
        just became.

        "Some spells or abilities that produce mana ... have an additional
        effect that affects the spell or ability that mana is spent on." Arena
        of Glory's "If that mana is spent on a creature spell, it gains haste
        until end of turn." is the printing: the sentence travelled with the
        mana (`ManaPool.spend_effects`), the payment recorded which of it was
        actually spent here (CR 601.2h, `ManaPayment.spend_effects_spent`) and
        `CastRecord.spend_effects` carried it through announcement.

        Applied after `enter_the_battlefield` because that is where the object
        gains a battlefield to be a permanent on: the grant is an ordinary
        layer 6 continuous effect (CR 613.1f) with an "until end of turn"
        duration, and every reader of haste - `Game.can_attack`, the summoning
        sickness check - already asks the computed board.

        A spell that is not the card type the sentence names gets nothing, and
        a sentence this engine cannot read gets nothing either; neither is
        refused, because this clause only ever gives something away.
        """
        sentences = self.cast_record(permanent).spend_effects
        if not sentences:
            return
        for sentence in sentences:
            for effect in spend_effect_effects(sentence, permanent, self.continuous_effects.tick()):
                self.continuous_effects.add(effect, self)

    def _mana_sources_while_resolving(self: "Game", player: Player) -> list[CardState]:
        """The untapped permanents whose mana abilities `player` could activate
        right now to pay a cost (CR 605.3a), each once, in battlefield order.

        The same candidate scan `CostPayment.auto_tap` and `legal_actions` read,
        so a source offered here is one the payment below can really tap.
        """
        found: list[CardState] = []
        scan = mana_candidate_scan(
            self.permanents_controlled_by(player.username), game=self, payer=player.username
        )
        for candidate in scan:
            state = candidate[0]
            if all(state.id != seen.id for seen in found):
                found.append(state)
        return found

    def _pay_mana_while_resolving(
        self: "Game",
        player: Player,
        cost: ManaCost,
        sources: Sequence[CardState],
        *,
        prompt: str,
        spend: ManaSpend | None = None,
        named: Sequence[NamedManaAbility] = (),
    ) -> None:
        """Pay `cost` from the floating pool plus mana abilities of `sources`.

        CR 118.3c: "Activating mana abilities is not mandatory, even if paying a
        cost is", so only as many of `sources` are activated as the payment
        needs, through `CostPayment.auto_tap` - the one solver every other mana
        payment in this engine uses. What is left over stays in the pool
        (CR 106.4a).

        `named` are mana abilities of any cost the player chose to activate
        first (CR 605.3a, CR 608.2g - Vivi Ornitier's `{0}`), each activated in
        full by `CostPayment.activate_mana_ability`.
        """
        payment = CostPayment.for_total(
            TotalCost.of(cost), game=self, payer=player.username, spend=spend
        )
        try:
            _activate_named_mana_abilities(self, payment, named)
        except ValueError as refused:
            payment.cancel()
            raise ValueError(f"{prompt}: {refused}") from refused
        try:
            payment.auto_tap(sources)
        except ValueError as unpayable:
            payment.cancel()
            raise ValueError(
                f'{prompt}: the mana sources named cannot pay {cost} (CR 118.3: "A player '
                f"can't pay a cost without having the necessary resources to pay it fully\"): "
                f"{unpayable}"
            ) from unpayable
        payment.pay()

    def pay_any_amount_of_energy(
        self: "Game",
        player: Player | str,
        *,
        source: str | None = None,
        source_id: str | None = None,
        prompt: str = "pay any amount of {E}",
    ) -> int:
        """ "You may pay any amount of {E}" (Galvanic Discharge, Wrath of the
        Skies) - CR 107.14, CR 118.3, CR 608.2d's variable-amount cousin of
        `may_pay_energy`.

        Unlike a fixed `{E}{E}{E}`, this is a real choice among every amount
        from 0 up to however much energy the player has *right now* - `amount`
        pays no more than that (CR 118.3), and 0 is always legal (declining).
        `Game.ask` validates the answer is an int in that range; nothing here
        or in `default_answer` ever substitutes the maximum for an unscripted
        or declined answer - CR 608.2d's choice is the player's, not an
        optimiser's, and a card that keys its own effect off the amount paid
        (Galvanic Discharge's damage, Wrath of the Skies's mana-value ceiling)
        would silently always deal maximum damage or destroy everything if
        this ever defaulted upward.

        Returns however much was actually paid (0 if declined or unaffordable
        to pay more), and pays exactly that - never a partial amount on top of
        a partial deduction, since the whole payment is one `remove_counters`
        call once the amount is already known to be legal.
        """
        if isinstance(player, str):
            player = self.player(player)
        available = player.energy
        decision = Decision(
            kind=DecisionKind.PAY_ENERGY_AMOUNT,
            player=player.username,
            prompt=prompt,
            source=source,
            source_id=source_id,
            amount=available,
        )
        paid = self.ask(decision)
        assert isinstance(paid, int)
        if paid > 0:
            player.remove_counters(Counter.ENERGY, paid)
            self.note_turn_count(ENERGY_PAID_OR_LOST, player.username, paid)
        return paid

    def pay_any_amount_of_life(
        self: "Game",
        player: Player | str,
        *,
        source: str | None = None,
        source_id: str | None = None,
        prompt: str = "pay any amount of life",
    ) -> int:
        """ "You may pay any amount of life" (Necrodominance) - CR 119.4's
        variable-amount cousin of `may_pay_life`, mirroring `pay_any_amount_
        of_energy` exactly: a real choice from 0 up to the player's *current*
        life total (CR 119.4: legal "only if their life total is greater
        than or equal to the amount of the payment", which paying down to
        exactly 0 satisfies), never defaulted upward for an unscripted
        answer - Necrodominance's own "draw that many cards" would otherwise
        silently draw the maximum every time.

        Returns however much was actually paid (0 if declined), and pays
        exactly that.
        """
        if isinstance(player, str):
            player = self.player(player)
        available = player.life
        decision = Decision(
            kind=DecisionKind.PAY_LIFE_AMOUNT,
            player=player.username,
            prompt=prompt,
            source=source,
            source_id=source_id,
            amount=available,
        )
        paid = self.ask(decision)
        assert isinstance(paid, int)
        if paid > 0:
            self.lose_life(player, paid, payment=True)  # CR 119.4
        return paid

    def unspent_mana_of(self: "Game", player: Player) -> ManaPool:
        """The mana this player has produced and not yet spent (CR 106.4).

        Their own `ManaPool`, except while a `CostPayment` of theirs is open:
        that payment opened as a copy of this very pool and every mana ability
        activated for it (CR 601.2g) adds into the copy, so the copy is the
        one that knows what is actually unspent. See `open_payment_pools`.
        """
        return self.open_payment_pools.get(player.username, player.mana_pool)

    def _pay_attack_costs(
        self: "Game",
        attacks: "Sequence[tuple[CardState, Targetable | str]]",
        sources: "Sequence[CardState] | None" = None,
    ) -> list[CardState]:
        """CR 508.1h-j: determine the total cost to attack, let the active
        player activate mana abilities for it, and pay it in full - or refuse
        the whole declaration (CR 508.1: "the game returns to the moment
        before the declaration") when it cannot be paid, since "Partial
        payments are not allowed" (CR 508.1j).

        The costs are `combat.total_attack_cost`'s - Ghostly Prison's and
        Dain, Lord of the Iron Hills' per-creature charges. Mana already in
        the pool pays first (`CostPayment.for_total` seeds it); the rest is
        auto-tapped from `sources` (the player's own choice of mana sources),
        else from every untapped permanent they control that is not being
        declared as an attacker - CR 508.1f has already tapped those by the
        time CR 508.1i's mana abilities are activated.
        """
        refs = [(creature, self.attack_target(defender)) for creature, defender in attacks]
        total, reasons = combat_rules.total_attack_cost(self, refs)
        returned = self._choose_attack_cost_returns(attacks)
        if not total.symbols:
            return returned
        active = self.active_player.username
        attacking = {creature.id for creature, _defender in attacks}
        pool = (
            list(sources)
            if sources is not None
            else [
                permanent
                for permanent in self.permanents_controlled_by(active)
                if permanent.id not in attacking and not permanent.tapped
            ]
        )
        payment = CostPayment.for_total(TotalCost(mana=total), game=self, payer=active)
        try:
            payment.auto_tap(pool)
            payment.pay()
        except ValueError as error:
            if payment.step is not CostStep.PAID:
                payment.cancel()
            raise ValueError(
                f"the cost to attack is {total} ({'; '.join(reasons)}) and it cannot be paid: "
                f"{error} (CR 508.1h, CR 508.1j)"
            ) from error
        return returned

    def _choose_attack_cost_returns(
        self: "Game", attacks: "Sequence[tuple[CardState, Targetable | str]]"
    ) -> list[CardState]:
        """CR 508.1g-h: the permanents each "can't attack unless you return a
        <permanent> you control to its owner's hand" cost (Floodtide Serpent)
        will return, chosen by the attacking player as the attack is declared
        (`attack_block_costs.return_costs`). Chosen before any mana is paid
        so a cost that cannot be paid changes nothing."""
        from ...machines import attack_block_costs

        taken: set = set()
        chosen: list[CardState] = []
        for creature, _defender in attacks:
            for sentence, candidates in attack_block_costs.return_costs(self, creature):
                available = [permanent for permanent in candidates if permanent.id not in taken]
                if not available:
                    raise ValueError(
                        f'{creature.name} can\'t attack: "{sentence}" and there is nothing '
                        "left to return (CR 508.1c, CR 118.3)"
                    )
                picked = available[-1]
                if len(available) > 1:
                    answer = self.ask(
                        Decision(
                            kind=DecisionKind.CHOOSE_CARDS,
                            player=self.active_player.username,
                            prompt=f"choose the permanent to return to pay for {creature.name} "
                            "attacking",
                            source=creature.name,
                            source_id=None,
                            amount=1,
                            cards=tuple(permanent.id for permanent in available),
                        )
                    )
                    by_id = {permanent.id: permanent for permanent in available}
                    picked = by_id[answer[0]]
                taken.add(picked.id)
                chosen.append(picked)
        return chosen

    def _return_attack_cost_permanents(self: "Game", chosen: "Sequence[CardState]") -> None:
        for permanent in chosen:
            self.return_to_hand(permanent)

    def _pay_block_costs(self: "Game", blocks: "Sequence[tuple[CardState, CardState]]") -> None:
        """CR 509.1d-f: determine the total cost to block, let the defending
        player activate mana abilities for it, and pay it in full - or refuse
        the whole declaration when it cannot be paid (CR 509.1f: "Partial
        payments are not allowed"). Only a block not already declared costs
        anything: a harness or caller re-declaring the whole combat does not
        pay again for the pairs already made."""
        from ...machines import combat_statics

        combat = self.combat
        total = ManaCost.parse("")
        reasons: list[str] = []
        payer: str | None = None
        for blocker, attacker in blocks:
            attack = combat.attack_by(attacker.id)
            if attack is not None and blocker.id in attack.blockers:
                continue
            for charge in combat_statics.extra_block_costs(self, blocker):
                total = total.plus(charge.cost)
                reasons.append(f"{blocker.name}: {charge.cost} ({charge.source.name})")
                payer = self.controller_of(blocker).username
        if not total.symbols or payer is None:
            return
        pool = [
            permanent for permanent in self.permanents_controlled_by(payer) if not permanent.tapped
        ]
        payment = CostPayment.for_total(TotalCost(mana=total), game=self, payer=payer)
        try:
            payment.auto_tap(pool)
            payment.pay()
        except ValueError as error:
            if payment.step is not CostStep.PAID:
                payment.cancel()
            raise ValueError(
                f"the cost to block is {total} ({'; '.join(reasons)}) and it cannot be paid: "
                f"{error} (CR 509.1d, CR 509.1f)"
            ) from error

    def spend_play_permission_choice(self: "Game", used: PlayPermission) -> None:
        """ "You may play one of those cards": the card just played or cast
        under `used` was the one, so every other permission the same
        instruction handed out (`PlayPermission.choice_group`) ends now."""
        if used.choice_group is None:
            return
        self.play_permissions = [
            permission
            for permission in self.play_permissions
            if permission.choice_group != used.choice_group
        ]

    def object_cost_offers(
        self: "Game", card: CardState, player: str
    ) -> dict[str, "ObjectCostOffer"]:
        """Which objects could be spent on `card`'s cost, and for what -
        convoke (CR 702.51a), delve (CR 702.66a), improvise (CR 702.126a),
        crew (CR 702.122a).

        `magic_cards_model_api.affordances.object_costs` used to import
        `machines/objects_as_costs.py` directly and walk the battlefield and
        graveyard itself to answer this; that walk is engine knowledge, not
        api shaping, so it lives here now. The api keeps `_label`, the dict
        shaping, and `object_costs`'s own three-key dict - this only answers
        *which cards are eligible*, the same `ObjectOffer.why_not` predicate
        the actual payment (`machines/objects_as_costs.convoke`/`delve`/
        `improvise`) uses, so a candidate list here can never disagree with
        what paying would accept.

        Only the keys that apply are present - a card with none of these
        gets an empty dict.
        """
        from ...machines.objects_as_costs import convoke_offer as _convoke_offer
        from ...machines.objects_as_costs import (
            crew_number,
            crew_offer,
            delve_offer,
            has_convoke,
            has_crew_loyalty_alternative,
            has_delve,
            has_improvise,
            has_station,
            improvise_offer,
            is_vehicle_permanent,
            station_offer,
        )

        battlefield = self.battlefield
        out: dict[str, ObjectCostOffer] = {}
        if has_convoke(card.card):
            offer = _convoke_offer()
            out["convoke"] = ObjectCostOffer(
                rule="CR 702.51a",
                candidates=[c for c in battlefield if offer.why_not(c, player, self) is None],
            )
        if has_delve(card.card):
            offer = delve_offer()
            out["delve"] = ObjectCostOffer(
                rule="CR 702.66a",
                candidates=[
                    c
                    for c in self.player(player).graveyard
                    if offer.why_not(c, player, self) is None
                ],
            )
        if has_improvise(card.card) or self.has_granted_improvise(player, card):
            offer = improvise_offer()
            out["improvise"] = ObjectCostOffer(
                rule="CR 702.126a",
                candidates=[c for c in battlefield if offer.why_not(c, player, self) is None],
            )
        # CR 613.5: whether this permanent is a Vehicle is the computed
        # answer, not the printed type line - Toph, the First Metalbender's
        # "nontoken artifacts you control are lands" and any layer-4 subtype
        # change both reach it, and a crewed Vehicle stays one.
        if is_vehicle_permanent(card, self):
            offer = crew_offer(card)
            out["crew"] = ObjectCostOffer(
                rule="CR 702.122a",
                number=crew_number(card.card),
                candidates=[c for c in battlefield if offer.why_not(c, player, self) is None],
                loyalty_candidates=[
                    c
                    for c in battlefield
                    if has_crew_loyalty_alternative(card.card)
                    and Type.PLANESWALKER in self.characteristics_of(c).types
                    and self.controller_of(c).username == player
                    and c.counters[Counter.LOYALTY] > 0
                ]
                if has_crew_loyalty_alternative(card.card)
                else [],
            )
        # CR 702.184a: a station permanent's own ability, offered while it is
        # on the battlefield - the candidates are the creatures its cost could
        # tap, the same `why_not` `station_activation`'s tap cost applies.
        if card.zone is Zone.BATTLEFIELD and has_station(card.card):
            offer = station_offer(card)
            out["station"] = ObjectCostOffer(
                rule="CR 702.184a",
                candidates=[c for c in battlefield if offer.why_not(c, player, self) is None],
            )
        return out

    # -- determining a spell's total cost (CR 601.2f) ----------------------

    def cost_reduction_for(
        self: "Game",
        spell: CardState,
        caster: str | None = None,
        targets: Sequence[TargetRef] | None = None,
        casting: object | None = None,
    ) -> ManaCost:
        """What this spell's own text takes off its cost right now (CR 601.2f).

        The reduction is *computed*, never stored: CR 601.2f is a step of casting
        that happens after modes and targets, and what it reads is the game state
        at that moment. Emrakul, the Promised End is the card that makes the
        difference visible - "This spell costs {1} less to cast for each card
        type among cards in your graveyard" is worth however many card types are
        in that graveyard when the cost is determined, not when the card was
        drawn or when announcement began.

        CR 205.2b: "Some objects have more than one card type (for example, an
        artifact creature). Such objects satisfy the criteria for any effect that
        applies to any of their card types" - so one artifact creature in the
        graveyard is two card types, not one.

        Mystical Dispute's own shape reads a different kind of "right now":
        "This spell costs {2} less to cast if it targets a blue spell." is not
        a fact about the board at all, it is about *this spell's own
        announced target* (CR 601.2c), which is chosen before CR 601.2f
        determines the cost - `targets` is `Casting.targets` at that moment,
        the same `list[TargetRef]` `choose_targets` already populated.
        Without `targets` (a caller that never passed any) this half simply
        finds nothing to check, the same as any other condition this reads
        finding no match.

        Four more shapes read the same "right now", each counting something
        different, and all of them generic-mana reductions that CR 118.7a
        confines to the generic component ("Effects that reduce a cost by an
        amount of generic mana affect only the generic mana component of that
        cost. They can't affect the colored or colorless mana components") -
        `ManaCost.minus` is what enforces that, so Leyline Binding's {5}{W}
        with all five basic land types out settles on {W} rather than {0}:

        - **a per-turn history** - Hollow One's "for each card you've cycled or
          discarded this turn", counted in `cards_discarded_this_turn`;
        - **domain** - Scion of Draco's and Leyline Binding's "for each basic
          land type among lands you control" (CR 305.6's five). *Domain* is an
          ability word, and CR 207.2c gives ability words "no special rules
          meaning", so there is no rule to cite beyond the sentence itself;
        - **an opponent's board** - Obsidian Charmaw's "for each land your
          opponents control that could produce {C}", which CR 106.7 defines as
          "any type of mana that an ability of that permanent would produce if
          the ability were to resolve at that time";
        - **affinity** - CR 702.41a: "'Affinity for [text]' means 'This spell
          costs {1} less to cast for each [text] you control.'" Read off the
          keyword line, not off its reminder text, which CR 207.2 makes
          italics with no game function.

        Every shape found is added up rather than raced: nothing in the pool
        prints two, but a card that did would get both, which is what CR 601.2f
        says happens ("Some effects may increase or reduce the cost to pay",
        plural). A card whose reduction sentence this does not recognise
        reduces nothing.
        """
        # Same DFC-family fix as `effect_for` above: a modal-DFC/transform
        # spell's reduction clause lives on `card_faces`, not the raw
        # top-level `oracle_text` field, so this has to read `oracle_text`
        # (which already falls back to the up face) rather than `card.oracle_text`.
        text = spell.oracle_text or ""
        owner = caster or spell.controller or self.active_player.username
        amount = 0

        # Vivid's own self reduction (CR 207.2c: an ability word, no rules
        # meaning) - Rime Chill's and Wildvine Pummeler's "This spell costs
        # {1} less to cast for each color among permanents you control."
        # `machines/vivid.py` is the one reader every position this amount is
        # printed in shares (the resolution-time amount and Squawkroaster's
        # CDA read it too).
        from ...machines.vivid import costs_less_per_color_among_reduction

        amount += costs_less_per_color_among_reduction(text, self, owner)

        match = _COSTS_LESS_PER_CARD_TYPE.search(text)
        if match is not None:
            types = {card_type for card in self.player(owner).graveyard for card_type in card.types}
            amount += int(match.group(1)) * len(types)

        per_quality = _COSTS_LESS_PER_QUALITY_CARD_IN_GRAVEYARD_RE.search(text)
        if per_quality is not None:
            from ...machines.effects import _card_description_is_readable, _quality_matcher

            quality = re.sub(r"\s+and(?:/or)?\s+", " or ", per_quality.group("quality"))
            if _card_description_is_readable(quality):
                matches = _quality_matcher(quality)
                counted = sum(1 for card in self.player(owner).graveyard if matches(card))
                amount += int(per_quality.group(1)) * counted

        discarded = _COSTS_LESS_PER_CARD_DISCARDED_RE.search(text)
        if discarded is not None:
            amount += int(discarded.group(1)) * self.cards_discarded_this_turn.get(owner, 0)

        domain = _COSTS_LESS_PER_BASIC_LAND_TYPE_RE.search(text)
        if domain is not None:
            amount += int(domain.group(1)) * len(self.basic_land_types_controlled(owner))

        charmaw = _COSTS_LESS_PER_OPPONENT_COLORLESS_LAND_RE.search(text)
        if charmaw is not None:
            lands = [
                permanent
                for permanent in self.battlefield
                if permanent.controller is not None
                and permanent.controller != owner
                and Type.LAND in self.characteristics_of(permanent).types
                and self.could_produce_colorless(permanent)
            ]
            amount += int(charmaw.group(1)) * len(lands)

        affinity = _AFFINITY_RE.search(text)
        if affinity is not None:
            amount += self._affinity_count(affinity.group("what").lower(), owner)

        colored_reduction = ManaCost()
        target_match = _COSTS_LESS_IF_TARGETS_SPELL_RE.search(text)
        if target_match is not None and targets:
            reduction = self._target_spell_reduction(target_match, targets)
            if reduction is not None:
                amount += reduction.generic
                colored_reduction = ManaCost(
                    symbols=tuple(
                        symbol
                        for symbol in reduction.symbols
                        if symbol.kind is not SymbolKind.GENERIC
                    )
                )

        described_match = (
            _COSTS_LESS_IF_TARGETS_DESCRIPTION_RE.search(text) if target_match is None else None
        )
        if described_match is not None and targets:
            reduction = self._target_description_reduction(described_match, targets, owner)
            if reduction is not None:
                amount += reduction.generic
                colored_reduction = ManaCost(
                    symbols=tuple(
                        symbol
                        for symbol in reduction.symbols
                        if symbol.kind is not SymbolKind.GENERIC
                    )
                )

        condition_match = _COSTS_LESS_IF_CONDITION_RE.search(text)
        # Out of Air's "if it targets a creature spell" and Bouncer's
        # Beatdown's "if it targets a black permanent" are the target shapes
        # above, not open board conditions - read once, never twice.
        if condition_match is not None and target_match is None and described_match is None:
            held = self.condition_holds(owner, condition_match.group("condition"), source=spell)
            if held:
                amount += int(condition_match.group("amount"))

        greatest_stat = _COSTS_LESS_X_WHERE_X_IS_GREATEST_STAT_RE.search(text)
        if greatest_stat is not None:
            stat = greatest_stat.group("stat").lower()
            values = [
                getattr(self.characteristics_of(state), stat) or 0
                for state in self.permanents_controlled_by(owner)
                if self.characteristics_of(state).is_creature
            ]
            amount += max(values, default=0)

        total_power_with_keyword = _COSTS_LESS_X_WHERE_X_IS_TOTAL_POWER_WITH_KEYWORD_RE.search(text)
        life_vs_starting = _COSTS_LESS_IF_LIFE_TOTAL_VS_STARTING_X_IS_DIFFERENCE_RE.search(text)
        if life_vs_starting is not None:
            # Shadow of Mortality's own shape - checked ahead of the generic
            # "where X is <expr>" fallback below, whose bare `.search` would
            # otherwise match this same sentence's own tail ("... where x is
            # the difference") and hand "the difference" to `amount_
            # expression`, which reads no such bare phrase (it needs a named
            # "between A and B" pair) and would silently add nothing.
            player = self.player(owner)
            holds = (
                player.life < player.starting_life
                if life_vs_starting.group("cmp").lower() == "less"
                else player.life > player.starting_life
            )
            if holds:
                amount += abs(player.life - player.starting_life)
        elif total_power_with_keyword is not None:
            keyword = total_power_with_keyword.group("keyword")
            amount += sum(
                self.characteristics_of(state).power or 0
                for state in self.permanents_controlled_by(owner)
                if self.characteristics_of(state).is_creature
                and (keyword is None or has_keyword(state, keyword, self))
            )
        elif greatest_stat is None and (
            generic_where_x := _COSTS_LESS_X_WHERE_X_IS_RE.search(text)
        ):
            # Sunderflock's own shape: "This spell costs {X} less to cast,
            # where X is the greatest mana value among Elementals you
            # control." Neither of the two specific readers above names a
            # subtype qualifier or a mana-value stat, so this general
            # fallback reads `amount_expression`'s own wider vocabulary
            # instead - the same reader `count_expression`'s "the number of
            # `<qualifier>` you control" family already shares with every
            # other resolution-time amount (`machines/effects.py`), evaluated
            # here with no object and no ability X of its own: CR 601.2f's
            # self reduction has neither.
            from ...machines.effects import amount_expression

            reader = amount_expression(generic_where_x.group("expr"))
            if reader is not None:
                amount += reader(self, owner, spell, 0)

        generic = ManaCost.parse(f"{{{amount}}}") if amount else ManaCost()
        reduction = generic.plus(colored_reduction) if colored_reduction.symbols else generic
        # The counted, "where X is" and conditional sentences of
        # `self_reduction_reader`, one per printed line (CR 601.2f).
        from ...machines.cost.statics import CostContext

        context = CostContext(
            game=self, owner=owner, spell=spell, targets=tuple(targets or ()), casting=casting
        )
        for line in text.split("\n"):
            reader = self_reduction_reader(_ABILITY_WORD_PREFIX_RE.sub("", line.strip(), count=1))
            if reader is not None:
                extra = reader(context)
                if extra.symbols:
                    reduction = reduction.plus(extra)
        return reduction

    def could_produce_colorless(self: "Game", permanent: CardState) -> bool:
        """Whether this permanent could produce {C} right now (CR 106.7).

        CR 106.7: "The type of mana a permanent could produce at any time
        includes any type of mana that an ability of that permanent would
        produce if the ability were to resolve at that time" - so this asks the
        permanent's mana abilities what they would add, never whether any mana
        was actually made. Obsidian Charmaw's "for each land your opponents
        control that could produce {C}" is the only reader today.

        Printed abilities and `granted_ability_texts`'s own are both asked, the
        same pair `machines/cost.py` taps a source with: Urza's Saga chapter I
        grants "{T}: Add {C}." onto a land that prints no mana ability at all,
        and that land could produce {C}. The board-conditional clauses ("If you
        control an Urza's Mine and an Urza's Power-Plant, add {C}{C}{C}
        instead") are resolved through `ManaAbility.effective`, so the answer is
        the one that holds for the board as it stands - which is what "at any
        time" in CR 106.7 pins it to.

        `any_color` abilities are not counted: CR 106.1b makes colorless one of
        the six *types* of mana but not one of the five colors, so "one mana of
        any color" is never {C}.
        """
        return Color.COLORLESS in self.colors_could_produce(permanent)

    def colors_could_produce(
        self: "Game", permanent: CardState, *, skip_could_produce_abilities: bool = False
    ) -> frozenset[Color]:
        """Every type of mana this permanent could produce right now (CR 106.7).

        CR 106.7: "The type of mana a permanent could produce at any time
        includes any type of mana that an ability of that permanent would
        produce if the ability were to resolve at that time." So each of its
        mana abilities is asked what it would add, against the board as it
        stands - never whether any mana was actually made, whether the
        permanent is untapped, or whether its controller could pay to activate
        it.

        "Type" is CR 106.1b's six, colorless included, so `Color.COLORLESS` is
        a member of the answer like any other. An `any_color` ability
        contributes CR 106.1a's five colours and not colorless.

        Printed and `granted_ability_texts` abilities are both asked, the same
        pair `machines/cost.py` taps a source with: Urza's Saga chapter I
        grants "{T}: Add {C}." onto a land that prints no mana ability at all.

        **`skip_could_produce_abilities` is the recursion guard.** Reflecting
        Pool's own "{T}: Add one mana of any type that a land you control could
        produce" is itself a land whose type is defined by a survey, so
        surveying a board of two Reflecting Pools - or a Pool and an Exotic
        Orchard pointed at each other - would recurse forever. CR 106.7 has no
        fixed point to offer there, so a permanent whose ability is itself a
        survey contributes nothing to someone else's survey; every other land
        answers normally. The answer stays under-inclusive rather than wrong,
        which is the same direction `colors_land_types_could_produce` errs in.
        """
        granted = granted_mana_abilities(permanent.granted_ability_texts)
        rewritten = rewritten_ability_lines(self, permanent)
        if rewritten is not None:
            # CR 613.5: once a continuous effect has rewritten the printed
            # lines, those computed lines are the ones this permanent has -
            # which is where a Blood Mooned nonbasic land's intrinsic "{T}: Add
            # {R}" comes from (CR 305.6), since nothing prints it. The grants
            # are still added on top, being layer 6 effects (CR 613.1f) applied
            # after the layer 4 change that caused the rewrite, so a Blood
            # Mooned Urza's Saga "could produce" both {R} and its chapter I
            # {C} - which is what CR 106.7 is asking.
            abilities = granted_mana_abilities(rewritten) + granted
        else:
            # Plus whatever layer 4 added without removing anything: a land
            # granted a basic land type could produce that type's mana
            # (CR 305.6), which is exactly what CR 106.7 is asking about.
            abilities = (
                parse_mana_abilities(permanent.card, permanent.up_face_name)
                + granted
                + granted_mana_abilities(added_ability_lines(self, permanent))
            )
        if not abilities:
            return frozenset()
        controller = permanent.controller_or_owner
        land_types = self._controlled_land_types(controller)
        own_counters = frozenset(permanent.counters.counts)
        has_imprinted_card = self.card_imprinted_on(permanent.id) is not None

        colors: set[Color] = set()
        for ability in abilities:
            if ability.could_produce is not None:
                if skip_could_produce_abilities:
                    continue
                surveyed = self._could_produce_survey(ability.could_produce, controller)
                options, any_color = ability.effective(
                    land_types,
                    own_counters,
                    has_imprinted_card,
                    could_produce_colors=surveyed,
                )
            else:
                options, any_color = ability.effective(land_types, own_counters, has_imprinted_card)
            if any_color:
                colors.update(_COLOR_WORDS.values())
            for option in options:
                colors.update(option)
        return frozenset(colors)

    def _could_produce_survey(
        self: "Game", which: CouldProduce, controller: str | None
    ) -> frozenset[Color]:
        """CR 106.7's survey itself: the types of mana the lands the clause
        names could produce right now.

        Reflecting Pool asks about "a land you control", Exotic Orchard about
        "a land an opponent controls" - `CouldProduce` is which. Every surveyed
        land is asked with the recursion guard on, so a survey never consults
        another survey (see `colors_could_produce`).

        CR 613.5: "land" here is the computed board, not the printed line -
        Toph, the First Metalbender's "Nontoken artifacts you control are
        lands in addition to their other types" makes an artifact a land the
        survey has to see, and the printed `CardState.types` never would.
        """
        colors: set[Color] = set()
        board = self.computed_board()
        for land in self.battlefield:
            if Type.LAND not in board.of(land).types:
                continue
            land_controller = self.controller_of(land).username
            if which is CouldProduce.LANDS_YOU_CONTROL:
                if land_controller != controller:
                    continue
            elif land_controller == controller:
                continue
            colors.update(self.colors_could_produce(land, skip_could_produce_abilities=True))
        return frozenset(colors)

    def _affinity_count(self: "Game", what: str, controller: str) -> int:
        """How much CR 702.41a's affinity takes off, in generic mana.

        "'Affinity for [text]' means 'This spell costs {1} less to cast for
        each [text] you control.'" - one generic per matching permanent, and
        the {1} is the rule's, not the card's, so the count *is* the amount.
        A "[text]" neither `_AFFINITY_CARD_TYPES` nor `_AFFINITY_SUBTYPES`
        names is left at nothing rather than guessed at.
        """
        card_type = _AFFINITY_CARD_TYPES.get(what)
        # Any printed subtype, plural as printed ("Allies", "Dragons", "Cats"),
        # beside the basic land types the old table spelled out (CR 702.41a:
        # "[text]" is whatever the card says; Allies at Last's "Affinity for
        # Allies" counts Ally creatures you control).
        subtype = (_AFFINITY_SUBTYPES.get(what) or canonical_subtype(what) or "").lower() or None
        if card_type is None and subtype is None:
            return 0
        counted = 0
        for permanent in self.permanents_controlled_by(controller):
            chars = self.characteristics_of(permanent)
            matches = (card_type is not None and card_type in chars.types) or (
                subtype is not None and subtype in {word.lower() for word in chars.subtypes}
            )
            # One permanent is one count however many ways it matches: CR
            # 205.2b makes an artifact creature both types, and "affinity for
            # artifacts" counts artifacts, not card types.
            counted += 1 if matches else 0
        return counted

    def _type_decrease_candidate_matches(
        self: "Game", effect: CostModifierEffect, candidate: CardState
    ) -> bool:
        """Whether `candidate` is one of `effect.applies_to_types`, with its
        optional subtype exclusion and keyword requirement also holding.

        `_counted_type_decrease` asks this of the spell being costed, and
        `first_each_turn` below asks it again of every *earlier* spell this
        turn - the identical filter both times, which is what makes Momo,
        Friendly Flier's own "The first **non-Lemur** creature spell **with
        flying**" correct: an earlier plain creature spell with no flying
        does not carry the qualifier either, so it does not make *this*
        flying creature spell any less the first one, exactly the way
        `spells_cast_this_turn` already excludes the spell being costed
        itself (CR 601.2f runs before CR 601.2i records it)."""
        if effect.applies_to_types and not any(
            card_type in candidate.types for card_type in effect.applies_to_types
        ):
            return False
        if effect.excludes_subtype is not None and effect.excludes_subtype in {
            subtype.lower() for subtype in candidate.subtypes
        }:
            return False
        return effect.requires_keyword is None or has_keyword(
            candidate, effect.requires_keyword, self
        )

    def _counted_type_decrease(
        self: "Game",
        effect: CostModifierEffect,
        permanent: CardState,
        spell: CardState,
        caster: str,
    ) -> ManaCost | None:
        """One `TYPE_DECREASE` naming the spell's types, as the cost it takes
        off (CR 601.2f), or `None` when it takes nothing off this spell.

        "The first `<types>` spell you cast each turn" (`first_each_turn`) is
        the caster's first *qualifying* spell this turn (`_type_decrease_
        candidate_matches`, types plus the optional subtype exclusion and
        keyword requirement): the spell being cast is not in `spells_cast_
        this_turn` yet (CR 601.2f comes before CR 601.2i records it), so any
        earlier qualifying one there means this is not the first. A "for
        each" count (`per_each`) is read now, for the permanent's controller,
        and multiplies the decrease. A colored decrease (`colored`, "{U} (or
        {1})") is that many of the color; CR 118.7b-c already turn what the
        cost has no {U} for into generic when `ManaCost.minus` applies it.
        """
        if not self._type_decrease_candidate_matches(effect, spell):
            # The subtype exclusion or keyword requirement Momo's own shape
            # adds - the caller has already confirmed `applies_to_types`
            # alone, which is why this asks only for the two extra filters
            # in practice, but asking the shared predicate keeps both call
            # sites answering the identical question.
            return None
        if effect.first_each_turn and any(
            self._type_decrease_candidate_matches(effect, earlier)
            for earlier in self.spells_cast_this_turn.get(caster, [])
        ):
            return None
        if effect.requires_toughness_greater_than_power and not (
            (spell.toughness or 0) > (spell.power or 0)
        ):
            # Doran, Besieged by Time: the spell's own toughness/power (CR
            # 208.1), read right now (CR 611.3a) - a spell with no numeric
            # value for either (CR 208.5) compares as 0.
            return None
        units = effect.amount
        if effect.per_equipped_power:
            from ...machines.keywords import equipped_creature

            host = equipped_creature(self, permanent)
            units = self.power_of(host) if host is not None else None
            if units is None:
                return None
        if effect.per_each is not None:
            from ...machines.effects import _for_each_multiplier

            count = _for_each_multiplier(effect.per_each)
            if count is None:
                return None
            units *= count(self, permanent.controller or caster, str(permanent.id))
        if units <= 0:
            return None
        if effect.colored is not None:
            return ManaCost.parse(f"{{{effect.colored.value}}}" * units)
        return ManaCost.parse(f"{{{units}}}")

    def determine_total_cost(self: "Game", casting: object) -> CostPayment:
        """CR 601.2f: work out the reduction now, then lock the total cost in.

        "Once the total cost is determined, any effects that directly affect the
        total cost are applied. Then the resulting total cost becomes 'locked
        in.' If effects would change the total cost after this time, they have no
        effect." Which is why the reduction is applied *here* rather than when
        the `Casting` was created: a card put into the graveyard between
        announcement and this call still counts, and one put there afterwards
        does not.

        `Casting.determine_cost` does not consult the game for a self-reduction
        on its own, so a scenario that wants Emrakul's discount - or Mystical
        Dispute's own "if it targets a blue spell" - calls this instead of
        `casting.determine_cost()`. Routing it into `machines/casting.py` is
        the tidier home - see `docs/engine-coverage.md`. `casting.targets`
        (CR 601.2c's announcement, already made by the time CR 601.2f runs)
        is what Mystical Dispute's own condition reads.
        """
        reduction = self.cost_reduction_for(
            casting.spell,  # type: ignore[attr-defined]
            casting.caster,  # type: ignore[attr-defined]
            targets=casting.targets,  # type: ignore[attr-defined]
            casting=casting,
        )
        if reduction.symbols:
            # Appended straight onto the casting's reductions rather than through
            # `reduce_cost`, which belongs to CR 601.2b and refuses to run once
            # targets have been chosen. CR 601.2f is a later step than that.
            casting.cost_reductions.append(reduction)  # type: ignore[attr-defined]
        return casting.determine_cost()  # type: ignore[attr-defined]

    def mana_color_options(
        self: "Game", permanent: CardState, index: int = 0, controller: str | None = None
    ) -> tuple[Color, ...]:
        """Every colour `activate_ability`'s own `color=` would accept for
        this mana ability right now (CR 605.1a), or empty when it makes no
        real choice - a single fixed colour, or none at all (CR 106.5).

        Read the same way `activate_ability`'s own mana fast path resolves
        one (CR 605.3b): `ManaAbility.effective`, narrowed by the same
        board-derived CR 106.7 survey and CR 614.12a chosen-colour reading
        that path already computes, then Mox Amber's own CR 106.5 "among
        legendary creatures and planeswalkers you control" narrowing
        (`among_colors`, read off the ability's printed effect text) - so a
        pure enumeration caller (`machines/legal_actions.py`) is offered
        exactly the colours a real activation would accept, not a superset
        guessed from the printed text alone that `activate_ability` would
        then refuse.

        `machines/legal_actions.py`'s own `Action` has no field for a live
        `ManaAbility`, only for ids and plain data - this is what lets it
        name the choice as `Action.color_options` instead: without it, an
        `ACTIVATE_MANA` action for a choice-offering ability (a dual land,
        Birds of Paradise's "any color") was reported affordable with no way
        for a caller to actually complete the call `activate_ability`
        demands.
        """
        ability = self.activated_abilities(permanent)[index]
        if ability.mana is None:
            return ()
        controller = controller or self.controller_of(permanent).username
        land_types = self._controlled_land_types(controller)
        own_counters = frozenset(permanent.counters.counts)
        has_imprinted_card = self.card_imprinted_on(permanent.id) is not None
        chosen = permanent.choice
        chosen_color = (
            Color(chosen.value) if chosen is not None and chosen.kind is ChoiceKind.COLOR else None
        )
        could_produce_colors = (
            self._could_produce_survey(ability.mana.could_produce, controller)
            if ability.mana.could_produce is not None
            else None
        )
        options, any_color = ability.mana.effective(
            land_types,
            own_counters,
            has_imprinted_card,
            could_produce_colors=could_produce_colors,
            chosen_color=chosen_color,
        )
        colors: list[Color] = []
        if any_color:
            colors.extend(_COLOR_WORDS.values())
        elif len(options) > 1:
            for option in options:
                for color in option:
                    if color not in colors:
                        colors.append(color)
        allowed = among_colors(ability.effect, self, controller)
        if allowed is not None:
            colors = [color for color in colors if color in allowed]
        return tuple(colors)

    def mana_color_choice_count(
        self: "Game", permanent: CardState, index: int = 0, controller: str | None = None
    ) -> int:
        """How many colours `activate_ability`'s own `color=` takes for this
        mana ability right now - the count that turns `mana_color_options`'
        flat pool into the choice the card actually offers (CR 605.1a).

        0 when the ability offers no choice at all (and `mana_color_options`
        is correspondingly empty). 1 for nearly every ability that offers
        one, including "Add two mana of any one color", whose own words lock
        both mana to the single colour named. The mana count for "Add N mana
        in any combination of colors" (`ManaAbility.any_color_mixed`), where
        each mana's colour is chosen on its own and `activate_ability` takes
        a sequence of that many - `ManaAbility.resolve` is what enforces the
        length and refuses a mixture the printed words never offered. No
        printing combines a mixture with CR 700.5's devotion count
        (`amount_from_devotion`), which is only knowable once the colour is
        chosen and so could not be enumerated ahead of the choice at all.

        Split out from `mana_color_options` rather than folded into it
        because a pool of five colours is the same pool either way: what
        differs is how many are drawn from it, and without this an enumerated
        `ACTIVATE_MANA` action (`Action.color_choice_count`) could only ever
        name one, making every genuine mixture unreachable for a caller
        driving the engine through `legal_actions`.
        """
        ability = self.activated_abilities(permanent)[index]
        if ability.mana is None:
            return 0
        if not self.mana_color_options(permanent, index, controller):
            return 0
        if not ability.mana.any_color_mixed:
            return 1
        # A count the board decides ("X mana in any combination of {U} and/or
        # {R}, where X is Vivi Ornitier's power") is that count now, not the
        # parser's placeholder of one - the same `mana_ability_most` reading a
        # payment counts on. An X the ability's own cost announces (CR 107.3a:
        # "Remove X storage counters") is reported at its most - every counter
        # there - and a caller names one colour per X it actually announces;
        # an X nothing on the board bounds ("{X}, {T}, Sacrifice ...") reports
        # the placeholder, one colour per X announced all the same.
        from ...machines.cost import mana_ability_most

        most = mana_ability_most(self, permanent, index, controller)
        return most if most else ability.mana.any_color_count

    def apply_mana_ability_rider(
        self: "Game", rider: ManaAbilityRider | None, controller: str, source: CardState
    ) -> None:
        """CR 405.6c: "If a mana ability both produces mana and has another
        effect, the mana is produced and the other effect happens immediately."

        The one funnel for that other effect, whichever route activated the
        ability: `activate_ability`'s mana fast path, and
        `CostPayment.tap_for_mana` when a source is tapped while paying a cost
        (a hand-picked source list and `auto_tap` both reach it). CR 118.3c
        makes tapping a source during payment an activation of its mana
        ability all the same, so the rider cannot depend on who chose it.
        """
        if rider is None:
            return
        if rider.kind == "damage_to_controller":
            self.deal_damage(self.player(controller), rider.amount, source=source)
        elif rider.kind == "lose_life":
            self.lose_life(self.player(controller), rider.amount)
        elif rider.kind == "gain_life":
            self.gain_life(controller, rider.amount)
        else:
            # CR 405.6c, aimed at "each opponent" (CR 102.2): everyone still
            # in the game who is not the controller, in turn order.
            for opponent in self.players_in_game:
                if opponent.username == controller:
                    continue
                if rider.kind == "opponents_gain_life":
                    self.gain_life(opponent, rider.amount)
                else:
                    self.lose_life(opponent, rider.amount)

    def why_cannot_pay_with(self: "Game", controlled: str, source: CardState) -> str | None:
        """Why this permanent cannot pay a controlled player's cost (CR 723.5a).

        "The controller of another player can use only that player's resources
        (cards, mana, and so on) to pay costs for that player." So a controller
        making their victim cast a spell has to find the mana on the victim's
        own board; their own lands are not available for it.

        The same question `CostPayment.tap_for_mana` and the auto-tap scans ask
        of every source (`cost.why_payer_cannot_use`), so this answer and a real
        payment cannot disagree.
        """
        return why_payer_cannot_use(source, controlled, self)


from ._common import (  # noqa: E402
    _ABILITY_WORD_PREFIX_RE,
    _COLOR_WORDS,
    _SPEND_AS_ANY_COLOR_STATIC_RE,
    _SPEND_AS_ANY_COLOR_TO_ACTIVATE_RE,
    ENERGY_PAID_OR_LOST,
    Targetable,
)
from ._conditions import _card_type_named, condition_is_readable  # noqa: E402
from .records import ObjectCostOffer  # noqa: E402
