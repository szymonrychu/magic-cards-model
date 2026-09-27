"""A keyword and a quoted dies trigger granted together until end of turn -
Pain 101: "Until end of turn, target creature gains deathtouch and "When this
creature dies, return it to the battlefield tapped under its owner's
control.""

- CR 613.1f / CR 113.10: both are layer 6 grants on the target, ending at
  cleanup (CR 514.2).
- CR 603.10a: a dies trigger "looks back in time" - the granted ability
  triggers off the creature as it last existed on the battlefield, and "it"
  is the card now in the graveyard.
- CR 400.7: the creature that returns is a new object - it has neither the
  deathtouch nor the granted trigger any more.
- "under its owner's control": a stolen creature goes home.

Off-set proof (legal, in no deck list): Infuse with Vitality - "Until end of
turn, target creature gains deathtouch and "When this creature dies, return
it to the battlefield tapped under its owner's control." You gain 2 life." -
the same grant with a second instruction after it.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def _abilities(scenario, permanent):
    return scenario.game.computed_board().of(permanent).abilities


def _resolve_everything(scenario):
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _board(spell, *, alice=(), bob=()):
    return (
        Scenario()
        .player(
            "alice",
            hand=[spell],
            battlefield=["Swamp", "Swamp", "Forest", *alice],
            library=["Island"] * 5,
        )
        .player("bob", battlefield=list(bob), library=["Island"] * 5)
        .build()
    )


def _cast(scenario, spell, target, *lands):
    return scenario.cast_and_resolve(
        spell, *scenario.untapped_sources(*lands, username="alice"), targets=[target]
    )


def test_pain_101_grants_deathtouch_and_the_trigger():
    scenario = _board("Pain 101", alice=["Grizzly Bears"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    _cast(scenario, "Pain 101", bears, "Swamp", "Swamp")

    abilities = _abilities(scenario, bears)
    assert "Deathtouch" in abilities
    assert any(line.startswith("When this creature dies") for line in abilities)


def test_the_creature_returns_tapped_when_it_dies():
    """CR 603.10a: the granted trigger fires off the creature that died."""
    scenario = _board("Pain 101", alice=["Grizzly Bears"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast(scenario, "Pain 101", bears, "Swamp", "Swamp")

    scenario.game.destroy(bears)
    _resolve_everything(scenario)

    back = scenario.creature("Grizzly Bears", "alice")
    assert back.zone is Zone.BATTLEFIELD
    assert back.tapped


def test_the_returned_creature_is_a_new_object_without_the_grants():
    """CR 400.7: neither deathtouch nor the trigger follows it back."""
    scenario = _board("Pain 101", alice=["Grizzly Bears"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast(scenario, "Pain 101", bears, "Swamp", "Swamp")
    scenario.game.destroy(bears)
    _resolve_everything(scenario)
    back = scenario.creature("Grizzly Bears", "alice")

    abilities = _abilities(scenario, back)
    assert "Deathtouch" not in abilities
    assert not any(line.startswith("When this creature dies") for line in abilities)

    scenario.game.destroy(back)
    _resolve_everything(scenario)
    assert back.zone is Zone.GRAVEYARD


def test_deathtouch_kills_a_bigger_blocker():
    scenario = _board("Pain 101", alice=["Grizzly Bears"], bob=["Craw Wurm"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    wurm = scenario.creature("Craw Wurm", "bob")
    _cast(scenario, "Pain 101", bears, "Swamp", "Swamp")

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    scenario.advance()
    scenario.block(bears, wurm)
    scenario.combat_damage()
    _resolve_everything(scenario)

    assert wurm.zone is Zone.GRAVEYARD
    # The Bears died too, and came straight back tapped.
    back = scenario.creature("Grizzly Bears", "alice")
    assert back.tapped


def test_the_grant_ends_at_cleanup():
    scenario = _board("Pain 101", alice=["Grizzly Bears"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast(scenario, "Pain 101", bears, "Swamp", "Swamp")

    scenario.start_at(Step.END_STEP)
    scenario.advance()  # cleanup (CR 514.2)

    assert "Deathtouch" not in _abilities(scenario, bears)
    scenario.game.destroy(bears)
    _resolve_everything(scenario)
    assert bears.zone is Zone.GRAVEYARD


def test_an_opponents_creature_returns_under_its_owners_control():
    scenario = _board("Pain 101", bob=["Hill Giant"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    _cast(scenario, "Pain 101", giant, "Swamp", "Swamp")

    scenario.game.destroy(giant)
    _resolve_everything(scenario)

    back = scenario.creature("Hill Giant", "bob")
    assert scenario.game.controller_of(back).username == "bob"
    assert back.tapped


# -- Infuse with Vitality -----------------------------------------------------


def test_infuse_with_vitality_grants_both_and_gains_life():
    scenario = _board("Infuse with Vitality", alice=["Grizzly Bears"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    _cast(scenario, "Infuse with Vitality", bears, "Swamp", "Forest")

    assert "Deathtouch" in _abilities(scenario, bears)
    assert scenario.player("alice").life == 22
    scenario.game.destroy(bears)
    _resolve_everything(scenario)
    back = scenario.creature("Grizzly Bears", "alice")
    assert back.tapped
