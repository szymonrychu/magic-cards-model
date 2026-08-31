""" "Tapped for mana", CR 106.12 and 106.12a.

CR 106.12: "To 'tap [a permanent] for mana' is to activate a mana ability of
that permanent that includes the {T} symbol in its activation cost."

CR 106.12a: "An ability that triggers whenever a permanent 'is tapped for
mana' ... triggers whenever such a mana ability resolves and produces mana."

The event is emitted from two places that both end in a permanent's own
`{T}: Add ...` ability resolving - `Game.activate_ability`'s CR 605.3b fast
path, when a permanent is tapped to activate its own mana ability, and
`machines/cost.CostPayment.tap_for_mana`, when a permanent is tapped to help
pay some other spell or ability's total cost - through the same
`machines/triggers.tapped_for_mana_event` builder, so a scenario exercising
either path is exercising the same event shape.

Three cards in the pool read this condition:

- Leyline of Abundance / Badgermole Cub: "Whenever you tap a creature for
  mana, add an additional {G}." - the controller's own creature, of any
  origin.
- Utopia Sprawl: "Whenever enchanted Forest is tapped for mana, its controller
  adds an additional one mana of the chosen color." - only the land the Aura
  is attached to, read off `attached_to`.

None of these have an `EFFECTS` entry ("add an additional" mana is not itself
wired up), and a *triggered* mana ability is not modelled as skipping the
stack the way CR 605.4a says it should (see `docs/engine-coverage.md`), so
every assertion here is "the ability reached the stack", not what it produces.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Color, Zone
from magic_cards_model.models.card import Type
from tests.scenarios.harness import Scenario


def test_tapping_your_own_creature_for_its_own_mana_ability_triggers_leyline():
    """The CR 605.3b fast path: Llanowar Elves activates its own {T}: Add {G}."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Leyline of Abundance", "Llanowar Elves"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    elves = scenario.creature("Llanowar Elves", "alice")

    scenario.activate(elves)

    assert scenario.stack_names() == ["Leyline of Abundance's triggered ability"]


def test_tapping_a_land_for_mana_does_not_trigger_leyline():
    """ "a creature" excludes an ordinary land, even though a land is also
    tapped for mana through the very same code path.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Leyline of Abundance", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (forest,) = scenario.untapped_sources("Forest", username="alice")

    scenario.activate(forest)

    assert scenario.stack_names() == []


def test_tapping_a_creature_to_pay_for_a_spell_triggers_badgermole_cub():
    """`CostPayment.tap_for_mana`'s call site: a second Llanowar Elves is cast,
    tapping the first one to help pay for it.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Llanowar Elves"],
            battlefield=["Badgermole Cub", "Llanowar Elves"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tapper = scenario.creature("Llanowar Elves", "alice")

    scenario.cast_onto_stack("Llanowar Elves", tapper, username="alice")

    assert scenario.stack_names() == ["Llanowar Elves", "Badgermole Cub's triggered ability"]


def test_an_opponents_creature_tapped_for_mana_does_not_trigger_badgermole_cub():
    """ "you tap" - only the controller's own taps count."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Badgermole Cub"])
        .player("bob", battlefield=["Llanowar Elves"])
        .build()
    )
    # Bob's Elves is summoning sick until his own turn begins (CR 302.6); start
    # at alice's cleanup and advance into bob's turn so it can be tapped at all.
    scenario.start_at(Step.CLEANUP)
    scenario.advance()
    elves = scenario.creature("Llanowar Elves", "bob")

    scenario.activate(elves, username="bob")

    assert scenario.stack_names() == []


def test_the_enchanted_land_being_tapped_for_mana_triggers_utopia_sprawl():
    """Cast and resolved for real: `resolve_top` now runs CR 608.3c for an Aura
    spell, attaching it to the target it resolved with, so this no longer needs
    `test_aura_attachment.py`'s hand-attach workaround - a real Utopia Sprawl,
    cast at a real Forest, is what enchants it.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Utopia Sprawl"], battlefield=["Forest", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    payer, forest = scenario.untapped_sources("Forest", "Forest", username="alice")

    sprawl = scenario.cast_and_resolve("Utopia Sprawl", payer, targets=[forest])

    assert sprawl.zone is Zone.BATTLEFIELD
    assert sprawl.attached_to == forest.id

    scenario.activate(forest)

    assert scenario.stack_names() == ["Utopia Sprawl's triggered ability"]


def test_tapping_a_plain_noncreature_land_does_not_trigger_badgermole_cub():
    """Real-game report (log seq 169-171): Nurturing Peatland's type line is
    plain "Land", printing no creature type, and tapping it for mana still
    queued a Badgermole Cub trigger copy alongside the two taps that actually
    were creatures. "A creature" excludes an ordinary land even when a
    creature-typed Badgermole Cub is watching every tap on the battlefield.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Badgermole Cub", "Nurturing Peatland"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (peatland,) = scenario.untapped_sources("Nurturing Peatland", username="alice")

    scenario.activate(peatland, color=Color.GREEN)

    assert scenario.stack_names() == []


def test_tapping_a_mana_producing_creature_triggers_badgermole_cub():
    """Delighted Halfling is an ordinary `Creature - Halfling Citizen` with a
    `{T}: Add {C}.` ability - the plain case the false-positive report above
    has to be told apart from.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Badgermole Cub", "Delighted Halfling"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    halfling = scenario.creature("Delighted Halfling", "alice")

    scenario.activate(halfling)

    assert scenario.stack_names() == ["Badgermole Cub's triggered ability"]


def test_tapping_a_land_animated_into_a_creature_triggers_badgermole_cub():
    """The sharp edge: a land earthbend turned into a creature is a Creature
    only on the *computed* board (CR 613.5) - its own `CardState.types`, the
    up-face-aware but layer-blind read `tapped_for_mana_event` used before this
    fix, still reports plain `Land`. Badgermole Cub's own ETB earthbends one of
    the Forests paying for it, so by the time that Forest is tapped for mana it
    has already been a 0/0 land creature with haste for a full resolution.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Badgermole Cub"], battlefield=["Forest", "Forest", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    pay1, pay2, target_forest = scenario.untapped_sources(
        "Forest", "Forest", "Forest", username="alice"
    )
    scenario.choose_trigger_targets("Badgermole Cub", [target_forest])
    scenario.cast_and_resolve("Badgermole Cub", pay1, pay2)
    scenario.pass_until_resolved()

    # Still plain `Land` on the printed/up-face read - only the computed board
    # (Game.characteristics_of) knows earthbend made it a creature too.
    assert Type.CREATURE not in target_forest.types

    scenario.activate(target_forest)

    assert scenario.stack_names() == ["Badgermole Cub's triggered ability"]


def test_a_different_land_being_tapped_does_not_trigger_utopia_sprawl():
    """Only the specific land the Aura is attached to - CR 303.4 - qualifies as
    "enchanted Forest", not just any Forest the same player controls.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Utopia Sprawl"], battlefield=["Forest", "Forest", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    payer, enchanted, other = scenario.untapped_sources(
        "Forest", "Forest", "Forest", username="alice"
    )

    scenario.cast_and_resolve("Utopia Sprawl", payer, targets=[enchanted])

    scenario.activate(other)

    assert scenario.stack_names() == []
