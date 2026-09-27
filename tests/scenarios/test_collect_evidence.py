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


# --------------------------------------------------------------------------
# Deadly Cover-Up: "As an additional cost to cast this spell, you may
# collect evidence 6. Destroy all creatures. If evidence was collected,
# exile a card from an opponent's graveyard. Then search its owner's
# graveyard, hand, and library for any number of cards with that name and
# exile them. That player shuffles, then draws a card for each card exiled
# from their hand this way." A mass destruction (already general) feeding a
# new conditional graveyard-hate reader
# (`_parse_mass_destroy_then_conditional_graveyard_hate_clause`) that reuses
# `_search_and_exile_matching_name` - the same search-exile-shuffle-draw The
# Stone Brain's and Surgical Extraction's own readers already established.
# --------------------------------------------------------------------------


def test_without_evidence_only_the_creatures_are_destroyed():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Deadly Cover-Up"],
            battlefield=["Swamp"] * 5,
            graveyard=["Lightning Bolt"],
        )
        .player(
            "bob",
            battlefield=["Grizzly Bears"],
            graveyard=["Lightning Bolt", "Lightning Bolt"],
            hand=["Lightning Bolt"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources(*(["Swamp"] * 5))

    scenario.cast_and_resolve("Deadly Cover-Up", *sources)

    assert bears.zone is Zone.GRAVEYARD
    bob = scenario.player("bob")
    assert len(bob.hand) == 1, "no evidence collected: no graveyard hate, no draw"
    assert len([c for c in bob.graveyard if c.name == "Lightning Bolt"]) == 2


def test_evidence_collected_exiles_every_bolt_and_draws_for_the_hand_one():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Deadly Cover-Up"],
            battlefield=["Swamp"] * 5,
            graveyard=["Craw Wurm"],
        )
        .player(
            "bob",
            battlefield=["Grizzly Bears"],
            graveyard=["Lightning Bolt", "Lightning Bolt"],
            hand=["Lightning Bolt"],
            library=["Lightning Bolt", "Plains", "Plains"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    craw_wurm = scenario.find("Craw Wurm", Zone.GRAVEYARD, "alice")
    graveyard_bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "bob")
    sources = scenario.untapped_sources(*(["Swamp"] * 5))
    bob_hand_before = scenario.player("bob").hand[0]

    casting = scenario.cast("Deadly Cover-Up")
    casting.collect_evidence([craw_wurm])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.will_choose_cards(graveyard_bolt, source="Deadly Cover-Up")
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    bob = scenario.player("bob")
    assert bears.zone is Zone.GRAVEYARD, "still destroyed regardless of evidence"
    assert not any(c.name == "Lightning Bolt" for c in bob.graveyard)
    assert not any(c.name == "Lightning Bolt" for c in bob.library)
    assert bob_hand_before.zone is Zone.EXILE, "the hand copy was exiled too"
    assert len([c for c in bob.hand if c.name != "Lightning Bolt"]) == 1, (
        "drew one card for the single card exiled from hand"
    )
    assert not any(c.name == "Lightning Bolt" for c in bob.hand)
