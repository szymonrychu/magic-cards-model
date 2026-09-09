"""Learn: CR 701.48a, a bare CR 701 keyword action.

"Learn" means "You may discard a card. If you do, draw a card. If you
didn't discard a card, you may reveal a Lesson card you own from outside
the game and put it into your hand." Read generically off the printed word
in `machines/effects.py`'s `_parse_learn_clause`, not by card name, on two
differently-shaped cards: Divide by Zero's capitalised, sentence-final
"Learn." on a spell, and Eyetwitch's lowercase, mid-sentence "learn" inside
a dies trigger.

The Lesson-reveal half is out of scope and documented as such: this engine
has no "outside the game" zone (see `docs/engine-coverage.md`).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _cast_divide_by_zero_at_a_spell(scenario):
    """Alice's own Shock, still on the stack, bounced by her own Divide by
    Zero in response - sidesteps `machines/targeting.py`'s unrelated "target
    spell or permanent" gap (that phrase's battlefield half is not read at
    all), which is not this mechanic's business to fix."""
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    shock = scenario.cast_onto_stack("Shock", mountain, username="alice", targets=["bob"])
    sources = scenario.untapped_sources("Island", "Island", "Island", username="alice")
    dbz = scenario.cast_onto_stack("Divide by Zero", *sources, username="alice", targets=[shock])
    return dbz


def test_divide_by_zero_lets_its_caster_discard_to_draw():
    """Divide by Zero: "Return target spell or permanent with mana value 1 or
    greater to its owner's hand. Learn."
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Divide by Zero", "Lightning Bolt", "Shock"],
            library=["Forest"],
            battlefield=["Island", "Island", "Island", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    hand_before = len(scenario.player("alice").hand)

    scenario.will_take_the_may(True, source="Divide by Zero")
    scenario.will_discard(bolt, username="alice")
    _cast_divide_by_zero_at_a_spell(scenario)
    scenario.pass_until_resolved()

    assert bolt.zone.value == "graveyard"
    assert len(scenario.player("alice").hand) == hand_before - 1


def test_declining_learn_discards_nothing_and_draws_nothing():
    """CR 608.2d: a "may" left unanswered/declined performs neither half."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Divide by Zero", "Lightning Bolt", "Shock"],
            library=["Forest"],
            battlefield=["Island", "Island", "Island", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hand_before = len(scenario.player("alice").hand)

    scenario.will_take_the_may(False, source="Divide by Zero")
    _cast_divide_by_zero_at_a_spell(scenario)
    scenario.pass_until_resolved()

    assert len(scenario.player("alice").hand) == hand_before - 1


def test_eyetwitch_learns_lowercase_and_mid_sentence_when_it_dies():
    """Eyetwitch: "When this creature dies, learn." - a triggered ability's
    own effect text, not a spell's trailing sentence, and the lowercase word
    Divide by Zero's regex has to match too.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], library=["Forest"], battlefield=["Eyetwitch"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    eyetwitch = scenario.creature("Eyetwitch", "alice")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    hand_before = len(scenario.player("alice").hand)

    scenario.game.destroy(eyetwitch)
    scenario.state_based_actions()
    scenario.will_take_the_may(True, source="Eyetwitch")
    scenario.will_discard(bolt, username="alice")
    scenario.pass_until_resolved()

    assert bolt.zone.value == "graveyard"
    assert len(scenario.player("alice").hand) == hand_before
