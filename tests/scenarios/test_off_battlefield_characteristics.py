"""Scenario: characteristics that exist only off the battlefield - "As long as
<this> isn't on the battlefield, it's a <P/T> <subtype> creature in addition
to its other types." (Grist, the Hunger Tide).

CR 113.6c: "An ability that states which zones it doesn't function in
functions everywhere except for the specified zones, even outside the game and
before the game begins." So in a hand, a library, a graveyard, exile and on
the stack Grist is a 1/1 Insect creature *and* a planeswalker - CR 205.1b's
"in addition to its other types" keeps the planeswalker type and the Grist
subtype - and on the battlefield it is a planeswalker only. It is not a
characteristic-defining ability: CR 604.3a's fifth criterion excludes an
ability that sets a value "only if certain conditions are met".

The bulk of this file is the readers that have to see it, one zone/filter
pair each, every one on a real printing that is not Grist:

- the stack: Essence Scatter's "counter target creature spell" may target it
  and Negate's "counter target noncreature spell" may not; Thalia, Guardian of
  Thraben's "Noncreature spells cost {1} more" does not tax it; Soul-Scar
  Mage's prowess ("Whenever you cast a noncreature spell", CR 702.108a) does
  not trigger;
- the hand: Duress's "noncreature, nonland card" cannot take it;
- the library: Grisly Salvage's "creature or land card" offers it, and
  Grist's own +1 counts a milled Grist as an Insect card;
- the graveyard: Raise Dead's "target creature card" finds it, Boneyard
  Wurm's CDA counts it, and Grist's own -5 counts it;
- exile: The Darkness Crystal's "target creature card exiled with" finds it.

And the other side of the zone line, on the battlefield: it is not a
creature, it enters from exile as a planeswalker only (CR 614.12's "as it
would exist on the battlefield" - Containment Priest's "nontoken creature
would enter" does not see it), and dying as a planeswalker is not a creature
dying (CR 603.10a's look-back), even though the card it leaves in the
graveyard is a creature card again.

No other Modern-, Pioneer- or Standard-legal printing carries this template
(Scryfall `o:"isn't on the battlefield"` returns Grist and Falkenrath Gorger,
whose "Each Vampire creature card you own that isn't on the battlefield has
madness" grants an ability, not a characteristic) - see
`docs/engine-coverage.md`.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Type
from magic_cards_model.models.card_state import Counter, ExileAnnotation, ExileMarker
from tests.scenarios.harness import Scenario

GRIST = "Grist, the Hunger Tide"


def _grist_in(zone: Zone):
    kwargs = {
        Zone.HAND: {"hand": [GRIST]},
        Zone.LIBRARY: {"library": [GRIST]},
        Zone.GRAVEYARD: {"graveyard": [GRIST]},
        Zone.EXILE: {"exile": [GRIST]},
    }[zone]
    scenario = Scenario().player("alice", **kwargs).player("bob").build()
    return scenario, scenario.find(GRIST, zone, "alice")


# --------------------------------------------------------------------------
# The characteristics themselves, zone by zone
# --------------------------------------------------------------------------


@pytest.mark.parametrize("zone", [Zone.HAND, Zone.LIBRARY, Zone.GRAVEYARD, Zone.EXILE])
def test_off_the_battlefield_grist_is_a_one_one_insect_creature_planeswalker(zone):
    """CR 113.6c's "everywhere except" and CR 205.1b's "in addition to its
    other types": the planeswalker type and the Grist subtype stay."""
    scenario, grist = _grist_in(zone)

    assert set(grist.types) == {Type.CREATURE, Type.PLANESWALKER}
    assert grist.is_creature
    assert grist.is_planeswalker
    assert set(grist.subtypes) == {"Grist", "Insect"}
    assert (grist.power, grist.toughness) == (1, 1)

    chars = scenario.game.characteristics_of(grist)
    assert chars.is_creature
    assert Type.PLANESWALKER in chars.types
    assert "Insect" in chars.subtypes
    assert (chars.power, chars.toughness) == (1, 1)


def test_on_the_battlefield_grist_is_a_planeswalker_only():
    """The ability's own "isn't on the battlefield": a permanent Grist is not
    a creature, not an Insect and has no power or toughness (CR 208.3)."""
    scenario = Scenario().player("alice", battlefield=[GRIST]).player("bob").build()
    grist = scenario.find(GRIST, Zone.BATTLEFIELD, "alice")

    assert grist.types == (Type.PLANESWALKER,)
    assert not grist.is_creature
    assert grist.subtypes == ("Grist",)
    assert grist.power is None and grist.toughness is None

    chars = scenario.game.characteristics_of(grist)
    assert chars.types == (Type.PLANESWALKER,)
    assert chars.subtypes == ("Grist",)
    assert chars.power is None
    assert grist.loyalty == 3


