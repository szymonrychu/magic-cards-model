""" "Whenever one or more `<description>` attack `<defender>`, ..." - the
group-attack trigger (CR 603.2c: "it can trigger repeatedly if one event
contains multiple occurrences") widened to read a trailing defender phrase.

`machines/triggers.py`'s `_ONE_OR_MORE_ATTACK_RE`/`batched_attackers` already
read "one or more `<description>` attack" with nothing after "attack" (The
Earth King's own "one or more creatures you control with power 4 or greater
attack"). Frenzied Gorespawn's second ability prints the identical group
shape with a defender named afterward: "Whenever one or more creatures
attack one of your opponents, those creatures gain menace until end of
turn." Before this fix the trailing "one of your opponents" left the whole
sentence unmatched by `_ONE_OR_MORE_ATTACK_RE`, so the ability never
recognised its own trigger event and the creatures already in combat never
gained menace.

CR 603.2c and CR 508.3a ("attacks [a player, planeswalker, or battle]")
verified with `mise run rules:find` in the session that wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword
from tests.scenarios.harness import Scenario


def test_frenzied_gorespawn_grants_menace_to_creatures_attacking_an_opponent():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Frenzied Gorespawn", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    assert not has_keyword(bears, "menace", scenario.game)

    scenario.attack_with(bears, defending="bob")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert has_keyword(bears, "menace", scenario.game)


def test_frenzied_gorespawn_does_not_grant_menace_against_its_own_controller():
    """ "one of your opponents" - bob is never his own opponent. Alice's
    Grizzly Bears attacks bob himself, who controls Frenzied Gorespawn -
    the defender is the ability's own controller, not one of that
    controller's opponents, so nothing is granted."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears"])
        .player("bob", battlefield=["Frenzied Gorespawn"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.attack_with(bears, defending="bob")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert not has_keyword(bears, "menace", scenario.game)
