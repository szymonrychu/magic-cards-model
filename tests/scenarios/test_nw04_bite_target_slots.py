"""A targeted creature deals damage equal to its power to its targeted victim(s):
the biter and every victim are told apart by the target they were announced
for, never by who controls them.

- Soul's Fire: "Target creature you control deals damage equal to its power
  to any target."
- Fall of the Hammer / Markov Retribution's mode / Itzquinth, Firstborn of
  Gishath's reflexive trigger: "... to another target creature."
- Cosmic Hunger: "... to another target creature, planeswalker, or battle."
- Betrayal at the Vault: "... to each of two other target creatures."
- Spinning Wheel Kick ({X}{X}{G}{G}): "... to each of X target creatures
  and/or planeswalkers."
- Mutiny / Breaking of the Fellowship: "Target creature an opponent controls
  deals damage equal to its power to another target creature that player
  controls."

Rules verified with `mise run rules:find`:

- **CR 601.2c** - the caster announces a target for each instance of the word
  "target"; which instance a target filled is what makes it the biter or a
  victim.
- **CR 115.3** - the same object can't be chosen twice for one instance of
  "target"; "another"/"other" can't name the object already chosen.
- **CR 115.4** - "any target" may be a creature, player, planeswalker or
  battle.
- **CR 608.2b** - on resolution each target is rechecked against its own
  instance; an illegal one is not affected. An illegal biter deals nothing; an
  illegal victim is skipped and the rest are still dealt damage.
- **CR 608.2h** - the biter's power is read as the damage is dealt.
- **CR 120.3a/120.3c/120.3e/120.3h** - damage to a player, planeswalker,
  creature, battle.
- **CR 107.3a** - X is announced while casting.
- **CR 701.14a** - fight: NOT what a bite does; the victim deals nothing back.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _notices(scenario) -> list[object]:
    game = scenario.game
    found: list[object] = list(game.continuous_effects.layer_notices)
    for name in type(game).model_fields:
        if name.endswith("_notices"):
            found.extend(getattr(game, name))
    return found


def _board(spell, lands, mine=(), theirs=(), *, bob_life=20) -> Scenario:
    scenario = (
        Scenario()
        .player("alice", hand=[spell], battlefield=[*lands, *mine])
        .player("bob", battlefield=list(theirs), life=bob_life)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast(scenario, spell, lands, targets):
    sources = scenario.untapped_sources(*lands, username="alice")
    scenario.cast_and_resolve(spell, *sources, username="alice", targets=targets)
    scenario.state_based_actions()


def _on_stack(scenario, spell, lands, targets):
    sources = scenario.untapped_sources(*lands, username="alice")
    return scenario.cast_onto_stack(spell, *sources, username="alice", targets=targets)


# -- Soul's Fire: "any target" ------------------------------------------------

SOULS_FIRE = ("Mountain", "Mountain", "Mountain")


def test_souls_fire_bites_an_opposing_creature_and_takes_nothing_back():
    scenario = _board("Soul's Fire", SOULS_FIRE, mine=("Hill Giant",), theirs=("Grizzly Bears",))
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    _cast(scenario, "Soul's Fire", SOULS_FIRE, [bears, giant])

    assert bears.zone is Zone.GRAVEYARD  # 3 damage
    assert giant.damage == 0  # a bite is not a fight (CR 701.14a)
    assert _notices(scenario) == []


def test_souls_fire_bites_a_player():
    scenario = _board("Soul's Fire", SOULS_FIRE, mine=("Hill Giant",))
    giant = scenario.creature("Hill Giant", "alice")
    _cast(scenario, "Soul's Fire", SOULS_FIRE, ["bob", giant])

    assert scenario.player("bob").life == 17
    assert giant.damage == 0
    assert _notices(scenario) == []


def test_souls_fire_bites_a_creature_its_own_caster_controls():
    """The victim is "any target": a creature you control is one. The roles
    come from the target each was announced for, so both being yours is no
    obstacle (CR 601.2c)."""
    scenario = _board("Soul's Fire", SOULS_FIRE, mine=("Hill Giant", "Grizzly Bears"))
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    # "any target" is the first instance the caster announces for.
    _cast(scenario, "Soul's Fire", SOULS_FIRE, [bears, giant])

    assert bears.zone is Zone.GRAVEYARD
    assert giant.damage == 0


def test_souls_fire_with_its_biter_gone_deals_no_damage():
    """CR 608.2b: the victim is still legal so the spell resolves, but the
    creature that would deal the damage is not there to deal it."""
    scenario = _board("Soul's Fire", SOULS_FIRE, mine=("Hill Giant",), theirs=("Grizzly Bears",))
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    _on_stack(scenario, "Soul's Fire", SOULS_FIRE, [bears, giant])
    scenario.game.return_to_hand(giant)
    scenario.pass_until_resolved()

    assert bears.damage == 0
    assert bears.zone is Zone.BATTLEFIELD


def test_souls_fire_with_its_victim_gone_deals_no_damage():
    scenario = _board(
        "Soul's Fire", SOULS_FIRE, mine=("Hill Giant",), theirs=("Grizzly Bears", "Watchwolf")
    )
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    wolf = scenario.creature("Watchwolf", "bob")
    _on_stack(scenario, "Soul's Fire", SOULS_FIRE, [bears, giant])
    scenario.game.return_to_hand(bears)
    scenario.pass_until_resolved()

    assert wolf.damage == 0
    assert giant.damage == 0
    assert scenario.player("bob").life == 20


def test_souls_fire_biter_whose_controller_changed_is_illegal():
    """CR 608.2b: "target creature you control" no longer accepts a creature
    an opponent now controls, even though the same object is still a fine
    "any target" - the biter is rechecked against its own instance."""
    scenario = _board("Soul's Fire", SOULS_FIRE, mine=("Hill Giant",), theirs=("Grizzly Bears",))
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    _on_stack(scenario, "Soul's Fire", SOULS_FIRE, [bears, giant])
    giant.controller = "bob"
    scenario.pass_until_resolved()

    assert bears.damage == 0
    assert giant.damage == 0


def test_souls_fire_reads_power_as_it_resolves():
    """CR 608.2h: a pump in response raises the damage."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Soul's Fire", "Giant Growth"],
            battlefield=[*SOULS_FIRE, "Forest", "Grizzly Bears"],
        )
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    _on_stack(scenario, "Soul's Fire", SOULS_FIRE, ["bob", bears])
    (forest,) = scenario.untapped_sources("Forest", username="alice")
    scenario.cast_and_resolve("Giant Growth", forest, username="alice", targets=[bears])
    scenario.pass_until_resolved()

    assert scenario.player("bob").life == 15  # 2 + 3


