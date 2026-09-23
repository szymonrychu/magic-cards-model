"""Scenario: "Exile this artifact" as an activation cost (CR 602.2b,
CR 118.3) - the permanent paying for its own ability by leaving the
battlefield for exile.

`cost_component_for_phrase` reads "Exile this card" and `Game.activation_cost`
reads the printed-name form ("Exile The Stone Brain"), but "exile this
<type>" (CR 700.7's self-reference by type word) was left as an unbuildable
cost, so Relic of Progenitus's second ability could never be activated.
Found by the behavioural sweep; Brittle Effigy (not in any deck, a
different ability and an extra {T}) proves the reader rather than the card.

Rules verified with `mise run rules:find`: CR 602.2b, CR 118.3, CR 406.2.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_relic_of_progenitus_exiles_itself_to_exile_all_graveyards():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Relic of Progenitus", "Island"],
            graveyard=["Grizzly Bears"],
            library=["Forest"],
        )
        .player("bob", graveyard=["Lightning Bolt"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    relic = scenario.find("Relic of Progenitus", Zone.BATTLEFIELD, "alice")

    scenario.activate(relic, *scenario.untapped_sources("Island"), index=1)

    assert relic.zone is Zone.EXILE, "the cost is paid on activation (CR 602.2b)"
    scenario.resolve_top()
    assert scenario.player("alice").graveyard == []
    assert scenario.player("bob").graveyard == []
    assert len(scenario.player("alice").hand) == 1


def test_brittle_effigy_exiles_itself_and_its_target():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Brittle Effigy"] + ["Wastes"] * 4)
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    effigy = scenario.find("Brittle Effigy", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.activate(effigy, *scenario.untapped_sources(*["Wastes"] * 4), targets=[bears])
    scenario.resolve_top()

    assert effigy.zone is Zone.EXILE
    assert bears.zone is Zone.EXILE
