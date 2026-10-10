"""Scenario: "`<this>` can block an additional creature each combat" and its
siblings (CR 509.1a, 510.1d).

CR 509.1a: "For each of the chosen creatures, the defending player chooses one
creature for it to block" - one attacker per blocker by default - and an
effect that says a creature "can block an additional creature each combat"
raises that bound by one (an additional seven: by seven; "any number of
creatures": no bound). CR 510.1d is the damage side: "If it's blocking two or
more creatures, it assigns its combat damage divided as its controller
chooses among them."

Forms proved, each on two different-wording printings:

- self, one extra: Foriysian Interceptor, Spike-Tailed Ceratops
- self, a counted extra: Watcher in the Web ("an additional seven creatures"),
  Kemba's Legion ("... for each Equipment attached to this creature")
- self, unbounded: Palace Guard ("any number of creatures")
- equipped creature: Echo Circlet
- group: High Ground and Brave the Sands ("Each creature you control"),
  Cenn's Tactician ("Each creature you control with a +1/+1 counter on it")

Every sibling printing of the same sentence is checked for being read handled
by the static audit (`test_every_listed_card_reads_its_line_as_handled`).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card

from .harness import Scenario

_MARKERS = ("can block an additional", "can block any number of creatures")

_LISTED = [
    "Foriysian Interceptor",
    "Ghastbark Twins",
    "Kemba's Legion",
    "Lairwatch Giant",
    "Night Market Guard",
    "Selesnya Sagittars",
    "Spike-Tailed Ceratops",
    "Tangleclaw Werewolf",
    "Two-Headed Dragon",
    "Avatar of Hope",
    "Guardian of the Gateless",
    "Palace Guard",
    "Brave the Sands",
    "High Ground",
    "Cenn's Tactician",
    "Echo Circlet",
    "Watcher in the Web",
]


@pytest.mark.parametrize("name", _LISTED)
def test_every_listed_card_reads_its_line_as_handled(name):
    clauses = [
        clause
        for clause in classify_clauses(card(name))
        if any(marker in clause.text.lower() for marker in _MARKERS)
    ]
    assert clauses, f"{name}: no clause carries the extra-blockers line"
    assert all(clause.category == HANDLED for clause in clauses), clauses


def declare(scenario, blocker, *attackers):
    """One blocker declared on each of these attackers, one `block` call per
    attacker (the harness rechecks the whole declaration each time)."""
    for attacker in attackers:
        scenario.block(attacker, blocker)


def attackers_vs(attacker_names: list[str], blocker_names: list[str], extra=()):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=attacker_names)
        .player("bob", battlefield=blocker_names + list(extra))
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    attackers = scenario.game.permanents_controlled_by("alice")
    attackers = [a for a in attackers if a.name in attacker_names]
    scenario.attack_with(*attackers)
    return scenario, attackers


# -- the default bound ---------------------------------------------------------


def test_an_ordinary_blocker_cannot_block_two_attackers():
    scenario, (first, second) = attackers_vs(["Hill Giant", "Hill Giant"], ["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.block(first, bears)
    with pytest.raises(ValueError, match="cannot block more than one attacker"):
        scenario.block(second, bears)


# -- self, one extra -------------------------------------------------------------


def test_foriysian_interceptor_blocks_two_attackers():
    scenario, (first, second) = attackers_vs(
        ["Hill Giant", "Hill Giant"], ["Foriysian Interceptor"]
    )
    interceptor = scenario.creature("Foriysian Interceptor", "bob")

    declare(scenario, interceptor, first, second)

    assert scenario.game.is_blocked(first) and scenario.game.is_blocked(second)
    assert scenario.game.combat.attack_by(first.id).blockers == [interceptor.id]
    assert scenario.game.combat.attack_by(second.id).blockers == [interceptor.id]


def test_a_second_extra_block_is_refused():
    """One additional creature means two attackers in all - the third is one
    too many."""
    scenario, (first, second, third) = attackers_vs(
        ["Hill Giant", "Hill Giant", "Hill Giant"], ["Foriysian Interceptor"]
    )
    interceptor = scenario.creature("Foriysian Interceptor", "bob")

    declare(scenario, interceptor, first, second)
    with pytest.raises(ValueError, match="cannot block more than"):
        scenario.block(third, interceptor)
    assert not scenario.game.is_blocked(third)


def test_spike_tailed_ceratops_a_second_wording_of_the_same_template():
    scenario, (first, second, third) = attackers_vs(
        ["Hill Giant", "Hill Giant", "Hill Giant"], ["Spike-Tailed Ceratops"]
    )
    ceratops = scenario.creature("Spike-Tailed Ceratops", "bob")

    declare(scenario, ceratops, first, second)
    with pytest.raises(ValueError, match="cannot block more than"):
        scenario.block(third, ceratops)


def test_the_extra_block_is_per_blocker_not_per_player():
    scenario, (first, second) = attackers_vs(
        ["Hill Giant", "Hill Giant"], ["Foriysian Interceptor", "Grizzly Bears"]
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    interceptor = scenario.creature("Foriysian Interceptor", "bob")

    scenario.block(first, interceptor)
    scenario.block(second, interceptor)
    with pytest.raises(ValueError, match="cannot block more than"):
        scenario.block(first, bears)
        scenario.block(second, bears)


def test_the_same_attacker_twice_is_still_refused():
    """ "An additional creature" is another attacker - blocking the one
    attacker twice is no block at all."""
    scenario, (first,) = attackers_vs(["Hill Giant"], ["Foriysian Interceptor"])
    interceptor = scenario.creature("Foriysian Interceptor", "bob")

    with pytest.raises(ValueError):
        scenario.game.declare_blockers([(interceptor, first), (interceptor, first)])


def test_each_restriction_still_applies_to_the_extra_block():
    """The extra block is judged like any other (CR 509.1b): a flyer cannot
    be the extra creature for a blocker with neither flying nor reach."""
    scenario, (giant, angel) = attackers_vs(
        ["Hill Giant", "Serra Angel"], ["Foriysian Interceptor"]
    )
    interceptor = scenario.creature("Foriysian Interceptor", "bob")

    scenario.block(giant, interceptor)
    with pytest.raises(ValueError, match="flying"):
        scenario.block(angel, interceptor)


def test_menace_still_needs_two_blockers_when_one_is_an_extra_block():
    """One creature blocking a menace attacker and another attacker is still
    one blocker on the menace attacker (CR 702.111b)."""
    scenario, (giant, brute) = attackers_vs(
        ["Hill Giant", "Boggart Brute"], ["Foriysian Interceptor"]
    )
    interceptor = scenario.creature("Foriysian Interceptor", "bob")
    if giant.name != "Hill Giant":
        giant, brute = brute, giant

    with pytest.raises(ValueError, match="menace"):
        scenario.game.declare_blockers([(interceptor, giant), (interceptor, brute)])


# -- combat damage (CR 510.1d) ---------------------------------------------------


def test_a_double_blocker_divides_its_combat_damage_as_its_controller_chooses():
    scenario, (first, second) = attackers_vs(
        ["Hill Giant", "Hill Giant"], ["Spike-Tailed Ceratops"]
    )
    ceratops = scenario.creature("Spike-Tailed Ceratops", "bob")
    declare(scenario, ceratops, first, second)

    scenario.will_assign_combat_damage((first, 3), (second, 1), username="bob")
    scenario.advance("alice")
    scenario.combat_damage()

    assert first.zone is Zone.GRAVEYARD  # 3 damage kills a 3/3
    assert second.zone is Zone.BATTLEFIELD and second.damage == 1
    assert ceratops.zone is Zone.GRAVEYARD  # 3 + 3 damage on a 4/4


def test_an_unscripted_double_blocker_assigns_lethal_in_order_then_the_rest():
    scenario, (first, second) = attackers_vs(
        ["Hill Giant", "Hill Giant"], ["Spike-Tailed Ceratops"]
    )
    ceratops = scenario.creature("Spike-Tailed Ceratops", "bob")
    declare(scenario, ceratops, first, second)

    scenario.advance("alice")
    scenario.combat_damage()

    assert first.zone is Zone.GRAVEYARD
    assert second.damage == 1


def test_a_double_blocker_does_not_double_its_damage():
    """4 power is divided - not 4 to each attacker."""
    scenario, (first, second) = attackers_vs(
        ["Hill Giant", "Hill Giant"], ["Spike-Tailed Ceratops"]
    )
    ceratops = scenario.creature("Spike-Tailed Ceratops", "bob")
    declare(scenario, ceratops, first, second)

    scenario.will_assign_combat_damage((first, 2), (second, 2), username="bob")
    scenario.advance("alice")
    scenario.combat_damage()

    assert first.damage + second.damage == 4


def test_a_double_blocker_with_one_attacker_gone_assigns_all_to_the_other():
    scenario, (first, second) = attackers_vs(
        ["Hill Giant", "Hill Giant"], ["Spike-Tailed Ceratops"]
    )
    ceratops = scenario.creature("Spike-Tailed Ceratops", "bob")
    declare(scenario, ceratops, first, second)
    scenario.game.combat.remove(first.id)  # CR 510.1d: only the one it still blocks

    scenario.advance("alice")
    scenario.combat_damage()

    assert second.zone is Zone.GRAVEYARD  # all 4 damage to the one it still blocks
    assert first.damage == 0


# -- self, a counted extra ---------------------------------------------------------


def test_watcher_in_the_web_blocks_eight_and_not_nine():
    names = ["Hill Giant"] * 9
    scenario, attackers = attackers_vs(names, ["Watcher in the Web"])
    watcher = scenario.creature("Watcher in the Web", "bob")

    scenario.game.declare_blockers([(watcher, attacker) for attacker in attackers[:8]])
    assert len(scenario.game.combat.attack_blocked_by(watcher.id).blockers) == 1
    with pytest.raises(ValueError, match="cannot block more than"):
        scenario.game.declare_blockers([(watcher, attacker) for attacker in attackers[:9]])


def test_kemba_s_legion_blocks_one_more_per_attached_equipment():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Hill Giant"] * 4)
        .player("bob", battlefield=["Kemba's Legion", "Bonesplitter", "Lightning Greaves"])
        .build()
    )
    legion = scenario.creature("Kemba's Legion", "bob")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    attackers = scenario.game.permanents_controlled_by("alice")
    scenario.attack_with(*attackers)

    with pytest.raises(ValueError, match="cannot block more than"):
        scenario.game.declare_blockers([(legion, attackers[0]), (legion, attackers[1])])

    bonesplitter = scenario.find("Bonesplitter", Zone.BATTLEFIELD, "bob")
    bonesplitter.attach_to(legion)
    scenario.game.declare_blockers([(legion, attackers[0]), (legion, attackers[1])])

    greaves = scenario.find("Lightning Greaves", Zone.BATTLEFIELD, "bob")
    greaves.attach_to(legion)
    scenario.game.declare_blockers([(legion, attacker) for attacker in attackers[:3]])
    with pytest.raises(ValueError, match="cannot block more than 3 attackers"):
        scenario.game.declare_blockers([(legion, attacker) for attacker in attackers[:4]])


# -- self, unbounded ---------------------------------------------------------------


def test_palace_guard_blocks_any_number_of_creatures():
    scenario, attackers = attackers_vs(["Hill Giant"] * 6, ["Palace Guard"])
    guard = scenario.creature("Palace Guard", "bob")

    scenario.game.declare_blockers([(guard, attacker) for attacker in attackers])

    assert all(scenario.game.is_blocked(attacker) for attacker in attackers)


def test_palace_guard_still_cannot_block_the_same_attacker_twice():
    scenario, (giant,) = attackers_vs(["Hill Giant"], ["Palace Guard"])
    guard = scenario.creature("Palace Guard", "bob")

    with pytest.raises(ValueError):
        scenario.game.declare_blockers([(guard, giant), (guard, giant)])


# -- equipped creature ---------------------------------------------------------------


def test_echo_circlet_gives_the_equipped_creature_an_extra_block():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Hill Giant", "Hill Giant"])
        .player("bob", battlefield=["Echo Circlet", "Grizzly Bears", "Runeclaw Bear"])
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    other = scenario.creature("Runeclaw Bear", "bob")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    first, second = scenario.game.permanents_controlled_by("alice")
    scenario.attack_with(first, second)

    with pytest.raises(ValueError, match="cannot block more than"):
        scenario.game.declare_blockers([(bears, first), (bears, second)])

    circlet = scenario.find("Echo Circlet", Zone.BATTLEFIELD, "bob")
    circlet.attach_to(bears)
    scenario.game.declare_blockers([(bears, first), (bears, second)])
    # only the equipped creature
    with pytest.raises(ValueError, match="cannot block more than"):
        scenario.game.declare_blockers([(other, first), (other, second)])


# -- group forms ---------------------------------------------------------------------


@pytest.mark.parametrize("source", ["High Ground", "Brave the Sands"])
def test_each_creature_you_control_blocks_an_additional_creature(source):
    scenario, (first, second) = attackers_vs(
        ["Hill Giant", "Hill Giant"], ["Grizzly Bears", "Runeclaw Bear"], extra=[source]
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    other = scenario.creature("Runeclaw Bear", "bob")

    scenario.game.declare_blockers([(bears, first), (bears, second), (other, first)])
    assert scenario.game.combat.attack_by(first.id).blockers == [bears.id, other.id]


def test_the_group_grant_is_only_for_its_controllers_creatures():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["High Ground", "Hill Giant", "Hill Giant", "Grizzly Bears"])
        .player("bob", battlefield=["Runeclaw Bear"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    giants = [a for a in scenario.game.permanents_controlled_by("alice") if a.name == "Hill Giant"]
    scenario.attack_with(*giants)
    other = scenario.creature("Runeclaw Bear", "bob")

    with pytest.raises(ValueError, match="cannot block more than"):
        scenario.game.declare_blockers([(other, giants[0]), (other, giants[1])])


def test_cenn_s_tactician_only_grants_creatures_with_a_plus_one_counter():
    scenario, (first, second) = attackers_vs(
        ["Hill Giant", "Hill Giant"], ["Grizzly Bears", "Runeclaw Bear"], extra=["Cenn's Tactician"]
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    other = scenario.creature("Runeclaw Bear", "bob")
    bears.add_counters(Counter.PLUS_ONE, 1)

    scenario.game.declare_blockers([(bears, first), (bears, second)])
    with pytest.raises(ValueError, match="cannot block more than"):
        scenario.game.declare_blockers([(other, first), (other, second)])


def test_cenn_s_tactician_a_different_counter_does_not_count():
    scenario, (first, second) = attackers_vs(
        ["Hill Giant", "Hill Giant"], ["Grizzly Bears"], extra=["Cenn's Tactician"]
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    bears.add_counters(Counter.CHARGE, 1)

    with pytest.raises(ValueError, match="cannot block more than"):
        scenario.game.declare_blockers([(bears, first), (bears, second)])


def test_two_sources_stack():
    """High Ground and Brave the Sands together: two additional creatures."""
    scenario, attackers = attackers_vs(
        ["Hill Giant"] * 3, ["Grizzly Bears"], extra=["High Ground", "Brave the Sands"]
    )
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.game.declare_blockers([(bears, attacker) for attacker in attackers])


def test_the_grant_ends_when_the_source_leaves():
    scenario, (first, second) = attackers_vs(
        ["Hill Giant", "Hill Giant"], ["Grizzly Bears"], extra=["High Ground"]
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    ground = scenario.find("High Ground", Zone.BATTLEFIELD, "bob")
    scenario.game.put_into_graveyard(ground)
    assert ground.zone is Zone.GRAVEYARD
    with pytest.raises(ValueError, match="cannot block more than"):
        scenario.game.declare_blockers([(bears, first), (bears, second)])


def test_every_proof_printing_is_legal_somewhere_tracked():
    for name in (
        "Foriysian Interceptor",
        "Spike-Tailed Ceratops",
        "Watcher in the Web",
        "Kemba's Legion",
        "Palace Guard",
        "Echo Circlet",
        "High Ground",
        "Brave the Sands",
        "Cenn's Tactician",
    ):
        legalities = card(name).legalities
        assert "legal" in {legalities.standard, legalities.pioneer, legalities.modern}, name
