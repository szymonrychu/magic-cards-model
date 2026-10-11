"""Scenario: an Aura's or Equipment's trigger that untaps the object it is
attached to - "untap enchanted permanent" / "untap equipped creature".

Volition Reins: "When this Aura enters, if enchanted permanent is tapped,
untap it." The intervening "if" names the enchanted permanent, so its "it" is
that permanent (`abilities._resolve_attached_object_pronoun`), never the Aura.
CR 303.4b: the enchanted object is the one the Aura is attached to; CR
701.26b: untap turns a permanent upright, and only a tapped one can untap.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card
from tests.scenarios.harness import Scenario


def _board():
    scenario = (
        Scenario()
        .player("alice", hand=["Volition Reins"], battlefield=["Island"] * 6)
        .player("bob", battlefield=["Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_volition_reins_clauses_are_handled():
    support = card_support(card("Volition Reins"))
    assert [c for c in support.clauses if c.status != "handled"] == []


def test_volition_reins_untaps_the_tapped_permanent_it_steals():
    scenario = _board()
    angel = scenario.find("Serra Angel", Zone.BATTLEFIELD, "bob")
    angel.tapped = True
    reins = scenario.cast_and_resolve(
        "Volition Reins", *scenario.untapped_sources(*["Island"] * 6), targets=[angel]
    )
    scenario.pass_until_resolved()
    assert reins.attached_to == angel.id
    assert scenario.game.controller_of(angel).username == "alice"
    assert not angel.tapped
    assert not reins.tapped, "the Aura itself is not what untaps"


def test_volition_reins_on_an_untapped_permanent_does_nothing_more():
    scenario = _board()
    angel = scenario.find("Serra Angel", Zone.BATTLEFIELD, "bob")
    scenario.cast_and_resolve(
        "Volition Reins", *scenario.untapped_sources(*["Island"] * 6), targets=[angel]
    )
    scenario.pass_until_resolved()
    assert scenario.game.controller_of(angel).username == "alice"
    assert not angel.tapped
