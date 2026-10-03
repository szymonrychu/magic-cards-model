"""Casting a modal double-faced card as its permanent back face (CR 712.11b),
and the permanent keeping that face up on the battlefield (CR 712.8f).

CR 712.11b: "A player casting a modal double-faced card or a copy of a modal
double-faced card as a spell chooses which face they are casting before
putting it onto the stack." CR 712.8f: "While a modal double-faced spell is on
the stack or a modal double-faced permanent is on the battlefield, it has only
the characteristics of the face that's up." CR 712.8a: off the battlefield and
stack it has only its front face's characteristics again.

Esika, God of the Tree // The Prismatic Bridge is the proving card: its back
face is a legendary enchantment whose upkeep trigger exists only while that
face is up. The same CR 712.8a reset is proven for a land face played under
CR 712.12 (Witch Enchanter // Witch-Blessed Meadow), which used to keep its
land face after leaving the battlefield.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import castable_faces
from magic_cards_model.models import Zone
from magic_cards_model.models.action import ActionKind
from magic_cards_model.models.card import Type
from tests.cards import card
from tests.scenarios.harness import Scenario

ESIKA = "Esika, God of the Tree"
ESIKA_CARD = "Esika, God of the Tree // The Prismatic Bridge"
BRIDGE = "The Prismatic Bridge"
FIVE_COLORS = ["Plains", "Island", "Swamp", "Mountain", "Forest"]


def _board(library: list[str] | None = None):
    return (
        Scenario()
        .player("alice", hand=[ESIKA_CARD], battlefield=list(FIVE_COLORS), library=library or [])
        .player("bob", library=["Forest"] * 5)
        .build()
    )


def _cast_bridge(scenario):
    casting = scenario.cast(ESIKA, "alice")
    casting.cast_as_split_half(BRIDGE)
    assert str(casting.base_cost) == "{W}{U}{B}{R}{G}"
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*FIVE_COLORS, username="alice"))
    spell = scenario.put_on_stack(casting)
    assert spell.name == BRIDGE
    assert spell.types == (Type.ENCHANTMENT,)
    scenario.resolve_top()
    return scenario.find(BRIDGE, Zone.BATTLEFIELD, "alice")


def test_a_permanent_back_face_is_a_cast_option() -> None:
    assert castable_faces(card(ESIKA_CARD)) == (None, BRIDGE)
    # CR 712.12: a land back face still is not.
    assert castable_faces(card("Valakut Awakening // Valakut Stoneforge")) == (None,)


def test_legal_actions_offer_both_faces_in_a_main_phase() -> None:
    scenario = _board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    esika = scenario.find(ESIKA, Zone.HAND, "alice")

    faces = {
        action.spell_face
        for action in scenario.game.legal_actions("alice")
        if action.kind is ActionKind.CAST and action.card_id == esika.id
    }

    assert faces == {None, BRIDGE}


def test_the_back_face_resolves_onto_the_battlefield_face_up() -> None:
    """CR 712.8f: the permanent has only The Prismatic Bridge's
    characteristics - a legendary enchantment, not a creature."""
    scenario = _board()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bridge = _cast_bridge(scenario)

    assert bridge.name == BRIDGE
    assert bridge.types == (Type.ENCHANTMENT,)
    assert Type.CREATURE not in scenario.game.characteristics_of(bridge).types
    assert "beginning of your upkeep" in bridge.oracle_text


def test_the_back_face_upkeep_trigger_fires() -> None:
    """The Prismatic Bridge's own trigger exists while its face is up."""
    scenario = _board(library=["Forest", "Grizzly Bears", "Forest"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _cast_bridge(scenario)

    for _ in range(40):
        if scenario.game.active_player.username == "alice" and scenario.step is Step.UPKEEP:
            break
        scenario.advance()
    assert scenario.step is Step.UPKEEP

    assert any(BRIDGE in item.name for item in [*scenario.pending_triggers, *scenario.game.stack])


def test_the_front_face_comes_back_once_it_leaves_the_battlefield() -> None:
    """CR 712.8a: back in the hand it is Esika again, and recast with no face
    named it resolves as the creature."""
    scenario = _board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bridge = _cast_bridge(scenario)

    in_hand = scenario.game.return_to_hand(bridge)

    assert in_hand.name == ESIKA
    assert Type.CREATURE in in_hand.types


def test_a_returned_land_face_is_its_front_face_again() -> None:
    """CR 712.8a for a CR 712.12 land face: Witch-Blessed Meadow returned to
    the hand is Witch Enchanter."""
    scenario = (
        Scenario()
        .player("alice", hand=["Witch Enchanter // Witch-Blessed Meadow"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    meadow = scenario.play_land("Witch Enchanter")
    assert meadow.name == "Witch-Blessed Meadow"

    in_hand = scenario.game.return_to_hand(meadow)

    assert in_hand.name == "Witch Enchanter"
    assert in_hand.land_face_played is None


def test_transforming_the_back_face_turns_the_front_face_up() -> None:
    """CR 701.27a: "turn it over so that its other face is up" - for a modal
    permanent cast as its back face, the other face is the front."""
    from magic_cards_model.machines.effects import transform_permanent

    scenario = _board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bridge = _cast_bridge(scenario)

    transform_permanent(scenario.game, bridge)

    assert bridge.name == ESIKA
    assert Type.CREATURE in bridge.types
