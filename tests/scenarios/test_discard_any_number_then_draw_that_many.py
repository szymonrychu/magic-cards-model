""" "..., discard any number of cards, then draw that many cards." - Cavalier
of Flame's own enters-the-battlefield trigger, a CR 608.2c linked quantity:
the draw count is not printed, it is whatever "that many" - the number
actually discarded - turns out to be.

Every CR number below was read in full from `.rules/MagicCompRules.txt` with
`mise run rules:find` in the session that wrote this file.

- **CR 107.1c** - "If a rule or ability instructs a player to choose 'any
  number,' that player may choose any positive number or zero."
- **CR 701.9a** - "To discard a card, move it from its owner's hand to that
  player's graveyard."
- **CR 701.9b** - "By default, effects that cause a player to discard a card
  allow the affected player to choose which card to discard."
- **CR 121.1** - "A player draws a card by putting the top card of their
  library into their hand ... It may also be done as part of ... an effect of
  a spell or ability."
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

CAVALIER = "Cavalier of Flame"


def test_discards_the_chosen_cards_then_draws_that_many():
    """Discarding two of three other hand cards draws exactly two back -
    CR 701.9b's own choice, scripted so the test proves the *chosen* two
    moved, not merely that some discard and some draw happened.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[CAVALIER, "Mountain", "Forest", "Lightning Bolt"],
            library=["Swamp", "Island"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mountain = scenario.find("Mountain", Zone.HAND, "alice")
    forest = scenario.find("Forest", Zone.HAND, "alice")
    scenario.will_choose_cards(mountain, forest, username="alice", source=CAVALIER)

    scenario.put_onto_battlefield(CAVALIER)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert mountain.zone is Zone.GRAVEYARD, "CR 701.9a"
    assert forest.zone is Zone.GRAVEYARD
    hand_names = sorted(state.name for state in scenario.player("alice").hand)
    assert hand_names == ["Island", "Lightning Bolt", "Swamp"], "CR 121.1: two drawn back"


def test_discarding_zero_cards_draws_zero():
    """CR 107.1c: "any number" runs down to zero, and a declined discard
    draws nothing rather than being refused or defaulting to some other count.
    """
    scenario = (
        Scenario().player("alice", hand=[CAVALIER, "Mountain"], library=["Swamp", "Island"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose_cards(username="alice", source=CAVALIER)

    scenario.put_onto_battlefield(CAVALIER)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    hand_names = sorted(state.name for state in scenario.player("alice").hand)
    assert hand_names == ["Mountain"], "nothing discarded, nothing drawn"