def test_a_copy_of_a_graveyard_grist_copies_no_creature_type():
    """CR 707.2: copiable values are the printed ones - the zone-conditional
    grant is an effect of a static ability, not printed text, so the layer-1
    starting point (`printed_characteristics`) never carries it even for a
    card sitting in a graveyard where the grant applies."""
    from magic_cards_model.machines.layers import printed_characteristics

    scenario, grist = _grist_in(Zone.GRAVEYARD)

    copiable = printed_characteristics(grist)
    assert copiable.types == (Type.PLANESWALKER,)
    assert copiable.subtypes == ("Grist",)
    assert copiable.power is None
    assert scenario.game.characteristics_of(grist).is_creature


# --------------------------------------------------------------------------
# The stack: a creature spell
# --------------------------------------------------------------------------


def _stack_board(bob_hand: list[str], bob_battlefield: list[str]) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=[GRIST], battlefield=["Swamp", "Forest", "Forest", "Swamp"])
        .player("bob", hand=bob_hand, battlefield=bob_battlefield)
    )


def test_grist_on_the_stack_is_a_one_one_creature_spell():
    scenario = _stack_board([], []).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    spell = scenario.cast_onto_stack(GRIST, username="alice", auto=True)

    assert spell.zone is Zone.STACK
    assert spell.is_creature and spell.is_planeswalker
    assert (spell.power, spell.toughness) == (1, 1)


