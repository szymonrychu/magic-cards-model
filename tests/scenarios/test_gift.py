"""Gift: CR 702.174, the additional-cost half and the "chosen player" effect.

"The first ability is always 'As an additional cost to cast this spell, you
may choose an opponent.'" (CR 702.174a) - `Casting.pay_gift` records the
choice; nothing is spent, since the choice *is* the cost. "For instant and
sorcery spells, the effect of a gift ability always happens before any other
spell abilities of the card" (CR 702.174j) -
`machines/effects.apply_gift_if_promised`, dispatched off the keyword's own
printed parameter through `_GIFT_EFFECTS` (CR 702.174d-i, every shape the
rule states, not only Into the Flood Maw's own "a tapped Fish").

A permanent's own gift trigger (CR 702.174b's "when this permanent enters,
if its gift cost was paid, [effect]") is not modelled - see
docs/engine-coverage.md.

Proved generic on Crumb and Get It's "Gift a Food", a card outside the deck
pool and outside this wave's brief.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_into_the_flood_maw_gifts_a_tapped_fish():
    """Into the Flood Maw: "Gift a tapped Fish ... Return target creature an
    opponent controls to its owner's hand."
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Into the Flood Maw"], battlefield=["Island"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    maw = scenario.find("Into the Flood Maw", Zone.HAND, "alice")
    (island,) = scenario.untapped_sources("Island", username="alice")

    scenario.game.cast(maw, "alice", targets=[bears], mana_sources=[island], gift="bob")
    scenario.pass_until_resolved()

    fish = [state for state in scenario.game.battlefield if state.name == "Fish Token"]
    assert len(fish) == 1
    (fish_token,) = fish
    assert fish_token.controller == "bob"
    assert fish_token.tapped
    assert bears.zone is Zone.HAND, "the main effect still resolved too"


def test_declining_the_gift_creates_no_fish():
    """CR 702.174k: a gift not promised does not happen."""
    scenario = (
        Scenario()
        .player("alice", hand=["Into the Flood Maw"], battlefield=["Island"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    maw = scenario.find("Into the Flood Maw", Zone.HAND, "alice")
    (island,) = scenario.untapped_sources("Island", username="alice")

    scenario.game.cast(maw, "alice", targets=[bears], mana_sources=[island])
    scenario.pass_until_resolved()

    assert "Fish Token" not in scenario.battlefield_names()


def test_crumb_and_get_it_gifts_a_food():
    """Crumb and Get It: "Gift a Food (... they create a Food token before
    its other effects. It's an artifact with '{2}, {T}, Sacrifice this
    token: You gain 3 life.')" - not in the deck pool, not named in this
    wave's brief.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Crumb and Get It"],
            battlefield=["Plains", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    card = scenario.find("Crumb and Get It", Zone.HAND, "alice")
    (plains,) = scenario.untapped_sources("Plains", username="alice")

    scenario.game.cast(card, "alice", targets=[bears], mana_sources=[plains], gift="bob")
    scenario.pass_until_resolved()

    food = [state for state in scenario.game.battlefield if state.name == "Food Token"]
    assert len(food) == 1
    assert food[0].controller == "bob"
