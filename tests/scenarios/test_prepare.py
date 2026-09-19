"""Scenario: Prepare / preparation cards (CR 722), Reality Fracture's own new
mechanic.

CR 722.1: "Preparation cards have a two-part card frame, with a smaller frame
inset within their text box." CR 722.2a: "The inset frame of a preparation
card is called a 'prepare spell.'" CR 722.3a: "Some spells and abilities
cause a permanent with a prepare spell to become prepared or state that a
permanent enters prepared. If that permanent has the alternative
characteristics of a prepare spell, this gives the permanent the 'prepared'
designation ... A permanent can't gain this designation unless it has a
prepare spell. Additionally, a permanent can't gain this designation if the
permanent already has it." CR 722.3b: "A rule or effect may cause a permanent
to become 'unprepared.' This removes the prepared designation from that
permanent." CR 722.3c: "As a permanent with a prepare spell gains the
prepared designation ..., its controller creates a copy of that object in
exile, except that copy has only the characteristics of that permanent's
prepare spell ... This copy remains in exile for as long as the prepared
permanent remains on the battlefield and has the prepared designation ...
For as long as the copy remains in exile, the prepared permanent's
controller may cast the copy. That permanent loses the prepared designation
at the time the spell becomes cast (see rule 601.2i)." CR 722.3d: "If a
prepare spell is copied, the copy is also a prepare spell."

Every CR number here was verified this session with `mise run rules:find`.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import PlayAction
from magic_cards_model.models.card import Layout, Type
from magic_cards_model.models.zone import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario

# -- reading the card --------------------------------------------------


def test_a_prepare_card_s_inset_frame_is_its_prepare_spell():
    """CR 722.2a: the inset frame - `card_faces[1]` on a real Scryfall
    printing, the same shape every other multifaced layout uses."""
    printing = card("Emergency Phytomedic")
    assert printing.layout is Layout.PREPARE
    face = printing.prepare_spell
    assert face is not None
    assert face.name == "Seed Suture"
    assert face.mana_cost == "{G/W}"


def test_a_non_prepare_card_has_no_prepare_spell():
    assert card("Grizzly Bears").prepare_spell is None


# -- CR 722.3a/722.3c: enters prepared ----------------------------------


def _phytomedic_board() -> Scenario:
    return (
        Scenario()
        .player("alice", hand=["Emergency Phytomedic"], battlefield=["Plains", "Forest"])
        .player("bob", battlefield=["Grizzly Bears"])
    )


def test_a_creature_that_enters_prepared_gets_the_designation_and_an_exile_copy():
    scenario = _phytomedic_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    phytomedic = scenario.cast_and_resolve(
        "Emergency Phytomedic", *scenario.untapped_sources("Plains")
    )

    assert phytomedic.zone is Zone.BATTLEFIELD
    assert phytomedic.prepared is True, "CR 722.3a: enters prepared"
    assert phytomedic.prepared_copy_id is not None

    copies = [state for state in scenario.game.exile if state.id == phytomedic.prepared_copy_id]
    assert len(copies) == 1, "CR 722.3c: a copy of that object in exile"
    (copy,) = copies
    assert copy.name == "Seed Suture", "the copy's characteristics are the prepare spell's"
    assert copy.mana_cost == "{G/W}"
    assert Type.SORCERY in copy.types
    assert copy.is_copy is True

    permission = scenario.game.play_permission_for(copy, "alice")
    assert permission is not None, "CR 722.3c: the controller may cast the copy"
    assert permission.action is PlayAction.CAST
    assert permission.pays_mana_cost is True
    assert permission.zone is Zone.EXILE


def test_a_permanent_that_already_has_the_designation_cannot_gain_it_again():
    """CR 722.3a's second sentence: a no-op, not a second copy."""
    scenario = _phytomedic_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    phytomedic = scenario.cast_and_resolve(
        "Emergency Phytomedic", *scenario.untapped_sources("Plains")
    )
    before = phytomedic.prepared_copy_id

    made = scenario.game.become_prepared(phytomedic)

    assert made is None
    assert phytomedic.prepared_copy_id == before
    assert len([s for s in scenario.game.exile if s.card.name == phytomedic.card.name]) == 1


def test_a_permanent_with_no_prepare_spell_cannot_become_prepared():
    scenario = Scenario().player("alice", battlefield=["Grizzly Bears"]).build()
    bears = scenario.creature("Grizzly Bears")

    made = scenario.game.become_prepared(bears)

    assert made is None
    assert bears.prepared is False


# -- CR 722.3c/601.2i: casting the copy ----------------------------------


def test_casting_the_copy_pays_its_own_mana_cost_and_resolves_as_the_spell():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Emergency Phytomedic"],
            battlefield=["Plains", "Forest", "Forest"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    phytomedic = scenario.cast_and_resolve(
        "Emergency Phytomedic", *scenario.untapped_sources("Plains")
    )
    copy = scenario.game.find_by_id(phytomedic.prepared_copy_id)
    target = scenario.creature("Grizzly Bears", "bob")
    life_before = scenario.player("alice").life

    casting = scenario.cast(copy.name, from_zone=Zone.EXILE)
    casting.use_permission()
    casting.choose_targets([target])
    (forest,) = scenario.untapped_sources("Forest")
    payment = casting.begin_paying()
    scenario.pay_with(payment, forest)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert target.counters.counts.get("+1/+1", 0) == 1, (
        "Seed Suture: a +1/+1 counter on target creature"
    )
    assert scenario.player("alice").life == life_before + 1, "Seed Suture: gain 1 life"


def test_casting_the_copy_removes_the_prepared_designation_cr_601_2i():
    scenario = _phytomedic_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    phytomedic = scenario.cast_and_resolve(
        "Emergency Phytomedic", *scenario.untapped_sources("Plains")
    )
    copy = scenario.game.find_by_id(phytomedic.prepared_copy_id)
    target = scenario.creature("Grizzly Bears", "bob")

    (forest,) = scenario.untapped_sources("Forest")
    casting = scenario.cast(copy.name, from_zone=Zone.EXILE)
    casting.use_permission()
    casting.choose_targets([target])
    payment = casting.begin_paying()
    scenario.pay_with(payment, forest)
    scenario.put_on_stack(casting)

    assert phytomedic.prepared is False, "CR 601.2i: lost as the spell becomes cast"
    assert phytomedic.prepared_copy_id is None
    assert copy.zone is Zone.STACK
    assert copy not in scenario.game.exile
