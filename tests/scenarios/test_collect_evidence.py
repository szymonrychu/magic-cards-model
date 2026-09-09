"""Collect evidence: CR 701.59a, crediting the sweep for work already done.

`machines/cost.py`'s `ComponentKind.COLLECT_EVIDENCE` (`collect_evidence_
cost`, matched by `_PHRASE_COLLECT_EVIDENCE`) already reads "Collect
evidence N" as a real, payable cost component - reached generically through
`cost_component_for_phrase`, the same `CostKind.OTHER` fill-in every
unclassified activated-ability cost sentence goes through
(`Game.activation_cost`). The only real gap was `machines/keywords.
executes()` never crediting the keyword. Proved here on Forensic
Researcher - a plain activated ability's own cost, not bundled inside a
bestow cost the way Detective's Phoenix prints it - outside the deck pool
and outside this wave's brief.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_forensic_researcher_pays_collect_evidence_from_the_graveyard():
    """Forensic Researcher: "{T}, Collect evidence 3: Tap target creature
    you don't control."
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            graveyard=["Lightning Bolt", "Grizzly Bears"],
            battlefield=["Forensic Researcher"],
        )
        .player("bob", battlefield=["Memnite"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    researcher = scenario.creature("Forensic Researcher", "alice")
    memnite = scenario.creature("Memnite", "bob")
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")

    scenario.activate(researcher, index=1, username="alice", targets=[memnite])
    scenario.pass_until_resolved()

    assert bolt.zone is Zone.EXILE
    assert bears.zone is Zone.EXILE
    assert memnite.tapped


def test_collect_evidence_refuses_a_graveyard_that_cannot_reach_the_total():
    """CR 701.59b: unable to reach the total mana value, the choice to
    collect evidence is refused rather than silently allowed for less.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            graveyard=["Lightning Bolt"],
            battlefield=["Forensic Researcher"],
        )
        .player("bob", battlefield=["Memnite"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    researcher = scenario.creature("Forensic Researcher", "alice")
    memnite = scenario.creature("Memnite", "bob")

    with pytest.raises(ValueError):
        scenario.activate(researcher, index=1, username="alice", targets=[memnite])
