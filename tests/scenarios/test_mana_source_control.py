"""Scenario: only a mana source's controller may tap it for mana.

The mechanic is who may activate a mana ability, and so whose permanents can
pay a cost. The rules, read whole this session with `mise run rules:find`:

- **CR 602.2** - "Only an object's controller (or its owner, if it doesn't
  have a controller) can activate its activated ability unless the object
  specifically says otherwise."
- **CR 605.3** - "Activating an activated mana ability follows the rules for
  activating any other activated ability (see rule 602.2), with the following
  exceptions" - none of which is about who may activate it.
- **CR 118.3c** - "Activating mana abilities is not mandatory", so auto-tap
  reaching past the payer's own board is not a payment the rules let anyone
  make on the payer's behalf.
- **CR 723.5a** - "The controller of another player can use only that
  player's resources (cards, mana, and so on) to pay costs for that player."
  A spell cast through player control is the controlled player's spell, paid
  from the controlled player's board.
- **CR 702.51a** convoke ("an untapped creature ... you control"),
  **CR 702.126a** improvise ("an untapped artifact you control") and
  **CR 702.66a** delve ("a card from your graveyard").

Before this, `CostPayment.tap_for_mana` asked whether a source could be tapped
at all but never whose it was, so a player naming an opponent's untapped land
as a source paid with it.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.objects_as_costs import convoke, delve, improvise
from magic_cards_model.models.action import ActionKind, Affordability
from magic_cards_model.models.mana import Color
from magic_cards_model.models.zone import Zone

from .harness import Scenario


def alice_bolts_bob_whose_mana_is_all_on_bobs_side() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lightning Bolt"], battlefield=[])
        .player("bob", battlefield=["Mountain", "Llanowar Elves", "Sol Ring"])
    )


# -- tapping a named source (CR 602.2, CR 605.3) ---------------------------


@pytest.mark.parametrize(
    ("source_name", "produces"),
    [
        ("Mountain", [Color.RED]),  # a land
        ("Llanowar Elves", [Color.GREEN]),  # a creature
        ("Sol Ring", [Color.COLORLESS, Color.COLORLESS]),  # an artifact
    ],
)
def test_an_opponents_mana_source_cannot_be_tapped_to_pay(source_name, produces):
    scenario = alice_bolts_bob_whose_mana_is_all_on_bobs_side().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    theirs = scenario.find(source_name, Zone.BATTLEFIELD, "bob")

    casting = scenario.cast("Lightning Bolt", targets=["bob"])
    payment = casting.begin_paying()

    with pytest.raises(
        ValueError, match=r"alice does not control .*\(CR 602\.2, CR 605\.3\)"
    ) as raised:
        payment.tap_for_mana(theirs, produces)

    assert source_name in str(raised.value)
    assert not theirs.tapped
    assert payment.pool.total == 0
    assert payment.tapped_for_mana == []


def test_game_cast_naming_an_opponents_land_is_refused_and_rewound():
    scenario = alice_bolts_bob_whose_mana_is_all_on_bobs_side().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "bob")

    with pytest.raises(ValueError, match=r"CR 602\.2"):
        scenario.game.cast(bolt, "alice", targets=["bob"], mana_sources=[(mountain, [Color.RED])])

    assert bolt.zone is Zone.HAND
    assert not mountain.tapped
    assert scenario.player("bob").life == 20


def test_the_payers_own_source_still_pays():
    """The near miss: the same Mountain, on alice's side, pays."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob", battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    mine = scenario.find("Mountain", Zone.BATTLEFIELD, "alice")

    scenario.game.cast(bolt, "alice", targets=["bob"], mana_sources=[(mine, [Color.RED])])

    assert bolt.zone is Zone.STACK
    assert mine.tapped


# -- auto-pay never reaches past the payer's board (CR 118.3c) -------------


def test_auto_pay_offered_every_permanent_taps_only_the_payers():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob", battlefield=["Mountain", "Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    everything = list(scenario.game.battlefield)

    scenario.game.cast(bolt, "alice", targets=["bob"], mana_sources=everything)

    mine = scenario.find("Mountain", Zone.BATTLEFIELD, "alice")
    assert mine.tapped
    assert not any(permanent.tapped for permanent in scenario.game.permanents_controlled_by("bob"))


def test_auto_pay_with_only_opponent_sources_on_offer_pays_nothing():
    scenario = alice_bolts_bob_whose_mana_is_all_on_bobs_side().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Lightning Bolt", targets=["bob"])
    payment = casting.begin_paying()

    with pytest.raises(ValueError):
        payment.auto_tap(scenario.game.permanents_controlled_by("bob"))

    assert not any(permanent.tapped for permanent in scenario.game.permanents_controlled_by("bob"))


