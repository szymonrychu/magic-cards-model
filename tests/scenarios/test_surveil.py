"""Scenario: surveil, and where the cards it moves actually go (CR 701.25).

Surveil is scry's twin with a different destination, and the difference is the
whole reason it gets its own file: a card put on the bottom of a library is
still in the library, while a card put into a graveyard has *changed zones*. That
makes every zone-change rule apply to it - a replacement effect watching the
graveyard (CR 614.1), the object becoming new (CR 400.7) - and none of them apply
to a scry.

Every CR number below was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file, and the full text of each
read out of the `2026-08-19` Comprehensive Rules release named by
`knowledge_search(type="cr_versions")` and verified against its published sha256.

- **CR 701.25a** - "To 'surveil N' means to look at the top N cards of your
  library, then put any number of them into your graveyard and the rest on top
  of your library in any order."
- **CR 701.25b** - additional cards an effect lets you look at join the same
  pool. No card in the pool does this.
- **CR 701.25c** - "If a player is instructed to surveil 0, no surveil event
  occurs."
- **CR 701.25d** - a "whenever a player surveils" trigger fires after the whole
  process. Nothing emits a surveil event yet.
- **CR 400.7** - an object that changes zones becomes a new object, which is why
  the surveilled card is looked up in the graveyard rather than trusted to be
  the same state.
- **CR 614.1** - a replacement effect gets its say on the move to the graveyard,
  which is what Rest in Peace proves here.

Dragon's Rage Channeler, Elegant Parlor and Thundering Falls are the pool's real
surveil cards. Most of this file drives `Game.surveil` directly, so one rule is
tested at a time; the section at the bottom runs it through their triggered
abilities, which have `machines/effects.py` entries now.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _library(*names: str, battlefield: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", library=list(names), battlefield=battlefield or [])
    )


def _library_names(scenario) -> list[str]:
    return [state.card.name for state in scenario.player("alice").library]


def _graveyard_names(scenario) -> list[str]:
    return [state.card.name for state in scenario.player("alice").graveyard]


def test_surveil_one_can_leave_the_card_on_top():
    """CR 701.25a: "put any number of them into your graveyard" includes none.

    Which is also the documented default when nobody answers - see
    `machines/decisions.py`.
    """
    scenario = _library("Island", "Mountain").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.surveil_keeping_everything_on_top()

    scenario.game.surveil("alice", 1, source="Dragon's Rage Channeler")

    assert _library_names(scenario) == ["Island", "Mountain"]
    assert _graveyard_names(scenario) == []


def test_the_surveil_question_names_cr_701_25a_s_own_two_destinations():
    """CR 701.25a: "put any number of them into your graveyard and the rest on
    top of your library".

    The graveyard, not a scry's bottom - the whole difference between the two
    keywords, said in the question itself so a client rendering it does not
    have to infer the destination from the kind. `Game.look_at_top_and_split`
    asks the same shape for cards with a third pair of destinations entirely,
    which is why one shared label would be wrong.
    """
    scenario = _library("Island", "Mountain", "Forest").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.surveil_keeping_everything_on_top()

    scenario.game.surveil("alice", 2, source="Dragon's Rage Channeler")

    (asked,) = scenario.questions_asked()
    assert asked.moved_label == "your graveyard"
    assert asked.kept_label == "top of your library"


def test_a_surveilled_card_is_in_the_graveyard_not_the_bottom_of_the_library():
    """The one difference from a scry, and the reason for this file.

    CR 701.25a sends the card to the graveyard. CR 400.7's "an object that moves
    from one zone to another becomes a new object" is why the assertion is on
    the graveyard's contents rather than on the state object's identity.
    """
    scenario = _library("Island", "Mountain", "Forest").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (island,) = scenario.top_of_library(1)
    scenario.surveil_to_graveyard(island)

    scenario.game.surveil("alice", 1, source="Dragon's Rage Channeler")

    assert _graveyard_names(scenario) == ["Island"]
    assert _library_names(scenario) == ["Mountain", "Forest"]
    assert island.zone is Zone.GRAVEYARD


def test_surveil_two_can_bin_one_and_reorder_the_other_onto_the_top():
    """CR 701.25a, both halves of the sentence in one answer.

    "Any number of them into your graveyard *and the rest on top of your library
    in any order*" - the kept cards are reorderable exactly as in a scry, so a
    surveil 2 that bins one card still gets to choose what the other sits above.
    """
    scenario = _library("Island", "Mountain", "Forest").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (island, mountain) = scenario.top_of_library(2)
    scenario.surveil_to_graveyard(mountain, top_order=[island])

    scenario.game.surveil("alice", 2, source="Dragon's Rage Channeler")

    assert _graveyard_names(scenario) == ["Mountain"]
    assert _library_names(scenario) == ["Island", "Forest"]


def test_both_cards_can_be_binned():
    """CR 701.25a: "any number" reaches all of them.

    They arrive in the graveyard in the order they were named, because CR 608.2f
    leaves the relative order of actions on several objects to the player
    controlling the effect.
    """
    scenario = _library("Island", "Mountain", "Forest").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (island, mountain) = scenario.top_of_library(2)
    scenario.surveil_to_graveyard(mountain, island)

    scenario.game.surveil("alice", 2, source="Dragon's Rage Channeler")

    assert _graveyard_names(scenario) == ["Mountain", "Island"]
    assert _library_names(scenario) == ["Forest"]


def test_surveil_zero_is_not_a_surveil_at_all():
    """CR 701.25c, the exact mirror of CR 701.22b.

    Asserted the only way it is observable: no question was put to the player,
    so there is no surveil event for CR 701.25d's trigger to watch.
    """
    scenario = _library("Island").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.game.surveil("alice", 0, source="Elegant Parlor")

    assert scenario.questions_asked() == []
    assert _library_names(scenario) == ["Island"]


def test_a_card_surveilled_under_rest_in_peace_is_exiled_instead():
    """CR 614.1: a move to the graveyard is a replaceable event, wherever it began.

    Rest in Peace reads "If a card or token would be put into a graveyard from
    anywhere, exile it instead", and "from anywhere" includes from the top of a
    library during a surveil. This is the case that proves surveil goes through
    the real zone-change machinery rather than appending to a list.
    """
    scenario = _library("Island", "Mountain", battlefield=["Rest in Peace"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (island,) = scenario.top_of_library(1)
    scenario.surveil_to_graveyard(island)

    scenario.game.surveil("alice", 1, source="Dragon's Rage Channeler")

    assert _graveyard_names(scenario) == []
    assert island.zone is Zone.EXILE
    assert _library_names(scenario) == ["Mountain"]


def test_surveilling_an_empty_library_asks_and_does_nothing():
    """CR 701.25c exempts surveil 0 only, so surveil 1 with no cards still asks.

    A surveil is not a draw, so CR 704.5b never comes into it and nobody loses.
    """
    scenario = _library().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.game.surveil("alice", 1, source="Elegant Parlor")

    assert len(scenario.questions_asked()) == 1
    assert _graveyard_names(scenario) == []
    assert scenario.game.winner is None


# -- through a real card ---------------------------------------------------
#
# "When this land enters, surveil 1" (Elegant Parlor, Thundering Falls) and
# "Whenever you cast a noncreature spell, surveil 1" (Dragon's Rage Channeler).


def test_a_surveil_land_entering_surveils_one():
    """CR 603.6a's enters-the-battlefield trigger, whose whole effect is
    CR 701.25a's surveil.

    The land also enters tapped, which is a separate replacement effect
    (CR 614.1c) and happens as it enters rather than when the trigger resolves -
    so the surveil is still waiting on the stack while the land is already there
    and already tapped.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", library=["Forest", "Island"], hand=["Elegant Parlor"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (forest,) = scenario.top_of_library(1)
    scenario.surveil_to_graveyard(forest)

    parlor = scenario.play_land("Elegant Parlor", "alice")
    assert parlor.tapped, "CR 614.1c applied as it entered"
    scenario.game.put_triggers_on_stack()  # CR 603.3
    scenario.resolve_top()

    assert [state.card.name for state in scenario.player("alice").graveyard] == ["Forest"]
    assert _library_names(scenario) == ["Island"]


