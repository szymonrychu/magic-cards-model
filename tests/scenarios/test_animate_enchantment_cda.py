"""An enchantment's activated ability that makes it a creature *and* grants
it a quoted power-and-toughness-setting ability:

- Beorn's Hospitality: "{5}{G}{G}: This enchantment becomes a Bear creature
  in addition to its other types and gains "This creature's power and
  toughness are each equal to the number of lands you control." (This effect
  doesn't end.)"
- Myth Realized (the off-set proof, not in any deck list): "{W}: Until end of
  turn, this enchantment becomes a Monk Avatar creature in addition to its
  other types and gains "This creature's power and toughness are each equal
  to the number of lore counters on it.""

Three layers, one instruction:

- layer 4 (CR 613.1d) adds the creature type and the creature subtype(s),
  keeping every type it had ("in addition to its other types");
- layer 6 (CR 613.1f) adds the quoted ability;
- the quoted ability sets power and toughness. It is *not* a
  characteristic-defining ability: CR 604.3a's criterion (4) excludes "an
  ability that an object grants to itself", so it applies in sublayer 7b
  (CR 613.4b), with the grant's own timestamp (CR 613.7a: "the timestamp of
  the effect that created the ability, whichever is later"). Being an
  ability the object has, it stops if a later layer-6 effect removes it.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.layers import Sublayer
from magic_cards_model.models import Type, Zone
from magic_cards_model.models.card_state import Counter

from .harness import Scenario

BEORN = "Beorn's Hospitality"
MYTH = "Myth Realized"


def _chars(scenario, permanent):
    return scenario.game.computed_board().of(permanent)


def _animate_beorn(scenario):
    beorn = scenario.find(BEORN, Zone.BATTLEFIELD, "alice")
    scenario.activate(beorn, *scenario.untapped_sources(*["Forest"] * 7, username="alice"))
    scenario.pass_until_resolved()
    return beorn


def test_beorns_hospitality_is_not_a_creature_until_activated():
    scenario = Scenario().player("alice", battlefield=[BEORN, *["Forest"] * 7]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    beorn = scenario.find(BEORN, Zone.BATTLEFIELD, "alice")

    assert Type.CREATURE not in _chars(scenario, beorn).types


def test_beorns_hospitality_becomes_a_bear_enchantment_creature_counting_lands():
    scenario = Scenario().player("alice", battlefield=[BEORN, *["Forest"] * 7]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    beorn = _animate_beorn(scenario)

    chars = _chars(scenario, beorn)
    assert Type.CREATURE in chars.types
    assert Type.ENCHANTMENT in chars.types  # "in addition to its other types"
    assert "Bear" in chars.subtypes
    assert (chars.power, chars.toughness) == (7, 7)
    assert (
        "This creature's power and toughness are each equal to the number of lands you control."
        in chars.abilities
    )


def test_the_granted_ability_is_a_7b_set_not_a_characteristic_defining_ability():
    """CR 604.3a (4): an ability an object grants to itself is never a CDA."""
    scenario = Scenario().player("alice", battlefield=[BEORN, *["Forest"] * 7]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    beorn = _animate_beorn(scenario)

    pt_effects = [
        effect
        for effect in scenario.game.continuous_effects.effects
        if effect.sublayer is not None and effect.layer.name == "POWER_TOUGHNESS"
    ]
    assert [effect.sublayer for effect in pt_effects] == [Sublayer.SET]
    assert not pt_effects[0].characteristic_defining
    assert _chars(scenario, beorn).power == 7


def test_beorns_power_follows_the_land_count_both_ways():
    scenario = (
        Scenario().player("alice", hand=["Forest"], battlefield=[BEORN, *["Forest"] * 7]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    beorn = _animate_beorn(scenario)
    assert _chars(scenario, beorn).power_toughness == (7, 7)

    lands = [card for card in scenario.game.battlefield if card.name == "Forest"]
    scenario.game.destroy(lands[0])
    assert _chars(scenario, beorn).power_toughness == (6, 6)


def test_beorns_effect_does_not_end_at_cleanup():
    scenario = Scenario().player("alice", battlefield=[BEORN, *["Forest"] * 7]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    beorn = _animate_beorn(scenario)

    scenario.start_at(Step.END_STEP)
    scenario.advance()  # cleanup (CR 514.2)

    chars = _chars(scenario, beorn)
    assert Type.CREATURE in chars.types
    assert chars.power_toughness == (7, 7)


def test_its_own_landfall_counter_lands_on_top_of_the_set_value():
    """7b sets, 7c adds (CR 613.4b before CR 613.4c): the next land is an
    eighth land *and* a +1/+1 counter on the Bear itself."""
    scenario = (
        Scenario().player("alice", hand=["Forest"], battlefield=[BEORN, *["Forest"] * 7]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    beorn = _animate_beorn(scenario)

    scenario.choose_trigger_targets(BEORN, [beorn])
    scenario.play_land("Forest")
    scenario.pass_until_resolved()

    assert beorn.counters[Counter.PLUS_ONE] == 1
    assert _chars(scenario, beorn).power_toughness == (9, 9)


def test_a_later_ability_removal_turns_the_granted_ability_off():
    """Dress Down ("Creatures lose all abilities.") entering later removes the
    granted ability in layer 6 before 7b applies (CR 613.6 keeps an effect
    going only once it has started to apply), so nothing sets the P/T
    of an enchantment printed with none. The layer journal records the 7b
    effect as skipped rather than applied."""
    scenario = (
        Scenario()
        .player("alice", hand=["Dress Down"], battlefield=[BEORN, *["Forest"] * 7])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    beorn = _animate_beorn(scenario)
    assert _chars(scenario, beorn).power == 7

    scenario.put_onto_battlefield("Dress Down", "alice")

    board = scenario.game.computed_board()
    assert board.of(beorn).abilities == ()
    assert board.of(beorn).power_toughness == (None, None)
    assert any("equal to the number of lands" in skipped for skipped in board.journal.skipped)


# -- Myth Realized (off-set proof) ------------------------------------------


def test_myth_realized_counts_its_own_lore_counters_until_end_of_turn():
    scenario = Scenario().player("alice", battlefield=[MYTH, "Plains"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    myth = scenario.find(MYTH, Zone.BATTLEFIELD, "alice")
    scenario.game.add_counters(myth, Counter.LORE, 3)

    scenario.activate(myth, *scenario.untapped_sources("Plains"), index=1)
    scenario.pass_until_resolved()

    chars = _chars(scenario, myth)
    assert Type.CREATURE in chars.types
    assert {"Monk", "Avatar"} <= set(chars.subtypes)
    assert chars.power_toughness == (3, 3)

    scenario.start_at(Step.END_STEP)
    scenario.advance()  # cleanup (CR 514.2)
    assert Type.CREATURE not in _chars(scenario, myth).types


def test_myth_realized_grows_with_each_new_lore_counter():
    scenario = Scenario().player("alice", battlefield=[MYTH, "Plains"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    myth = scenario.find(MYTH, Zone.BATTLEFIELD, "alice")
    scenario.game.add_counters(myth, Counter.LORE, 1)
    scenario.activate(myth, *scenario.untapped_sources("Plains"), index=1)
    scenario.pass_until_resolved()
    assert _chars(scenario, myth).power_toughness == (1, 1)

    scenario.game.add_counters(myth, Counter.LORE, 2)

    assert _chars(scenario, myth).power_toughness == (3, 3)


def test_myth_realized_with_no_lore_counters_is_a_zero_zero_and_dies():
    scenario = Scenario().player("alice", battlefield=[MYTH, "Plains"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    myth = scenario.find(MYTH, Zone.BATTLEFIELD, "alice")

    scenario.activate(myth, *scenario.untapped_sources("Plains"), index=1)
    scenario.pass_until_resolved()
    scenario.state_based_actions()

    assert myth.zone is Zone.GRAVEYARD
