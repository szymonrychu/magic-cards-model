"""Way of the Paradox: "When Way of the Paradox enters, empower Jace 5.
Whenever you activate a loyalty ability, you gain 1 life. You may play an
additional land this turn."

Two things new on this branch, both read straight off the printed sentence:

- **`Game.extra_land_plays`/`Game.grant_extra_land_play`** - CR 305.2's
  allowance increase granted by a *resolving* trigger rather than a
  permanent's own static ability, feeding `Game.land_allowance` for the rest
  of the turn it resolved on. `machines/effects._ADDITIONAL_LAND_PLAY_RE` is
  read ahead of the generic "you may" strip in `_parse_optional_player_clause`
  because the grant itself is unconditional - only the *later* land play this
  turn is optional (CR 305.1), not accepting the grant.
- The trigger condition itself, "whenever you activate a loyalty ability", is
  `machines/abilities.py`'s existing reader (CR 606, CR 603.2) - nothing new
  about it - composed here with the life-gain and land-grant clauses the way
  any two-sentence triggered ability's effect already composes (CR 608.2c).

CR numbers looked up with `knowledge_search(type="rules")` in this session:
CR 305.2, CR 305.2a, CR 119.3, CR 606.2, CR 603.2.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_activating_a_loyalty_ability_gains_life_and_grants_an_extra_land_play():
    scenario = (
        Scenario()
        .player(
            "alice",
            life=20,
            hand=["Way of the Paradox", "Forest", "Forest"],
            library=["Island"] * 5,
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.put_onto_battlefield("Way of the Paradox")
    scenario.pass_until_resolved()  # "When Way of the Paradox enters, empower Jace 5."

    jace = scenario.find("Jace", Zone.BATTLEFIELD, "alice")
    assert jace.loyalty == 5

    assert scenario.game.land_allowance("alice") == 1, "CR 305.2's ordinary one, still"

    scenario.activate(jace, index=1)  # "-3: Draw a card."
    while scenario.game.stack:
        scenario.resolve_top()

    assert scenario.player("alice").life == 21, "CR 119.3: the triggered gain landed"
    assert scenario.game.land_allowance("alice") == 2, "the additional land play landed too"

    # Prove the number is not merely bookkeeping: alice can actually play a
    # second land this turn where CR 305.1 would otherwise stop her at one.
    first = scenario.play_land("Forest")
    second = scenario.play_land("Forest")
    assert first.zone is Zone.BATTLEFIELD
    assert second.zone is Zone.BATTLEFIELD


def test_the_extra_land_play_does_not_survive_into_the_next_turn():
    """CR 305.2's increase is granted "this turn" only - `Game.advance`
    resets `extra_land_plays` the moment the turn actually changes
    (`turns_taken` ticks over), the same reset `lands_played` itself gets."""
    scenario = (
        Scenario()
        .player("alice", life=20, hand=["Way of the Paradox"], library=["Island"] * 5)
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.put_onto_battlefield("Way of the Paradox")
    scenario.pass_until_resolved()
    jace = scenario.find("Jace", Zone.BATTLEFIELD, "alice")

    scenario.activate(jace, index=1)  # "-3: Draw a card."
    while scenario.game.stack:
        scenario.resolve_top()
    assert scenario.game.land_allowance("alice") == 2

    while scenario.turn.turn_number == 1 or scenario.turn.active_player != "alice":
        scenario.advance()

    assert scenario.game.land_allowance("alice") == 1, "CR 305.2's grant was only for that turn"


def test_two_activations_in_one_turn_grant_two_additional_land_plays():
    """CR 305.2: each activation's trigger adds one more land play, so the
    allowance is cumulative, and each gains 1 life. The second activation is a
    different planeswalker's (CR 606.3 allows one per permanent per turn)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            life=20,
            hand=["Way of the Paradox", "Forest", "Forest", "Forest"],
            battlefield=["Ajani Unrelenting"],
            library=["Island"] * 5,
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Way of the Paradox")
    scenario.pass_until_resolved()
    jace = scenario.find("Jace", Zone.BATTLEFIELD, "alice")
    ajani = scenario.find("Ajani Unrelenting", Zone.BATTLEFIELD, "alice")

    scenario.activate(jace, index=1)  # [-3]
    while scenario.game.stack:
        scenario.resolve_top()
    scenario.activate(ajani, index=0)  # +1
    while scenario.game.stack:
        scenario.resolve_top()

    assert scenario.player("alice").life == 22
    assert scenario.game.land_allowance("alice") == 3
    lands = [scenario.play_land("Forest") for _ in range(3)]
    assert all(land.zone is Zone.BATTLEFIELD for land in lands)
