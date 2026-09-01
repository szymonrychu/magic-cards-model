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
from collections.abc import Callable, Sequence
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ..models.card import Card, Type
from ..models.card_state import (
    CardState,
    Counter,
    ExileAnnotation,
    ExileMarker,
    FaceDownCharacteristics,
    TargetRef,
)
from ..models.mana import ManaCost
from ..models.zone import Zone
from .abilities import (
    AbilityKind,
    ActivatedAbility,
    Cost,
    CostKind,
    KeywordAbility,
    TriggeredAbility,
    TriggerEvent,
    TriggerWord,
    keyword_abilities,
)
from .combat import has_keyword
from .cost import CostPayment, CostStep, TotalCost, discard_cost, total_cost_for_phrase
from .decisions import Decision, DecisionKind
from .layers import (
    ContinuousEffect,
    Duration,
    Layer,
    Sublayer,
    add_type,
    modify_power_toughness,
)
from .objects_as_costs import crew_number, crew_offer, power_of, total_power
from .triggers import AbilityOnStack, GameEvent, activated_abilities_of, triggers_for


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
    PERSIST = "CR 702.79a"
    DREDGE = "CR 702.52a"
    MOBILIZE = "CR 702.181a"
    MADNESS = "CR 702.35a"
    MORPH = "CR 702.37a"
    DISGUISE = "CR 702.168a"
    INDESTRUCTIBLE = "CR 702.12b"
    EXERT = "CR 701.43a"
    REBOUND = "CR 702.88a"
    HIDEAWAY = "CR 702.75a"
    CREW = "CR 702.122a"
    EVOKE = "CR 702.74a"


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
        "cascade",
        "storm",
        "persist",
        "dredge",
        "mobilize",
        "indestructible",
        "exert",
        "rebound",
        "hideaway",
        "crew",
        # CR 702.74a. Two abilities, executed in two places: the static half is
        # an alternative cost and belongs to `machines/casting.py`
        # (`keyword_cast_options`), the triggered half - "When this permanent
        # enters, if its evoke cost was paid, its controller sacrifices it" -
        # is `_evoke_ability`/`_evoke_effect` here.
        "evoke",
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
        return TotalCost.of(ManaCost.parse(printed)).assign_payer(payer)
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
    event: TriggerEvent,
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


def _mobilize_ability(ability: KeywordAbility) -> TriggeredAbility:
    """CR 702.181a: "Mobilize N" means "Whenever this creature attacks, create N
    1/1 red Warrior creature tokens. Those tokens enter tapped and attacking.
    Sacrifice them at the beginning of the next end step.""
    """
    count = ability.count if ability.count is not None else 1
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


#: The keyword lines this module can write out as triggered abilities, by the
#: Scryfall spelling of the keyword. A keyword missing from here is a keyword
#: `machines/triggers.py` still cannot produce.
_TRIGGER_EXPANSIONS: dict[str, Callable[[KeywordAbility], TriggeredAbility]] = {
    "ward": _ward_ability,
    "prowess": _prowess_ability,
    "cascade": _cascade_ability,
    "storm": _storm_ability,
    "persist": _persist_ability,
    "mobilize": _mobilize_ability,
    "evoke": _evoke_ability,
    "madness": _madness_ability,
    "hideaway": _hideaway_ability,
}


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
    for ability in keyword_abilities(card):
        expand = _TRIGGER_EXPANSIONS.get(ability.canonical.lower())
        if expand is not None:
            built.append(expand(ability))
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


def granted_keyword_ability(text: str) -> KeywordAbility | None:
    """One `CardState.granted_ability_texts` line read back as a CR 702 keyword.

    None for a line that is not a bare keyword, and None for a keyword this
    module writes no triggered ability for - a grant nothing here can expand
    hands out nothing rather than a guessed ability.
    """
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
            built.append(expand(ability))
    return built


# --------------------------------------------------------------------------
# Activating an ability, from whichever zone it functions in (CR 602.1a)
# --------------------------------------------------------------------------


