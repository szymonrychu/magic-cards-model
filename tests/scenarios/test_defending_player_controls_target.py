"""Scenario: "target creature defending player controls" on an attack trigger.

CR 508.5: "If an ability of an attacking creature refers to a defending
player, ... the defending player it's referring to is the player that
creature is attacking" - so the attacker's own controller's creatures are
never legal targets. Found by the behavioural sweep once it took optional
targets: Aetherstorm Roc's "tap up to one target creature defending player
controls" was offered, and took, its own controller's Memnite. Proven again
on Hellkite Whelp's mandatory "deals 1 damage to target creature defending
player controls".

CR numbers read with `mise run rules:find` in the session that wrote this
file: 508.5, 603.3d.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from tests.scenarios.harness import Scenario


def _attack(attacker: str, *, bob_battlefield: list[str]):
    scenario = (
        Scenario()
        .player("alice", battlefield=[attacker, "Memnite"])
        .player("bob", battlefield=bob_battlefield)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature(attacker, "alice"), defending="bob")
    return scenario


def _offered(scenario, source: str) -> set[str]:
    (question,) = [
        q
        for q in scenario.questions_asked()
        if q.kind is DecisionKind.CHOOSE_TARGETS and q.source == source
    ]
    return {scenario.game.find_by_id(ref.card_id).name for ref in question.targets}


def test_aetherstorm_roc_offers_only_the_defending_players_creatures():
    scenario = _attack("Aetherstorm Roc", bob_battlefield=["Grizzly Bears"])

    assert _offered(scenario, "Aetherstorm Roc") == {"Grizzly Bears"}


def test_hellkite_whelp_offers_only_the_defending_players_creatures():
    scenario = _attack("Hellkite Whelp", bob_battlefield=["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "bob")

    assert _offered(scenario, "Hellkite Whelp") == {"Grizzly Bears"}
    scenario.pass_until_resolved()
    assert bears.damage == 1


def test_hellkite_whelp_with_no_defending_creature_has_no_target():
    """CR 603.3d: with no legal target the mandatory trigger is removed -
    alice's own Memnite does not stand in for one."""
    scenario = _attack("Hellkite Whelp", bob_battlefield=[])
    memnite = scenario.creature("Memnite", "alice")

    scenario.pass_until_resolved()

    assert memnite.damage == 0
