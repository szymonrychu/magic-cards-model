""""Exile the top two cards of your library. Until the end of your next turn,
you may play those cards." - Wrenn's Resolve and Reckless Impulse print the
identical sentence (verified with `resolve_cards` in this session, against
`tests/fixtures/cards/wrenn_s_resolve.json` and `.../reckless_impulse.json`).

This is a *longer* sibling of `test_play_from_exile.py`'s "until end of turn"
grant: `PlayPermission.expires_end_of_next_turn` survives the casting turn's
own cleanup, survives every turn that is not the caster's own next one, and
only actually drops at the cleanup of the caster's own next turn.

Every rule cited here was looked up with `knowledge_search(type="rules")` in
the session that wrote this file:

- **CR 601.3** - "A player can begin to cast a spell only if a rule or effect
  allows that player to cast it."
- **CR 601.1a** / **CR 701.18b** - "playing a card" covers a land found among
  the exiled cards, unlike Ugin's/Ragavan's own "cast" grant.
- **CR 514.2** - "all 'until end of turn' and 'this turn' effects end" in the
  cleanup step - the duration this file's own grant outlives by one more
  turn cycle, since the card says "until the end of **your next turn**", not
  "until end of turn".
- **CR 400.7** - a card that leaves exile and returns is a new object; the
  permission does not follow it.
- **CR 406.1** - exile is a holding zone with no rule that empties it, which
  is why a card nobody got around to playing just stays there.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import PlayAction
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board(*, library: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Wrenn's Resolve"],
            battlefield=["Mountain", "Mountain", "Mountain"],
            library=library if library is not None else ["Lightning Bolt", "Forest", "Island"],
        )
        .player("bob", library=["Island", "Island"])
    )


def _cast_resolve(scenario, *, card_name: str = "Wrenn's Resolve"):
    """Cast the impulse-draw spell ({1}{R}) and resolve it; returns the
    exiled cards."""
    mountains = scenario.untapped_sources("Mountain", "Mountain")
    before = {state.id for state in scenario.game.exile}
    spell = scenario.cast_and_resolve(card_name, *mountains)
    exiled = [state for state in scenario.game.exile if state.id not in before]
    return spell, exiled


def _end_turn(scenario):
    """Run the active player's cleanup (CR 514.1, 514.2) and cross into the
    next turn - `manual_turn_based_actions()` never runs `Game.cleanup_step`
    on its own, and `Scenario.start_at` alone never moves past the step it
    was aimed at, so both calls are needed to actually reach the next
    player's turn."""
    scenario.start_at(Step.CLEANUP)
    scenario.turn_based_actions()
    scenario.advance()


def test_the_top_two_cards_are_exiled_and_each_gets_a_play_permission():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    spell, exiled = _cast_resolve(scenario)

    assert spell.zone is Zone.GRAVEYARD
    assert sorted(state.name for state in exiled) == ["Forest", "Lightning Bolt"]
    assert [state.name for state in scenario.player("alice").library] == ["Island"]
    for state in exiled:
        permission = scenario.game.play_permission_for(state, "alice")
        assert permission is not None
        assert permission.action is PlayAction.PLAY
        assert permission.pays_mana_cost is True
        assert permission.source_name == "Wrenn's Resolve"


def test_a_land_among_the_exiled_cards_can_be_played_as_a_land():
    """CR 701.18b: "play" reaches the land drop, unlike Ugin's/Ragavan's own
    "cast"-only grant (`test_play_from_exile.py`)."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _, exiled = _cast_resolve(scenario)
    forest = next(state for state in exiled if state.name == "Forest")

    scenario.play_land("Forest", from_zone=Zone.EXILE)

    assert forest.zone is Zone.BATTLEFIELD
    assert scenario.game.lands_played["alice"] == 1


def test_a_spell_among_the_exiled_cards_is_cast_for_its_own_mana_cost():
    """Neither printing says "without paying their mana costs" - unlike
    Ugin's ultimate, the exiled Bolt still owes {R}."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _, exiled = _cast_resolve(scenario)
    bolt = next(state for state in exiled if state.name == "Lightning Bolt")

    casting = scenario.cast("Lightning Bolt", from_zone=Zone.EXILE)
    casting.use_permission()
    casting.choose_targets(["bob"])
    assert str(casting.total_cost.mana) == "{R}"

    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.pay_with(casting.begin_paying(), mountain)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bolt.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 17


