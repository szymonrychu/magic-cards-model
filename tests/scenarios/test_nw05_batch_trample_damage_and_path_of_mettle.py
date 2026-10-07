"""A batched combat-damage trigger restricted to creatures with trample, and
Path of Mettle's keyword-list group, keyword-list attack trigger and random
destroy.

- Quartzwood Crasher: "Whenever one or more creatures you control with
  trample deal combat damage to a player, create an X/X green Dinosaur Beast
  creature token with trample, where X is the amount of damage those
  creatures dealt to that player."
- Path of Mettle: "When Path of Mettle enters, it deals 1 damage to each
  creature that doesn't have first strike, double strike, vigilance, or
  haste." / "Whenever you attack with at least two creatures that have first
  strike, double strike, vigilance, and/or haste, transform Path of Mettle."
- Metzali, Tower of Triumph: "{2}{W}, {T}: Choose a creature at random that
  attacked this turn. Destroy that creature."

No other legal printing carries "the amount of damage those creatures dealt
to that player", "each creature that doesn't have <keyword list>", "attack
with at least two creatures that have <keyword list>" or "a creature at
random that attacked this turn" - see MEMORY.md.

Rules verified with `mise run rules:find`:

- **CR 603.2c** - one combat damage step's damage is one event: one trigger.
- **CR 120.3** - each creature's damage is its own; X sums those that count.
- **CR 508.1** - declaring attackers; "attacked this turn" is a declared one.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.effects import transform_permanent
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario

PATH = "Path of Mettle // Metzali, Tower of Triumph"


def _drain(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _notices(scenario) -> list[object]:
    game = scenario.game
    found: list[object] = list(game.continuous_effects.layer_notices)
    for name in type(game).model_fields:
        if name.endswith("_notices"):
            found.extend(getattr(game, name))
    return found


def _on_battlefield(scenario, name: str) -> bool:
    return any(permanent.name == name for permanent in scenario.game.battlefield)


def _outcomes(name: str) -> list[str]:
    return [c.outcome for c in card_support(card(name)).clauses if c.kind != "keyword"]


def test_listed_cards_read_handled():
    for name in ("Quartzwood Crasher", PATH):
        assert set(_outcomes(name)) == {"handled"}, (name, _outcomes(name))


# -- Quartzwood Crasher -------------------------------------------------------------


def _combat(alice: list[str], bob: list[str]):
    scenario = Scenario().player("alice", battlefield=alice).player("bob", battlefield=bob).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario


def _dinosaurs(scenario) -> list:
    return [
        p
        for p in scenario.game.battlefield
        if p.token and "Dinosaur" in p.card.type_line and p.controller == "alice"
    ]


def test_quartzwood_one_trigger_for_every_trampler_x_is_their_total():
    scenario = _combat(["Quartzwood Crasher", "Colossal Dreadmaw"], [])
    attackers = scenario.creatures("Quartzwood Crasher", "Colossal Dreadmaw", username="alice")
    scenario.attack_with(*attackers)
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.game.put_triggers_on_stack()
    assert len(scenario.game.stack) == 1, "CR 603.2c: one batch, one trigger"
    _drain(scenario)
    (token,) = _dinosaurs(scenario)
    assert scenario.game.power_of(token) == 12 and scenario.game.toughness_of(token) == 12
    assert scenario.player("bob").life == 8


def test_quartzwood_ignores_damage_from_creatures_without_trample():
    scenario = _combat(["Quartzwood Crasher", "Hill Giant"], [])
    scenario.attack_with(*scenario.creatures("Quartzwood Crasher", "Hill Giant", username="alice"))
    scenario.no_blocks()
    scenario.combat_damage()
    _drain(scenario)
    (token,) = _dinosaurs(scenario)
    assert scenario.game.power_of(token) == 6, "the Giant's 3 is not trample damage"


def test_quartzwood_counts_only_the_trample_damage_that_reached_the_player():
    scenario = _combat(["Quartzwood Crasher"], ["Grizzly Bears"])
    crasher = scenario.creature("Quartzwood Crasher", "alice")
    scenario.attack_with(crasher)
    scenario.block(crasher, scenario.creature("Grizzly Bears", "bob"))
    scenario.combat_damage()
    _drain(scenario)
    (token,) = _dinosaurs(scenario)
    assert scenario.game.power_of(token) == 4
    assert scenario.player("bob").life == 16


def test_quartzwood_no_trigger_without_trample_damage_to_a_player():
    scenario = _combat(["Quartzwood Crasher", "Hill Giant"], ["Giant Spider"])
    crasher = scenario.creature("Quartzwood Crasher", "alice")
    scenario.attack_with(scenario.creature("Hill Giant", "alice"))
    scenario.no_blocks()
    scenario.combat_damage()
    _drain(scenario)
    assert _dinosaurs(scenario) == []
    assert crasher.zone is Zone.BATTLEFIELD


# -- Path of Mettle ---------------------------------------------------------------------


def test_path_of_mettle_pings_each_creature_without_the_keywords():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[PATH],
            battlefield=["Grizzly Bears", "Serra Angel", "Youthful Knight", "Raging Goblin"],
        )
        .player("bob", battlefield=["Hill Giant", "Giant Spider"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield(PATH, "alice")
    _drain(scenario)
    damaged = {
        name: scenario.creature(name, owner).damage
        for name, owner in (
            ("Serra Angel", "alice"),
            ("Youthful Knight", "alice"),
            ("Raging Goblin", "alice"),
            ("Hill Giant", "bob"),
            ("Giant Spider", "bob"),
        )
    }
    assert damaged == {
        "Serra Angel": 0,
        "Youthful Knight": 0,
        "Raging Goblin": 0,
        "Hill Giant": 1,
        "Giant Spider": 1,
    }
    assert scenario.creature("Grizzly Bears", "alice").damage == 1


def _attack_with_path(attackers: list[str]):
    scenario = (
        Scenario()
        .player("alice", battlefield=[PATH, *attackers, "Plains", "Plains", "Plains"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(*[scenario.creature(name, "alice") for name in attackers])
    _drain(scenario)
    return scenario, scenario.find(PATH, Zone.BATTLEFIELD)


def test_path_of_mettle_transforms_when_two_keyworded_creatures_attack():
    scenario, path = _attack_with_path(["Serra Angel", "Youthful Knight"])
    assert path.transformed is True
    assert _notices(scenario) == []


def test_path_of_mettle_counts_any_mix_of_the_listed_keywords():
    scenario, path = _attack_with_path(["Raging Goblin", "Youthful Knight", "Grizzly Bears"])
    assert path.transformed is True


def test_path_of_mettle_does_not_transform_with_one_keyworded_attacker():
    scenario, path = _attack_with_path(["Serra Angel", "Grizzly Bears", "Hill Giant"])
    assert path.transformed is False


# -- Metzali: a random attacker -----------------------------------------------------------


def _metzali_after_attack(attackers: list[str], others: list[str] = ()):
    scenario, path = _attack_with_path(attackers + list(others))
    scenario.no_blocks()
    scenario.combat_damage()
    while scenario.step is not Step.POSTCOMBAT_MAIN:
        scenario.advance()
        _drain(scenario)
    return scenario, path


def test_metzali_destroys_one_creature_that_attacked_this_turn():
    scenario, metzali = _metzali_after_attack(["Serra Angel", "Youthful Knight"])
    assert metzali.transformed is True
    scenario.activate(metzali, *scenario.untapped_sources("Plains", "Plains", "Plains"), index=2)
    _drain(scenario)
    alive = [name for name in ("Serra Angel", "Youthful Knight") if _on_battlefield(scenario, name)]
    assert len(alive) == 1
    assert _notices(scenario) == []


def test_metzali_never_picks_a_creature_that_did_not_attack():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[PATH, "Serra Angel", "Youthful Knight", "Grizzly Bears"] + ["Plains"] * 3,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(
        scenario.creature("Serra Angel", "alice"), scenario.creature("Youthful Knight", "alice")
    )
    _drain(scenario)
    scenario.no_blocks()
    scenario.combat_damage()
    while scenario.step is not Step.POSTCOMBAT_MAIN:
        scenario.advance()
        _drain(scenario)
    metzali = scenario.find(PATH, Zone.BATTLEFIELD)
    scenario.activate(metzali, *scenario.untapped_sources("Plains", "Plains", "Plains"), index=2)
    _drain(scenario)
    assert scenario.creature("Grizzly Bears", "alice").zone is Zone.BATTLEFIELD


def test_metzali_with_no_attacker_this_turn_destroys_nothing():
    scenario = (
        Scenario()
        .player("alice", battlefield=[PATH, "Grizzly Bears", "Plains", "Plains", "Plains"])
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    path = scenario.find(PATH, Zone.BATTLEFIELD)
    transform_permanent(scenario.game, path)
    scenario.activate(path, *scenario.untapped_sources("Plains", "Plains", "Plains"), index=2)
    _drain(scenario)
    assert scenario.creature("Grizzly Bears", "alice").zone is Zone.BATTLEFIELD
    assert scenario.creature("Hill Giant", "bob").zone is Zone.BATTLEFIELD


def test_metzali_choice_is_random_not_always_the_same_attacker():
    """Different games (different seeds) pick different attackers; within one
    game the pick is seeded, which the conftest replay check proves byte for
    byte on every Metzali scenario here."""
    picks = set()
    for _ in range(12):
        scenario, metzali = _metzali_after_attack(
            ["Serra Angel", "Youthful Knight", "Raging Goblin"]
        )
        scenario.activate(
            metzali, *scenario.untapped_sources("Plains", "Plains", "Plains"), index=2
        )
        _drain(scenario)
        gone = [
            name
            for name in ("Serra Angel", "Youthful Knight", "Raging Goblin")
            if not _on_battlefield(scenario, name)
        ]
        assert len(gone) == 1
        picks.add(gone[0])
    assert len(picks) >= 2
