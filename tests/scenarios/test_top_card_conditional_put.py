""" "Look at/reveal the top card of your library. If it's a <kind> card, [you
may ]put it <somewhere>. Otherwise/If you don't, put it <somewhere else>."

`_LOOK_TOP_CARD_CONDITIONAL_RE` already read Fecund Greenshell's "look at ...
you may put it ... Otherwise, put it ...". Three more printings share the
mechanic but miss the regex on wording it did not yet allow for:

- **Coiling Oracle** - "reveal" (not "look at"), no "you may" (the put is
  mandatory once the condition holds), and "put that card" (not "put it") on
  the else-arm: "reveal the top card of your library. If it's a land card,
  put it onto the battlefield. Otherwise, put that card into your hand."
- **Risen Reef** - "look at", "you may", and a differently-worded else-arm:
  "If you don't put the card onto the battlefield, put it into your hand."
  instead of a bare "Otherwise, ...".
- **Skyward Eye Prophets** - the same mandatory shape as Coiling Oracle, but
  on a `{T}:` activated ability rather than an enters trigger, and phrased
  with "it" throughout: "{T}: Reveal the top card of your library. If it's a
  land card, put it onto the battlefield. Otherwise, put it into your hand."

**Reveal versus look is a real visibility difference, not flavor text.**
CR 701.20a's reveal shows the card to all players; CR 701.20e's look shows it
only to the viewer named - here, the ability's controller. Coiling Oracle and
Skyward Eye Prophets reveal (`Game.reveal`); Risen Reef looks (`Game.look`).

CR numbers read with `mise run rules:find` in the session that wrote this
file:

- **CR 701.20a** - "To reveal a card, show that card to all players for a
  brief time... Revealing a card doesn't cause it to leave the zone it's in."
- **CR 701.20e** - "Looking at a card follows the same rules as revealing a
  card, except that the card is shown only to the specified player."
- **CR 608.2d** - a resolving effect's "you may" is answered by the player as
  the effect applies it.
- **CR 609.3** / **CR 101.3** - an effect that attempts something impossible
  does only as much as possible; an empty library leaves no top card to look
  at or reveal, so the whole instruction is ignored, not attempted.
- **CR 110.4a** - "permanent card" family; a land card is CR 305.1's own
  card type, what the `kind` group here matches.

Card text verified with `resolve_cards` in the session that wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import PlayedScenario, Scenario


def resolve_stack(scenario: PlayedScenario) -> None:
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()


# -- Coiling Oracle: reveal, mandatory, "put that card" ----------------------


def _oracle_board(library: list[str]) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Coiling Oracle"],
            battlefield=["Forest", "Island"],
            library=library,
        )
        .player("bob")
    )


def test_coiling_oracle_reveals_a_land_and_puts_it_onto_the_battlefield_untapped():
    scenario = _oracle_board(["Forest", "Lightning Bolt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.top_of_library(1, "alice")[0]

    scenario.cast_and_resolve("Coiling Oracle", *scenario.untapped_sources("Forest", "Island"))
    resolve_stack(scenario)

    assert forest.zone is Zone.BATTLEFIELD
    assert not forest.tapped, "no printed 'tapped' - CR 305.1's basic entry"
    assert [c.name for c in scenario.player("alice").library] == ["Lightning Bolt"]
    assert scenario.player("alice").hand == []


def test_coiling_oracle_reveals_a_nonland_and_puts_it_into_hand():
    scenario = _oracle_board(["Lightning Bolt", "Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.top_of_library(1, "alice")[0]

    scenario.cast_and_resolve("Coiling Oracle", *scenario.untapped_sources("Forest", "Island"))
    resolve_stack(scenario)

    assert bolt.zone is Zone.HAND
    assert [c.name for c in scenario.player("alice").library] == ["Forest"]


def test_coiling_oracle_reveals_the_top_card_to_both_players():
    """CR 701.20a: a "reveal" is shown to every player, not just the
    resolving one - the visibility difference from Risen Reef's "look"."""
    scenario = _oracle_board(["Forest", "Lightning Bolt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("Coiling Oracle", *scenario.untapped_sources("Forest", "Island"))
    resolve_stack(scenario)

    reveals = [r for r in scenario.game.reveals if r.source == "Coiling Oracle"]
    # `Reveal.viewers is None` is CR 701.20a's "show that card to all
    # players" - the contrast with Risen Reef's `viewers == ["alice"]` below.
    assert [(r.card_name, r.viewers) for r in reveals] == [("Forest", None)]


def test_coiling_oracle_with_an_empty_library_does_nothing():
    scenario = _oracle_board([]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("Coiling Oracle", *scenario.untapped_sources("Forest", "Island"))
    resolve_stack(scenario)

    assert scenario.player("alice").hand == []
    assert scenario.player("alice").library == []
    assert scenario.game.unmodeled_trigger_effect_notices == []


# -- Risen Reef: look, "you may", the "if you don't" else-arm ----------------


def _risen_reef_board(library: list[str]) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Risen Reef"],
            battlefield=["Forest", "Island", "Forest"],
            library=library,
        )
        .player("bob")
    )


def test_risen_reef_may_accepted_puts_a_land_onto_the_battlefield_tapped():
    scenario = _risen_reef_board(["Forest", "Lightning Bolt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.top_of_library(1, "alice")[0]
    scenario.will_take_the_may(True, source="Risen Reef")

    scenario.cast_and_resolve(
        "Risen Reef", *scenario.untapped_sources("Forest", "Island", "Forest")
    )
    resolve_stack(scenario)

    assert forest.zone is Zone.BATTLEFIELD
    assert forest.tapped, "the printed destination is 'onto the battlefield tapped'"
    assert scenario.player("alice").hand == []


def test_risen_reef_may_declined_puts_the_card_into_hand():
    """CR 118.12's "If you don't put the card onto the battlefield, put it
    into your hand." - a declined "you may" does not leave the card on top of
    the library the way Fecund Greenshell's bare "Otherwise" does; Risen
    Reef's else-arm fires on the decline itself."""
    scenario = _risen_reef_board(["Forest", "Lightning Bolt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.top_of_library(1, "alice")[0]
    scenario.will_take_the_may(False, source="Risen Reef")

    scenario.cast_and_resolve(
        "Risen Reef", *scenario.untapped_sources("Forest", "Island", "Forest")
    )
    resolve_stack(scenario)

    assert forest.zone is Zone.HAND
    assert [c.name for c in scenario.player("alice").library] == ["Lightning Bolt"]


def test_risen_reef_a_nonland_top_card_goes_to_hand_with_no_question_asked():
    scenario = _risen_reef_board(["Lightning Bolt", "Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.top_of_library(1, "alice")[0]

    scenario.cast_and_resolve(
        "Risen Reef", *scenario.untapped_sources("Forest", "Island", "Forest")
    )
    resolve_stack(scenario)

    assert bolt.zone is Zone.HAND
    assert [
        decision for decision in scenario.questions_asked() if decision.source == "Risen Reef"
    ] == []


def test_risen_reef_looks_at_the_top_card_known_only_to_its_controller():
    """CR 701.20e: a "look" shows the card only to the named player - here
    Risen Reef's controller - never to the opponent, unlike Coiling Oracle's
    reveal."""
    scenario = _risen_reef_board(["Forest", "Lightning Bolt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(True, source="Risen Reef")

    scenario.cast_and_resolve(
        "Risen Reef", *scenario.untapped_sources("Forest", "Island", "Forest")
    )
    resolve_stack(scenario)

    reveals = [r for r in scenario.game.reveals if r.source == "Risen Reef"]
    assert [(r.card_name, r.viewers) for r in reveals] == [("Forest", ["alice"])]
    assert scenario.game.known_to("bob") == []


def test_risen_reef_with_an_empty_library_does_nothing():
    scenario = _risen_reef_board([]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve(
        "Risen Reef", *scenario.untapped_sources("Forest", "Island", "Forest")
    )
    resolve_stack(scenario)

    assert scenario.player("alice").hand == []
    assert scenario.game.unmodeled_trigger_effect_notices == []


# -- Skyward Eye Prophets: activated ability, mandatory, "it" throughout -----


def _prophets_board(library: list[str]) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Skyward Eye Prophets", "Forest"],
            library=library,
        )
        .player("bob")
        .build()
    )


def test_skyward_eye_prophets_taps_to_put_a_land_onto_the_battlefield_untapped():
    scenario = _prophets_board(["Forest", "Lightning Bolt"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.top_of_library(1, "alice")[0]
    prophets = scenario.creature("Skyward Eye Prophets", "alice")

    scenario.activate(prophets)
    resolve_stack(scenario)

    assert forest.zone is Zone.BATTLEFIELD
    assert not forest.tapped
    assert [c.name for c in scenario.player("alice").library] == ["Lightning Bolt"]


def test_skyward_eye_prophets_taps_to_put_a_nonland_into_hand():
    scenario = _prophets_board(["Lightning Bolt", "Forest"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.top_of_library(1, "alice")[0]
    prophets = scenario.creature("Skyward Eye Prophets", "alice")

    scenario.activate(prophets)
    resolve_stack(scenario)

    assert bolt.zone is Zone.HAND
    assert [c.name for c in scenario.player("alice").library] == ["Forest"]


def test_skyward_eye_prophets_reveals_the_top_card_to_both_players():
    scenario = _prophets_board(["Forest", "Lightning Bolt"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    prophets = scenario.creature("Skyward Eye Prophets", "alice")

    scenario.activate(prophets)
    resolve_stack(scenario)

    reveals = [r for r in scenario.game.reveals if r.source == "Skyward Eye Prophets"]
    assert [(r.card_name, r.viewers) for r in reveals] == [("Forest", None)]


def test_skyward_eye_prophets_with_an_empty_library_does_nothing():
    scenario = _prophets_board([])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    prophets = scenario.creature("Skyward Eye Prophets", "alice")

    scenario.activate(prophets)
    resolve_stack(scenario)

    assert scenario.player("alice").hand == []
    assert scenario.player("alice").library == []
