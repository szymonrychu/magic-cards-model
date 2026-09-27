"""Several permanents at once becoming copies of one target - Mirrorform:
"Each nonland permanent you control becomes a copy of target non-Aura
permanent."

Every CR number here was read whole with `mise run rules:find` in the session
that wrote this file:

- **CR 613.1a** layer 1: copy effects modify copiable values; everything
  later (a pump, a counter) still applies on top.
- **CR 707.2** a copy acquires the copiable values - printed text as
  modified by other copy effects, never counters, status or non-copy
  effects.
- **CR 707.4** a permanent copying a different object while remaining on
  the battlefield: no enters or leaves abilities trigger.
- **CR 611.2a** no duration printed - until the end of the game; **CR
  611.2c** the set of permanents is fixed as the spell resolves.
- **CR 704.5p** a creature attached to something becomes unattached (an
  Equipment that is now a creature).
- **CR 704.5j** the legend rule, for a copy of a legendary permanent.

Second printing (legal in Modern, in no deck list, Scryfall printing read
2026-09-27): Mirrorweave - "Each other creature becomes a copy of target
nonlegendary creature until end of turn." (every controller's creatures,
"other" than the target, and a duration).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.models import Type, Zone
from tests.scenarios.harness import Scenario

MIRRORFORM = "Mirrorform"


def _chars(scenario: Scenario, permanent):
    return scenario.game.characteristics_of(permanent)


def _end_the_turn(scenario: Scenario) -> None:
    scenario.start_at(Step.END_STEP)
    scenario.advance()  # cleanup (CR 514.2)
    scenario.turn_based_actions()


def _mirrorform(*, alice=(), bob=(), hand=()):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=[MIRRORFORM, *hand],
            battlefield=["Island"] * 6 + list(alice),
            library=["Island"] * 5,
        )
        .player("bob", battlefield=list(bob), library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast(scenario: Scenario, target) -> None:
    scenario.cast_and_resolve(
        MIRRORFORM, *scenario.untapped_sources(*["Island"] * 6), targets=[target]
    )


def test_each_nonland_permanent_you_control_becomes_a_copy():
    scenario = _mirrorform(alice=("Grizzly Bears", "Sol Ring"), bob=("Serra Angel",))
    angel = scenario.creature("Serra Angel", "bob")
    bears = scenario.creature("Grizzly Bears", "alice")
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")

    _cast(scenario, angel)

    for permanent in (bears, ring):
        chars = _chars(scenario, permanent)
        assert chars.name == "Serra Angel"
        assert (chars.power, chars.toughness) == (4, 4)
        assert Type.CREATURE in chars.types
        assert has_keyword(permanent, Keyword.FLYING, scenario.game)


def test_lands_are_left_alone():
    scenario = _mirrorform(alice=("Grizzly Bears",), bob=("Serra Angel",))
    angel = scenario.creature("Serra Angel", "bob")

    _cast(scenario, angel)

    island = scenario.find("Island", Zone.BATTLEFIELD, "alice")
    assert _chars(scenario, island).name == "Island"


def test_the_opponents_permanents_are_left_alone():
    scenario = _mirrorform(alice=("Grizzly Bears",), bob=("Serra Angel", "Hill Giant"))
    angel = scenario.creature("Serra Angel", "bob")
    giant = scenario.creature("Hill Giant", "bob")

    _cast(scenario, angel)

    assert _chars(scenario, giant).name == "Hill Giant"


def test_the_copy_is_permanent():
    """CR 611.2a: no duration, so it outlives the turn."""
    scenario = _mirrorform(alice=("Grizzly Bears",), bob=("Serra Angel",))
    angel = scenario.creature("Serra Angel", "bob")
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast(scenario, angel)

    _end_the_turn(scenario)

    assert _chars(scenario, bears).name == "Serra Angel"


def test_the_copy_does_not_copy_counters_or_pumps():
    """CR 707.2: counters and non-copy effects are not copiable values."""
    scenario = _mirrorform(alice=("Grizzly Bears",), bob=("Hill Giant",))
    giant = scenario.creature("Hill Giant", "bob")
    bears = scenario.creature("Grizzly Bears", "alice")
    giant.add_counters("+1/+1", 2)

    _cast(scenario, giant)

    assert (_chars(scenario, bears).power, _chars(scenario, bears).toughness) == (3, 3)


def test_the_copying_permanents_keep_their_own_counters():
    """CR 707.4: noncopy effects and counters on the copier stay."""
    scenario = _mirrorform(alice=("Grizzly Bears",), bob=("Hill Giant",))
    giant = scenario.creature("Hill Giant", "bob")
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.add_counters("+1/+1", 1)

    _cast(scenario, giant)

    assert (_chars(scenario, bears).power, _chars(scenario, bears).toughness) == (4, 4)


def test_a_permanent_entering_later_is_not_a_copy():
    """CR 611.2c: the set is fixed as the spell resolves."""
    scenario = _mirrorform(alice=("Grizzly Bears",), bob=("Serra Angel",), hand=("Hill Giant",))
    angel = scenario.creature("Serra Angel", "bob")
    _cast(scenario, angel)

    giant = scenario.put_onto_battlefield("Hill Giant", "alice")

    assert _chars(scenario, giant).name == "Hill Giant"


def test_copying_does_not_trigger_enters_abilities():
    """CR 707.4: becoming a copy is not entering the battlefield - copying
    Kitchen Finks gains no life."""
    scenario = _mirrorform(alice=("Grizzly Bears",), bob=("Kitchen Finks",))
    finks = scenario.creature("Kitchen Finks", "bob")
    life = scenario.player("alice").life

    _cast(scenario, finks)
    scenario.pass_until_resolved()

    assert scenario.player("alice").life == life
    assert _chars(scenario, scenario.creature("Grizzly Bears", "alice")).name == "Kitchen Finks"


def test_an_equipment_that_becomes_a_creature_falls_off():
    """CR 704.5p: a creature attached to something becomes unattached."""
    scenario = _mirrorform(alice=("Grizzly Bears", "Bonesplitter"), bob=("Hill Giant",))
    bears = scenario.creature("Grizzly Bears", "alice")
    splitter = scenario.find("Bonesplitter", Zone.BATTLEFIELD, "alice")
    splitter.attach_to(bears)
    giant = scenario.creature("Hill Giant", "bob")

    _cast(scenario, giant)
    scenario.state_based_actions()

    assert splitter.attached_to is None
    assert _chars(scenario, splitter).name == "Hill Giant"


def test_copying_a_legend_makes_the_legend_rule_apply():
    """CR 704.5j: two copies of a legendary permanent - keep one."""
    scenario = _mirrorform(
        alice=("Grizzly Bears", "Savannah Lions"), bob=("Isamaru, Hound of Konda",)
    )
    isamaru = scenario.creature("Isamaru, Hound of Konda", "bob")

    _cast(scenario, isamaru)
    scenario.will_choose_cards(scenario.creature("Grizzly Bears", "alice"), username="alice")
    scenario.state_based_actions()

    names = [
        _chars(scenario, permanent).name
        for permanent in scenario.game.permanents_controlled_by("alice")
        if Type.CREATURE in _chars(scenario, permanent).types
    ]
    assert names.count("Isamaru, Hound of Konda") == 1


def test_an_aura_cannot_be_the_target():
    scenario = _mirrorform(alice=("Grizzly Bears",), bob=("Hill Giant", "Pacifism"))
    pacifism = scenario.find("Pacifism", Zone.BATTLEFIELD, "bob")

    casting = scenario.cast(MIRRORFORM, username="alice")
    with pytest.raises(ValueError):
        casting.choose_targets([pacifism])


def test_the_target_gone_means_nothing_happens():
    """CR 608.2b: the only target is illegal, so the spell does nothing."""
    scenario = _mirrorform(alice=("Grizzly Bears",), bob=("Hill Giant",))
    giant = scenario.creature("Hill Giant", "bob")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_onto_stack(
        MIRRORFORM, *scenario.untapped_sources(*["Island"] * 6), targets=[giant]
    )
    scenario.game.destroy(giant)
    scenario.resolve_top()

    assert _chars(scenario, bears).name == "Grizzly Bears"


# --------------------------------------------------------------------------
# Mirrorweave
# --------------------------------------------------------------------------


def _mirrorweave(*, alice=(), bob=()):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Mirrorweave"],
            battlefield=["Island"] * 4 + list(alice),
            library=["Island"] * 5,
        )
        .player("bob", battlefield=list(bob), library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_mirrorweave_copies_every_other_creature_until_end_of_turn():
    scenario = _mirrorweave(alice=("Grizzly Bears",), bob=("Hill Giant", "Serra Angel"))
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    angel = scenario.creature("Serra Angel", "bob")

    scenario.cast_and_resolve(
        "Mirrorweave", *scenario.untapped_sources(*["Island"] * 4), targets=[bears]
    )

    assert _chars(scenario, giant).name == "Grizzly Bears"
    assert _chars(scenario, angel).name == "Grizzly Bears"
    assert (_chars(scenario, angel).power, _chars(scenario, angel).toughness) == (2, 2)
    _end_the_turn(scenario)
    assert _chars(scenario, angel).name == "Serra Angel"


def test_mirrorweave_leaves_noncreatures_alone():
    scenario = _mirrorweave(alice=("Grizzly Bears", "Sol Ring"))
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.cast_and_resolve(
        "Mirrorweave", *scenario.untapped_sources(*["Island"] * 4), targets=[bears]
    )

    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")
    assert _chars(scenario, ring).name == "Sol Ring"


@pytest.mark.parametrize("name", [MIRRORFORM, "Mirrorweave"])
def test_the_sweep_handles_every_clause(name):
    from magic_cards_model.support import HANDLED, card_support
    from tests.cards import card

    support = card_support(card(name))
    assert support.effect_outcome == HANDLED, support.effect_detail
