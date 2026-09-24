"""Adventure: cast the small half, exile it, cast the creature later (CR 715).

CR 715.3: "As a player plays an adventurer card, the player chooses whether they
play the card normally or as an Adventure." CR 715.3a: "When casting an
adventurer card as an Adventure, only the alternative characteristics are
evaluated to see if it can be cast." CR 715.3b: "While on the stack as an
Adventure, the spell has only its alternative characteristics." CR 715.4: "In
every zone except the stack, and while on the stack not as an Adventure, an
adventurer card has only its normal characteristics."

CR 715.3d is the part that needs annotated exile: "Instead of putting a spell
that was cast as an Adventure into its owner's graveyard as it resolves, its
controller exiles it. For as long as that card remains exiled, that player may
play it."

Adventure is not a CR 702 keyword - there is no `Adventure [cost]` line to parse
- so the whole thing is read off the card's faces: `CardState.face_played`
carries the announced half (CR 715.3b), and the exile on resolution is a
registered stack replacement (CR 715.3d).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import (
    adventure_face,
    exile_adventured,
    keyword_cast_options,
)
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Type
from magic_cards_model.models.card_state import ExileMarker
from magic_cards_model.models.mana import ManaCost
from tests.cards import card, card_state
from tests.scenarios.harness import Scenario


def board(lands: int = 5) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Bonecrusher Giant"], battlefield=["Mountain"] * lands)
        .player("bob", battlefield=["Grizzly Bears"])
    )


# -- reading the card -------------------------------------------------------


def test_the_adventure_half_is_found_by_its_type_line():
    """CR 715.1: the inset frame is the one whose type line says Adventure."""
    face = adventure_face(card("Bonecrusher Giant"))

    assert face is not None
    assert face.name == "Stomp"
    assert face.mana_cost == "{1}{R}"


def test_a_card_with_no_adventure_has_no_adventure_face():
    assert adventure_face(card("Grizzly Bears")) is None


def test_an_adventurer_card_offers_a_cast_from_exile():
    """CR 715.3d: while it remains exiled, its controller may play it."""
    (option,) = keyword_cast_options(card("Bonecrusher Giant"))

    assert option.keyword == "Adventure"
    assert option.zone is Zone.EXILE
    assert option.marker is ExileMarker.ADVENTURED
    assert option.pays_mana_cost is True


def test_a_spell_on_the_stack_as_an_adventure_reads_the_adventure_face():
    """CR 715.3b, the half of it that lives on `CardState`.

    "While on the stack as an Adventure, the spell has only its alternative
    characteristics." `CardState.face_played` is where the announced half is
    recorded and `CardState.up_face` is what reads it - the same field and the
    same read a split card's chosen half already goes through (CR 709.3b),
    both being one mechanism. Set here directly to pin the field's own
    behaviour in isolation; `machines/casting.Casting.cast` is what writes it
    in a real announcement, and the tests below drive that path.
    """
    stomp = card_state("Bonecrusher Giant", zone=Zone.STACK, controller="alice")
    stomp.face_played = "Stomp"

    assert stomp.name == "Stomp"
    assert stomp.types == (Type.INSTANT,)
    assert stomp.is_permanent is False
    assert stomp.mana_cost == "{1}{R}"
    assert "deals 2 damage to any target" in stomp.oracle_text


def test_off_the_stack_it_is_the_adventurer_card_again():
    """CR 715.4: "In every zone except the stack, and while on the stack not as
    an Adventure, an adventurer card has only its normal characteristics." The
    Bonecrusher Giant in a graveyard is a Giant, whatever half was last cast.
    """
    stomp = card_state("Bonecrusher Giant", zone=Zone.STACK, controller="alice")
    stomp.face_played = "Stomp"
    assert stomp.name == "Stomp"

    stomp.move_to(Zone.GRAVEYARD)

    assert stomp.name == "Bonecrusher Giant"
    assert stomp.types == (Type.CREATURE,)


# -- casting the two halves -------------------------------------------------


def test_casting_it_normally_costs_the_creature_halfs_mana_cost():
    """CR 715.3: the caster chooses; choosing "normally" is the front face.

    Scryfall prints both halves in one string, `{2}{R} // {1}{R}`, so reading the
    whole string would charge {3}{R}{R} for either half.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Bonecrusher Giant")

    assert casting.total_cost.mana == ManaCost.parse("{2}{R}")


