"""Earthbend, CR 701.66a.

"'Earthbend N' means 'Target land you control becomes a 0/0 land creature
with haste in addition to its other types. Put N +1/+1 counters on it. When
that land dies or is put into exile, return it to the battlefield tapped
under your control.'"

Badgermole Cub is the only earthbend card in the pool ("When this creature
enters, earthbend 1."), but the keyword prints on 28 real cards, so these
tests are written against the *shape* CR 701.66a describes rather than
anything specific to Badgermole Cub - any other earthbend card would read the
same way, since `machines/effects._parse_earthbend_clause` reads the number
off the ability's own text rather than keying on the card name.

Two traps the reminder text does not warn about, both covered below:

- the land gains the creature type "in addition to its other types"
  (CR 205.1b) - it keeps every type and subtype it already had, and its own
  mana ability with it, rather than becoming *only* a creature the way
  `machines/layers.set_basic_land_type`'s CR 305.7 path would.
- it returns "tapped under your control" (CR 603.7e) - the earthbend
  ability's controller, not the land's owner, and tapped, not the blink
  idiom's untapped-under-owner default.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.machines.keywords import executes
from magic_cards_model.models import CardState, Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import PlayedScenario, Scenario


def _earthbend_a_fresh_forest(extra_battlefield: int = 2) -> tuple[PlayedScenario, CardState]:
    """Cast Badgermole Cub, earthbending one of `extra_battlefield` + 1 Forests
    that were already on the battlefield before this turn - so the earthbent
    land itself is never summoning sick, which keeps the "does it still
    function" tests separate from the "does it attack the turn it is
    animated" test below.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Badgermole Cub"],
            battlefield=["Forest"] * (extra_battlefield + 1),
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Forest"] * (extra_battlefield + 1))
    pay_sources, target_forest = sources[:extra_battlefield], sources[extra_battlefield]
    scenario.choose_trigger_targets("Badgermole Cub", [target_forest])
    scenario.cast_and_resolve("Badgermole Cub", *pay_sources)
    scenario.pass_until_resolved()
    return scenario, target_forest


def test_earthbend_is_reported_as_executed_by_the_pool_sweeper():
    """`machines/keywords.executes` used to say nothing about earthbend at
    all, which is indistinguishable from "known and ignored" to
    `scripts/sweep_pool.py`. It is a CR 701 keyword action rather than a CR
    702 keyword ability - its clause parser lives in `machines/effects.py`,
    not `machines/keywords.py` - but the sweeper still needs to be told.
    """
    assert executes("Earthbend") is True
    assert executes("earthbend") is True


def test_earthbend_makes_the_target_land_a_1_1_creature_with_haste():
    """Layer 7b sets 0/0, sublayer 7c's counter then applies on top of that -
    CR 613.4 fixes that order regardless of timestamp - so one +1/+1 counter
    on a 0/0 is unconditionally a 1/1, never a creature that is briefly a
    legal-to-die 0/0 (CR 704.3/117.5 only check state-based actions when a
    player would receive priority, never mid-resolution).
    """
    scenario, forest = _earthbend_a_fresh_forest()

    assert scenario.game.targeting_notices == []
    assert scenario.game.characteristics_of(forest).is_creature
    assert scenario.game.power_of(forest) == 1
    assert scenario.game.toughness_of(forest) == 1
    assert forest.counters[Counter.PLUS_ONE] == 1
    assert has_keyword(forest, Keyword.HASTE, scenario.game)


