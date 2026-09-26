"""Secrets of Strixhaven's symmetric/edict/halving templates: a modal
"you may sacrifice. If you do, draw two" mode, a cast-trigger's conditional
self-copy plus a symmetric edict-and-drain body, an opponent-chosen
greatest-mana-value exile edict, and CR 107.1a's halving with a single
trailing rounding declaration - each proven on a second real printing too.

Rules verified with `mise run rules:find` in the session that wrote this
file:

- **CR 700.2a** - a modal spell's chosen modes each resolve as their own
  instruction, in the order printed.
- **CR 118.12** - "you may `<action>`. If you do, `<consequence>`."
- **CR 707.10** - a copy is put on the stack, not cast.
- **CR 701.21a** - sacrifice: the permanent's own controller chooses which.
- **CR 701.10a** - exile as an edict: the same choice, exiled instead.
- **CR 107.1a** - a fractional count must be rounded the printed direction.
- **CR 119.3** - an effect that causes a player to lose life.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board(alice: dict | None = None, bob: dict | None = None):
    alice_kwargs = {"library": ["Plains"] * 8, **(alice or {})}
    bob_kwargs = {"library": ["Plains"] * 8, **(bob or {})}
    scenario = Scenario().player("alice", **alice_kwargs).player("bob", **bob_kwargs).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


# -- Witherbloom Charm: a modal "you may sacrifice. If you do, draw two." --


def test_witherbloom_charm_sacrifice_mode_draws_two_when_taken():
    scenario = _board(
        {"hand": ["Witherbloom Charm"], "battlefield": ["Swamp", "Forest", "Mishra's Bauble"]}
    )
    alice = scenario.player("alice")
    bauble = scenario.creature("Mishra's Bauble", "alice")
    spell = scenario.find("Witherbloom Charm", Zone.HAND, "alice")
    scenario.will_take_the_may(True, username="alice")
    scenario.will_choose_cards(bauble, username="alice")
    scenario.game.cast(
        spell,
        "alice",
        modes=[1],
        mana_sources=scenario.untapped_sources("Swamp", "Forest", username="alice"),
    )
    scenario.pass_until_resolved()
    assert bauble.zone is Zone.GRAVEYARD
    assert len(alice.hand) == 2


def test_witherbloom_charm_sacrifice_mode_draws_nothing_when_declined():
    scenario = _board(
        {"hand": ["Witherbloom Charm"], "battlefield": ["Swamp", "Forest", "Mishra's Bauble"]}
    )
    alice = scenario.player("alice")
    bauble = scenario.creature("Mishra's Bauble", "alice")
    spell = scenario.find("Witherbloom Charm", Zone.HAND, "alice")
    scenario.will_take_the_may(False, username="alice")
    scenario.game.cast(
        spell,
        "alice",
        modes=[1],
        mana_sources=scenario.untapped_sources("Swamp", "Forest", username="alice"),
    )
    scenario.pass_until_resolved()
    assert bauble.zone is Zone.BATTLEFIELD
    assert len(alice.hand) == 0


def test_witherbloom_charm_life_gain_mode():
    scenario = _board({"hand": ["Witherbloom Charm"], "battlefield": ["Swamp", "Forest"]})
    alice = scenario.player("alice")
    before = alice.life
    spell = scenario.find("Witherbloom Charm", Zone.HAND, "alice")
    scenario.game.cast(
        spell,
        "alice",
        modes=[2],
        mana_sources=scenario.untapped_sources("Swamp", "Forest", username="alice"),
    )
    scenario.pass_until_resolved()
    assert alice.life == before + 5


def test_witherbloom_charm_destroy_mode_targets_a_cheap_nonland_permanent():
    scenario = _board(
        {"hand": ["Witherbloom Charm"], "battlefield": ["Swamp", "Forest"]},
        {"battlefield": ["Mishra's Bauble"]},
    )
    target = scenario.creature("Mishra's Bauble", "bob")
    spell = scenario.find("Witherbloom Charm", Zone.HAND, "alice")
    scenario.game.cast(
        spell,
        "alice",
        modes=[3],
        targets=[target],
        mana_sources=scenario.untapped_sources("Swamp", "Forest", username="alice"),
    )
    scenario.pass_until_resolved()
    assert target.zone is Zone.GRAVEYARD


# -- Social Snub: cast-trigger self-copy while controlling a creature, plus
# -- the symmetric edict-and-drain body --


def _resolve_everything(scenario) -> None:
    while scenario.game.stack or scenario.game.pending_triggers:
        scenario.pass_until_resolved()


def test_social_snub_no_copy_without_a_creature():
    scenario = _board(
        {"hand": ["Social Snub"], "battlefield": ["Swamp", "Plains", "Plains"]},
        {"battlefield": ["Grizzly Bears"]},
    )
    alice = scenario.player("alice")
    bob = scenario.player("bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    alice_before, bob_before = alice.life, bob.life
    scenario.cast_onto_stack("Social Snub", auto=True)
    scenario.will_choose_cards(bears, username="bob")
    _resolve_everything(scenario)
    assert bears.zone is Zone.GRAVEYARD
    assert alice.life == alice_before + 1
    assert bob.life == bob_before - 1


def test_social_snub_copies_itself_while_you_control_a_creature():
    """ "When you cast this spell while you control a creature, you may copy
    this spell." - CR 707.10's copy runs the symmetric edict-and-drain body a
    second time."""
    scenario = _board(
        {
            "hand": ["Social Snub"],
            "battlefield": ["Swamp", "Plains", "Plains", "Runeclaw Bear"],
        },
        {"battlefield": ["Grizzly Bears", "Elite Vanguard"]},
    )
    alice = scenario.player("alice")
    bob = scenario.player("bob")
    alice_before, bob_before = alice.life, bob.life
    scenario.will_take_the_may(True, username="alice")
    scenario.cast_onto_stack("Social Snub", auto=True)
    scenario.will_choose_cards(scenario.creature("Grizzly Bears", "bob"), username="bob")
    scenario.will_choose_cards(scenario.creature("Elite Vanguard", "bob"), username="bob")
    scenario.will_choose_cards(scenario.creature("Runeclaw Bear", "alice"), username="alice")
    _resolve_everything(scenario)
    # Two resolutions of "each opponent loses 1 life and you gain 1 life."
    assert alice.life == alice_before + 2
    assert bob.life == bob_before - 2


# -- Pox Plague: three-step halving with one trailing "Round down each
# -- time." -------------------------------------------------------------


def test_pox_plague_halves_life_hand_and_permanents_rounded_down():
    scenario = _board(
        {
            "hand": ["Pox Plague", "Mishra's Bauble", "Lightning Bolt"],
            "battlefield": ["Swamp"] * 5 + ["Runeclaw Bear", "Grizzly Bears", "Mountain"],
        },
        {"hand": ["Forest"], "battlefield": ["Plains"]},
    )
    alice = scenario.player("alice")
    bob = scenario.player("bob")
    alice.life = 11  # half rounds down to 5
    bob.life = 3  # half rounds down to 1
    alice_permanents = list(scenario.game.permanents_controlled_by("alice"))  # 8 permanents
    # Pox Plague itself is on the stack by the time this resolves, so
    # alice's hand is down to 2 cards: half of that, rounded down, is 1.
    discarded_card = scenario.find("Mishra's Bauble", Zone.HAND, "alice")
    scenario.will_choose_cards(discarded_card, username="alice")
    scenario.will_choose_cards(*alice_permanents[:4], username="alice")  # sacrifice half of 8 -> 4
    # bob: hand of 1 -> half rounds down to 0, nothing to choose; permanents
    # of 1 -> half rounds down to 0, nothing to choose either.
    scenario.cast_and_resolve("Pox Plague", auto=True)
    assert alice.life == 6
    assert bob.life == 2
    assert len(alice.hand) == 1
    assert len(bob.hand) == 1
    assert sum(1 for p in scenario.game.permanents_controlled_by("alice")) == 4
    assert sum(1 for p in scenario.game.permanents_controlled_by("bob")) == 1


def test_peer_into_the_abyss_halves_library_and_life_rounded_up():
    """Peer into the Abyss's own template - "Round up each time." over a
    *targeted* player's library and life instead of Pox Plague's "each
    player" life/hand/board - the second real printing (`card_search
    o:"half their life"`) proving the trailing rounding declaration is read
    generally, not fitted to Pox Plague's own three actions."""
    scenario = _board(
        {"hand": ["Peer into the Abyss"], "battlefield": ["Swamp"] * 7, "library": ["Plains"] * 7}
    )
    bob = scenario.player("bob")
    bob.life = 11  # half rounds up to 6
    scenario.cast_and_resolve("Peer into the Abyss", auto=True, targets=["bob"])
    assert bob.life == 5
    assert len(bob.hand) == 4  # half of 7, rounded up


# -- End of the Hunt: opponent-chosen exile among the greatest mana value --


def test_end_of_the_hunt_exiles_the_opponents_highest_mana_value_choice():
    scenario = _board(
        {"hand": ["End of the Hunt"], "battlefield": ["Swamp", "Plains"]},
        {"battlefield": ["Grizzly Bears", "Mishra's Bauble"]},
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    bauble = scenario.creature("Mishra's Bauble", "bob")
    scenario.cast_and_resolve("End of the Hunt", auto=True, targets=["bob"])
    assert bears.zone is Zone.EXILE
    assert bauble.zone is Zone.BATTLEFIELD


def test_blot_out_exiles_the_opponents_highest_mana_value_choice():
    """The identical template with "exile" already printed (`Blot Out`) -
    the second real printing the reported card's own regex was widened
    to cover, proven independently."""
    scenario = _board(
        {"hand": ["Blot Out"], "battlefield": ["Swamp", "Swamp", "Swamp"]},
        {"battlefield": ["Grizzly Bears", "Mishra's Bauble"]},
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    bauble = scenario.creature("Mishra's Bauble", "bob")
    scenario.cast_and_resolve("Blot Out", auto=True, targets=["bob"])
    assert bears.zone is Zone.EXILE
    assert bauble.zone is Zone.BATTLEFIELD


# -- Ral Zarek, Guest Lecturer: "-1" unbounded target-player discard -------


def test_ral_zarek_minus_one_makes_any_number_of_target_players_discard():
    scenario = _board(
        {"battlefield": ["Ral Zarek, Guest Lecturer"], "hand": ["Mishra's Bauble"]},
        {"hand": ["Lightning Bolt"]},
    )
    alice = scenario.player("alice")
    bob = scenario.player("bob")
    ral = scenario.creature("Ral Zarek, Guest Lecturer", "alice")
    scenario.will_choose_targets("alice", "bob")
    scenario.will_choose_cards(*alice.hand, username="alice")
    scenario.will_choose_cards(*bob.hand, username="bob")
    scenario.activate(ral, index=1)
    scenario.pass_until_resolved()
    assert len(alice.hand) == 0
    assert len(bob.hand) == 0


def test_ral_zarek_minus_one_may_target_zero_players():
    """CR 107.1c's "any number of" runs from zero - naming none is legal."""
    scenario = _board({"battlefield": ["Ral Zarek, Guest Lecturer"]})
    ral = scenario.creature("Ral Zarek, Guest Lecturer", "alice")
    scenario.will_choose_targets()
    scenario.activate(ral, index=1)
    scenario.pass_until_resolved()
