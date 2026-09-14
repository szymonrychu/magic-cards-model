"""A self-sacrifice gated on how the permanent arrived: "sacrifice it unless
it escaped" (CR 702.138b, CR 701.21a).

CR 702.138b: "A spell or permanent 'escaped' if that spell or the spell that
became that permanent as it resolved was cast from a graveyard with an escape
ability." So "unless it escaped" is false only for the permanent a spell cast
with escape became. A hard-cast Titan and one put onto the battlefield
without being cast at all both did not escape, and both are sacrificed.

CR 113.7a: "Once activated or triggered, an ability exists on the stack
independently of its source." The Titan's second enters trigger still
resolves when the first has already sacrificed it.

Every CR number here was read with `mise run rules:find` in the session that
wrote this file: 702.138a, 702.138b, 701.21a, 113.7a. Uro, Titan of Nature's
Wrath is the reported card; Kroxa, Titan of Death's Hunger (off-pool, added
with `scripts/add_card.py`) prints the same sentence in another colour pair
with another escape cost.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import PlayedScenario, Scenario

URO = "Uro, Titan of Nature's Wrath"
KROXA = "Kroxa, Titan of Death's Hunger"


def board(**alice) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", library=["Lightning Bolt"] * 5, **alice)
        .player("bob", library=["Island"] * 5, hand=["Island", "Island"])
    )


def resolve_stack(scenario: PlayedScenario) -> None:
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()


def escape(scenario: PlayedScenario, name: str, *lands: str) -> None:
    fuel = [card for card in scenario.player("alice").graveyard if card.name != name]
    casting = scenario.cast(name, from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Escape", choosing=fuel[:5])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*lands))
    scenario.put_on_stack(casting)
    resolve_stack(scenario)


def test_a_hard_cast_uro_is_sacrificed_and_its_other_trigger_still_resolves():
    scenario = board(hand=[URO], battlefield=["Forest", "Island", "Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    hand_before = len(alice.hand) - 1

    scenario.cast_onto_stack(URO, *scenario.untapped_sources("Forest", "Island", "Island"))
    resolve_stack(scenario)

    uro = scenario.find(URO, Zone.GRAVEYARD, "alice")
    assert uro.zone is Zone.GRAVEYARD
    assert alice.life == 23
    assert len(alice.hand) == hand_before + 1


def test_an_escaped_uro_stays_and_its_other_trigger_still_resolves():
    scenario = board(
        graveyard=[URO, *["Mishra's Bauble"] * 5],
        battlefield=["Forest", "Forest", "Island", "Island"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")

    escape(scenario, URO, "Forest", "Forest", "Island", "Island")

    assert scenario.find(URO, Zone.BATTLEFIELD, "alice").zone is Zone.BATTLEFIELD
    assert alice.life == 23
    assert len(alice.hand) == 1


def test_an_uro_put_onto_the_battlefield_without_being_cast_did_not_escape():
    """CR 702.138b: only a spell cast from a graveyard with escape escaped.
    A permanent that was never a spell at all did not."""
    scenario = board(hand=[URO]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    uro = scenario.put_onto_battlefield(URO)
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == [f"{URO}'s triggered ability"] * 2
    resolve_stack(scenario)

    assert uro.zone is Zone.GRAVEYARD


def test_a_hard_cast_kroxa_is_sacrificed():
    """Off-pool generality: the same sentence on another Titan."""
    scenario = board(hand=[KROXA], battlefield=["Swamp", "Mountain"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_onto_stack(KROXA, *scenario.untapped_sources("Swamp", "Mountain"))
    resolve_stack(scenario)

    assert scenario.find(KROXA, Zone.GRAVEYARD, "alice").zone is Zone.GRAVEYARD


def test_an_escaped_kroxa_stays():
    scenario = board(
        graveyard=[KROXA, *["Mishra's Bauble"] * 5],
        battlefield=["Swamp", "Swamp", "Mountain", "Mountain"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    escape(scenario, KROXA, "Swamp", "Swamp", "Mountain", "Mountain")

    assert scenario.find(KROXA, Zone.BATTLEFIELD, "alice").zone is Zone.BATTLEFIELD
