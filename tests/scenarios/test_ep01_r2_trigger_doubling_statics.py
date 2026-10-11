"""Trigger multipliers (CR 603.2d) and trigger suppression beyond Panharmonicon
(EP-01 round 2, T8).

Rules read whole with `mise run rules:find` in the session that wrote this:

- **CR 603.2d** - "An ability may state that a triggered ability triggers
  additional times. In this case, rather than simply determining that such an
  ability has triggered, determine how many times it should trigger, then
  trigger it that many times."
- **CR 603.10a** - leaves-the-battlefield and dies abilities look back in time,
  so a dying creature's own "when this dies" ability is doubled by Teysa Karlov.
- **CR 309.4c** - a room ability triggers when the venture marker moves in.

Printings: Teysa Karlov and Drivnod, Carnage Dominus ("a creature dying"),
Isshin, Two Heavens as One ("a creature attacking"), Gandalf the White ("a
legendary permanent or an artifact entering or leaving"), Delney, Streetwise
Lookout (power 2 or less), Echoes of Eternity (colorless spell / permanent),
Sanctum of All (six Shrines), Hama Pashar, Ruin Seeker (room abilities) and
Hushbringer (entering or dying cause nothing).
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import AbilityKind
from magic_cards_model.machines.dungeon import venture
from tests.scenarios.harness import Scenario

SHRINES = [
    "Sanctum of All",
    "Honden of Seeing Winds",
    "Honden of Life's Web",
    "Honden of Infinite Rage",
    "Sanctum of Fruitful Harvest",
    "Sanctum of Tranquil Light",
]


def _board(alice, *, bob=(), hand=(), step=Step.PRECOMBAT_MAIN):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=list(alice),
            hand=[*hand, "Lightning Bolt"],
            library=["Plains"] * 12,
        )
        .player("bob", battlefield=list(bob), library=["Plains"] * 12)
        .build()
    )
    scenario.start_at(step)
    return scenario


def _triggers_from(scenario, source) -> list:
    return [
        item
        for item in [*scenario.pending_triggers, *scenario.game.stack]
        if getattr(item, "kind", None) is AbilityKind.TRIGGERED
        and getattr(item, "source_id", None) == source.id
    ]


def _resolve_all(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.pass_until_resolved()


def _kill(scenario, victim, *, username="alice"):
    other = "bob" if username == "alice" else "alice"
    assert other
    scenario.cast_onto_stack(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username=username)[:1],
        username=username,
        targets=[victim],
    )
    scenario.pass_until_resolved()
    scenario.state_based_actions()


def _all_named(scenario, name):
    return [c for c in scenario.game.battlefield if c.name == name]


# ---- "a creature dying" (Teysa Karlov, Drivnod) -------------------------------


def test_teysa_doubles_a_dies_trigger_of_my_permanent():
    scenario = _board(["Teysa Karlov", "Blood Artist", "Grizzly Bears", "Mountain"])
    artist = scenario.creature("Blood Artist", "alice")
    _kill(scenario, scenario.creature("Grizzly Bears", "alice"))
    assert len(_triggers_from(scenario, artist)) == 2


def test_drivnod_doubles_it_too_and_two_of_them_stack():
    scenario = _board(
        ["Drivnod, Carnage Dominus", "Teysa Karlov", "Blood Artist", "Grizzly Bears", "Mountain"]
    )
    artist = scenario.creature("Blood Artist", "alice")
    _kill(scenario, scenario.creature("Grizzly Bears", "alice"))
    assert len(_triggers_from(scenario, artist)) == 3


def test_the_dying_creatures_own_trigger_is_doubled_by_looking_back():
    scenario = _board(["Teysa Karlov", "Dynamite Diver", "Mountain"])
    diver = scenario.creature("Dynamite Diver", "alice")
    scenario.will_choose_targets("bob")
    _kill(scenario, diver)
    assert len(_triggers_from(scenario, diver)) == 2


def test_a_non_dying_cause_is_not_doubled_by_teysa():
    scenario = _board(["Teysa Karlov", "Soul Warden", "Mountain"], hand=["Grizzly Bears"])
    warden = scenario.creature("Soul Warden", "alice")
    scenario.put_onto_battlefield("Grizzly Bears", username="alice")
    assert len(_triggers_from(scenario, warden)) == 1


def test_teysa_does_not_double_an_opponents_permanents():
    scenario = _board(["Teysa Karlov", "Grizzly Bears", "Mountain"], bob=["Blood Artist"])
    artist = scenario.creature("Blood Artist", "bob")
    _kill(scenario, scenario.creature("Grizzly Bears", "alice"))
    assert len(_triggers_from(scenario, artist)) == 1


# ---- "a creature attacking" (Isshin) ------------------------------------------


def test_isshin_doubles_an_attack_trigger_of_mine():
    scenario = _board(["Isshin, Two Heavens as One", "Screeching Soulbreaker"])
    soulbreaker = scenario.creature("Screeching Soulbreaker", "alice")
    soulbreaker.summoning_sick = False
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(soulbreaker)
    assert len(_triggers_from(scenario, soulbreaker)) == 2
    bob_life = scenario.game.player("bob").life
    _resolve_all(scenario)
    assert scenario.game.player("bob").life == bob_life - 2


def test_isshin_does_not_double_a_non_attack_trigger():
    scenario = _board(["Isshin, Two Heavens as One", "Soul Warden"], hand=["Grizzly Bears"])
    warden = scenario.creature("Soul Warden", "alice")
    scenario.put_onto_battlefield("Grizzly Bears", username="alice")
    assert len(_triggers_from(scenario, warden)) == 1


def test_without_isshin_an_attack_trigger_happens_once():
    scenario = _board(["Screeching Soulbreaker"])
    soulbreaker = scenario.creature("Screeching Soulbreaker", "alice")
    soulbreaker.summoning_sick = False
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(soulbreaker)
    assert len(_triggers_from(scenario, soulbreaker)) == 1


# ---- "a legendary permanent or an artifact entering or leaving" (Gandalf) ------


def test_gandalf_doubles_for_a_legendary_or_artifact_entering():
    scenario = _board(["Gandalf the White", "Soul Warden"], hand=["Ornithopter"])
    warden = scenario.creature("Soul Warden", "alice")
    scenario.put_onto_battlefield("Ornithopter", username="alice")
    assert len(_triggers_from(scenario, warden)) == 2


def test_gandalf_does_not_double_for_a_plain_creature_entering():
    scenario = _board(["Gandalf the White", "Soul Warden"], hand=["Grizzly Bears"])
    warden = scenario.creature("Soul Warden", "alice")
    scenario.put_onto_battlefield("Grizzly Bears", username="alice")
    assert len(_triggers_from(scenario, warden)) == 1


def test_gandalf_doubles_for_a_legendary_creature_dying_but_not_a_plain_one():
    scenario = _board(["Gandalf the White", "Blood Artist", "Isamaru, Hound of Konda", "Mountain"])
    artist = scenario.creature("Blood Artist", "alice")
    _kill(scenario, scenario.creature("Isamaru, Hound of Konda", "alice"))
    assert len(_triggers_from(scenario, artist)) == 2


# ---- stat and colour qualified sources (Delney, Echoes of Eternity) -----------


def test_delney_doubles_a_small_creatures_trigger_not_a_big_ones():
    scenario = _board(
        ["Delney, Streetwise Lookout", "Soul Warden", "Mayhem Devil"], hand=["Grizzly Bears"]
    )
    warden = scenario.creature("Soul Warden", "alice")
    scenario.put_onto_battlefield("Grizzly Bears", username="alice")
    assert len(_triggers_from(scenario, warden)) == 2


def test_delney_ignores_a_creature_with_power_three_or_more():
    scenario = _board(
        ["Delney, Streetwise Lookout", "Screeching Soulbreaker", "Rampaging Brontodon"]
    )
    small = scenario.creature("Screeching Soulbreaker", "alice")
    big = scenario.creature("Rampaging Brontodon", "alice")
    assert scenario.game.power_of(big) >= 3
    small.summoning_sick = big.summoning_sick = False
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(small, big)
    assert len(_triggers_from(scenario, small)) == 2
    assert len(_triggers_from(scenario, big)) == 1


def test_echoes_doubles_a_colorless_permanents_trigger_not_a_colored_ones():
    scenario = _board(["Echoes of Eternity", "Solemn Simulacrum", "Blood Artist", "Mountain"])
    solemn = scenario.creature("Solemn Simulacrum", "alice")
    artist = scenario.creature("Blood Artist", "alice")
    scenario.will_choose_targets("bob")
    _kill(scenario, solemn)
    assert len(_triggers_from(scenario, solemn)) == 2
    assert len(_triggers_from(scenario, artist)) == 1


# ---- count gate (Sanctum of All) ----------------------------------------------


def _upkeep_triggers(scenario, name):
    return len(
        _triggers_from(scenario, next(c for c in scenario.game.battlefield if c.name == name))
    )


def test_sanctum_of_all_doubles_another_shrine_with_six_shrines():
    scenario = _board(SHRINES, step=Step.UNTAP)
    scenario.advance()
    assert _upkeep_triggers(scenario, "Honden of Seeing Winds") == 2


def test_sanctum_of_all_does_not_double_with_only_five_shrines():
    scenario = _board(SHRINES[:5], step=Step.UNTAP)
    scenario.advance()
    assert _upkeep_triggers(scenario, "Honden of Seeing Winds") == 1


def test_sanctum_of_all_never_doubles_itself():
    scenario = _board(SHRINES, step=Step.UNTAP)
    scenario.advance()
    assert _upkeep_triggers(scenario, "Sanctum of All") == 1


# ---- room abilities (Hama Pashar) ---------------------------------------------


def test_hama_pashar_makes_a_room_ability_trigger_twice():
    scenario = _board(["Hama Pashar, Ruin Seeker"])
    scenario.will_choose_mode("Tomb of Annihilation", username="alice")
    venture(scenario.game, "alice", source_name="test")
    scenario.game.put_triggers_on_stack()
    assert len(scenario.game.stack) == 2
    life = scenario.game.player("alice").life
    _resolve_all(scenario)
    assert scenario.game.player("alice").life == life - 2


def test_a_room_ability_triggers_once_without_hama_pashar():
    scenario = _board([])
    scenario.will_choose_mode("Tomb of Annihilation", username="alice")
    venture(scenario.game, "alice", source_name="test")
    scenario.game.put_triggers_on_stack()
    assert len(scenario.game.stack) == 1


# ---- suppression (Hushbringer) ------------------------------------------------


def test_hushbringer_stops_enters_and_dies_triggers_for_creatures():
    scenario = _board(
        ["Hushbringer", "Soul Warden", "Blood Artist", "Mountain"], hand=["Grizzly Bears"]
    )
    warden = scenario.creature("Soul Warden", "alice")
    artist = scenario.creature("Blood Artist", "alice")
    scenario.put_onto_battlefield("Grizzly Bears", username="alice")
    assert not _triggers_from(scenario, warden)
    _kill(scenario, scenario.creature("Grizzly Bears", "alice"))
    assert not _triggers_from(scenario, artist)


def test_hushbringer_does_not_stop_an_artifact_that_is_not_a_creature():
    scenario = _board(["Hushbringer", "Soul Warden"], hand=["Mind Stone"])
    warden = scenario.creature("Soul Warden", "alice")
    scenario.put_onto_battlefield("Mind Stone", username="alice")
    assert len(_triggers_from(scenario, warden)) == 0, "Soul Warden reads creatures only"


def test_echoes_doubles_the_cast_trigger_of_a_colorless_spell():
    """Desolation Twin is a colorless spell: its "when you cast this spell"
    trigger is a triggered ability of a colorless spell you control."""
    scenario = _board(["Echoes of Eternity", *["Mountain"] * 10], hand=["Desolation Twin"])
    scenario.cast_onto_stack("Desolation Twin", *scenario.untapped_sources(*["Mountain"] * 10))
    twin = next(c for c in scenario.game.spells_on_stack if c.name == "Desolation Twin")
    assert len(_triggers_from(scenario, twin)) == 2


def test_a_colored_spell_cast_trigger_is_not_doubled_by_echoes():
    scenario = _board(
        ["Echoes of Eternity", "Forest", "Island", "Mountain"], hand=["Shardless Agent"]
    )
    sources = [
        *scenario.untapped_sources("Forest"),
        *scenario.untapped_sources("Island"),
        *scenario.untapped_sources("Mountain"),
    ]
    scenario.cast_onto_stack("Shardless Agent", *sources)
    agent = next(c for c in scenario.game.spells_on_stack if c.name == "Shardless Agent")
    assert len(_triggers_from(scenario, agent)) == 1
