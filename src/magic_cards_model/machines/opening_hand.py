"""Opening-hand actions: the step between the mulligan and the first turn (CR 103.6).

Every CR number in this file was looked up with
`knowledge_search(q="...", type="rules")` in the session that wrote it. The
search excerpts truncate at roughly two hundred characters, so where a rule's
tail is cut off that is said explicitly below rather than filled in from memory.

**CR 103.6** - "Some cards allow a player to take actions with them from their
opening hand. Once the mulligan process (see rule 103.5) is complete, the
starting player may take any such actions in any order. Then ea[ch other
player ...]" - the excerpt truncates there. What is verified, and all this
module relies on, is the part that is quoted: the sequence runs *once the
mulligan process is complete*, the *starting player goes first*, and each
player's own actions may be taken *in any order*. The engine walks
`Game.players`, which is seated with the starting player first, and takes one
player's actions in hand order; "in any order" leaves that free.

**CR 103.6a** - "If a card allows a player to begin the game with that card on
the battlefield, the player taking this action puts that card onto the
battlefield." That is the whole of the Leyline shape: the card moves from hand
to battlefield, and nothing else about it is special.

**CR 103.6b** - "If a card allows a player to reveal it from their opening hand,
the player taking this action does so. The card remains revealed until the first
turn begins. Each card may be revealed this way only on[ce ...]" - truncated
again, but the sentence is unambiguous about what it forbids, and
`Game.take_opening_hand_actions` runs once per game and looks at each card once,
so no card is offered the reveal twice.

**CR 103.8** - "The starting player takes their first turn." That is what
CR 103.6 runs *before*, and what CR 103.6b's "until the first turn begins"
means.

**CR 101.4** - "If multiple players would make choices and/or take actions at
the same time, the active player (the player whose turn it is) makes any choices
required, then the next player in turn order (usually the ...)" - truncated, but
it is not the rule that orders this sequence anyway: CR 103.6 states its own
order (starting player, then the others in turn order), and there is no active
player yet because no turn has begun. CR 101.4 is cited here only to record that
it was checked and does not apply.

**CR 701.20a** - "To reveal a card, show that card to all players for a brief
time." `Game.reveal` is what records that, and CR 701.20b keeps the card in hand
while it is revealed.

## What is read off a card, and what is not

Two printed templates, and only two:

- **CR 103.6a**, `BEGIN_ON_BATTLEFIELD`: "If this card is in your opening hand[
  and you're not the starting player], you may begin the game with [it/<name>]
  on the battlefield[ with a N counter on it]."
- **CR 103.6b**, `REVEAL`: "You may reveal this card from your opening hand."

Either may be followed by a rider - a trailing "If you do, ..." sentence that
does something the template itself does not describe. A rider is *parsed*,
never looked up by card name: `read_rider` splits it into CR 603.7's delayed
timing, when it has one, and the effect text, which is read by the same
`machines/effects.trigger_effect_for` every printed triggered ability goes
through.

- "If you do, at the beginning of your first upkeep, `<effect>`." (Devourer of
  Destiny) and "If you do, at the beginning of the first upkeep, `<effect>`."
  (Chancellor of the Forge) create a delayed triggered ability (CR 603.7) that
  fires once (CR 603.7b) - on the holder's own first upkeep for "your", on the
  game's first upkeep, whoever's it is, for "the".
- "If you do, `<effect>`." with no timing (Gemstone Caverns' "exile a card from
  your hand") is performed at once, as part of the action.

## Failing closed

A paragraph that mentions "opening hand" and matches neither template, or that
matches one but carries a rider whose timing or effect no reader recognises,
produces an
`OpeningHandNotice` and **no action at all**. The player is not offered a
choice they could not actually carry out, and the game carries a record saying
so - `Game.opening_hand_notices`. Silently offering the Leyline half of a card
whose rider is unimplemented would be the failure mode this project already
calls out: an effect that reads as permission while quietly doing less than the
card says.
"""

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import ConfigDict

from ..models.card import Card
from ..models.card_state import CardState
from ..snapshot import EngineModel
from .abilities import AbilityKind, TriggeredAbility, TriggerEvent, TriggerWord
from .delayed import CreatedTriggeredAbility, DelayedTrigger
from .triggers import AbilityOnStack
from .turn import Step

if TYPE_CHECKING:  # pragma: no cover - import cycle: the models build on the machines
    from ..models.game import Game
    from ..models.player import Player

__all__ = [
    "OpeningHandAction",
    "OpeningHandActionKind",
    "OpeningHandNotice",
    "Rider",
    "perform_rider",
    "read_opening_hand_actions",
    "read_opening_hand_line",
    "read_rider",
]


