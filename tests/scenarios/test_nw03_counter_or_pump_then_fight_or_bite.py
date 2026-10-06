"""A counter or a pump on your creature, then it fights or bites.

Ancient Animus: "Put a +1/+1 counter on target creature you control if it's
legendary. Then it fights target creature an opponent controls."
Ent's Fury: "Put a +1/+1 counter on target creature you control if its power is
4 or greater. Then that creature gets +1/+1 until end of turn and fights target
creature you don't control."
Throw from the Saddle: "Target creature you control gets +1/+1 until end of
turn. Put a +1/+1 counter on it instead if it's a Mount. Then it deals damage
equal to its power to target creature you don't control."

Rules verified with `mise run rules:find`:

- **CR 608.2c** - the instructions run in the order written, so the counter or
  pump lands before the fight or bite, and the condition is asked as its own
  instruction resolves (never when the spell is cast).
- **CR 701.14a** - fight: each creature deals damage equal to its power to the
  other.
- **CR 701.14b** - if either creature is gone or no longer a creature, neither
  fights.
- **CR 608.2b** - a target that is illegal on resolution is not affected; the
  instructions that need only the other target still happen.
- **CR 614.1a** - "instead": the Mount's counter replaces the +1/+1 pump.
- **CR 205.4d** - "legendary" is a supertype, read off the computed
  characteristics.
- **CR 122.1a** - a +1/+1 counter adds to power and toughness and lasts.
- **CR 120.3** - a bite is plain damage from the biter; nothing comes back.

Only Ancient Animus, Ent's Fury and Throw from the Saddle print these
sentences (Scryfall search over every Modern/Pioneer/Standard card,
2026-10-06); the unconditional counter-then-fight and pump-then-fight pairs
they sit next to are pinned on Chelonian Tackle, which
go through the same reader.
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


def _pt(scenario, card) -> tuple[int | None, int | None]:
    return (
        scenario.game.continuous_effects.board(scenario.game.battlefield).of(card).power_toughness
    )


def _board(spell, lands, mine=(), theirs=("Gray Ogre",)) -> Scenario:
    scenario = (
        Scenario()
        .player("alice", hand=[spell], battlefield=[*lands, *mine])
        .player("bob", battlefield=list(theirs))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast(scenario, spell, lands, mine, theirs):
    sources = scenario.untapped_sources(*lands, username="alice")
    scenario.cast_and_resolve(spell, *sources, username="alice", targets=[mine, theirs])
    scenario.state_based_actions()


# -- Ancient Animus -----------------------------------------------------------

ANIMUS_LANDS = ("Forest", "Forest")


def test_ancient_animus_puts_the_counter_on_a_legendary_creature_then_it_fights():
    scenario = _board("Ancient Animus", ANIMUS_LANDS, mine=("Isamaru, Hound of Konda",))
    isamaru = scenario.creature("Isamaru, Hound of Konda", "alice")
    ogre = scenario.creature("Gray Ogre", "bob")
    _cast(scenario, "Ancient Animus", ANIMUS_LANDS, isamaru, ogre)

    assert _pt(scenario, isamaru) == (3, 3)  # 2/2 with the counter
    assert ogre.zone is Zone.GRAVEYARD  # 3 damage kills the 2/2
    assert isamaru.zone is Zone.BATTLEFIELD  # took 2, survives as a 3/3
    assert isamaru.damage == 2
    assert _notices(scenario) == []


def test_ancient_animus_gives_no_counter_to_a_nonlegendary_creature_but_it_still_fights():
    """ "Then it fights" is its own instruction: the failed condition on the
    counter does not stop it (CR 608.2c)."""
    scenario = _board(
        "Ancient Animus", ANIMUS_LANDS, mine=("Grizzly Bears",), theirs=("Hill Giant",)
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    _cast(scenario, "Ancient Animus", ANIMUS_LANDS, bears, giant)

    assert bears.counters.power_toughness_modifier == 0
    assert giant.damage == 2
    assert giant.zone is Zone.BATTLEFIELD
    assert bears.zone is Zone.GRAVEYARD  # took 3
    assert _notices(scenario) == []


def test_ancient_animus_with_its_own_target_gone_does_nothing():
    """CR 608.2b: a creature that left the battlefield is no longer a legal
    target, so the counter has no object and nothing fights."""
    scenario = _board("Ancient Animus", ANIMUS_LANDS, mine=("Isamaru, Hound of Konda",))
    isamaru = scenario.creature("Isamaru, Hound of Konda", "alice")
    ogre = scenario.creature("Gray Ogre", "bob")
    sources = scenario.untapped_sources(*ANIMUS_LANDS, username="alice")
    scenario.cast_onto_stack("Ancient Animus", *sources, username="alice", targets=[isamaru, ogre])
    scenario.game.return_to_hand(isamaru)
    scenario.pass_until_resolved()

    assert ogre.zone is Zone.BATTLEFIELD
    assert ogre.damage == 0


def test_ancient_animus_with_its_opposing_target_gone_still_places_the_counter():
    """CR 608.2b / 701.14b: nothing fights, but the counter is its own
    instruction and its target is still legal."""
    scenario = _board("Ancient Animus", ANIMUS_LANDS, mine=("Isamaru, Hound of Konda",))
    isamaru = scenario.creature("Isamaru, Hound of Konda", "alice")
    ogre = scenario.creature("Gray Ogre", "bob")
    sources = scenario.untapped_sources(*ANIMUS_LANDS, username="alice")
    scenario.cast_onto_stack("Ancient Animus", *sources, username="alice", targets=[isamaru, ogre])
    scenario.game.return_to_hand(ogre)
    scenario.pass_until_resolved()

    assert _pt(scenario, isamaru) == (3, 3)
    assert isamaru.damage == 0
    assert _notices(scenario) == []


def test_ancient_animus_refuses_a_creature_you_control_as_the_fight_target():
    scenario = _board(
        "Ancient Animus", ANIMUS_LANDS, mine=("Isamaru, Hound of Konda", "Grizzly Bears")
    )
    isamaru = scenario.creature("Isamaru, Hound of Konda", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    with pytest.raises(ValueError):
        scenario.cast("Ancient Animus", username="alice", targets=[isamaru, bears])


def test_ancient_animus_the_counter_stays_after_the_turn_ends():
    scenario = _board("Ancient Animus", ANIMUS_LANDS, mine=("Isamaru, Hound of Konda",))
    isamaru = scenario.creature("Isamaru, Hound of Konda", "alice")
    ogre = scenario.creature("Gray Ogre", "bob")
    _cast(scenario, "Ancient Animus", ANIMUS_LANDS, isamaru, ogre)
    scenario.game.continuous_effects.end_the_turn(scenario.game)

    assert _pt(scenario, isamaru) == (3, 3)


# -- Ent's Fury ---------------------------------------------------------------

FURY_LANDS = ("Forest", "Forest")


def test_ents_fury_counters_a_power_four_creature_pumps_it_and_fights():
    scenario = _board("Ent's Fury", FURY_LANDS, mine=("Drover Grizzly",), theirs=("Hill Giant",))
    grizzly = scenario.creature("Drover Grizzly", "alice")  # 4/2
    giant = scenario.creature("Hill Giant", "bob")
    _cast(scenario, "Ent's Fury", FURY_LANDS, grizzly, giant)

    assert _pt(scenario, grizzly) == (6, 4)  # counter, then +1/+1
    assert giant.zone is Zone.GRAVEYARD
    assert grizzly.damage == 3
    assert grizzly.zone is Zone.BATTLEFIELD
    assert _notices(scenario) == []


def test_ents_fury_the_pump_is_until_end_of_turn_and_the_counter_is_not():
    scenario = _board("Ent's Fury", FURY_LANDS, mine=("Drover Grizzly",), theirs=("Hill Giant",))
    grizzly = scenario.creature("Drover Grizzly", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    _cast(scenario, "Ent's Fury", FURY_LANDS, grizzly, giant)
    scenario.game.continuous_effects.end_the_turn(scenario.game)

    assert _pt(scenario, grizzly) == (5, 3)


def test_ents_fury_a_power_three_creature_gets_only_the_pump_and_still_fights():
    scenario = _board(
        "Ent's Fury", FURY_LANDS, mine=("Brightfield Mustang",), theirs=("Gray Ogre",)
    )
    mustang = scenario.creature("Brightfield Mustang", "alice")  # 3/3
    ogre = scenario.creature("Gray Ogre", "bob")
    _cast(scenario, "Ent's Fury", FURY_LANDS, mustang, ogre)

    assert _pt(scenario, mustang) == (4, 4)  # the pump alone
    scenario.game.continuous_effects.end_the_turn(scenario.game)
    assert _pt(scenario, mustang) == (3, 3)  # no counter was ever placed
    assert ogre.zone is Zone.GRAVEYARD


def test_ents_fury_reads_the_power_as_it_resolves_so_the_pump_comes_after_the_check():
    """CR 608.2c: a 3-power creature is not "4 or greater" even though the
    +1/+1 later in the same spell would make it so."""
    scenario = _board("Ent's Fury", FURY_LANDS, mine=("Brightfield Mustang",))
    mustang = scenario.creature("Brightfield Mustang", "alice")
    ogre = scenario.creature("Gray Ogre", "bob")
    _cast(scenario, "Ent's Fury", FURY_LANDS, mustang, ogre)

    assert mustang.counters.power_toughness_modifier == 0


def test_ents_fury_with_its_opposing_target_gone_still_counters_and_pumps():
    scenario = _board("Ent's Fury", FURY_LANDS, mine=("Drover Grizzly",), theirs=("Hill Giant",))
    grizzly = scenario.creature("Drover Grizzly", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    sources = scenario.untapped_sources(*FURY_LANDS, username="alice")
    scenario.cast_onto_stack("Ent's Fury", *sources, username="alice", targets=[grizzly, giant])
    scenario.game.return_to_hand(giant)
    scenario.pass_until_resolved()

    assert _pt(scenario, grizzly) == (6, 4)
    assert grizzly.damage == 0


def test_ents_fury_with_its_own_target_gone_does_nothing():
    scenario = _board("Ent's Fury", FURY_LANDS, mine=("Drover Grizzly",), theirs=("Hill Giant",))
    grizzly = scenario.creature("Drover Grizzly", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    sources = scenario.untapped_sources(*FURY_LANDS, username="alice")
    scenario.cast_onto_stack("Ent's Fury", *sources, username="alice", targets=[grizzly, giant])
    scenario.game.return_to_hand(grizzly)
    scenario.pass_until_resolved()

    assert giant.damage == 0


# -- Throw from the Saddle ----------------------------------------------------


def _throw(mine, theirs="Colossal Dreadmaw"):
    scenario = _board("Throw from the Saddle", ("Forest", "Forest"), mine=(mine,), theirs=(theirs,))
    return scenario, scenario.creature(mine, "alice"), scenario.creature(theirs, "bob")


def test_throw_from_the_saddle_pumps_a_non_mount_then_it_bites_for_its_new_power():
    scenario, bears, giant = _throw("Grizzly Bears")
    _cast(scenario, "Throw from the Saddle", ("Forest", "Forest"), bears, giant)

    assert _pt(scenario, bears) == (3, 3)
    assert giant.damage == 3  # the pumped power, not the printed 2
    assert bears.damage == 0  # a bite, not a fight (CR 120.3)
    assert _notices(scenario) == []


def test_throw_from_the_saddle_puts_a_counter_instead_on_a_mount():
    scenario, mustang, giant = _throw("Brightfield Mustang")
    _cast(scenario, "Throw from the Saddle", ("Forest", "Forest"), mustang, giant)

    assert mustang.counters.power_toughness_modifier == 1
    assert _pt(scenario, mustang) == (4, 4)  # the counter only: not also pumped
    assert giant.damage == 4
    scenario.game.continuous_effects.end_the_turn(scenario.game)
    assert _pt(scenario, mustang) == (4, 4)  # the counter lasts


def test_throw_from_the_saddle_a_non_mounts_pump_ends_with_the_turn():
    scenario, bears, giant = _throw("Grizzly Bears")
    _cast(scenario, "Throw from the Saddle", ("Forest", "Forest"), bears, giant)
    assert bears.counters.power_toughness_modifier == 0
    scenario.game.continuous_effects.end_the_turn(scenario.game)

    assert _pt(scenario, bears) == (2, 2)


def test_throw_from_the_saddle_does_not_pump_and_counter_a_mount():
    """ "Instead" replaces the pump (CR 614.1a): exactly +1/+1 in total."""
    scenario, mustang, giant = _throw("Brightfield Mustang")
    _cast(scenario, "Throw from the Saddle", ("Forest", "Forest"), mustang, giant)

    assert _pt(scenario, mustang) == (4, 4)


def test_throw_from_the_saddle_with_the_victim_gone_still_pumps_and_deals_no_damage():
    scenario, bears, giant = _throw("Grizzly Bears")
    sources = scenario.untapped_sources("Forest", "Forest", username="alice")
    scenario.cast_onto_stack(
        "Throw from the Saddle", *sources, username="alice", targets=[bears, giant]
    )
    scenario.game.return_to_hand(giant)
    scenario.pass_until_resolved()

    assert _pt(scenario, bears) == (3, 3)
    assert bears.damage == 0


def test_throw_from_the_saddle_with_the_biter_gone_deals_no_damage():
    scenario, bears, giant = _throw("Grizzly Bears")
    sources = scenario.untapped_sources("Forest", "Forest", username="alice")
    scenario.cast_onto_stack(
        "Throw from the Saddle", *sources, username="alice", targets=[bears, giant]
    )
    scenario.game.return_to_hand(bears)
    scenario.pass_until_resolved()

    assert giant.damage == 0


def test_throw_from_the_saddle_refuses_your_own_creature_as_the_victim():
    scenario = _board(
        "Throw from the Saddle", ("Forest", "Forest"), mine=("Grizzly Bears", "Brightfield Mustang")
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    mustang = scenario.creature("Brightfield Mustang", "alice")
    with pytest.raises(ValueError):
        scenario.cast("Throw from the Saddle", username="alice", targets=[bears, mustang])


# -- the unconditional neighbours still read as before -------------------------


def test_the_plain_pump_then_fight_pair_is_unchanged():
    lands = ("Forest", "Forest", "Forest")
    scenario = _board("Chelonian Tackle", lands, mine=("Grizzly Bears",), theirs=("Hill Giant",))
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    _cast(scenario, "Chelonian Tackle", lands, bears, giant)

    assert _pt(scenario, bears) == (2, 12)
    assert giant.damage == 2
    assert _notices(scenario) == []


# -- "If it's legendary, it also gains ..." on second printings ----------------
#
# Gimli's Fury: "Target creature gets +3/+2 until end of turn. If it's
# legendary, it also gains trample until end of turn."
# Blessing of Belzenlok: "Target creature gets +2/+1 until end of turn. If it's
# legendary, it also gains lifelink until end of turn."
# The same CR 205.4d condition Ancient Animus asks, read of the creature the
# pump acted on, on a second and third printing (neither a listed card nor in
# an api deck).


def _abilities(scenario, card) -> list[str]:
    return list(scenario.game.characteristics_of(card).abilities)


@pytest.mark.parametrize(
    ("spell", "lands", "keyword", "pump"),
    [
        ("Gimli's Fury", ("Mountain", "Mountain"), "Trample", (5, 4)),
        ("Blessing of Belzenlok", ("Swamp",), "Lifelink", (4, 3)),
    ],
)
def test_a_legendary_creature_gets_the_pump_and_the_keyword(spell, lands, keyword, pump):
    scenario = _board(spell, lands, mine=("Isamaru, Hound of Konda",), theirs=())
    isamaru = scenario.creature("Isamaru, Hound of Konda", "alice")
    sources = scenario.untapped_sources(*lands, username="alice")
    scenario.cast_and_resolve(spell, *sources, username="alice", targets=[isamaru])

    assert _pt(scenario, isamaru) == pump
    assert keyword in _abilities(scenario, isamaru)
    assert _notices(scenario) == []


@pytest.mark.parametrize(
    ("spell", "lands", "keyword", "pump"),
    [
        ("Gimli's Fury", ("Mountain", "Mountain"), "Trample", (5, 4)),
        ("Blessing of Belzenlok", ("Swamp",), "Lifelink", (4, 3)),
    ],
)
def test_a_nonlegendary_creature_gets_the_pump_but_not_the_keyword(spell, lands, keyword, pump):
    scenario = _board(spell, lands, mine=("Grizzly Bears",), theirs=())
    bears = scenario.creature("Grizzly Bears", "alice")
    sources = scenario.untapped_sources(*lands, username="alice")
    scenario.cast_and_resolve(spell, *sources, username="alice", targets=[bears])

    assert _pt(scenario, bears) == pump
    assert keyword not in _abilities(scenario, bears)
    assert _notices(scenario) == []


def test_the_keyword_grant_ends_with_the_turn():
    lands = ("Mountain", "Mountain")
    scenario = _board("Gimli's Fury", lands, mine=("Isamaru, Hound of Konda",), theirs=())
    isamaru = scenario.creature("Isamaru, Hound of Konda", "alice")
    sources = scenario.untapped_sources(*lands, username="alice")
    scenario.cast_and_resolve("Gimli's Fury", *sources, username="alice", targets=[isamaru])
    scenario.game.continuous_effects.end_the_turn(scenario.game)

    assert "Trample" not in _abilities(scenario, isamaru)
    assert _pt(scenario, isamaru) == (2, 2)
