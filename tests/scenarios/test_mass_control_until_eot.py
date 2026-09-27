"""Gaining control of a whole group until end of turn - Broadcast Takeover:
"Gain control of all artifacts your opponents control until end of turn.
Untap them. They gain haste until end of turn."

- CR 613.1b: the control change is a layer 2 effect, lasting until the
  cleanup step (CR 514.2).
- CR 611.2c: "the set of objects it affects is determined when that
  continuous effect begins. After that point, the set won't change" - an
  artifact that comes under an opponent's control afterwards is not taken,
  and one the spell took stays taken for the turn.
- CR 701.26b: "Untap them" untaps each permanent the first sentence named.
- CR 702.10b: haste lets a stolen artifact creature attack although its new
  controller has not controlled it since their turn began (CR 302.6).

Off-set proof (legal, in no deck list): Mob Rule - "Choose one - * Gain
control of all creatures with power 4 or greater until end of turn. Untap
those creatures. They gain haste until end of turn. * Gain control of all
creatures with power 3 or less until end of turn. Untap those creatures.
They gain haste until end of turn." - the same instruction over creatures, a
power qualifier instead of a controller one, "those creatures" as the
anaphor, and every player's creatures (the caster's own included).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario

TAKEOVER = "Broadcast Takeover"
MOUNTAINS = ["Mountain"] * 5


def _controller(scenario, permanent):
    return scenario.game.controller_of(permanent).username


def _cast_takeover(scenario):
    return scenario.cast_and_resolve(
        TAKEOVER, *scenario.untapped_sources(*MOUNTAINS, username="alice")
    )


def _takeover_board(*, alice=(), bob=()):
    return (
        Scenario()
        .player("alice", hand=[TAKEOVER], battlefield=[*MOUNTAINS, *alice], library=["Island"] * 5)
        .player("bob", battlefield=list(bob), library=["Island"] * 5)
        .build()
    )


def test_takeover_gains_control_of_every_opposing_artifact():
    scenario = _takeover_board(bob=["Sol Ring", "Mind Stone", "Ornithopter"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "bob")
    thopter = scenario.creature("Ornithopter", "bob")

    _cast_takeover(scenario)

    assert {_controller(scenario, p) for p in (ring, stone, thopter)} == {"alice"}


def test_takeover_untaps_them():
    scenario = _takeover_board(bob=["Sol Ring", "Ornithopter"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")
    thopter = scenario.creature("Ornithopter", "bob")
    ring.tap()
    thopter.tap()

    _cast_takeover(scenario)

    assert not ring.tapped
    assert not thopter.tapped


def test_takeover_leaves_nonartifacts_and_the_casters_own_artifacts_alone():
    scenario = _takeover_board(alice=["Mind Stone"], bob=["Grizzly Bears", "Sol Ring"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    own_stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "alice")
    own_stone.tap()

    _cast_takeover(scenario)

    assert _controller(scenario, bears) == "bob"
    assert _controller(scenario, own_stone) == "alice"
    # "Untap them" is only the artifacts the first sentence took.
    assert own_stone.tapped


def test_a_stolen_artifact_creature_has_haste_and_can_attack():
    """CR 702.10b over CR 302.6: alice has not controlled it since her turn
    began, and haste is what lets it attack."""
    scenario = _takeover_board(bob=["Ornithopter"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    thopter = scenario.creature("Ornithopter", "bob")

    _cast_takeover(scenario)

    assert "Haste" in scenario.game.computed_board().of(thopter).abilities
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(thopter)
    assert thopter in scenario.attackers()


def test_control_and_haste_end_at_cleanup():
    scenario = _takeover_board(bob=["Sol Ring", "Ornithopter"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")
    thopter = scenario.creature("Ornithopter", "bob")
    _cast_takeover(scenario)

    scenario.start_at(Step.END_STEP)
    scenario.advance()  # cleanup (CR 514.2)

    assert _controller(scenario, ring) == "bob"
    assert _controller(scenario, thopter) == "bob"
    assert "Haste" not in scenario.game.computed_board().of(thopter).abilities


def test_the_set_is_fixed_when_the_spell_resolves():
    """CR 611.2c: an artifact bob gets afterwards stays bob's."""
    scenario = (
        Scenario()
        .player("alice", hand=[TAKEOVER], battlefield=MOUNTAINS, library=["Island"] * 5)
        .player("bob", hand=["Mind Stone"], battlefield=["Sol Ring"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")
    _cast_takeover(scenario)

    stone = scenario.put_onto_battlefield("Mind Stone", "bob")

    assert _controller(scenario, ring) == "alice"
    assert _controller(scenario, stone) == "bob"


def test_an_opponent_with_no_artifacts_loses_nothing():
    scenario = _takeover_board(bob=["Grizzly Bears"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    takeover = _cast_takeover(scenario)

    assert takeover.zone is Zone.GRAVEYARD
    assert _controller(scenario, bears) == "bob"


# -- Mob Rule: the same instruction, creatures by power ------------------------


def _cast_mob_rule(scenario, mode):
    casting = scenario.cast("Mob Rule", username="alice")
    casting.choose_modes([mode])
    scenario.pay_with(
        casting.begin_paying(), *scenario.untapped_sources(*["Mountain"] * 6, username="alice")
    )
    scenario.put_on_stack(casting)
    scenario.resolve_top()


def _mob_board():
    return (
        Scenario()
        .player(
            "alice",
            hand=["Mob Rule"],
            battlefield=["Mountain"] * 6 + ["Grizzly Bears", "Serra Angel"],
            library=["Island"] * 5,
        )
        .player("bob", battlefield=["Craw Wurm", "Hill Giant"], library=["Island"] * 5)
        .build()
    )


def test_mob_rule_power_four_or_greater_takes_only_the_big_creatures():
    scenario = _mob_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wurm = scenario.creature("Craw Wurm", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    wurm.tap()

    _cast_mob_rule(scenario, 1)

    assert _controller(scenario, wurm) == "alice"
    assert not wurm.tapped
    assert _controller(scenario, giant) == "bob"


def test_mob_rule_power_three_or_less_takes_the_small_ones():
    scenario = _mob_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wurm = scenario.creature("Craw Wurm", "bob")
    giant = scenario.creature("Hill Giant", "bob")

    _cast_mob_rule(scenario, 2)

    assert _controller(scenario, giant) == "alice"
    assert _controller(scenario, wurm) == "bob"
    assert "Haste" in scenario.game.computed_board().of(giant).abilities


def test_mob_rule_includes_the_casters_own_creatures():
    """ "all creatures" names every player's: alice's own Serra Angel is
    untapped and gains haste as well."""
    scenario = _mob_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "alice")
    angel.tap()

    _cast_mob_rule(scenario, 1)

    assert _controller(scenario, angel) == "alice"
    assert not angel.tapped
    assert "Haste" in scenario.game.computed_board().of(angel).abilities
