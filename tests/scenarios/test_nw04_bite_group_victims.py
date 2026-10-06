"""A targeted creature deals damage equal to its power to a group it does not
target: "each other creature [that player controls]" and "each opponent".

- Chandra's Ignition: "Target creature you control deals damage equal to its
  power to each other creature and each opponent."
- Waltz of Rage (proof printing): "Target creature you control deals damage
  equal to its power to each other creature. Until end of turn, whenever a
  creature you control dies, exile the top card of your library. You may play
  it until the end of your next turn."
- Alpha Brawl: "Target creature an opponent controls deals damage equal to its
  power to each other creature that player controls, then each of those
  creatures deals damage equal to its power to that creature."

Rules verified with `mise run rules:find`:

- **CR 115.10/115.10a** - the group is affected without being targeted; it is
  read as the spell resolves.
- **CR 120.3/120.4** - every recipient of one instruction is dealt its damage
  at once; state-based actions wait for the whole spell (**CR 704.3**).
- **CR 608.2b** - the only target is the biter: with it illegal the spell
  does not resolve at all.
- **CR 608.2c** - Alpha Brawl's "then" runs after the first damage; **CR
  608.2h** reads each creature's power as its own damage is dealt, so a
  wither biter's -1/-1 counters shrink what comes back. Creatures dealt lethal
  damage are still on the battlefield until state-based actions, so they
  still deal damage back (Alpha Brawl's Gatherer ruling, 2014-07-18).
- **CR 120.3d** - wither damage to a creature is -1/-1 counters.
"""

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


