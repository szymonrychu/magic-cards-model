"""FRA stream S8: "Put target card from `<your|a>` graveyard on the bottom
of `<your|its owner's>` library." (CR 401.2, CR 108.3).

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file.

- **CR 401.2** - a library stays face down and in whatever order cards are
  put into it; this is a plain move, never CR 701.24's shuffle.
- **CR 108.3** - "its owner's library" moves the card into whichever player
  owns it, not the ability's own controller.
- **CR 404.1** - a graveyard is per player.

Paradox Shaper is the reported card, handed to this stream directly. Its
own printed wording targets only "your graveyard" and moves the card to
"your library" - self only. Cogwork Archivist (Strixhaven, real, non-FRA,
non-pool) prints the same shape off a genuinely different cost (`{2}, {T}:`
rather than Paradox Shaper's bare `{2}:`) and a genuinely different target
phrase - "a graveyard" (any player's) onto "its owner's library" - which
this parser reads as the same underlying move with a wider legal target,
not a second copy of the mechanic.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_paradox_shaper_puts_its_own_graveyard_card_on_the_bottom():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Paradox Shaper", "Island", "Island"],
            graveyard=["Grizzly Bears"],
            library=["Forest", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    shaper = scenario.creature("Paradox Shaper", "alice")
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    sources = scenario.untapped_sources("Island", "Island")

    scenario.activate(shaper, *sources, targets=[bears])
    scenario.pass_until_resolved()

    alice = scenario.player("alice")
    assert bears.zone is Zone.LIBRARY
    assert alice.library[-1] is bears, "put on the bottom, not the top"


def test_cogwork_archivist_reaches_an_opponents_graveyard_and_routes_by_owner():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Cogwork Archivist", "Island", "Island"])
        .player("bob", graveyard=["Lightning Bolt"], library=["Forest", "Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    archivist = scenario.creature("Cogwork Archivist", "alice")
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "bob")
    sources = scenario.untapped_sources("Island", "Island")

    scenario.activate(archivist, *sources, targets=[bolt])
    scenario.pass_until_resolved()

    bob = scenario.player("bob")
    assert bolt.zone is Zone.LIBRARY
    assert bob.library[-1] is bolt, "its owner's library (bob's), not alice's"
