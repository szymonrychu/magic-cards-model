""" "create a colorless Equipment artifact token named `<Name>` with
"`<ability>`" and equip `<cost>`[. When you do, attach it to target creature
you control.]" (CR 111.3's token text, CR 702.6a's equip, CR 603.12's
reflexive attach).

Iron Hills Blacksmith: "When this creature enters, create a colorless
Equipment artifact token named Axe with \"Equipped creature gets +1/+0\" and
equip {2}." (no attach - the token just sits there). Dain Ironfoot: the same
sentence, with "When you do, attach it to target creature you control."
riding after it.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import equip_activation, has_equip
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario, mana_from


def test_iron_hills_blacksmith_creates_a_named_equipment_token_unattached():
    scenario = (
        Scenario()
        .player("alice", hand=["Iron Hills Blacksmith"], battlefield=["Plains", "Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    before = {state.id for state in scenario.game.battlefield}

    sources = scenario.untapped_sources("Plains", "Plains")
    scenario.cast_and_resolve("Iron Hills Blacksmith", *sources)
    scenario.pass_until_resolved()

    created = [state for state in scenario.game.battlefield if state.id not in before]
    axe = next(state for state in created if state.name == "Axe")
    assert axe.attached_to is None
    assert "Equipment" in axe.subtypes
    assert has_equip(axe.card)
    assert axe.oracle_text.splitlines()[0] == "Equipped creature gets +1/+0."


def test_iron_hills_blacksmiths_axe_token_can_be_equipped():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Iron Hills Blacksmith"],
            battlefield=["Grizzly Bears", "Plains", "Plains", "Plains", "Plains"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    before = {state.id for state in scenario.game.battlefield}
    bears = scenario.creature("Grizzly Bears", "alice")

    sources = scenario.untapped_sources("Plains", "Plains")
    scenario.cast_and_resolve("Iron Hills Blacksmith", *sources)
    scenario.pass_until_resolved()

    created = [state for state in scenario.game.battlefield if state.id not in before]
    axe = next(state for state in created if state.name == "Axe")

    activation = equip_activation(scenario.game, axe, bears, "alice")
    payment = activation.begin_paying()
    for source in scenario.untapped_sources("Plains", "Plains", username="alice"):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    scenario.pass_until_resolved()

    assert axe.attached_to == bears.id
    assert scenario.game.power_of(bears) == 3, "the Axe's own +1/+0 applies"


def test_dain_ironfoot_creates_the_token_then_attaches_it_to_target_creature():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Dáin Ironfoot"],
            battlefield=["Grizzly Bears", "Mountain", "Mountain", "Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    scenario.cast_and_resolve("Dáin Ironfoot", *sources)
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()

    axe = scenario.find("Axe", Zone.BATTLEFIELD, "alice")
    assert axe.attached_to == bears.id


def test_blacksmiths_talent_creates_the_same_shaped_named_equipment_token():
    """Bloomburrow's own printing of the same named-Equipment-token
    template, proof the reader is not fitted to Iron Hills Blacksmith's or
    Dain Ironfoot's own wording (a different token name, cost, and bonus)."""
    scenario = (
        Scenario()
        .player("alice", hand=["Blacksmith's Talent"], battlefield=["Mountain", "Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    before = {state.id for state in scenario.game.battlefield}

    sources = scenario.untapped_sources("Mountain", "Mountain")
    scenario.cast_and_resolve("Blacksmith's Talent", *sources)
    scenario.pass_until_resolved()

    created = [state for state in scenario.game.battlefield if state.id not in before]
    sword = next(state for state in created if state.name == "Sword")
    assert has_equip(sword.card)
    assert sword.oracle_text.splitlines()[0] == "Equipped creature gets +1/+1."
