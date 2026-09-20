"""FRA stream S8b: "Separate all `<quality>` target player controls into two
piles. `<consequence>` all `<quality>` in the pile of that player's choice."
- CR 700.3's pile primitive, a genuine **two-player, two-step** decision
(`_SEPARATE_INTO_TWO_PILES_RE` in `machines/effects.py`,
`DecisionKind.CHOOSE_PILE` in `machines/decisions.py`).

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file.

- **CR 700.3/700.3a** - "Some effects cause objects to be temporarily
  grouped into piles. Each of the affected objects must be put into exactly
  one of those piles, unless the effect specifies otherwise."
- **CR 700.3d** - "A pile can contain zero or more objects."
- **CR 608.2c** - "The controller of the spell or ability follows its
  instructions in the order written" - the unattributed default performer
  of an instruction nothing else names.
- **CR 701.21a** - sacrifice. **CR 701.16a** - regeneration replaces
  destruction with a specific set of effects; this instruction is destroy,
  not a "would be destroyed" event, so "they can't be regenerated" only
  ever reinforces the outcome this clause already produces.
- **CR 115.1** - "target player" is a real target, chosen as the ability is
  activated (CR 601.2c/602.2b).

**This is not one player's free choice.** Liliana of the Veil's own printed
sentence never says who separates - only the second sentence names a
performer ("That player sacrifices ..."), and CR 608.2c's own default for
an unattributed instruction is the resolving ability's *controller*, not
the target. Confirmed against the card's official ruling: "When Liliana's
third ability resolves, **you** put each permanent the player controls
into one of the two piles" - "you" being Liliana's own controller. The
*target* player only ever picks a whole pile afterward. An earlier version
of this reader modelled both steps as one player's free choice, which is
correct only when the same player performs both - it does not hold here,
so it was replaced with a true two-step primitive: `Decision.kind ==
CHOOSE_CARDS` (`exact=False`, the same "any number of these" shape
`SCRY`/`SURVEIL` already use) for the controller's own division, then
`DecisionKind.CHOOSE_PILE` (a plain boolean, the same shape
`PUT_ON_TOP_OR_BOTTOM` already is) for the target's own pick.

Liliana of the Veil's own `-6` is the reported ability. Do or Die (real,
non-FRA, non-pool) is the off-set proof: an instant printing the identical
two-sentence pile shape narrowed to "creatures" and "Destroy" rather than
"permanents" and "sacrifices" - proof the consequence verb, not just the
pile-division sentence, generalises. Every scenario below activates or
casts the ability under one player's control and targets a genuinely
*different* player, so the two decisions land on two different players by
construction, not by coincidence.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def test_liliana_of_the_veils_minus_six_lets_alice_divide_and_bob_choose_the_pile():
    """Alice controls Liliana and does the dividing; bob is the target and
    picks which whole pile he sacrifices - two different players, two
    different questions, in that order."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Liliana of the Veil"])
        .player(
            "bob",
            battlefield=["Grizzly Bears", "Hill Giant", "Elvish Mystic", "Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    liliana = scenario.find("Liliana of the Veil", Zone.BATTLEFIELD, "alice")
    liliana.add_counters(Counter.LOYALTY, 3)  # 3 printed -> 6, enough for -6
    bears = scenario.creature("Grizzly Bears", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    elves = scenario.creature("Elvish Mystic", "bob")
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "bob")

    # Step 1: alice (Liliana's own controller, CR 608.2c's default) divides
    # bob's four permanents - bears and the giant go in pile one.
    scenario.will_choose_cards(bears, giant, username="alice", source="Liliana of the Veil")
    # Step 2: bob (the target) picks pile one to sacrifice.
    scenario.will_choose_pile(True, username="bob", source="Liliana of the Veil")
    scenario.activate(liliana, index=2, targets=["bob"])
    scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD
    assert giant.zone is Zone.GRAVEYARD
    assert elves.zone is Zone.BATTLEFIELD, "pile two: bob's own pick left it alone"
    assert mountain.zone is Zone.BATTLEFIELD, "a land is a permanent bob controls, not excluded"


def test_bob_can_pick_the_complement_pile_instead():
    """The identical division as above, but bob picks pile *two* this time -
    proof the second decision genuinely belongs to bob, not a fixed outcome
    of alice's own split."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Liliana of the Veil"])
        .player(
            "bob",
            battlefield=["Grizzly Bears", "Hill Giant", "Elvish Mystic", "Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    liliana = scenario.find("Liliana of the Veil", Zone.BATTLEFIELD, "alice")
    liliana.add_counters(Counter.LOYALTY, 3)
    bears = scenario.creature("Grizzly Bears", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    elves = scenario.creature("Elvish Mystic", "bob")
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "bob")

    scenario.will_choose_cards(bears, giant, username="alice", source="Liliana of the Veil")
    scenario.will_choose_pile(False, username="bob", source="Liliana of the Veil")
    scenario.activate(liliana, index=2, targets=["bob"])
    scenario.pass_until_resolved()

    assert bears.zone is Zone.BATTLEFIELD, "pile one: bob picked pile two instead"
    assert giant.zone is Zone.BATTLEFIELD
    assert elves.zone is Zone.GRAVEYARD, "pile two: bob's own choice"
    assert mountain.zone is Zone.GRAVEYARD


def test_liliana_of_the_veils_minus_six_can_leave_pile_one_empty():
    """CR 700.3d: a pile may be empty - alice's own division can put
    nothing in pile one, and bob choosing it sacrifices nothing."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Liliana of the Veil"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    liliana = scenario.find("Liliana of the Veil", Zone.BATTLEFIELD, "alice")
    liliana.add_counters(Counter.LOYALTY, 3)
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.will_choose_cards(username="alice", source="Liliana of the Veil")
    scenario.will_choose_pile(True, username="bob", source="Liliana of the Veil")
    scenario.activate(liliana, index=2, targets=["bob"])
    scenario.pass_until_resolved()

    assert bears.zone is Zone.BATTLEFIELD


def test_do_or_die_destroys_the_pile_bob_chooses_of_creatures_only():
    scenario = (
        Scenario()
        .player("alice", hand=["Do or Die"], battlefield=["Swamp", "Swamp"])
        .player("bob", battlefield=["Grizzly Bears", "Hill Giant", "Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "bob")
    sources = scenario.untapped_sources("Swamp", "Swamp")

    scenario.will_choose_cards(bears, username="alice", source="Do or Die")
    scenario.will_choose_pile(True, username="bob", source="Do or Die")
    scenario.cast_and_resolve("Do or Die", *sources, targets=["bob"])

    assert bears.zone is Zone.GRAVEYARD
    assert giant.zone is Zone.BATTLEFIELD, "pile two: bob's own choice left the giant out"
    assert mountain.zone is Zone.BATTLEFIELD, "Do or Die's own quality is creatures only"