def test_casting_it_as_an_adventure_costs_the_adventure_halfs_mana_cost():
    """CR 715.3a: only the alternative characteristics are evaluated."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Bonecrusher Giant")
    casting.cast_as_adventure()

    assert casting.face == "Stomp"
    assert casting.total_cost.mana == ManaCost.parse("{1}{R}")


def test_the_adventure_reaches_the_stack_for_two_mana():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    sources = scenario.untapped_sources("Mountain", "Mountain")
    casting = scenario.cast("Bonecrusher Giant")
    casting.cast_as_adventure()
    # CR 715.3b: on the stack as an Adventure the spell has only Stomp's
    # characteristics, and Stomp's own text is "Stomp deals 2 damage to any
    # target." - so CR 601.2c requires a target announced for it. This cast
    # used to go through with none, because the announcement was read against
    # the whole printing, whose front face names no target at all.
    casting.choose_targets([scenario.creature("Grizzly Bears", "bob")])
    scenario.pay_with(casting.begin_paying(), *sources)
    stomp = scenario.put_on_stack(casting)

    assert stomp.zone is Zone.STACK


def test_a_card_with_no_adventure_cannot_be_cast_as_one():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Grizzly Bears"], battlefield=["Forest", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Grizzly Bears")

    with pytest.raises(ValueError, match="no Adventure"):
        casting.cast_as_adventure()


# -- the exile, and the creature that follows -------------------------------


def test_an_exiled_adventure_is_marked_and_can_be_cast_as_the_creature():
    """CR 715.3d, applied by hand: exile it, then cast the creature for {2}{R}."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    sources = scenario.untapped_sources("Mountain", "Mountain")
    casting = scenario.cast("Bonecrusher Giant")
    casting.cast_as_adventure()
    # CR 715.3b: on the stack as an Adventure the spell has only Stomp's
    # characteristics, and Stomp's own text is "Stomp deals 2 damage to any
    # target." - so CR 601.2c requires a target announced for it. This cast
    # used to go through with none, because the announcement was read against
    # the whole printing, whose front face names no target at all.
    casting.choose_targets([scenario.creature("Grizzly Bears", "bob")])
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)
    stomp = scenario.resolve_top()
    exile_adventured(scenario.game, stomp, "alice")

    assert stomp.zone is Zone.EXILE
    assert stomp.exile_annotation is not None
    assert stomp.exile_annotation.marker is ExileMarker.ADVENTURED

    giant_casting = scenario.cast("Bonecrusher Giant", from_zone=Zone.EXILE)
    giant_casting.use_keyword("Adventure")

    assert giant_casting.total_cost.mana == ManaCost.parse("{2}{R}")

    remaining = scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    scenario.pay_with(giant_casting.begin_paying(), *remaining)
    on_stack = scenario.put_on_stack(giant_casting)
    # The creature half is cast from exile, a shared zone (CR 400.2). It must
    # leave exile as it goes onto the stack, not stay in both at once - the
    # duplication bug `Game.put_on_stack` used to have.
    assert scenario.zones_containing(on_stack) == ["shared:stack"]

    giant = scenario.resolve_top()

    assert giant.zone is Zone.BATTLEFIELD
    assert giant not in scenario.game.exile


def test_casting_the_adventured_creature_without_announcing_adventure_is_refused():
    """The `test_flashback.py` live-game defect, generalized to CR 715.3d's
    Adventure exile: `pays_mana_cost=True` there too (the creature's own
    `{2}{R}` is the right cost), but the permission to cast it from exile at
    all is still tied to the Adventure keyword - a caster who never calls
    `use_keyword("Adventure")` must be refused, not let through just because
    the fallback cost happens to be correct.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    sources = scenario.untapped_sources("Mountain", "Mountain")
    casting = scenario.cast("Bonecrusher Giant")
    casting.cast_as_adventure()
    # CR 715.3b: on the stack as an Adventure the spell has only Stomp's
    # characteristics, and Stomp's own text is "Stomp deals 2 damage to any
    # target." - so CR 601.2c requires a target announced for it. This cast
    # used to go through with none, because the announcement was read against
    # the whole printing, whose front face names no target at all.
    casting.choose_targets([scenario.creature("Grizzly Bears", "bob")])
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)
    stomp = scenario.resolve_top()
    exile_adventured(scenario.game, stomp, "alice")

    remaining = scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    giant_casting = scenario.cast("Bonecrusher Giant", from_zone=Zone.EXILE)
    assert giant_casting.total_cost.mana == ManaCost.parse("{2}{R}")
    scenario.pay_with(giant_casting.begin_paying(), *remaining)

    with pytest.raises(ValueError, match="Adventure"):
        giant_casting.cast()
    giant_casting.cancel()

    assert stomp.zone is Zone.EXILE
    assert all(source.untapped for source in remaining)


def test_an_unmarked_adventurer_card_in_exile_may_not_be_cast_from_there():
    """CR 601.3: only the CR 715.3d pile carries the permission (CR 406.4)."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", exile=["Bonecrusher Giant"], battlefield=["Mountain"] * 3)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Bonecrusher Giant", from_zone=Zone.EXILE)

    with pytest.raises(ValueError, match="not adventured"):
        casting.use_keyword("Adventure")


