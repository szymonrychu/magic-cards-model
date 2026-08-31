"""Scenario: Mosswort Bridge - Hideaway 4 (CR 702.75a) and "{G}, {T}: You may
play the exiled card without paying its mana cost if creatures you control
have total power 10 or greater."

CR 702.75a: "Hideaway N" means "When this permanent enters, look at the top
N cards of your library. Exile one of them face down and put the rest on the
bottom of your library in a random order." `docs/engine-coverage.md` records
hideaway as one of the keywords with no execution path before this session -
`machines/keywords.py`'s `_hideaway_ability`/`_hideaway_effect` are the fix,
reusing `ExileMarker.IMPRINTED` (the general "exiled with this permanent"
link, not specific to the ability word "Imprint") so the land's own later
ability can find the card again through `Game.card_imprinted_on`.

The second ability's own "you may play ... if [condition]" is CR 608.2d's
"the player can't choose an option that's illegal or impossible": the
permission (`Game.grant_play_permission`, CR 601.3) is only ever granted
once the total-power condition already holds.

Every rule cited here was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 702.75a** - hideaway itself, quoted above.
- **CR 406.4** - the annotated exile pile.
- **CR 701.24a** - shuffling only promises no player knows the order; the
  rest-on-bottom-in-random-order shape here is CR 702.75a's own wording, not
  a shuffle event.
- **CR 601.3** - "A player can begin to cast a spell only if a rule or effect
  allows that player to cast it" - the permission `grant_play_permission`
  creates.
- **CR 118.9** - "without paying its mana cost."
- **CR 608.2d** - the conditional "you may."
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import ExileMarker

from .harness import Scenario


def _scenario(library: list[str]) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Mosswort Bridge"],
            library=library,
            battlefield=["Forest"] * 4,
        )
        .player("bob")
    )


def test_hideaway_exiles_one_of_the_top_four_face_down_and_bottoms_the_rest():
    scenario = _scenario(
        ["Lightning Bolt", "Opt", "Goblin Guide", "Craterous Stomp", "Faithless Looting"]
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    top_four = [
        scenario.find(name, Zone.LIBRARY, "alice")
        for name in ["Lightning Bolt", "Opt", "Goblin Guide", "Craterous Stomp"]
    ]
    scenario.will_choose_cards(top_four[2], source="Mosswort Bridge")

    bridge = scenario.play_land("Mosswort Bridge", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    goblin_guide = top_four[2]
    assert goblin_guide.zone is Zone.EXILE
    assert goblin_guide.exile_annotation is not None
    assert goblin_guide.exile_annotation.marker is ExileMarker.IMPRINTED
    assert goblin_guide.exile_annotation.linked_permanent_id == bridge.id

    library_names = [state.name for state in scenario.player("alice").library]
    assert "Goblin Guide" not in library_names
    assert set(library_names[-3:]) == {"Lightning Bolt", "Opt", "Craterous Stomp"}
    assert scenario.game.card_imprinted_on(bridge.id) is goblin_guide


def test_playing_the_hidden_card_once_total_power_is_high_enough():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Mosswort Bridge"],
            library=["Goblin Guide", "Opt", "Lightning Bolt", "Craterous Stomp"],
            battlefield=["Forest"] * 4 + ["Elder Gargaroth", "Ancient Adamantoise"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    goblin_guide = scenario.find("Goblin Guide", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(goblin_guide, source="Mosswort Bridge")

    bridge = scenario.play_land("Mosswort Bridge", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    # Hideaway enters the land tapped (CR 614.1c's own separate clause) -
    # untapped by hand here since this file is about the second ability, not
    # the already-generic "enters tapped" shape.
    bridge.untap()

    forest = scenario.untapped_sources("Forest")[0]
    scenario.activate(bridge, forest, index=1)
    scenario.resolve_top()

    permission = scenario.game.play_permission_for(goblin_guide, "alice")
    assert permission is not None
    assert not permission.pays_mana_cost


def test_playing_the_hidden_card_is_refused_when_total_power_is_too_low():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Mosswort Bridge"],
            library=["Goblin Guide", "Opt", "Lightning Bolt", "Craterous Stomp"],
            battlefield=["Forest"] * 4 + ["Elder Gargaroth"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    goblin_guide = scenario.find("Goblin Guide", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(goblin_guide, source="Mosswort Bridge")

    bridge = scenario.play_land("Mosswort Bridge", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()
    bridge.untap()

    forest = scenario.untapped_sources("Forest")[0]
    scenario.activate(bridge, forest, index=1)
    scenario.resolve_top()

    assert scenario.game.play_permission_for(goblin_guide, "alice") is None