class OpeningHandActionKind(StrEnum):
    """The two things CR 103.6's subrules let a card do from an opening hand."""

    #: CR 103.6a: "the player taking this action puts that card onto the battlefield".
    BEGIN_ON_BATTLEFIELD = "begin_on_battlefield"
    #: CR 103.6b: "the player taking this action does so", and the card stays in hand.
    REVEAL = "reveal"


@dataclass(frozen=True)
class OpeningHandAction:
    """One action a card offers its holder before the first turn (CR 103.6)."""

    kind: OpeningHandActionKind
    #: The paragraph this was read off, as printed.
    text: str
    #: CR 103.6a's optional "with a luck counter on it" - the counter kind, or None.
    counter: str | None = None
    #: Gemstone Caverns' "and you're not the starting player" (CR 103.8's
    #: starting player). False for every other printing in the pool.
    requires_not_starting_player: bool = False
    #: The trailing sentence the template does not describe, as printed, or "".
    #: A non-empty rider must be readable by `read_rider` or the action is not
    #: offered.
    rider: str = ""


class OpeningHandNotice(EngineModel):
    """A card that claims an opening-hand action the engine did not carry out.

    Recorded rather than swallowed: an unreadable paragraph is not the same
    thing as a card with no opening-hand action, and a scenario that wants to
    prove the engine noticed can read `Game.opening_hand_notices`. Same
    unreadable-is-not-the-same-as-no-effect posture every other notice list on
    `Game` keeps.
    """

    model_config = ConfigDict(frozen=True)

    card_name: str
    text: str
    """The paragraph that was not acted on, as printed."""
    reason: str


#: CR 103.6a, both eras of wording. WOTC shortened "enters the battlefield" to
#: "enters" in 2024 but this template still says "on the battlefield" in every
#: printing in the pool; the optional counter clause is Gemstone Caverns'.
_BEGIN_ON_BATTLEFIELD = re.compile(
    r"^If this card is in your opening hand"
    r"(?P<restriction> and you're not the starting player)?"
    r", you may begin the game with (?:it|.+?) on the battlefield"
    r"(?: with an? (?P<counter>[\w+/-]+) counter on it)?"
    r"\.(?P<rider>.*)$",
    re.IGNORECASE,
)

#: CR 103.6b.
_REVEAL = re.compile(
    r"^You may reveal this card from your opening hand\.(?P<rider>.*)$",
    re.IGNORECASE,
)


def read_opening_hand_actions(
    card: Card,
) -> tuple[list[OpeningHandAction], list[OpeningHandNotice]]:
    """Read CR 103.6's actions off a printing, with a notice for anything unread.

    Paragraph-atomic, like every other reader in this package: oracle text puts
    one ability per line, and a line either matches a template whole or is
    reported unread. A line that never mentions an opening hand is not this
    module's business and produces neither an action nor a notice.
    """
    actions: list[OpeningHandAction] = []
    notices: list[OpeningHandNotice] = []
    for paragraph in (card.oracle_text or "").split("\n"):
        read = read_opening_hand_line(card.name, paragraph)
        if isinstance(read, OpeningHandAction):
            actions.append(read)
        elif read is not None:
            notices.append(read)
    return actions, notices


def read_opening_hand_line(
    card_name: str, paragraph: str
) -> OpeningHandAction | OpeningHandNotice | None:
    """One oracle paragraph read as CR 103.6's action, a notice when it
    mentions an opening hand but cannot be carried out in full, or None when
    it is not about an opening hand at all. `support.py` asks this per line."""
    line = paragraph.strip()
    if "opening hand" not in line.lower():
        return None

    begin = _BEGIN_ON_BATTLEFIELD.match(line)
    reveal = _REVEAL.match(line)
    if begin is not None:
        action = OpeningHandAction(
            kind=OpeningHandActionKind.BEGIN_ON_BATTLEFIELD,
            text=line,
            counter=begin.group("counter"),
            requires_not_starting_player=begin.group("restriction") is not None,
            rider=begin.group("rider").strip(),
        )
    elif reveal is not None:
        action = OpeningHandAction(
            kind=OpeningHandActionKind.REVEAL,
            text=line,
            rider=reveal.group("rider").strip(),
        )
    else:
        return OpeningHandNotice(
            card_name=card_name,
            text=line,
            reason=(
                "mentions an opening hand but matches neither CR 103.6a's "
                "begin-on-the-battlefield template nor CR 103.6b's reveal one"
            ),
        )

    if action.rider and read_rider(card_name, action.rider) is None:
        return OpeningHandNotice(
            card_name=card_name,
            text=line,
            reason=(
                f"CR 103.6's action carries a rider ({action.rider!r}) whose timing "
                f"or effect no reader recognises, so taking the action would do "
                f"less than the card says"
            ),
        )
    return action