def _board(spell, lands, mine=(), theirs=(), *, library=()) -> Scenario:
    scenario = (
        Scenario()
        .player("alice", hand=[spell], battlefield=[*lands, *mine], library=list(library))
        .player("bob", battlefield=list(theirs), life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _on_stack(scenario, spell, lands, targets):
    sources = scenario.untapped_sources(*lands, username="alice")
    return scenario.cast_onto_stack(spell, *sources, username="alice", targets=targets)


# -- Chandra's Ignition --------------------------------------------------------

IGNITION = ("Mountain",) * 5


def test_chandras_ignition_hits_every_other_creature_and_each_opponent():
    scenario = _board(
        "Chandra's Ignition",
        IGNITION,
        mine=("Hill Giant", "Grizzly Bears"),
        theirs=("Watchwolf", "Craw Wurm"),
    )
    giant = scenario.creature("Hill Giant", "alice")
    my_bears = scenario.creature("Grizzly Bears", "alice")
    wolf = scenario.creature("Watchwolf", "bob")
    wurm = scenario.creature("Craw Wurm", "bob")
    _on_stack(scenario, "Chandra's Ignition", IGNITION, [giant])
    scenario.pass_until_resolved()

    assert giant.damage == 0  # "each other creature"
    assert my_bears.zone is Zone.GRAVEYARD  # yours too
    assert wolf.zone is Zone.GRAVEYARD
    assert wurm.damage == 3
    assert scenario.player("bob").life == 17
    assert scenario.player("alice").life == 20  # you are not an opponent
    assert _notices(scenario) == []


def test_chandras_ignition_with_its_biter_gone_does_not_resolve():
    scenario = _board("Chandra's Ignition", IGNITION, mine=("Hill Giant",), theirs=("Watchwolf",))
    giant = scenario.creature("Hill Giant", "alice")
    wolf = scenario.creature("Watchwolf", "bob")
    _on_stack(scenario, "Chandra's Ignition", IGNITION, [giant])
    scenario.game.return_to_hand(giant)
    scenario.pass_until_resolved()

    assert wolf.damage == 0
    assert scenario.player("bob").life == 20


def test_chandras_ignition_lifelink_biter_gains_for_every_recipient():
    """CR 120.3f: each recipient's damage is lifelink damage."""
    scenario = _board(
        "Chandra's Ignition",
        IGNITION,
        mine=("Vampire Nighthawk",),
        theirs=("Watchwolf", "Grizzly Bears"),
    )
    nighthawk = scenario.creature("Vampire Nighthawk", "alice")
    _on_stack(scenario, "Chandra's Ignition", IGNITION, [nighthawk])
    scenario.pass_until_resolved()

    assert scenario.player("alice").life == 26  # 2 + 2 + 2
    assert scenario.player("bob").life == 18


# -- Waltz of Rage (proof printing) --------------------------------------------

WALTZ = ("Mountain",) * 5


def test_waltz_of_rage_bites_each_other_creature_but_no_player():
    scenario = _board(
        "Waltz of Rage",
        WALTZ,
        mine=("Hill Giant", "Giant Spider"),
        theirs=("Craw Wurm",),
        library=("Mountain", "Forest"),
    )
    giant = scenario.creature("Hill Giant", "alice")
    spider = scenario.creature("Giant Spider", "alice")
    wurm = scenario.creature("Craw Wurm", "bob")
    _on_stack(scenario, "Waltz of Rage", WALTZ, [giant])
    scenario.pass_until_resolved()

    assert giant.damage == 0
    assert spider.damage == 3
    assert wurm.damage == 3
    assert scenario.player("bob").life == 20
    assert _notices(scenario) == []


# -- Alpha Brawl ---------------------------------------------------------------

BRAWL = ("Mountain",) * 8


def test_alpha_brawl_target_hits_its_controllers_other_creatures_then_they_hit_back():
    scenario = _board(
        "Alpha Brawl",
        BRAWL,
        mine=("Grizzly Bears",),
        theirs=("Craw Wurm", "Giant Spider", "Watchwolf"),
    )
    wurm = scenario.creature("Craw Wurm", "bob")
    spider = scenario.creature("Giant Spider", "bob")
    wolf = scenario.creature("Watchwolf", "bob")
    my_bears = scenario.creature("Grizzly Bears", "alice")
    _on_stack(scenario, "Alpha Brawl", BRAWL, [wurm])
    scenario.pass_until_resolved()

    # Both were dealt 6 - lethal - and still hit back for 2 + 3 before
    # state-based actions saw any of it.
    assert {wurm.zone, spider.zone, wolf.zone} == {Zone.GRAVEYARD}
    assert my_bears.damage == 0  # "that player controls"
    assert _notices(scenario) == []


def test_alpha_brawl_lethally_damaged_creature_still_hits_back():
    scenario = _board("Alpha Brawl", BRAWL, theirs=("Craw Wurm", "Grizzly Bears"))
    wurm = scenario.creature("Craw Wurm", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    _on_stack(scenario, "Alpha Brawl", BRAWL, [wurm])
    scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD
    assert wurm.damage == 2


def test_alpha_brawl_retaliation_reads_power_after_the_first_damage():
    """A wither biter's -1/-1 counters (CR 120.3d) shrink the creature that
    hits back: Giant Spider 2/4 becomes -1/1 and deals no damage."""
    scenario = _board("Alpha Brawl", BRAWL, theirs=("Boggart Ram-Gang", "Giant Spider"))
    gang = scenario.creature("Boggart Ram-Gang", "bob")
    spider = scenario.creature("Giant Spider", "bob")
    _on_stack(scenario, "Alpha Brawl", BRAWL, [gang])
    scenario.pass_until_resolved()

    assert spider.counters.power_toughness_modifier == -3
    assert gang.damage == 0
    assert gang.zone is Zone.BATTLEFIELD


def test_alpha_brawl_with_no_other_creature_does_nothing():
    scenario = _board("Alpha Brawl", BRAWL, mine=("Grizzly Bears",), theirs=("Craw Wurm",))
    wurm = scenario.creature("Craw Wurm", "bob")
    bears = scenario.creature("Grizzly Bears", "alice")
    _on_stack(scenario, "Alpha Brawl", BRAWL, [wurm])
    scenario.pass_until_resolved()

    assert wurm.damage == 0
    assert bears.damage == 0
    assert _notices(scenario) == []


def test_alpha_brawl_with_its_target_gone_does_not_resolve():
    scenario = _board("Alpha Brawl", BRAWL, theirs=("Craw Wurm", "Hill Giant"))
    wurm = scenario.creature("Craw Wurm", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    _on_stack(scenario, "Alpha Brawl", BRAWL, [wurm])
    scenario.game.return_to_hand(wurm)
    scenario.pass_until_resolved()

    assert giant.damage == 0
