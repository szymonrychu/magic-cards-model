"""'When that creature dies this turn' / 'When a creature dealt damage this way
dies this turn' delayed riders on a damage spell.

Searing Blood ({R}{R}): "Searing Blood deals 2 damage to target creature.
When that creature dies this turn, Searing Blood deals 3 damage to the
creature's controller."

Skeletonize ({4}{R}): "Skeletonize deals 3 damage to target creature. When a
creature dealt damage this way dies this turn, create a 1/1 black Skeleton
creature token with "{B}: Regenerate this token.""

CR 603.7 / CR 603.7c: the spell's resolution creates a delayed triggered
ability about that object; CR 603.7b: it lasts "this turn". CR 603.10a: a
leaves-the-battlefield trigger looks back in time, so "the creature's
controller" is the controller as it last existed (CR 608.2h). CR 615.6:
prevented damage is never dealt, so a creature whose damage was all prevented
was not "dealt damage this way".

Proof printings on the same delayed-trigger family: Make Your Mark and
Otherworldly Outburst ("When that creature dies this turn, create a ... token"),
with a second effect run through the same resolver for the two readers that
have no other printing.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.effects import effect_for
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board(alice_hand, lands, bob_battlefield, bob_hand=(), alice_extra=()):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=list(alice_hand),
            battlefield=list(lands) + list(alice_extra),
            library=["Mountain"] * 3,
        )
        .player(
            "bob", hand=list(bob_hand), battlefield=list(bob_battlefield), library=["Island"] * 3
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _tokens(scenario, name, username="alice"):
    return [
        card
        for card in scenario.game.battlefield
        if card.name.startswith(name) and card.token and card.controller == username
    ]


# -- Searing Blood ---------------------------------------------------------------


def _blood(scenario, target):
    scenario.cast_and_resolve(
        "Searing Blood", *scenario.untapped_sources("Mountain", "Mountain"), targets=[target]
    )


def test_searing_blood_kills_the_creature_and_hits_its_controller_for_three():
    scenario = _board(["Searing Blood"], ["Mountain"] * 2, ["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "bob")
    _blood(scenario, bears)
    scenario.state_based_actions()
    scenario.pass_until_resolved()
    assert bears.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 17
    assert scenario.player("alice").life == 20


def test_a_surviving_creature_that_dies_later_this_turn_still_pays_out():
    scenario = _board(["Searing Blood", "Lightning Bolt"], ["Mountain"] * 3, ["Hill Giant"])
    giant = scenario.creature("Hill Giant", "bob")
    _blood(scenario, giant)
    assert giant.zone is Zone.BATTLEFIELD
    assert scenario.player("bob").life == 20
    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[giant]
    )
    scenario.state_based_actions()
    scenario.pass_until_resolved()
    assert giant.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 17


def test_the_damage_goes_to_whoever_controlled_the_creature_not_the_caster():
    scenario = _board(["Searing Blood"], ["Mountain"] * 2, [], alice_extra=["Grizzly Bears"])
    mine = scenario.creature("Grizzly Bears", "alice")
    _blood(scenario, mine)
    scenario.state_based_actions()
    scenario.pass_until_resolved()
    assert mine.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 17
    assert scenario.player("bob").life == 20


def test_searing_blood_with_its_target_gone_does_nothing():
    """CR 608.2b: no legal target, no damage and no delayed trigger."""
    scenario = _board(
        ["Searing Blood"], ["Mountain"] * 2, ["Grizzly Bears", "Island"], bob_hand=["Unsummon"]
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    spell = scenario.cast_onto_stack(
        "Searing Blood", *scenario.untapped_sources("Mountain", "Mountain"), targets=[bears]
    )
    scenario.pass_priority("alice")
    scenario.cast_and_resolve(
        "Unsummon",
        *scenario.untapped_sources("Island", username="bob"),
        username="bob",
        targets=[bears],
    )
    scenario.resolve_top()
    assert spell.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 20


# -- Skeletonize -----------------------------------------------------------------


def _skeletonize(scenario, target):
    scenario.cast_and_resolve(
        "Skeletonize", *scenario.untapped_sources(*["Mountain"] * 5), targets=[target]
    )
    scenario.state_based_actions()
    scenario.pass_until_resolved()


def test_skeletonize_creates_a_skeleton_when_the_damaged_creature_dies():
    scenario = _board(["Skeletonize"], ["Mountain"] * 5, ["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "bob")
    _skeletonize(scenario, bears)
    assert bears.zone is Zone.GRAVEYARD
    (skeleton,) = _tokens(scenario, "Skeleton")
    assert skeleton.token
    assert _tokens(scenario, "Skeleton", "bob") == []


def test_skeletonize_makes_no_skeleton_when_the_creature_survives():
    scenario = _board(["Skeletonize"], ["Mountain"] * 5, ["Serra Angel"])
    angel = scenario.creature("Serra Angel", "bob")
    _skeletonize(scenario, angel)
    assert angel.zone is Zone.BATTLEFIELD
    assert _tokens(scenario, "Skeleton") == []


def test_skeletonize_pays_out_when_the_creature_dies_later_this_turn():
    scenario = _board(["Skeletonize", "Lightning Bolt"], ["Mountain"] * 6, ["Serra Angel"])
    angel = scenario.creature("Serra Angel", "bob")
    _skeletonize(scenario, angel)
    assert _tokens(scenario, "Skeleton") == []
    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[angel]
    )
    scenario.state_based_actions()
    scenario.pass_until_resolved()
    assert angel.zone is Zone.GRAVEYARD
    assert len(_tokens(scenario, "Skeleton")) == 1


def test_fully_prevented_damage_was_not_dealt_this_way():
    """CR 615.6: Healing Salve stops all 3, so the Bears were not dealt damage
    by Skeletonize and dying afterwards to something else earns no Skeleton."""
    scenario = _board(
        ["Skeletonize", "Lightning Bolt"],
        ["Mountain"] * 6,
        ["Grizzly Bears", "Plains"],
        bob_hand=["Healing Salve"],
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.cast_onto_stack(
        "Skeletonize", *scenario.untapped_sources(*["Mountain"] * 5), targets=[bears]
    )
    scenario.pass_priority("alice")
    salve = scenario.cast("Healing Salve", "bob")
    salve.choose_modes([2])
    salve.choose_targets([bears])
    payment = salve.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Plains", username="bob"))
    scenario.put_on_stack(salve)
    scenario.resolve_top()
    scenario.resolve_top()
    assert bears.damage == 0
    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[bears]
    )
    scenario.state_based_actions()
    scenario.pass_until_resolved()
    assert bears.zone is Zone.GRAVEYARD
    assert _tokens(scenario, "Skeleton") == []


# -- The same readers with a different consequence --------------------------------


def test_the_dealt_damage_this_way_reader_takes_any_consequence_the_family_reads():
    scenario = _board(["Skeletonize"], ["Mountain"] * 5, ["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "bob")
    spell = scenario.cast_onto_stack(
        "Skeletonize", *scenario.untapped_sources(*["Mountain"] * 5), targets=[bears]
    )
    effect = effect_for(
        "Skeletonize",
        "Skeletonize deals 3 damage to target creature. When a creature dealt damage this way "
        "dies this turn, you gain 4 life.",
    )
    effect(scenario.game, spell)
    scenario.state_based_actions()
    scenario.pass_until_resolved()
    assert bears.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 24


# -- Proof printings: the existing "that creature dies this turn" sentence -----------


def test_make_your_mark_still_creates_its_spirit_when_the_creature_dies():
    scenario = _board(
        ["Make Your Mark", "Lightning Bolt"],
        ["Mountain", "Plains", "Mountain"],
        [],
        alice_extra=["Grizzly Bears"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_and_resolve(
        "Make Your Mark", *scenario.untapped_sources("Plains"), targets=[bears]
    )
    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[bears]
    )
    scenario.state_based_actions()
    scenario.pass_until_resolved()
    assert bears.zone is Zone.GRAVEYARD
    assert len([c for c in scenario.game.battlefield if c.token]) == 1