class KeywordActivation(BaseModel):
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
    targets: list[TargetRef] = Field(default_factory=list)
    game: Any = Field(default=None, exclude=True, repr=False)
    payment: CostPayment | None = None
    on_stack: AbilityOnStack | None = None
    applied: bool = False
    """True once this keyword's effect has happened (CR 608.2).

    Set by `run_effect`, whoever calls it. It exists so the effect cannot happen
    twice when both the resolver and `resolve` know how to run it."""
    result: Any = Field(default=None, exclude=True, repr=False)
    """Whatever the effect returned, kept for the caller that asked."""
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
        effect = KEYWORD_EFFECTS.get(self.keyword.lower())
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
            self.sorcery_only
            and self.game is not None
            and not self.game.can_cast_sorcery(self.player)
        ):
            # CR 307.5: "only as a sorcery" means priority, own main phase,
            # empty stack - and nothing about actually casting a sorcery.
            return (
                f"{self.card.name}'s {self.keyword} ability can only be activated as a "
                f"sorcery: {self.player}'s main phase, with the stack empty "
                f"({self.rule}, CR 307.5)"
            )
        return None

    def begin_paying(self) -> CostPayment:
        """CR 602.2a-b: announce the activation and open its cost."""
        refusal = self.why_not()
        if refusal is not None:
            raise ValueError(refusal)
        if self.payment is None:
            self.payment = CostPayment.for_total(
                self.cost.assign_payer(self.player), game=self.game, payer=self.player
            )
        return self.payment

    def activate(self) -> AbilityOnStack:
        """Put the ability on the stack, its cost paid (CR 602.2).

        Not a mana ability, so it uses the stack and can be responded to
        (CR 605.1a is what would take it off).
        """
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
            # The link back, so the effect is findable from the object on the
            # stack rather than only from here (CR 113.1c, CR 608.2) - unset
            # for `generic_effect`, so `Game._effect_of` reaches the ordinary
            # card-text resolution instead of asking this module for one.
            keyword_activation=None if self.generic_effect else self,
        )
        self.game.stack.append(self.on_stack)
        self.game.put_triggers_on_stack()  # CR 117.3c hands priority straight back
        return self.on_stack

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
        """Rewind the cost, leaving everything where it was (CR 733.1)."""
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
    printed = cycling_abilities(card.card)
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
    return KeywordActivation(
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
                f"Search your library for a {typed} card, reveal it, and put it into your hand. "
                f"Then shuffle."
                if typed
                else "Draw a card."
            ),
        ),
        game=game,
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
    if typed is None:
        return game.draw_cards(activation.player, 1)

    # CR 702.29e: "Search your library for a [type] card, reveal it, and put it
    # into your hand. Then shuffle." The shuffle does not happen - a scenario's
    # rigged library is the point of the scenario - which is the same
    # concession Solemn Simulacrum's effect entry makes.
    owner = game.player(activation.player)
    for state in list(owner.library):
        if _matches_type(state.card, typed):
            owner.move(state, Zone.HAND)
            return [state]
    return []


def _matches_type(card: Card, named: str) -> bool:
    """Whether a card is of the type a typecycling ability names (CR 702.29e).

    The name is a land subtype ("Forest") for forestcycling and a card type
    ("Land") for landcycling, so both are tried - CR 205.2a for the card types,
    CR 305.6 for the basic land types.
    """
    if named.lower() in {subtype.lower() for subtype in card.subtypes}:
        return True
    try:
        return Type(named.lower()) in card.types
    except ValueError:
        return False


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
# Equip (CR 702.6)
# --------------------------------------------------------------------------


