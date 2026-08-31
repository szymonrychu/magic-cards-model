"""CR 118.12a's "unless", read onto a discard: Winternight Stories.

"Draw three cards. Then discard two cards unless you discard a creature card."

CR 118.12a spells out what "unless" means: "[Do something] unless [a player
does something else]" is shorthand for "[a player] may [do something else]. If
[that player] doesn't, [effect]." So the smaller discard is the *option* and
the larger one is what happens when it is declined - which is why the engine
asks a plain "you may" (CR 608.2d) before falling through.

CR 701.9a is the discard itself ("move it from its owner's hand to that
player's graveyard") and CR 701.9b is why the player picks which card: "By
default, effects that cause a player to discard a card allow the affected
player to choose which card to discard."

The whole sentence is read as one instruction (CR 608.2c: the controller
"follows its instructions in the order written"), so the draw happens first
and a card drawn by this very spell is a legal thing to discard to it.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def board(library: list[str], hand: list[str] | None = None) -> Scenario:
    """Alice with Winternight Stories in hand and three Islands to cast it."""
    return (
        Scenario()
        .player(
            "alice",
            library=library,
            hand=["Winternight Stories", *(hand or [])],
            battlefield=["Island", "Island", "Island"],
        )
        .player("bob", library=["Forest", "Forest"])
    )


def cast_it(scenario):
    islands = scenario.untapped_sources("Island", "Island", "Island")
    return scenario.cast_and_resolve("Winternight Stories", *islands)


def test_discarding_a_creature_card_is_the_whole_price():
    """The happy path: taking CR 118.12a's option discards exactly one card,
    the creature, and never the two the sentence otherwise demands."""
    scenario = board(["Grizzly Bears", "Island", "Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bears = scenario.find("Grizzly Bears", Zone.LIBRARY, "alice")

    scenario.will_take_the_may(True, source="Winternight Stories")
    scenario.will_choose_cards(bears, source="Winternight Stories")
    cast_it(scenario)

    assert bears.zone is Zone.GRAVEYARD
    assert [state.name for state in alice.graveyard] == [
        "Grizzly Bears",
        "Winternight Stories",
    ]
    # Three drawn, one discarded: the two Islands are still in hand.
    assert sorted(state.name for state in alice.hand) == ["Island", "Island"]


def test_declining_the_option_discards_two_cards_instead():
    """CR 118.12a's other half: "If [that player] doesn't, [effect]" - the
    plain two-card discard runs when the option is refused."""
    scenario = board(["Grizzly Bears", "Island", "Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")

    scenario.will_take_the_may(False, source="Winternight Stories")
    cast_it(scenario)

    assert len(alice.hand) == 1
    binned = [state.name for state in alice.graveyard if state.name != "Winternight Stories"]
    assert len(binned) == 2


def test_a_hand_with_no_creature_card_is_never_offered_the_option():
    """CR 608.2d: "the player can't choose an option that's illegal or
    impossible." With no creature card in hand there is nothing to discard
    for the option, so the question is not put at all - the two-card discard
    simply happens."""
    scenario = board(["Island", "Island", "Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")

    cast_it(scenario)

    assert not [
        decision
        for decision in scenario.questions_asked()
        if decision.source == "Winternight Stories" and decision.kind.value == "may"
    ]
    assert len(alice.hand) == 1


def test_a_creature_drawn_by_this_very_spell_can_pay_the_option():
    """CR 608.2c's "in the order written": the draw is the first instruction,
    so the three cards it finds are in hand by the time the discard asks."""
    scenario = board(["Island", "Island", "Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bears = scenario.find("Grizzly Bears", Zone.LIBRARY, "alice")

    scenario.will_take_the_may(True, source="Winternight Stories")
    scenario.will_choose_cards(bears, source="Winternight Stories")
    cast_it(scenario)

    assert bears.zone is Zone.GRAVEYARD
    assert len(alice.hand) == 2


def test_an_artifact_creature_counts_as_a_creature_card():
    """CR 205.2a's card types are a set, not a choice - an artifact creature
    card is a creature card, so Memnite is a legal answer to the option."""
    scenario = board(["Memnite", "Island", "Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    memnite = scenario.find("Memnite", Zone.LIBRARY, "alice")

    scenario.will_take_the_may(True, source="Winternight Stories")
    scenario.will_choose_cards(memnite, source="Winternight Stories")
    cast_it(scenario)

    assert memnite.zone is Zone.GRAVEYARD
    assert len(scenario.player("alice").hand) == 2


def test_the_option_only_ever_costs_one_card_even_with_two_creatures_in_hand():
    """ "Unless you discard **a** creature card" is singular. Holding two does
    not make the option cost two."""
    scenario = board(["Grizzly Bears", "Memnite", "Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bears = scenario.find("Grizzly Bears", Zone.LIBRARY, "alice")

    scenario.will_take_the_may(True, source="Winternight Stories")
    scenario.will_choose_cards(bears, source="Winternight Stories")
    cast_it(scenario)

    assert bears.zone is Zone.GRAVEYARD
    assert sorted(state.name for state in alice.hand) == ["Island", "Memnite"]


def test_a_short_hand_discards_everything_it_has_and_no_more():
    """A hand smaller than the two cards demanded is not a rules violation:
    the player discards what they have. The library here holds one card, so
    the draw finds one and the hand is a single card when the discard runs."""
    scenario = board(["Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")

    scenario.will_take_the_may(False, source="Winternight Stories")
    cast_it(scenario)

    assert alice.hand == []
    assert sorted(state.name for state in alice.graveyard) == [
        "Island",
        "Winternight Stories",
    ]


def test_the_harmonize_line_is_not_part_of_what_the_spell_does():
    """Winternight Stories prints "Harmonize {4}{U}" above its effect. That is
    a way to *cast* the card from a graveyard, not an instruction the spell
    follows on resolution, so it neither runs nor stops the rest of the
    paragraph from running (CR 608.2c has no notion of half an effect - a
    line the resolver could not read would take the whole thing down)."""
    scenario = board(["Grizzly Bears", "Island", "Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    before = len(alice.library)

    scenario.will_take_the_may(False, source="Winternight Stories")
    spell = cast_it(scenario)

    assert spell.zone is Zone.GRAVEYARD
    assert len(alice.library) == before - 3


@pytest.mark.parametrize("taken", [True, False])
def test_the_spell_itself_always_reaches_the_graveyard(taken: bool):
    """Whichever branch of the "unless" runs, the sorcery finishes resolving
    and is put into its owner's graveyard."""
    scenario = board(["Grizzly Bears", "Island", "Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.LIBRARY, "alice")

    scenario.will_take_the_may(taken, source="Winternight Stories")
    if taken:
        scenario.will_choose_cards(bears, source="Winternight Stories")
    spell = cast_it(scenario)

    assert spell.zone is Zone.GRAVEYARD
