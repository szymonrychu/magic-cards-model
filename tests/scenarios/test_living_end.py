"""Living End's own resolution effect: a per-player exile/sacrifice/return.

Card text: "Suspend 3—{2}{B}{B}\\nEach player exiles all creature cards from
their graveyard, then sacrifices all creatures they control, then puts all
cards they exiled this way onto the battlefield." Suspend is CR 702.62a's
three abilities, none of them the spell's own resolution instruction; what
this file is about is the sentence after it.

Before this wave, that sentence parsed as nothing at all: `_CLAUSE_SEPARATOR`
in `machines/effects.py` cuts on every ", then " the way CR 608.2c's own
clause split does, so "exiles ... graveyard", "sacrifices ... control" and
"puts ... battlefield" came back as three separate fragments, none of which
matched a known clause shape - and the *whole* sentence was silently dropped,
which is what `fail_closed` warns is the worst outcome available: a resolved
Living End that touched nothing looked exactly like a legal, empty-of-effect
sorcery, not a mistake. `machines/effects._spell_effect_or_notice` now checks
the sentence whole, ahead of the ordinary per-clause split, and
`each_player_exiles_sacrifices_and_returns_creatures` performs it:

- **CR 701.13a / 406.2** - exile, off any zone (`Game.exile_permanent` does
  not care which one a card is coming from).
- **CR 701.21a** - sacrifice, off the battlefield only.
- **CR 400.7, 110.2a** - a card returns as a new permanent, not the graveyard
  card come back to life; `Game.put_onto_battlefield` is the Tooth and Nail
  path this effect reuses.

The Suspend line itself getting out of the way is `_strip_keyword_ability_lines` in
`machines/effects.py` - general to the keyword's own "Suspend N—[cost]" shape
(CR 702.62a), not to this one card, since any suspended card whose resolution
also does something would have hit the identical bug.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import cascade
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_reanimates_creatures_from_the_graveyard_for_both_players():
    """The core loop: each player's own graveyard creatures come back, each
    player's own battlefield creatures die on the way."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Living End"],
            graveyard=["Grizzly Bears"],
            battlefield=["Kitchen Finks"],
        )
        .player("bob", graveyard=["Colossal Dreadmaw"], battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    living_end = scenario.find("Living End", Zone.HAND)
    scenario.game.put_on_stack(living_end, "alice")
    living_end.targets = []

    scenario.resolve_top()

    battlefield_by_owner = {(state.name, state.controller) for state in scenario.game.battlefield}
    assert battlefield_by_owner == {("Grizzly Bears", "alice"), ("Colossal Dreadmaw", "bob")}
    # Kitchen Finks was sacrificed and stayed in the graveyard; Living End
    # itself lands there too once it finishes resolving (CR 608.2n).
    assert sorted(state.name for state in scenario.player("alice").cards_in(Zone.GRAVEYARD)) == [
        "Kitchen Finks",
        "Living End",
    ]
    assert [state.name for state in scenario.player("bob").cards_in(Zone.GRAVEYARD)] == [
        "Grizzly Bears"
    ]
    assert living_end.zone is Zone.GRAVEYARD


def test_noncreature_cards_in_the_graveyard_are_left_alone():
    """ "creature cards" - Lightning Bolt in the graveyard is not exiled,
    sacrificed, or returned; it is simply not this effect's business."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Living End"],
            graveyard=["Grizzly Bears", "Lightning Bolt"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    living_end = scenario.find("Living End", Zone.HAND)
    scenario.game.put_on_stack(living_end, "alice")
    living_end.targets = []

    scenario.resolve_top()

    assert [state.name for state in scenario.game.battlefield] == ["Grizzly Bears"]
    assert sorted(state.name for state in scenario.player("alice").cards_in(Zone.GRAVEYARD)) == [
        "Lightning Bolt",
        "Living End",
    ]


def test_battlefield_creatures_still_die_with_an_empty_graveyard():
    """Sacrificing "all creatures they control" does not wait on the exile
    step finding anything - a player with nothing in the graveyard still
    loses their board, and gets nothing back for it."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Living End"], battlefield=["Kitchen Finks"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    living_end = scenario.find("Living End", Zone.HAND)
    scenario.game.put_on_stack(living_end, "alice")
    living_end.targets = []

    scenario.resolve_top()

    assert scenario.game.battlefield == []
    assert [state.name for state in scenario.player("alice").cards_in(Zone.GRAVEYARD)] == [
        "Kitchen Finks",
        "Living End",
    ]


def test_nothing_to_exile_and_nothing_to_sacrifice_does_not_crash():
    """A player with an empty graveyard and no creatures is simply skipped."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Living End"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    living_end = scenario.find("Living End", Zone.HAND)
    scenario.game.put_on_stack(living_end, "alice")
    living_end.targets = []

    scenario.resolve_top()

    assert scenario.game.battlefield == []


def test_cascading_into_living_end_actually_reanimates():
    """Living End can never be hardcast - it has no mana cost - so the only
    way this deck's finisher happens at all is Shardless Agent's cascade
    (CR 702.85a) hitting it and it being cast "without paying its mana cost"
    for the {0} that is all it has.

    This is the wave's whole point proven end to end: cascade exiles down to
    Living End, the free cast puts it on the stack the same manual way
    `test_cascade.py` already establishes cascade's optional half works, and
    resolving it actually reanimates - not a mock of any of these three
    pieces, the real keyword, the real card, the real effect.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Shardless Agent"],
            library=["Living End"],
            graveyard=["Grizzly Bears"],
            battlefield=["Forest", "Island", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    agent = scenario.cast_onto_stack(
        "Shardless Agent", *scenario.untapped_sources("Forest", "Island", "Forest")
    )

    result = cascade(scenario.game, agent, seed=0)
    assert result.hit is not None
    assert result.hit.name == "Living End"
    assert result.hit.zone is Zone.STACK  # cast during resolution (CR 608.2g)

    scenario.resolve_top()  # Living End resolves

    assert "Grizzly Bears" in [state.name for state in scenario.game.battlefield]
    # Grizzly Bears came back; Living End itself joins the graveyard once it
    # finishes resolving (CR 608.2n), free cast or not.
    assert [state.name for state in scenario.player("alice").cards_in(Zone.GRAVEYARD)] == [
        "Living End"
    ]
