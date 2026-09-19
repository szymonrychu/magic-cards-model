"""Scenario: "Target creature gets +N/+N and gains <keyword> until end of
turn." - one CR 608.2c instruction (CR 611.2), not the pump and the keyword
grant as two.

Give In to Violence ("Target creature gets +2/+2 and gains lifelink until end
of turn.") used to resolve and do nothing at all, with no record anywhere that
anything had gone unread: `split_effect_clauses` cuts the sentence in two on
its own "and" separator before any clause parser ever sees it whole, so
neither half matched `_CONTINUOUS_PUMP_OR_KEYWORD_RE`'s pure-pump or
pure-keyword shape and the whole spell fell through to nothing (CR 608.2c has
no notion of running half an instruction, but here it silently ran *none* of
it). `_merge_continuous_pump_keyword_clauses` (`machines/effects.py`) now
undoes that cut and hands the whole spell to `create_continuous_effect`, which
reads the card's own oracle text through `machines/layers.py`'s
`parsed_layer_effects` - the same parser a plain "gets +N/+N until end of
turn." already goes through.

What that parser can and cannot read is `machines/layers.py`'s own business,
not this file's: `test_parsed_layer_effects.py` already covers the shape in
isolation. This file is about the two things that only show up once a spell,
not a bare sentence, resolves:

- the pump and the keyword grant are one instruction, and both take (or both
  fail to take) together;
- a shape this pool has real cards for but `parsed_layer_effects` cannot fully
  read - more than one keyword (Aerial Maneuver) - reaches `create_
  continuous_effect` exactly like the readable ones do, and comes back as a
  `LayerNotice` instead of a card that quietly did nothing. Adamant Will's
  indestructible used to be the second example here and no longer is: the
  keyword whitelist now covers the grantable abilities no *combat* rule reads
  (CR 702.12a), so the card works.

Every CR number in this file was looked up with `knowledge_search(type="rules")`
in the session that wrote it.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.machines.keywords import is_indestructible
from magic_cards_model.machines.layers import LayerNotice
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario


def computed(scenario: Scenario):
    """The board with static abilities and stored durational effects applied."""
    return scenario.game.continuous_effects.board(scenario.game.battlefield)


# --------------------------------------------------------------------------
# Give In to Violence: the pump and the keyword grant both take, and lifelink
# actually pays off in combat, not just on the computed board.
# --------------------------------------------------------------------------


def test_give_in_to_violence_pumps_and_grants_lifelink():
    """CR 611.2, sublayer 7c (CR 613.4c) for the pump and layer 6 (CR 613.1f)
    for the keyword - both from the one spell, both up at once.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Give In to Violence"],
            battlefield=["Swamp", "Swamp", "Grizzly Bears"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    swamps = scenario.untapped_sources("Swamp", "Swamp")
    scenario.cast_and_resolve("Give In to Violence", *swamps, targets=[bears])

    board = computed(scenario)
    assert board.of(bears).power_toughness == (4, 4), "a 2/2 plus +2/+2"
    assert has_keyword(bears, Keyword.LIFELINK, scenario.game)


def test_the_granted_lifelink_actually_gains_life_in_combat():
    """CR 702.15b: "Damage dealt by a source with lifelink causes that source's
    controller ... to gain that much life (in addition to any other results
    that damage causes)."

    Grizzly Bears has no lifelink printed on it; the only way this test's life
    total moves is the grant reaching combat, the same standard
    `test_parsed_layer_effects.py` holds a granted double strike to.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Give In to Violence"],
            battlefield=["Swamp", "Swamp", "Grizzly Bears"],
        )
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    swamps = scenario.untapped_sources("Swamp", "Swamp")
    scenario.cast_and_resolve("Give In to Violence", *swamps, targets=[bears])

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    scenario.no_blocks()
    alice = scenario.player("alice")
    life_before = alice.life
    scenario.combat_damage()

    assert alice.life - life_before == 4, "the pumped 4 power comes back as 4 life"


def test_both_halves_expire_together_in_the_cleanup_step():
    """CR 514.2, CR 703.4p: "until end of turn" ends in the cleanup step, and
    it is one duration for the whole instruction (CR 611.2a), not one each.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Give In to Violence"],
            battlefield=["Swamp", "Swamp", "Grizzly Bears"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    swamps = scenario.untapped_sources("Swamp", "Swamp")
    scenario.cast_and_resolve("Give In to Violence", *swamps, targets=[bears])

    scenario.start_at(Step.END_STEP)
    assert computed(scenario).of(bears).power_toughness == (4, 4), "still up in the end step"

    scenario.advance()  # cleanup

    board = computed(scenario)
    assert board.of(bears).power_toughness == (2, 2)
    assert not has_keyword(bears, Keyword.LIFELINK, scenario.game)


# --------------------------------------------------------------------------
# A different keyword, actually changing what can block - not just what the
# computed board reports.
# --------------------------------------------------------------------------


def test_angelic_blessing_grants_flying_that_actually_evades_a_ground_blocker():
    """CR 702.9b: "A creature with flying can't be blocked except by creatures
    with flying and/or reach."

    Grizzly Bears has neither, so the only way it stops being a legal blocker
    is the grant reaching `Game.can_block`, which reads the computed board
    (`machines/combat.py`'s `has_keyword`) rather than the printing alone.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Angelic Blessing"],
            battlefield=["Plains", "Plains", "Plains", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    attacker = scenario.creature("Grizzly Bears", "alice")
    plains = scenario.untapped_sources("Plains", "Plains", "Plains")
    scenario.cast_and_resolve("Angelic Blessing", *plains, targets=[attacker])

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(attacker)

    blocker = scenario.creature("Grizzly Bears", "bob")
    assert not scenario.game.can_block(blocker, attacker)


# --------------------------------------------------------------------------
# Fail-closed: real cards sharing the shape this pool cannot fully read.
# --------------------------------------------------------------------------


def test_a_keyword_outside_the_combat_vocabulary_is_still_granted():
    """Adamant Will: "Target creature gets +2/+2 and gains indestructible
    until end of turn." (verified with `resolve_cards`).

    Indestructible (CR 702.12a: "Indestructible is a static ability") is not
    part of `machines/combat.py`'s `Keyword` vocabulary, because no combat rule
    reads it - but it is not unmodelled either: `machines/keywords.py`'s
    `is_indestructible` asks `combat.has_keyword`, which reads the *computed*
    board (CR 613.5), so a layer 6 grant (CR 613.1f) of it does exactly what
    CR 702.12b says. This sentence used to fail closed with a `LayerNotice`
    only because `machines/layers.py`'s keyword whitelist was the combat one
    verbatim; it now names the grantable keywords no combat rule reads too, so
    the pump and the grant both take, as one CR 608.2c instruction.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Adamant Will"], battlefield=["Plains", "Plains", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    plains = scenario.untapped_sources("Plains", "Plains")
    spell = scenario.cast_and_resolve("Adamant Will", *plains, targets=[bears])

    assert spell.zone is Zone.GRAVEYARD, "the spell still resolves and leaves the stack"
    board = computed(scenario)
    assert board.of(bears).power_toughness == (4, 4), "the +2/+2 half applies (CR 613.4c)"
    assert is_indestructible(bears, scenario.game), "and so does the grant (CR 613.1f)"

    assert scenario.game.continuous_effects.layer_notices == []


def test_more_than_one_granted_keyword_records_a_notice_and_applies_nothing():
    """Aerial Maneuver: "Target creature gets +1/+1 and gains flying and first
    strike until end of turn."

    Flying and first strike are each modelled on their own - `_KNOWN_KEYWORDS`
    (`machines/layers.py`) is a whitelist of exactly one bare keyword per
    grant, precisely so "flying and first strike" is not accepted and granted
    as one bogus ability string instead of two real ones (Aerial Maneuver is
    the real card that whitelist's own docstring names). The whole sentence
    fails closed the same way Adamant Will's does, even though every word in
    it is individually understood.
    """
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Aerial Maneuver"], battlefield=["Plains", "Plains", "Grizzly Bears"]
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    plains = scenario.untapped_sources("Plains", "Plains")
    spell = scenario.cast_and_resolve("Aerial Maneuver", *plains, targets=[bears])

    board = computed(scenario)
    assert board.of(bears).power_toughness == (2, 2)
    assert not has_keyword(bears, Keyword.FLYING, scenario.game)
    assert not has_keyword(bears, Keyword.FIRST_STRIKE, scenario.game)

    notices = scenario.game.continuous_effects.layer_notices
    assert notices == [
        LayerNotice(
            source_id=spell.id,
            source_name="Aerial Maneuver",
            text=card("Aerial Maneuver").oracle_text,
        )
    ]


# --------------------------------------------------------------------------
# Dauntless Onslaught (off-pool, verified with `resolve_cards`): "Up to two
# target creatures each get +2/+2 until end of turn." A plural subject
# `_CONTINUOUS_PUMP_OR_KEYWORD_RE`/`_PUMP_RE` used to refuse outright - both
# only ever recognised the singular "target creature" - so the whole spell
# was silent even at a single legal target.
# --------------------------------------------------------------------------


def test_dauntless_onslaught_pumps_both_chosen_targets():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Dauntless Onslaught"],
            battlefield=["Plains", "Plains", "Plains", "Grizzly Bears", "Watchwolf"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    wolf = scenario.creature("Watchwolf", "alice")
    plains = scenario.untapped_sources("Plains", "Plains", "Plains")
    scenario.cast_and_resolve("Dauntless Onslaught", *plains, targets=[bears, wolf])

    board = computed(scenario)
    assert board.of(bears).power_toughness == (4, 4), "a 2/2 plus +2/+2"
    assert board.of(wolf).power_toughness == (5, 5), "a 3/3 plus +2/+2"


def test_dauntless_onslaught_can_choose_only_one_of_its_up_to_two():
    """CR 115.6: "up to two" allows fewer - the untargeted creature is
    untouched."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Dauntless Onslaught"],
            battlefield=["Plains", "Plains", "Plains", "Grizzly Bears", "Watchwolf"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    wolf = scenario.creature("Watchwolf", "alice")
    plains = scenario.untapped_sources("Plains", "Plains", "Plains")
    scenario.cast_and_resolve("Dauntless Onslaught", *plains, targets=[bears])

    board = computed(scenario)
    assert board.of(bears).power_toughness == (4, 4)
    assert board.of(wolf).power_toughness == (3, 3), "never targeted, never pumped"


# --------------------------------------------------------------------------
# Xenagos, God of Revels (pool): "At the beginning of combat on your turn,
# another target creature you control gains haste and gets +X/+X until end
# of turn, where X is that creature's power." X is read once per target, off
# that creature's own (CR 613.5 computed) power at the moment the trigger
# resolves - `CardState.power` already gives the computed value.
# --------------------------------------------------------------------------


def test_xenagos_doubles_the_targets_power_and_grants_haste():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Xenagos, God of Revels", "Grizzly Bears"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.choose_trigger_targets("Xenagos, God of Revels", [bears])
    scenario.advance()
    assert scenario.step is Step.BEGINNING_OF_COMBAT
    scenario.pass_until_resolved()

    board = computed(scenario)
    assert board.of(bears).power_toughness == (4, 4), "a 2/2 plus +2/+2 (X = its own power, 2)"
    assert has_keyword(bears, Keyword.HASTE, scenario.game)
