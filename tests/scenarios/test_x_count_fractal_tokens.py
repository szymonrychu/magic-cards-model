"""Scenario: X-count Fractal tokens - "Create a 0/0 green and blue Fractal
creature token[s]. Put X +1/+1 counters on it/each of them, where X is
`<count>`", for the two counts the Secrets of Strixhaven pool prints that a
fixed number or `machines/effects.amount_expression`'s existing terms could
not already read:

- Fractal Anomaly: "where X is the number of cards you've drawn this turn" -
  EC4's own running per-player total (`Game.cards_drawn_this_turn`), the same
  fact `machines/conditions/history._drew` already reads as a boolean,
  reused here as a count (`count_expression`'s own new term).
- Emil, Vastlands Roamer: "where X is the number of differently named lands
  you control" - a new, generalised `count_expression` term (any card-type
  or subtype qualifier, not fixed to lands), read through the new "Put X
  `<kind>` counters on it, where X is `<expr>`" rider
  (`_RIDER_PUT_VARIABLE_COUNTERS_RE`) that `_parse_token_then_object_
  anaphor_clause_pair` already threads any two-sentence "Create ... token.
  <rider>." pair through.

Body of Research is this file's proof printing: the same two-sentence
"Create a token. Put X counters on it, where X is `<expr>`." shape as
Emil's own activated ability, with a third, genuinely different count -
"the number of cards in your library" - that `count_expression` already read
before this task (Tamiyo, Seasoned Scholar's own -7 uses it), proving the new
rider generalises to whatever count `count_expression` knows rather than
being fitted to either of the two named cards.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 121.2** - drawing a card, the event `Game.cards_drawn_this_turn`
  counts.
- **CR 201.4a** - "differently named" compares an object's copiable name.
- **CR 107.1b** - a negative or undefined calculation result is zero.
- **CR 701.7a** - creating a token puts a new object onto the battlefield.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def _to_main(scenario: Scenario) -> None:
    scenario.start_at(Step.PRECOMBAT_MAIN)


def _fractals(scenario: Scenario) -> list:
    return [state for state in scenario.game.battlefield if state.name == "Fractal Token"]


# ---------------------------------------------------------------------------
# Fractal Anomaly - "Create a 0/0 green and blue Fractal creature token and
# put X +1/+1 counters on it, where X is the number of cards you've drawn
# this turn."
# ---------------------------------------------------------------------------


def test_fractal_anomaly_sizes_the_token_by_cards_drawn_this_turn():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Fractal Anomaly", "Divination"],
            battlefield=["Island", "Island", "Island", "Island"],
            library=["Mountain"] * 10,
        )
        .build()
    )
    _to_main(scenario)
    draw_sources = scenario.untapped_sources("Island", "Island", "Island")
    scenario.cast_and_resolve("Divination", *draw_sources)  # +2 cards drawn this turn
    (source,) = scenario.untapped_sources("Island")
    scenario.cast_and_resolve("Fractal Anomaly", source)

    (token,) = _fractals(scenario)
    assert token.counters["+1/+1"] == 2
    assert scenario.game.characteristics_of(token).power == 2
    assert scenario.game.characteristics_of(token).toughness == 2


def test_fractal_anomaly_makes_a_zero_zero_token_with_no_draws_yet():
    """CR 107.1b: with nothing drawn yet this turn, X is zero - the token is
    still created (CR 701.7a puts a 0/0 object onto the battlefield), and
    then immediately dies to the 704.5f state-based action."""
    scenario = Scenario().player("alice", hand=["Fractal Anomaly"], battlefield=["Island"]).build()
    _to_main(scenario)
    (source,) = scenario.untapped_sources("Island")
    scenario.cast_and_resolve("Fractal Anomaly", source)

    assert _fractals(scenario) == []
    graveyard_names = [card.name for card in scenario.player("alice").graveyard]
    assert "Fractal Token" not in graveyard_names  # a token ceases to exist, CR 111.7


# ---------------------------------------------------------------------------
# Emil, Vastlands Roamer - "{4}{G}, {T}: Create a 0/0 green and blue Fractal
# creature token. Put X +1/+1 counters on it, where X is the number of
# differently named lands you control."
# ---------------------------------------------------------------------------


def test_emil_sizes_the_token_by_differently_named_lands():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Emil, Vastlands Roamer",
                "Mountain",
                "Island",
                "Plains",
                "Forest",
                "Forest",
            ],
        )
        .build()
    )
    _to_main(scenario)
    sources = scenario.untapped_sources("Mountain", "Island", "Plains", "Forest", "Forest")
    emil = scenario.find("Emil, Vastlands Roamer", Zone.BATTLEFIELD)
    scenario.activate(emil, *sources)
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()

    (token,) = _fractals(scenario)
    # Four differently named lands: Mountain, Island, Plains, Forest - the
    # second Forest does not add a fifth name (CR 201.4a).
    assert token.counters["+1/+1"] == 4


def test_emil_does_not_count_duplicate_land_names_twice():
    """Four copies of the same land name count once, not four times - the
    differently-named count is over names (CR 201.4a), not over lands."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Emil, Vastlands Roamer",
                "Mountain",
                "Mountain",
                "Mountain",
                "Mountain",
                "Forest",
            ],
        )
        .build()
    )
    _to_main(scenario)
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain", "Forest")
    emil = scenario.find("Emil, Vastlands Roamer", Zone.BATTLEFIELD)
    scenario.activate(emil, *sources)
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()

    (token,) = _fractals(scenario)
    # Two distinct names (Mountain, Forest) despite five lands on the board.
    assert token.counters["+1/+1"] == 2


# ---------------------------------------------------------------------------
# Body of Research - proof printing for the "Create a token. Put X counters
# on it, where X is `<expr>`." rider, with a third, pre-existing count:
# "Put X +1/+1 counters on it, where X is the number of cards in your
# library."
# ---------------------------------------------------------------------------


def test_body_of_research_sizes_the_token_by_cards_in_library():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Body of Research"],
            battlefield=["Forest", "Forest", "Forest", "Island", "Island", "Island"],
            library=["Mountain"] * 7,
        )
        .build()
    )
    _to_main(scenario)
    assert len(scenario.player("alice").library) == 7
    sources = scenario.untapped_sources("Forest", "Forest", "Forest", "Island", "Island", "Island")
    scenario.cast_and_resolve("Body of Research", *sources)

    (token,) = _fractals(scenario)
    assert token.counters["+1/+1"] == 7
