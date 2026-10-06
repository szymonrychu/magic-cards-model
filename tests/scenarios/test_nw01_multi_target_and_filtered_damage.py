"""Different fixed amounts to several distinct targets, and damage to a filtered
or target-relative group.

Listed cards (NW-01, task T3):

- **Cone of Flame** - "deals 1 damage to any target, 2 damage to another
  target, and 3 damage to a third target."
- **Marrow Shards** - "deals 1 damage to each attacking creature." (its
  Phyrexian-mana reminder line must not block the read)
- **Fear, Fire, Foes!** - "Damage can't be prevented this turn. ... deals X
  damage to target creature and 1 damage to each other creature with the same
  controller."
- **Chandra's Fury** - "deals 4 damage to target player or planeswalker and 1
  damage to each creature that player or that planeswalker's controller
  controls."

Second printings that prove the readers are templates (each legal in Modern,
none in a deck list): **Serpentine Spike** ("2 damage to target creature, 3
damage to another target creature, and 4 damage to a third target creature"),
**Rain of Blades** ("1 damage to each attacking creature") and **Radiating
Lightning** ("3 damage to target player and 1 damage to each creature that
player controls"). No second printing of Fear, Fire, Foes!'s "each other
creature with the same controller" wording exists in the three formats, so its
group half is proved on Radiating Lightning's and Chandra's Fury's "that
player controls" group.

Rules, each read with `mise run rules:find` in the session that wrote this
file:

- **CR 115.1 / 115.3** - each "target" is its own instance; "another target"
  names something different from the targets already chosen.
- **CR 608.2b** - an illegal target takes nothing, the rest of the spell still
  happens; with every target illegal the spell does not resolve.
- **CR 608.2c** - instructions run in printed order.
- **CR 120.2b** - the spell is the source of the damage.
- **CR 615.12** - "damage can't be prevented" leaves prevention effects
  applying but preventing nothing.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _board(*, hand, alice_battlefield, bob_battlefield, alice_life: int = 20) -> Scenario:
    scenario = (
        Scenario()
        .player("alice", hand=hand, battlefield=alice_battlefield, life=alice_life)
        .player("bob", battlefield=bob_battlefield)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_x(scenario, name, x, targets):
    casting = scenario.cast(name, "alice", targets=targets)
    casting.x_value = x
    payment = casting.begin_paying()
    scenario.auto_pay(payment, username="alice")
    scenario.put_on_stack(casting)
    return scenario.resolve_top()


# -- Cone of Flame --------------------------------------------------------------


def _cone():
    return _board(
        hand=["Cone of Flame"],
        alice_battlefield=["Mountain"] * 5 + ["Hill Giant"],
        bob_battlefield=["Grizzly Bears", "Colossal Dreadmaw"],
    )


def test_cone_of_flame_deals_one_two_and_three_in_target_order():
    scenario = _cone()
    bears = scenario.creature("Grizzly Bears", "bob")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")

    scenario.cast_and_resolve(
        "Cone of Flame", auto=True, targets=[scenario.player("bob"), bears, dreadmaw]
    )

    assert scenario.player("bob").life == 19, "the first target takes 1"
    assert bears.zone is Zone.GRAVEYARD, "the second takes 2: lethal to a 2/2"
    assert dreadmaw.damage == 3, "the third takes 3"


def test_cone_of_flame_amounts_follow_the_order_the_targets_were_named():
    scenario = _cone()
    bears = scenario.creature("Grizzly Bears", "bob")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")

    scenario.cast_and_resolve(
        "Cone of Flame", auto=True, targets=[dreadmaw, scenario.player("bob"), bears]
    )

    assert dreadmaw.damage == 1
    assert scenario.player("bob").life == 18
    assert bears.zone is Zone.GRAVEYARD, "3 damage to the third"


def test_cone_of_flame_three_targets_must_be_distinct():
    """CR 115.3: "another" and "a third" name something other than the
    targets already chosen."""
    scenario = _cone()
    bears = scenario.creature("Grizzly Bears", "bob")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")

    with pytest.raises(ValueError):
        scenario.cast("Cone of Flame", targets=[bears, bears, dreadmaw])
    with pytest.raises(ValueError):
        scenario.cast("Cone of Flame", targets=[bears, dreadmaw, bears])
    with pytest.raises(ValueError):
        scenario.cast("Cone of Flame", targets=[bears, dreadmaw, dreadmaw])


def test_cone_of_flame_needs_all_three_targets():
    scenario = _cone()
    bears = scenario.creature("Grizzly Bears", "bob")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")

    with pytest.raises(ValueError):
        scenario.cast("Cone of Flame", targets=[bears, dreadmaw])


def test_cone_of_flame_an_illegal_target_is_skipped_and_the_others_still_hit():
    """CR 608.2b."""
    scenario = _cone()
    bears = scenario.creature("Grizzly Bears", "bob")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    scenario.cast_onto_stack(
        "Cone of Flame", auto=True, targets=[scenario.player("bob"), bears, dreadmaw]
    )
    scenario.game.destroy(bears)

    scenario.resolve_top()

    assert scenario.player("bob").life == 19
    assert dreadmaw.damage == 3


def test_cone_of_flame_with_every_target_gone_does_not_resolve():
    scenario = _cone()
    bears = scenario.creature("Grizzly Bears", "bob")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    giant = scenario.creature("Hill Giant", "alice")
    scenario.cast_onto_stack("Cone of Flame", auto=True, targets=[bears, dreadmaw, giant])
    for target in (bears, dreadmaw, giant):
        scenario.game.destroy(target)

    scenario.resolve_top()

    assert scenario.player("bob").life == 20 and scenario.player("alice").life == 20
    assert scenario.find("Cone of Flame", Zone.GRAVEYARD, "alice") is not None


def test_cone_of_flame_can_aim_at_planeswalkers_and_players_alike():
    scenario = _board(
        hand=["Cone of Flame"],
        alice_battlefield=["Mountain"] * 5,
        bob_battlefield=["Chandra, Torch of Defiance", "Grizzly Bears"],
    )
    chandra = scenario.find("Chandra, Torch of Defiance", Zone.BATTLEFIELD, "bob")
    chandra.add_counters(Counter.LOYALTY, 6 - chandra.counters[Counter.LOYALTY])
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.cast_and_resolve(
        "Cone of Flame", auto=True, targets=[bears, scenario.player("alice"), chandra]
    )

    assert bears.damage == 1
    assert scenario.player("alice").life == 18, "the caster may be its own second target"
    assert chandra.counters[Counter.LOYALTY] == 3


def test_serpentine_spike_two_three_four_to_three_distinct_creatures_with_exile():
    """The same reader on a second printing, with its own exile rider: "if a
    creature dealt damage this way would die this turn, exile it instead"."""
    scenario = _board(
        hand=["Serpentine Spike"],
        alice_battlefield=["Mountain"] * 7,
        bob_battlefield=["Grizzly Bears", "Hill Giant", "Colossal Dreadmaw"],
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")

    scenario.cast_and_resolve("Serpentine Spike", auto=True, targets=[bears, giant, dreadmaw])

    assert scenario.find("Grizzly Bears", Zone.EXILE, "bob") is not None
    assert scenario.find("Hill Giant", Zone.EXILE, "bob") is not None
    assert dreadmaw.zone is Zone.BATTLEFIELD and dreadmaw.damage == 4


def test_serpentine_spike_cannot_name_one_creature_twice():
    scenario = _board(
        hand=["Serpentine Spike"],
        alice_battlefield=["Mountain"] * 7,
        bob_battlefield=["Grizzly Bears", "Colossal Dreadmaw"],
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")

    with pytest.raises(ValueError):
        scenario.cast("Serpentine Spike", targets=[bears, dreadmaw, bears])


# -- Marrow Shards / Rain of Blades ------------------------------------------------


def _combat_board(name):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[name],
            battlefield=["Plains", "Plains", "Grizzly Bears", "Hill Giant", "Runeclaw Bear"],
        )
        .player("bob", battlefield=["Colossal Dreadmaw"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario


@pytest.mark.parametrize("name", ["Marrow Shards", "Rain of Blades"])
def test_one_damage_to_each_attacking_creature_and_only_those(name):
    scenario = _combat_board(name)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    runeclaw = scenario.creature("Runeclaw Bear", "alice")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    scenario.attack_with(bears, giant)

    scenario.cast_and_resolve(name, auto=True)

    assert bears.damage == 1 and giant.damage == 1, "each attacking creature, the caster's own too"
    assert runeclaw.damage == 0, "not attacking"
    assert dreadmaw.damage == 0, "not attacking"
    assert scenario.player("bob").life == 20


def test_marrow_shards_with_nothing_attacking_does_nothing():
    scenario = _combat_board("Marrow Shards")
    scenario.cast_and_resolve("Marrow Shards", auto=True)

    assert scenario.creature("Grizzly Bears", "alice").damage == 0


def test_rain_of_blades_finishes_a_wounded_attacker():
    scenario = _combat_board("Rain of Blades")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(bears)
    scenario.game.deal_damage(bears, 1, source=scenario.creature("Colossal Dreadmaw", "bob"))

    scenario.cast_and_resolve("Rain of Blades", auto=True)

    assert bears.zone is Zone.GRAVEYARD


# -- Fear, Fire, Foes! -----------------------------------------------------------


def _fff(**kwargs):
    return _board(
        hand=["Fear, Fire, Foes!"],
        alice_battlefield=["Mountain"] * 5 + ["Hill Giant"],
        bob_battlefield=["Grizzly Bears", "Runeclaw Bear", "Colossal Dreadmaw"],
        **kwargs,
    )


def test_fear_fire_foes_x_to_the_target_and_one_to_each_other_creature_of_its_controller():
    scenario = _fff()
    bears = scenario.creature("Grizzly Bears", "bob")
    runeclaw = scenario.creature("Runeclaw Bear", "bob")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    giant = scenario.creature("Hill Giant", "alice")

    _cast_x(scenario, "Fear, Fire, Foes!", 3, [dreadmaw])

    assert dreadmaw.damage == 3, "X to the target, and not the extra 1 as well"
    assert bears.damage == 1 and runeclaw.damage == 1
    assert giant.damage == 0, "the caster's own creatures have another controller"


def test_fear_fire_foes_group_follows_the_targets_controller_not_the_caster():
    scenario = _fff()
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")

    _cast_x(scenario, "Fear, Fire, Foes!", 1, [giant])

    assert giant.damage == 1
    assert bears.damage == 0, "Bob's creatures are not the target's controller's"


def test_fear_fire_foes_with_x_zero_still_pings_the_others():
    scenario = _fff()
    bears = scenario.creature("Grizzly Bears", "bob")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")

    _cast_x(scenario, "Fear, Fire, Foes!", 0, [dreadmaw])

    assert dreadmaw.damage == 0
    assert bears.damage == 1


def test_fear_fire_foes_target_gone_means_the_spell_does_not_resolve():
    """CR 608.2b: its only target illegal, nothing happens - the group half
    included."""
    scenario = _fff()
    bears = scenario.creature("Grizzly Bears", "bob")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    casting = scenario.cast("Fear, Fire, Foes!", "alice", targets=[dreadmaw])
    casting.x_value = 2
    payment = casting.begin_paying()
    scenario.auto_pay(payment, username="alice")
    scenario.put_on_stack(casting)
    scenario.game.destroy(dreadmaw)

    scenario.resolve_top()

    assert bears.damage == 0 and bears.zone is Zone.BATTLEFIELD


def test_fear_fire_foes_damage_cant_be_prevented_but_chandras_fury_damage_can():
    """CR 615.12: with the first sentence, protection from red prevents
    nothing; the same group damage from a spell without it is prevented."""
    scenario = _board(
        hand=["Fear, Fire, Foes!", "Chandra's Fury"],
        alice_battlefield=["Mountain"] * 10,
        bob_battlefield=[
            "Sword of Fire and Ice",
            "Grizzly Bears",
            "Colossal Dreadmaw",
            "Hill Giant",
        ],
    )
    sword = scenario.find("Sword of Fire and Ice", Zone.BATTLEFIELD, "bob")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    sword.attach_to(dreadmaw)  # staging: protection from red

    scenario.cast_and_resolve("Chandra's Fury", auto=True, targets=[scenario.player("bob")])
    assert dreadmaw.damage == 0, "protection prevented the 1 damage"

    _cast_x(scenario, "Fear, Fire, Foes!", 1, [bears])
    assert dreadmaw.damage == 1, "unpreventable this turn"


# -- Chandra's Fury / Radiating Lightning ---------------------------------------


def test_chandras_fury_player_takes_four_and_each_of_their_creatures_one():
    scenario = _board(
        hand=["Chandra's Fury"],
        alice_battlefield=["Mountain"] * 5 + ["Hill Giant"],
        bob_battlefield=["Grizzly Bears", "Colossal Dreadmaw"],
    )
    scenario.cast_and_resolve("Chandra's Fury", auto=True, targets=[scenario.player("bob")])

    assert scenario.player("bob").life == 16
    assert scenario.creature("Grizzly Bears", "bob").damage == 1
    assert scenario.creature("Colossal Dreadmaw", "bob").damage == 1
    assert scenario.creature("Hill Giant", "alice").damage == 0


def test_chandras_fury_at_a_planeswalker_hits_it_and_its_controllers_creatures():
    scenario = _board(
        hand=["Chandra's Fury"],
        alice_battlefield=["Mountain"] * 5 + ["Hill Giant"],
        bob_battlefield=["Chandra, Torch of Defiance", "Grizzly Bears"],
    )
    chandra = scenario.find("Chandra, Torch of Defiance", Zone.BATTLEFIELD, "bob")
    chandra.add_counters(Counter.LOYALTY, 6 - chandra.counters[Counter.LOYALTY])

    scenario.cast_and_resolve("Chandra's Fury", auto=True, targets=[chandra])

    assert chandra.counters[Counter.LOYALTY] == 2
    assert scenario.player("bob").life == 20, "the planeswalker takes it, not its controller"
    assert scenario.creature("Grizzly Bears", "bob").damage == 1
    assert scenario.creature("Hill Giant", "alice").damage == 0


def test_chandras_fury_aimed_at_its_caster_burns_the_casters_side():
    scenario = _board(
        hand=["Chandra's Fury"],
        alice_battlefield=["Mountain"] * 5 + ["Hill Giant"],
        bob_battlefield=["Grizzly Bears"],
    )
    scenario.cast_and_resolve("Chandra's Fury", auto=True, targets=[scenario.player("alice")])

    assert scenario.player("alice").life == 16
    assert scenario.creature("Hill Giant", "alice").damage == 1
    assert scenario.creature("Grizzly Bears", "bob").damage == 0


def test_radiating_lightning_three_to_the_player_one_to_each_of_their_creatures():
    scenario = _board(
        hand=["Radiating Lightning"],
        alice_battlefield=["Mountain"] * 4 + ["Hill Giant"],
        bob_battlefield=["Grizzly Bears", "Colossal Dreadmaw"],
    )
    scenario.cast_and_resolve("Radiating Lightning", auto=True, targets=[scenario.player("bob")])

    assert scenario.player("bob").life == 17
    assert scenario.creature("Grizzly Bears", "bob").damage == 1
    assert scenario.creature("Colossal Dreadmaw", "bob").damage == 1
    assert scenario.creature("Hill Giant", "alice").damage == 0


def test_radiating_lightning_with_no_creatures_still_hits_the_player():
    scenario = _board(
        hand=["Radiating Lightning"],
        alice_battlefield=["Mountain"] * 4,
        bob_battlefield=[],
    )
    scenario.cast_and_resolve("Radiating Lightning", auto=True, targets=[scenario.player("bob")])

    assert scenario.player("bob").life == 17
