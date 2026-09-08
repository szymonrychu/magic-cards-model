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

Either may be followed by a rider - a further sentence that does something the
template itself does not describe. Gemstone Caverns' "If you do, exile a card
from your hand" and Devourer of Destiny's "If you do, at the beginning of your
first upkeep, ..." are the two in the card pool. A rider is *not* parsed: it is
looked up by card name in `RIDERS`, exactly the way `machines/effects.py` and
`machines/delayed.py` key their own hand-written behaviour, because the shapes
have nothing in common with each other.

## Failing closed

A paragraph that mentions "opening hand" and matches neither template, or that
matches one but carries a rider with no `RIDERS` entry, produces an
`OpeningHandNotice` and **no action at all**. The player is not offered a
choice they could not actually carry out, and the game carries a record saying
so - `Game.opening_hand_notices`. Silently offering the Leyline half of a card
whose rider is unimplemented would be the failure mode this project already
calls out: an effect that reads as permission while quietly doing less than the
card says.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from ..models.card import Card
from ..models.card_state import CardState
from .abilities import TriggerEvent
from .decisions import Decision, DecisionKind
from .delayed import DelayedTrigger, devourer_of_destiny_first_upkeep
from .turn import Step

if TYPE_CHECKING:  # pragma: no cover - import cycle: the models build on the machines
    from ..models.game import Game
    from ..models.player import Player

__all__ = [
    "RIDERS",
    "OpeningHandAction",
    "OpeningHandActionKind",
    "OpeningHandNotice",
    "read_opening_hand_actions",
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
    #: A non-empty rider needs a `RIDERS` entry or the action is not offered.
    rider: str = ""


class OpeningHandNotice(BaseModel):
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
    text = card.oracle_text or ""

    for paragraph in text.split("\n"):
        line = paragraph.strip()
        if "opening hand" not in line.lower():
            continue

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
            notices.append(
                OpeningHandNotice(
                    card_name=card.name,
                    text=line,
                    reason=(
                        "mentions an opening hand but matches neither CR 103.6a's "
                        "begin-on-the-battlefield template nor CR 103.6b's reveal one"
                    ),
                )
            )
            continue

        if action.rider and card.name not in RIDERS:
            notices.append(
                OpeningHandNotice(
                    card_name=card.name,
                    text=line,
                    reason=(
                        f"CR 103.6's action carries a rider ({action.rider!r}) with no "
                        f"entry in machines/opening_hand.py's RIDERS, so taking the "
                        f"action would do less than the card says"
                    ),
                )
            )
            continue

        actions.append(action)

    return actions, notices


# -- riders: what the template does not describe ---------------------------


def _gemstone_caverns_rider(game: "Game", card_state: CardState, player: "Player") -> None:
    """ "If you do, exile a card from your hand." (Gemstone Caverns)

    A cost the card charges for starting on the battlefield, paid after it is
    already there - the sentence is "if you do", not "unless you do", so there
    is no branch where the Caverns stays in hand. Which card is exiled is the
    holder's choice, asked as CR 608.2d's `CHOOSE_CARDS` question the cleanup
    discard already uses; an empty hand exiles nothing, because there is
    nothing to choose.

    Nothing here is random, so nothing here needs the match seed: a replay with
    the same declarations and the same scripted choice exiles the same card.

    The exile goes through `Game.exile_cards`, never
    `Player.move(state, Zone.EXILE)`. CR 400.1: "Each player has their own
    library, hand, and graveyard. The other zones are shared by all players" -
    so there is one exile zone, `Game.shared_zones[Zone.EXILE]`, and CR 406.2's
    "put it into the exile zone" means that one. Exiling into a pile of the
    holder's own left the card where `Game.exile`, `Game.all_targetables` and
    every seat's board could not see it: paid, gone from hand, and nowhere.
    """
    hand = list(player.hand)
    if not hand:
        return
    chosen = game.ask(
        Decision(
            kind=DecisionKind.CHOOSE_CARDS,
            player=player.username,
            prompt="exile a card from your hand",
            source=card_state.name,
            amount=1,
            cards=tuple(state.id for state in hand),
        )
    )
    assert isinstance(chosen, tuple)
    by_id = {state.id: state for state in hand}
    game.exile_cards([by_id[card_id] for card_id in chosen])


def _devourer_of_destiny_rider(game: "Game", card_state: CardState, player: "Player") -> None:
    """ "If you do, at the beginning of your first upkeep, ..." (Devourer of Destiny)

    A delayed triggered ability (CR 603.7): created now, by the opening-hand
    action, and waiting for one particular step. "Your first upkeep" is the
    next upkeep that is *this player's* - `only_when_active` is what makes it
    theirs and `remaining=1` (CR 603.7b's default, "only once - the next time
    its trigger event occurs") is what makes it the first.
    """
    game.delayed_triggers.create(
        DelayedTrigger(
            text=(
                "At the beginning of your first upkeep, look at the top four cards of "
                "your library. You may put one of those cards back on top of your "
                "library. Exile the rest."
            ),
            effect=devourer_of_destiny_first_upkeep,
            event=TriggerEvent.BEGINNING_OF_STEP,
            step=Step.UPKEEP,
            controller=player.username,
            source_id=card_state.id,
            source_name=card_state.name,
            only_when_active=player.username,
        )
    )


#: What a card's trailing "If you do, ..." sentence actually does, by card name.
#: Hand-written for the same reason `machines/delayed.py`'s own registry is:
#: the two riders in the pool have no shape in common, so there is nothing to
#: parse. A card with a rider and no entry here is refused the action outright
#: and reported on `Game.opening_hand_notices`; see this module's docstring.
RIDERS: dict[str, Callable[["Game", CardState, "Player"], None]] = {
    "Gemstone Caverns": _gemstone_caverns_rider,
    "Devourer of Destiny": _devourer_of_destiny_rider,
}
