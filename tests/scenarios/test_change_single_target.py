"""CR 115.7a/115.7b: "change the target" / "change a target" of a spell or
ability already on the stack.

Every card here was read off its own Scryfall printing in
`data/printings/`:

- Bolt Bend: "Change the target of target spell or ability with a single
  target." (plus a power-conditioned discount, see
  `test_power_conditioned_discount.py`).
- Redirect Lightning: the same sentence behind a "pay 5 life or pay {2}"
  additional cost (see `test_pay_life_or_mana_additional_cost.py`).
- Hydroelectric Specimen: "When this creature enters, you may change the
  target of target instant or sorcery spell with a single target to this
  creature."
- Ricochet Trap (proof printing, Modern-legal, in no deck): "Change the
  target of target spell with a single target." - a spell-only noun.
- Spellskite (proof printing, Modern-legal, in no deck): "{U/P}: Change a
  target of target spell or ability to this creature." - CR 115.7b's "a
  target", on an activated ability, with no single-target restriction.

The rules, verified with `mise run rules:find` in the session that wrote this
file:

- CR 115.7a: "each target can be changed only to another legal target. If a
  target can't be changed to another legal target, the original target is
  unchanged, even if the original target is itself illegal by then."
- CR 115.7b: "change a target" follows 115.7a "except that only one of those
  targets may be changed".
- CR 115.7e: "only the final set of targets is evaluated to determine whether
  the change is legal".
- CR 115.9a: "with a single target" counts the targets chosen when the spell
  or ability was put on the stack.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def bolt_board(*bob_hand: str, bob_battlefield: tuple[str, ...] = ()) -> Scenario:
    """Alice holds a Bolt; Bob holds whatever redirects it."""
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Lightning Bolt", "Giant Growth", "Duress", "Prey Upon"],
            battlefield=["Mountain", "Swamp", "Swamp", "Forest", "Grizzly Bears"],
        )
        .player(
            "bob",
            hand=list(bob_hand),
            battlefield=["Mountain"] * 4 + ["Island"] * 3 + list(bob_battlefield),
        )
    )


def _alice_bolts(scenario, target):
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="alice", targets=[target])
    scenario.pass_priority("alice")
    return bolt


# -- CR 115.7a: "change the target" -----------------------------------------


def test_bolt_bend_sends_a_bolt_back_at_its_caster():
    """The whole point of the card: Bob chooses the new target, and the Bolt
    then resolves at it."""
    scenario = bolt_board("Bolt Bend").build()
    bolt = _alice_bolts(scenario, "bob")
    scenario.cast_onto_stack("Bolt Bend", auto=True, username="bob", targets=[bolt])
    scenario.will_choose_targets("alice", username="bob")

    scenario.resolve_top()
    assert [ref.username for ref in bolt.targets] == ["alice"]
    scenario.resolve_top()

    assert scenario.player("alice").life == 17
    assert scenario.player("bob").life == 20


def test_the_change_is_mandatory_and_never_offers_the_original_target():
    """CR 115.7a: "changed only to *another* legal target". The question is
    not a "may" - Bolt Bend says "change", not "you may change" - and the
    target the Bolt already has is not among the answers."""
    scenario = bolt_board("Bolt Bend").build()
    bolt = _alice_bolts(scenario, "bob")
    scenario.cast_onto_stack("Bolt Bend", auto=True, username="bob", targets=[bolt])

    scenario.resolve_top()

    asked = [q for q in scenario.questions_asked() if q.source == "Bolt Bend"]
    assert [q.kind for q in asked] == [DecisionKind.CHOOSE_TARGETS]
    (question,) = asked
    assert question.target_minimum == 1
    offered = {ref.username for ref in question.targets if ref.is_player}
    assert offered == {"alice"}
    assert bolt.targets[0] != "bob"


def _alice_grows_her_bears(scenario):
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    (forest,) = scenario.untapped_sources("Forest", username="alice")
    growth = scenario.cast_onto_stack("Giant Growth", forest, username="alice", targets=[bears])
    scenario.pass_priority("alice")
    return growth, bears


def test_no_other_legal_target_leaves_the_spell_unchanged():
    """CR 115.7a: "If a target can't be changed to another legal target, the
    original target is unchanged". Giant Growth ("Target creature gets
    +3/+3") on the only creature in play: there is nowhere legal to move it,
    so nobody is asked anything and the Bears still get the pump."""
    scenario = bolt_board("Bolt Bend").build()
    growth, bears = _alice_grows_her_bears(scenario)
    scenario.cast_onto_stack("Bolt Bend", auto=True, username="bob", targets=[growth])

    scenario.resolve_top()

    assert not [q for q in scenario.questions_asked() if q.source == "Bolt Bend"]
    assert [ref.card_id for ref in growth.targets] == [bears.id]
    scenario.resolve_top()
    assert scenario.game.power_of(bears) == 5


def test_only_legal_new_targets_are_offered():
    """ "target creature" can move to Bob's Memnite and nowhere else - a
    player is not a creature."""
    scenario = bolt_board("Bolt Bend", bob_battlefield=("Memnite",)).build()
    growth, bears = _alice_grows_her_bears(scenario)
    memnite = scenario.creature("Memnite", "bob")
    scenario.cast_onto_stack("Bolt Bend", auto=True, username="bob", targets=[growth])

    scenario.resolve_top()
    (question,) = [q for q in scenario.questions_asked() if q.source == "Bolt Bend"]
    assert [ref.card_id for ref in question.targets] == [memnite.id]
    scenario.resolve_top()

    assert scenario.game.power_of(memnite) == 4
    assert scenario.game.power_of(bears) == 2


def test_an_illegal_new_target_is_refused():
    """A scripted answer naming a player for Giant Growth's "target creature"
    is refused rather than silently accepted."""
    scenario = bolt_board("Bolt Bend", bob_battlefield=("Memnite",)).build()
    growth, _ = _alice_grows_her_bears(scenario)
    scenario.cast_onto_stack("Bolt Bend", auto=True, username="bob", targets=[growth])
    scenario.will_choose_targets("alice", username="bob")

    with pytest.raises(ValueError):
        scenario.resolve_top()


def test_the_new_target_is_judged_from_the_changed_spells_controller():
    """Legality is the changed spell's own, read from its controller's seat:
    Duress's "target opponent" means an opponent of *Alice*. Alice is Bob's
    opponent but not her own, so there is no other legal target and Duress
    stays on Bob."""
    scenario = bolt_board("Bolt Bend").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (swamp, _) = scenario.untapped_sources("Swamp", "Swamp", username="alice")
    duress = scenario.cast_onto_stack("Duress", swamp, username="alice", targets=["bob"])
    scenario.pass_priority("alice")
    scenario.cast_onto_stack("Bolt Bend", auto=True, username="bob", targets=[duress])

    scenario.resolve_top()

    assert not [q for q in scenario.questions_asked() if q.source == "Bolt Bend"]
    assert [ref.username for ref in duress.targets] == ["bob"]


def test_bolt_bend_changes_the_target_of_a_triggered_ability():
    """ "target spell *or ability*": Orcish Bowmasters' enters trigger (one
    target, "1 damage to any target") is moved off Bob's face onto Alice's."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Orcish Bowmasters"], battlefield=["Swamp", "Swamp"])
        .player("bob", hand=["Bolt Bend"], battlefield=["Mountain"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.choose_trigger_targets("Orcish Bowmasters", ["bob"])
    scenario.cast_onto_stack("Orcish Bowmasters", auto=True, username="alice")
    scenario.resolve_top()
    scenario.pass_priority("alice")
    (trigger,) = [item for item in scenario.game.stack if item.name != "Orcish Bowmasters"]

    scenario.cast_onto_stack("Bolt Bend", auto=True, username="bob", targets=[trigger])
    scenario.will_choose_targets("alice", username="bob")
    scenario.resolve_top()
    assert [ref.username for ref in trigger.targets] == ["alice"]
    scenario.resolve_top()

    assert scenario.player("alice").life == 19
    assert scenario.player("bob").life == 20


def test_redirect_lightning_changes_the_target_too():
    """Redirect Lightning prints the identical sentence, so it moves the Bolt
    the same way - read off the template, not the card."""
    scenario = bolt_board("Redirect Lightning").build()
    bolt = _alice_bolts(scenario, "bob")
    scenario.cast_onto_stack("Redirect Lightning", auto=True, username="bob", targets=[bolt])
    scenario.will_choose_targets("alice", username="bob")

    scenario.resolve_top()
    scenario.resolve_top()

    assert scenario.player("alice").life == 17


# -- proof printing: Ricochet Trap ------------------------------------------


def test_ricochet_trap_changes_the_target_of_a_spell():
    """Ricochet Trap's "target spell with a single target": the same reader,
    a different noun, a different card."""
    scenario = bolt_board("Ricochet Trap").build()
    bolt = _alice_bolts(scenario, "bob")
    scenario.cast_onto_stack("Ricochet Trap", auto=True, username="bob", targets=[bolt])
    scenario.will_choose_targets("alice", username="bob")

    scenario.resolve_top()
    scenario.resolve_top()

    assert scenario.player("alice").life == 17
    assert scenario.player("bob").life == 20


def test_ricochet_trap_cannot_target_an_ability():
    """ "target spell" is not "target spell or ability" (CR 115.2)."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Orcish Bowmasters"], battlefield=["Swamp", "Swamp"])
        .player("bob", hand=["Ricochet Trap"], battlefield=["Mountain"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.choose_trigger_targets("Orcish Bowmasters", ["bob"])
    scenario.cast_onto_stack("Orcish Bowmasters", auto=True, username="alice")
    scenario.resolve_top()
    scenario.pass_priority("alice")
    (trigger,) = [item for item in scenario.game.stack if item.name != "Orcish Bowmasters"]

    with pytest.raises(ValueError):
        scenario.cast_onto_stack("Ricochet Trap", auto=True, username="bob", targets=[trigger])


# -- "to this creature": Hydroelectric Specimen -----------------------------


def _specimen_answers(scenario, spell):
    scenario.choose_trigger_targets("Hydroelectric Specimen", [spell])
    scenario.cast_onto_stack("Hydroelectric Specimen", auto=True, username="bob")
    scenario.resolve_top()
    assert scenario.stack_names()[-1] != "Hydroelectric Specimen"
    scenario.resolve_top()


def test_hydroelectric_specimen_pulls_a_bolt_onto_itself():
    """A legal "to this creature" change: the Bolt ("any target") can target
    the Specimen, so it now does, and the Specimen (a 1/4) takes the 3."""
    scenario = bolt_board("Hydroelectric Specimen").build()
    bolt = _alice_bolts(scenario, "bob")
    scenario.will_take_the_may(True, username="bob")
    _specimen_answers(scenario, bolt)
    specimen = scenario.creature("Hydroelectric Specimen", "bob")

    assert [ref.card_id for ref in bolt.targets] == [specimen.id]
    scenario.resolve_top()
    assert specimen.damage == 3
    assert scenario.player("bob").life == 20


def test_hydroelectric_specimen_leaves_an_illegal_change_alone():
    """Duress ("Target opponent reveals their hand ...") cannot target a
    creature at all, so "to this creature" is not a legal change and the
    spell is unchanged (CR 115.7a) - and since there is nothing to choose, the
    "you may" is never put to Bob."""
    scenario = bolt_board("Hydroelectric Specimen").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (swamp, _) = scenario.untapped_sources("Swamp", "Swamp", username="alice")
    duress = scenario.cast_onto_stack("Duress", swamp, username="alice", targets=["bob"])
    scenario.pass_priority("alice")
    _specimen_answers(scenario, duress)

    assert [ref.username for ref in duress.targets] == ["bob"]
    assert not [
        q
        for q in scenario.questions_asked()
        if q.source == "Hydroelectric Specimen" and q.kind is DecisionKind.MAY
    ]


def test_declining_hydroelectric_specimens_may_changes_nothing():
    scenario = bolt_board("Hydroelectric Specimen").build()
    bolt = _alice_bolts(scenario, "bob")
    scenario.will_take_the_may(False, username="bob")
    _specimen_answers(scenario, bolt)

    assert [ref.username for ref in bolt.targets] == ["bob"]


def test_hydroelectric_specimen_only_targets_a_spell_with_a_single_target():
    """CR 115.9a: Prey Upon was put on the stack with two targets, so the
    trigger cannot be aimed at it."""
    scenario = bolt_board("Hydroelectric Specimen", bob_battlefield=("Memnite",)).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    memnite = scenario.creature("Memnite", "bob")
    prey = scenario.cast_onto_stack(
        "Prey Upon", auto=True, username="alice", targets=[bears, memnite]
    )
    scenario.pass_priority("alice")

    with pytest.raises(ValueError, match="single target"):
        scenario.choose_trigger_targets("Hydroelectric Specimen", [prey])


# -- CR 115.7b "change a target ... to this creature": Spellskite -------------


def test_spellskite_redirects_a_bolt_to_itself():
    scenario = bolt_board(bob_battlefield=("Spellskite",)).build()
    bolt = _alice_bolts(scenario, "bob")
    skite = scenario.creature("Spellskite", "bob")
    island = scenario.untapped_sources("Island", username="bob")[0]

    scenario.activate(skite, island, username="bob", targets=[bolt])
    scenario.resolve_top()

    assert [ref.card_id for ref in bolt.targets] == [skite.id]
    scenario.resolve_top()
    assert skite.damage == 3
    assert scenario.player("bob").life == 20


def test_spellskite_changes_only_the_target_it_can_legally_become():
    """CR 115.7b/115.7e on a two-target spell. Prey Upon: "Target creature you
    control fights target creature you don't control." Spellskite is Bob's, so
    it can only become the *second* target - the first is unchanged, and the
    final set is legal."""
    scenario = bolt_board(bob_battlefield=("Spellskite", "Memnite")).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    memnite = scenario.creature("Memnite", "bob")
    skite = scenario.creature("Spellskite", "bob")
    prey = scenario.cast_onto_stack(
        "Prey Upon", auto=True, username="alice", targets=[bears, memnite]
    )
    scenario.pass_priority("alice")
    island = scenario.untapped_sources("Island", username="bob")[0]

    scenario.activate(skite, island, username="bob", targets=[prey])
    scenario.resolve_top()

    assert [ref.card_id for ref in prey.targets] == [bears.id, skite.id]


def test_spellskite_already_targeted_changes_nothing():
    """ "another legal target" (CR 115.7a, via 115.7b): a Bolt already aimed at
    Spellskite has nowhere new to go."""
    scenario = bolt_board(bob_battlefield=("Spellskite",)).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    skite = scenario.creature("Spellskite", "bob")
    bolt = _alice_bolts_at_object(scenario, skite)
    island = scenario.untapped_sources("Island", username="bob")[0]

    scenario.activate(skite, island, username="bob", targets=[bolt])
    scenario.resolve_top()

    assert [ref.card_id for ref in bolt.targets] == [skite.id]


def _alice_bolts_at_object(scenario, target):
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="alice", targets=[target])
    scenario.pass_priority("alice")
    return bolt


def test_spellskite_that_left_the_battlefield_changes_nothing():
    """ "to this creature" needs the creature: once Spellskite is gone the
    change cannot be made, and the Bolt keeps its original target."""
    scenario = bolt_board(bob_battlefield=("Spellskite",)).build()
    bolt = _alice_bolts(scenario, "bob")
    skite = scenario.creature("Spellskite", "bob")
    island = scenario.untapped_sources("Island", username="bob")[0]
    scenario.activate(skite, island, username="bob", targets=[bolt])
    scenario.game.sacrifice(skite)

    scenario.resolve_top()

    assert [ref.username for ref in bolt.targets] == ["bob"]


def test_spellskite_asks_which_target_when_it_could_become_either():
    """CR 115.7b: "only one of those targets may be changed". Dual Shot ("1
    damage to each of up to two target creatures") at Bob's Memnite and
    Alice's Grizzly Bears: Spellskite could replace either, so Bob picks which
    - here the Memnite - and the other target is untouched. CR 115.3 is why
    the two stay distinct: one instance of "target" never names Spellskite
    twice."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Dual Shot"], battlefield=["Mountain", "Grizzly Bears"])
        .player("bob", battlefield=["Island", "Spellskite", "Memnite"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    memnite = scenario.creature("Memnite", "bob")
    bears = scenario.creature("Grizzly Bears", "alice")
    skite = scenario.creature("Spellskite", "bob")
    shot = scenario.cast_onto_stack(
        "Dual Shot", auto=True, username="alice", targets=[memnite, bears]
    )
    scenario.pass_priority("alice")
    (island,) = scenario.untapped_sources("Island", username="bob")
    scenario.activate(skite, island, username="bob", targets=[shot])
    scenario.will_choose_targets(memnite, username="bob")

    scenario.resolve_top()
    (question,) = [q for q in scenario.questions_asked() if q.source == "Spellskite"]
    assert {ref.card_id for ref in question.targets} == {memnite.id, bears.id}
    assert [ref.card_id for ref in shot.targets] == [skite.id, bears.id]

    scenario.resolve_top()
    assert skite.damage == 1
    assert bears.damage == 1
    assert memnite.damage == 0


def test_a_modal_spells_changed_target_reaches_its_mode():
    """CR 700.2f: "Changing a spell or ability's target can't change its
    mode." Prismari Command, modes "2 damage to any target" and "Target player
    draws two cards, then discards two cards": Spellskite can only replace the
    damage target, and the damage mode then resolves at Spellskite."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Prismari Command"],
            library=["Island", "Island", "Island"],
            battlefield=["Island", "Mountain", "Mountain"],
        )
        .player("bob", battlefield=["Island", "Spellskite"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    skite = scenario.creature("Spellskite", "bob")
    command = scenario.game.cast(
        scenario.find("Prismari Command", Zone.HAND, "alice"),
        "alice",
        modes=[1, 2],
        targets=["bob", "alice"],
        mana_sources=scenario.untapped_sources("Island", "Mountain", "Mountain", username="alice"),
    )
    scenario.pass_priority("alice")
    (island,) = scenario.untapped_sources("Island", username="bob")
    scenario.activate(skite, island, username="bob", targets=[command])

    scenario.resolve_top()
    assert [ref.username or ref.card_id for ref in command.targets] == [skite.id, "alice"]

    scenario.resolve_top()
    assert skite.damage == 2
    assert scenario.player("bob").life == 20


def test_deflecting_swat_chooses_new_targets_for_an_ability():
    """CR 115.7d on an ability: Deflecting Swat's "choose new targets for
    target spell or ability" now reaches Orcish Bowmasters' trigger and moves
    its 1 damage from Bob to Alice."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Orcish Bowmasters"], battlefield=["Swamp", "Swamp"])
        .player("bob", hand=["Deflecting Swat"], battlefield=["Mountain"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.choose_trigger_targets("Orcish Bowmasters", ["bob"])
    scenario.cast_onto_stack("Orcish Bowmasters", auto=True, username="alice")
    scenario.resolve_top()
    scenario.pass_priority("alice")
    (trigger,) = [item for item in scenario.game.stack if item.name != "Orcish Bowmasters"]

    scenario.cast_onto_stack("Deflecting Swat", auto=True, username="bob", targets=[trigger])
    scenario.will_take_the_may(True, username="bob")
    scenario.will_choose_targets("alice", username="bob")
    scenario.resolve_top()
    scenario.resolve_top()

    assert scenario.player("alice").life == 19
    assert scenario.player("bob").life == 20