# -- resolving as an Adventure ----------------------------------------------


def test_an_adventure_exiles_itself_on_resolution():
    """CR 715.3d: exiled instead of put into its owner's graveyard."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    sources = scenario.untapped_sources("Mountain", "Mountain")
    casting = scenario.cast("Bonecrusher Giant")
    casting.cast_as_adventure()
    # CR 715.3b: on the stack as an Adventure the spell has only Stomp's
    # characteristics, and Stomp's own text is "Stomp deals 2 damage to any
    # target." - so CR 601.2c requires a target announced for it. This cast
    # used to go through with none, because the announcement was read against
    # the whole printing, whose front face names no target at all.
    casting.choose_targets([scenario.creature("Grizzly Bears", "bob")])
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)
    stomp = scenario.resolve_top()

    assert stomp.zone is Zone.EXILE


def test_an_adventure_on_the_stack_is_an_instant_and_not_a_creature():
    """CR 715.3b: on the stack as an Adventure it has only Stomp's types."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    sources = scenario.untapped_sources("Mountain", "Mountain")
    casting = scenario.cast("Bonecrusher Giant")
    casting.cast_as_adventure()
    # CR 715.3b: on the stack as an Adventure the spell has only Stomp's
    # characteristics, and Stomp's own text is "Stomp deals 2 damage to any
    # target." - so CR 601.2c requires a target announced for it. This cast
    # used to go through with none, because the announcement was read against
    # the whole printing, whose front face names no target at all.
    casting.choose_targets([scenario.creature("Grizzly Bears", "bob")])
    scenario.pay_with(casting.begin_paying(), *sources)
    stomp = scenario.put_on_stack(casting)

    assert stomp.is_permanent is False


# -- CR 715.3a/715.3b: the Adventure half's own characteristics -------------
#
# `Casting.targeting`, `Game._announcement_profile` and
# `Game._resolution_profile` were all scoped to `Layout.SPLIT`, so an
# Adventure spell was announced against the *whole printing's* profile. For
# Bonecrusher Giant that profile is the Giant's own trigger text, which names
# no target at all - so a targetless Stomp was cast happily and resolved
# dealing no damage, and a targeted one was refused "too many targets: 1
# chosen where the spell takes at most 0". CR 715.3a is word for word CR
# 709.3a's test ("only the alternative characteristics are evaluated to see if
# it can be cast") and CR 715.3b word for word CR 709.3b's, so the two layouts
# get the same reading.


def test_the_adventure_half_announces_its_own_target_requirement():
    """CR 715.3b: on the stack as an Adventure the spell has only Stomp's
    characteristics, and Stomp's text is "Stomp deals 2 damage to any target."
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Bonecrusher Giant")
    casting.cast_as_adventure()

    profile = casting.targeting
    assert profile.understood
    assert [requirement.phrase for requirement in profile.requirements] == ["any target"]


def test_the_adventure_half_refuses_a_cast_with_no_target():
    """CR 601.2c: a spell that requires a target may not be cast without one.
    This used to be allowed, and the spell then resolved doing nothing.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Bonecrusher Giant")
    casting.cast_as_adventure()
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Mountain", "Mountain"))

    with pytest.raises(ValueError, match="target"):
        casting.cast()
    casting.cancel()