# -- "another target creature" ------------------------------------------------

HAMMER = ("Mountain", "Mountain")


def test_fall_of_the_hammer_bites_another_creature_you_control():
    """Both creatures are yours: the biter is the first instance, the victim
    the "another target creature" (CR 601.2c), not told apart by controller."""
    scenario = _board("Fall of the Hammer", HAMMER, mine=("Hill Giant", "Grizzly Bears"))
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast(scenario, "Fall of the Hammer", HAMMER, [giant, bears])

    assert bears.zone is Zone.GRAVEYARD
    assert giant.damage == 0
    assert _notices(scenario) == []


def test_fall_of_the_hammer_with_the_roles_the_other_way_round():
    scenario = _board("Fall of the Hammer", HAMMER, mine=("Hill Giant", "Grizzly Bears"))
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast(scenario, "Fall of the Hammer", HAMMER, [bears, giant])

    assert giant.damage == 2
    assert bears.damage == 0


def test_fall_of_the_hammer_cannot_name_the_biter_as_its_victim():
    """CR 115.3: "another target creature" is not the creature already chosen."""
    scenario = _board("Fall of the Hammer", HAMMER, mine=("Hill Giant",))
    giant = scenario.creature("Hill Giant", "alice")
    with pytest.raises(ValueError):
        scenario.cast("Fall of the Hammer", "alice", targets=[giant, giant])


def test_fall_of_the_hammer_with_its_victim_gone_still_does_nothing_to_the_biter():
    scenario = _board("Fall of the Hammer", HAMMER, mine=("Hill Giant",), theirs=("Grizzly Bears",))
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    _on_stack(scenario, "Fall of the Hammer", HAMMER, [giant, bears])
    scenario.game.return_to_hand(bears)
    scenario.pass_until_resolved()

    assert giant.damage == 0


