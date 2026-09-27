"""Invasion of Pyrulea // Gargantuan Slabhorn.

Verified this session with `mise run rules:find` against the current CR:

- **CR 701.22a** - "To 'scry N' means to look at the top N cards of your
  library, then put any number of them on the bottom of your library in any
  order and the rest on top of your library in any order."
- **CR 701.20a** - revealing a card is a public action.
- **CR 712.1** - "A double-faced card has a Magic card face on one side and
  either a Magic card face or half of an oversized card face on the other."
- **CR 701.27g** - "Some spells and abilities refer to a 'transformed
  permanent.' This phrase refers to a double-faced permanent on the
  battlefield with its back face up."

Front face: "When this Siege enters, scry 3, then reveal the top card of
your library. If it's a land or double-faced card, draw a card." Back face
(Gargantuan Slabhorn): "Trample, ward {2} / Other transformed permanents you
control have trample and ward {2}."

Track Down (real, Modern/Pioneer-legal sorcery: "Scry 3, then reveal the top
card of your library. If it's a creature or land card, draw a card.") proves
the "Scry N, then reveal the top card ... If it's a `<quality>` card, draw a
card." template generalises beyond this Siege's own "land or double-faced"
quality.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

PYRULEA = "Invasion of Pyrulea"
TRACK_DOWN = "Track Down"
IKORIA = "Invasion of Ikoria"


def _scry_bottoming_the_top_three(scenario, library_names: list[str], *, username: str = "alice"):
    """Bottom the top three library cards on the next scry (CR 701.22a),
    leaving whatever was fourth as the new top card."""
    to_bottom = [scenario.find(name, Zone.LIBRARY, username) for name in library_names[:3]]
    scenario.scry_bottoming(*to_bottom, username=username)


def test_draws_when_the_scried_top_card_is_a_land():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[PYRULEA],
            battlefield=["Forest", "Island"],
            library=["Llanowar Elves", "Goblin Guide", "Elite Vanguard", "Mountain", "Swamp"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lands = scenario.untapped_sources("Forest", "Island")
    alice = scenario.player("alice")

    _scry_bottoming_the_top_three(scenario, ["Llanowar Elves", "Goblin Guide", "Elite Vanguard"])
    scenario.cast_and_resolve(PYRULEA, *lands)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    # Mountain (the 4th library card) is on top once the scry bottoms the
    # first 3; a land, so the reveal draws it, leaving Swamp on top.
    assert alice.library[0].name == "Swamp"
    assert [state.name for state in alice.hand] == ["Mountain"]


def test_draws_when_the_scried_top_card_is_double_faced():
    """ "Double-faced card" (CR 712.1) - a transform/MDFC layout, not a card
    type: Invasion of Ikoria (a Battle - Siege) qualifies even sitting in a
    library, unplayed."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[PYRULEA],
            battlefield=["Forest", "Island"],
            library=["Llanowar Elves", "Goblin Guide", "Elite Vanguard", IKORIA, "Swamp"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lands = scenario.untapped_sources("Forest", "Island")
    alice = scenario.player("alice")

    _scry_bottoming_the_top_three(scenario, ["Llanowar Elves", "Goblin Guide", "Elite Vanguard"])
    scenario.cast_and_resolve(PYRULEA, *lands)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    # Invasion of Ikoria (the 4th library card) is on top once the scry
    # bottoms the first 3; a double-faced card, so the reveal draws it.
    assert alice.library[0].name == "Swamp"
    assert [state.name for state in alice.hand] == [IKORIA]


def test_does_not_draw_when_the_scried_top_card_is_neither():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[PYRULEA],
            battlefield=["Forest", "Island"],
            library=["Mountain", "Swamp", "Plains", "Llanowar Elves", "Goblin Guide"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lands = scenario.untapped_sources("Forest", "Island")
    alice = scenario.player("alice")

    _scry_bottoming_the_top_three(scenario, ["Mountain", "Swamp", "Plains"])
    scenario.cast_and_resolve(PYRULEA, *lands)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    # Llanowar Elves (the 4th library card) is on top once the scry bottoms
    # the first 3; neither a land nor double-faced, so nothing is drawn and
    # it stays on top.
    assert alice.library[0].name == "Llanowar Elves"
    assert len(alice.hand) == 0


def test_track_down_shares_the_scry_then_reveal_conditional_draw_template():
    """A real Modern/Pioneer-legal sibling with a different quality
    ("creature or land") on the identical "Scry N, then reveal the top card
    of your library. If it's a `<quality>` card, draw a card." template."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[TRACK_DOWN],
            battlefield=["Forest", "Forest"],
            library=["Island", "Swamp", "Plains", "Llanowar Elves", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lands = scenario.untapped_sources("Forest", "Forest")
    alice = scenario.player("alice")

    _scry_bottoming_the_top_three(scenario, ["Island", "Swamp", "Plains"])
    scenario.cast_and_resolve(TRACK_DOWN, *lands)

    # Llanowar Elves (the 4th library card) is on top once the scry bottoms
    # the first 3; a creature, so the reveal draws it, leaving Mountain on top.
    assert alice.library[0].name == "Mountain"
    assert [state.name for state in alice.hand] == ["Llanowar Elves"]


def test_back_face_grants_trample_and_ward_to_other_transformed_permanents_only():
    """ "Other transformed permanents you control have trample and ward {2}."
    (CR 701.27g's "transformed permanent") - a second transformed permanent
    (Zilortha, Apex of Ikoria) gains both; a permanent that never transformed
    (Grizzly Bears) gains neither."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[PYRULEA, IKORIA],
            battlefield=["Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    slabhorn_card = scenario.find(PYRULEA, Zone.HAND, "alice")
    ikoria_card = scenario.find(IKORIA, Zone.HAND, "alice")
    scenario.game.put_onto_battlefield(slabhorn_card, "alice", transformed=True)
    zilortha = scenario.game.put_onto_battlefield(ikoria_card, "alice", transformed=True)
    bears = scenario.creature("Grizzly Bears", "alice")
    game = scenario.game

    assert has_keyword(zilortha, Keyword.TRAMPLE, game)
    assert any(
        line.lower().startswith("ward {2}") for line in game.characteristics_of(zilortha).abilities
    )
    assert not has_keyword(bears, Keyword.TRAMPLE, game)
    assert not any(
        line.lower().startswith("ward") for line in game.characteristics_of(bears).abilities
    )