def equip_activation(
    game: Any, equipment: CardState, target: CardState, player: str
) -> KeywordActivation:
    """Build the activation for an Equipment's equip ability (CR 702.6a).

    "Equip is an activated ability of Equipment cards. 'Equip [cost]' means
    "[Cost]: Attach this permanent to target creature you control. Activate
    only as a sorcery.""

    CR 301.5b is why this is needed at all: "Equipment enter the battlefield
    like other artifacts. They don't enter the battlefield attached to a
    creature. The equip keyword ability attaches" it.
    """
    ability = _keyword(equipment.card, "equip")
    if ability is None:
        raise ValueError(f"{equipment.name} has no equip ability ({KeywordRule.EQUIP})")
    cost = _keyword_cost(ability, player)
    if cost is None:
        raise ValueError(
            f"{equipment.name}'s equip cost {ability.cost!r} could not be read, "
            f"so it cannot be paid"
        )
    return KeywordActivation(
        card=equipment,
        player=player,
        keyword="Equip",
        rule=str(KeywordRule.EQUIP),
        zone=Zone.BATTLEFIELD,
        cost=cost,
        sorcery_only=True,
        targets=[TargetRef.to_card(target)],
        ability=_synthetic_ability(
            ability,
            cost_text=ability.cost or "",
            effect="Attach this permanent to target creature you control.",
        ),
        game=game,
    )


def _equip_effect(activation: KeywordActivation) -> CardState | None:
    """Attach the Equipment to its target (CR 702.6a, CR 701.3a).

    The target is rechecked here because CR 608.2b does: a creature that has
    left the battlefield, or changed controller out from under "creature you
    control", is no longer a legal target and the ability does nothing.
    """
    game = activation.game
    for target in activation.targets:
        creature = game.resolve_target(target)
        if not isinstance(creature, CardState):
            continue
        if creature.zone is not Zone.BATTLEFIELD or not creature.is_creature:
            continue  # CR 301.5: an Equipment can't legally be attached to a noncreature
        if game.controller_of(creature).username != activation.player:
            continue
        activation.card.attach_to(creature)
        return creature
    return None


# --------------------------------------------------------------------------
# Crew (CR 702.122) and Vehicles (CR 301.7)
# --------------------------------------------------------------------------


