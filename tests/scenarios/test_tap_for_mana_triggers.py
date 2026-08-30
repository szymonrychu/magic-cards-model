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
from magic_cards_model.models import Zone
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
    """`test_aura_attachment.py`'s pattern for attaching an Aura without a full
    cast: `machines/effects.py` has no entry that attaches a resolving Aura,
    so the attachment is made directly and the trigger is what is under test.
    """
    scenario = (
        Scenario().player("alice", battlefield=["Forest", "Utopia Sprawl"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.find("Forest", Zone.BATTLEFIELD)
    sprawl = scenario.find("Utopia Sprawl", Zone.BATTLEFIELD)
    sprawl.attach_to(forest)

    scenario.activate(forest)

    assert scenario.stack_names() == ["Utopia Sprawl's triggered ability"]


def test_a_different_land_being_tapped_does_not_trigger_utopia_sprawl():
    """Only the specific land the Aura is attached to - CR 303.4 - qualifies as
    "enchanted Forest", not just any Forest the same player controls.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Forest", "Forest", "Utopia Sprawl"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    enchanted, other = scenario.untapped_sources("Forest", "Forest", username="alice")
    sprawl = scenario.find("Utopia Sprawl", Zone.BATTLEFIELD)
    sprawl.attach_to(enchanted)

    scenario.activate(other)

    assert scenario.stack_names() == []
