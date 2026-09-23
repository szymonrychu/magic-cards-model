"""A mandatory discard as the cost of its own consequence: "Discard a card. If
you do, `<effect>`." - no "you may", so there is no question to decline, only
a hand that may be empty.

Every CR number below was read whole with `mise run rules:find` in the session
that wrote this file:

- **CR 118.12** - "[Do something]. If [a player] [does ...], [effect]." The
  action is a cost paid as the ability resolves, and "If you do" checks
  whether the player "started to pay a mandatory cost": a player with no card
  in hand cannot start, so nothing is drawn.
- **CR 701.9b** - the discarding player chooses which card.
- **CR 603.3c** - a modal triggered ability's mode is announced as it goes on
  the stack.
- **CR 604.3** - Territorial Kavu's domain line is a characteristic-defining
  ability; **CR 305.6** names the five basic land types it counts.

Territorial Kavu's attack trigger ("choose one - Discard a card. If you do,
draw a card. / Exile up to one target card from a graveyard.") is the reported
card. Shadow of the Goblin's "Unreliable Visions - At the beginning of your
first main phase, discard a card. If you do, draw a card." is the proof
printing: Standard-legal, not in any api deck, a flavor-word labelled trigger
outside any modal list.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

RUMMAGE = "Discard a card. If you do, draw a card."
EXILE = "Exile up to one target card from a graveyard."
BASICS = ["Mountain", "Forest", "Island"]


def kavu_board(hand: list[str], bob_graveyard: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=hand,
            battlefield=["Territorial Kavu", *BASICS],
            library=["Plains", "Swamp"],
        )
        .player("bob", graveyard=bob_graveyard or [])
        .build()
    )


def attack_and_resolve(scenario) -> None:
    kavu = scenario.creature("Territorial Kavu", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(kavu, defending="bob")
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()


def test_the_rummage_mode_discards_then_draws():
    scenario = kavu_board(["Lightning Bolt"])
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    scenario.will_choose_mode(RUMMAGE, username="alice")
    scenario.will_discard(bolt)

    attack_and_resolve(scenario)

    assert bolt.zone is Zone.GRAVEYARD
    assert [state.name for state in scenario.player("alice").hand] == ["Plains"]


def test_the_rummage_mode_with_an_empty_hand_draws_nothing():
    """CR 118.12: an empty hand never starts to pay the discard."""
    scenario = kavu_board([])
    scenario.will_choose_mode(RUMMAGE, username="alice")

    attack_and_resolve(scenario)

    assert scenario.player("alice").hand == []
    assert len(scenario.player("alice").library) == 2


def test_the_rummage_mode_asks_no_may_question():
    """Mandatory: no "you may" is put to the player, only which card."""
    scenario = kavu_board(["Lightning Bolt", "Shock"])
    shock = scenario.find("Shock", Zone.HAND, "alice")
    scenario.will_choose_mode(RUMMAGE, username="alice")
    scenario.will_discard(shock)

    attack_and_resolve(scenario)

    kinds = {d.kind.value for d in scenario.questions_asked() if d.source == "Territorial Kavu"}
    assert "may" not in kinds
    assert shock.zone is Zone.GRAVEYARD
    assert sorted(s.name for s in scenario.player("alice").hand) == ["Lightning Bolt", "Plains"]


def test_the_exile_mode_exiles_a_card_from_an_opponents_graveyard():
    scenario = kavu_board([], bob_graveyard=["Lightning Bolt"])
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "bob")
    scenario.will_choose_mode(EXILE, username="alice")
    scenario.will_choose_targets(bolt, username="alice")

    attack_and_resolve(scenario)

    assert bolt.zone is Zone.EXILE
    assert scenario.player("alice").hand == []


def test_the_exile_mode_with_no_target_does_nothing():
    """ "Up to one" (CR 115.6) - zero targets is a legal announcement."""
    scenario = kavu_board(["Lightning Bolt"])
    scenario.will_choose_mode(EXILE, username="alice")

    attack_and_resolve(scenario)

    assert [state.name for state in scenario.player("alice").hand] == ["Lightning Bolt"]


def test_domain_sets_power_and_toughness_to_the_basic_land_types():
    """CR 604.3 / CR 305.6: three basic land types, a 3/3."""
    scenario = kavu_board([])
    kavu = scenario.creature("Territorial Kavu", "alice")

    characteristics = scenario.game.characteristics_of(kavu)

    assert (characteristics.power, characteristics.toughness) == (3, 3)


def test_domain_counts_types_not_lands():
    """Two Mountains are one basic land type."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Territorial Kavu", "Mountain", "Mountain"])
        .player("bob")
        .build()
    )
    kavu = scenario.creature("Territorial Kavu", "alice")

    characteristics = scenario.game.characteristics_of(kavu)

    assert (characteristics.power, characteristics.toughness) == (1, 1)


# -- proof printing: Shadow of the Goblin -------------------------------------


def goblin_board(hand: list[str]) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=hand,
            battlefield=["Shadow of the Goblin"],
            library=["Plains", "Swamp", "Island"],
        )
        .player("bob", library=["Plains"] * 3)
        .build()
    )


def enter_first_main(scenario) -> None:
    """Move from the draw step into the precombat main phase. `start_at` moves
    the step pointer without running the draw step's own draw (CR 504.1), so
    the hand is exactly what the scenario staged."""
    scenario.start_at(Step.DRAW)
    scenario.advance()
    assert scenario.step is Step.PRECOMBAT_MAIN
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()


def test_shadow_of_the_goblin_rummages_at_the_first_main_phase():
    scenario = goblin_board(["Lightning Bolt"])
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    scenario.will_discard(bolt)

    enter_first_main(scenario)

    assert bolt.zone is Zone.GRAVEYARD
    assert [state.name for state in scenario.player("alice").hand] == ["Plains"]


def test_shadow_of_the_goblin_with_an_empty_hand_draws_nothing():
    """CR 118.12: nothing to discard, so the draw never happens."""
    scenario = goblin_board([])

    enter_first_main(scenario)

    alice = scenario.player("alice")
    assert alice.hand == []
    assert alice.graveyard == []
    assert len(alice.library) == 3
