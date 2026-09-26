"""Scenario: "... if this spell was cast from anywhere other than your hand,
..." (CR 601.2a's origin zone), on Antiquities on the Loose and its own
Flashback (CR 702.34a). `CastRecord.origin_zone` already carries this fact -
Ral, Monsoon Mage's own Flashback-adjacent rebound reads the identical field
the opposite way ("cast from your hand") - so this rider is a new reader of
an existing record, not a new cast-zone tracking subsystem.

Otterball Antics is this file's proof printing: the identical rider template,
worded the *other* way a card in the pool prints it - "put a +1/+1 counter on
**that creature**" (the just-created token itself) rather than Antiquities'
own "put a +1/+1 counter on **each `<subtype>` you control**" (every matching
permanent on the board) - proving the reader generalises to both shapes
rather than being fitted to Antiquities' own plural wording.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 601.2a** - casting a spell moves it from wherever it was to the
  stack; that origin zone is what this rider compares against "your hand".
- **CR 702.34a** - Flashback: "You may cast this card from your graveyard
  ... Then exile this card instead of putting it anywhere else any time it
  would leave the stack."
- **CR 111.7** - a token that leaves the battlefield ceases to exist as a
  state-based action, so it is never found in a graveyard afterwards.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def _to_main(scenario: Scenario) -> None:
    scenario.start_at(Step.PRECOMBAT_MAIN)


def _flashback(scenario: Scenario, name: str, *sources):
    casting = scenario.cast(name, from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Flashback")
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)
    return scenario.resolve_top()


# ---------------------------------------------------------------------------
# Antiquities on the Loose - "Create two 2/2 red and white Spirit creature
# tokens. Then if this spell was cast from anywhere other than your hand,
# put a +1/+1 counter on each Spirit you control." Flashback {4}{W}{W}.
# ---------------------------------------------------------------------------


def test_antiquities_on_the_loose_grants_no_counters_cast_from_hand():
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Antiquities on the Loose"], battlefield=["Plains", "Plains", "Plains"]
        )
        .build()
    )
    _to_main(scenario)
    sources = scenario.untapped_sources("Plains", "Plains", "Plains")
    scenario.cast_and_resolve("Antiquities on the Loose", *sources)

    spirits = [state for state in scenario.game.battlefield if state.name == "Spirit Token"]
    assert len(spirits) == 2
    for spirit in spirits:
        assert spirit.counters["+1/+1"] == 0


def test_antiquities_on_the_loose_grants_counters_when_flashed_back():
    scenario = (
        Scenario()
        .player(
            "alice",
            graveyard=["Antiquities on the Loose"],
            battlefield=["Plains"] * 6,
        )
        .build()
    )
    _to_main(scenario)
    sources = scenario.untapped_sources(*(["Plains"] * 6))
    _flashback(scenario, "Antiquities on the Loose", *sources)

    spirits = [state for state in scenario.game.battlefield if state.name == "Spirit Token"]
    assert len(spirits) == 2
    for spirit in spirits:
        assert spirit.counters["+1/+1"] == 1

    # CR 702.34a: flashback exiles the card instead of putting it in the
    # graveyard when it would next leave the stack.
    assert scenario.player("alice").graveyard == []
    assert any(card.name == "Antiquities on the Loose" for card in scenario.game.exile)


def test_antiquities_on_the_loose_counts_a_spirit_already_on_the_board():
    """ "Each Spirit you control" is every matching permanent, not only the
    two tokens this resolution just created: cast once from hand (no
    counters), then flash it back from the graveyard it left - the second
    resolution's counter goes on all four Spirits now on the board, the two
    already-uncountered ones included."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Antiquities on the Loose"],
            battlefield=["Plains"] * 9,
        )
        .build()
    )
    _to_main(scenario)
    first_sources = scenario.untapped_sources("Plains", "Plains", "Plains")
    scenario.cast_and_resolve("Antiquities on the Loose", *first_sources)
    early_spirits = [state for state in scenario.game.battlefield if state.name == "Spirit Token"]
    assert len(early_spirits) == 2
    assert all(spirit.counters["+1/+1"] == 0 for spirit in early_spirits)

    remaining_sources = scenario.untapped_sources(*(["Plains"] * 6))
    _flashback(scenario, "Antiquities on the Loose", *remaining_sources)

    spirits = [state for state in scenario.game.battlefield if state.name == "Spirit Token"]
    assert len(spirits) == 4
    assert all(spirit.counters["+1/+1"] == 1 for spirit in spirits)


# ---------------------------------------------------------------------------
# Otterball Antics - proof printing, the "on that creature" shape: "Create a
# 1/1 blue and red Otter creature token with prowess. If this spell was cast
# from anywhere other than your hand, put a +1/+1 counter on that creature."
# Flashback {3}{U}.
# ---------------------------------------------------------------------------


def test_otterball_antics_grants_no_counter_cast_from_hand():
    scenario = (
        Scenario()
        .player("alice", hand=["Otterball Antics"], battlefield=["Island", "Island"])
        .build()
    )
    _to_main(scenario)
    sources = scenario.untapped_sources("Island", "Island")
    scenario.cast_and_resolve("Otterball Antics", *sources)

    (otter,) = [state for state in scenario.game.battlefield if state.name == "Otter Token"]
    assert otter.counters["+1/+1"] == 0


def test_otterball_antics_grants_a_counter_on_that_creature_when_flashed_back():
    scenario = (
        Scenario()
        .player("alice", graveyard=["Otterball Antics"], battlefield=["Island"] * 4)
        .build()
    )
    _to_main(scenario)
    sources = scenario.untapped_sources(*(["Island"] * 4))
    _flashback(scenario, "Otterball Antics", *sources)

    (otter,) = [state for state in scenario.game.battlefield if state.name == "Otter Token"]
    assert otter.counters["+1/+1"] == 1
