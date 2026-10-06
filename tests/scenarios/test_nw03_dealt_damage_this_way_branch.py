"""Scenario: "<damage sentence>. If a <quality> is dealt damage this way,
<effect>."

Listed cards: Provoke the Trolls ("a creature" ... "it gets +5/+0 until end of
turn") and Redcap Melee ("a nonred permanent" ... "you sacrifice a land").
Proof printings: Play with Fire ("a player" ... "scry 1") and Burn from Within
("a creature" ... "it loses indestructible until end of turn. If that creature
would die this turn, exile it instead.").

Verified this session with `mise run rules:find`:

- **CR 120.3** - the results of damage depend on whether the recipient is a
  player or a permanent (a planeswalker loses loyalty, a creature has it marked).
- **CR 615.6** - prevented damage is never dealt, so its recipient is not
  "dealt damage this way".
- **CR 608.2b** - an illegal sole target means the spell does nothing.
- **CR 105.2** - a permanent's colour is read off its characteristics.
- **CR 701.21a** - to sacrifice a permanent is to move it from the battlefield
  to its owner's graveyard; its controller chooses it.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter

from .harness import Scenario


def _board(*, hand, lands, alice_battlefield=(), bob_battlefield=(), library=("Mountain",) * 4):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=list(hand),
            battlefield=list(lands) + list(alice_battlefield),
            library=list(library),
        )
        .player("bob", battlefield=list(bob_battlefield))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast(scenario, name, targets, mountains):
    return scenario.cast_and_resolve(
        name, *scenario.untapped_sources(*["Mountain"] * mountains), targets=targets
    )


def _power(scenario, creature):
    return scenario.game.characteristics_of(creature).numeric_power


def _lands_of(scenario, username):
    return [
        state
        for state in scenario.game.battlefield
        if state.name == "Mountain" and scenario.game.controller_of(state).username == username
    ]


def _burn(scenario, target, x):
    scenario.game.cast(
        scenario.find("Burn from Within", Zone.HAND, "alice"),
        "alice",
        x_value=x,
        targets=[target],
        mana_sources=scenario.untapped_sources(*["Mountain"] * (x + 1)),
    )
    scenario.resolve_top()


def _protect(scenario, creature):
    """Shielded Passage on `creature`: all damage to it this turn is prevented."""
    scenario.cast_and_resolve(
        "Shielded Passage", *scenario.untapped_sources("Plains"), targets=[creature]
    )


# -- Provoke the Trolls ----------------------------------------------------------


def test_provoke_the_trolls_pumps_a_creature_that_survives_the_damage():
    scenario = _board(
        hand=["Provoke the Trolls"], lands=["Mountain"] * 4, bob_battlefield=["Colossal Dreadmaw"]
    )
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    _cast(scenario, "Provoke the Trolls", [dreadmaw], 4)
    assert dreadmaw.zone is Zone.BATTLEFIELD
    assert dreadmaw.damage == 3
    assert _power(scenario, dreadmaw) == 11  # 6 + 5, though it survived


def test_provoke_the_trolls_pump_lasts_until_end_of_turn():
    scenario = _board(
        hand=["Provoke the Trolls"], lands=["Mountain"] * 4, bob_battlefield=["Colossal Dreadmaw"]
    )
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    _cast(scenario, "Provoke the Trolls", [dreadmaw], 4)
    while scenario.step is not Step.CLEANUP:
        scenario.advance()
    scenario.advance()
    assert _power(scenario, dreadmaw) == 6


def test_provoke_the_trolls_on_a_player_pumps_nothing():
    scenario = _board(
        hand=["Provoke the Trolls"],
        lands=["Mountain"] * 4,
        alice_battlefield=["Grizzly Bears"],
        bob_battlefield=["Colossal Dreadmaw"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    _cast(scenario, "Provoke the Trolls", ["bob"], 4)
    assert scenario.player("bob").life == 17
    assert _power(scenario, bears) == 2
    assert _power(scenario, dreadmaw) == 6


def test_provoke_the_trolls_on_a_planeswalker_pumps_nothing():
    scenario = _board(
        hand=["Provoke the Trolls"],
        lands=["Mountain"] * 4,
        bob_battlefield=["Jace Beleren", "Colossal Dreadmaw"],
    )
    jace = scenario.find("Jace Beleren", Zone.BATTLEFIELD, "bob")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    loyalty = jace.counter_count(Counter.LOYALTY)
    _cast(scenario, "Provoke the Trolls", [jace], 4)
    assert (
        jace.counter_count(Counter.LOYALTY) == loyalty - 3
    )  # dealt damage, but a planeswalker is no creature
    assert _power(scenario, dreadmaw) == 6


def test_provoke_the_trolls_does_not_pump_a_creature_whose_damage_was_prevented():
    scenario = _board(
        hand=["Provoke the Trolls", "Shielded Passage"],
        lands=["Mountain"] * 4 + ["Plains"],
        bob_battlefield=["Colossal Dreadmaw"],
    )
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    _protect(scenario, dreadmaw)
    _cast(scenario, "Provoke the Trolls", [dreadmaw], 4)
    assert dreadmaw.damage == 0
    assert _power(scenario, dreadmaw) == 6  # CR 615.6: never dealt


def test_provoke_the_trolls_with_an_illegal_target_does_nothing():
    scenario = _board(
        hand=["Provoke the Trolls"],
        lands=["Mountain"] * 4,
        bob_battlefield=["Grizzly Bears", "Colossal Dreadmaw"],
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    scenario.game.cast(
        scenario.find("Provoke the Trolls", Zone.HAND, "alice"),
        "alice",
        targets=[bears],
        mana_sources=scenario.untapped_sources(*["Mountain"] * 4),
    )
    scenario.game.destroy(bears)
    scenario.resolve_top()
    assert _power(scenario, dreadmaw) == 6


def test_provoke_the_trolls_pumps_a_creature_that_dies_without_error():
    scenario = _board(
        hand=["Provoke the Trolls"], lands=["Mountain"] * 4, bob_battlefield=["Grizzly Bears"]
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    _cast(scenario, "Provoke the Trolls", [bears], 4)
    assert bears.zone is Zone.GRAVEYARD


# -- Redcap Melee ----------------------------------------------------------------


def test_redcap_melee_on_a_nonred_creature_sacrifices_a_land():
    scenario = _board(hand=["Redcap Melee"], lands=["Mountain"], bob_battlefield=["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "bob")
    _cast(scenario, "Redcap Melee", [bears], 1)
    assert bears.zone is Zone.GRAVEYARD
    assert _lands_of(scenario, "alice") == []


def test_redcap_melee_lets_its_controller_choose_which_land_to_sacrifice():
    scenario = _board(
        hand=["Redcap Melee"], lands=["Mountain"] * 3, bob_battlefield=["Grizzly Bears"]
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    mountains = _lands_of(scenario, "alice")
    scenario.will_choose_cards(mountains[2])
    _cast(scenario, "Redcap Melee", [bears], 1)
    remaining = _lands_of(scenario, "alice")
    assert len(remaining) == 2
    assert mountains[2] not in remaining


def test_redcap_melee_on_a_red_creature_sacrifices_nothing():
    scenario = _board(hand=["Redcap Melee"], lands=["Mountain"] * 2, bob_battlefield=["Hill Giant"])
    giant = scenario.creature("Hill Giant", "bob")
    _cast(scenario, "Redcap Melee", [giant], 1)
    assert giant.zone is Zone.GRAVEYARD
    assert len(_lands_of(scenario, "alice")) == 2  # CR 105.2: Hill Giant is red


def test_redcap_melee_on_a_nonred_planeswalker_sacrifices_a_land():
    scenario = _board(
        hand=["Redcap Melee"], lands=["Mountain"] * 2, bob_battlefield=["Jace Beleren"]
    )
    jace = scenario.find("Jace Beleren", Zone.BATTLEFIELD, "bob")
    scenario.will_choose_cards(_lands_of(scenario, "alice")[0])
    _cast(scenario, "Redcap Melee", [jace], 1)
    assert len(_lands_of(scenario, "alice")) == 1


def test_redcap_melee_on_a_red_planeswalker_sacrifices_nothing():
    scenario = _board(
        hand=["Redcap Melee"],
        lands=["Mountain"] * 2,
        bob_battlefield=["Chandra, Torch of Defiance"],
    )
    chandra = scenario.find("Chandra, Torch of Defiance", Zone.BATTLEFIELD, "bob")
    _cast(scenario, "Redcap Melee", [chandra], 1)
    assert len(_lands_of(scenario, "alice")) == 2


def test_redcap_melee_sacrifices_only_its_controllers_land():
    scenario = _board(
        hand=["Redcap Melee"],
        lands=["Mountain"],
        bob_battlefield=["Grizzly Bears", "Mountain"],
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    _cast(scenario, "Redcap Melee", [bears], 1)
    assert len(_lands_of(scenario, "bob")) == 1
    assert _lands_of(scenario, "alice") == []


def test_redcap_melee_sacrifices_nothing_when_the_damage_was_prevented():
    scenario = _board(
        hand=["Redcap Melee", "Shielded Passage"],
        lands=["Mountain"] * 2 + ["Plains"],
        bob_battlefield=["Grizzly Bears"],
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    _protect(scenario, bears)
    _cast(scenario, "Redcap Melee", [bears], 1)
    assert bears.zone is Zone.BATTLEFIELD
    assert len(_lands_of(scenario, "alice")) == 2


def test_redcap_melee_with_an_illegal_target_sacrifices_nothing():
    scenario = _board(
        hand=["Redcap Melee"], lands=["Mountain"] * 2, bob_battlefield=["Grizzly Bears"]
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.game.cast(
        scenario.find("Redcap Melee", Zone.HAND, "alice"),
        "alice",
        targets=[bears],
        mana_sources=scenario.untapped_sources("Mountain"),
    )
    scenario.game.destroy(bears)
    scenario.resolve_top()
    assert len(_lands_of(scenario, "alice")) == 2


# -- Play with Fire (a player) ---------------------------------------------------


def test_play_with_fire_on_a_player_scries_one():
    scenario = _board(
        hand=["Play with Fire"], lands=["Mountain"], library=("Forest", "Island", "Swamp")
    )
    top = scenario.top_of_library(1)[0]
    scenario.scry_bottoming(top)
    _cast(scenario, "Play with Fire", ["bob"], 1)
    assert scenario.player("bob").life == 18
    assert scenario.top_of_library(1)[0] is not top


def test_play_with_fire_on_a_creature_does_not_scry():
    scenario = _board(
        hand=["Play with Fire"], lands=["Mountain"], bob_battlefield=["Colossal Dreadmaw"]
    )
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    before = len(scenario.questions_asked())
    _cast(scenario, "Play with Fire", [dreadmaw], 1)
    assert dreadmaw.damage == 2
    assert len(scenario.questions_asked()) == before


# -- Burn from Within (a creature, a chained referent rider) ---------------------


def test_burn_from_within_strips_indestructible_and_exiles_the_creature_it_kills():
    scenario = _board(
        hand=["Burn from Within"],
        lands=["Mountain"] * 2,
        bob_battlefield=["Darksteel Myr"],
    )
    myr = scenario.creature("Darksteel Myr", "bob")
    _burn(scenario, myr, 1)
    assert myr.zone is Zone.EXILE  # lost indestructible, died, exiled instead


def test_burn_from_within_on_a_player_changes_no_creature():
    scenario = _board(
        hand=["Burn from Within"], lands=["Mountain"] * 2, bob_battlefield=["Darksteel Myr"]
    )
    myr = scenario.creature("Darksteel Myr", "bob")
    _burn(scenario, "bob", 1)
    assert scenario.player("bob").life == 19
    assert myr.zone is Zone.BATTLEFIELD
    scenario.game.deal_damage(myr, 5, source=scenario.find("Burn from Within", Zone.GRAVEYARD))
    scenario.game.check_state_based_actions()
    assert myr.zone is Zone.BATTLEFIELD  # still indestructible


def test_burn_from_within_x_zero_deals_nothing_and_changes_nothing():
    scenario = _board(
        hand=["Burn from Within"], lands=["Mountain"], bob_battlefield=["Darksteel Myr"]
    )
    myr = scenario.creature("Darksteel Myr", "bob")
    _burn(scenario, myr, 0)
    scenario.game.deal_damage(myr, 5, source=scenario.find("Burn from Within", Zone.GRAVEYARD))
    scenario.game.check_state_based_actions()
    assert myr.zone is Zone.BATTLEFIELD  # no damage dealt this way, still indestructible