def test_the_adventure_half_deals_its_damage_to_the_chosen_target():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    casting = scenario.cast("Bonecrusher Giant")
    casting.cast_as_adventure()
    casting.choose_targets([bears])
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Mountain", "Mountain"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bears.zone is Zone.GRAVEYARD, "2 damage to a 2/2 (CR 704.5g)"


def test_the_adventure_row_reports_the_adventure_halfs_own_slots():
    """`Action.target_slots` on the Stomp row is Stomp's requirement; the
    plain creature row (`spell_face=None`) carries none.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    rows = {
        action.spell_face: tuple(slot.phrase for slot in action.target_slots)
        for action in scenario.game.legal_actions("alice")
        if action.card_id == scenario.find("Bonecrusher Giant", Zone.HAND, "alice").id
    }

    assert rows["Stomp"] == ("any target",)
    assert rows[None] == ()


def test_legal_targets_for_the_adventure_face_is_the_adventure_halfs_own():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.find("Bonecrusher Giant", Zone.HAND, "alice")
    bears = scenario.creature("Grizzly Bears", "bob")

    (candidates,) = scenario.game.legal_targets(giant, "alice", spell_face="Stomp")

    assert bears in candidates
    assert scenario.game.legal_targets(giant, "alice") == ()


def test_an_instant_adventure_half_may_be_cast_at_instant_speed():
    """CR 715.3a: only the alternative characteristics are evaluated to see if
    it can be cast, and Stomp's is `Instant - Adventure`. The creature half
    is a Creature with no flash and stays sorcery-speed, so the enumeration
    at upkeep offers the Stomp row and no plain-creature row at all.

    Bonecrusher Giant's own front-face Creature type used to answer for both:
    Stomp, a plain Instant, was refused during an upkeep step.
    """
    scenario = board().build()
    scenario.start_at(Step.UPKEEP)
    giant = scenario.find("Bonecrusher Giant", Zone.HAND, "alice")

    faces = {
        action.spell_face
        for action in scenario.game.legal_actions("alice")
        if action.card_id == giant.id
    }
    assert faces == {"Stomp"}, "the Giant itself is a Creature (CR 302.1)"

    casting = scenario.cast("Bonecrusher Giant")
    casting.cast_as_adventure()
    assert casting.face == "Stomp"
    casting.cancel()

    # The creature half proposes fine - CR 601.2a's move is allowed because
    # *some* face of this card is castable right now - and is refused at
    # CR 601.2i, against the answer frozen at the proposal.
    giant_casting = scenario.cast("Bonecrusher Giant")
    scenario.pay_with(
        giant_casting.begin_paying(), *scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    )
    with pytest.raises(ValueError, match="CR 117.1a"):
        giant_casting.cast()
    giant_casting.cancel()


# -- generality: an adventurer card this wave did not motivate -------------


def test_another_adventurer_cards_adventure_half_reads_its_own_text():
    """Murderous Rider // Swift End - not the card either defect was found
    on, in no decklist here, and a different phrase, cost shape and effect:
    Swift End is `{1}{B}{B}` "Destroy target creature or planeswalker. You
    lose 2 life." against Stomp's `{1}{R}` "any target" damage.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Murderous Rider"], battlefield=["Swamp"] * 3)
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.UPKEEP)
    bears = scenario.creature("Grizzly Bears", "bob")

    rider = scenario.find("Murderous Rider", Zone.HAND, "alice")
    rows = {
        action.spell_face: tuple(slot.phrase for slot in action.target_slots)
        for action in scenario.game.legal_actions("alice")
        if action.card_id == rider.id
    }
    assert rows["Swift End"] == ("target creature or planeswalker",)
    assert None not in rows, "the Zombie Knight is a Creature, not castable at upkeep"

    casting = scenario.cast("Murderous Rider")
    casting.cast_as_adventure()
    casting.choose_targets([bears])
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Swamp", "Swamp", "Swamp"))
    stack = scenario.put_on_stack(casting)
    assert Type.INSTANT in stack.types, "CR 715.3b"
    scenario.resolve_top()

    assert bears.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 18, "Swift End's own rider"


# -- the exile a real resolution makes --------------------------------------


