"""Scenario: CR 122.1c shield counters, and Captain America, Super-Soldier's
own conditional group hexproof grant.

Every rule cited here was looked up with `mise run rules:find` in the
session that wrote this file.

- **CR 122.1c** - "One or more shield counters on a permanent create a
  single replacement effect and a single prevention effect that protect the
  permanent. These effects are 'If this permanent would be destroyed as the
  result of an effect, instead remove a shield counter from it' and 'If
  damage would be dealt to this permanent, prevent that damage and remove a
  shield counter from it.'"
- **CR 614.1c** - "[This] enters with [counters]", a replacement effect.
- **CR 702.11b/c** - hexproof, on a permanent and on a player.
- **CR 205.3m** - Hero is a creature type.
- **CR 613.1f** - layer 6, ability-adding and -removing effects.

`tests/scenarios/test_diamond_city_shield_counter.py` already proves CR
122.5's *move* keyword action on a shield counter; this file is CR 122.1c's
own effect, which the pool had no printing to exercise before Captain
America, Super-Soldier.

Captain America's own "Captain America enters with a shield counter on
him." fell through `machines/replacement.py::_ENTERS_WITH` UNPARSED - that
reader's own trailing group only ever reads "on it", and Captain America's
printing uses the gendered pronoun "him" the way `test_keyword_counters.py`'s
own off-pool proofs (Arwen, Mortal Queen; Leatherhead, Swamp Stalker) do
too. `machines/keyword_counters.py::enters_with_counters_pronoun_fallback`
is this task's own fallback for it, called from `Game.enter_the_battlefield`
only when the ordinary pipeline placed nothing at all - see that function's
own docstring for the reasoning and the verified `_ENTERS_WITH.match` call
that found the gap.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.models import Zone

from .harness import Scenario


def _captain_america_on_the_battlefield() -> tuple:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Captain America, Super-Soldier"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cap = scenario.creature("Captain America, Super-Soldier", "alice")
    return scenario, cap


# ---------------------------------------------------------------------------
# CR 614.1c: "Captain America enters with a shield counter on him."
# ---------------------------------------------------------------------------


def test_captain_america_enters_with_a_shield_counter():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Captain America, Super-Soldier"],
            battlefield=["Plains", "Plains", "Plains"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Plains", "Plains", "Plains")

    cap = scenario.cast_and_resolve("Captain America, Super-Soldier", *sources)

    assert cap.counters["shield"] == 1


# ---------------------------------------------------------------------------
# CR 122.1c's own prevention effect: damage.
# ---------------------------------------------------------------------------


def test_shield_counter_prevents_damage_and_is_spent():
    scenario, cap = _captain_america_on_the_battlefield()
    cap.add_counters("shield", 1)

    dealt = scenario.game.deal_damage(cap, 5)

    assert dealt == 0
    assert cap.damage == 0
    assert cap.counters["shield"] == 0


def test_a_second_shield_counter_survives_a_second_instance_of_damage():
    scenario, cap = _captain_america_on_the_battlefield()
    cap.add_counters("shield", 2)

    scenario.game.deal_damage(cap, 3)
    assert cap.counters["shield"] == 1
    assert cap.damage == 0

    scenario.game.deal_damage(cap, 3)
    assert cap.counters["shield"] == 0
    assert cap.damage == 0


def test_damage_lands_once_the_shield_counter_is_gone():
    scenario, cap = _captain_america_on_the_battlefield()
    cap.add_counters("shield", 1)
    scenario.game.deal_damage(cap, 3)
    assert cap.counters["shield"] == 0

    dealt = scenario.game.deal_damage(cap, 3)

    assert dealt == 3
    assert cap.damage == 3


# ---------------------------------------------------------------------------
# CR 122.1c's own replacement effect: destruction.
# ---------------------------------------------------------------------------


def test_shield_counter_replaces_destruction_and_is_spent():
    scenario, cap = _captain_america_on_the_battlefield()
    cap.add_counters("shield", 1)

    scenario.game.destroy(cap)

    assert cap.zone is Zone.BATTLEFIELD
    assert cap.counters["shield"] == 0


def test_captain_america_is_destroyed_once_the_shield_counter_is_gone():
    scenario, cap = _captain_america_on_the_battlefield()
    cap.add_counters("shield", 1)
    scenario.game.destroy(cap)
    assert cap.counters["shield"] == 0

    scenario.game.destroy(cap)

    assert cap.zone is Zone.GRAVEYARD


def test_shield_counter_does_not_stop_sacrifice():
    """CR 701.8b: only "destroy" is destruction - a shield counter's own
    replacement is CR 122.1c's "would be destroyed", which sacrifice never
    is (CR 701.21a: "its controller moves it ... directly to ... the
    graveyard"). `Game.sacrifice` never even consults `has_shield_counter`,
    so one sacrifice call is enough - proving CR 122.1c's own destruction
    replacement never intercepted it (a shield counter that had would have
    left the permanent on the battlefield, exactly as `test_shield_counter_
    replaces_destruction_and_is_spent` shows for `destroy`)."""
    scenario, cap = _captain_america_on_the_battlefield()
    cap.add_counters("shield", 1)

    scenario.game.sacrifice(cap)

    assert cap.zone is Zone.GRAVEYARD


def test_indestructible_and_a_shield_counter_together_leave_the_counter_unspent():
    """CR 702.12b already refuses the destruction outright before this
    task's own shield-counter check ever runs (`Game._destroy_impl`'s own
    ordering) - the same "indestructible wins outright" simplification the
    method already made for regeneration, so the shield counter is not
    spent on a destruction indestructible alone already stopped."""
    scenario, cap = _captain_america_on_the_battlefield()
    cap.add_counters("shield", 1)
    scenario.game.add_counters(cap, "indestructible", 1)

    scenario.game.destroy(cap)

    assert cap.zone is Zone.BATTLEFIELD
    assert cap.counters["shield"] == 1


# ---------------------------------------------------------------------------
# "As long as Captain America has a shield counter on him, you and other
# Heroes you control have hexproof." (CR 702.11b/c, CR 613.1f)
# ---------------------------------------------------------------------------


def test_controller_has_hexproof_while_the_shield_counter_is_on_captain_america():
    scenario, cap = _captain_america_on_the_battlefield()
    cap.add_counters("shield", 1)

    plain, qualities = scenario.game.player_hexproof(scenario.game.player("alice"))

    assert plain is True
    assert qualities == []


def test_controller_loses_hexproof_once_the_shield_counter_is_gone():
    scenario, cap = _captain_america_on_the_battlefield()
    # No shield counter placed at all.
    plain, _ = scenario.game.player_hexproof(scenario.game.player("alice"))
    assert plain is False


def test_other_heroes_the_controller_controls_gain_hexproof():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Captain America, Super-Soldier", "Nick Fury, Agent of S.H.I.E.L.D."],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cap = scenario.creature("Captain America, Super-Soldier", "alice")
    fury = scenario.creature("Nick Fury, Agent of S.H.I.E.L.D.", "alice")  # a Hero
    cap.add_counters("shield", 1)

    assert has_keyword(fury, "hexproof", scenario.game) is True


def test_captain_america_himself_is_excluded_by_other():
    scenario, cap = _captain_america_on_the_battlefield()
    cap.add_counters("shield", 1)

    # "you and OTHER Heroes you control" - Captain America (himself a
    # Hero) does not grant himself hexproof through this static.
    assert has_keyword(cap, "hexproof", scenario.game) is False


def test_a_non_hero_creature_the_controller_controls_does_not_gain_hexproof():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Captain America, Super-Soldier", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cap = scenario.creature("Captain America, Super-Soldier", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    cap.add_counters("shield", 1)

    assert has_keyword(bears, "hexproof", scenario.game) is False


def test_an_opponents_hero_does_not_gain_hexproof_from_someone_elses_captain_america():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Captain America, Super-Soldier"])
        .player("bob", battlefield=["Nick Fury, Agent of S.H.I.E.L.D."])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cap = scenario.creature("Captain America, Super-Soldier", "alice")
    fury = scenario.creature("Nick Fury, Agent of S.H.I.E.L.D.", "bob")
    cap.add_counters("shield", 1)

    assert has_keyword(fury, "hexproof", scenario.game) is False


def test_the_group_hexproof_grant_ends_once_the_shield_counter_is_gone():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Captain America, Super-Soldier", "Nick Fury, Agent of S.H.I.E.L.D."],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cap = scenario.creature("Captain America, Super-Soldier", "alice")
    fury = scenario.creature("Nick Fury, Agent of S.H.I.E.L.D.", "alice")
    cap.add_counters("shield", 1)
    assert has_keyword(fury, "hexproof", scenario.game) is True

    scenario.game.deal_damage(cap, 1)  # consumes the shield counter (CR 122.1c)
    assert cap.counters["shield"] == 0

    assert has_keyword(fury, "hexproof", scenario.game) is False
    plain, _ = scenario.game.player_hexproof(scenario.game.player("alice"))
    assert plain is False
