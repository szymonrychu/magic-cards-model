"""FRA stream S8: "Reveal cards from the top of your library until you
reveal a `<kind>`[ or `<kind2>`] card. Put that card `<dest>` and the rest
on the bottom of your library in a random order." (CR 701.20a's open-ended
reveal, CR 607.1's "that card"/"the rest" linked-ability anaphora).

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file.

- **CR 701.20a** - to reveal a card, show it to all players; revealing moves
  nothing by itself.
- **CR 607.1** - "that card" and "the rest" are linked back onto exactly
  what the reveal sentence showed, not a fresh scan of the library or
  graveyard.
- **CR 701.13a** - exiling, for Identity Echo's own antecedent target.
- **CR 401.2** - the top of the library is a known position; revealing in
  order from there is what "until" walks down.
- **CR 701.24a** - shuffling is a distinct action never printed here; "the
  rest ... in a random order" is a randomization, not a shuffle, so nothing
  watching for a shuffle fires.

Identity Echo's own activated ability is the reported card: "Exile target
creature or planeswalker you control. Reveal cards from the top of your
library until you reveal a creature or planeswalker card. Put that card
onto the battlefield and the rest on the bottom of your library in a random
order." Evolutionary Leap (real, non-FRA, non-pool) is the off-set proof:
the identical reveal-until-kind-then-put shape with a single kind (creature,
not the two-way "creature or planeswalker" disjunction), a different
destination (hand, not the battlefield), and no antecedent exile at all -
proving the merge and the kind reader both generalize.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_identity_echo_exiles_then_reveals_until_creature_or_planeswalker():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Identity Echo",
                "Grizzly Bears",
                "Mountain",
                "Mountain",
                "Mountain",
                "Mountain",
            ],
            library=["Lightning Bolt", "Forest", "Hill Giant", "Elvish Mystic"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    identity_echo = scenario.find("Identity Echo", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain")
    alice = scenario.player("alice")

    bolt = alice.library[0]
    forest = alice.library[1]
    hill_giant = alice.library[2]
    elvish_mystic = alice.library[3]

    scenario.activate(identity_echo, *sources, index=0, targets=[bears])
    scenario.pass_until_resolved()

    assert bears.zone is Zone.EXILE, "the antecedent's own targeted exile (CR 701.13a)"
    assert hill_giant.zone is Zone.BATTLEFIELD, "the creature card that stopped the reveal"
    assert bolt.zone is Zone.LIBRARY and forest.zone is Zone.LIBRARY, (
        "the rest of what was revealed went to the bottom, in a random order"
    )
    assert elvish_mystic.zone is Zone.LIBRARY, (
        "never revealed at all - the reveal stopped before it"
    )
    remaining_names = {card.name for card in alice.library}
    assert remaining_names == {"Lightning Bolt", "Forest", "Elvish Mystic"}


def test_evolutionary_leap_reveals_until_creature_to_hand():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Evolutionary Leap", "Grizzly Bears", "Forest"],
            library=["Lightning Bolt", "Island", "Hill Giant"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    evolutionary_leap = scenario.find("Evolutionary Leap", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    (forest,) = scenario.untapped_sources("Forest")
    alice = scenario.player("alice")
    hand_before = len(alice.hand)

    bolt = alice.library[0]
    island = alice.library[1]
    hill_giant = alice.library[2]

    scenario.activate(evolutionary_leap, forest, index=0, sacrificing=[bears])
    scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD, "the cost's own sacrifice"
    assert hill_giant.zone is Zone.HAND, "the creature card that stopped the reveal"
    assert len(alice.hand) == hand_before + 1
    assert bolt.zone is Zone.LIBRARY and island.zone is Zone.LIBRARY