def test_essence_scatter_counters_grist_as_a_creature_spell():
    """Essence Scatter: "Counter target creature spell." (CR 701.6a)."""
    scenario = _stack_board(["Essence Scatter"], ["Island", "Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    spell = scenario.cast_onto_stack(GRIST, username="alice", auto=True)
    scenario.pass_priority("alice")

    islands = scenario.untapped_sources("Island", "Island", username="bob")
    scenario.cast_and_resolve("Essence Scatter", *islands, username="bob", targets=[spell])

    assert spell.zone is Zone.GRAVEYARD
    assert scenario.stack_names() == []


def test_negate_cannot_target_grist_because_it_is_a_creature_spell():
    """Negate: "Counter target noncreature spell." A planeswalker spell that
    is also a creature spell is not a noncreature spell (CR 601.2c refuses)."""
    scenario = _stack_board(["Negate"], ["Island", "Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    spell = scenario.cast_onto_stack(GRIST, username="alice", auto=True)
    scenario.pass_priority("alice")

    with pytest.raises(ValueError):
        scenario.cast("Negate", username="bob").choose_targets([spell])


def test_thalia_guardian_of_thraben_does_not_tax_grist():
    """Thalia, Guardian of Thraben: "Noncreature spells cost {1} more to
    cast." Grist is a creature spell, so its three lands pay for it."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=[GRIST], battlefield=["Swamp", "Forest", "Forest"])
        .player("bob", battlefield=["Thalia, Guardian of Thraben"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lands = scenario.untapped_sources("Swamp", "Forest", "Forest", username="alice")

    grist = scenario.cast_and_resolve(GRIST, *lands, username="alice")

    assert grist.zone is Zone.BATTLEFIELD


def test_thalia_still_taxes_a_noncreature_spell_beside_it():
    """The contrast: Duress is a noncreature spell, and one Swamp no longer
    pays for it under Thalia."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Duress"], battlefield=["Swamp"])
        .player("bob", hand=[GRIST], battlefield=["Thalia, Guardian of Thraben"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (swamp,) = scenario.untapped_sources("Swamp", username="alice")

    with pytest.raises(ValueError):
        scenario.cast_and_resolve("Duress", swamp, username="alice", targets=["bob"])


def test_prowess_does_not_trigger_on_casting_grist():
    """Soul-Scar Mage's prowess: "Whenever you cast a noncreature spell"
    (CR 702.108a). Grist is a creature spell."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=[GRIST],
            battlefield=["Soul-Scar Mage", "Swamp", "Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_onto_stack(GRIST, username="alice", auto=True)

    assert scenario.stack_names() == [GRIST]
    assert scenario.pending_triggers == []


# --------------------------------------------------------------------------
# The hand and the library
# --------------------------------------------------------------------------


def test_duress_cannot_take_grist_as_a_noncreature_card():
    """Duress: "You choose a noncreature, nonland card from it." Grist in a
    hand is a creature card, so only the Lightning Bolt beside it is offered."""
    scenario = (
        Scenario()
        .player("alice", hand=["Duress"], battlefield=["Swamp"])
        .player("bob", hand=[GRIST, "Lightning Bolt"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")
    grist = scenario.find(GRIST, Zone.HAND, "bob")
    scenario.will_choose_cards(bolt, source="Duress")

    (swamp,) = scenario.untapped_sources("Swamp", username="alice")
    scenario.cast_and_resolve("Duress", swamp, username="alice", targets=["bob"])

    (choice,) = [d for d in scenario.questions_asked() if d.kind is DecisionKind.CHOOSE_CARDS]
    assert grist.id not in choice.cards
    assert bolt.zone is Zone.GRAVEYARD
    assert grist.zone is Zone.HAND


def test_grisly_salvage_offers_grist_as_a_creature_card():
    """Grisly Salvage: "You may put a creature or land card from among them
    into your hand." Grist in the library is a creature card."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Grisly Salvage"],
            battlefield=["Swamp", "Forest"],
            library=[GRIST, "Lightning Bolt", "Negate", "Duress", "Opt", "Swamp"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    grist, bolt, negate, duress, opt = scenario.top_of_library(5)
    scenario.will_take_the_may(source="Grisly Salvage")
    scenario.will_choose_cards(grist, source="Grisly Salvage")

    mana = scenario.untapped_sources("Swamp", "Forest", username="alice")
    scenario.cast_and_resolve("Grisly Salvage", *mana)

    (choice,) = [
        d
        for d in scenario.questions_asked()
        if d.kind is DecisionKind.CHOOSE_CARDS and d.source == "Grisly Salvage"
    ]
    assert set(choice.cards) == {grist.id}
    assert grist.zone is Zone.HAND


def test_grists_plus_one_counts_a_milled_grist_as_an_insect_card():
    """Grist's +1: "If an Insect card was milled this way, put a loyalty
    counter on Grist and repeat this process." A second Grist milled is an
    Insect card in the graveyard; the Island after it is not."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=[GRIST], library=[GRIST, "Island"])
        .player("bob", library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    grist = scenario.find(GRIST, Zone.BATTLEFIELD, "alice")

    scenario.activate(grist, index=0)
    scenario.pass_until_resolved()

    assert grist.loyalty == 5, "3 printed + 1 activation cost + 1 for the milled Grist"
    insects = [s for s in scenario.game.battlefield if s.token and "Insect" in s.subtypes]
    assert len(insects) == 2
    assert [s.name for s in scenario.player("alice").graveyard] == [GRIST, "Island"]


# --------------------------------------------------------------------------
# The graveyard
# --------------------------------------------------------------------------


def test_raise_dead_returns_grist_as_a_creature_card():
    """Raise Dead: "Return target creature card from your graveyard to your
    hand." (CR 115.1's target, checked on the graveyard card)."""
    scenario = (
        Scenario()
        .player("alice", hand=["Raise Dead"], battlefield=["Swamp"], graveyard=[GRIST])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    grist = scenario.find(GRIST, Zone.GRAVEYARD, "alice")

    (swamp,) = scenario.untapped_sources("Swamp", username="alice")
    scenario.cast_and_resolve("Raise Dead", swamp, username="alice", targets=[grist])

    assert grist.zone is Zone.HAND


def test_boneyard_wurm_counts_grist_as_a_creature_card():
    """Boneyard Wurm's CDA counts "creature cards in your graveyard"."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Boneyard Wurm"], graveyard=[GRIST, "Lightning Bolt"])
        .player("bob")
        .build()
    )
    wurm = scenario.find("Boneyard Wurm", Zone.BATTLEFIELD, "alice")

    assert scenario.game.power_of(wurm) == 1
    assert scenario.game.toughness_of(wurm) == 1


def _minus_five(loyalty_added: int) -> Scenario:
    scenario = (
        Scenario()
        .player("alice", battlefield=[GRIST], graveyard=[GRIST, "Lightning Bolt"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    grist = scenario.find(GRIST, Zone.BATTLEFIELD, "alice")
    scenario.game.add_counters(grist, Counter.LOYALTY, loyalty_added)
    scenario.activate(grist, index=2)
    scenario.resolve_top()
    return scenario


def test_grists_minus_five_counts_a_graveyard_grist():
    """Grist's -5 counts "creature cards in your graveyard" - a Grist card
    there is one (and the Bolt is not). The activating Grist stays at 1
    loyalty, on the battlefield, where it is no creature card."""
    scenario = _minus_five(loyalty_added=3)

    assert scenario.find(GRIST, Zone.BATTLEFIELD, "alice").loyalty == 1
    assert scenario.player("bob").life == 19


def test_a_grist_that_minus_fived_to_zero_counts_itself():
    """Paying -5 from 5 loyalty leaves Grist at 0, and CR 704.5i puts it into
    the graveyard before the ability resolves - where it is a creature card
    too, so both Grists count."""
    scenario = _minus_five(loyalty_added=2)

    assert [s.name for s in scenario.player("alice").graveyard].count(GRIST) == 2
    assert scenario.player("bob").life == 18


# --------------------------------------------------------------------------
# Exile, and entering the battlefield from it
# --------------------------------------------------------------------------


def _crystal_with_grist_exiled(bob_battlefield: list[str] | None = None):
    scenario = (
        Scenario()
        .player("alice", hand=["The Darkness Crystal"], battlefield=["Swamp"] * 10)
        .player("bob", graveyard=[GRIST], battlefield=bob_battlefield or [])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp")
    crystal = scenario.cast_and_resolve("The Darkness Crystal", *sources)

    grist = scenario.find(GRIST, Zone.GRAVEYARD, "bob")
    # Real state staged by hand, the same way `test_the_darkness_crystal.py`
    # stages it: the Crystal's own exiling paragraph is a separate replacement.
    scenario.player("bob").cards_in(Zone.GRAVEYARD).remove(grist)
    with scenario.game._id_allocator_scope():  # noqa: SLF001
        grist.move_to(Zone.EXILE)
    grist.exile_annotation = ExileAnnotation(
        marker=ExileMarker.IMPRINTED, owner=grist.owner, linked_permanent_id=crystal.id
    )
    scenario.game.exile.append(grist)
    return scenario, crystal, grist


def test_the_darkness_crystal_returns_an_exiled_grist_as_a_planeswalker():
    """The Darkness Crystal: "Put target creature card exiled with The
    Darkness Crystal onto the battlefield ..." Grist in exile is a creature
    card, so it is a legal target; on the battlefield it is a planeswalker
    with its printed loyalty (CR 306.5b) and no creature type."""
    scenario, crystal, grist = _crystal_with_grist_exiled()
    assert grist.is_creature

    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp", "Swamp", "Swamp")
    scenario.activate(crystal, *sources, targets=[grist])
    scenario.resolve_top()

    assert grist.zone is Zone.BATTLEFIELD
    assert grist.controller == "alice"
    assert not grist.is_creature
    assert not scenario.game.characteristics_of(grist).is_creature
    assert grist.loyalty == 3


def test_containment_priest_does_not_see_grist_entering_as_a_creature():
    """Containment Priest: "If a nontoken creature would enter and it wasn't
    cast, exile it instead." CR 614.12: which replacement applies is decided
    by the characteristics the permanent "would exist" with on the
    battlefield - and there Grist is not a creature, even though it is one in
    the exile zone it is coming from."""
    scenario, crystal, grist = _crystal_with_grist_exiled(bob_battlefield=["Containment Priest"])

    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp", "Swamp", "Swamp")
    scenario.activate(crystal, *sources, targets=[grist])
    scenario.resolve_top()

    assert grist.zone is Zone.BATTLEFIELD


# --------------------------------------------------------------------------
# Leaving the battlefield: a planeswalker died, a creature card arrived
# --------------------------------------------------------------------------


def test_grist_dying_as_a_planeswalker_is_not_a_creature_dying():
    """CR 603.10a's look-back reads Grist as it last existed on the
    battlefield - a planeswalker - so no creature died this turn; the card it
    leaves in the graveyard is a creature card again (CR 113.6c)."""
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob", battlefield=[GRIST])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    grist = scenario.find(GRIST, Zone.BATTLEFIELD, "bob")

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=[grist])
    scenario.state_based_actions()

    assert grist.zone is Zone.GRAVEYARD
    assert scenario.game.creatures_died_this_turn == 0
    assert grist.is_creature
    assert grist.last_known_types == (Type.PLANESWALKER,)