def test_the_permission_survives_the_casting_turns_own_cleanup():
    """The whole point of "your next turn" rather than plain "this turn":
    the permission is still good after alice's own turn ends."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _, exiled = _cast_resolve(scenario)
    forest = next(state for state in exiled if state.name == "Forest")

    scenario.start_at(Step.CLEANUP)
    scenario.turn_based_actions()

    assert forest.zone is Zone.EXILE
    assert scenario.game.play_permission_for(forest, "alice") is not None


def test_the_permission_survives_the_opponents_intervening_turn():
    """Bob's turn happens between alice casting this and alice's own next
    turn - the permission has to still be good throughout it."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _, exiled = _cast_resolve(scenario)
    forest = next(state for state in exiled if state.name == "Forest")

    _end_turn(scenario)  # alice's casting turn ends; bob's begins
    assert scenario.turn.active_player == "bob"

    scenario.start_at(Step.POSTCOMBAT_MAIN)
    assert forest.zone is Zone.EXILE
    assert scenario.game.play_permission_for(forest, "alice") is not None

    _end_turn(scenario)  # bob's turn ends; alice's begins

    assert forest.zone is Zone.EXILE
    assert scenario.game.play_permission_for(forest, "alice") is not None, (
        "still alice's next turn to come - bob's own turn does not end it"
    )


def test_the_permission_is_still_good_during_alices_own_next_turn():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _, exiled = _cast_resolve(scenario)
    forest = next(state for state in exiled if state.name == "Forest")

    _end_turn(scenario)  # alice's casting turn ends; bob's begins
    _end_turn(scenario)  # bob's turn ends; alice's own next turn begins
    assert scenario.turn.active_player == "alice"

    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert forest.zone is Zone.EXILE
    assert scenario.game.play_permission_for(forest, "alice") is not None

    scenario.play_land("Forest", from_zone=Zone.EXILE)
    assert forest.zone is Zone.BATTLEFIELD


def test_the_permission_expires_at_the_cleanup_of_alices_own_next_turn():
    """CR 514.2, on the later of the two turns this grant reaches."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _, exiled = _cast_resolve(scenario)
    forest = next(state for state in exiled if state.name == "Forest")

    _end_turn(scenario)  # alice's casting turn ends; bob's begins
    _end_turn(scenario)  # bob's turn ends; alice's own next turn begins
    assert scenario.turn.active_player == "alice"
    scenario.start_at(Step.CLEANUP)  # alice's own next turn ends
    scenario.turn_based_actions()

    assert forest.zone is Zone.EXILE
    assert scenario.game.play_permission_for(forest, "alice") is None


def test_an_unused_exiled_card_stays_exiled_forever_once_the_grant_expires():
    """No "put on the bottom" instruction is printed here (unlike cascade's
    own CR 702.85a), so CR 406.1 leaves the card sitting in exile."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _, exiled = _cast_resolve(scenario)
    bolt = next(state for state in exiled if state.name == "Lightning Bolt")

    for _ in range(3):
        _end_turn(scenario)

    assert bolt.zone is Zone.EXILE
    assert scenario.game.play_permission_for(bolt, "alice") is None


def test_reckless_impulse_prints_the_identical_grant():
    """Both cards share one parser; this confirms the second printing is not
    accidentally still silent."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Reckless Impulse"],
            battlefield=["Mountain", "Mountain", "Mountain"],
            library=["Lightning Bolt", "Forest"],
        )
        .player("bob", library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    spell, exiled = _cast_resolve(scenario, card_name="Reckless Impulse")

    assert spell.zone is Zone.GRAVEYARD
    assert sorted(state.name for state in exiled) == ["Forest", "Lightning Bolt"]
    for state in exiled:
        assert scenario.game.play_permission_for(state, "alice") is not None