# -- riders: what the template does not describe ---------------------------


#: "If you do, <body>" - CR 103.6's action is the antecedent of "do".
_RIDER_RE = re.compile(r"^if you do, (?P<body>.+)$", re.IGNORECASE)

#: "at the beginning of your first upkeep, <effect>" / "at the beginning of
#: the first upkeep, <effect>" - CR 603.7's delayed triggered ability, created
#: by the action. "your" is the holder's own first upkeep; "the" is the game's
#: first upkeep, whoever's turn it is.
_FIRST_STEP_RE = re.compile(
    r"^at the beginning of (?P<whose>your|the) first (?P<step>upkeep), (?P<effect>.+)$",
    re.IGNORECASE,
)

#: The steps a "first <step>" rider can name, and the step each is.
_FIRST_STEPS: dict[str, Step] = {"upkeep": Step.UPKEEP}


@dataclass(frozen=True)
class Rider:
    """A parsed opening-hand rider: its effect text and, for a delayed one,
    the step it waits for and whose it is."""

    #: The effect, as printed, with the "If you do," and any timing removed.
    effect: str
    #: CR 603.7's delayed timing - the step it waits for, or None to perform
    #: the effect as part of the action itself.
    step: Step | None = None
    #: "your first <step>": only the holder's own step triggers it.
    yours: bool = False


def read_rider(card_name: str, rider: str) -> Rider | None:
    """Read an opening-hand rider, or None when any part of it is unreadable.

    The effect must be one `machines/effects.trigger_effect_for` really
    performs - a fail-closed stand-in (`..._notice_only`) is not enough, since
    offering the action would then do less than the card says.
    """
    from .effects import trigger_effect_for

    match = _RIDER_RE.match(rider.strip())
    if match is None:
        return None
    body = match.group("body").strip()
    step: Step | None = None
    yours = False
    timed = _FIRST_STEP_RE.match(body)
    if timed is not None:
        step = _FIRST_STEPS[timed.group("step").lower()]
        yours = timed.group("whose").lower() == "your"
        body = timed.group("effect").strip()
    event = TriggerEvent.BEGINNING_OF_STEP if step is not None else None
    effect = trigger_effect_for(card_name, event, body)
    if effect is None or getattr(effect, "__name__", "").endswith("notice_only"):
        return None
    return Rider(effect=body, step=step, yours=yours)


def perform_rider(game: "Game", card_state: CardState, player: "Player", text: str) -> None:
    """Carry out a rider `read_rider` already accepted.

    A timed rider creates its delayed triggered ability (CR 603.7), fired once
    (CR 603.7b, `remaining=1`): the created ability's own printed shape is
    "At the beginning of your upkeep" or "At the beginning of each upkeep",
    read by the same condition matcher and effect dispatcher every printed
    trigger uses (`CreatedTriggeredAbility`), and "your" is further pinned to
    the holder's own step with `only_when_active`.

    An untimed rider is performed at once, as part of the action, by the
    effect `trigger_effect_for` reads off its text, with the card as its
    source and its holder as the player doing it.
    """
    from .effects import trigger_effect_for

    rider = read_rider(card_state.card.name, text)
    assert rider is not None  # `read_opening_hand_actions` refused it otherwise
    if rider.step is not None:
        whose = "your" if rider.yours else "each"
        created = f"At the beginning of {whose} {rider.step.value}, {rider.effect}"
        # The trigger as printed ("your first upkeep" / "the first upkeep") is
        # what a seat is shown; `created` is the shape the matcher reads, and
        # `remaining=1` is what makes it the first (CR 603.7b).
        printed = (
            f"At the beginning of {'your' if rider.yours else 'the'} first "
            f"{rider.step.value}, {rider.effect}"
        )
        game.delayed_triggers.create(
            DelayedTrigger(
                text=printed,
                effect=CreatedTriggeredAbility(ability_text=created, source_card=card_state.card),
                event=TriggerEvent.BEGINNING_OF_STEP,
                step=rider.step,
                controller=player.username,
                source_id=card_state.id,
                source_name=card_state.name,
                only_when_active=player.username if rider.yours else None,
            )
        )
        return
    effect = trigger_effect_for(card_state.card.name, None, rider.effect)
    assert effect is not None
    effect(
        game,
        AbilityOnStack(
            kind=AbilityKind.TRIGGERED,
            ability=TriggeredAbility(
                raw=text,
                text=text,
                face=card_state.name,
                word=TriggerWord.WHEN,
                condition="you take this opening-hand action",
                effect=rider.effect,
            ),
            source_id=card_state.id,
            source_name=card_state.name,
            controller=player.username,
        ),
    )
