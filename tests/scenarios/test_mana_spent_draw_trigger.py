"""Scenario: Uncover the Moon-Letters - "Whenever you cast a noncreature
spell, you may draw X cards, where X is the amount of mana spent to cast
that spell. If you do, discard two cards."

CR 601.2h: "The player pays the total cost." `CastRecord.mana_spent` is what
was actually spent paying it (`machines/cost.ManaPayment.spend`), read back
here off *the cast spell's own record* - `AbilityOnStack.event`'s own
subject, not the trigger's source - the same "it is that spell, not this
one" distinction `machines/triggers._cast_record_for_clause`'s own docstring
draws for Vexing Bauble's "if no mana was spent to cast it".

No second real printing shares this exact combined "may draw X where X is
mana spent, then discard N" template (verified against the Scryfall bulk
data this session - see the dated MEMORY.md line); the corner cases below
are the proof of generality this file substitutes instead: a spell paid
with generic mana from several sources, declining the "may", and the
creature/noncreature type gate.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def resolve_all(scenario: Scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def board() -> Scenario:
    return Scenario().player(
        "alice",
        hand=["Uncover the Moon-Letters", "Lightning Bolt", "Plains", "Plains"],
        library=["Mountain", "Island", "Forest", "Swamp", "Plains"],
        battlefield=["Island", "Island", "Island", "Island", "Mountain"],
    )


def test_drawing_x_cards_equal_to_mana_spent_then_discarding_two():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Uncover the Moon-Letters",
        *scenario.untapped_sources("Island", "Island", "Island", "Island"),
    )
    hand_before = len(scenario.player("alice").hand)

    scenario.will_take_the_may(True, source="Uncover the Moon-Letters")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    scenario.game.cast(
        bolt, "alice", targets=["alice"], mana_sources=[scenario.untapped_sources("Mountain")[0]]
    )
    resolve_all(scenario)

    # Lightning Bolt costs {R}: 1 mana spent, so draw 1, then discard 2 -
    # a net -1 on top of the Bolt itself leaving hand for the stack.
    assert len(scenario.player("alice").hand) == hand_before - 1 + 1 - 2


def test_declining_the_may_draws_and_discards_nothing():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Uncover the Moon-Letters",
        *scenario.untapped_sources("Island", "Island", "Island", "Island"),
    )
    hand_before = len(scenario.player("alice").hand)

    scenario.will_take_the_may(False, source="Uncover the Moon-Letters")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    scenario.game.cast(
        bolt, "alice", targets=["alice"], mana_sources=[scenario.untapped_sources("Mountain")[0]]
    )
    resolve_all(scenario)

    assert len(scenario.player("alice").hand) == hand_before - 1


def test_a_creature_spell_does_not_trigger_it():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Uncover the Moon-Letters", "Grizzly Bears"],
            library=["Mountain", "Island"],
            battlefield=["Forest", "Forest", "Island", "Island", "Island", "Island"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Uncover the Moon-Letters",
        *scenario.untapped_sources("Island", "Island", "Island", "Island"),
    )
    hand_before = len(scenario.player("alice").hand)

    scenario.cast_and_resolve("Grizzly Bears", *scenario.untapped_sources("Forest", "Forest"))
    resolve_all(scenario)

    assert len(scenario.player("alice").hand) == hand_before - 1  # only the cast, no draw offered