def test_earthbend_keeps_the_lands_own_types_and_mana_ability():
    """CR 205.1b: "in addition to its other types" - the Forest subtype and
    its intrinsic `{T}: Add {G}` (CR 305.6) both survive, and it gains no
    creature subtype of its own. This is the trap `layers.set_basic_land_type`
    (CR 305.7's "sets a land's subtype", the Blood Moon path) would fail: that
    call strips the land's own mana ability, which `layers.add_type` never
    does because it only adds a card type, not a land type.
    """
    from magic_cards_model.models.card import Type

    scenario, forest = _earthbend_a_fresh_forest()
    chars = scenario.game.characteristics_of(forest)

    assert Type.LAND in chars.types
    assert Type.CREATURE in chars.types
    assert chars.subtypes == ("Forest",)

    from magic_cards_model.models.card import Color

    scenario.activate(forest)
    # The Forest's own {G}, plus Badgermole Cub's "Whenever you tap a creature
    # for mana, add an additional {G}" - the earthbent Forest is a creature,
    # and the triggered mana ability resolves at once (CR 605.4a).
    assert scenario.player("alice").mana_pool.floating.get(Color.GREEN) == 2
    assert forest.tapped is True


def test_a_freshly_played_land_can_attack_the_turn_it_is_earthbent():
    """CR 702.10b: haste lets a creature attack even without having been
    controlled continuously since the turn began. `CardState.is_summoning_
    sick` gates on the land's *printed* types, so it misreports False here
    even though the land genuinely has not been under alice's control since
    the turn began - `Game.can_attack`/`machines.combat.attack_refusal` are
    what actually gate an attack, and they read the raw `summoning_sick` flag
    together with `has_keyword`, not that property, which is why the attack
    still correctly depends on haste rather than on this trap masking it.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Badgermole Cub", "Forest"], battlefield=["Forest", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    pay_sources = scenario.untapped_sources("Forest", "Forest")
    new_forest = scenario.play_land("Forest")
    scenario.choose_trigger_targets("Badgermole Cub", [new_forest])
    scenario.cast_and_resolve("Badgermole Cub", *pay_sources)
    scenario.pass_until_resolved()

    assert new_forest.summoning_sick is True
    # The documented trap: this property is misleading for an animated land.
    assert new_forest.is_summoning_sick() is False
    assert scenario.can_attack(new_forest) is True

    scenario.attack_with(new_forest)

    assert new_forest in scenario.attackers()


def test_earthbent_land_returns_tapped_under_its_controller_when_it_dies():
    """CR 701.66a's first half of "dies or is put into exile", and CR 603.7e:
    the delayed trigger's controller is the earthbend ability's controller
    (alice), read off `DelayedTrigger.controller` - not
    `delayed.return_subject_to_battlefield_under_owner`'s owner-and-untapped
    default, which this implementation deliberately does not reuse.
    """
    scenario, forest = _earthbend_a_fresh_forest()
    stamp_before = forest.zone_change_stamp

    scenario.game.destroy(forest)
    assert forest.zone is Zone.GRAVEYARD
    scenario.pass_until_resolved()

    assert forest.zone is Zone.BATTLEFIELD
    assert forest.tapped is True
    assert forest.controller == "alice"
    assert forest.zone_change_stamp != stamp_before


def test_earthbent_land_returns_tapped_under_its_controller_when_exiled():
    """The "or is put into exile" half - `Game.exile_permanent` now emits
    `TriggerEvent.LEAVES_BATTLEFIELD_TO_EXILE`, the event this half needed
    and that nothing emitted before.
    """
    scenario, forest = _earthbend_a_fresh_forest()

    scenario.game.exile_permanent(forest)
    assert forest.zone is Zone.EXILE
    scenario.pass_until_resolved()

    assert forest.zone is Zone.BATTLEFIELD
    assert forest.tapped is True
    assert forest.controller == "alice"


def test_the_returned_land_is_an_ordinary_land_again():
    """CR 400.7: the returned permanent is a new object. `layers.
    only_this_incarnation` is what stops earthbend's own `Duration.INDEFINITE`
    continuous effects from reapplying to it - without that scoping,
    `ContinuousEffects.end_the_turn` never clears an indefinite effect, so the
    land would silently come back animated, with its counters (CR 122.2 says
    otherwise), or untapped, forever.
    """
    scenario, forest = _earthbend_a_fresh_forest()

    scenario.game.destroy(forest)
    scenario.pass_until_resolved()

    chars = scenario.game.characteristics_of(forest)
    assert not chars.is_creature
    assert not has_keyword(forest, Keyword.HASTE, scenario.game)
    assert forest.counters[Counter.PLUS_ONE] == 0


def test_earthbent_land_does_not_return_when_bounced_to_hand():
    """CR 603.7c: "if that object is no longer in the zone it's expected to
    be in ... the ability won't affect it." A bounce is neither of the two
    events the delayed trigger watches (`DIES`, `LEAVES_BATTLEFIELD_TO_
    EXILE`), so nothing even fires - the land simply sits in hand.
    """
    scenario, forest = _earthbend_a_fresh_forest()

    scenario.game.return_to_hand(forest)

    assert forest.zone is Zone.HAND
    assert scenario.pending_triggers == []
    scenario.pass_until_resolved()
    assert forest.zone is Zone.HAND


def test_a_second_earthbend_delayed_trigger_is_dropped_once_the_first_fires():
    """CR 603.7a's one ability watching "dies or is put into exile" is
    represented as two `DelayedTrigger`s, one per event; once the land
    actually dies, the sibling watching for the exile half has nothing left
    to do and is dropped rather than left to spend itself on nothing later.
    """
    scenario, forest = _earthbend_a_fresh_forest()
    assert len(scenario.game.delayed_triggers.triggers) == 2

    scenario.game.destroy(forest)
    scenario.pass_until_resolved()

    assert scenario.game.delayed_triggers.triggers == []


def test_earthbend_with_no_legal_target_leaves_a_notice_and_does_nothing():
    """CR 608.2d's ordinary "nothing satisfies the restriction" outcome:
    alice controls no land at all, so "target land you control" has nothing
    to choose, and the trigger goes on the stack with no target and resolves
    doing nothing - recorded as a `TargetingNotice`, not silently dropped.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Badgermole Cub"])
        .player("bob", battlefield=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.put_onto_battlefield("Badgermole Cub")
    scenario.pass_until_resolved()

    bobs_forest = scenario.find("Forest", Zone.BATTLEFIELD, "bob")
    assert not scenario.game.characteristics_of(bobs_forest).is_creature
    notices = scenario.game.targeting_notices
    assert len(notices) == 1
    assert notices[0].source_name == "Badgermole Cub"


def test_rockalanche_reads_earthbend_x_where_x_is_defined_by_the_card():
    """Rockalanche (off-pool, added with `scripts/add_card.py`, verified
    against its own printed text): "Earthbend X, where X is the number of
    Forests you control." (CR 107.3f's own defined X, evaluated through
    `machines/effects.amount_expression` the way `_parse_put_counters_
    equal_to_clause`'s "equal to `<expr>`" tail already is.)

    Two things Badgermole Cub's fixed "earthbend 1" cannot prove: Rockalanche
    prints the keyword directly on a sorcery rather than on a creature's
    triggered ability, so `_parse_earthbend_clause` has to read `for_spell=
    True` the same as `for_spell=False`; and its count is a variable X, not
    a literal digit, read off the board rather than off the text.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Rockalanche"],
            battlefield=["Forest", "Forest", "Forest", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    island = scenario.find("Island", Zone.BATTLEFIELD, "alice")
    sources = scenario.untapped_sources("Forest", "Forest", "Forest")

    scenario.cast_and_resolve("Rockalanche", *sources, targets=[island])

    assert scenario.game.targeting_notices == []
    assert scenario.game.characteristics_of(island).is_creature
    # X = 3, the number of Forests alice controls - unaffected by which land
    # was actually earthbent (the Island, deliberately not one of the
    # Forests being counted).
    assert scenario.game.power_of(island) == 3
    assert scenario.game.toughness_of(island) == 3
    assert island.counters[Counter.PLUS_ONE] == 3
