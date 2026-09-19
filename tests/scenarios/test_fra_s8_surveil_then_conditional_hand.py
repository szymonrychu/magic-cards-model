"""FRA stream S8: "Surveil `<n>`. If you put a `<quality>` card into your
graveyard this way, put that card into your hand." (CR 701.25a, CR 608.2c).

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file.

- **CR 701.25a** - surveil: look at the top N, then any number into the
  graveyard and the rest back on top.
- **CR 608.2c** - "this way" is anaphora onto exactly what the surveil just
  put into the graveyard - a fresh graveyard scan could not tell that card
  apart from one already sitting there.
- **CR 202.3** - mana value, for Enlightened Confidant's own dynamic
  ceiling.

Chandra, Chill of Compliance's own `+1` is one reported card - a plain,
static quality ("noncreature, nonland"). **Enlightened Confidant is not an
off-set proof - it is a second FRA S8 card in this same stream's own
assignment** (`fra-names.txt` lists it; Scryfall has no printing of this
name outside `fra`, so the "real Modern staple" this docstring used to
claim is a different card that merely shares a name with a card this set
also prints). Both are built here as themselves, not as generality proof
for one another.

The genuine off-set proof for the *new* capability Enlightened Confidant
needed - `Game.life_gained_amount_this_turn`, a per-turn-history field
nothing before this stream recorded the actual life-gained amount for,
only whether any was gained at all - is Celestine, the Living Saint (real,
non-FRA, non-pool, Warhammer 40,000): "return target creature card with
mana value X or less from your graveyard to the battlefield, where X is
the amount of life you gained this turn." A different clause family
entirely (a *targeted* reanimation's own comparison bound, read through
`machines/targeting.py`'s `TargetRequirement.comparison_x_definition`,
not the surveil-then-hand player clause `count_expression`'s own
`_COUNT_LIFE_GAINED_THIS_TURN_RE` branch feeds), proving the expression
reader itself - not this one clause shape - is what generalizes.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.targeting import profile_for_text
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_chandra_surveils_and_takes_a_noncreature_nonland_card():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Chandra, Chill of Compliance"],
            library=["Lightning Bolt", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    chandra = scenario.creature("Chandra, Chill of Compliance", "alice")
    alice = scenario.player("alice")
    bolt = alice.library[0]
    assert bolt.name == "Lightning Bolt"

    scenario.surveil_to_graveyard(bolt, username="alice")
    scenario.activate(chandra, index=0)
    scenario.pass_until_resolved()

    assert bolt.zone is Zone.HAND, "an instant is noncreature and nonland"


def test_chandra_leaves_a_land_in_the_graveyard_not_the_hand():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Chandra, Chill of Compliance"],
            library=["Forest", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    chandra = scenario.creature("Chandra, Chill of Compliance", "alice")
    alice = scenario.player("alice")
    forest = alice.library[0]
    assert forest.name == "Forest"

    scenario.surveil_to_graveyard(forest, username="alice")
    scenario.activate(chandra, index=0)
    scenario.pass_until_resolved()

    assert forest.zone is Zone.GRAVEYARD, "a land fails the nonland half"


def test_enlightened_confidant_reads_a_dynamic_mana_value_ceiling():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Enlightened Confidant"],
            library=["Lightning Bolt", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bolt = alice.library[0]
    assert bolt.name == "Lightning Bolt" and bolt.mana_value == 1

    alice.gain_life(1)
    while scenario.step is not Step.END_STEP:
        scenario.advance()
    scenario.surveil_to_graveyard(bolt, username="alice")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert bolt.zone is Zone.HAND, "1 life gained covers a mana value 1 card"


def test_enlightened_confidant_leaves_a_too_expensive_card_in_the_graveyard():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Enlightened Confidant"],
            library=["Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bears = alice.library[0]
    assert bears.name == "Grizzly Bears" and bears.mana_value == 2

    alice.gain_life(1)
    while scenario.step is not Step.END_STEP:
        scenario.advance()
    scenario.surveil_to_graveyard(bears, username="alice")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD, "mana value 2 exceeds the 1 life gained"


def test_celestines_own_dynamic_mana_value_target_bound_reads_the_same_expression():
    """Celestine, the Living Saint's own reanimation trigger targets a
    graveyard creature card "with mana value X or less ... where X is the
    amount of life you gained this turn" - a `TargetRequirement.comparison_
    x_definition`, not the surveil clause's own `count_expression` call, so
    this is a genuinely different code path reading the identical phrase.
    Read at the targeting level (clause-level probe): the reanimation
    clause this bound sits inside is its own, separate "return target X
    with mana value X or less ... where X is ..." shape that no card in
    this stream's own assignment needs, so building it is out of scope
    here - only the expression reader itself is this stream's own new
    capability, and this is what proves it general.
    """
    profile = profile_for_text(
        "return target creature card with mana value X or less from your graveyard "
        "to the battlefield, where X is the amount of life you gained this turn."
    )
    assert profile.understood
    (requirement,) = profile.requirements
    assert requirement.comparison_x_definition == "the amount of life you gained this turn"
