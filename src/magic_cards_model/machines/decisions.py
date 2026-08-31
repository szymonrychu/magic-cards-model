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

A caller that stands behind a *live* player - the API's per-game decision
mailbox is the first one - sets `DecisionScript.provider` instead of, or on top
of, scripting answers: `Game.ask` tries a scripted answer first (a test's
staging always wins), then the provider, and only then `default_answer`.
`ask_mulligan` follows that same order without going through `Game.ask`, so
CR 103.5's declaration reaches a live seat too; `ask_attackers` and
`ask_blockers` still do not, and are the last two questions here a provider
cannot answer. The
provider is not a resumable state machine and does not need to be one - it is
a `Protocol` with one method that blocks the calling thread until a real
answer arrives or it gives up, exactly the shape a synchronous call stack
needs.

When nobody - script or provider - has anything to say, `default_answer`
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

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID

from ..models.card_state import TargetRef

if TYPE_CHECKING:  # pragma: no cover - import cycle: the models build on the machines
    from ..models.card_state import CardState

__all__ = [
    "NOT_ANSWERED",
    "CardSplit",
    "Decision",
    "DecisionKind",
    "DecisionProvider",
    "DecisionScript",
    "NotAnswered",
    "ScriptedAnswer",
    "ask_attackers",
    "ask_blockers",
    "ask_mulligan",
    "default_answer",
    "legal_options",
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
    #: Only mana already floating in that player's pool can pay it. CR 608.2g
    #: lets a player activate mana abilities right here, but this engine has
    #: no interactive "tap a land mid-resolution" step, so a controller who
    #: would have to tap a source to make the payment is treated as unable to
    #: pay - see `docs/engine-coverage.md`.
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
    #: the legal answers to the five colors for a color choice, and is empty
    #: for the other two, whose universe (every card name; every creature
    #: type) is too large to enumerate here. Which of the three was actually
    #: asked is not carried on the `Decision` at all - the replacement effect
    #: that asks already knows, from the card's own printed text, and records
    #: it on `CardState.choice`'s own `ChoiceKind` once the answer comes back.
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
    #: Whether the affirmative branch is legal at all (CR 608.2d, CR 119.4).
    #: `False` removes it from `legal_options`, which is how paying 2 life at
    #: 1 life stops being an option rather than becoming a rules violation.
    affirmative_is_legal: bool = True
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
    #: string" (a card name, a creature type - too large a set to enumerate).
    #: Populated with the five colors' letter codes for a color choice.
    options: tuple[str, ...] = ()
    #: `CHOOSE_CARDS` only: `True` (the default, every existing question) means
    #: `amount` is exact - the cleanup discard, which always names precisely
    #: how many. `False` means CR 107.1c's "any number" - Valakut Awakening's
    #: "put any number of cards from your hand" - so `amount` is a ceiling
    #: (every card offered) and any count from zero up to it, inclusive, is a
    #: legal answer.
    exact: bool = True


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
    if decision.kind in (DecisionKind.DECLARE_ATTACKERS, DecisionKind.DECLARE_BLOCKERS):
        # CR 508.1 says "if any" and CR 509.1 says "may": declaring nobody is
        # always legal, and is what an unscripted player does.
        return ()
    if decision.kind is DecisionKind.CHOOSE_CARDS:
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
        # something. The first offered option for a color choice; an empty
        # string for the other two, which offer none: there is no rule-backed
        # "first card name" or "first creature type" to reach for.
        return decision.options[0] if decision.options else ""
    if decision.kind is DecisionKind.CHOOSE_A_MODE:
        # CR 700.2a's choice is mandatory too, same reasoning as
        # CHOOSE_A_QUALITY just above: the first printed mode, not a
        # judgement about which mode is best.
        return decision.options[0] if decision.options else ""
    return CardSplit()


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


class NotAnswered:
    """Sentinel returned by a `DecisionProvider` that has no answer right now.

    Distinct from any real answer (`False`, `CardSplit()`, and `()` are all
    real answers) so `Game.ask` can tell "asked and heard nothing back" apart
    from "asked and was told no". A timed-out provider returns this, and
    `Game.ask` then falls through to `default_answer` exactly as if no
    provider had been asked at all.
    """


#: The one instance; a provider returns this object, not a fresh one, so a
#: caller can compare with `is`.
NOT_ANSWERED = NotAnswered()


class DecisionProvider(Protocol):
    """A live player standing behind a `Decision`, outside the engine.

    One method, deliberately: `Game.ask` (and `ask_mulligan`, for CR 103.5's
    declaration) already does the asking, the
    recording (`DecisionScript.asked`), and the validation against
    `legal_options`. A provider's only job is to produce an answer or say it
    has none, so that whatever calls it - a human at a keyboard, a UI, a
    server thread parked on a socket - stays out of the engine's control flow.
    Nothing here is resumable and nothing needs to be: the call blocks the
    thread that is resolving the spell until the answer, or a timeout that the
    provider itself is responsible for enforcing, comes back.
    """

    def decide(self, decision: Decision) -> object:
        """Return the player's answer, or `NOT_ANSWERED` if none arrived."""
        ...


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
    #: Consulted by `Game.ask` - and by `ask_mulligan`, which puts CR 103.5's
    #: declaration by the same rules without going through `Game.ask` - when
    #: nothing is scripted. `None` in every
    #: scenario test, so a test's behaviour is unaffected by this existing at
    #: all - a caller that wants live answers (the API's per-game mailbox)
    #: sets this instead of scripting anything.
    #:
    #: Typed as `Any`, not `DecisionProvider | None`, because `Game` is a
    #: pydantic model and `DecisionScript` is a plain dataclass nested inside
    #: it: pydantic builds a validation schema for every field of a nested
    #: dataclass, and a `Protocol` has none to build. The real type callers
    #: should assign is `DecisionProvider | None`; `Any` here is a pydantic
    #: accommodation, not a relaxation of what belongs in this field.
    provider: Any = None

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

    def clear(self) -> None:
        self.answers.clear()


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
    `script.provider` - the same mailbox a `DecisionProvider` behind the API
    fills in - is asked, and only when neither speaks (no provider, or
    `NOT_ANSWERED`) does `default_answer` keep the dealt hand. That is what
    makes CR 103.5's declaration answerable by a human at all; without it the
    question was asked and recorded but never published anywhere a person could
    see it.

    Asking a provider does not disturb the replay: nothing random happens here,
    and the reshuffle seed `Match.run_mulligans` derives is a function of the
    declarations, not of who produced them.
    """
    decision = Decision(kind=DecisionKind.MULLIGAN, player=player, prompt=prompt)
    script.asked.append(decision)
    found, value = script.take(decision)
    if not found and script.provider is not None:
        provided = script.provider.decide(decision)
        if provided is not NOT_ANSWERED:
            found, value = True, provided
    if not found:
        return bool(default_answer(decision))
    if not isinstance(value, bool):
        raise ValueError(f"{decision.prompt}: a yes-or-no question needs a bool answer")
    return value


def _ask_declaration(
    script: DecisionScript,
    kind: DecisionKind,
    player: str,
    prompt: str,
    attackers: tuple[UUID, ...] = (),
) -> list[tuple["CardState", "CardState | TargetRef"]]:
    """Put a combat declaration to one player, and return what they declared.

    The shared body of `ask_attackers` and `ask_blockers`. Like `ask_mulligan`,
    this is a question the rules ask rather than one a resolving effect does, so
    it is asked and answered here rather than through `Game.ask` - but unlike
    the mulligan there is no yes-or-no to validate: the answer is a list of
    pairs, and whether the declared creatures may actually attack or block is
    the declaration rules' business, not the answer's. The caller passes the
    value straight through to `Game.declare_attackers` or
    `Game.declare_blockers`, which refuse an illegal declaration.
    """
    decision = Decision(kind=kind, player=player, prompt=prompt, cards=attackers)
    script.asked.append(decision)
    found, value = script.take(decision)
    if not found:
        value = default_answer(decision)
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{decision.prompt}: the answer is a list of pairs")
    for pair in value:
        if not isinstance(pair, tuple) or len(pair) != 2:
            raise ValueError(f"{decision.prompt}: each answer is a (creature, target) pair")
    return list(value)


def ask_attackers(
    script: DecisionScript,
    player: str,
    *,
    prompt: str = "declare attackers",
) -> list[tuple["CardState", "CardState | TargetRef"]]:
    """Put CR 703.4i's declaration to the active player (CR 508.1).

    "First, the active player declares which creatures they control, if any,
    are attacking, and then, if they are, the chosen opponents or planeswalkers
    they're attacking." The value is `(creature, defender)` pairs in declaration
    order; an unscripted player declares nobody, which is always legal ("if
    any").
    """
    return _ask_declaration(script, DecisionKind.DECLARE_ATTACKERS, player, prompt)


def ask_blockers(
    script: DecisionScript,
    player: str,
    *,
    prompt: str = "declare blockers",
    attackers: tuple[UUID, ...] = (),
) -> list[tuple["CardState", "CardState | TargetRef"]]:
    """Put CR 703.4j's declaration to one defending player (CR 509.1).

    "The defending player declares which creatures they control, if any, are
    blocking which attacking creatures, and which attacking creatures those
    creatures are blocking." The value is `(blocker, attacker)` pairs;
    `attackers` carries the ids of the creatures attacking this player, as
    context on the decision. In a multiplayer game each defending player is
    asked in turn order (CR 802.4), and the whole combat is judged as one
    declaration (CR 509.1) once every answer is in.
    """
    return _ask_declaration(script, DecisionKind.DECLARE_BLOCKERS, player, prompt, attackers)
