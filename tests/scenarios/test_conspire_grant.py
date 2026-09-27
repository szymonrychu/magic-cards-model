"""Scenario: conspire (CR 702.78a), printed and granted.

CR 702.78a: "Conspire is a keyword that represents two abilities. The first
is a static ability that functions while the spell with conspire is on the
stack. The second is a triggered ability that functions while the spell with
conspire is on the stack. 'Conspire' means 'As an additional cost to cast
this spell, you may tap two untapped creatures you control that each share a
color with it' and 'When you cast this spell, if its conspire cost was paid,
copy it. If the spell has any targets, you may choose new targets for the
copy.'"

Granted by Raiding Schemes' "Each noncreature spell you cast has conspire."
and by the proof printing Wort, the Raidmother's "Each red or green instant
or sorcery spell you cast has conspire."; printed on Burn Trail. CR 707.10:
the copy isn't cast; CR 707.10f: a copy of a permanent spell becomes a token
as it resolves.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file: CR 702.78a, CR 707.10, CR 707.10c, CR 707.10f,
CR 601.2b.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import executes
from magic_cards_model.models import Zone
from tests.scenarios.harness import PlayedScenario, Scenario


def _board(*, alice_battlefield, alice_hand, bob_battlefield=("Craw Wurm", "Hill Giant")):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=list(alice_hand),
            battlefield=list(alice_battlefield),
            library=["Island"] * 5,
        )
        .player("bob", battlefield=list(bob_battlefield), library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _conspire_triggers(scenario: PlayedScenario) -> list:
    return [
        item
        for item in [*scenario.game.stack, *scenario.game.pending_triggers]
        if getattr(item, "is_ability", False)
        and (getattr(item.ability, "keyword", None) or "").lower() == "conspire"
    ]


def _cast(scenario, name, *, tapping=(), targets=None):
    casting = scenario.cast(name)
    if tapping:
        # CR 601.2b: the additional cost is announced before targets.
        casting.pay_conspire(list(tapping))
    if targets is not None:
        casting.choose_targets(targets)
    payment = casting.begin_paying()
    scenario.auto_pay(payment)
    return scenario.put_on_stack(casting)


def _goblins(scenario):
    return [p for p in scenario.game.battlefield if p.name == "Raging Goblin"]


def test_conspire_is_an_executed_keyword():
    assert executes("Conspire")


def test_raiding_schemes_conspire_taps_two_red_creatures_and_copies_the_bolt():
    scenario = _board(
        alice_battlefield=["Raiding Schemes", "Raging Goblin", "Raging Goblin", "Mountain"],
        alice_hand=["Lightning Bolt"],
    )
    goblins = _goblins(scenario)
    wurm = scenario.creature("Craw Wurm", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.will_take_the_may(True, username="alice")
    scenario.will_choose_targets(giant, username="alice")

    bolt = _cast(scenario, "Lightning Bolt", tapping=goblins, targets=[wurm])

    assert all(goblin.tapped for goblin in goblins)
    assert scenario.game.cast_record_of(bolt).conspire_paid == 1
    assert len(_conspire_triggers(scenario)) == 1
    while scenario.game.stack:
        scenario.resolve_top()
    assert giant.zone is Zone.GRAVEYARD
    assert wurm.damage == 3


def test_not_paying_conspire_casts_the_spell_once():
    scenario = _board(
        alice_battlefield=["Raiding Schemes", "Raging Goblin", "Raging Goblin", "Mountain"],
        alice_hand=["Lightning Bolt"],
    )
    wurm = scenario.creature("Craw Wurm", "bob")
    _cast(scenario, "Lightning Bolt", targets=[wurm])
    assert _conspire_triggers(scenario) == []
    assert scenario.stack_names() == ["Lightning Bolt"]


def test_creatures_that_share_no_color_cannot_pay():
    """ "Two untapped creatures you control that each share a color with it"
    - green Llanowar Elves share nothing with red Lightning Bolt."""
    scenario = _board(
        alice_battlefield=["Raiding Schemes", "Llanowar Elves", "Llanowar Elves", "Mountain"],
        alice_hand=["Lightning Bolt"],
    )
    elves = [p for p in scenario.game.battlefield if p.name == "Llanowar Elves"]
    casting = scenario.cast("Lightning Bolt")
    with pytest.raises(ValueError, match="share a color"):
        casting.pay_conspire(elves)


def test_a_tapped_creature_cannot_pay():
    scenario = _board(
        alice_battlefield=["Raiding Schemes", "Raging Goblin", "Raging Goblin", "Mountain"],
        alice_hand=["Lightning Bolt"],
    )
    goblins = _goblins(scenario)
    goblins[0].tapped = True
    casting = scenario.cast("Lightning Bolt")
    with pytest.raises(ValueError, match="untapped"):
        casting.pay_conspire(goblins)


def test_it_takes_exactly_two_creatures():
    scenario = _board(
        alice_battlefield=["Raiding Schemes", "Raging Goblin", "Raging Goblin", "Mountain"],
        alice_hand=["Lightning Bolt"],
    )
    casting = scenario.cast("Lightning Bolt")
    with pytest.raises(ValueError, match="two"):
        casting.pay_conspire(_goblins(scenario)[:1])


def test_a_creature_spell_does_not_have_conspire_from_raiding_schemes():
    """ "Each noncreature spell" - a creature spell has no conspire to pay."""
    scenario = _board(
        alice_battlefield=["Raiding Schemes", "Raging Goblin", "Raging Goblin", "Mountain"],
        alice_hand=["Raging Goblin"],
    )
    casting = scenario.cast("Raging Goblin")
    with pytest.raises(ValueError, match="conspire"):
        casting.pay_conspire(_goblins(scenario))


def test_an_opponents_raiding_schemes_grants_you_nothing():
    scenario = _board(
        alice_battlefield=["Raging Goblin", "Raging Goblin", "Mountain"],
        alice_hand=["Lightning Bolt"],
        bob_battlefield=["Raiding Schemes"],
    )
    casting = scenario.cast("Lightning Bolt")
    with pytest.raises(ValueError, match="conspire"):
        casting.pay_conspire(_goblins(scenario))


def test_a_copied_noncreature_permanent_spell_becomes_a_token():
    """CR 707.10f: Goblin Bombardment's copy resolves into a token."""
    scenario = _board(
        alice_battlefield=[
            "Raiding Schemes",
            "Raging Goblin",
            "Raging Goblin",
            "Mountain",
            "Mountain",
        ],
        alice_hand=["Goblin Bombardment"],
    )
    _cast(scenario, "Goblin Bombardment", tapping=_goblins(scenario))
    while scenario.game.stack:
        scenario.resolve_top()
    bombardments = [p for p in scenario.game.battlefield if p.name == "Goblin Bombardment"]
    assert len(bombardments) == 2
    assert sorted(p.token for p in bombardments) == [False, True]