def crew_activation(
    game: Any, vehicle: CardState, crewing: Sequence[CardState], player: str
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
    number = crew_number(vehicle.card)
    if number is None:
        raise ValueError(f"{vehicle.name} has no crew ability ({KeywordRule.CREW})")

    chosen = list(crewing)
    offer = crew_offer(vehicle)
    seen: set[UUID] = set()
    for creature in chosen:
        refusal = offer.why_not(creature, player, game)
        if refusal is not None:
            raise ValueError(refusal)
        if creature.id in seen:
            raise ValueError(
                f"{creature.name} was chosen twice to crew {vehicle.name}, but it has "
                f"only one untap to spend ({KeywordRule.CREW}, CR 118.3)"
            )
        seen.add(creature.id)

    have = total_power(chosen, game)
    if have < number:
        listing = ", ".join(f"{c.name} ({power_of(c, game)})" for c in chosen) or "nothing"
        raise ValueError(
            f"crewing {vehicle.name} needs total power {number} or greater, but "
            f"{listing} totals {have} ({KeywordRule.CREW})"
        )

    ability = _keyword(vehicle.card, "crew")
    assert ability is not None  # `crew_number` already found it
    cost = TotalCost(components=[offer.component(creature, player) for creature in chosen])
    return KeywordActivation(
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
    """
    game = activation.game
    vehicle = activation.card
    if vehicle.zone is not Zone.BATTLEFIELD:
        # CR 608.2: the ability resolves regardless, but a Vehicle that has
        # left the battlefield is a different object (CR 400.7) and nothing
        # here applies to it.
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
                selector=_only_this(vehicle.id),
                modification=add_type(added),
            )
        )
        for added in (Type.ARTIFACT, Type.CREATURE)
    ]
    return created


#: The subtypes CR 704.5n names, and the host each one may legally be on.
#: An Equipment attaches to a creature (CR 301.5a, CR 702.6a); a Fortification
#: attaches to a land, and CR 301.6 says "It can't legally be attached to an
#: object that isn't a land."
_ATTACHES_TO: dict[str, str] = {"Equipment": "creature", "Fortification": "land"}


def _host_is_legal_for(attached: CardState, host: CardState | None, wanted: str) -> bool:
    """Whether CR 704.5n's host is a legal one for this Equipment or Fortification."""
    if host is None or host.zone is not Zone.BATTLEFIELD:
        return False
    if host.id == attached.id:
        return False  # CR 301.5c: "An Equipment can't equip itself."
    return host.is_creature if wanted == "creature" else Type.LAND in host.types


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
    """
    unattached: list[CardState] = []
    for permanent in list(game.battlefield):
        if permanent.attached_to is None:
            continue
        wanted = next(
            (host_kind for name, host_kind in _ATTACHES_TO.items() if name in permanent.subtypes),
            None,
        )
        if wanted is None:
            continue  # CR 704.5m's Aura, or CR 704.5p's everything else.
        host = game.find_by_id(permanent.attached_to)
        host = host if isinstance(host, CardState) else None
        if not _host_is_legal_for(permanent, host, wanted):
            permanent.unattach()
            unattached.append(permanent)
    return unattached


def has_ascend(card: Card) -> bool:
    """Whether this card's own printed text grants *ascend* (CR 702.131)."""
    return any(keyword.lower() == "ascend" for keyword in card.keywords)


def ascend_state_based_actions(game: Any) -> list[str]:
    """CR 702.131b: "Ascend on a permanent represents a static ability. It
    means 'Any time you control ten or more permanents and you don't have the
    city's blessing, you get the city's blessing for the rest of the game.'"

    Read as a background check the same way `equipment_state_based_actions`
    and `aura_state_based_actions` are, rather than through
    `machines/triggers.py`: an "any time ... is true" static ability is
    CR 603.8's *state trigger* shape, not an ordinary event-triggered ability
    with a stack object of its own, so there is no `AbilityOnStack` for it to
    put on the stack. Getting the blessing is not itself a game object that
    resolves - it just happens, the moment the condition is met.

    `Player.has_citys_blessing` is CR 702.131c's designation, "no rules
    meaning other than to act as a marker" that, once set, nothing in the
    rules ever clears - so this only ever turns the flag on, and a player who
    already has it is skipped outright rather than rechecked.

    **CR 702.131a** (ascend printed on an instant or sorcery, a spell ability
    checked once as the spell resolves rather than a permanent's static
    check) is not modelled: nothing in the card pool prints ascend on a
    non-permanent.

    **Not modelled**: CR 702.131d - "After a player gets the city's blessing,
    continuous effects are reapplied before the game checks to see if the
    game state or preceding events have matched any trigger conditions." This
    engine's continuous effects are recomputed from scratch on every
    `computed_board()` call rather than reapplied incrementally, so there is
    no separate reapplication step for this rule to slot into; the only
    consequence would be a trigger that itself depends on already having the
    blessing seeing it one instant later than CR 702.131d demands, which
    nothing in the pool exercises.
    """
    blessed: list[str] = []
    for player in game.players_in_game:
        if player.has_citys_blessing:
            continue
        permanents = game.permanents_controlled_by(player.username)
        if len(permanents) < 10:
            continue
        if not any(has_ascend(permanent.card) for permanent in permanents):
            continue
        player.has_citys_blessing = True
        blessed.append(player.username)
    return blessed


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

    Not dispatched by `Game.check_state_based_actions`, which calls
    `equipment_state_based_actions` and not this - see `docs/engine-coverage.md`.
    """
    unattached: list[CardState] = []
    for permanent in list(game.battlefield):
        if permanent.attached_to is None:
            continue
        types = permanent.types
        if Type.CREATURE in types or Type.BATTLE in types:
            permanent.unattach()
            unattached.append(permanent)
            continue
        if any(name in permanent.subtypes for name in ("Aura", "Equipment", "Fortification")):
            continue
        permanent.unattach()
        unattached.append(permanent)
    return unattached


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
        profile.check(list(targets or []), player, game)

    cost = game.activation_cost(
        card, source_index, player, sacrificing=sacrificing, discarding=discarding
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
        generic_effect=True,
        game=game,
    )


# --------------------------------------------------------------------------
# Ward (CR 702.21)
# --------------------------------------------------------------------------


class WardTrigger(BaseModel):
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
        cost = ward_cost(permanent.card, payer)
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
    """
    if Type.CREATURE in spell.card.types:
        return []
    controller = spell.controller or game.active_player.username
    return [
        permanent
        for permanent in game.battlefield
        if permanent.is_creature
        and has_prowess(permanent.card)
        and game.controller_of(permanent).username == controller
    ]


#: What one prowess trigger does on resolution (CR 702.108a), applied by
#: `_prowess_effect` as a sublayer 7c continuous effect (CR 613.4c) that ends in
#: the cleanup step (CR 514.2, CR 703.4p).
prowess_bonus: tuple[int, int] = (1, 1)


# --------------------------------------------------------------------------
# Cascade (CR 702.85)
# --------------------------------------------------------------------------


class CascadeResult(BaseModel):
    """What one cascade trigger exiled and what it found (CR 702.85a)."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    exiled: list[CardState] = Field(default_factory=list)
    """Everything exiled on the way, the hit included, in the order exiled."""
    hit: CardState | None = None
    """The nonland card with a lesser mana value, or None if the library ran out."""


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
    reads). **Not modelled**: that added "if the resulting spell's mana value
    is less..." condition on the free cast itself - nothing in this pool casts
    the hit under a cost-altering effect that would change its mana value
    between the exile and the cast, so this is recorded as a known gap rather
    than guessed at; see `docs/engine-coverage.md`.

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

    - **"yes"** grants a `PlayPermission` (CR 601.3's dynamic half) for the
      hit, annotated `ExileMarker.CASCADE` so a caller can find it again, with
      `bottom_if_unused=True` - the hit stays in exile only until the caller
      actually casts it *or* until this permission would otherwise expire.

      This is **not** the same shape `machines/casting.finish_suspend` uses,
      on purpose, even though an earlier pass here justified it that way.
      CR 702.85a's own sentence is one instruction, read as a whole
      (CR 608.2c): "cast it... [or] put [it]... on the bottom" - there is no
      textual gap between them the way Ugin, Eye of the Storms' "−11:
      ...**Until end of turn**, you may cast..." or Ragavan, Nimble Pilferer's
      "...**Until end of turn**, you may cast that card." print one, and
      Suspend's own third ability (CR 702.62a) names its own fallback
      outright - "if you don't, it remains exiled" - so leaving the card
      sitting in exile is genuinely that rule's own terminal state. Cascade
      prints neither an "until end of turn" grant nor an "it remains exiled"
      fallback; its only named resting place for a card that "weren't cast"
      is the bottom of the library. `Game._bottom_unused_cascade_permissions`,
      run from `cleanup_step` the instant before an expiring `until_end_of_
      turn` permission would otherwise just be dropped, is what keeps that
      true even when a live caller answers "yes" and then never actually
      drives `Casting.use_permission()` through to a real cast - the one hole
      the earlier pass left open, because it deferred *only* to "the caller",
      the same shape that is correct for Ugin/Ragavan/Suspend precisely
      because their own rules name an "outlives the resolution" duration or
      an explicit fallback and cascade's does not.
    - **"no"**, or "yes" refused because `affirmative_is_legal` was False -
      goes straight onto the bottom, in the very same random shuffle the
      misses get, exactly as CR 702.85a's single sentence says: nothing here
      leaves a hit dangling on the strength of a choice that was never really
      offered.

    The cards go to the bottom in a random order, which is a real shuffle of a
    known set rather than the library shuffle the engine does not model; `seed`
    pins it so a scenario stays reproducible.
    """
    from .casting import PlayAction, why_cannot_cast_restriction  # casting imports this module

    controller = spell.controller or game.active_player.username
    owner = game.player(controller)
    threshold = spell.card.cmc

    result = CascadeResult()
    while owner.library:
        state = owner.library[0]
        owner.move(state, Zone.EXILE)
        game.exile.append(state)
        result.exiled.append(state)
        if not state.card.is_land and state.card.cmc < threshold:
            result.hit = state
            break

    cast_hit = False
    if result.hit is not None:
        restriction = why_cannot_cast_restriction(result.hit, owner.username, game)
        decision = Decision(
            kind=DecisionKind.MAY,
            player=owner.username,
            prompt=f"cast {result.hit.name} without paying its mana cost (cascade)",
            source=spell.name,
            affirmative_is_legal=restriction is None,
        )
        cast_hit = bool(game.ask(decision))
        if cast_hit:
            result.hit.exile_annotation = ExileAnnotation(
                marker=ExileMarker.CASCADE, owner=owner.username
            )
            game.grant_play_permission(
                result.hit,
                owner.username,
                action=PlayAction.CAST,
                pays_mana_cost=False,
                source_name=f"{spell.name}'s cascade",
                rule="CR 702.85a",
                bottom_if_unused=True,
            )

    bottomed = [state for state in result.exiled if not (cast_hit and state is result.hit)]
    random.Random(seed).shuffle(bottomed)
    for state in bottomed:
        game.exile.remove(state)
        owner.add(state, Zone.LIBRARY)  # the bottom of the library
    return result


# --------------------------------------------------------------------------
# Persist (CR 702.79)
# --------------------------------------------------------------------------


def has_persist(card: Card) -> bool:
    return any(keyword.lower() == "persist" for keyword in card.keywords)


def persist_return(game: Any, card: CardState) -> CardState | None:
    """Perform a persist trigger (CR 702.79a).

    "Persist is a triggered ability. 'Persist' means "When this permanent is put
    into a graveyard from the battlefield, if it had no -1/-1 counters on it,
    return it to the battlefield under its owner's control with a -1/-1 counter
    on it.""

    The intervening *if* is about the permanent as it last existed, and CR 122.2
    destroyed its counters on the way out - so `last_known_counters` is what is
    read (CR 704.8, CR 603.10a). Returns the permanent, or None when the *if*
    was false, which is what stops a persisted creature persisting forever.
    """
    if not has_persist(card.card):
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


# --------------------------------------------------------------------------
# Rebound (CR 702.88)
# --------------------------------------------------------------------------


def has_rebound(card: Card) -> bool:
    """CR 702.88a: "Rebound appears on some instants and sorceries." Read the
    same way `has_persist` reads a permanent keyword - off Scryfall's own
    `keywords` list rather than a substring search of the oracle text, so a
    card that merely *mentions* the word in reminder text elsewhere is never
    mistaken for one that prints the ability.
    """
    return any(keyword.lower() == "rebound" for keyword in card.keywords)


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
    count = dredge_count(card.card)
    if count is None:
        return f"{card.name} has no dredge ability ({KeywordRule.DREDGE})"
    if card.zone is not Zone.GRAVEYARD:
        return (
            f"{card.name}'s dredge ability functions in a graveyard, but it is in "
            f"the {card.zone.value} ({KeywordRule.DREDGE})"
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
    refusal = why_cannot_dredge(game, card, player)
    if refusal is not None:
        raise ValueError(refusal)
    count = dredge_count(card.card)
    assert count is not None

    owner = game.player(player)
    milled = list(owner.library[:count])
    for state in milled:
        owner.move(state, Zone.GRAVEYARD)  # CR 701.17a
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


def why_cannot_turn_face_up(permanent: CardState) -> str | None:
    """Why the CR 702.37e special action is unavailable right now, or None.

    "Any time you have priority, you may turn a face-down permanent you control
    with a morph ability face up. This is a special action; it doesn't use the
    stack (see rule 116). To do this, show all players what the permanent's
    morph cost would be if it were face up, pay that cost, then turn the
    permanent face up. **(If the permanent wouldn't have a morph cost if it were
    face up, it can't be turned face up this way.)**"

    That last clause is why the check is against the card and not against the
    face-down object: the object has no text at all (CR 708.2), so the morph
    cost has to be read off the printing it is hiding.
    """
    if permanent.zone is not Zone.BATTLEFIELD:
        return (
            f"{permanent.card.name} is in the {permanent.zone.value}; only a permanent "
            f"can be turned face up ({KeywordRule.MORPH})"
        )
    if permanent.face_up:
        return f"{permanent.card.name} is already face up"
    ability = morph_ability(permanent.card)
    if ability is None or not ability.cost:
        return (
            f"{permanent.card.name} would have no morph cost if it were face up, so it "
            f"cannot be turned face up this way (CR 702.37e)"
        )
    return None


def turn_face_up_cost(permanent: CardState, player: str) -> TotalCost | None:
    """The morph cost this permanent pays to be turned face up (CR 702.37e)."""
    ability = morph_ability(permanent.card)
    if ability is None:
        return None
    return _keyword_cost(ability, player)


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
    owner = game.player(player)
    if card not in owner.cards_in(Zone.HAND):
        raise ValueError(f"{card.name} is not in {player}'s hand (CR 701.9a)")

    if not madness_replaces_discard(card):
        owner.move(card, Zone.GRAVEYARD)
        return card

    turn = getattr(getattr(game, "turn", None), "turn_number", None)
    owner.cards_in(Zone.HAND).remove(card)
    card.move_to(Zone.EXILE)
    card.exile_annotation = madness_annotation(card, turn)
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


def enchant_restrictions(card: Card) -> list[str]:
    """What every `Enchant [object or player]` line on this card demands.

    CR 702.5a: "Enchant is a static ability, written 'Enchant [object or
    player].' The enchant ability restricts what an Aura spell can target and
    what an Aura can enchant."

    CR 702.5c is why this is a list and not one string: "If an Aura has multiple
    instances of enchant, **all of them apply**. The Aura's target must follow
    the restrictions from all the instances of enchant."
    """
    return [
        (ability.parameter or "").strip()
        for ability in keyword_abilities(card)
        if ability.canonical.lower() == "enchant" and (ability.parameter or "").strip()
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

    restrictions = enchant_restrictions(aura.card)
    if not restrictions:
        return f"{aura.name} has no enchant ability, so it cannot be attached (CR 702.5a)"

    for restriction in restrictions:
        profile = profile_for_text(f"target {restriction}")
        if not profile.understood or not profile.requirements:
            continue  # unread, so unchecked - see docs/engine-coverage.md
        refusal = profile.requirements[0].rejects(target, caster, game)
        if refusal is not None:
            return f"{aura.name} says 'Enchant {restriction}': {refusal} (CR 702.5a)"
    return None


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
    """
    doomed: list[CardState] = []
    for permanent in list(game.battlefield):
        if "Aura" not in permanent.subtypes:
            continue
        attachment = permanent.attachment
        if attachment is None:
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
            selector=_only_this(source.id),
            modification=modify_power_toughness(power, toughness),
        )
    )


def _only_this(card_id: UUID) -> Callable[[Any, Any], bool]:
    """A layer selector that picks out one permanent (CR 611.2c)."""

    def selector(chars: Any, board: Any) -> bool:
        return bool(chars.card_id == card_id)

    return selector


def _persist_effect(game: Any, ability: AbilityOnStack) -> CardState | None:
    """CR 702.79a's effect: return it with a -1/-1 counter on it.

    The intervening *if* has already been checked twice by the time this runs -
    once when it triggered (CR 603.4) and once on resolution (CR 608.2a) - so
    there is nothing left to test here.
    """
    source = ability.source(game)
    if source is None or source.zone is not Zone.GRAVEYARD:
        return None
    return persist_return(game, source)


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
    """CR 702.85a's exiling half.

    Casting the hit is left to the caller: "You may cast that card", and there
    is nobody here to ask - the same concession every optional trigger in this
    engine makes (CR 603.5). `cascade` performs the exiling and the bottoming.
    """
    source = ability.source(game)
    if source is None:
        return None
    return cascade(game, source)


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
        game.offer_new_targets_for_copy(copy, controller, source_name=source.name)
        copies.append(copy)
    return copies


def _ward_effect(game: Any, ability: AbilityOnStack) -> bool:
    """CR 702.21a's effect: "counter that spell or ability unless that player pays".

    The "unless" is read off **this very ability**: `WardTrigger` opens the
    payment on `AbilityOnStack.unless_payment`, so the object that was paid is
    the object now resolving. Ward's cost is paid as the trigger resolves, and
    a second standalone object holding the payment could only disagree with
    this one.

    Nobody can be asked at this point whether they want to pay, so a payment
    that was never opened, or opened and not finished, counts as unpaid and the
    spell is countered - the opposite default to an optional trigger, and the
    right one: CR 702.21a makes countering what happens *unless* something is
    done, rather than something a player opts into.

    Returns True if the targeting spell or ability survived.
    """
    if ward_was_paid(ability):
        return True
    event = ability.event
    if event is None or event.targeted_by is None:
        return True
    for item in list(game.stack):
        if getattr(item, "id", None) == event.targeted_by:
            game.counter(item)  # CR 701.6a
            return False
    # CR 608.2b is not this: the spell is simply no longer on the stack, so
    # there is nothing left to counter.
    return True


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
    printed = ability.ability
    text = printed.effect if isinstance(printed, TriggeredAbility) else ""
    match = _HIDEAWAY_COUNT_RE.search(text or "")
    count = int(match.group("n")) if match is not None else 4
    controller = game.controller_of(ability)
    looked = list(controller.library[:count])
    if not looked:
        return
    decision = Decision(
        kind=DecisionKind.CHOOSE_CARDS,
        player=controller.username,
        prompt=f"exile a card face down with {source.name} (hideaway)",
        source=source.name,
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

    if rest:
        rng = random.Random(  # noqa: S311
            f"{game.shuffle_seed}:{game.shuffles_performed}:hideaway-{source.id}"
        )
        rng.shuffle(rest)
        for state in rest:
            controller.move(state, Zone.LIBRARY)
        game.shuffles_performed += 1


#: What one keyword's triggered ability does when it resolves, by keyword.
#: `Game._effect_of` has to consult this before the card-name registry - see
#: `docs/engine-coverage.md` for the hook.
KEYWORD_TRIGGER_EFFECTS: dict[str, Callable[[Any, AbilityOnStack], Any]] = {
    "prowess": _prowess_effect,
    "persist": _persist_effect,
    "cascade": _cascade_effect,
    "storm": _storm_effect,
    "ward": _ward_effect,
    "madness": _madness_effect,
    "hideaway": _hideaway_effect,
    "evoke": _evoke_effect,
}


def keyword_trigger_effect(
    ability: TriggeredAbility,
) -> Callable[[Any, AbilityOnStack], Any] | None:
    """The effect of a triggered ability that was printed as a keyword, or None.

    Mobilize (CR 702.181a) deliberately has no entry: its effect is creating
    tokens, and nothing in this engine creates one - see
    `docs/engine-coverage.md`. The trigger still fires, goes on the stack, and
    can be responded to; it simply does nothing when it gets there, which is the
    same shape as a card with no entry in `machines/effects.py`.
    """
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
}

for _name in ("cycling", "landcycling", "typecycling"):
    KEYWORD_EFFECTS[_name] = _cycling_effect
for _land in ("plains", "island", "swamp", "mountain", "forest"):
    KEYWORD_EFFECTS[f"{_land}cycling"] = _cycling_effect
del _name, _land
