"""Scenario: token count and naming shapes this wave adds.

- Smaug, Wicked Worm: "When Smaug enters, create X tapped Treasure tokens,
  where X is the number of artifacts your opponents control." - `count_
  expression`'s "you control" reader widened to "your opponents control".
- Stone-Giant of High Pass: "Whenever this creature enters or attacks,
  create a 3/1 colorless Wall artifact creature token with defender named
  Stone Boulder." - `_TOKEN_CLAUSE_RE`'s "named `<Name>`" ahead of "with
  `<tail>`" order, reordered for a card that prints the keyword tail first.

Verified this session with `mise run rules:find`:

- **CR 613.5** - "your opponents control" is read off the computed board,
  the identical layer-aware count `count_expression`'s existing "you
  control" branch already uses.
- **CR 111.9** - a token's own name is set as it is created, independent of
  which order its other characteristics are printed in.
- **CR 508.3d/603.6a** - "enters or attacks" is two separate trigger
  conditions sharing one paragraph (CR 603.1b), already read by the engine
  before this wave; only the token clause itself is new here.

`Viridian Lorebearers` (off-pool, added with `scripts/add_card.py`,
Modern-legal, verified against its own printed text) proves the "your
opponents control" widening on a second printing sharing Smaug's own
`count_expression` machinery but a different consuming effect (a pump, not a
token count). `Fire Navy Trebuchet` (off-pool, added the same way,
Modern/Pioneer/Standard-legal) proves the reordered "token with `<tail>`
named `<Name>`" shape on a second printing.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.models import Zone

from .harness import Scenario


def test_smaug_creates_one_tapped_treasure_per_artifact_opponents_control():
    """Bob controls two artifacts (a Mox Amber-shaped stand-in and an
    Ornithopter); Alice controls a third that must not count."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Smaug, Wicked Worm"],
            battlefield=["Swamp"] * 4 + ["Mountain"] + ["Ornithopter"],
        )
        .player("bob", battlefield=["Ornithopter", "Ornithopter"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve(
        "Smaug, Wicked Worm", *scenario.untapped_sources(*(["Swamp"] * 4 + ["Mountain"]))
    )
    scenario.pass_until_resolved()

    treasures = [
        state
        for state in scenario.game.permanents_controlled_by("alice")
        if state.name == "Treasure Token"
    ]
    assert len(treasures) == 2
    assert all(state.tapped for state in treasures)


def test_smaug_creates_no_treasures_with_no_opposing_artifacts():
    scenario = (
        Scenario()
        .player("alice", hand=["Smaug, Wicked Worm"], battlefield=["Swamp"] * 4 + ["Mountain"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve(
        "Smaug, Wicked Worm", *scenario.untapped_sources(*(["Swamp"] * 4 + ["Mountain"]))
    )
    scenario.pass_until_resolved()

    assert not any(
        state.name == "Treasure Token" for state in scenario.game.permanents_controlled_by("alice")
    )


def test_viridian_lorebearers_reads_the_same_opponents_control_count():
    """Off-pool proof: a pump effect naming "the number of artifacts your
    opponents control" through the identical widened `count_expression`."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Forest"] * 4 + ["Viridian Lorebearers", "Elvish Mystic"],
        )
        .player("bob", battlefield=["Ornithopter", "Ornithopter"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lorebearers = scenario.creature("Viridian Lorebearers", "alice")
    lorebearers.summoning_sick = False
    mystic = scenario.creature("Elvish Mystic", "alice")

    scenario.activate(
        lorebearers,
        *scenario.untapped_sources(*["Forest"] * 4),
        targets=[mystic],
    )
    scenario.pass_until_resolved()

    assert scenario.game.power_of(mystic) == 1 + 2
    assert scenario.game.toughness_of(mystic) == 1 + 2


def test_stone_giant_creates_a_named_wall_when_it_enters():
    """The reordered "token with defender named Stone Boulder" clause."""
    scenario = (
        Scenario()
        .player("alice", hand=["Stone-Giant of High Pass"], battlefield=["Mountain"] * 7)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve(
        "Stone-Giant of High Pass", *scenario.untapped_sources(*["Mountain"] * 7)
    )
    scenario.pass_until_resolved()

    boulder = scenario.creature("Stone Boulder", "alice")
    characteristics = scenario.game.characteristics_of(boulder)
    assert characteristics.power == 3
    assert characteristics.toughness == 1
    assert has_keyword(boulder, Keyword.DEFENDER, scenario.game)


def test_fire_navy_trebuchet_reads_the_same_reordered_token_clause():
    """Off-pool proof: "create a 2/1 ... token with flying named Ballistic
    Boulder that's tapped and attacking." shares the reordered name-after-tail
    shape `_reorder_token_named_after_tail` reads for Stone-Giant."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Fire Navy Trebuchet", "Forest", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    attacker = scenario.creature("Grizzly Bears", "alice")
    attacker.summoning_sick = False
    scenario.attack_with(attacker)
    scenario.pass_until_resolved()

    boulder = scenario.creature("Ballistic Boulder", "alice")
    assert boulder.zone is Zone.BATTLEFIELD
    assert has_keyword(boulder, Keyword.FLYING, scenario.game)
