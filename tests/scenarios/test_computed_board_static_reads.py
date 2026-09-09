"""Scenario: several `Game` board-inspection helpers read a permanent's
*computed* characteristics (CR 613.5) rather than its printed ones (CR
613.1's starting point, CR 712.8d's up-face-only printed reading) - the
legend rule's own supertype and name check, the land-subtype survey
`ManaAbility.resolve`'s conditional Tron clauses depend on, and the "could
this land produce" survey Reflecting Pool and Exotic Orchard read.

Every CR number below was looked up with `mise run rules:find` this session.

Every card below is a real Scryfall printing already in the pool
(`src/magic_cards_model/data/printings/`), used for the *shape* of continuous
effect it produces rather than for anything specific to the card:

- **The legend rule (CR 704.5j)** - `_legend_rule_losers` used to group
  permanents by their *printed* supertypes and name. The Mycosynth Gardens
  becoming a copy of Mox Opal (CR 707.2, 707.4) makes it a second, computed-
  only "Mox Opal" - Legendary Artifact - while its own printed card is an
  ordinary land. A fix that reads printed characteristics never notices the
  two Mox Opals share a name at all, and both survive; the computed board
  correctly forces the choice.
- **Land-subtype counting (CR 205.3i)** - `_controlled_land_types` feeds
  Urza's Tower's own "If you control an Urza's Mine and an Urza's
  Power-Plant, ..." Blood Moon (CR 305.7's set-a-land's-subtype path)
  strips Urza's Mine's and Urza's Power-Plant's printed subtypes and
  replaces them with Mountain, computed only - a printed read still counts
  them as Urza lands after Blood Moon has made them Mountains.
- **CR 106.7's "could produce" survey** - `_could_produce_survey` used to
  filter the battlefield on `Type.LAND in land.types`, the printed line.
  Toph, the First Metalbender's "Nontoken artifacts you control are lands in
  addition to their other types" makes Tablet of Discovery a land only on
  the computed board, so Reflecting Pool's "any type that a land you control
  could produce" only sees Tablet's fixed {T}: Add {R} once the survey reads
  computed types.

`_roles_beyond_the_newest` (CR 704.5z, CR 303.7a) is fixed the same way -
`board.of(permanent).subtypes` instead of the printed `permanent.subtypes` -
but no printing in the pool grants the "Role" subtype computed-only; every
Role in the pool prints it directly on the token. It is exercised below only
as a plain regression that the state-based action still works once its
board is threaded through rather than recomputed, since no card in the pool
distinguishes printed from computed for this specific site.

**`source_has_quality`** (CR 609.7b, CR 702.16a's own "sources ... that are
permanents with that card type" clause) is exercised directly, by calling
the public method itself rather than through a "protection from creatures"
printing - the pool has no card granting protection from a card type other
than Emrakul's own printed "protection from instants" (which asks about
spells, not battlefield permanents, so it cannot show this divergence
either). The method is public and this is exactly the fact under test, the
same way `_controlled_land_types` above is asked directly.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_the_legend_rule_catches_a_clone_that_copied_a_legendary_permanent():
    """CR 704.5j: "If two or more legendary permanents with the same name
    are controlled by the same player, that player chooses one of them, and
    the rest are put into their owners' graveyards." The Mycosynth Gardens'
    own activated ability (CR 707.2, 707.4) makes it a copy of Mox Opal - a
    Legendary Artifact only on the computed board - while alice's original
    Mox Opal is unaffected. `_legend_rule_losers` has to group by the
    computed name and supertypes to see the collision at all.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["The Mycosynth Gardens", "Forest", "Mox Opal"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gardens = scenario.find("The Mycosynth Gardens", Zone.BATTLEFIELD)
    real_mox = scenario.find("Mox Opal", Zone.BATTLEFIELD)
    (forest,) = scenario.untapped_sources("Forest")

    scenario.activate(gardens, forest, index=2, targets=[real_mox], x_value=0)
    scenario.resolve_top()

    chars = scenario.game.characteristics_of(gardens)
    assert chars.name == "Mox Opal"
    assert gardens.name == "The Mycosynth Gardens"  # the printed card never changed

    scenario.game.check_state_based_actions()

    still_on_battlefield = [
        gardens in scenario.game.battlefield,
        real_mox in scenario.game.battlefield,
    ]
    assert still_on_battlefield.count(True) == 1, "the legend rule chose one and binned the other"
    graveyard = scenario.player("alice").graveyard
    assert len(graveyard) == 1
    assert graveyard[0] in (gardens, real_mox)


def test_the_legend_rule_leaves_two_different_legendary_names_alone():
    """The inverse: alice's real Mox Opal and an *un-copied* Mycosynth
    Gardens share no name at all, so nothing about the legend rule should
    touch either. Guards a fix that grouped too eagerly.
    """
    scenario = Scenario().player("alice", battlefield=["The Mycosynth Gardens", "Mox Opal"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.game.check_state_based_actions()

    names = sorted(state.name for state in scenario.game.battlefield)
    assert names == ["Mox Opal", "The Mycosynth Gardens"]


def test_urza_tower_counts_urza_lands_by_their_computed_subtype():
    """CR 305.7: Blood Moon sets each nonbasic land's subtype to Mountain,
    replacing Urza's Mine's and Urza's Power-Plant's own subtypes with it.
    `_controlled_land_types` (through `colors_could_produce`) has to read
    that computed subtype rather than the two lands' still-printed "Urza's
    Mine"/"Urza's Power-Plant" text, or it would keep believing both Tron
    pieces are still out after Blood Moon has turned them into Mountains.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Blood Moon"],
            battlefield=["Urza's Mine", "Urza's Power Plant", "Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mine = scenario.find("Urza's Mine", Zone.BATTLEFIELD)
    power_plant = scenario.find("Urza's Power Plant", Zone.BATTLEFIELD)

    before = scenario.game._controlled_land_types("alice")
    assert "Mine" in before
    assert "Power-Plant" in before

    sources = scenario.untapped_sources("Urza's Mine", "Urza's Power Plant", "Mountain")
    scenario.cast_and_resolve("Blood Moon", *sources)

    after = scenario.game._controlled_land_types("alice")
    assert "Mine" not in after, "CR 305.7: the printed subtype is gone"
    assert "Power-Plant" not in after
    assert "Mountain" in after
    assert scenario.game.characteristics_of(mine).subtypes == ("Mountain",)
    assert scenario.game.characteristics_of(power_plant).subtypes == ("Mountain",)


def test_reflecting_pool_sees_a_computed_only_land_producing_a_fixed_color():
    """CR 106.7: Toph, the First Metalbender's static ability makes Tablet
    of Discovery ("{T}: Add {R}.") a land in addition to its other types,
    computed only. Reflecting Pool's own "{T}: Add one mana of any type that
    a land you control could produce" has to survey the battlefield by
    computed type to see it at all.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Toph, the First Metalbender", "Tablet of Discovery", "Reflecting Pool"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tablet = scenario.find("Tablet of Discovery", Zone.BATTLEFIELD)
    pool = scenario.find("Reflecting Pool", Zone.BATTLEFIELD)

    chars = scenario.game.characteristics_of(tablet)
    assert chars.is_land, "Toph: nontoken artifacts you control are lands too"

    from magic_cards_model.models.card import Color

    options = scenario.game.colors_could_produce(pool)
    assert Color.RED in options, "the survey has to see Tablet of Discovery as a land"


def test_reflecting_pool_does_not_see_a_plain_artifact_without_toph():
    """The inverse: with no Toph in play, Tablet of Discovery is never a
    land, and Reflecting Pool's survey should not include red at all.
    """
    scenario = (
        Scenario().player("alice", battlefield=["Tablet of Discovery", "Reflecting Pool"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    pool = scenario.find("Reflecting Pool", Zone.BATTLEFIELD)

    from magic_cards_model.models.card import Color

    options = scenario.game.colors_could_produce(pool)
    assert Color.RED not in options


def test_two_roles_from_the_same_player_still_lose_the_older_one():
    """Regression for `_roles_beyond_the_newest` threading a board through
    rather than recomputing one: two Monstrous Rage auras (Role-granting,
    CR 111.10k) on the same creature from the same controller still leave
    only the newer Role, exactly as before the refactor. No printing in the
    pool grants the "Role" subtype only computed, so this does not probe
    the printed/computed distinction itself - see the module docstring.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Monstrous Rage", "Monstrous Rage"],
            battlefield=["Grizzly Bears", "Mountain", "Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD)
    mountains = scenario.untapped_sources("Mountain", "Mountain")

    scenario.cast_and_resolve("Monstrous Rage", mountains[0], targets=[bears])
    first_role = scenario.find("Monster", Zone.BATTLEFIELD)
    scenario.cast_and_resolve("Monstrous Rage", mountains[1], targets=[bears])

    scenario.game.check_state_based_actions()

    assert first_role.zone is Zone.GRAVEYARD, "CR 704.5z: only the most recent Role survives"


def test_source_has_quality_sees_an_earthbent_lands_computed_creature_type():
    """CR 609.7b, CR 702.16a: "sources ... that are permanents with that
    card type" - `source_has_quality(source, "creature")` has to say True for
    an earthbent land (CR 701.66a) once it is on the battlefield, because
    that is exactly the fact protection from creatures (CR 702.16e) would
    ask about a damage source. Called directly on the public method: the
    pool has no card granting protection from a card type other than
    Emrakul's own printed "protection from instants", which asks about a
    *spell*, not a battlefield permanent, and so cannot exercise this
    divergence either.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Badgermole Cub"],
            battlefield=["Forest", "Forest", "Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest", "Forest")
    pay_sources, target_forest = sources[:2], sources[2]
    scenario.choose_trigger_targets("Badgermole Cub", [target_forest])
    scenario.cast_and_resolve("Badgermole Cub", *pay_sources)
    scenario.pass_until_resolved()

    assert scenario.game.source_has_quality(target_forest, "creature") is True
    assert scenario.game.source_has_quality(target_forest, "land") is True


def test_source_has_quality_stays_false_for_a_plain_lands_creature_quality():
    """The inverse: an un-animated Forest is never a creature source."""
    scenario = Scenario().player("alice", battlefield=["Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.find("Forest", Zone.BATTLEFIELD)

    assert scenario.game.source_has_quality(forest, "creature") is False
    assert scenario.game.source_has_quality(forest, "land") is True
