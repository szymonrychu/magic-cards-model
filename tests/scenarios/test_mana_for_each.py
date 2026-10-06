"""A mana ability that adds one printed symbol "for each" thing a count
reads (CR 605.1a, CR 605.3b: read as it resolves) - `ManaAbility.
for_each_expression`. The Planets' "Add {G} for each creature you control"
is covered in `test_station.py`; this is the self-counter count."""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.cost import mana_ability_most
from magic_cards_model.models import Color, Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def test_everflowing_chalice_adds_one_colorless_per_charge_counter():
    """Everflowing Chalice: "{T}: Add {C} for each charge counter on this
    artifact." - two counters, two mana."""
    scenario = Scenario().player("alice", battlefield=["Everflowing Chalice"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    chalice = scenario.find("Everflowing Chalice", Zone.BATTLEFIELD)
    scenario.game.add_counters(chalice, Counter.CHARGE, 2)

    scenario.activate(chalice, index=0)

    assert scenario.game.player("alice").mana_pool.total == 2


def test_everflowing_chalice_with_no_counters_adds_nothing():
    """CR 605.2: a mana ability is still one when the game state lets it
    produce no mana - zero counters, zero mana."""
    scenario = Scenario().player("alice", battlefield=["Everflowing Chalice"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    chalice = scenario.find("Everflowing Chalice", Zone.BATTLEFIELD)

    scenario.activate(chalice, index=0)

    assert scenario.game.player("alice").mana_pool.total == 0


# --------------------------------------------------------------------------
# The "for each <counted thing>" phrase family, read through the same
# readers every other "for each" effect uses (CR 605.3b: counted as the
# ability resolves). One real printing per wording.
# --------------------------------------------------------------------------


def test_cabal_stronghold_adds_black_for_each_basic_swamp_only():
    """Cabal Stronghold: "{3}, {T}: Add {B} for each basic Swamp you
    control." CR 205.4a's basic supertype: Watery Grave is a Swamp but not a
    basic one, and the opponent's Swamp is not one alice controls. The three
    Swamps tapped to pay {3} still count - tapped is not "not controlled"."""
    scenario = (
        Scenario()
        .player(
            "alice", battlefield=["Cabal Stronghold", "Swamp", "Swamp", "Swamp", "Watery Grave"]
        )
        .player("bob", battlefield=["Swamp"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    stronghold = scenario.find("Cabal Stronghold", Zone.BATTLEFIELD)
    swamps = scenario.untapped_sources("Swamp", "Swamp", "Swamp", username="alice")

    scenario.activate(stronghold, *swamps, index=1)

    pool = scenario.game.player("alice").mana_pool
    assert pool.floating == {Color.BLACK: 3}


def test_crypt_of_agadeem_adds_black_for_each_black_creature_card_in_graveyard():
    """Crypt of Agadeem: "{2}, {T}: Add {B} for each black creature card in
    your graveyard." A black noncreature card (Thoughtseize) and a nonblack
    creature card (Grizzly Bears) are not counted, nor is the opponent's
    graveyard."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Crypt of Agadeem", "Swamp", "Swamp"],
            graveyard=["Bloodghast", "Kheru Dreadmaw", "Thoughtseize", "Grizzly Bears"],
        )
        .player("bob", graveyard=["Bloodghast"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    crypt = scenario.find("Crypt of Agadeem", Zone.BATTLEFIELD)
    crypt.untap()
    swamps = scenario.untapped_sources("Swamp", "Swamp", username="alice")

    scenario.activate(crypt, *swamps, index=1)

    assert scenario.game.player("alice").mana_pool.floating == {Color.BLACK: 2}


def test_overgrown_battlement_adds_green_for_each_creature_with_defender():
    """Overgrown Battlement: "{T}: Add {G} for each creature you control with
    defender." Itself and a Fog Bank count; Grizzly Bears (no defender) and
    the opponent's Fog Bank do not."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Overgrown Battlement", "Fog Bank", "Grizzly Bears"])
        .player("bob", battlefield=["Fog Bank"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    battlement = scenario.find("Overgrown Battlement", Zone.BATTLEFIELD)

    scenario.activate(battlement, index=0)

    assert scenario.game.player("alice").mana_pool.floating == {Color.GREEN: 2}


def test_powerstone_shard_adds_colorless_for_each_artifact_named_powerstone_shard():
    """Powerstone Shard: "{T}: Add {C} for each artifact you control named
    Powerstone Shard." CR 201.2: by name - another artifact (Sol Ring) does
    not count, nor does the opponent's Shard."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Powerstone Shard"] * 3 + ["Sol Ring"])
        .player("bob", battlefield=["Powerstone Shard"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    shard = scenario.find("Powerstone Shard", Zone.BATTLEFIELD, "alice")

    scenario.activate(shard, index=0)

    assert scenario.game.player("alice").mana_pool.floating == {Color.COLORLESS: 3}


def test_leafkin_avenger_adds_green_for_each_creature_with_power_4_or_greater():
    """Leafkin Avenger (4/3): "{T}: Add {G} for each creature with power 4 or
    greater you control." Itself and a 6/6 Wurmcoil Engine count; Grizzly
    Bears and the opponent's Leafkin Avenger do not."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Leafkin Avenger", "Wurmcoil Engine", "Grizzly Bears"])
        .player("bob", battlefield=["Leafkin Avenger"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    avenger = scenario.find("Leafkin Avenger", Zone.BATTLEFIELD, "alice")

    scenario.activate(avenger, index=0)

    assert scenario.game.player("alice").mana_pool.floating == {Color.GREEN: 2}


def test_mage_ring_network_adds_colorless_for_each_storage_counter_removed():
    """Mage-Ring Network: "{T}, Remove any number of storage counters from this
    land: Add {C} for each storage counter removed this way." CR 107.3a: the
    number removed is announced as the ability is activated - two of three
    removed is two mana, one counter left."""
    scenario = Scenario().player("alice", battlefield=["Mage-Ring Network"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    network = scenario.find("Mage-Ring Network", Zone.BATTLEFIELD)
    scenario.game.add_counters(network, "storage", 3)

    scenario.activate(network, index=2, x_value=2)

    assert scenario.game.player("alice").mana_pool.floating == {Color.COLORLESS: 2}
    assert network.counter_count("storage") == 1


# --------------------------------------------------------------------------
# Auto-tap plans with the amount the ability makes right now (CR 601.2g,
# CR 118.3c), not one mana per source.
# --------------------------------------------------------------------------


def test_auto_tap_pays_two_generic_with_one_two_counter_chalice():
    """An Everflowing Chalice with two charge counters makes {C}{C}: a {2}
    Mind Stone is paid by it alone, both Wastes left untapped."""
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Mind Stone"], battlefield=["Everflowing Chalice", "Wastes", "Wastes"]
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    chalice = scenario.find("Everflowing Chalice", Zone.BATTLEFIELD)
    scenario.game.add_counters(chalice, Counter.CHARGE, 2)

    scenario.cast_onto_stack("Mind Stone", username="alice", auto=True)

    tapped = [s.name for s in scenario.game.permanents_controlled_by("alice") if s.tapped]
    assert tapped == ["Everflowing Chalice"]
    assert scenario.game.player("alice").mana_pool.floating == {}


def test_auto_tap_does_not_count_a_zero_counter_chalice_as_mana():
    """CR 605.2: a Chalice with no counters makes no mana, so one Wastes and
    the Chalice cannot pay {2} - refused, nothing tapped, rather than a plan
    that counts the Chalice as a mana it would never make."""
    scenario = (
        Scenario()
        .player("alice", hand=["Mind Stone"], battlefield=["Everflowing Chalice", "Wastes"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Mind Stone", "alice")
    payment = casting.begin_paying()

    with pytest.raises(ValueError):
        payment.auto_tap(scenario.game.permanents_controlled_by("alice"))

    assert not any(s.tapped for s in scenario.game.permanents_controlled_by("alice"))


def test_auto_tap_pays_three_generic_with_one_powerstone_shard_of_three():
    """Three Powerstone Shards each make {C}{C}{C}: Wurmcoil Engine's {6} is
    paid by two Shards, never all three."""
    scenario = (
        Scenario()
        .player("alice", hand=["Wurmcoil Engine"], battlefield=["Powerstone Shard"] * 3)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_onto_stack("Wurmcoil Engine", username="alice", auto=True)

    tapped = [s for s in scenario.game.permanents_controlled_by("alice") if s.tapped]
    assert len(tapped) == 2
    assert scenario.game.player("alice").mana_pool.floating == {}


def test_auto_tap_pays_green_with_one_overgrown_battlement_of_two():
    """Two Overgrown Battlements each make {G}{G}: Tarmogoyf's {1}{G} taps
    one of them, not both."""
    scenario = (
        Scenario()
        .player("alice", hand=["Tarmogoyf"], battlefield=["Overgrown Battlement"] * 2)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_onto_stack("Tarmogoyf", username="alice", auto=True)

    tapped = [s for s in scenario.game.permanents_controlled_by("alice") if s.tapped]
    assert len(tapped) == 1
    assert scenario.game.player("alice").mana_pool.floating == {}


# --------------------------------------------------------------------------
# The same family, other wordings: "on the battlefield" (anyone's),
# "an amount of {G} equal to <count>", and a "where X is" count the "for
# each" reader answers. Each printing is one the parser used to read as a
# single mana.
# --------------------------------------------------------------------------


def test_priest_of_titania_counts_every_elf_on_the_battlefield():
    """Priest of Titania: "{T}: Add {G} for each Elf on the battlefield." No
    control clause - the opponent's Llanowar Elves count too; Grizzly Bears
    (a Bear) does not."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Priest of Titania", "Llanowar Elves", "Grizzly Bears"])
        .player("bob", battlefield=["Llanowar Elves"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    priest = scenario.find("Priest of Titania", Zone.BATTLEFIELD)

    scenario.activate(priest, index=0)

    assert scenario.game.player("alice").mana_pool.floating == {Color.GREEN: 3}


def test_viridian_joiner_adds_green_equal_to_its_power():
    """Viridian Joiner: "{T}: Add an amount of {G} equal to this creature's
    power." Two +1/+1 counters make it a 3/4: three mana."""
    scenario = Scenario().player("alice", battlefield=["Viridian Joiner"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    joiner = scenario.find("Viridian Joiner", Zone.BATTLEFIELD)
    scenario.game.add_counters(joiner, Counter.PLUS_ONE, 2)

    scenario.activate(joiner, index=0)

    assert scenario.game.player("alice").mana_pool.floating == {Color.GREEN: 3}


def test_marwyn_adds_green_equal_to_her_own_named_power():
    """Marwyn, the Nurturer: "{T}: Add an amount of {G} equal to Marwyn's
    power." CR 201.5: the name means this object - one counter, 2 power, two
    mana."""
    scenario = (
        Scenario().player("alice", battlefield=["Marwyn, the Nurturer"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    marwyn = scenario.find("Marwyn, the Nurturer", Zone.BATTLEFIELD)
    scenario.game.add_counters(marwyn, Counter.PLUS_ONE, 1)

    scenario.activate(marwyn, index=0)

    assert scenario.game.player("alice").mana_pool.floating == {Color.GREEN: 2}


def test_karametras_acolyte_adds_green_equal_to_devotion_to_green():
    """Karametra's Acolyte ({3}{G}): "{T}: Add an amount of {G} equal to your
    devotion to green." CR 700.5: its own {G} and Tarmogoyf's {G} - two;
    the opponent's Llanowar Elves are not alice's devotion."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Karametra's Acolyte", "Tarmogoyf"])
        .player("bob", battlefield=["Llanowar Elves"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    acolyte = scenario.find("Karametra's Acolyte", Zone.BATTLEFIELD)

    scenario.activate(acolyte, index=0)

    assert scenario.game.player("alice").mana_pool.floating == {Color.GREEN: 2}


def test_slobad_adds_red_equal_to_the_sacrificed_artifacts_mana_value():
    """Slobad, Iron Goblin: "{T}, Sacrifice an artifact: Add an amount of {R}
    equal to the sacrificed artifact's mana value." Wurmcoil Engine is mana
    value 6: six red, and CR 106.6's "Spend this mana only to cast artifact
    spells or activate abilities of artifacts" travels with it."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Slobad, Iron Goblin", "Wurmcoil Engine"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    slobad = scenario.find("Slobad, Iron Goblin", Zone.BATTLEFIELD)
    wurmcoil = scenario.find("Wurmcoil Engine", Zone.BATTLEFIELD)

    scenario.activate(slobad, index=0, sacrificing=[wurmcoil])

    pool = scenario.game.player("alice").mana_pool
    assert pool.floating == {Color.RED: 6}
    assert sum(entry.total for entry in pool.restricted) == 6


def test_koth_minus_two_adds_red_for_each_mountain():
    """Koth of the Hammer: "-2: Add {R} for each Mountain you control." A
    loyalty ability is not a mana ability (CR 605.1a) - it resolves from the
    stack - but it adds the counted amount all the same: three Mountains,
    three red."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Koth of the Hammer", "Mountain", "Mountain", "Mountain"])
        .player("bob", battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    koth = scenario.find("Koth of the Hammer", Zone.BATTLEFIELD)

    scenario.activate(koth, index=1)
    scenario.pass_until_resolved()

    assert scenario.game.player("alice").mana_pool.floating == {Color.RED: 3}


def test_axebane_guardian_adds_x_in_any_combination_for_its_defenders():
    """Axebane Guardian: "{T}: Add X mana in any combination of colors, where
    X is the number of creatures you control with defender." Itself and a Fog
    Bank: two mana, each of its own colour."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Axebane Guardian", "Fog Bank", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    guardian = scenario.find("Axebane Guardian", Zone.BATTLEFIELD)

    scenario.activate(guardian, index=0, color=[Color.WHITE, Color.BLUE])

    assert scenario.game.player("alice").mana_pool.floating == {Color.WHITE: 1, Color.BLUE: 1}


def test_auto_tap_pays_with_one_axebane_guardian_counted_by_its_defenders():
    """Two defenders make Axebane Guardian's X two: Tarmogoyf's {1}{G} is
    paid by the Guardian alone, the Forest left untapped."""
    scenario = (
        Scenario()
        .player("alice", hand=["Tarmogoyf"], battlefield=["Axebane Guardian", "Fog Bank", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_onto_stack("Tarmogoyf", username="alice", auto=True)

    tapped = [s.name for s in scenario.game.permanents_controlled_by("alice") if s.tapped]
    assert tapped == ["Axebane Guardian"]
    assert scenario.game.player("alice").mana_pool.floating == {}


def test_auto_tap_counts_viridian_joiner_by_its_power():
    """A 3-power Viridian Joiner makes {G}{G}{G}: Tarmogoyf's {1}{G} taps it
    and no Forest."""
    scenario = (
        Scenario()
        .player("alice", hand=["Tarmogoyf"], battlefield=["Viridian Joiner", "Forest", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    joiner = scenario.find("Viridian Joiner", Zone.BATTLEFIELD)
    scenario.game.add_counters(joiner, Counter.PLUS_ONE, 2)

    scenario.cast_onto_stack("Tarmogoyf", username="alice", auto=True)

    tapped = [s.name for s in scenario.game.permanents_controlled_by("alice") if s.tapped]
    assert tapped == ["Viridian Joiner"]


def test_tapping_cabal_stronghold_into_a_payment_does_not_skip_its_mana_cost():
    """A payment that only taps Cabal Stronghold has not paid the {3} its
    "Add {B} for each basic Swamp" ability costs (CR 602.2b, CR 605.3a): the
    tap is refused, not two free black mana."""
    scenario = (
        Scenario()
        .player("alice", hand=["Mind Stone"], battlefield=["Cabal Stronghold", "Swamp", "Swamp"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    stronghold = scenario.find("Cabal Stronghold", Zone.BATTLEFIELD)
    payment = scenario.cast("Mind Stone", "alice").begin_paying()

    with pytest.raises(ValueError):
        payment.tap_for_mana(stronghold, [Color.BLACK, Color.BLACK])

    assert not stronghold.tapped
    assert payment.pool.floating == {}


def test_the_most_a_cost_dependent_count_can_make_right_now():
    """`cost.mana_ability_most`: what a seat planning a payment is told a
    count can reach before choosing how to pay for it - all three storage
    counters removed (CR 107.3a's announced X), the costliest artifact
    sacrificed, and a board count as it stands."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Mage-Ring Network",
                "Slobad, Iron Goblin",
                "Wurmcoil Engine",
                "Ornithopter",
                "Everflowing Chalice",
            ],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    game = scenario.game
    network = scenario.find("Mage-Ring Network", Zone.BATTLEFIELD)
    slobad = scenario.find("Slobad, Iron Goblin", Zone.BATTLEFIELD)
    chalice = scenario.find("Everflowing Chalice", Zone.BATTLEFIELD)
    game.add_counters(network, "storage", 3)
    game.add_counters(chalice, Counter.CHARGE, 2)

    assert mana_ability_most(game, network, 2, "alice") == 3
    assert mana_ability_most(game, slobad, 0, "alice") == 6
    assert mana_ability_most(game, chalice, 0, "alice") == 2
    assert mana_ability_most(game, network, 0, "alice") is None
