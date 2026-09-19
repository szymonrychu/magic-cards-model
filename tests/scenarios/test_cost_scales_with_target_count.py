"""Scenario: a spell's own printed cost that scales with how many targets it
ends up choosing - "This spell costs {1} more to cast for each target beyond
the first." (CR 601.2f).

Fireball prints the sentence outright: "This spell costs {1} more to cast for
each target beyond the first." Launch the Fleet prints the identical sentence
behind the ability word "Strive" instead: "Strive — This spell costs {1} more
to cast for each target beyond the first." CR 207.2c: an ability word "[has]
no special rules meaning and no individual entries in the Comprehensive
Rules" - "strive" is one of the words that list names - so the em dash in
front changes nothing about what the sentence after it means, and the two
cards' clauses are one mechanic, not two.

CR 602.2b makes this askable at all: casting an ability follows "the process
for casting a spell listed in rules 601.2b-i", and CR 601.2c's target
announcement is one of those rules, listed *before* 601.2f's total cost is
worked out. So by the time this sentence prices the spell, `Casting.targets`
already holds every target the caster actually chose (CR 601.2c: "Once the
number of targets the spell has is determined, that number doesn't change"),
and "beyond the first" is simply `len(targets) - 1`, floored at zero.

Every CR number here was verified with `mise run rules:find` in the session
that wrote this file.
"""

from magic_cards_model.machines import Step

from .harness import Scenario


def test_fireball_with_one_target_pays_no_increase():
    """ "Beyond the first" of one target is zero - the printed {X}{R} alone."""
    scenario = (
        Scenario()
        .player("alice", hand=["Fireball"], battlefield=["Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Fireball", targets=["bob"])
    casting.x_value = 5

    assert str(casting.total_cost.mana) == "{5}{R}"


def test_fireball_with_three_targets_pays_two_more():
    """Three targets is two beyond the first, at {1} each: {X}{R} plus {2}."""
    scenario = (
        Scenario()
        .player("alice", hand=["Fireball"], battlefield=["Mountain"])
        .player("bob", battlefield=["Grizzly Bears", "Watchwolf"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    watchwolf = scenario.creature("Watchwolf", "bob")

    casting = scenario.cast("Fireball", targets=[bears, watchwolf, "bob"])
    casting.x_value = 5

    assert str(casting.total_cost.mana) == "{7}{R}"


def test_fireball_targets_are_announced_before_the_cost_reflects_them():
    """CR 601.2c before CR 601.2f: with no targets chosen yet, the increase is
    zero - the same "targets before cost" order Dragonfire Blade's own
    per-target equip discount already relies on."""
    scenario = (
        Scenario()
        .player("alice", hand=["Fireball"], battlefield=["Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Fireball")
    casting.x_value = 5

    assert str(casting.total_cost.mana) == "{5}{R}"


def test_launch_the_fleet_off_set_proof_with_one_target():
    """A wording variant of the identical sentence - "Strive — This spell
    costs {1} more to cast for each target beyond the first." - proving the
    fix reads the sentence, not Fireball's own exact printing."""
    scenario = (
        Scenario()
        .player("alice", hand=["Launch the Fleet"], battlefield=["Plains"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    casting = scenario.cast("Launch the Fleet", targets=[bears])

    assert str(casting.total_cost.mana) == "{W}"


def test_launch_the_fleet_off_set_proof_with_three_targets():
    """Three targets, two beyond the first, {1} each: {W} plus {2}."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Launch the Fleet"],
            battlefield=["Plains", "Grizzly Bears", "Watchwolf"],
        )
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    watchwolf = scenario.creature("Watchwolf", "alice")
    giant = scenario.creature("Hill Giant", "bob")

    casting = scenario.cast("Launch the Fleet", targets=[bears, watchwolf, giant])

    assert str(casting.total_cost.mana) == "{2}{W}"


def test_a_card_with_no_such_sentence_pays_no_increase_at_all():
    """The control: an ordinary multi-target spell with no "costs more per
    target" sentence of its own is untouched by this reader (Arc Lightning:
    "Arc Lightning deals 3 damage divided as you choose among one, two, or
    three targets.", no cost clause at all)."""
    scenario = (
        Scenario()
        .player("alice", hand=["Arc Lightning"], battlefield=["Mountain"])
        .player("bob", battlefield=["Grizzly Bears", "Watchwolf"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    watchwolf = scenario.creature("Watchwolf", "bob")

    casting = scenario.cast("Arc Lightning", targets=[bears, watchwolf, "bob"])

    assert str(casting.total_cost.mana) == "{2}{R}"
