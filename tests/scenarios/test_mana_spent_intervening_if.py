"""CR 601.2h: what mana was spent to cast a spell, read back by an intervening
*if* (CR 603.4).

Every CR number below was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file.

- **CR 601.2h** - "The player pays the total cost... First, they pay all costs
  that don't involve random elements..." This is the moment the mana actually
  leaves the pool, and `machines/cost.CostPayment.pay` is where it happens -
  `ManaPayment.spend` is exactly what was spent, by colour.
- **CR 603.4 / CR 608.2a** - the intervening *if* is checked when the trigger
  event occurs, and rechecked on resolution.

Before this fix, nothing recorded what CR 601.2h actually spent against the
spell it paid for, so "if no mana was spent to cast it" (Vexing Bauble) and
"if [mana] was spent to cast it" (Wistfulness, Drowner of Truth) all failed
closed - `InterveningIfNotice` recorded the refusal, and the ability never
triggered either way (see `test_intervening_if.py`'s old version of this file,
and `docs/engine-coverage.md`). Now `Game.note_cast` records
`CostPayment.mana_payment.spend` onto `CastRecord.mana_spent` as the spell goes
on the stack (`machines/casting.Casting.cast`), and
`machines/triggers.intervening_if_holds` reads it back - both branches, of
every clause.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color
from tests.scenarios.harness import Scenario

# --------------------------------------------------------------------------
# Vexing Bauble: "if no mana was spent to cast it"
# --------------------------------------------------------------------------


def _bauble_board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            hand=["Lightning Bolt", "Memnite"],
            battlefield=["Vexing Bauble", "Mountain"],
        )
        .player("bob", library=["Forest"])
    )


def test_vexing_bauble_counters_a_spell_cast_for_no_mana():
    """Memnite's mana cost is `{0}` (CR 202.1a's total is zero, not merely
    small), so casting it spends no mana at all - the exact condition Vexing
    Bauble asks about.
    """
    scenario = _bauble_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bauble = scenario.creature("Vexing Bauble", "alice")

    memnite = scenario.cast_onto_stack("Memnite")

    assert scenario.game.cast_record(memnite).mana_spent == {}
    assert not scenario.game.cast_record(memnite).any_mana_spent
    assert scenario.game.intervening_if_notices == []
    assert scenario.stack_names() == [
        "Memnite",
        f"{bauble.name}'s triggered ability",
    ]

    scenario.pass_until_resolved()  # Vexing Bauble's trigger counters Memnite
    assert memnite.zone is Zone.GRAVEYARD


def test_vexing_bauble_does_not_counter_a_spell_paid_with_mana():
    """The negative: real mana was spent, so the condition is false and the
    ability does not trigger at all (CR 603.4) - Lightning Bolt is never
    countered and resolves normally.
    """
    scenario = _bauble_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain")

    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, targets=[scenario.player("bob")])

    assert scenario.game.cast_record(bolt).mana_of_color_spent(Color.RED) == 1
    assert scenario.game.cast_record(bolt).any_mana_spent
    assert scenario.game.intervening_if_notices == []
    assert scenario.stack_names() == ["Lightning Bolt"]

    scenario.pass_until_resolved()
    assert bolt.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 17


# --------------------------------------------------------------------------
# Wistfulness: "if {G}{G} was spent to cast it" / "if {U}{U} was spent to cast it"
# --------------------------------------------------------------------------


def _wistfulness_board(
    battlefield: list[str], bob_battlefield: list[str] | None = None
) -> Scenario:
    return (
        Scenario()
        .player("alice", library=["Forest"], hand=["Wistfulness"], battlefield=battlefield)
        .player("bob", library=["Forest"], battlefield=bob_battlefield or [])
    )


def test_wistfulness_paid_with_double_green_triggers_only_the_green_ability():
    """{3}{G/U}{G/U} paid entirely with Forests spends five green mana - well
    past the "{G}{G}" the first ability asks for, and none of the blue the
    second one does.

    The green half is "exile target artifact or enchantment an opponent
    controls" (verified with `resolve_cards`) - a mandatory target (CR 601.2c),
    so bob needs one on the battlefield or CR 603.3d removes the triggered
    ability before it is ever placed on the stack, which would make this test
    about targeting instead of about the intervening *if* it is meant to
    cover.
    """
    scenario = _wistfulness_board(["Forest"] * 5, bob_battlefield=["Ornithopter"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*(["Forest"] * 5))

    wistfulness = scenario.cast_onto_stack("Wistfulness", *sources)

    record = scenario.game.cast_record(wistfulness)
    assert record.mana_of_color_spent(Color.GREEN) == 5
    assert record.mana_of_color_spent(Color.BLUE) == 0

    scenario.pass_until_resolved()  # Wistfulness enters the battlefield
    assert scenario.game.intervening_if_notices == []
    assert scenario.stack_names() == ["Wistfulness's triggered ability"]


def test_wistfulness_paid_with_double_blue_triggers_only_the_blue_ability():
    """The mirror: paid entirely with Islands, only the "{U}{U}" ability fires."""
    scenario = _wistfulness_board(["Island"] * 5).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*(["Island"] * 5))

    wistfulness = scenario.cast_onto_stack("Wistfulness", *sources)

    record = scenario.game.cast_record(wistfulness)
    assert record.mana_of_color_spent(Color.BLUE) == 5
    assert record.mana_of_color_spent(Color.GREEN) == 0

    scenario.pass_until_resolved()  # Wistfulness enters the battlefield
    assert scenario.game.intervening_if_notices == []
    assert scenario.stack_names() == ["Wistfulness's triggered ability"]


def _wistfulness_draw_discard_board() -> Scenario:
    """Enough library to actually draw two, unlike `_wistfulness_board`'s
    single Forest - the tests above only care whether the trigger goes on
    the stack, these care whether its effect (CR 121.2's draw, CR 701.9a's
    discard) actually happens.
    """
    return (
        Scenario()
        .player(
            "alice",
            library=["Forest", "Mountain"],
            hand=["Wistfulness", "Lightning Bolt"],
            battlefield=["Island"] * 5,
        )
        .player("bob", library=["Forest"])
    )


def test_wistfulness_paid_with_double_blue_draws_two_then_discards_one():
    """CR 121.2: two individual draws, then CR 701.9a's discard - net +1 card
    in hand (Wistfulness itself left the hand to be cast; two are drawn; one
    is discarded), and the drawn cards are the ones actually on top of the
    library, not merely a count.
    """
    scenario = _wistfulness_draw_discard_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*(["Island"] * 5))
    forest = scenario.find("Forest", Zone.LIBRARY, "alice")
    mountain = scenario.find("Mountain", Zone.LIBRARY, "alice")

    wistfulness = scenario.cast_onto_stack("Wistfulness", *sources)
    scenario.pass_until_resolved()  # Wistfulness enters the battlefield
    scenario.pass_until_resolved()  # the {U}{U} triggered ability

    alice = scenario.player("alice")
    assert wistfulness.zone is Zone.BATTLEFIELD
    assert forest.zone is Zone.HAND
    assert alice.library == []
    # Lightning Bolt was in hand from the start; Forest and Mountain were
    # both drawn (CR 121.2); exactly one of the three is now discarded
    # (CR 701.9b's unscripted default is the back of the offered hand, which
    # lands on Mountain - the most recently drawn card).
    assert mountain.zone is Zone.GRAVEYARD
    assert len(alice.hand) == 2
    assert {state.name for state in alice.hand} == {"Forest", "Lightning Bolt"}


def test_wistfulness_discard_is_a_real_choice_not_a_random_card():
    """CR 701.9b: absent an override, *the discarding player* chooses which
    card - scripted here to keep Lightning Bolt and discard Forest instead
    of the unscripted default, proving the choice is a real `CHOOSE_CARDS`
    question and not a hardcoded "discard the last card drawn".
    """
    scenario = _wistfulness_draw_discard_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*(["Island"] * 5))
    forest = scenario.find("Forest", Zone.LIBRARY, "alice")

    scenario.cast_onto_stack("Wistfulness", *sources)
    scenario.pass_until_resolved()

    scenario.will_choose_cards(forest, username="alice", source="Wistfulness")
    scenario.pass_until_resolved()  # the {U}{U} triggered ability

    alice = scenario.player("alice")
    assert forest.zone is Zone.GRAVEYARD
    assert "Lightning Bolt" in [state.name for state in alice.hand]


def test_wistfulness_paid_with_neither_color_doubled_triggers_neither_ability():
    """Pay the two hybrid symbols with one green and one blue, and the three
    generic with colorless Wastes mana: one green, one blue, neither reaching
    the two required for either ability - both conditions are false, and
    *neither* ability triggers, not "both, because the module couldn't tell".
    """
    scenario = _wistfulness_board(["Forest", "Island", "Wastes", "Wastes", "Wastes"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Island", "Wastes", "Wastes", "Wastes")

    wistfulness = scenario.cast_onto_stack("Wistfulness", *sources)

    record = scenario.game.cast_record(wistfulness)
    assert record.mana_of_color_spent(Color.GREEN) == 1
    assert record.mana_of_color_spent(Color.BLUE) == 1

    scenario.pass_until_resolved()  # Wistfulness enters the battlefield
    assert scenario.game.intervening_if_notices == []
    assert scenario.stack_names() == []


# --------------------------------------------------------------------------
# Drowner of Truth: "if {C} was spent to cast it"
# --------------------------------------------------------------------------


def _drowner_board(battlefield: list[str]) -> Scenario:
    return (
        Scenario()
        .player("alice", library=["Forest"], hand=["Drowner of Truth"], battlefield=battlefield)
        .player("bob", library=["Forest"])
    )


def test_drowner_of_truth_triggers_when_colorless_mana_paid_the_generic():
    """Drowner of Truth costs `{5}{G/U}{G/U}` - no `{C}` symbol is printed at
    all, so colorless mana can only get spent on it by choice, paying part of
    the generic {5} with a Wastes instead of a Forest or Island.
    """
    scenario = _drowner_board(
        ["Forest", "Forest", "Island", "Island", "Wastes", "Wastes", "Wastes"]
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(
        "Forest", "Forest", "Island", "Island", "Wastes", "Wastes", "Wastes"
    )

    drowner = scenario.cast_onto_stack("Drowner of Truth", *sources)

    record = scenario.game.cast_record(drowner)
    assert record.mana_of_color_spent(Color.COLORLESS) == 3
    assert scenario.game.intervening_if_notices == []
    assert scenario.stack_names() == [
        "Drowner of Truth",
        "Drowner of Truth's triggered ability",
    ]


def test_drowner_of_truth_does_not_trigger_when_no_colorless_mana_was_spent():
    """The negative: paid entirely with Forests and Islands, no colorless mana
    ever entered the payment, so the condition is false.
    """
    scenario = _drowner_board(["Forest"] * 4 + ["Island"] * 3).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(
        "Forest", "Forest", "Forest", "Forest", "Island", "Island", "Island"
    )

    drowner = scenario.cast_onto_stack("Drowner of Truth", *sources)

    record = scenario.game.cast_record(drowner)
    assert record.mana_of_color_spent(Color.COLORLESS) == 0
    assert scenario.game.intervening_if_notices == []
    assert scenario.stack_names() == ["Drowner of Truth"]
