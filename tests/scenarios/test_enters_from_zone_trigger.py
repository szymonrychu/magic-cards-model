"""An enters trigger narrowed by where the permanent came from (CR 603.6a).

"When this creature enters from your graveyard" (Phyrexian Dragon Engine) and "... from your hand"
(Thousand-Faced Shadow) only match an enters event whose permanent moved
from that zone; the same permanent entering any other way does not trigger.
The origin is read off the enters event (`GameEvent.origin_zone`).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_reanimated_from_your_graveyard_the_trigger_fires():
    """Phyrexian Dragon Engine returned by Unearth ("Return target creature
    card with mana value 3 or less from your graveyard to the battlefield"):
    it entered from its owner's graveyard, so its trigger goes on the stack."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Unearth", "Opt"],
            graveyard=["Phyrexian Dragon Engine"],
            battlefield=["Swamp"],
            library=["Island"] * 5,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    target = scenario.find("Phyrexian Dragon Engine", Zone.GRAVEYARD, "alice")
    scenario.cast_and_resolve("Unearth", *scenario.untapped_sources("Swamp"), targets=[target])

    assert target.zone is Zone.BATTLEFIELD
    assert [o.source_name for o in scenario.game.stack] == ["Phyrexian Dragon Engine"]


def test_put_onto_the_battlefield_from_hand_the_graveyard_trigger_does_not_fire():
    """Phyrexian Dragon Engine's "enters from your graveyard": put onto the
    battlefield straight from hand, nothing asks to discard."""
    scenario = (
        Scenario()
        .player("alice", hand=["Phyrexian Dragon Engine", "Opt"], library=["Island"] * 5)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    engine = scenario.find("Phyrexian Dragon Engine", Zone.HAND, "alice")

    scenario.game.put_onto_battlefield(engine, "alice")

    assert engine.zone is Zone.BATTLEFIELD
    assert not scenario.game.stack
    assert scenario.find("Opt", Zone.HAND, "alice").zone is Zone.HAND


def test_thousand_faced_shadow_cast_from_hand_is_not_attacking_so_nothing_is_copied():
    """CR 603.4: "if it's attacking" - cast in a main phase it enters from
    hand but not attacking, so the trigger never fires."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Thousand-Faced Shadow"],
            battlefield=["Grizzly Bears", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Island", username="alice")
    shadow = scenario.cast_and_resolve("Thousand-Faced Shadow", *sources)

    assert shadow.zone is Zone.BATTLEFIELD
    assert not scenario.game.stack
    assert [s.name for s in scenario.game.permanents_controlled_by("alice")].count(
        "Grizzly Bears"
    ) == 1