def test_the_surveil_land_can_be_told_to_keep_the_card():
    """CR 701.25a: "put **any number** of them into your graveyard" - and none is
    a number, which is also the engine's default.

    Thundering Falls is Elegant Parlor's ability on a different pair of land
    types; both are the same trigger, and both have their own registry entry
    rather than one shared one.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", library=["Forest", "Island"], hand=["Thundering Falls"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.surveil_keeping_everything_on_top()

    scenario.play_land("Thundering Falls", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert scenario.player("alice").graveyard == []
    assert _library_names(scenario) == ["Forest", "Island"]


def test_dragons_rage_channeler_surveils_on_a_noncreature_spell():
    """ "Whenever you cast a noncreature spell, surveil 1."

    CR 601.2 is the trigger event - casting, not resolving - so the surveil
    trigger is put on the stack *above* the spell that caused it (CR 603.3) and
    resolves first.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            library=["Forest", "Island"],
            hand=["Lightning Bolt"],
            battlefield=["Dragon's Rage Channeler", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (forest,) = scenario.top_of_library(1)
    scenario.surveil_to_graveyard(forest)

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_onto_stack("Lightning Bolt", mountain, username="alice", targets=["bob"])

    assert scenario.stack_names()[-1].endswith("triggered ability")
    scenario.resolve_top()

    assert [state.card.name for state in scenario.player("alice").graveyard] == ["Forest"]


def test_dragons_rage_channeler_does_not_surveil_on_a_creature_spell():
    """ "a **noncreature** spell" (CR 109.2b's negated card type).

    The trigger does not fire at all, which is a different thing from firing and
    surveilling nothing - and the only way to tell them apart is that no question
    was asked (CR 608.2d).
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            library=["Forest", "Island"],
            hand=["Grizzly Bears"],
            battlefield=["Dragon's Rage Channeler", "Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    sources = scenario.untapped_sources("Forest", "Forest", username="alice")
    scenario.cast_and_resolve("Grizzly Bears", *sources, username="alice")

    assert scenario.questions_asked() == []
    assert scenario.player("alice").graveyard == []