def test_legal_actions_do_not_count_an_opponents_mana_as_affordable():
    from magic_cards_model.machines.legal_actions import legal_actions

    scenario = alice_bolts_bob_whose_mana_is_all_on_bobs_side().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")

    rows = [
        action
        for action in legal_actions(scenario.game, "alice")
        if action.kind is ActionKind.CAST and action.card_id == bolt.id
    ]

    assert rows
    assert all(row.affordable is Affordability.NO for row in rows)


# -- a controlled player pays from their own board (CR 723.5a) --------------


def bob_controlled_by_alice_in_his_main_phase():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", library=["Island"], battlefield=["Island", "Llanowar Elves"])
        .player(
            "bob",
            library=["Island", "Island"],
            hand=["Opt", "Conclave Tribunal"],
            battlefield=["Island", "Plains", "Plains", "Plains"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.gain_control_of_player("alice", "bob")
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()  # bob's untap step
    scenario.advance()  # upkeep
    scenario.turn.advance_to(Step.PRECOMBAT_MAIN)
    assert scenario.turn.active_player == "bob"
    assert scenario.game.is_controlling_player("alice", "bob")
    return scenario


def test_a_controlled_players_spell_cannot_be_paid_from_the_controllers_land():
    scenario = bob_controlled_by_alice_in_his_main_phase()
    opt = scenario.find("Opt", Zone.HAND, "bob")
    alices_island = scenario.find("Island", Zone.BATTLEFIELD, "alice")

    with pytest.raises(ValueError, match=r"CR 723\.5a") as raised:
        scenario.game.cast(opt, "bob", mana_sources=[(alices_island, [Color.BLUE])])

    assert "Island" in str(raised.value)
    assert opt.zone is Zone.HAND
    assert not alices_island.tapped


def test_a_controlled_players_spell_pays_from_the_controlled_players_land():
    scenario = bob_controlled_by_alice_in_his_main_phase()
    opt = scenario.find("Opt", Zone.HAND, "bob")
    bobs_island = scenario.find("Island", Zone.BATTLEFIELD, "bob")

    scenario.game.cast(opt, "bob", mana_sources=[(bobs_island, [Color.BLUE])])

    assert opt.zone is Zone.STACK
    assert bobs_island.tapped


def test_auto_pay_for_a_controlled_player_taps_only_their_lands():
    scenario = bob_controlled_by_alice_in_his_main_phase()
    opt = scenario.find("Opt", Zone.HAND, "bob")
    alices_island = scenario.find("Island", Zone.BATTLEFIELD, "alice")
    bobs_island = scenario.find("Island", Zone.BATTLEFIELD, "bob")

    scenario.game.cast(opt, "bob", mana_sources=[alices_island, bobs_island])

    assert bobs_island.tapped
    assert not alices_island.tapped


def test_a_controlled_player_cannot_convoke_with_the_controllers_creature():
    scenario = bob_controlled_by_alice_in_his_main_phase()
    elves = scenario.find("Llanowar Elves", Zone.BATTLEFIELD, "alice")

    casting = scenario.cast("Conclave Tribunal", username="bob")
    payment = casting.begin_paying()

    with pytest.raises(ValueError, match=r"CR 723\.5a"):
        convoke(payment, casting.spell, elves)

    assert not elves.tapped


# -- the object-paying keywords name their own rule --------------------------


def test_convoking_with_an_opponents_creature_cites_convoke():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Conclave Tribunal"], battlefield=[])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    theirs = scenario.creature("Grizzly Bears", "bob")

    casting = scenario.cast("Conclave Tribunal")
    payment = casting.begin_paying()

    with pytest.raises(ValueError, match=r"alice does not control Grizzly Bears.*CR 702\.51a"):
        convoke(payment, casting.spell, theirs)
    assert not theirs.tapped


def test_improvising_with_an_opponents_artifact_cites_improvise():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Kappa Cannoneer"], battlefield=[])
        .player("bob", battlefield=["Welding Jar"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    theirs = scenario.creature("Welding Jar", "bob")

    casting = scenario.cast("Kappa Cannoneer")
    payment = casting.begin_paying()

    with pytest.raises(ValueError, match=r"alice does not control Welding Jar.*CR 702\.126a"):
        improvise(payment, casting.spell, theirs)
    assert not theirs.tapped


def test_delving_an_opponents_graveyard_cites_delve():
    """Delve is about the graveyard, not control: the refusal says whose
    graveyard the card is in."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Treasure Cruise"], battlefield=[])
        .player("bob", graveyard=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (theirs,) = list(scenario.player("bob").graveyard)

    casting = scenario.cast("Treasure Cruise")
    payment = casting.begin_paying()

    with pytest.raises(
        ValueError, match=r"Mountain is in bob's graveyard, not alice's.*CR 702\.66a"
    ):
        delve(payment, casting.spell, theirs)
    assert theirs.zone is Zone.GRAVEYARD
