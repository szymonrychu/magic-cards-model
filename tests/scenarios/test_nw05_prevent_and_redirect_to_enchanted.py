"""Life equal to a creature's power with a next-time prevention shield on it,
and a turn-long redirection of damage onto an enchanted creature.

- Dazzling Reflection: "You gain life equal to target creature's power. The
  next time that creature would deal damage this turn, prevent that damage."
- Saving Grace: "When this Aura enters, all damage that would be dealt this
  turn to you and permanents you control is dealt to enchanted creature
  instead."

Second printing: Soul's Grace ("You gain life equal to target creature's
power.", the same reader without the shield). No other legal printing
creates a turn-long redirection onto "enchanted creature" - Pariah and With
Great Power . . . print it as a static ability, which is the replacement
statics reader's, not this one - see MEMORY.md.

Rules verified with `mise run rules:find`:

- **CR 608.2h** - the power is read as the spell resolves.
- **CR 615.1** - prevention effects watch for damage that would be dealt.
- **CR 614.9** - a redirection effect; if the new recipient is no longer on
  the battlefield, the effect does nothing.
- **CR 303.4b** - "enchanted creature" is what the Aura is attached to.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario

LANDS = ["Plains"] * 4 + ["Mountain"] * 2


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


def _main(alice=(), bob=(), hand=()) -> object:
    scenario = (
        Scenario()
        .player("alice", battlefield=[*LANDS, *alice], hand=list(hand))
        .player("bob", battlefield=list(bob))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _outcomes(name: str) -> list[str]:
    return [c.outcome for c in card_support(card(name)).clauses if c.kind != "keyword"]


def test_listed_and_proof_cards_read_handled():
    for name in ("Dazzling Reflection", "Saving Grace", "Soul's Grace"):
        assert set(_outcomes(name)) == {"handled"}, (name, _outcomes(name))


# -- life equal to target creature's power ---------------------------------------


def test_dazzling_reflection_gains_the_power_and_shields_the_next_damage():
    scenario = _main(bob=["Craw Wurm"], hand=["Dazzling Reflection"])
    wurm = scenario.creature("Craw Wurm", "bob")
    scenario.cast_and_resolve("Dazzling Reflection", targets=[wurm], auto=True)
    assert scenario.player("alice").life == 26
    assert scenario.game.deal_damage(scenario.player("alice"), 6, source=wurm) == 0
    assert scenario.player("alice").life == 26
    assert scenario.game.deal_damage(scenario.player("alice"), 6, source=wurm) == 6, (
        "CR 615.1: only the next instance"
    )
    assert scenario.player("alice").life == 20


def test_dazzling_reflection_shield_only_watches_that_creature():
    scenario = _main(bob=["Craw Wurm", "Hill Giant"], hand=["Dazzling Reflection"])
    wurm = scenario.creature("Craw Wurm", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.cast_and_resolve("Dazzling Reflection", targets=[wurm], auto=True)
    assert scenario.game.deal_damage(scenario.player("alice"), 3, source=giant) == 3
    assert scenario.game.deal_damage(scenario.player("alice"), 6, source=wurm) == 0


def test_dazzling_reflection_on_your_own_creature_still_prevents_its_damage():
    scenario = _main(alice=["Hill Giant"], bob=["Grizzly Bears"], hand=["Dazzling Reflection"])
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.cast_and_resolve("Dazzling Reflection", targets=[giant], auto=True)
    assert scenario.player("alice").life == 23
    assert scenario.game.deal_damage(bears, 3, source=giant) == 0
    assert bears.damage == 0


def test_dazzling_reflection_shield_ends_with_the_turn():
    scenario = _main(bob=["Craw Wurm"], hand=["Dazzling Reflection"])
    wurm = scenario.creature("Craw Wurm", "bob")
    scenario.cast_and_resolve("Dazzling Reflection", targets=[wurm], auto=True)
    while scenario.turn.active_player == "alice":
        scenario.advance()
    assert scenario.game.deal_damage(scenario.player("alice"), 6, source=wurm) == 6


def test_dazzling_reflection_illegal_target_does_nothing():
    scenario = _main(bob=["Craw Wurm"], hand=["Dazzling Reflection"])
    wurm = scenario.creature("Craw Wurm", "bob")
    scenario.cast_onto_stack("Dazzling Reflection", targets=[wurm], auto=True)
    scenario.game.sacrifice(wurm)
    scenario.resolve_top()
    assert scenario.player("alice").life == 20
    assert _notices(scenario) == []


def test_souls_grace_proof_gains_life_equal_to_the_power_as_it_resolves():
    scenario = _main(bob=["Craw Wurm"], hand=["Soul's Grace"])
    wurm = scenario.creature("Craw Wurm", "bob")
    scenario.cast_and_resolve("Soul's Grace", targets=[wurm], auto=True)
    assert scenario.player("alice").life == 26
    assert scenario.game.deal_damage(scenario.player("alice"), 6, source=wurm) == 6, (
        "no shield without the second sentence"
    )


def test_souls_grace_zero_power_gains_nothing():
    scenario = _main(bob=["Ornithopter"], hand=["Soul's Grace"])
    wall = scenario.creature("Ornithopter", "bob")
    scenario.cast_and_resolve("Soul's Grace", targets=[wall], auto=True)
    assert scenario.player("alice").life == 20


# -- Saving Grace ------------------------------------------------------------------------


def _saving_grace(alice=("Colossal Dreadmaw", "Grizzly Bears"), bob=("Hill Giant",)):
    scenario = _main(alice=list(alice), bob=list(bob), hand=["Saving Grace"])
    dreadmaw = scenario.creature("Colossal Dreadmaw", "alice")
    scenario.cast_onto_stack("Saving Grace", targets=[dreadmaw], auto=True)
    scenario.resolve_top()
    _drain(scenario)
    return scenario, dreadmaw


def test_saving_grace_redirects_damage_to_you_onto_the_enchanted_creature():
    scenario, dreadmaw = _saving_grace()
    giant = scenario.creature("Hill Giant", "bob")
    scenario.game.deal_damage(scenario.player("alice"), 3, source=giant)
    assert scenario.player("alice").life == 20
    assert dreadmaw.damage == 3


def test_saving_grace_redirects_damage_to_your_other_permanents():
    scenario, dreadmaw = _saving_grace()
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.deal_damage(bears, 2, source=scenario.creature("Hill Giant", "bob"))
    assert bears.damage == 0
    assert dreadmaw.damage == 2


def test_saving_grace_damage_to_the_enchanted_creature_itself_stays_there():
    scenario, dreadmaw = _saving_grace()
    scenario.game.deal_damage(dreadmaw, 4, source=scenario.creature("Hill Giant", "bob"))
    assert dreadmaw.damage == 4


def test_saving_grace_does_not_protect_the_opponent():
    scenario, dreadmaw = _saving_grace()
    giant = scenario.creature("Hill Giant", "bob")
    scenario.game.deal_damage(scenario.player("bob"), 2, source=dreadmaw)
    scenario.game.deal_damage(giant, 2, source=dreadmaw)
    assert scenario.player("bob").life == 18
    assert giant.damage == 2
    assert dreadmaw.damage == 0


def test_saving_grace_lasts_only_this_turn():
    scenario, dreadmaw = _saving_grace()
    while scenario.turn.active_player == "alice":
        scenario.advance()
    scenario.game.deal_damage(
        scenario.player("alice"), 3, source=scenario.creature("Hill Giant", "bob")
    )
    assert scenario.player("alice").life == 17


def test_saving_grace_redirect_does_nothing_once_the_creature_is_gone():
    """CR 614.9: the new recipient left the battlefield, so the damage is
    dealt where it was going."""
    scenario, dreadmaw = _saving_grace()
    scenario.game.sacrifice(dreadmaw)
    scenario.game.deal_damage(
        scenario.player("alice"), 3, source=scenario.creature("Hill Giant", "bob")
    )
    assert scenario.player("alice").life == 17


def test_saving_grace_lethal_redirect_kills_the_enchanted_creature():
    scenario, dreadmaw = _saving_grace(alice=("Colossal Dreadmaw",))
    giant = scenario.creature("Hill Giant", "bob")
    for _ in range(3):
        scenario.game.deal_damage(scenario.player("alice"), 3, source=giant)
    scenario.state_based_actions()
    assert dreadmaw.zone is Zone.GRAVEYARD, "6/9 with 9 damage"
    assert scenario.player("alice").life == 20
