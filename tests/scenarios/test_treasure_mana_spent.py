""" "If mana from a Treasure was spent to cast it" (CR 601.2h's spent mana,
CR 106.3's source of mana): mana keeps whether its source was a Treasure,
the payment records how much of it paid the cost, and the cast record
answers the intervening if (CR 603.4).

Smaug, Wicked Worm is the reported card ("Whenever you cast a spell, if mana
from a Treasure was spent to cast it, you draw a card and lose 1 life.");
Hired Hexblade is the second printing ("When this creature enters, if mana
from a Treasure was spent to cast it, you draw a card and you lose 1 life.").
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Color
from magic_cards_model.models.token import create_predefined_tokens
from tests.scenarios.harness import Scenario


def _resolve_all(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _treasure_mana(scenario, color: Color, username: str = "alice") -> None:
    (treasure,) = create_predefined_tokens(scenario.game, "Treasure", username)
    _resolve_all(scenario)
    scenario.game.activate_ability(treasure, 0, username, color=color)


def _smaug_board(*battlefield: str):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Smaug, Wicked Worm", *battlefield],
            library=["Island"] * 5,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_a_spell_paid_with_treasure_mana_draws_and_loses_life():
    scenario = _smaug_board()
    _treasure_mana(scenario, Color.RED)
    hand = len(scenario.player("alice").hand)
    scenario.cast_onto_stack("Lightning Bolt", targets=["bob"])
    _resolve_all(scenario)

    assert len(scenario.player("alice").hand) == hand - 1 + 1
    assert scenario.player("alice").life == 19
    assert not scenario.game.intervening_if_notices


def test_a_spell_paid_with_land_mana_does_not_trigger():
    scenario = _smaug_board("Mountain")
    scenario.cast_onto_stack(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == ["Lightning Bolt"]
    assert not scenario.game.intervening_if_notices


def test_floating_treasure_mana_pays_before_an_untapped_land():
    """The pool's mana pays first; the Mountain stays untapped, and the cast
    record says one mana from a Treasure paid the Bolt."""
    scenario = _smaug_board("Mountain")
    _treasure_mana(scenario, Color.RED)
    scenario.cast_onto_stack("Lightning Bolt", targets=["bob"])
    bolt = next(
        item for item in scenario.game.stack if getattr(item, "name", "") == "Lightning Bolt"
    )
    record = scenario.game.cast_record(bolt)
    assert record.treasure_mana_spent == 1
    assert scenario.player("alice").mana_pool.is_empty
    assert scenario.untapped_sources("Mountain")


def test_the_pool_forgets_treasure_mana_when_it_empties():
    scenario = _smaug_board()
    _treasure_mana(scenario, Color.RED)
    pool = scenario.player("alice").mana_pool
    assert pool.treasure == {Color.RED: 1}
    pool.empty()
    assert pool.treasure == {}


def test_hired_hexblade_reads_the_same_condition_on_its_enters_trigger():
    scenario = (
        Scenario()
        .player("alice", hand=["Hired Hexblade"], battlefield=["Swamp"], library=["Island"] * 5)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _treasure_mana(scenario, Color.BLACK)
    hand = len(scenario.player("alice").hand)
    scenario.cast_onto_stack("Hired Hexblade", *scenario.untapped_sources("Swamp"))
    _resolve_all(scenario)

    assert len(scenario.player("alice").hand) == hand - 1 + 1
    assert scenario.player("alice").life == 19
