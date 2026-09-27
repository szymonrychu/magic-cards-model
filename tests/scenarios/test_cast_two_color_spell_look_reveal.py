""" "Whenever you cast a spell that's exactly two colors, look at the top six
cards of your library. You may reveal a card that's exactly two colors from
among them and put it into your hand. Put the rest on the bottom of your
library in a random order." - Invasion of Ravnica // Guildpact Paragon's own
back face.

Every CR number here was looked up with `mise run rules:find`:

- **CR 105.2b** - "A multicolored object is two or more of the five
  colors" - "exactly two colors" narrows that count to precisely 2 rather
  than "2 or more".
- **CR 701.20e** - "look at" shows a zone's cards to one player only.
- **CR 701.20a** - to reveal a card is to show it to everyone.
- **CR 401.4** - only an *ordered* placement lets its owner choose the
  order; "in a random order" is not that.

`machines/effects._merge_look_top_reveal_to_hand_clauses` already reads
"look at the top N ... you may reveal a `<quality>` card from among them ...
put the rest on the bottom in a random order" (Duskwatch Recruiter and
others) with the quality word placed *before* "card" ("a creature card").
Guildpact Paragon spells it the other way round, as a relative clause after
"card" ("a card that's exactly two colors") - the same CR 105.2 colour count
`_COLOR_COUNT_WORDS` already reads for "monocolored"/"multicolored", just
never spelled out with its own number before, and never in this word order.

No second Modern/Pioneer/Standard-legal printing of "a card that's exactly
two colors" or "you cast a spell that's exactly two colors" turned up on a
Scryfall search of the printed phrases - this looks to be the one place
Magic has printed either sentence. Generality is therefore proven the way
the fix itself is general - `_relative_quality_matcher` reads any color
count this way (`monocolored`, `multicolored`, or any spelled-out "exactly N
colors"), not a check fitted to "two" - rather than by a second card, which
does not exist in print; see this session's `MEMORY.md` note.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

RAVNICA = "Invasion of Ravnica // Guildpact Paragon"


def _paragon_board(library: list[str]) -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[RAVNICA, "Lightning Helix"],
            battlefield=["Mountain", "Mountain", "Plains"],
            library=library,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    card = scenario.find("Invasion of Ravnica", Zone.HAND, "alice")
    scenario.game.put_onto_battlefield(card, "alice", transformed=True)
    return scenario


def test_casting_a_two_color_spell_offers_a_two_color_card_from_the_top():
    """Lightning Helix ({R}{W}) is exactly two colors, so it triggers the
    look; Boros Reckoner among the top six (also exactly two colors) is
    what gets offered and taken."""
    scenario = _paragon_board(
        library=["Boros Reckoner", "Grizzly Bears", "Forest", "Island", "Swamp", "Plains"]
    )
    reckoner = scenario.find("Boros Reckoner", Zone.LIBRARY, "alice")

    scenario.cast_onto_stack("Lightning Helix", targets=["bob"], auto=True)
    # `Game.look_at_top_and_split` reuses CR 701.22a's own `SCRY` question
    # (see its own docstring) - "moved" here means "to hand", the
    # destination this ability's own text names.
    scenario.scry_bottoming(reckoner, username="alice")
    scenario.pass_until_resolved()  # Lightning Helix
    scenario.pass_until_resolved()  # Guildpact Paragon's own cast trigger

    assert reckoner.zone is Zone.HAND
    assert reckoner not in scenario.player("alice").library


def test_a_monocolored_spell_cast_alone_triggers_nothing():
    """Grizzly Bears is one colour (green), not "exactly two", so casting it
    triggers nothing at all - the stack is empty once it resolves and the
    library is untouched."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[RAVNICA, "Grizzly Bears"],
            battlefield=["Forest", "Forest"],
            library=["Boros Reckoner", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    card = scenario.find("Invasion of Ravnica", Zone.HAND, "alice")
    scenario.game.put_onto_battlefield(card, "alice", transformed=True)

    scenario.cast_and_resolve("Grizzly Bears", auto=True)

    assert scenario.game.stack == []
    assert scenario.player("alice").library[0].name == "Boros Reckoner"
