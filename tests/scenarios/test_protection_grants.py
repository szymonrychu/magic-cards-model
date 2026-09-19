"""Scenario: protection *granted* by another permanent's static ability, as
opposed to `test_protection.py`'s Emrakul, which has its own protection printed
on itself.

CR 613.1f: "Layer 6: Ability-adding effects ... are applied." CR 702.16a's
protection is one such ability, and Akroma's Memorial grants it exactly the
way `test_indefinite_keyword_grant.py`'s True Conviction grants double strike
and lifelink: "Creatures you control have flying, first strike, vigilance,
trample, haste, and protection from black and from red." (CR 611.3, a static
ability's effect, so it lasts exactly as long as Akroma's Memorial does -
CR 611.3b - and switches off the moment it leaves, CR 613.6, the same as
`test_indefinite_keyword_grant.py`'s own grant does for its keywords).

Before this file, `docs/engine-coverage.md` and `protection_qualities`'s own
docstring said flatly that nothing grants protection - there were no layers
for it. `machines/layers.py`'s `_INDEFINITE_KEYWORD_AND_PROTECTION_GRANT_RE`
and `Game._effective_protection_qualities` are what changed that: a granted
"Protection from <quality>" line is added to `Characteristics.abilities` the
same way a granted keyword is, and `protection_refusal`/`protection_from_damage`
now read it there in addition to a permanent's own printed text.

The **damage half** (CR 702.16e) is proven end to end, because
`Game.deal_damage` now carries a source (`docs/engine-coverage.md`,
`scenarios/test_prevention_effects.py`) and both combat and spell damage name
one. The **targeting half** (CR 702.16b) is proven too, and for a *colour*
quality: `Game.protection_refusal` matches the quality with the same reader
the damage half uses, so a red spell is refused at announcement rather than
announced and then prevented.

That ordering is why the spell-damage case below is a **sweeper** and not a
Lightning Bolt. A red spell cannot legally be pointed at a creature with
protection from red at all (CR 702.16b), so a Bolt never reaches the point
where CR 702.16e would prevent its damage; only a spell that chooses no
targets can demonstrate the damage half against a colour quality.

Every CR number here was looked up with `knowledge_search(type="rules")` in
the session that wrote this file.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import equip_activation
from magic_cards_model.models import Zone

from .harness import Scenario, mana_from


def computed(scenario: Scenario):
    """The board with static abilities and stored durational effects applied."""
    return scenario.game.continuous_effects.board(scenario.game.battlefield)


def test_akromas_memorial_grants_both_protection_qualities():
    """CR 702.16g: "protection from A and from B" is two abilities, and both
    are read out of the one sentence, not just the first.

    Compared as a set, not a list: the two grants share one timestamp (both
    come from the same sentence), and `compute_board`'s tie-break among
    same-timestamp effects sorts on each effect's randomly generated id, so
    which one lands in `Characteristics.abilities` first is not guaranteed
    run to run - only that both are there.
    """
    scenario = (
        Scenario().player("alice", battlefield=["Akroma's Memorial", "Grizzly Bears"]).build()
    )
    bears = scenario.creature("Grizzly Bears", "alice")

    board = computed(scenario)

    assert board.of(bears).has_ability("Protection from black")
    assert board.of(bears).has_ability("Protection from red")
    assert set(scenario.game._effective_protection_qualities(bears)) == {"black", "red"}


def test_a_creature_without_the_memorial_has_no_granted_protection():
    """The grant only ever reaches creatures on a battlefield with the
    Memorial on it - Grizzly Bears on its own has none of it.
    """
    scenario = Scenario().player("alice", battlefield=["Grizzly Bears"]).build()
    bears = scenario.creature("Grizzly Bears", "alice")

    assert scenario.game._effective_protection_qualities(bears) == []


def test_the_granted_protection_prevents_combat_damage_from_a_red_source():
    """CR 702.16e: "Any damage that would be dealt by sources that have the
    stated quality ... is prevented." Hill Giant is red and deals no damage to
    the protected Grizzly Bears; Grizzly Bears is green, so its own damage
    back at Hill Giant is unaffected.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("bob", battlefield=["Hill Giant"])
        .player("alice", battlefield=["Akroma's Memorial", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.attack_with(giant, defending="alice")
    scenario.advance()
    scenario.block(giant, bears)
    scenario.combat_damage()

    assert bears.damage == 0, "protection from red prevented Hill Giant's damage"
    assert giant.damage == 2, "Grizzly Bears is green, so its own damage was not prevented"


def test_the_granted_protection_prevents_spell_damage_from_a_red_source():
    """The damage half again, off a spell this time rather than a blocker.

    The spell has to be a **non-targeting** one, and that is the point of the
    case rather than an inconvenience: CR 702.16b stops a red spell being
    *targeted* at the protected creature at all, so a Lightning Bolt aimed at
    it never gets far enough to have its damage prevented - the announcement is
    refused (see the last test in this file). Pyroclasm's "Pyroclasm deals 2
    damage to each creature" chooses no targets, so it resolves against the
    protected creature and CR 702.16e is what stops it: 2 damage, enough to
    kill a 2/2 outright, prevented in full.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Pyroclasm"], battlefield=["Mountain", "Mountain"])
        .player("bob", battlefield=["Akroma's Memorial", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources("Mountain", "Mountain", username="alice")

    pyroclasm = scenario.cast_onto_stack("Pyroclasm", *sources)
    scenario.resolve_top()

    assert pyroclasm.zone is Zone.GRAVEYARD
    assert bears.damage == 0, "protection from red prevented Pyroclasm's damage (CR 702.16e)"
    assert bears.zone is Zone.BATTLEFIELD, (
        "a 2/2 that took none of the 2 damage is not destroyed (CR 704.5g)"
    )


def test_the_grant_switches_off_the_moment_the_memorial_leaves():
    """CR 613.6: nothing here is a duration expiring - the effect is simply
    not generated once its source is gone, the same as
    `test_indefinite_keyword_grant.py`'s True Conviction.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("bob", battlefield=["Hill Giant"])
        .player("alice", battlefield=["Akroma's Memorial", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    memorial = scenario.creature("Akroma's Memorial", "alice")

    scenario.game.destroy(memorial)
    assert scenario.game._effective_protection_qualities(bears) == []

    scenario.attack_with(giant, defending="alice")
    scenario.advance()
    scenario.block(giant, bears)
    scenario.combat_damage()

    assert bears.zone is Zone.GRAVEYARD, (
        "no more protection, so Hill Giant's 3 damage lands in full on a 2-toughness Bears"
    )


def test_granted_color_protection_still_stops_a_same_colored_spell_from_targeting():
    """CR 702.16b's targeting half, for a *colour* quality and a granted one.

    `Game.protection_refusal` reads the quality with the same matcher the
    damage half uses, so a colour is enforced at announcement (CR 601.2c) and
    not only prevented on resolution - the two halves of CR 702.16 agree about
    what "the stated quality" means."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob", battlefield=["Akroma's Memorial", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")

    with pytest.raises(ValueError, match="protection"):
        scenario.cast("Lightning Bolt", username="alice", targets=[bears])


# -- The equipped/enchanted-creature shape (Sword of Fire and Ice) ---------
#
# Everything above is the *anthem* shape ("Creatures you control have ...").
# Sword of Fire and Ice's own static is the other real shape that grants
# protection: "Equipped creature gets +2/+2 and has protection from red and
# from blue." - `_ATTACHED_CREATURE_STATIC_RE` (Cori-Steel Cutter's "gets
# +1/+1 and has trample and haste"), not the anthem regex. This is the
# off-set genericity proof for the widening that also closed Dragonfire
# Blade's "hexproof from monocolored" (fra-s10b): the same
# `_split_and_validate_keywords` tokenizer now reads a qualified "<keyword>
# from <quality>[ and from <quality>]*" item in *either* shape, rather than
# each shape carrying its own copy of that grammar.


def test_sword_of_fire_and_ice_grants_both_protection_qualities_once_equipped():
    """CR 702.16g: "protection from A and from B" is two abilities, and the
    equipped-creature shape splits them exactly the way the anthem shape
    above already does (`_split_protection_qualities`, shared by both)."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Sword of Fire and Ice", "Grizzly Bears", "Forest", "Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    sword = scenario.find("Sword of Fire and Ice", Zone.BATTLEFIELD, "alice")

    activation = equip_activation(scenario.game, sword, bears, "alice")
    payment = activation.begin_paying()
    for source in scenario.untapped_sources("Forest", "Forest", username="alice"):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    activation.resolve()

    board = computed(scenario)
    assert board.of(bears).has_ability("Protection from red")
    assert board.of(bears).has_ability("Protection from blue")
    assert bears.power == 4 and bears.toughness == 4


def test_the_granted_protection_from_the_equipped_shape_stops_a_matching_spell_from_targeting():
    """CR 702.16b again, off the equipped-creature shape rather than the
    anthem one - the same targeting enforcement, a different static ability
    producing the grant."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Sword of Fire and Ice", "Grizzly Bears", "Forest", "Forest"],
        )
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    sword = scenario.find("Sword of Fire and Ice", Zone.BATTLEFIELD, "alice")

    activation = equip_activation(scenario.game, sword, bears, "alice")
    payment = activation.begin_paying()
    for source in scenario.untapped_sources("Forest", "Forest", username="alice"):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    activation.resolve()

    with pytest.raises(ValueError, match="protection"):
        scenario.cast("Lightning Bolt", username="bob", targets=[bears])
