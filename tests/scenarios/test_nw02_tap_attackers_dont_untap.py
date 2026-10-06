"""A group tap followed by "Those creatures don't untap during <whose> next
untap step.", the group being every creature the first sentence applied to.

Rules verified with `mise run rules:find`:

- **CR 701.26a** - "Only untapped permanents can be tapped": an attacker that
  is already tapped is simply not tapped again, but it is still one of the
  creatures the instruction applied to.
- **CR 502.3** - the untap step: "effects can keep one or more of a player's
  permanents from untapping". The effect is checked in the untap step of the
  creature's own controller, which is "their controller's next untap step".
- **CR 608.2c** - the instructions are followed in the order written, and a
  conditional first sentence (Fateful hour is an ability word, CR 207.2c)
  gates the "those creatures" that follow it.
- **CR 611.2c** - the set of creatures is fixed when the effect begins; a
  creature that attacks or arrives later is not in it.
- **CR 506.4b** - tapping a creature already declared as an attacker does not
  remove it from combat.

Reported card: Clinging Mists (Fateful hour, "tap all attacking creatures").
Second printing: Sleep ("Tap all creatures target player controls. Those
creatures don't untap during that player's next untap step."), which proves
the same rider on a different group phrase. Snow Day is the regression check
for the targeted version that already read.
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


def _mists_board(bob_life: int) -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Serra Angel", "Grizzly Bears", "Goblin Guide", "Hill Giant"],
        )
        .player(
            "bob",
            life=bob_life,
            hand=["Clinging Mists"],
            battlefield=["Forest", "Forest", "Forest", "Gray Ogre"],
        )
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario


def _attack_and_mist(scenario) -> dict[str, object]:
    angel = scenario.creature("Serra Angel", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    goblin = scenario.creature("Goblin Guide", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    scenario.attack_with(angel, bears, goblin)
    scenario.pass_priority("alice")
    sources = scenario.untapped_sources("Forest", "Forest", "Forest", username="bob")
    scenario.cast_and_resolve("Clinging Mists", *sources, username="bob")
    return {"angel": angel, "bears": bears, "goblin": goblin, "giant": giant}


def test_fateful_hour_taps_the_vigilant_attacker_and_holds_every_attacker_down():
    scenario = _mists_board(bob_life=5)
    creatures = _attack_and_mist(scenario)
    angel, bears, goblin, giant = (creatures[k] for k in ("angel", "bears", "goblin", "giant"))

    # Serra Angel's vigilance kept it untapped through the attack; the spell taps it.
    assert angel.tapped and bears.tapped and goblin.tapped
    assert angel.exerted and bears.exerted and goblin.exerted
    assert not giant.exerted
    assert _notices(scenario) == []

    # CR 506.4b: tapping an attacker does not take it out of combat.
    assert {c.id for c in scenario.attackers()} == {angel.id, bears.id, goblin.id}

    # Alice's next untap step: the three attackers stay tapped, the rest untaps.
    giant.tap()
    scenario.game.untap_step()
    assert angel.tapped and bears.tapped and goblin.tapped
    assert giant.untapped
    assert not angel.exerted

    # CR 502.3: only the next untap step is affected.
    scenario.game.untap_step()
    assert angel.untapped and bears.untapped and goblin.untapped


def test_clinging_mists_above_five_life_taps_nothing_and_holds_nothing_down():
    scenario = _mists_board(bob_life=6)
    creatures = _attack_and_mist(scenario)
    angel, bears = creatures["angel"], creatures["bears"]

    assert angel.untapped  # vigilance, and the gated tap never happened
    assert not angel.exerted and not bears.exerted
    assert _notices(scenario) == []
    scenario.game.untap_step()
    assert bears.untapped


def test_clinging_mists_still_prevents_all_combat_damage_at_any_life_total():
    scenario = _mists_board(bob_life=5)
    _attack_and_mist(scenario)
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.player("bob").life == 5


def test_a_creature_that_was_not_attacking_is_not_held_down():
    scenario = _mists_board(bob_life=3)
    creatures = _attack_and_mist(scenario)
    giant = creatures["giant"]
    ogre = scenario.creature("Gray Ogre", "bob")

    assert giant.untapped and not giant.exerted
    assert ogre.untapped and not ogre.exerted


def test_the_hold_belongs_to_the_creatures_controller_untap_step_not_the_casters():
    scenario = _mists_board(bob_life=5)
    creatures = _attack_and_mist(scenario)
    bears = creatures["bears"]

    # Bob's own untap step is not "their controller's" untap step for Alice's creatures.
    scenario.player("bob").untap_all(scenario.game.permanents_controlled_by("bob"))
    assert bears.tapped and bears.exerted

    scenario.player("alice").untap_all(scenario.game.permanents_controlled_by("alice"))
    assert bears.tapped and not bears.exerted


def test_a_creature_that_left_the_battlefield_is_not_remembered():
    """CR 400.7: a new object has no memory of the effect."""
    scenario = _mists_board(bob_life=5)
    creatures = _attack_and_mist(scenario)
    goblin = creatures["goblin"]

    scenario.game.return_to_hand(goblin)
    assert goblin.zone is Zone.HAND
    assert not goblin.exerted


# -- second printing: Sleep ---------------------------------------------------


def _sleep_board() -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Sleep"],
            battlefield=["Island", "Island", "Island", "Island", "Serra Angel"],
        )
        .player(
            "bob", hand=["Gray Ogre"], battlefield=["Grizzly Bears", "Goblin Guide", "Hill Giant"]
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_sleep_taps_every_creature_the_target_player_controls_and_holds_them_down():
    scenario = _sleep_board()
    bears = scenario.creature("Grizzly Bears", "bob")
    goblin = scenario.creature("Goblin Guide", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    angel = scenario.creature("Serra Angel", "alice")
    goblin.tap()  # CR 701.26a: already tapped, still one of "those creatures"

    sources = scenario.untapped_sources("Island", "Island", "Island", "Island")
    scenario.cast_and_resolve("Sleep", *sources, targets=["bob"])

    assert bears.tapped and goblin.tapped and giant.tapped
    assert bears.exerted and goblin.exerted and giant.exerted
    assert not angel.exerted
    assert _notices(scenario) == []

    scenario.player("bob").untap_all(scenario.game.permanents_controlled_by("bob"))
    assert bears.tapped and goblin.tapped and giant.tapped

    scenario.player("bob").untap_all(scenario.game.permanents_controlled_by("bob"))
    assert bears.untapped and goblin.untapped and giant.untapped


def test_sleep_does_not_hold_down_a_creature_that_arrives_afterwards():
    """CR 611.2c: the set is fixed when the effect begins."""
    scenario = _sleep_board()
    sources = scenario.untapped_sources("Island", "Island", "Island", "Island")
    scenario.cast_and_resolve("Sleep", *sources, targets=["bob"])

    late = scenario.put_onto_battlefield("Gray Ogre", username="bob")
    assert late.untapped and not late.exerted


# -- regression: Snow Day already read the targeted version ---------------------


def test_snow_day_still_taps_two_targets_and_holds_them_down():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Snow Day"],
            battlefield=["Island"] * 6 + ["Grizzly Bears", "Goblin Guide"],
            library=["Forest", "Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    goblin = scenario.creature("Goblin Guide", "alice")
    sources = scenario.untapped_sources(*["Island"] * 6)
    scenario.cast_and_resolve("Snow Day", *sources, targets=[bears, goblin])

    assert bears.exerted and goblin.exerted and bears.tapped and goblin.tapped