def test_markov_retribution_vampire_bites_another_creature():
    """Proof printing: a "target Vampire you control" biter, in a mode."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Markov Retribution"],
            battlefield=["Mountain", "Mountain", "Mountain", "Vampire Nighthawk"],
        )
        .player("bob", battlefield=["Hill Giant"], life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    nighthawk = scenario.creature("Vampire Nighthawk", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    casting = scenario.cast("Markov Retribution")
    casting.choose_modes([2])
    casting.choose_targets([nighthawk, giant])
    scenario.pay_with(
        casting.begin_paying(), *scenario.untapped_sources(*("Mountain",) * 3, username="alice")
    )
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()
    scenario.state_based_actions()

    # 2 damage from a deathtouch, lifelink source.
    assert giant.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 22
    assert nighthawk.damage == 0
    assert _notices(scenario) == []


def test_itzquinth_reflexive_trigger_dinosaur_bites_another_creature():
    """Proof printing: the same reader on a reflexive triggered ability
    (CR 603.12) - "When you do, target Dinosaur you control deals damage
    equal to its power to another target creature."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Itzquinth, Firstborn of Gishath"],
            battlefield=["Mountain", "Forest", "Mountain", "Forest", "Craw Wurm"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources("Mountain", "Forest", username="alice")
    scenario.cast_and_resolve("Itzquinth, Firstborn of Gishath", *sources, username="alice")
    itzquinth = scenario.creature("Itzquinth, Firstborn of Gishath", "alice")
    scenario.will_pay_the_mana_cost(True, source="Itzquinth, Firstborn of Gishath")
    scenario.will_choose_targets(itzquinth, bears, source="Itzquinth, Firstborn of Gishath")
    for _ in range(4):
        if not scenario.game.stack and not scenario.pending_triggers:
            break
        scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD  # 2 damage
    assert itzquinth.damage == 0
    assert _notices(scenario) == []


# -- Cosmic Hunger: "another target creature, planeswalker, or battle" --------

HUNGER = ("Forest", "Forest")


def test_cosmic_hunger_bites_a_planeswalker():
    scenario = _board(
        "Cosmic Hunger", HUNGER, mine=("Grizzly Bears",), theirs=("Liliana of the Veil",)
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    liliana = scenario.find("Liliana of the Veil", Zone.BATTLEFIELD, "bob")
    _cast(scenario, "Cosmic Hunger", HUNGER, [bears, liliana])

    assert liliana.counter_count("loyalty") == 1  # 3 - 2 (CR 120.3c)
    assert _notices(scenario) == []


def test_cosmic_hunger_bites_a_battle():
    scenario = (
        Scenario()
        .player("alice", hand=["Cosmic Hunger", "Invasion of Ikoria"], battlefield=[*HUNGER])
        .player("bob", battlefield=["Craw Wurm"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    siege = scenario.put_onto_battlefield("Invasion of Ikoria", "alice")
    scenario.pass_until_resolved()  # the Siege's own enters trigger
    wurm = scenario.creature("Craw Wurm", "bob")
    wurm.controller = "alice"  # a control change already happened
    defense = siege.counter_count("defense")
    _cast(scenario, "Cosmic Hunger", HUNGER, [wurm, siege])

    assert siege.counter_count("defense") == max(defense - 6, 0)  # CR 120.3h
    assert _notices(scenario) == []


def test_cosmic_hunger_cannot_target_a_player():
    scenario = _board("Cosmic Hunger", HUNGER, mine=("Grizzly Bears",))
    bears = scenario.creature("Grizzly Bears", "alice")
    with pytest.raises(ValueError):
        scenario.cast("Cosmic Hunger", "alice", targets=[bears, "bob"])


# -- Betrayal at the Vault: "each of two other target creatures" ---------------

VAULT = ("Forest",) * 6


def test_betrayal_at_the_vault_deals_full_power_to_each_of_two_victims():
    scenario = _board(
        "Betrayal at the Vault", VAULT, mine=("Hill Giant",), theirs=("Grizzly Bears", "Watchwolf")
    )
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    wolf = scenario.creature("Watchwolf", "bob")
    _cast(scenario, "Betrayal at the Vault", VAULT, [giant, bears, wolf])

    assert bears.zone is Zone.GRAVEYARD
    assert wolf.zone is Zone.GRAVEYARD  # 3 each, not divided
    assert giant.damage == 0
    assert _notices(scenario) == []


def test_betrayal_at_the_vault_one_victim_gone_the_other_still_takes_it():
    scenario = _board(
        "Betrayal at the Vault", VAULT, mine=("Hill Giant",), theirs=("Grizzly Bears", "Craw Wurm")
    )
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    wurm = scenario.creature("Craw Wurm", "bob")
    _on_stack(scenario, "Betrayal at the Vault", VAULT, [giant, bears, wurm])
    scenario.game.return_to_hand(bears)
    scenario.pass_until_resolved()

    assert wurm.damage == 3


def test_betrayal_at_the_vault_biter_gone_no_damage_at_all():
    scenario = _board(
        "Betrayal at the Vault", VAULT, mine=("Hill Giant",), theirs=("Grizzly Bears", "Watchwolf")
    )
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    wolf = scenario.creature("Watchwolf", "bob")
    _on_stack(scenario, "Betrayal at the Vault", VAULT, [giant, bears, wolf])
    scenario.game.return_to_hand(giant)
    scenario.pass_until_resolved()

    assert bears.damage == 0
    assert wolf.damage == 0


def test_betrayal_at_the_vault_victims_can_be_your_own_creatures():
    scenario = _board(
        "Betrayal at the Vault", VAULT, mine=("Craw Wurm", "Grizzly Bears", "Watchwolf")
    )
    wurm = scenario.creature("Craw Wurm", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    wolf = scenario.creature("Watchwolf", "alice")
    _cast(scenario, "Betrayal at the Vault", VAULT, [wurm, bears, wolf])

    assert bears.zone is Zone.GRAVEYARD
    assert wolf.zone is Zone.GRAVEYARD
    assert wurm.damage == 0


def test_betrayal_at_the_vault_needs_two_different_other_creatures():
    """CR 115.3: one creature can't fill both places of the one instance,
    and "other" can't be the biter."""
    scenario = _board("Betrayal at the Vault", VAULT, mine=("Hill Giant",), theirs=("Watchwolf",))
    giant = scenario.creature("Hill Giant", "alice")
    wolf = scenario.creature("Watchwolf", "bob")
    with pytest.raises(ValueError):
        scenario.cast("Betrayal at the Vault", "alice", targets=[giant, wolf, wolf])
    with pytest.raises(ValueError):
        scenario.cast("Betrayal at the Vault", "alice", targets=[giant, wolf, giant])


# -- Spinning Wheel Kick: "each of X target creatures and/or planeswalkers" ----


def _kick(scenario, x, targets, lands):
    casting = scenario.cast("Spinning Wheel Kick", "alice")
    casting.x_value = x  # CR 601.2b: X is announced before the targets (CR 601.2c)
    casting.choose_targets(targets)
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources(*lands, username="alice"))
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()
    scenario.state_based_actions()


def test_spinning_wheel_kick_x_two_hits_a_creature_and_a_planeswalker():
    lands = ("Forest",) * 6
    scenario = _board(
        "Spinning Wheel Kick",
        lands,
        mine=("Hill Giant",),
        theirs=("Grizzly Bears", "Liliana of the Veil"),
    )
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    liliana = scenario.find("Liliana of the Veil", Zone.BATTLEFIELD, "bob")
    _kick(scenario, 2, [giant, bears, liliana], lands)

    assert bears.zone is Zone.GRAVEYARD
    assert liliana.zone is Zone.GRAVEYARD  # 3 loyalty, 3 damage
    assert giant.damage == 0
    assert _notices(scenario) == []


def test_spinning_wheel_kick_x_zero_names_no_victim_and_deals_nothing():
    lands = ("Forest", "Forest")
    scenario = _board("Spinning Wheel Kick", lands, mine=("Hill Giant",), theirs=("Grizzly Bears",))
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    _kick(scenario, 0, [giant], lands)

    assert bears.damage == 0
    assert giant.damage == 0
    assert _notices(scenario) == []


def test_spinning_wheel_kick_takes_no_more_victims_than_x():
    """CR 601.2c: "each of X target ..." is exactly X targets once X is
    announced (CR 107.3a)."""
    lands = ("Forest",) * 4
    scenario = _board(
        "Spinning Wheel Kick", lands, mine=("Hill Giant",), theirs=("Grizzly Bears", "Watchwolf")
    )
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    wolf = scenario.creature("Watchwolf", "bob")
    casting = scenario.cast("Spinning Wheel Kick", "alice")
    casting.x_value = 1
    with pytest.raises(ValueError):
        casting.choose_targets([giant, bears, wolf])


def test_spinning_wheel_kick_victim_gone_the_rest_still_take_damage():
    lands = ("Forest",) * 6
    scenario = _board(
        "Spinning Wheel Kick", lands, mine=("Hill Giant",), theirs=("Grizzly Bears", "Craw Wurm")
    )
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    wurm = scenario.creature("Craw Wurm", "bob")
    casting = scenario.cast("Spinning Wheel Kick", "alice")
    casting.x_value = 2
    casting.choose_targets([giant, bears, wurm])
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources(*lands, username="alice"))
    scenario.put_on_stack(casting)
    scenario.game.return_to_hand(bears)
    scenario.pass_until_resolved()

    assert wurm.damage == 3


# -- Mutiny: "another target creature that player controls" -------------------


def test_mutiny_has_an_opponents_creature_bite_another_of_theirs():
    scenario = _board("Mutiny", ("Mountain",), theirs=("Hill Giant", "Grizzly Bears"))
    giant = scenario.creature("Hill Giant", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    _cast(scenario, "Mutiny", ("Mountain",), [giant, bears])

    assert bears.zone is Zone.GRAVEYARD
    assert giant.damage == 0
    assert _notices(scenario) == []


def test_mutiny_victim_must_be_controlled_by_the_biters_controller():
    """CR 601.2c: "that player" is the opponent who controls the first
    target, so a creature of the caster's own is not a legal second target."""
    scenario = _board("Mutiny", ("Mountain",), mine=("Grizzly Bears",), theirs=("Hill Giant",))
    giant = scenario.creature("Hill Giant", "bob")
    bears = scenario.creature("Grizzly Bears", "alice")
    with pytest.raises(ValueError):
        scenario.cast("Mutiny", "alice", targets=[giant, bears])


def test_mutiny_biter_gone_no_damage():
    scenario = _board("Mutiny", ("Mountain",), theirs=("Hill Giant", "Grizzly Bears"))
    giant = scenario.creature("Hill Giant", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    _on_stack(scenario, "Mutiny", ("Mountain",), [giant, bears])
    scenario.game.return_to_hand(giant)
    scenario.pass_until_resolved()

    assert bears.damage == 0


def test_mutiny_victim_now_controlled_by_another_player_is_not_bitten():
    """CR 608.2b: the victim must still be controlled by that player."""
    scenario = _board("Mutiny", ("Mountain",), theirs=("Hill Giant", "Grizzly Bears"))
    giant = scenario.creature("Hill Giant", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    _on_stack(scenario, "Mutiny", ("Mountain",), [giant, bears])
    bears.controller = "alice"
    scenario.pass_until_resolved()

    assert bears.damage == 0
    assert giant.damage == 0


def test_breaking_of_the_fellowship_bites_then_the_ring_tempts_you():
    """Proof printing: the Mutiny sentence followed by its own rider."""
    lands = ("Mountain", "Mountain")
    scenario = _board(
        "Breaking of the Fellowship",
        lands,
        mine=("Grizzly Bears",),
        theirs=("Hill Giant", "Watchwolf"),
    )
    giant = scenario.creature("Hill Giant", "bob")
    wolf = scenario.creature("Watchwolf", "bob")
    _cast(scenario, "Breaking of the Fellowship", lands, [giant, wolf])

    assert wolf.zone is Zone.GRAVEYARD
    assert giant.damage == 0
    assert scenario.player("alice").ring_tempted_count == 1
    assert _notices(scenario) == []
