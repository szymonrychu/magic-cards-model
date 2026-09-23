"""The `TriggerEvent.LOYALTY_ABILITY_ACTIVATED` condition, read off "Whenever
you activate a loyalty ability" (Ajani Unrelenting's own token trigger) and
"Whenever an opponent activates a loyalty ability" (Gideon the Oathless's
damage trigger) - the same underlying event, checked from each side. Also
Ajani Unrelenting's own `-3`, a damage-each-creature-except-tokens-you-control
sweep.

Nothing watched a loyalty ability being activated before this: `Game.
activate_ability`'s own CR 606.3 once-per-turn bookkeeping
(`loyalty_activations`) counted it, but raised no event `machines/triggers.py`
could match a condition against.

Verified this session with `knowledge_search(q="...", type="rules")` and
cross-checked with `mise run rules:find` (on-disk CR effective 2026-09-25):

- **CR 606.3** - activating a loyalty ability, and the once-per-turn
  restriction it is subject to.
- **CR 603.2** - a triggered ability triggers whenever the game state
  matches the event it describes, including another ability's own
  activation.
- **CR 611.2c** - a resolving ability's continuous effect fixes the set of
  objects it affects as it begins: the Cadet the trigger made first gets the
  `+1`'s +1/+0.
- **CR 119.2** - damage generally.
- **CR 111.7** - a token's characteristics are those stated when it was
  created; "except for tokens you control" excludes it from a mass-damage
  sweep by that status.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_ajani_unrelenting_creates_a_cadet_when_its_controller_activates_loyalty() -> None:
    """ "Whenever you activate a loyalty ability, create a 2/2 colorless
    Wizard Soldier creature token named Cadet." - the trigger goes on the
    stack above the loyalty ability itself and resolves first.
    """
    scenario = Scenario().player("alice", battlefield=["Ajani Unrelenting"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ajani = scenario.find("Ajani Unrelenting", Zone.BATTLEFIELD, "alice")

    scenario.activate(ajani, index=0)  # +1
    scenario.resolve_top()  # the loyalty-activated trigger, ahead of +1 itself
    scenario.resolve_top()  # +1 itself

    cadets = [
        state for state in scenario.game.permanents_controlled_by("alice") if state.name == "Cadet"
    ]
    assert len(cadets) == 1
    # The Cadet is a 2/2 as created, and already on the battlefield when the
    # +1 ("Creatures you control get +1/+0 and gain haste until end of turn")
    # resolves after it, so CR 611.2c fixes it into the affected set: 3/2.
    assert scenario.game.characteristics_of(cadets[0]).power_toughness == (3, 2)


def test_gideon_the_oathless_damages_an_opponent_who_activates_a_loyalty_ability() -> None:
    """ "Whenever an opponent activates a loyalty ability, Gideon deals 1
    damage to that player." - the same trigger event, read from the
    opposite side (an *opponent's* own activation, not the controller's).

    Garruk, Veiled Butcher's own `+2` (not Ajani Unrelenting) is the one
    activated here specifically because it creates nothing of its own -
    Ajani Unrelenting's own token trigger would otherwise also feed
    Gideon's *other*, unrelated "a creature an opponent controls enters"
    trigger and conflate the two.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Garruk, Veiled Butcher", "Grizzly Bears"])
        .player("bob", battlefield=["Gideon the Oathless"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    garruk = scenario.find("Garruk, Veiled Butcher", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    alice_life_before = scenario.game.player("alice").life

    scenario.activate(garruk, index=0, targets=[bears])  # +2, alice's own turn (CR 606.3)
    scenario.resolve_top()  # Gideon's own trigger - bob's opponent (alice) activated
    scenario.resolve_top()  # +2 itself

    assert scenario.game.player("alice").life == alice_life_before - 1


def test_gideon_the_oathless_does_not_fire_for_its_own_controllers_activation() -> None:
    """Gideon the Oathless watches for an *opponent's* activation only - its
    own controller activating a loyalty ability (here, their own Ashiok,
    Dream Render) never matches the condition at all.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Gideon the Oathless", "Ashiok, Dream Render"],
            life=20,
        )
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.activate(
        scenario.find("Ashiok, Dream Render", Zone.BATTLEFIELD, username="alice"),
        index=0,
        username="alice",
        targets=["alice"],
    )
    scenario.game.put_triggers_on_stack()

    assert "Gideon the Oathless's triggered ability" not in scenario.stack_names()


def test_ajani_unrelenting_minus_three_damages_every_creature_except_tokens_alice_controls() -> (
    None
):
    """ "Ajani deals 4 damage to each creature except for tokens you
    control." - alice's own Cadet token survives; alice's nontoken creature
    and bob's board, token or not, all take it.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ajani Unrelenting", "Grizzly Bears"])
        .player("bob", battlefield=["Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ajani = scenario.find("Ajani Unrelenting", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    angel = scenario.creature("Serra Angel", "bob")

    scenario.activate(ajani, index=2)  # -3
    scenario.resolve_top()  # the loyalty-activated trigger creates a Cadet first
    cadet = next(
        state for state in scenario.game.permanents_controlled_by("alice") if state.name == "Cadet"
    )
    scenario.resolve_top()  # -3 itself

    assert bears.zone is Zone.GRAVEYARD, "not a token - takes the 4 damage, a 2/2 dies to it"
    assert angel.zone is Zone.GRAVEYARD, "bob's Serra Angel is not alice's token either"
    assert cadet.zone is Zone.BATTLEFIELD, "alice's own token is excluded"
    assert cadet.damage == 0