def test_a_resolved_adventure_is_exiled_in_the_adventured_pile_without_help():
    """CR 715.3d, as the resolution itself performs it: "its controller exiles
    it. For as long as that card remains exiled, that player may play it." The
    tests above apply `exile_adventured` by hand; a real game has no such
    hand, so the stack replacement has to leave the card in the adventured
    pile itself, or the creature half can never be cast from there.

    Found by the behavioural sweep (`tests/test_behavioural_sweep.py`): no
    "cast a spell from exile" trigger could be raised through an Adventure.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Bonecrusher Giant")
    casting.cast_as_adventure()
    casting.choose_targets([scenario.creature("Grizzly Bears", "bob")])
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Mountain", "Mountain"))
    scenario.put_on_stack(casting)
    giant = scenario.resolve_top()

    assert giant.zone is Zone.EXILE
    assert giant.exile_annotation is not None
    assert giant.exile_annotation.marker is ExileMarker.ADVENTURED
    assert giant.exile_annotation.owner == "alice"

    creature = scenario.cast("Bonecrusher Giant", from_zone=Zone.EXILE)
    creature.use_keyword("Adventure")
    scenario.pay_with(
        creature.begin_paying(), *scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    )
    scenario.put_on_stack(creature)
    assert scenario.resolve_top().zone is Zone.BATTLEFIELD


def test_another_adventurers_resolved_adventure_is_marked_too():
    """The same replacement on a different adventurer (Murderous Rider's Swift
    End, which also costs its caster 2 life): the pile is the rule's, not the
    card's."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Murderous Rider"], battlefield=["Swamp"] * 3)
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Murderous Rider")
    casting.cast_as_adventure()
    casting.choose_targets([scenario.creature("Grizzly Bears", "bob")])
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Swamp", "Swamp", "Swamp"))
    scenario.put_on_stack(casting)
    rider = scenario.resolve_top()

    assert rider.zone is Zone.EXILE
    assert rider.exile_annotation is not None
    assert rider.exile_annotation.marker is ExileMarker.ADVENTURED


# -- CR 715.3d: "It can't be cast as an Adventure this way" -----------------


def test_the_adventure_half_cannot_be_recast_from_the_adventured_exile():
    """CR 715.3d: "For as long as that card remains exiled, that player may
    play it. It can't be cast as an Adventure this way." The permission
    `use_keyword("Adventure")` claims covers the creature face only, so
    Stomp named on top of it is refused at CR 601.2i."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Bonecrusher Giant")
    casting.cast_as_adventure()
    casting.choose_targets([scenario.creature("Grizzly Bears", "bob")])
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Mountain", "Mountain"))
    scenario.put_on_stack(casting)
    assert scenario.resolve_top().zone is Zone.EXILE

    again = scenario.cast("Bonecrusher Giant", from_zone=Zone.EXILE)
    again.use_keyword("Adventure")
    with pytest.raises(ValueError, match=r"CR 715\.3d"):
        again.cast_as_adventure()
    again.cancel()
    assert again.spell.zone is Zone.EXILE

    # Named first and claimed second, the finished cast is refused instead.
    again = scenario.cast("Bonecrusher Giant", from_zone=Zone.EXILE)
    again.cast_as_adventure()
    again.use_keyword("Adventure")
    again.choose_targets(["bob"])
    scenario.pay_with(again.begin_paying(), *scenario.untapped_sources("Mountain", "Mountain"))
    with pytest.raises(ValueError, match=r"CR 715\.3d"):
        again.cast()
    again.cancel()
    assert again.spell.zone is Zone.EXILE


def test_another_adventurers_sorcery_half_cannot_be_recast_from_exile_either():
    """The same limit on Lovestruck Beast's Heart's Desire (a sorcery with no
    target): the permission's own shape, never Bonecrusher Giant's."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lovestruck Beast"], battlefield=["Forest"] * 4)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Lovestruck Beast")
    casting.cast_as_adventure()
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Forest"))
    scenario.put_on_stack(casting)
    assert scenario.resolve_top().zone is Zone.EXILE

    again = scenario.cast("Lovestruck Beast", from_zone=Zone.EXILE)
    again.use_keyword("Adventure")
    with pytest.raises(ValueError, match=r"CR 715\.3d"):
        again.cast_as_adventure()
    again.cancel()

    beast = scenario.cast("Lovestruck Beast", from_zone=Zone.EXILE)
    beast.use_keyword("Adventure")
    scenario.pay_with(
        beast.begin_paying(), *scenario.untapped_sources("Forest", "Forest", "Forest")
    )
    scenario.put_on_stack(beast)
    assert scenario.resolve_top().zone is Zone.BATTLEFIELD