def test_wort_grants_conspire_to_a_green_instant():
    """The proof printing: a colour-and-type quality ("red or green instant
    or sorcery") on the same grant."""
    scenario = _board(
        alice_battlefield=["Wort, the Raidmother", "Grizzly Bears", "Grizzly Bears", "Forest"],
        alice_hand=["Giant Growth"],
    )
    bears = [p for p in scenario.game.battlefield if p.name == "Grizzly Bears"]
    wort = scenario.creature("Wort, the Raidmother", "alice")
    scenario.will_take_the_may(True, username="alice")
    scenario.will_choose_targets(wort, username="alice")

    _cast(scenario, "Giant Growth", tapping=bears, targets=[bears[0]])
    while scenario.game.stack:
        scenario.resolve_top()

    assert scenario.game.characteristics_of(wort).power == 3 + 3
    assert scenario.game.characteristics_of(bears[0]).power == 2 + 3


def test_wort_does_not_grant_conspire_to_a_blue_spell():
    scenario = _board(
        alice_battlefield=["Wort, the Raidmother", "Raging Goblin", "Raging Goblin", "Island"],
        alice_hand=["Opt"],
    )
    casting = scenario.cast("Opt")
    with pytest.raises(ValueError, match="conspire"):
        casting.pay_conspire(_goblins(scenario))


def test_printed_conspire_on_burn_trail():
    """Burn Trail prints conspire itself - the same two abilities."""
    scenario = _board(
        alice_battlefield=[
            "Raging Goblin",
            "Raging Goblin",
            "Mountain",
            "Mountain",
            "Mountain",
            "Mountain",
        ],
        alice_hand=["Burn Trail"],
    )
    scenario.will_take_the_may(False, username="alice")
    _cast(scenario, "Burn Trail", tapping=_goblins(scenario), targets=["bob"])
    while scenario.game.stack:
        scenario.resolve_top()
    assert scenario.player("bob").life == 20 - 3 - 3
