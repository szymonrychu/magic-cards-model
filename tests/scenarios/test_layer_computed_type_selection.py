"""Selecting permanents by card type reads the *computed* board, not the
printed type line (CR 613.5, CR 613.1d).

A land animated by earthbend (CR 701.66a) is a creature. Not "acts like
one": CR 613.1d puts type-changing effects in layer 4, and CR 613.5 says the
layer system's answer is applied "continually and automatically" - so the
land's card types, for every question the game asks, are land *and* creature
(CR 205.1b's "in addition to its other types"). Its mana value stays 0: CR
202.3a, "the mana value of an object with no mana cost is 0", and a land
prints none.

That makes an animated land the sharpest possible probe for the defect this
file exists to pin down: a permanent whose printed type line and whose
computed types disagree, and which sits at the extreme end of the mana-value
scale so that any "mana value N or less" window contains it.

The engine has two ways to ask a permanent what it is, and only one of them
is right for a battlefield permanent:

- `game.characteristics_of(permanent)` - the CR 613 layer stack, run to
  completion. This is the object's characteristics.
- `CardState.types` / `.subtypes` / `.mana_value` - the printed type line of
  whichever face is up (CR 712.8d). This is CR 613.1's *starting point*, the
  "actual object" before a single continuous effect has been applied. Right
  for a card in hand or a graveyard, where no continuous effect reaches it;
  wrong for anything on the battlefield.

Wrath of the Skies ("You get X {E}, then you may pay any amount of {E}.
Destroy each artifact, creature, and enchantment with mana value less than or
equal to the amount of {E} paid this way") read the printed one, and an
animated land walked out of a sweep that should have killed it. The generic
`_parse_mass_destroy_predicate` next to it already read the computed one, so
the two mass-destroy paths in the same module disagreed about what a creature
is.

Covered here, in both directions - because getting this backwards produces a
wrong board just as confidently:

- an animated land inside a mana-value window is destroyed;
- an ordinary creature inside the same window is destroyed in the same
  resolution, so a passing test cannot be a sweep that did nothing;
- a permanent above the window survives it;
- a **plain, unanimated land is not destroyed by "destroy all creatures"** -
  the inverse. A fix that made everything a creature would pass every
  assertion above and fail this one.
- earthbend's own CR 603.7 delayed return still fires when the sweep is what
  killed the land, and returns it as the plain land CR 400.7 makes of it.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Type
from magic_cards_model.models.card_state import CardState, Counter

from .harness import PlayedScenario, Scenario


def _board_with_an_animated_land() -> tuple[PlayedScenario, CardState, CardState, CardState]:
    """alice holds Wrath of the Skies over four Plains; bob has an animated
    Forest, the Badgermole Cub that animated it, a plain untouched Forest,
    and a Hill Giant.

    Badgermole Cub is put onto the battlefield rather than cast: it is bob's
    creature and this is alice's turn, and CR 302.1's sorcery-speed timing
    would otherwise force a whole extra turn cycle into a scenario that is
    about resolution, not timing. The enters-the-battlefield trigger and its
    earthbend are the real ones either way.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Wrath of the Skies"], battlefield=["Plains"] * 4)
        .player("bob", hand=["Badgermole Cub"], battlefield=["Forest", "Forest", "Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    animated, untouched = scenario.untapped_sources("Forest", "Forest", username="bob")
    scenario.choose_trigger_targets("Badgermole Cub", [animated])
    cub = scenario.put_onto_battlefield("Badgermole Cub", "bob")
    scenario.pass_until_resolved()
    return scenario, animated, untouched, cub


def _sweep_for_two(scenario: PlayedScenario) -> None:
    """Cast Wrath of the Skies for X=2 and pay all 2 energy: the window is
    every artifact, creature, and enchantment of mana value 0, 1, or 2."""
    plains = scenario.untapped_sources(*["Plains"] * 4, username="alice")
    scenario.will_pay_energy_amount(2)
    casting = scenario.cast("Wrath of the Skies", "alice")
    casting.determine_cost(x_value=2)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *plains)
    scenario.put_on_stack(casting)
    scenario.resolve_top()


def test_the_animated_land_is_a_creature_on_the_computed_board_only():
    """The premise every other test here rests on, asserted rather than
    assumed: `characteristics_of` says creature, the printed read does not,
    and the two disagreeing is exactly the gap a consumer can fall into.
    """
    scenario, animated, untouched, _cub = _board_with_an_animated_land()

    computed = scenario.game.characteristics_of(animated)
    assert Type.CREATURE in computed.types
    assert Type.LAND in computed.types, "CR 205.1b: in addition to its other types"
    assert Type.CREATURE not in animated.types, "the printed type line is still just Land"
    assert computed.mana_value == 0, "CR 202.3a: no mana cost, so mana value 0"

    plain = scenario.game.characteristics_of(untouched)
    assert Type.CREATURE not in plain.types, "the other Forest was never animated"


def test_mass_destroy_by_mana_value_kills_an_animated_land():
    """The reported defect. A land animated into a creature has mana value 0,
    which is inside a "mana value 2 or less" window, and CR 701.8a's destroy
    applies to it like any other creature.
    """
    scenario, animated, _untouched, _cub = _board_with_an_animated_land()

    _sweep_for_two(scenario)

    assert animated.zone is Zone.GRAVEYARD, (
        "an animated land is a creature (CR 613.1d) of mana value 0 (CR 202.3a)"
    )


def test_the_same_sweep_kills_an_ordinary_creature_inside_the_window():
    """The boundary the report exercised, so that a green suite cannot be a
    sweep which quietly matched nothing: Badgermole Cub itself is {1}{G}, mana
    value 2, and dies to the same resolution.
    """
    scenario, _animated, _untouched, cub = _board_with_an_animated_land()

    _sweep_for_two(scenario)

    assert cub.zone is Zone.GRAVEYARD, "mana value 2 is inside a 2-or-less window"


def test_the_same_sweep_spares_a_creature_above_the_window():
    """Hill Giant is {3}{R}, mana value 4. Reading computed types must not
    turn into ignoring the mana-value bound.
    """
    scenario, _animated, _untouched, _cub = _board_with_an_animated_land()
    giant = scenario.creature("Hill Giant", "bob")

    _sweep_for_two(scenario)

    assert giant.zone is Zone.BATTLEFIELD, "mana value 4 is over the amount paid"


def test_the_same_sweep_spares_a_land_that_was_never_animated():
    """The inverse, in the same resolution as the kill: the untouched Forest
    is a land and nothing else, so no amount of energy paid reaches it. A
    "destroy each artifact, creature, and enchantment" clause never destroys a
    plain land, whatever its mana value.
    """
    scenario, _animated, untouched, _cub = _board_with_an_animated_land()

    _sweep_for_two(scenario)

    assert untouched.zone is Zone.BATTLEFIELD, "a plain land is not a creature"


def test_wrath_of_god_does_not_destroy_an_unanimated_land():
    """The inverse against the *generic* mass-destroy path too: "Destroy all
    creatures" must leave every land alone. This is the assertion a fix that
    over-read - one that treated every permanent as a creature - would fail,
    and it is why the animated-land tests above are not sufficient on their
    own.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Wrath of God"], battlefield=["Plains"] * 4)
        .player("bob", battlefield=["Forest", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    plains = scenario.untapped_sources(*["Plains"] * 4, username="alice")

    scenario.cast_and_resolve("Wrath of God", *plains, username="alice")

    assert bears.zone is Zone.GRAVEYARD, "the sweep did happen"
    assert forest.zone is Zone.BATTLEFIELD, "a land is not a creature"


def test_wrath_of_god_destroys_an_animated_land():
    """The same generic path, the other direction: once earthbend has made the
    Forest a creature, "Destroy all creatures" is about it too.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Wrath of God"], battlefield=["Plains"] * 4)
        .player("bob", hand=["Badgermole Cub"], battlefield=["Forest", "Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    animated, untouched = scenario.untapped_sources("Forest", "Forest", username="bob")
    scenario.choose_trigger_targets("Badgermole Cub", [animated])
    scenario.put_onto_battlefield("Badgermole Cub", "bob")
    scenario.pass_until_resolved()
    plains = scenario.untapped_sources(*["Plains"] * 4, username="alice")

    scenario.cast_and_resolve("Wrath of God", *plains, username="alice")

    assert animated.zone is Zone.GRAVEYARD
    assert untouched.zone is Zone.BATTLEFIELD


def test_earthbends_delayed_return_fires_when_the_sweep_is_what_killed_the_land():
    """CR 701.66a's third sentence - "When that land dies or is put into
    exile, return it to the battlefield tapped under your control" - is a
    delayed triggered ability (CR 603.7a), and a mass destroy is a perfectly
    ordinary way for the land to die.

    It comes back as a new object (CR 400.7), so the +1/+1 counter earthbend
    put on it is gone and it is a plain land again - the animation does not
    follow it, which is the whole reason `machines/effects.earthbend` scopes
    its continuous effects to one incarnation rather than to the land's id.

    This test exists because the fix above is what first made the land die at
    all: before it, this trigger could never fire from a sweep, and a
    correct-looking destroy that stranded the return would be a worse bug
    than the one it replaced.
    """
    scenario, animated, _untouched, _cub = _board_with_an_animated_land()

    _sweep_for_two(scenario)
    assert animated.zone is Zone.GRAVEYARD
    scenario.pass_until_resolved()

    assert animated.zone is Zone.BATTLEFIELD, "CR 701.66a returns it"
    assert animated.tapped is True, "returned tapped"
    assert animated.counters[Counter.PLUS_ONE] == 0, "CR 400.7: a new object"
    returned = scenario.game.characteristics_of(animated)
    assert Type.CREATURE not in returned.types, "the animation did not follow it back"
    assert Type.LAND in returned.types


# --------------------------------------------------------------------------
# The same defect in the other direction: a permanent that becomes a LAND.
#
# Toph, the First Metalbender prints "Nontoken artifacts you control are lands
# in addition to their other types" - CR 205.1b again, but reaching artifacts
# instead of lands, and with no earthbend in it at all. It is the sharpest
# available probe for every "each land you control" selection, because a Mox
# Amber under Toph is a land whose printed type line says only Artifact, and
# because it changes no subtype, no power and no toughness - so a test that
# passes can only be reading layer 4.
# --------------------------------------------------------------------------


def test_tophs_static_makes_an_artifact_a_land_on_the_computed_board_only():
    """The premise, asserted the same way the earthbend one is."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Toph, the First Metalbender", "Mox Amber"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mox = scenario.find("Mox Amber", Zone.BATTLEFIELD, "alice")

    computed = scenario.game.characteristics_of(mox)
    assert Type.LAND in computed.types
    assert Type.ARTIFACT in computed.types, "CR 205.1b: in addition to its other types"
    assert Type.LAND not in mox.types, "the printed type line is Legendary Artifact"


def test_scapeshift_offers_an_artifact_that_is_a_land():
    """ "Sacrifice any number of lands" asks what the permanents ARE, not what
    they print. Under Toph the Mox is among the lands offered, and it is the
    one sacrificed here - so the assertion cannot be satisfied by the Forests.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Scapeshift"],
            battlefield=[
                "Toph, the First Metalbender",
                "Mox Amber",
                "Forest",
                "Forest",
                "Forest",
                "Forest",
            ],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mox = scenario.find("Mox Amber", Zone.BATTLEFIELD, "alice")
    forests = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest")

    scenario.will_choose_cards(mox, source="Scapeshift")
    scenario.cast_and_resolve("Scapeshift", *forests, username="alice")

    asked = [d for d in scenario.questions_asked() if d.source == "Scapeshift"]
    assert asked, "Scapeshift asked which lands to sacrifice"
    assert mox.id in asked[0].cards, "an artifact that is a land is a land you may sacrifice"
    assert mox.zone is Zone.GRAVEYARD


def test_scapeshift_does_not_offer_a_plain_artifact():
    """The inverse. With no Toph on the battlefield the same Mox Amber is an
    artifact and nothing else, and "sacrifice any number of lands" must not
    reach it.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Scapeshift"],
            battlefield=["Mox Amber", "Forest", "Forest", "Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mox = scenario.find("Mox Amber", Zone.BATTLEFIELD, "alice")
    forests = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest")

    scenario.will_choose_cards(source="Scapeshift")
    scenario.cast_and_resolve("Scapeshift", *forests, username="alice")

    asked = [d for d in scenario.questions_asked() if d.source == "Scapeshift"]
    assert asked
    assert mox.id not in asked[0].cards, "a plain artifact is not a land"
    assert mox.zone is Zone.BATTLEFIELD


def test_gruul_turfs_bounce_offers_an_artifact_that_is_a_land():
    """Gruul Turf's "When this land enters, return a land you control to its
    owner's hand" is the same question with a different verb, and it is a
    forced one - the Karoo lands have no "may". Under Toph, the Mox is a legal
    answer to it.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Gruul Turf"],
            battlefield=["Toph, the First Metalbender", "Mox Amber"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mox = scenario.find("Mox Amber", Zone.BATTLEFIELD, "alice")

    scenario.will_choose_cards(mox, source="Gruul Turf")
    scenario.play_land("Gruul Turf", username="alice")
    scenario.pass_until_resolved()

    assert mox.zone is Zone.HAND, "an artifact that is a land is a land you control"


def test_grists_minus_two_can_sacrifice_an_animated_land():
    """Grist's "-2: You may sacrifice a creature." reads its candidates
    through `machines/effects._sacrifice_restriction`, which is the same
    printed-vs-computed question one more time. An earthbent land is a
    creature you control and is therefore a legal sacrifice.

    Grist is on the battlefield here, so its own "As long as Grist isn't on
    the battlefield, it's a 1/1 Insect creature" static does not apply and
    Grist itself is not among the candidates - which is what makes the
    animated Forest the only creature there is to sacrifice, and the
    assertion unambiguous.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Badgermole Cub"],
            battlefield=["Grist, the Hunger Tide", "Forest", "Forest", "Forest"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    animated, pay_one, pay_two = scenario.untapped_sources("Forest", "Forest", "Forest")
    scenario.choose_trigger_targets("Badgermole Cub", [animated])
    cub = scenario.cast_and_resolve("Badgermole Cub", pay_one, pay_two, username="alice")
    scenario.pass_until_resolved()
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.will_take_the_may(True)
    scenario.will_choose_cards(animated, source="Grist, the Hunger Tide")
    scenario.activate(
        grist := scenario.find("Grist, the Hunger Tide", Zone.BATTLEFIELD, "alice"),
        index=1,
        targets=[bears],
    )
    del grist, cub
    scenario.pass_until_resolved()

    assert animated.zone in (Zone.GRAVEYARD, Zone.BATTLEFIELD)
    asked = [
        decision
        for decision in scenario.questions_asked()
        if decision.source == "Grist, the Hunger Tide" and decision.cards
    ]
    assert asked, "Grist asked which creature to sacrifice"
    assert animated.id in asked[-1].cards, "an animated land is a creature you may sacrifice"


def test_mosswort_bridges_hideaway_counts_an_animated_lands_power():
    """ "if creatures you control have total power 10 or greater" is two
    computed questions at once: which permanents are creatures (layer 4,
    CR 613.1d) and what each one's power is (layer 7, CR 613.1g). Elder
    Gargaroth (6), Raging Goblin (1) and the Badgermole Cub that did the
    animating (2) are nine printed power between them; the animated Forest's
    one takes it to ten, and nothing else on the board can.

    Set up the same way `tests/scenarios/test_mosswort_bridge.py` does - the
    land is untapped by hand after hideaway, since the enters-tapped clause is
    not what this asserts.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Mosswort Bridge", "Badgermole Cub"],
            library=["Goblin Guide", "Opt", "Lightning Bolt", "Craterous Stomp"],
            battlefield=["Forest"] * 4 + ["Elder Gargaroth", "Raging Goblin"],
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

    animated, pay_one, pay_two, activate_with = scenario.untapped_sources(*["Forest"] * 4)
    scenario.choose_trigger_targets("Badgermole Cub", [animated])
    scenario.cast_and_resolve("Badgermole Cub", pay_one, pay_two, username="alice")
    scenario.pass_until_resolved()

    printed_total = sum(
        state.power or 0
        for state in scenario.game.permanents_controlled_by("alice")
        if state.is_creature
    )
    assert printed_total == 9, "the printed read falls one short, which is the whole point"

    scenario.activate(bridge, activate_with, index=1)
    scenario.resolve_top()

    assert goblin_guide.zone is Zone.STACK, "a 1/1 animated land is a creature with power 1"


def test_mosswort_bridge_still_refuses_when_the_animated_land_is_not_enough():
    """The inverse: strip Raging Goblin and the same board tops out at
    nine computed power, so the permission must not be granted. A fix that
    counted every land, animated or not, would pass the test above and fail
    this one.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Mosswort Bridge", "Badgermole Cub"],
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

    animated, pay_one, pay_two, activate_with = scenario.untapped_sources(*["Forest"] * 4)
    scenario.choose_trigger_targets("Badgermole Cub", [animated])
    scenario.cast_and_resolve("Badgermole Cub", pay_one, pay_two, username="alice")
    scenario.pass_until_resolved()

    scenario.activate(bridge, activate_with, index=1)
    scenario.resolve_top()

    assert scenario.game.play_permission_for(goblin_guide, "alice") is None
