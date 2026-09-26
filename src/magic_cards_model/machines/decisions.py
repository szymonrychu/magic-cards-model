"""Asking a player a question while a spell or ability is resolving (CR 608.2d).

Every CR number in this file was looked up with
`knowledge_search(q="...", type="rules")` in the session that wrote it, and the
full text of each was then read out of the `2026-08-19` Comprehensive Rules
release named by `knowledge_search(type="cr_versions")`, verified against the
sha256 that call publishes (`4381ad1b...423f`). The excerpts truncate at roughly
150 characters and the deciding clause of CR 608.2d is in the tail.

**CR 608.2d** is the whole reason this module exists:

    If an effect of a spell or ability offers any choices other than choices
    already made as part of casting the spell, activating the ability, or
    otherwise putting the spell or ability on the stack, the player announces
    these while applying the effect. The player can't choose an option that's
    illegal or impossible, with the exception that having a library with no
    cards in it doesn't make drawing a card an impossible action (see rule
    121.3).

Two consequences are modelled here and nowhere else:

- *The player announces these while applying the effect.* A choice belongs to
  resolution, not to announcement - which is why this is not part of
  `machines/casting.py`.
- *The player can't choose an option that's illegal or impossible.* Every
  question carries its legal options and a decision is filtered against them
  before it is answered. A question with exactly one legal option is answered
  without asking; a question with none is not asked at all, and the caller is
  told nothing was chosen.

**CR 614.12a** puts the same machinery in front of a permanent entering the
battlefield: "If a replacement effect that modifies how a permanent enters the
battlefield requires a choice, that choice is made before the permanent enters
the battlefield." That is the shockland.

**CR 101.4** orders simultaneous choices in APNAP order, and **CR 101.4c** says
a player making more than one choice at once makes them in the order specified,
or in an order of their choosing. Neither is exercised yet: every question this
engine asks is asked of one player at a time, in the order the effect prints.

## There is no player agent, and there is deliberately not going to be one

A rules engine cannot invent an opponent. What it can do is make the question
explicit, so that a caller - a test, a UI, a future agent - answers it. That is
`DecisionScript`: a queue of answers, matched to the questions as they are
asked. `tests/scenarios/harness.py` fills it in; see `Scenario.scry_bottoms` and
its siblings.

There is exactly one way to answer a decision from outside the engine, and
every asker in this module uses it the same way: `Game.ask` tries a scripted
answer first (a test's staging always wins), then the replay tape
(`DecisionScript.recorded`, see below), then a pause if
`DecisionScript.pause_when_unanswered` is set, and only then `default_answer`.
`ask_mulligan` and `ask_trigger_order` follow that same order without going
through `Game.ask`, so CR 103.5's declaration and CR 603.3b's ordering are
answerable the same way. `_ask_declaration` (the two combat declarations,
`ask_attackers`/`ask_blockers`) follows it too, with nothing left out - a
scripted answer, then the tape, then a pause if enabled, then `default_answer`.
A live seat outside the engine - the API's own transport - answers by staging
into the script or the tape, never by blocking this module's call stack.

## Pausing instead of blocking: `Answer`, the tape, and `DecisionPending`

Blocking the thread that is resolving a spell for as long as a live seat takes
to answer is the whole reason `docs/../memory/harness-deadlock-defaulted-
every-decision.md` exists. The alternative this module supports instead is
**pausing**: instead of a call that blocks, a caller sets
`DecisionScript.pause_when_unanswered = True`, and a question nothing can
answer raises `DecisionPending` rather than defaulting or blocking. The raise
carries a `PendingDecision` - the question, its sequence number, and the CR
citation that governs it - for a caller to store however it stores a paused
game.

Resuming is replay, not a checkpoint: there is no mid-effect state to save, so
the caller re-runs the same command from the last *committed* snapshot,
answers included. `DecisionScript.recorded` is that answer tape - a list of
`Answer`, oldest first - and `DecisionScript.consumed` is how far this run has
read into it. `DecisionScript.begin_replay` is how a caller starts that
re-run: it loads the tape, zeroes `consumed`, and clears `asked`, so a resumed
run's `PendingDecision.seq` numbering starts at 0 exactly like the first
attempt's did, rather than inheriting a stale, uncleared count from whatever
this `Game` object happened to carry forward; `DecisionScript.finish_replay`
is the other half, raising if a command finished without reading the whole
tape - the mirror image of a tape that runs out too soon.

Every one of the four askers (`Game.ask`, `ask_mulligan`, `ask_trigger_order`,
`_ask_declaration`) reads the tape positionally, right after a scripted
answer: `recorded[consumed]` is the next answer, and a tape whose next entry
names the wrong kind, the wrong player, or the wrong `seq` is corrupt -
replayed against the wrong question, it would produce a wrong game that still
runs to completion, which is worse than a crash, so it raises rather than
being skipped past (see `DecisionScript.take_from_tape`). All four then fall
through to a pause or `default_answer` the same way. The mutated `Game` from
the paused attempt is discarded, never stored - which is what makes
double-applying an answer structurally impossible: there is nothing left to
apply it to twice.

When nobody - script or tape - has anything to say, `default_answer`
answers instead, by a rule written down here rather than improvised per card:

- `MAY` - **take it**, which is what the effect registry already did before this
  module existed, so no registered card changes behaviour.
- `PAY_LIFE` - **pay**, whenever CR 119.4 allows it. The affirmative branch, and
  the one that leaves the permanent untapped.
- `SCRY` - **keep every card on top**. CR 701.22a permits putting "any number"
  on the bottom, and none is a number.
- `SURVEIL` - **keep every card on top**, by CR 701.25a and the same reasoning.
- `MULLIGAN` - **keep**. A mulligan is a decision a scenario states; an
  unscripted player keeps the hand they were dealt (CR 103.5).
- `OPENING_HAND_ACTION` - **decline**. CR 103.6's "may take any such actions" is
  the same shape and gets the same treatment: an unscripted player does not
  begin the game with a Leyline on the battlefield (CR 103.6a) or reveal a card
  from their opening hand (CR 103.6b) unless somebody says so.

A default is a documented deviation, not a decision. A scenario that cares says
what it wants.

The mulligan declaration was the first question here that the rules ask rather
than a resolving effect: CR 103.5 has every player declare, in turn order,
whether they will take a mulligan. It is a boolean like `MAY`, with the opposite
default, and `ask_mulligan` is how it is put. The combat declarations joined it:
CR 703.4i has the active player declare which creatures attack (CR 508.1), and
CR 703.4j has each defending player declare blockers (CR 509.1), both asked when
their step's turn-based action runs rather than while anything resolves.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import ConfigDict, model_validator

from magic_cards_model.phrases import with_indefinite_article

from ..models.card_state import TargetRef
from ..snapshot import EngineModel

if TYPE_CHECKING:  # pragma: no cover - import cycle: the models build on the machines
    from ..models.card_state import CardState
    from .triggers import AbilityOnStack

__all__ = [
    "Answer",
    "CardSplit",
    "DamageAssignment",
    "Decision",
    "DecisionKind",
    "DecisionPending",
    "DecisionScript",
    "DeclaredPair",
    "PendingAbility",
    "PendingDecision",
    "ScriptedAnswer",
    "ask_attackers",
    "ask_blockers",
    "ask_mulligan",
    "ask_trigger_order",
    "damage_assignment_answer",
    "default_answer",
    "legal_options",
    "rule_for_kind",
    "source_id_of",
]


class DecisionKind(StrEnum):
    """The kinds of question a player is asked - while a resolving effect makes
    its choices (CR 608.2d), or while a turn-based action does its work."""

    #: A plain "you may" - a yes-or-no with no cost attached.
    MAY = "may"
    #: "You may pay N life" (CR 119.4). Illegal below N life, hence its own kind.
    PAY_LIFE = "pay_life"
    #: A fixed-amount "you may pay {E}..." (Static Prison's "unless you pay
    #: {E}" is the same shape read the other way round: paying is what avoids
    #: the bad outcome rather than what causes a good one, but CR 107.14's
    #: payment and CR 118.3's affordability check are identical either way).
    #: Illegal when the player does not have `amount` energy counters to
    #: remove, the same `affirmative_is_legal` shape `PAY_LIFE` already uses
    #: for CR 119.4's life-total floor.
    PAY_ENERGY = "pay_energy"
    #: A fixed-amount "unless its controller pays {N}" (Censor, Mystical
    #: Dispute). CR 118.12a: "[Do something] unless [a player does something
    #: else]" means "[a player] may [do something else]. If [that player]
    #: doesn't, [effect]." - so this is `MAY`'s shape read backwards, the same
    #: way `PAY_ENERGY`'s docstring already reads Static Prison's "unless".
    #: `Decision.player` is the *target spell's* controller, not the resolving
    #: counterspell's - CR 608.2d's "the player" is whoever the effect names.
    #:
    #: CR 608.2g: "If an effect gives a player the option to pay mana, they may
    #: activate mana abilities before taking that action." The floating pool
    #: and the untapped mana sources in `Decision.mana_sources` both count
    #: toward `affirmative_is_legal`; the answer is `True` (the engine picks
    #: the sources, as `CostPayment.auto_tap` does), `False`, or a tuple of the
    #: offered source ids to activate while paying.
    PAY_MANA = "pay_mana"
    #: "You may pay any amount of {E}" (Galvanic Discharge, Wrath of the
    #: Skies) - CR 107.14/118.3's variable-amount cousin of `PAY_ENERGY`. The
    #: answer is an `int` from 0 up to `Decision.amount` (the energy the
    #: player has when asked), not a bool: declining is paying 0, which is
    #: always legal, and paying more than is available is not (CR 118.3).
    PAY_ENERGY_AMOUNT = "pay_energy_amount"
    #: "You may pay any amount of life" (Necrodominance) - CR 119.4's
    #: variable-amount cousin of `PAY_LIFE`, the same relationship
    #: `PAY_ENERGY_AMOUNT` already has to `PAY_ENERGY`. The answer is an
    #: `int` from 0 up to `Decision.amount` (the payer's life total when
    #: asked, CR 119.4's "only if their life total is greater than or equal
    #: to the amount of the payment" - paying down to exactly 0 is legal,
    #: only *below* 0 is not); declining is paying 0, always legal
    #: (CR 119.4b: "Players can always pay 0 life").
    PAY_LIFE_AMOUNT = "pay_life_amount"
    #: Scry N: which of the looked-at cards go to the bottom (CR 701.22a).
    SCRY = "scry"
    #: Surveil N: which of them go to the graveyard (CR 701.25a).
    SURVEIL = "surveil"
    #: Whether to take a mulligan (CR 103.5). True takes one, False keeps.
    #: Asked by the starting-a-game process, not while an effect resolves, and
    #: never offered once CR 103.5's zero-hand ceiling has been reached.
    MULLIGAN = "mulligan"
    #: Whether to take one of CR 103.6's opening-hand actions - beginning the
    #: game with a card on the battlefield (CR 103.6a) or revealing it from the
    #: opening hand (CR 103.6b). Asked once per offering card, in the sequence
    #: that runs after the mulligan process completes and before the first turn
    #: begins (CR 103.8), so like `MULLIGAN` it belongs to the rules rather than
    #: to a resolving effect.
    #:
    #: A boolean like `MAY`, and deliberately **not** `MAY`: CR 103.6 says the
    #: player "may take any such actions", and an unscripted player should not
    #: silently start the game with a Leyline on the battlefield. The default is
    #: therefore to decline, the same way `MULLIGAN`'s is to keep - see
    #: `default_answer`.
    OPENING_HAND_ACTION = "opening_hand_action"
    #: Which creatures attack, and at whom (CR 703.4i, 508.1). Asked of the
    #: active player when the declare attackers step begins. The value is
    #: `(creature, defender)` pairs, in declaration order.
    DECLARE_ATTACKERS = "declare_attackers"
    #: Which creatures block which attackers (CR 703.4j, 509.1). Asked of each
    #: defending player in turn order (CR 802.4) when the declare blockers step
    #: begins. The value is `(blocker, attacker)` pairs.
    DECLARE_BLOCKERS = "declare_blockers"
    #: How one blocked attacking creature divides its combat damage (CR 703.4k,
    #: 510.1c, 702.19b). Asked of the attacking creature's controller as the
    #: combat damage step begins, and only when there is something to choose:
    #: two or more blockers, or trample with power beyond the blockers' lethal
    #: damage. `cards` is the attacker then its blockers, `targets` every legal
    #: recipient (the defender too, with trample), `lethal_damage` aligned with
    #: `targets`, and `amount` the power to assign. The value is
    #: `(target, amount)` pairs.
    ASSIGN_COMBAT_DAMAGE = "assign_combat_damage"
    #: Choose exactly `amount` cards out of `cards`, a candidate set drawn from
    #: one zone. The cleanup discard (CR 514.1, CR 703.4n) is the first caller -
    #: CR 701.9b: "effects that cause a player to discard a card allow the
    #: affected player to choose which card to discard" - but the shape is
    #: general on purpose: any "choose N of these cards" question (a search
    #: turning up more hits than needed, choosing among revealed cards) is the
    #: same question with a different prompt and a different source zone, so it
    #: reuses this kind rather than growing a new one per card.
    #:
    #: CR 103.5's bottoming is one of those callers, and the one furthest from
    #: a resolving effect: keeping a hand after a mulligan costs "the number of
    #: cards that player will put on the bottom of their library" (CR 103.5c,
    #: CR 800.6), and *which* cards those are is the keeper's choice. It is
    #: asked here rather than as its own kind because the shape is identical -
    #: exactly N, out of one zone, order significant - and because
    #: `default_answer`'s "back of the offered cards" is already, to the card,
    #: what `Player.keep_hand(None)` did before anyone was asked.
    CHOOSE_CARDS = "choose_cards"
    #: "Choose any number of ... players" (CR 701.34a's own proliferate,
    #: verbatim - `machines/effects._parse_proliferate_clause`'s own player
    #: half) - `CHOOSE_CARDS`' twin for a CR 608.2d choice among candidate
    #: *players* rather than cards, over `Decision.players` (a tuple of
    #: usernames, positionally what `Decision.cards` already is for card
    #: ids) instead of `Decision.cards`. Not `CHOOSE_TARGETS`: nothing here
    #: is a CR 115.1 target - proliferate's own choice is CR 608.2c/608.2d
    #: prose ("choose ... players"), never the word "target", so it carries
    #: none of CR 601.2c's announcement-time legality machinery (no CR
    #: 608.2b on-resolution re-check, no protection/hexproof refusal) - only
    #: "is this a subset of what was offered, and does the count match".
    CHOOSE_PLAYERS = "choose_players"
    #: Choose up to `target_maximum` targets out of `targets` for a spell or
    #: ability that has already been put on the stack (CR 115.1, CR 603.3d).
    #: Not `CHOOSE_CARDS`: a target may be a player (Footlight Fiend's "target
    #: player") or an ability on the stack (Tishana's Tidebinder), not only a
    #: card, and CR 115.6's "up to N" is optional rather than exact - `amount`
    #: means exactly `amount`, which "up to" is not.
    #:
    #: `target_minimum` carries the floor: CR 601.2c has the player "announce
    #: their choice of an appropriate object or player for each target the
    #: spell requires" - a plain "target permanent" is not a "you may", so an
    #: answer choosing fewer than `target_minimum` legal targets is refused by
    #: `Game.ask` exactly like an illegal target is, whenever enough legal
    #: targets exist to meet it. `target_minimum` is 0 for an "up to N"/"any
    #: number of" requirement (CR 115.6, CR 107.1c), which is genuinely
    #: optional - Karn, the Great Creator's "up to one target artifact" may
    #: choose zero and must then affect nothing; see
    #: `tests/scenarios/test_type_changing_and_pt_setting_effects.py`. The
    #: default answer is now the first `target_minimum` offered targets when
    #: that floor is above zero, not empty; see `default_answer` and
    #: `Game.put_triggers_on_stack`.
    CHOOSE_TARGETS = "choose_targets"
    #: "As [this] enters, choose a color/card name/creature type" (CR 614.1c,
    #: CR 614.12a). One kind for all three shapes: `Decision.options` narrows
    #: the legal answers to the five colors for a color choice and to CR
    #: 205.3m's creature types for a creature type choice, and is empty for a
    #: card name, whose universe (every card name) is too large to enumerate
    #: here. `Decision.quality` names which of the three was asked, so a
    #: refusal can say what the answer failed to be; the replacement effect
    #: that asks records it on `CardState.choice`'s own `ChoiceKind` once the
    #: answer comes back.
    CHOOSE_A_QUALITY = "choose_a_quality"
    #: CR 603.3c/700.2b: "The controller of a modal triggered ability chooses
    #: the mode(s) as part of putting that ability on the stack." Elder
    #: Gargaroth's "Whenever this creature attacks or blocks, choose one -"
    #: is the only printing in the pool, and it is always exactly one mode
    #: (a plain "choose one", never "choose one or more"), so the answer is
    #: one of `Decision.options` - the mode's own printed text - rather than
    #: an index; `Decision.source` is the ability's source, same as every
    #: other kind here.
    CHOOSE_A_MODE = "choose_a_mode"
    #: "[Its owner] puts it on their choice of the top or bottom of their
    #: library" (Subtlety) - CR 608.2d's own choice, made by whichever player
    #: the effect names (CR 401.2's order otherwise fixed), not by the
    #: resolving ability's controller. `True` is the top, `False` the bottom -
    #: a plain boolean rather than `CHOOSE_A_QUALITY`'s open `options` string,
    #: because there are exactly two answers and neither is a color, a card
    #: name, or a creature type (that kind's own documented scope, CR 614.1c/
    #: 614.12a). The default keeps the card visible rather than buried, the
    #: same "least destructive, most reversible" posture `SCRY`/`SURVEIL`'s own
    #: "keep everything on top" default already takes.
    PUT_ON_TOP_OR_BOTTOM = "put_on_top_or_bottom"
    #: CR 700.3's own two-way pile split (Liliana of the Veil's own `-6`,
    #: "Separate all permanents target player controls into two piles. That
    #: player sacrifices all permanents in the pile of their choice."; Do or
    #: Die's identical shape). Two *different* players are involved and two
    #: *different* `Game.ask` calls happen, in order - CR 608.2c's own
    #: unattributed "Separate ... into two piles" is CR 608.2c's resolving
    #: controller's own instruction (confirmed against the card's official
    #: ruling: "you put each permanent the player controls into one of the
    #: two piles"), read the identical `CHOOSE_CARDS` way `SCRY`/`SURVEIL`
    #: already read "which of these move" (`exact=False`, 0 up to all,
    #: CR 700.3d's "a pile can contain zero or more objects") - "pile one" is
    #: whatever that first answer names, "pile two" the complement among the
    #: same qualifying set. Only the *second* choice - which whole pile the
    #: instruction actually acts on - is this kind, asked of the player the
    #: card names for it (Liliana's/Do or Die's own "that player", i.e. the
    #: ability's target), a plain boolean the identical shape `PUT_ON_TOP_OR_
    #: BOTTOM` already is: `True` for pile one (`Decision.cards`, the first
    #: player's own choice of what to put there), `False` for its complement
    #: - not enumerated a second time on the decision, since the chooser is a
    #: real player who can already see every permanent the target controls
    #: and just read off which of them `Decision.cards` names.
    CHOOSE_PILE = "choose_pile"
    #: CR 603.3b: "If multiple abilities have triggered since the last time a
    #: player received priority, the abilities are placed on the stack in a
    #: two-part process. First, each player, in APNAP order, puts each
    #: triggered ability they control on the stack **in any order they
    #: choose**." That last clause is a real choice and this is it - asked of
    #: one player, about the abilities *that player* controls, once APNAP has
    #: already fixed which player's block goes on first.
    #:
    #: Not a resolving effect's choice (CR 608.2d), so it sits beside
    #: `MULLIGAN` and the two combat declarations as a question the rules ask.
    #:
    #: `Decision.cards` carries the `AbilityOnStack.id` of each of that
    #: player's waiting abilities, in the order they triggered. The answer is a
    #: permutation of exactly those ids, **bottom of the stack first** - so the
    #: last id in the answer is the one that resolves first, which is the way
    #: round DDR#983's trick needs (put the Harrier's on last, resolve it
    #: first). An answer that is not a permutation of what was offered is
    #: refused; the default is the offered order unchanged, which is what this
    #: engine did before anybody was asked.
    ORDER_TRIGGERS = "order_triggers"
    #: CR 702.52a: "if you would draw a card, you may instead mill N cards
    #: [...] return this card from your graveyard to your hand." Asked once
    #: for each individual draw (CR 121.2) a player is about to make, naming
    #: every graveyard card whose dredge is satisfiable right now
    #: (`Decision.cards`, filtered by `machines/keywords.why_cannot_dredge`'s
    #: own CR 702.52b library-size floor already) - not asked at all when
    #: none is. CR 616.1e: several optional replacement effects competing for
    #: the same event, any one of which "may be chosen" - the answer is an
    #: empty tuple to decline (draw normally, the unscripted default) or a
    #: single chosen card's id, never more than one, since a single draw
    #: can only be replaced once.
    DREDGE = "dredge"


@dataclass(frozen=True)
class CardSplit:
    """The answer to a scry or a surveil (CR 701.22a, CR 701.25a).

    Both rules have the same shape - look at N, move *any number* of them
    somewhere, put *the rest* on top in any order - so one answer serves both.
    Where "somewhere" is depends on the question: the bottom of the library for
    a scry, the graveyard for a surveil.

    Cards are named by `CardState.id` so an answer can be written before the
    cards are looked at, which is what lets a scenario say what it wants in
    advance.
    """

    #: The cards leaving the top: to the bottom (scry) or to the graveyard
    #: (surveil). "Any number of them", so an empty tuple is a real answer.
    moved: tuple[UUID, ...] = ()
    #: The order the rest go back on top, topmost first. None keeps the order
    #: they were looked at in - "the rest on top of your library in any order"
    #: leaves that free, so the engine has to pick something, and picking
    #: "unchanged" is the choice that makes a rigged library stay rigged.
    top_order: tuple[UUID, ...] | None = None


@dataclass(frozen=True)
class PendingAbility:
    """One triggered ability waiting to be ordered onto the stack (CR 603.3).

    "Once an ability has triggered, its controller puts it on the stack as an
    object that's not a card" (CR 603.3), and "an ability can be an activated
    or triggered ability on the stack. This kind of ability is an object"
    (CR 113.1c) - an object with no card behind it, and, at the moment
    `ORDER_TRIGGERS` is asked, in no zone at all (CR 603.3b is asked one step
    *before* CR 603.3 puts it on the stack). CR 603.3a controls it by "the
    player who controlled its source at the time it triggered", which is
    `controller` here.

    This is `Decision.abilities`' own element, one per `Decision.cards` entry,
    positionally aligned - the structured twin of `card_labels`' prose, built
    by `source_id_of(ability)` so `source_id` follows the same convention
    `Decision.source_id` does.
    """

    #: The `AbilityOnStack.id` this entry names - the same id `Decision.cards`
    #: holds at this position.
    id: UUID
    #: The source's own battlefield id (`source_id_of`), or `None` when the
    #: source has none to give (`AbilityOnStack.source_id` is `None`) - what
    #: lets a client point at the permanent asking, and tell two copies of one
    #: card apart, which the source name alone cannot.
    source_id: str | None
    #: The source's printed name.
    source_name: str
    #: The triggered ability's own printed text (CR 603.1), not the source's
    #: whole `oracle_text` - empty when the ability has none to give.
    text: str
    #: Who controls this ability (CR 603.3a) - the block `ask_trigger_order`
    #: is ordering is always one controller's, but a client reading a paused
    #: question benefits from not having to look it up elsewhere.
    controller: str


@dataclass(frozen=True)
class Decision:
    """One question, its asker, and every legal answer to it (CR 608.2d).

    Built by `Game`, answered by `Game.ask`. The options are computed by the
    caller because legality is a question about the game state - whether the
    life can be paid (CR 119.4), whether there are cards to look at - and this
    module is deliberately stateless.
    """

    kind: DecisionKind
    #: Whose choice it is. CR 608.2d says "the player", which is the controller
    #: of the resolving spell or ability unless the effect names somebody else.
    player: str
    #: What is being asked, in words, so a failure reads as a sentence.
    prompt: str
    #: The card whose text is asking, by name. `None` for a question the rules
    #: ask rather than a card - the mulligan declaration (CR 103.5) is the one.
    source: str | None = None
    #: The game object asking, by id: the `CardState`/`TokenState` whose spell,
    #: ability, trigger, replacement effect or cost produced this question -
    #: for an ability on the stack, the card behind it (`AbilityOnStack.
    #: source_id`). A name cannot tell two Steam Vents apart; this can, which
    #: is what lets a client point at the card asking. `None` when no object
    #: asks - a turn-based action (the combat declarations, CR 508.1/509.1;
    #: the cleanup discard, CR 514.1), a state-based action (the legend rule,
    #: CR 704.5j), the pregame (CR 103.5), or CR 603.3b's ordering, which is
    #: about several abilities at once and so has no single asker - though
    #: each `abilities` entry below names its own. A string so it serializes
    #: as itself; build it with `source_id_of`. Like `card`, not part of
    #: `ScriptedAnswer.matches`.
    source_id: str | None = None
    #: The specific card this question is about, when a name is not enough to
    #: identify it. Set for CR 103.6's opening-hand actions, where a hand can
    #: hold two copies of the card offering the action and the answer has to say
    #: which one; `None` everywhere else. Not part of `Answer.matches`, so a
    #: script keyed to a kind, a player and a card name goes on matching.
    card: UUID | None = None
    #: How much: the life to pay, the N of scry N / surveil N, or how many of
    #: `cards` a `CHOOSE_CARDS` answer must contain.
    amount: int = 0
    #: The cards being looked at, for `SCRY` and `SURVEIL`, top first; the
    #: candidate cards a `CHOOSE_CARDS` answer must be a subset of.
    cards: tuple[UUID, ...] = ()
    #: The candidate players a `CHOOSE_PLAYERS` answer must be a subset of -
    #: `cards`' own twin, keyed by username rather than card id, since a
    #: player has no `UUID` of their own to be named by.
    players: tuple[str, ...] = ()
    #: A human-readable label per `cards` entry, positionally aligned, for the
    #: kinds whose ids name something no card lookup can resolve.
    #:
    #: `ORDER_TRIGGERS` is the case that needs it: `cards` there holds
    #: `AbilityOnStack` ids, and CR 113.1c / CR 405.1 make an ability on the
    #: stack an object with no card, so nothing that resolves ids against the
    #: board can name them. Worse, CR 603.3b is asked one step *before*
    #: CR 603.3's "its controller puts it on the stack", so at the moment the
    #: question is published those abilities are in no zone at all - not the
    #: stack, not `pending_triggers` - and a caller reading the game cannot
    #: find them however hard it looks. The asker is the only thing that still
    #: holds them, so the label has to travel with the question - one way of
    #: naming this kind's `cards`; `abilities` below is the other.
    #:
    #: Empty for every other kind, whose `cards` are real cards a lookup can
    #: name.
    card_labels: tuple[str, ...] = ()
    #: `ORDER_TRIGGERS` only - set only for that kind, empty everywhere else.
    #: The structured form of `card_labels` above: one `PendingAbility` per
    #: `cards` entry, positionally aligned, that also carries the source's own
    #: object id, so a client can point at the permanent asking rather than
    #: only naming it - `card_labels`' prose cannot say which Chalice of the
    #: Void is which; this can.
    abilities: tuple[PendingAbility, ...] = ()
    #: Where the cards the player picks (`CardSplit.moved`) end up, and where
    #: the ones they do not pick end up, in short lowercase prose: "bottom of
    #: your library", "your graveyard", "top of your library", "exiled".
    #:
    #: `SCRY` and `SURVEIL` are asked with one fixed pair of destinations each
    #: (CR 701.22a: bottom / top; CR 701.25a: graveyard / top), but
    #: `Game.look_at_top_and_split` asks the *same* question for cards whose
    #: pair is neither - Devourer of Destiny keeps one on top and exiles the
    #: rest - so the kind alone does not say where anything goes. Without
    #: these, every client has to guess the scry pair, and for Devourer that
    #: guess is wrong on both halves: it tells the player the card they tick
    #: goes to the bottom when it is the one card that stays on top, and never
    #: mentions exile at all.
    #:
    #: Note which way round they are. `moved` is *the pile the player opts
    #: into*, not "the pile that leaves the top": scry's opt-in is bottoming a
    #: card, Devourer's opt-in is putting one back on top. That is what makes
    #: an empty answer the right decline in both cases. So do not read
    #: `moved_label` as "where the cards go that leave the library" - read the
    #: label, which is why it travels with the question.
    moved_label: str = ""
    kept_label: str = ""
    #: Whether the affirmative branch is legal at all (CR 608.2d, CR 119.4).
    #: `False` removes it from `legal_options`, which is how paying 2 life at
    #: 1 life stops being an option rather than becoming a rules violation.
    affirmative_is_legal: bool = True
    #: `MAY` only: overrides `default_answer`'s engine-wide "take it" for this
    #: one question. `None` (every caller but two) leaves that convention in
    #: force. The second is miracle's reveal (CR 702.94a, `Game._offer_
    #: miracle_reveal`): revealing a card from a hand gives away hidden
    #: information (CR 402.3), so an unscripted player keeps it hidden.
    #: `Game.may`'s own "you may shuffle" clause is the first - the
    #: shuffle ends whatever look or order the cards above it just fixed (CR
    #: 701.20d: reordering the library un-reveals it), so an unscripted answer
    #: there defaults to declining, the same "leave the look's order alone"
    #: posture `SCRY`/`SURVEIL`'s own defaults already take, rather than to
    #: taking the option the way an unscripted sacrifice or discard does. A
    #: documented deviation on the one question that asks it, not a silent
    #: special case - see `Game.may`'s own docstring.
    default_may: bool | None = None
    #: The legal targets a `CHOOSE_TARGETS` answer must be a subset of, worked
    #: out by `machines/targeting.py`'s own checker so this module does not
    #: grow a second target grammar.
    targets: tuple[TargetRef, ...] = ()
    #: The most targets a `CHOOSE_TARGETS` answer may contain (CR 115.6's "up
    #: to N"), or `None` for "any number of" (CR 107.1c).
    target_maximum: int | None = None
    #: The fewest targets a `CHOOSE_TARGETS` answer may contain and still be
    #: legal, capped at `len(targets)` by every caller that builds one - CR
    #: 601.2c's "the player announces their choice ... for each target the
    #: spell requires" is not optional once a legal target exists. 0 for a
    #: "you may"-shaped requirement (CR 115.6's "up to N", CR 107.1c's "any
    #: number of") or for an ability with no targeting requirement at all.
    target_minimum: int = 0
    #: The legal answers to a `CHOOSE_A_QUALITY` question, or empty for "any
    #: string" (a card name - too large a set to enumerate). Populated with the
    #: five colors' letter codes for a color choice, and with CR 205.3m's
    #: creature types (`data/creature_types.py`) for a creature type choice.
    options: tuple[str, ...] = ()
    #: `CHOOSE_A_QUALITY` only: which quality is being chosen, as a
    #: `ChoiceKind` value ("color", "card_name", "creature_type"), or "" when
    #: the asker is not an "as [this] enters, choose" effect (a mana color
    #: narrowed by `options` alone). `Game.ask` reads it to say why an answer
    #: outside `options` is refused - "is not a creature type (CR 205.3m)" -
    #: instead of listing every legal answer.
    quality: str = ""
    #: `CHOOSE_CARDS` only: `True` (the default, every existing question) means
    #: `amount` is exact - the cleanup discard, which always names precisely
    #: how many. `False` means CR 107.1c's "any number" - Valakut Awakening's
    #: "put any number of cards from your hand" - so `amount` is a ceiling
    #: (every card offered) and any count from zero up to it, inclusive, is a
    #: legal answer.
    exact: bool = True
    #: `CHOOSE_CARDS` only: what an unscripted, unprovided player chooses, in
    #: place of the kind's own documented default ("the back of `cards`", or
    #: nothing at all when `exact` is `False`). `None` - every question that
    #: existed before searching became one choice - keeps that default.
    #:
    #: `Game.search_library` is the caller that needs it. CR 701.23b makes a
    #: stated-quality search of a hidden zone declinable, so the question is
    #: `exact=False` and the generic "any number" default would be to find
    #: *nothing* - which is a real answer a player may give, but a ridiculous
    #: one to give on their behalf: an unscripted fetchland would pay the life,
    #: sacrifice itself, and find no land. The searcher's default is instead
    #: "find, taking the candidates in zone order", which is exactly what this
    #: engine did when a search was a walk of yes/no questions whose own `MAY`
    #: default was yes. A default is a documented deviation, not a decision
    #: (see the module docstring), and this field is where a caller writes the
    #: deviation down rather than hiding it in a reversed candidate list.
    default_cards: tuple[UUID, ...] | None = None
    #: `PAY_MANA` only: the untapped permanents whose mana abilities the payer
    #: may activate while paying (CR 608.2g, CR 605.3a). An answer naming
    #: sources must name a subset of these.
    mana_sources: tuple[UUID, ...] = ()
    #: `ASSIGN_COMBAT_DAMAGE` only: the damage each of `targets` still needs
    #: before it counts as assigned lethal damage (CR 702.19b, CR 702.2c),
    #: aligned with `targets`; 0 for the player or planeswalker being attacked.
    lethal_damage: tuple[int, ...] = ()
    #: `ASSIGN_COMBAT_DAMAGE` only: what an unscripted, unpaused seat assigns -
    #: lethal damage to each blocker in declaration order, the rest through
    #: with trample or onto the last blocker without it.
    default_damage: tuple[tuple[TargetRef, int], ...] | None = None
    #: `ASSIGN_COMBAT_DAMAGE` only: whether the attacker has trample, so damage
    #: may go past its blockers once each has lethal damage (CR 702.19b).
    trample: bool = False


def source_id_of(obj: "CardState | AbilityOnStack | UUID | None") -> str | None:
    """The `Decision.source_id` naming `obj` as the object asking.

    A `CardState` (a `TokenState` included) is its own id. An `AbilityOnStack`
    is an object of its own (CR 113.1c) but not a card, so it names the card
    behind it, or nothing when it has none. A bare id is taken as given;
    `None` stays `None`.
    """
    if obj is None:
        return None
    if isinstance(obj, UUID):
        return str(obj)
    if obj.state_class == "AbilityOnStack":
        return None if obj.source_id is None else str(obj.source_id)
    return str(obj.id)


def legal_options(decision: Decision) -> tuple[bool, ...]:
    """The yes/no options a player may actually choose (CR 608.2d).

    Only the boolean questions have an enumerable option set; a scry's answer is
    a subset of the cards and every subset is legal, so `SCRY` and `SURVEIL`
    return both booleans and are validated by `Game` instead.
    """
    if decision.kind in (
        DecisionKind.MAY,
        DecisionKind.PAY_LIFE,
        DecisionKind.PAY_ENERGY,
        DecisionKind.PAY_MANA,
    ):
        return (True, False) if decision.affirmative_is_legal else (False,)
    return (True, False)


def default_answer(decision: Decision) -> object:
    """What happens when nobody has said what they want. See the module docstring.

    Never returns an illegal option: the affirmative is taken only when
    `affirmative_is_legal` says CR 608.2d allows it.
    """
    if decision.kind in (DecisionKind.MULLIGAN, DecisionKind.OPENING_HAND_ACTION):
        # CR 103.5's mulligan and CR 103.6's opening-hand actions are both
        # "may", and both are decisions a scenario states rather than ones an
        # engine should take on a player's behalf: an unscripted player keeps
        # the hand they were dealt and takes no opening-hand action.
        return False
    if decision.kind is DecisionKind.MAY and decision.default_may is not None:
        # A caller wrote its own deviation down rather than taking the
        # engine-wide one below - see `Decision.default_may`.
        return decision.default_may
    if decision.kind in (
        DecisionKind.MAY,
        DecisionKind.PAY_LIFE,
        DecisionKind.PAY_ENERGY,
        DecisionKind.PAY_MANA,
    ):
        return decision.affirmative_is_legal
    if decision.kind in (DecisionKind.PAY_ENERGY_AMOUNT, DecisionKind.PAY_LIFE_AMOUNT):
        # Paying nothing is always legal (CR 118.3's energy floor, CR 119.4b's
        # life floor never forbid it), and is the least-committal answer - the
        # same "leave it as it was" convention `SCRY`/`SURVEIL`'s "keep
        # everything on top" default follows, not a claim that 0 is somehow
        # the right amount for an unscripted player to pay.
        return 0
    if decision.kind is DecisionKind.PUT_ON_TOP_OR_BOTTOM:
        return True
    if decision.kind is DecisionKind.CHOOSE_PILE:
        # Neither pile is more "destructive" than the other here - both name
        # the same consequence (sacrifice, destroy) - so this is an arbitrary
        # but consistent choice, the same way `PUT_ON_TOP_OR_BOTTOM`'s own
        # default is a documented pick rather than a claim that pile one is
        # somehow correct for an unscripted player.
        return True
    if decision.kind is DecisionKind.ORDER_TRIGGERS:
        # CR 603.3b's "in any order they choose" with nobody choosing: the
        # order they triggered in, which is exactly what `apnap_order` gave
        # this engine before the question existed. A permutation is always
        # legal, so there is no `affirmative_is_legal` branch here.
        return decision.cards
    if decision.kind is DecisionKind.DREDGE:
        # CR 702.52a's "you may instead" with nobody choosing: draw normally.
        # An unscripted player does not silently reshape their graveyard and
        # hand in place of the draw the caller actually asked for - the same
        # "leave the more ordinary outcome alone" posture `SCRY`/`SURVEIL`'s
        # own "keep everything on top" default already takes.
        return ()
    if decision.kind is DecisionKind.ASSIGN_COMBAT_DAMAGE:
        # CR 510.1c's division with nobody choosing: the asker's own
        # documented split, which is what combat did before it asked.
        return decision.default_damage or ()
    if decision.kind in (DecisionKind.DECLARE_ATTACKERS, DecisionKind.DECLARE_BLOCKERS):
        # CR 508.1 says "if any" and CR 509.1 says "may": declaring nobody is
        # always legal, and is what an unscripted player does.
        return ()
    if decision.kind is DecisionKind.CHOOSE_CARDS:
        if decision.default_cards is not None:
            # The asker wrote down what an unscripted player takes - see
            # `Decision.default_cards`. Like every other branch here it is the
            # asker's job to keep it legal (a subset of `cards`, within
            # `amount`): `Game.ask` returns a default without re-validating it,
            # because a default that could be illegal would be a bug in the
            # question, not an answer to refuse.
            return decision.default_cards
        if not decision.exact:
            # CR 107.1c's "any number": the least-destructive, most-reversible
            # answer is none at all - the same posture `SCRY`/`SURVEIL`'s own
            # "keep everything on top" default already takes - not `amount`
            # cards, which for Valakut Awakening's "any number of cards from
            # your hand" would otherwise default an unscripted player to
            # emptying their whole hand.
            return ()
        # The back of `cards`, in the order the caller offered them. The
        # cleanup discard offers the hand in hand order, so this is exactly
        # "discard from the back of the hand" - the behaviour this kind
        # replaced, preserved as the unscripted, unprovided fallback.
        if decision.amount <= 0:
            return ()
        return decision.cards[len(decision.cards) - decision.amount :]
    if decision.kind is DecisionKind.CHOOSE_PLAYERS:
        # `CHOOSE_CARDS`' own default, over `players` instead of `cards`:
        # every printed proliferate in the pool is CR 107.1c's "any number",
        # so the least-destructive unscripted answer is choosing nobody.
        if not decision.exact:
            return ()
        if decision.amount <= 0:
            return ()
        return decision.players[len(decision.players) - decision.amount :]
    if decision.kind is DecisionKind.CHOOSE_TARGETS:
        # CR 601.2c: "the player announces their choice ... for each target
        # the spell requires" - a mandatory requirement (`target_minimum` > 0)
        # is not a "decline" question, so an unscripted player still has to
        # name enough legal targets when there are any; the first ones
        # offered, not a judgement about which target is best. `target_minimum`
        # is capped at `len(decision.targets)` by every caller, so this never
        # asks for more than are actually legal.
        #
        # `target_minimum` is 0 for a genuinely optional "up to N"/"any number
        # of" requirement (CR 115.6, CR 107.1c) - Karn, the Great Creator's own
        # case - so this still returns empty there, exactly as it always did.
        if decision.target_minimum > 0:
            return decision.targets[: decision.target_minimum]
        return ()
    if decision.kind is DecisionKind.CHOOSE_A_QUALITY:
        # CR 614.12a's choice is mandatory - there is no "decline" branch the
        # way `MAY` has one - so an unscripted answer still has to name
        # something. The first offered option for a color or creature type
        # choice; an empty string for a card name, which offers none: there is
        # no rule-backed "first card name" to reach for.
        return decision.options[0] if decision.options else ""
    if decision.kind is DecisionKind.CHOOSE_A_MODE:
        # CR 700.2a's choice is mandatory too, same reasoning as
        # CHOOSE_A_QUALITY just above: the first printed mode, not a
        # judgement about which mode is best.
        return decision.options[0] if decision.options else ""
    if decision.exact and decision.amount > 0:
        # A split the printed text makes mandatory - Waker of Waves' "put one
        # of them into your hand" - has no empty answer to fall back on, so
        # the first `amount` cards looked at are moved: a legal answer, not a
        # judgement about which card is best.
        return CardSplit(moved=decision.cards[: decision.amount])
    return CardSplit()


def rule_for_kind(kind: DecisionKind) -> str:
    """The CR citation that actually governs asking a decision of `kind`.

    Ported from the API's own `rule_for_kind` (previously
    `magic_cards_model_api.decisions.rule_for_kind`), which verified each of
    its citations with `knowledge_search(q="...", type="rules")` before
    writing them - but not verbatim: this version grows two branches the API's
    does not have, `DECLARE_ATTACKERS` and `DECLARE_BLOCKERS`, because the API
    version never had to cite them (see `ANSWERABLE_KINDS`'s own docstring in
    `magic_cards_model_api.decisions`, which explains why those two kinds
    never reach that module at all). Those two citations - CR 703.4i, CR
    508.1, CR 703.4j, CR 509.1 - were looked up fresh with
    `knowledge_search(q="...", type="rules")` in the session that added them
    here and read whole with `mise run rules:find`; every other branch below
    is the API's own, carried over rather than re-derived.

    Every `DecisionKind` this module ever asks through `Game.ask` is answered
    "while applying the effect" of a spell or ability already on the stack,
    which is CR 608.2d - except `CHOOSE_TARGETS`, which is choosing targets
    *while putting* the spell or ability on the stack in the first place, the
    exact case CR 608.2d's own wording excludes ("choices other than choices
    already made as part of casting the spell, activating the ability, or
    otherwise putting the spell or ability on the stack"). That step is CR
    603.3d for a triggered ability, which folds in CR 601.2c ("the player
    announces their choice of an appropriate object or player for each
    target") for the spell-casting case 603.3d itself delegates to.

    `MULLIGAN` and `OPENING_HAND_ACTION` are asked before the first turn, not
    while any effect resolves; `ORDER_TRIGGERS` is asked while a batch of
    simultaneous triggers goes on the stack, one step before any of them
    resolves; `DECLARE_ATTACKERS`/`DECLARE_BLOCKERS` are each a turn-based
    action's own declaration (CR 508.1, CR 509.1), not a resolving effect's
    choice either. Used by `PendingDecision.rule` so a paused decision carries
    its own citation.
    """
    if kind is DecisionKind.CHOOSE_TARGETS:
        return "CR 603.3d, CR 601.2c (targets chosen while going on the stack)"
    if kind is DecisionKind.MULLIGAN:
        # Also before the first turn, and one step earlier than CR 103.6:
        # the declaration each player makes in the mulligan process itself.
        return "CR 103.5 (the mulligan declaration, before the first turn)"
    if kind is DecisionKind.OPENING_HAND_ACTION:
        # No effect is applying and no spell is going on the stack: this is
        # CR 103.6's own start-of-game sequence, "once the mulligan process
        # (see rule 103.5) is complete, the starting player may take any such
        # actions in any order", before the first turn begins.
        return "CR 103.6 (an action taken from the opening hand, before the first turn)"
    if kind is DecisionKind.ORDER_TRIGGERS:
        # No effect is applying here either: this is the two-part process that
        # *puts* a batch of simultaneous triggers on the stack, one step
        # before any of them resolves. CR 603.3b, the same family of exception
        # `CHOOSE_TARGETS` is - a choice made while going on the stack, which
        # CR 608.2d's own wording excludes.
        return "CR 603.3b (the order simultaneous triggers go on the stack)"
    if kind is DecisionKind.DECLARE_ATTACKERS:
        return "CR 703.4i, CR 508.1 (declaring attackers, a turn-based action)"
    if kind is DecisionKind.DECLARE_BLOCKERS:
        return "CR 703.4j, CR 509.1 (declaring blockers, a turn-based action)"
    if kind is DecisionKind.PAY_MANA:
        return (
            "CR 608.2d, CR 608.2g (a choice made while the effect applies; the player "
            "may activate mana abilities before paying)"
        )
    if kind is DecisionKind.ASSIGN_COMBAT_DAMAGE:
        return "CR 703.4k, CR 510.1c, CR 702.19b (assigning combat damage, a turn-based action)"
    if kind is DecisionKind.DREDGE:
        # Not CR 608.2d either: dredge is a static/replacement ability
        # (CR 702.52a) offered as the draw itself is about to happen, and
        # CR 616.1e is what governs choosing among the applicable optional
        # replacement effects it competes with.
        return "CR 702.52a, CR 616.1 (replacing a draw with dredge, an optional replacement effect)"
    return "CR 608.2d (a choice made while the effect applies)"


#: Which single `Answer` field carries a `kind`'s value - the one place that
#: mapping is written down, so `Answer`'s own validator and `to_engine` cannot
#: drift apart from each other the way two hand-written `if` chains could.
_ANSWER_FIELD_FOR_KIND: dict[DecisionKind, str] = {
    DecisionKind.MAY: "accept",
    DecisionKind.PAY_LIFE: "accept",
    DecisionKind.PAY_ENERGY: "accept",
    DecisionKind.PAY_MANA: "accept",
    DecisionKind.MULLIGAN: "accept",
    DecisionKind.OPENING_HAND_ACTION: "accept",
    DecisionKind.PUT_ON_TOP_OR_BOTTOM: "accept",
    DecisionKind.CHOOSE_PILE: "accept",
    DecisionKind.PAY_ENERGY_AMOUNT: "amount",
    DecisionKind.PAY_LIFE_AMOUNT: "amount",
    DecisionKind.CHOOSE_CARDS: "card_ids",
    DecisionKind.CHOOSE_PLAYERS: "usernames",
    DecisionKind.ORDER_TRIGGERS: "card_ids",
    DecisionKind.DREDGE: "card_ids",
    DecisionKind.SCRY: "split",
    DecisionKind.SURVEIL: "split",
    DecisionKind.CHOOSE_TARGETS: "targets",
    DecisionKind.CHOOSE_A_QUALITY: "text",
    DecisionKind.CHOOSE_A_MODE: "text",
    DecisionKind.DECLARE_ATTACKERS: "pairs",
    DecisionKind.DECLARE_BLOCKERS: "pairs",
    DecisionKind.ASSIGN_COMBAT_DAMAGE: "damage",
}
assert set(_ANSWER_FIELD_FOR_KIND) == set(DecisionKind), (
    "every DecisionKind needs exactly one Answer field - see _ANSWER_FIELD_FOR_KIND"
)

#: Every value field `Answer` can carry - exactly one is set, matching
#: `decision.kind` (see `_ANSWER_FIELD_FOR_KIND`); the rest stay `None`.
_ANSWER_VALUE_FIELDS = frozenset(_ANSWER_FIELD_FOR_KIND.values())


class DeclaredPair(EngineModel):
    """One `(creature, defender)` pair in a recorded `DECLARE_ATTACKERS` or
    `DECLARE_BLOCKERS` answer (CR 508.1, CR 509.1).

    Not a bare `(UUID, UUID)` tuple: a blocker's target is always a card (CR
    509.1a - "one creature for it to block"), but an attacker's is
    overwhelmingly a player (CR 508.1b's "opponents or planeswalkers"), and a
    `Player` has no id of its own, only a username - a pair of ids cannot name
    that at all, which is the whole reason attacking a player used to be
    unreplayable through the tape. Exactly one of `defender_card`/
    `defender_player` is set, the same "name what you mean" shape
    `machines/decisions.py`'s `_ANSWER_FIELD_FOR_KIND` already uses for
    `Answer` itself - never both, never neither.

    A frozen pydantic model for the same reason `Answer` is one and not a
    dataclass: it has to survive `Game.model_dump(mode="json")` round-tripping
    a paused game.
    """

    model_config = ConfigDict(frozen=True)

    #: The attacking or blocking creature, by id.
    creature: UUID
    #: The defender, when it is a card - a planeswalker or battle attacked
    #: (CR 508.1b), or the attacker a blocker is assigned to (CR 509.1a).
    defender_card: UUID | None = None
    #: The defender, when it is a player - by far the common case for an
    #: attack, and the case a bare id pair could never express.
    defender_player: str | None = None

    @model_validator(mode="after")
    def _exactly_one_defender(self) -> "DeclaredPair":
        if (self.defender_card is None) == (self.defender_player is None):
            raise ValueError(
                "a DeclaredPair needs exactly one of defender_card/defender_player set"
            )
        return self


class DamageAssignment(EngineModel):
    """One `(recipient, amount)` entry of a recorded `ASSIGN_COMBAT_DAMAGE`
    answer (CR 510.1c, CR 702.19b).

    Exactly one of `target_card`/`target_player` is set, for the same reason
    `DeclaredPair` names a player by username: a player has no id.
    """

    model_config = ConfigDict(frozen=True)

    target_card: UUID | None = None
    target_player: str | None = None
    amount: int

    @model_validator(mode="after")
    def _one_recipient(self) -> "DamageAssignment":
        if (self.target_card is None) == (self.target_player is None):
            raise ValueError("a damage assignment names exactly one card or one player")
        return self

    @property
    def target(self) -> TargetRef:
        if self.target_card is not None:
            return TargetRef.to_card(self.target_card)
        return TargetRef.to_player(self.target_player)


def damage_assignment_answer(
    decision: Decision, value: object
) -> tuple[tuple[TargetRef, int], ...]:
    """Check one `ASSIGN_COMBAT_DAMAGE` answer and return it canonical.

    CR 510.1e: the assignment is checked as a whole, and an illegal one is
    refused. The checks, each the rule that makes the answer illegal:

    - CR 510.1a: the amounts add up to the creature's power, none negative.
    - CR 510.1c: a recipient is one of the creatures blocking it; the player or
      planeswalker it attacks only with trample.
    - CR 702.19b: damage to that player or planeswalker only once every blocker
      is assigned lethal damage (`Decision.lethal_damage`, which already counts
      marked damage, deathtouch and damage other attackers assign this step).
    """
    if not isinstance(value, (tuple, list)):
        raise ValueError(f"{decision.prompt}: needs (target, amount) pairs")
    offered = {ref: index for index, ref in enumerate(decision.targets)}
    blocker_ids = set(decision.cards[1:])
    chosen: dict[TargetRef, int] = {}
    for entry in value:
        if isinstance(entry, DamageAssignment):
            target, amount = entry.target, entry.amount
        elif isinstance(entry, (tuple, list)) and len(entry) == 2:
            target, amount = TargetRef.coerce(entry[0]), entry[1]
        else:
            raise ValueError(f"{decision.prompt}: each entry is a (target, amount) pair")
        if not isinstance(amount, int) or isinstance(amount, bool) or amount < 0:
            raise ValueError(
                f"{decision.prompt}: {amount!r} is not an amount of damage (CR 510.1a)"
            )
        if target not in offered:
            if target.is_player or target.card_id not in blocker_ids:
                raise ValueError(
                    f"{decision.prompt}: {target} is not a creature blocking it, and only "
                    f"trample lets damage go past its blockers (CR 510.1c, CR 702.19b)"
                )
            raise ValueError(f"{decision.prompt}: {target} was not offered (CR 510.1c)")
        if target in chosen:
            raise ValueError(f"{decision.prompt}: {target} is named twice")
        chosen[target] = amount
    total = sum(chosen.values())
    if total != decision.amount:
        raise ValueError(
            f"{decision.prompt}: {total} damage assigned, but the creature assigns "
            f"exactly its power, {decision.amount} (CR 510.1a)"
        )
    past_blockers = [
        ref for ref, amount in chosen.items() if amount and ref.card_id not in blocker_ids
    ]
    if past_blockers:
        short = [
            ref
            for ref, index in offered.items()
            if ref.card_id in blocker_ids and chosen.get(ref, 0) < decision.lethal_damage[index]
        ]
        if short:
            raise ValueError(
                f"{decision.prompt}: damage can reach {past_blockers[0]} only once every "
                f"blocker is assigned lethal damage, and {short[0]} is not (CR 702.19b)"
            )
    canonical = {ref: ref for ref in decision.targets}
    return tuple((canonical[ref], amount) for ref, amount in chosen.items() if amount)


class Answer(EngineModel):
    """One recorded answer to one `Decision` - the tape `DecisionScript.recorded`
    is made of, and what `Game.ask`/`ask_mulligan`/`ask_trigger_order`/
    `_ask_declaration` read from it (see the module docstring's "Pausing
    instead of blocking" section).

    A frozen pydantic model, not the plain dataclass `Decision`/`CardSplit`
    already in this module are: the tape has to survive `Game.model_dump
    (mode="json")` round-tripping a paused game, the same reason commit
    739ee2b turned `machines/layers.py`'s continuous-effect closures into
    frozen pydantic models instead of plain dataclasses.

    Carries exactly one typed value field per `DecisionKind` - never a bare
    `object`, so a corrupt or hand-edited tape entry fails to construct rather
    than reaching `to_engine` and failing later, more confusingly, deep inside
    whichever asker read it. `_ANSWER_FIELD_FOR_KIND` is the single mapping
    that says which field a given `kind` uses; `_check_one_value_field` below
    is what enforces it.
    """

    model_config = ConfigDict(frozen=True)

    #: This answer's position in the sequence of decisions asked so far -
    #: `PendingDecision.seq` when it was first asked (or a test/caller's own
    #: count, when nothing was ever paused). Not consulted by `take_from_tape`
    #: to pick which entry to read - the tape is read positionally, oldest
    #: first - it is audit metadata: evidence of which question this was
    #: supposed to answer, for a log or an assertion to check against.
    seq: int
    kind: DecisionKind
    #: Whose answer this is - checked against `Decision.player` by
    #: `DecisionScript.take_from_tape` before the value is used at all.
    player: str
    #: Free-text explanation a live seat may have given alongside its answer
    #: (an AI seat's chain of reasoning, say). Never read by `to_engine` or by
    #: any rule this engine enforces - CR 608.2d cares what a player chooses,
    #: never why - so this is pure audit trail, carried on the tape the same
    #: way it would be carried in a decision log.
    reasoning: str | None = None

    #: `MAY`, `PAY_LIFE`, `PAY_ENERGY`, `PAY_MANA`, `MULLIGAN`,
    #: `OPENING_HAND_ACTION`, `PUT_ON_TOP_OR_BOTTOM`, `CHOOSE_PILE` - every
    #: yes/no question this module asks, including the two that are not
    #: `Game.ask` questions at all (`MULLIGAN`, CR 103.5) and the two whose
    #: two options are not literally yes/no but are still a plain boolean
    #: (`PUT_ON_TOP_OR_BOTTOM`, `True` for the top; `CHOOSE_PILE`, `True` for
    #: pile one).
    accept: bool | None = None
    #: `PAY_ENERGY_AMOUNT`, `PAY_LIFE_AMOUNT` - how much was paid, 0 or more.
    amount: int | None = None
    #: `CHOOSE_CARDS` - which candidates were chosen; `ORDER_TRIGGERS` - the
    #: chosen order's `AbilityOnStack` ids; `PAY_MANA` (beside `accept=True`
    #: only) - the offered mana sources to activate while paying (CR 608.2g).
    #: For the first two: the
    #: chosen order's `AbilityOnStack` ids, bottom of the stack first (CR
    #: 603.3b). Both are "a tuple of ids naming some of `Decision.cards`",
    #: which is why they share a field rather than each growing its own.
    card_ids: tuple[UUID, ...] | None = None
    #: `CHOOSE_PLAYERS` - which candidate players were chosen (CR 701.34a's
    #: own "and/or players" half). `card_ids`' own twin: a player has no
    #: `UUID`, only a username, so this cannot share that field's type.
    usernames: tuple[str, ...] | None = None
    #: `SCRY`, `SURVEIL` - CR 701.22a's and CR 701.25a's split of the cards
    #: looked at.
    split: CardSplit | None = None
    #: `CHOOSE_TARGETS` - the chosen targets (CR 601.2c, CR 603.3d).
    targets: tuple[TargetRef, ...] | None = None
    #: `CHOOSE_A_QUALITY`, `CHOOSE_A_MODE` - the chosen color/name/type or
    #: printed mode text.
    text: str | None = None
    #: `DECLARE_ATTACKERS`, `DECLARE_BLOCKERS` - `DeclaredPair`s, in
    #: declaration order. A blocker always blocks a creature (CR 509.1a), so
    #: every `DECLARE_BLOCKERS` pair sets `defender_card`; an attacker's
    #: target is overwhelmingly a player (CR 508.1b's "opponents or
    #: planeswalkers" - a player has no id of its own, only a username, which
    #: is what `defender_player` carries), but can also be a planeswalker or a
    #: battle, which is `defender_card`. `Game._resolve_declaration` resolves
    #: each id or username against the game as it stands when the tape is
    #: replayed.
    pairs: tuple["DeclaredPair", ...] | None = None
    #: `ASSIGN_COMBAT_DAMAGE` - `DamageAssignment`s, one per recipient
    #: (CR 510.1c, CR 702.19b).
    damage: tuple[DamageAssignment, ...] | None = None

    @model_validator(mode="after")
    def _check_one_value_field(self) -> "Answer":
        wanted = _ANSWER_FIELD_FOR_KIND[self.kind]
        value = getattr(self, wanted)
        if value is None:
            raise ValueError(
                f"{with_indefinite_article(self.kind.value)} answer needs its {wanted!r} field set"
            )
        if self.kind in (DecisionKind.CHOOSE_A_QUALITY, DecisionKind.CHOOSE_A_MODE) and value == "":
            # CR 614.12a's and CR 700.2a's choices are both mandatory - there
            # is no "decline" branch - so an empty string is never a real
            # answer, only ever a missing one. `Game.ask` refuses it too (see
            # its own `not value` check), so this is an early refusal, not the
            # only one; the api's `quality_answer`/`mode_answer` refuse the
            # same way for the same reason.
            raise ValueError(
                f"{with_indefinite_article(self.kind.value)} answer needs a non-empty {wanted!r}"
            )
        allowed_extra = {"card_ids"} if self.kind is DecisionKind.PAY_MANA else set()
        if self.kind is DecisionKind.PAY_MANA and self.card_ids is not None and not self.accept:
            raise ValueError("a pay_mana answer names mana sources only when it pays")
        stray = [
            field_name
            for field_name in _ANSWER_VALUE_FIELDS
            if field_name != wanted
            and field_name not in allowed_extra
            and getattr(self, field_name) is not None
        ]
        if stray:
            raise ValueError(
                f"{with_indefinite_article(self.kind.value)} answer only uses {wanted!r}, "
                f"not {', '.join(stray)}"
            )
        return self

    def to_engine(self) -> object:
        """This answer's value, in the shape `Game.ask` (or `ask_mulligan`/
        `ask_trigger_order`/`_ask_declaration`) expects back from a
        consultant - the single kind-to-value mapping every one of the API's
        old per-kind `*_answer` coercions (`bool_answer`, `card_ids_answer`,
        ...) used to do by hand, one `DecisionKind` at a time.

        `_check_one_value_field` already guarantees the right field is set, so
        this is a lookup, not a re-validation.
        """
        if self.kind is DecisionKind.PAY_MANA and self.card_ids is not None:
            return self.card_ids
        return getattr(self, _ANSWER_FIELD_FOR_KIND[self.kind])


@dataclass(frozen=True)
class PendingDecision:
    """A `Decision` nothing could answer, snapshotted for a caller to store and
    answer later (see the module docstring's "Pausing instead of blocking").

    Not itself the pause state - the "committed state, command, answers so
    far" tuple a caller persists is built from this plus the `Game` as it
    stood before the paused command ran, not from anything carried here. This
    is just the question, its place in the sequence, and the rule that governs
    it.
    """

    #: This decision's position among every decision asked in this run so far
    #: - `len(DecisionScript.asked) - 1` at the moment it was raised. Matches
    #: `Answer.seq` once a caller answers it and appends the answer to the
    #: tape, though nothing here enforces that pairing - see `Answer.seq`.
    #:
    #: "This run" means what `DecisionScript.begin_replay` scopes it to mean:
    #: `asked` is a field on the `Game` this decision was raised from, and
    #: nothing resets it on its own, so this is the semantics fixed here
    #: rather than the wording - a caller that resumes a paused command
    #: *must* call `begin_replay` before re-running it, precisely so `asked`
    #: restarts at empty and this numbering restarts at 0, matching the
    #: `Answer.seq` values it assigns from a previous `pending.seq`. Skip
    #: `begin_replay` and this docstring's claim goes back to being false, the
    #: same way it was found to be before `begin_replay` existed: `asked`
    #: would carry forward whatever a resumed `Game` already had, and this
    #: would count from wherever that left off, not from 0.
    seq: int
    #: The question itself, already run through `Game._with_card_labels` when
    #: raised from `Game.ask` (never from the other three askers, which have
    #: no card labels to add).
    decision: Decision
    #: `rule_for_kind(decision.kind)` - the CR citation that governs this
    #: question, computed once here so a caller does not have to re-derive it.
    rule: str


class DecisionPending(BaseException):
    """Raised when a decision has no scripted answer and no unconsumed tape
    entry, with `DecisionScript.pause_when_unanswered` set (see the module
    docstring).

    Deliberately a `BaseException`, not an `Exception`. `models/game.py`'s
    `Game.resolve_top` and `Game._resolve_ability`, and `machines/cost.py`'s
    `CostPayment.pay`, each wrap effect resolution in a bare `except
    Exception` (or `except ValueError`) that unwinds the in-progress
    resolution - sends the spell to the graveyard, discards the ability,
    unpays the cost - before re-raising. A `DecisionPending` that is meant to
    *pause* resolution, not fail it, must pass straight through every one of
    those handlers undisturbed; the only exception type that no `except
    Exception`/`except ValueError` anywhere in `machines/` can catch is one
    that is not an `Exception` at all. `BaseException` is the standard
    library's own escape hatch for exactly this (`SystemExit`,
    `KeyboardInterrupt`, `GeneratorExit` are its only other direct
    subclasses) - a signal meant to unwind past ordinary exception handling,
    which is precisely what a pause is.
    """

    def __init__(self, pending: PendingDecision) -> None:
        super().__init__(pending)
        #: The paused question, for a caller to catch this and store.
        self.pending = pending


@dataclass
class ScriptedAnswer:
    """One answer waiting for the question it belongs to.

    Matching is by kind, and optionally by player and by the name of the card
    asking. A `uses` of `None` means the answer keeps applying - "every scry
    this game bottoms everything" - while a number counts down and is spent.
    """

    kind: DecisionKind
    value: object
    player: str | None = None
    source: str | None = None
    uses: int | None = 1

    def matches(self, decision: Decision) -> bool:
        if self.kind is not decision.kind:
            return False
        if self.player is not None and self.player != decision.player:
            return False
        return not (self.source is not None and self.source != decision.source)

    @property
    def spent(self) -> bool:
        return self.uses is not None and self.uses <= 0


@dataclass
class DecisionScript:
    """The answers a caller has queued up, oldest first.

    Not a player agent and not a mock: it holds nothing but answers a real
    player could have given, and the engine performs the consequences itself.
    A rigged library and a scripted decision are the same kind of staging.
    """

    answers: list[ScriptedAnswer] = field(default_factory=list)
    #: Every question asked, in order, whether scripted or defaulted. A scenario
    #: can assert that a card asked at all - "scry 0 does not scry" (CR 701.22b)
    #: is only observable here.
    asked: list[Decision] = field(default_factory=list)
    #: The replay tape - every `Answer` a previous, paused attempt at this same
    #: command already received, oldest first. Consulted after a scripted
    #: answer, by `take_from_tape`; empty in every existing scenario test and
    #: every caller that has not paused, so nothing about this existing
    #: changes anybody's behaviour. See the module docstring's "Pausing
    #: instead of blocking" section.
    recorded: list[Answer] = field(default_factory=list)
    #: How many of `recorded`, from the front, this run has already read.
    #: `take_from_tape` reads `recorded[consumed]` and advances this by one
    #: each time it finds a match - positional, not a lookup by `Answer.seq`,
    #: because the tape is a queue of what happened last time, in order, not
    #: an index.
    consumed: int = 0
    #: Whether a question nothing else can answer raises `DecisionPending`
    #: (`True`) or falls through to `default_answer` (`False`, the default).
    #: `False` is what keeps every existing test's behaviour exactly as it
    #: was - only a caller that opts in by setting this can ever see a
    #: `DecisionPending` at all.
    pause_when_unanswered: bool = False

    def add(self, answer: ScriptedAnswer) -> ScriptedAnswer:
        self.answers.append(answer)
        return answer

    def extend(self, answers: Iterable[ScriptedAnswer]) -> None:
        self.answers.extend(answers)

    def take(self, decision: Decision) -> tuple[bool, object]:
        """The scripted answer for this question, if there is one.

        Returns `(found, value)` rather than `value | None`, because `False` and
        "bottom nothing" are both real answers that a `None` would swallow.
        """
        for answer in self.answers:
            if answer.spent or not answer.matches(decision):
                continue
            if answer.uses is not None:
                answer.uses -= 1
                if answer.spent:
                    self.answers.remove(answer)
            return True, answer.value
        return False, None

    def take_from_tape(self, decision: Decision) -> tuple[bool, object]:
        """The next recorded `Answer`, if the tape has one left.

        Read positionally - `recorded[consumed]` - not looked up by kind or
        player, because the tape is the exact sequence of answers a previous
        attempt at this same command already received, in the order it asked
        for them; the next entry is either this question's answer or the tape
        is corrupt.

        A kind or player mismatch **raises** rather than being skipped: a
        recorded answer replayed against a different question would still
        produce a game that runs to completion, just the wrong one, and a
        wrong game that looks right is worse than a crash (see `memory/
        silent-default-dispatch-tables.md`). Returning `(False, None)` here
        would let a caller mistake "the tape has nothing for this" for "the
        tape is broken", which are not the same fact.

        `answer.seq` is checked too, against `self.consumed` - not read to
        pick which entry to use (the tape is read positionally, not by seq),
        but as a second, independent check that this entry really is the one
        that was asked in this position: kind and player can both coincide by
        accident (two `MAY`s asked of the same player, one for each of two
        different cards), and a tape mis-bound that way would pass the checks
        above and still answer the wrong question - the worst failure mode
        this mechanism has, and the one `seq` exists to catch. It costs
        nothing to check, so there is no reason not to.
        """
        if self.consumed >= len(self.recorded):
            return False, None
        answer = self.recorded[self.consumed]
        if answer.kind is not decision.kind or answer.player != decision.player:
            raise ValueError(
                f"{decision.prompt}: recorded answer #{self.consumed} belongs to "
                f"{answer.player}'s {answer.kind.value}, not {decision.player}'s "
                f"{decision.kind.value} - the tape is corrupt or out of order"
            )
        if answer.seq != self.consumed:
            raise ValueError(
                f"{decision.prompt}: recorded answer #{self.consumed} claims seq={answer.seq} - "
                f"the tape is corrupt or out of order"
            )
        self.consumed += 1
        return True, answer.to_engine()

    def clear(self) -> None:
        self.answers.clear()

    def begin_replay(self, answers: Iterable[Answer]) -> None:
        """Start replaying a tape from the top, on a `Game` that may already
        carry state from a different command entirely.

        Sets `recorded` to `answers`, zeroes `consumed`, and clears `asked` -
        all three, together, because a caller resuming from a committed
        snapshot (see the module docstring's "Pausing instead of blocking")
        has no other way to know it must zero them by hand: `consumed` is a
        persisted field nothing else ever resets, so a stale nonzero value
        left over from a previous command would silently skip that many
        entries of the *new* tape before this one is even read; and clearing
        `asked` is what makes `PendingDecision.seq` (`len(asked) - 1`) start
        counting at 0 for this run, matching the `Answer.seq` values a caller
        assigns from `pending.seq` when it built this very tape - see
        `PendingDecision.seq`'s own docstring.

        Not called automatically by anything in this module: a caller that
        wants to replay a tape from scratch calls this once, before re-running
        the command, rather than assigning `recorded`/`consumed` directly.
        """
        self.recorded = list(answers)
        self.consumed = 0
        self.asked = []

    def finish_replay(self) -> None:
        """Assert the tape begun by `begin_replay` was read to the end.

        The mirror image of `take_from_tape`'s own refusal: that raises when a
        tape is read *out of order*; this raises when a command finishes
        without reading the tape *far enough* - a tape longer than the
        questions actually asked, which nothing else would ever notice,
        because a command that stops asking questions before the tape runs
        out looks exactly like a command that finished normally. A caller that
        replays a tape and does not call this can silently drop trailing
        answers a previous attempt already received.
        """
        if self.consumed != len(self.recorded):
            raise ValueError(
                f"the tape had {len(self.recorded)} answer(s) but only {self.consumed} were "
                f"asked for - the tape is longer than the questions this run actually asked"
            )


def ask_mulligan(script: DecisionScript, player: str, *, prompt: str = "take a mulligan") -> bool:
    """Put CR 103.5's mulligan declaration to a player, and return the answer.

    "A player who is dissatisfied with their initial hand may take a mulligan."
    Every player declares, in turn order, whether they will take one; True takes
    a mulligan and False keeps the hand.

    A boolean question asked and validated here rather than through `Game.ask`
    for the same reason it has its own kind: it is CR 103.5's question, asked
    before the first turn, and its default is the opposite of `MAY`'s - an
    unscripted player keeps the hand they were dealt. Both options are always
    legal when the question is put; the caller offers it only while CR 103.5's
    "a player can take mulligans until their opening hand would be zero cards"
    still allows one.

    Not going through `Game.ask` does not mean skipping the live player. The
    order of consultation is `Game.ask`'s exactly: a scripted answer wins, then
    the replay tape (`script.take_from_tape`), then `DecisionPending` if
    `script.pause_when_unanswered`, and only when nothing speaks (no tape
    entry, no pause) does `default_answer` keep the dealt hand. That is what
    makes CR 103.5's declaration answerable by a human, or resumable from a
    paused game, at all; without it the question was asked and recorded but
    never published anywhere a person - or a resumed run - could see it.

    Nothing random happens here, and the reshuffle seed `Match.run_mulligans`
    derives is a function of the declarations, not of who produced them.
    """
    decision = Decision(kind=DecisionKind.MULLIGAN, player=player, prompt=prompt, source_id=None)
    script.asked.append(decision)
    found, value = script.take(decision)
    if not found:
        found, value = script.take_from_tape(decision)
    if not found and script.pause_when_unanswered:
        raise DecisionPending(
            PendingDecision(
                seq=len(script.asked) - 1, decision=decision, rule=rule_for_kind(decision.kind)
            )
        )
    if not found:
        return bool(default_answer(decision))
    if not isinstance(value, bool):
        raise ValueError(f"{decision.prompt}: a yes-or-no question needs a bool answer")
    return value


def ask_trigger_order(
    script: DecisionScript,
    player: str,
    abilities: tuple[PendingAbility, ...],
    *,
    prompt: str = "order your triggered abilities on the stack",
) -> tuple[UUID, ...]:
    """Put CR 603.3b's ordering to one player, and return the order they chose.

    "First, each player, in APNAP order, puts each triggered ability they
    control on the stack in any order they choose." APNAP has already decided
    which *player's* block goes on first; this is the only choice left, and it
    is the one DDR#983 turns on.

    `abilities` is that player's own waiting abilities, one `PendingAbility`
    per ability, in the order they triggered - `PendingAbility` rather than
    `AbilityOnStack` objects so this module stays free of
    `machines/triggers.py`. The answer is a permutation of exactly them,
    **bottom of the stack first**, given as ids or as source names
    (`_resolve_trigger_order`). Asked and validated here rather than through
    `Game.ask` for
    the same reason `ask_mulligan` and the two combat declarations are: it is a
    question the rules ask, not one a resolving effect asks (CR 608.2d), and
    there is no yes-or-no for `legal_options` to narrow.

    Consultation order is `Game.ask`'s exactly - a scripted answer first, then
    the replay tape, then `DecisionPending` if `script.pause_when_unanswered`,
    then `default_answer`'s "leave it as it triggered". Fewer than two
    abilities is not a choice at all (CR 101.4's
    "if multiple players would make choices"; here, one ability has exactly
    one order), so nothing is asked and nothing is recorded.

    An answer that is not a permutation of `abilities` is refused outright
    rather than silently repaired: dropping an ability would be CR 603.3's "its
    controller puts it on the stack" going unperformed, and adding one would
    put an ability on the stack that never triggered.

    The `prompt` carries each source's printed name, numbered against `cards`.
    `Decision.cards` here holds `AbilityOnStack` ids, and an ability on the
    stack is an object but not a card (CR 113.1c, CR 405.1), so nothing that
    looks ids up among the board's cards can name them - a live seat asked this
    question with only the ids in front of it is being asked to choose between
    two anonymous hex strings.
    """
    ids = tuple(ability.id for ability in abilities)
    if len(ids) < 2:
        return ids
    # The prompt names each ability's source, numbered in the same order as
    # `cards`, because `Decision.cards` for this kind holds `AbilityOnStack`
    # ids and an ability is not a card (CR 113.1c, CR 405.1) - so nothing that
    # resolves ids against the board can put a name to them, and a live seat
    # would otherwise be asked to order two anonymous ids. The numbering is
    # positional against `cards` so an answerer that only has the ids can still
    # tell which is which.
    prompt = f"{prompt}, bottom of the stack first: " + ", ".join(
        f"{index}. {ability.source_name}" for index, ability in enumerate(abilities, start=1)
    )
    # `card_labels` is the structured form of what the prompt says in prose:
    # one label per `cards` entry, so a caller does not have to parse English
    # to build a usable picker. `abilities` carries each source's own printed
    # text too, which is what makes the label say more than just the source
    # name - the common case for this kind is two abilities off the same
    # source, which the name alone does not distinguish.
    labels = tuple(
        f"{ability.source_name} - {ability.text}" if ability.text else ability.source_name
        for ability in abilities
    )
    decision = Decision(
        kind=DecisionKind.ORDER_TRIGGERS,
        player=player,
        prompt=prompt,
        cards=ids,
        card_labels=labels,
        abilities=abilities,
        # CR 603.3b's question is about several abilities, each with a source
        # of its own, so no one object asks it.
        source_id=None,
    )
    script.asked.append(decision)
    found, value = script.take(decision)
    if not found:
        found, value = script.take_from_tape(decision)
    if not found and script.pause_when_unanswered:
        raise DecisionPending(
            PendingDecision(
                seq=len(script.asked) - 1, decision=decision, rule=rule_for_kind(decision.kind)
            )
        )
    if not found:
        value = default_answer(decision)
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{decision.prompt}: the answer is a sequence of ability ids or names")
    order = _resolve_trigger_order(decision, tuple(value), abilities)
    if sorted(order, key=str) != sorted(ids, key=str):
        raise ValueError(f"{decision.prompt}: the answer must order exactly the abilities offered")
    return order


def _resolve_trigger_order(
    decision: Decision, answer: tuple[object, ...], abilities: tuple[PendingAbility, ...]
) -> tuple[UUID, ...]:
    """Turn an `ORDER_TRIGGERS` answer into ability ids.

    A live answerer names ids, because it is looking at the abilities. A
    *scripted* one cannot: the abilities do not exist until the event fires, so
    a scenario that wants to state CR 603.3b's order in advance has only the
    printed source name to say it with - the same vocabulary
    `Scenario.choose_trigger_targets` already uses to name a trigger before it
    is on the stack. So a `str` in the answer is read as a source name and
    matched to one of the abilities offered.

    A name matching more than one of the offered abilities is refused rather
    than guessed at: two triggers of the same permanent are two orderings and
    the answer would not have said which is which.
    """
    remaining = list(abilities)
    order: list[UUID] = []
    for item in answer:
        if isinstance(item, UUID):
            order.append(item)
            continue
        if not isinstance(item, str):
            raise ValueError(f"{decision.prompt}: {item!r} is neither an ability id nor a name")
        hits = [
            ability
            for ability in remaining
            if ability.source_name == item or ability.source_name.split("//")[0].strip() == item
        ]
        if len(hits) != 1:
            raise ValueError(
                f"{decision.prompt}: {item!r} names {len(hits)} of the abilities offered, not one"
            )
        remaining.remove(hits[0])
        order.append(hits[0].id)
    return tuple(order)


def _ask_declaration(
    script: DecisionScript,
    kind: DecisionKind,
    player: str,
    prompt: str,
    attackers: tuple[UUID, ...] = (),
    default: Sequence[tuple[UUID, UUID | str]] = (),
) -> list[tuple["CardState | UUID", "CardState | TargetRef | UUID | str"]]:
    """Put a combat declaration to one player, and return what they declared.

    The shared body of `ask_attackers` and `ask_blockers`. Like `ask_mulligan`,
    this is a question the rules ask rather than one a resolving effect does, so
    it is asked and answered here rather than through `Game.ask` - but unlike
    the mulligan there is no yes-or-no to validate: the answer is a list of
    pairs, and whether the declared creatures may actually attack or block is
    the declaration rules' business, not the answer's. The caller passes the
    value through to `Game.declare_attackers` or `Game.declare_blockers` -
    `Game._resolve_declaration` first, when a pair might name ids rather than
    objects - which refuse an illegal declaration.

    Consultation order is every other asker's here, unchanged: a scripted
    answer first, then the replay tape, then `DecisionPending` if
    `script.pause_when_unanswered`, then `default_answer`'s "declare nobody".
    There is exactly one way to answer a decision from outside the engine -
    staging into the script or the tape - and this asker uses it the same way
    `Game.ask`, `ask_mulligan`, and `ask_trigger_order` do.
    """
    decision = Decision(
        kind=kind,
        player=player,
        prompt=prompt,
        cards=attackers,
        source_id=None,
        default_cards=tuple(creature for creature, _defender in default) or None,
    )
    script.asked.append(decision)
    found, value = script.take(decision)
    if not found:
        found, value = script.take_from_tape(decision)
    if not found and script.pause_when_unanswered:
        raise DecisionPending(
            PendingDecision(
                seq=len(script.asked) - 1, decision=decision, rule=rule_for_kind(decision.kind)
            )
        )
    if not found:
        # The asker's own legal floor when it gave one (CR 508.1d: a creature
        # that attacks each combat if able; CR 509.1c: one that blocks a named
        # attacker if able), else "declare nobody".
        value = tuple(default) if default else default_answer(decision)
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{decision.prompt}: the answer is a list of pairs")
    pairs: list[tuple[object, object]] = []
    for pair in value:
        if isinstance(pair, DeclaredPair):
            defender = (
                pair.defender_card if pair.defender_card is not None else pair.defender_player
            )
            pairs.append((pair.creature, defender))
            continue
        if not isinstance(pair, tuple) or len(pair) != 2:
            raise ValueError(f"{decision.prompt}: each answer is a (creature, target) pair")
        pairs.append(pair)
    return pairs


def ask_attackers(
    script: DecisionScript,
    player: str,
    *,
    prompt: str = "declare attackers",
    default: Sequence[tuple[UUID, UUID | str]] = (),
) -> list[tuple["CardState | UUID", "CardState | TargetRef | UUID | str"]]:
    """Put CR 703.4i's declaration to the active player (CR 508.1).

    "First, the active player declares which creatures they control, if any,
    are attacking, and then, if they are, the chosen opponents or planeswalkers
    they're attacking." The value is `(creature, defender)` pairs in declaration
    order; an unscripted player declares nobody, which is always legal ("if
    any").
    """
    return _ask_declaration(script, DecisionKind.DECLARE_ATTACKERS, player, prompt, default=default)


def ask_blockers(
    script: DecisionScript,
    player: str,
    *,
    prompt: str = "declare blockers",
    attackers: tuple[UUID, ...] = (),
    default: Sequence[tuple[UUID, UUID | str]] = (),
) -> list[tuple["CardState | UUID", "CardState | TargetRef | UUID | str"]]:
    """Put CR 703.4j's declaration to one defending player (CR 509.1).

    "The defending player declares which creatures they control, if any, are
    blocking which attacking creatures, and which attacking creatures those
    creatures are blocking." The value is `(blocker, attacker)` pairs;
    `attackers` carries the ids of the creatures attacking this player, as
    context on the decision. In a multiplayer game each defending player is
    asked in turn order (CR 802.4), and the whole combat is judged as one
    declaration (CR 509.1) once every answer is in.
    """
    return _ask_declaration(
        script, DecisionKind.DECLARE_BLOCKERS, player, prompt, attackers, default
    )
