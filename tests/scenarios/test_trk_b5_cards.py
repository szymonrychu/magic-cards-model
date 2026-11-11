"""Scenario: trk B5, simple cards part 1, one test per card.

CR rules cited here were looked up with `mise run rules:find` in the writing session.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.models.card import Color
from magic_cards_model.models.card_state import Counter
from magic_cards_model.models.zone import Zone
from tests.scenarios.harness import Scenario


def test_khan_despot_by_design_pings_opponents_and_their_creatures() -> None:
    """Khan's enters trigger deals 1 damage to each opponent and each creature
    your opponents control, and spares the controller's own creatures."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Khan, Despot by Design"],
            battlefield=["Mountain"] * 5 + ["Grizzly Bears"],
        )
        .player("bob", battlefield=["Grizzly Bears", "Llanowar Elves"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Mountain"] * 5)
    scenario.cast_onto_stack("Khan, Despot by Design", *sources)
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    bob = scenario.player("bob")
    assert bob.life == 19
    assert scenario.player("alice").life == 20
    assert scenario.creature("Grizzly Bears", "bob").damage == 1
    assert "Llanowar Elves" not in scenario.battlefield_names(), "1 damage kills the 1/1"
    alice_bears = scenario.creature("Grizzly Bears", "alice")
    assert alice_bears.damage == 0
    assert scenario.creature("Khan, Despot by Design", "alice").damage == 0


def test_dominion_supervisor_gives_creatures_with_counters_trample() -> None:
    """The enters trigger puts a +1/+1 counter on a target creature; "creatures
    you control with counters on them have trample" follows the counter, and
    ignores an opposing creature that also has one."""
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Dominion Supervisor"], battlefield=["Forest"] * 3 + ["Grizzly Bears"]
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ours = scenario.creature("Grizzly Bears", "alice")
    theirs = scenario.creature("Grizzly Bears", "bob")
    theirs.add_counters(Counter.PLUS_ONE, 1)
    scenario.cast_onto_stack("Dominion Supervisor", *scenario.untapped_sources(*["Forest"] * 3))
    scenario.pass_until_resolved()
    assert not has_keyword(ours, "trample", scenario.game)
    scenario.choose_trigger_targets("Dominion Supervisor", [ours])
    scenario.pass_until_resolved()
    assert ours.counter_count(Counter.PLUS_ONE) == 1
    assert has_keyword(ours, "trample", scenario.game)
    assert not has_keyword(theirs, "trample", scenario.game), "only creatures you control"
    supervisor = scenario.creature("Dominion Supervisor", "alice")
    assert not has_keyword(supervisor, "trample", scenario.game), "it has no counter itself"


def test_dr_joseph_mbenga_doubles_counters_and_protects_other_counter_creatures() -> None:
    """Counters put on your creatures are doubled, and your other creatures with
    counters have hexproof (the doctor himself does not)."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Dr. Joseph M'Benga", "Grizzly Bears", "Llanowar Elves"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    elves = scenario.creature("Llanowar Elves", "alice")
    mbenga = scenario.creature("Dr. Joseph M'Benga", "alice")
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 1, putter="alice")
    assert bears.counter_count(Counter.PLUS_ONE) == 2
    assert has_keyword(bears, "hexproof", scenario.game)
    assert not has_keyword(elves, "hexproof", scenario.game), "no counters, no hexproof"
    scenario.game.add_counters(mbenga, Counter.PLUS_ONE, 1, putter="alice")
    assert mbenga.counter_count(Counter.PLUS_ONE) == 2
    assert not has_keyword(mbenga, "hexproof", scenario.game), "other creatures only"


def test_lt_cmdr_geordi_la_forge_doubles_charge_counters_on_your_artifacts() -> None:
    """Charge counters on an artifact you control are doubled; other counter
    kinds and an opponent's artifact are not."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Lt. Cmdr. Geordi La Forge", "Romulan Bird-of-Prey", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Romulan Bird-of-Prey"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mine = scenario.find("Romulan Bird-of-Prey", Zone.BATTLEFIELD, "alice")
    theirs = scenario.find("Romulan Bird-of-Prey", Zone.BATTLEFIELD, "bob")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.add_counters(mine, "charge", 2, putter="alice")
    assert mine.counter_count("charge") == 4
    scenario.game.add_counters(theirs, "charge", 2, putter="bob")
    assert theirs.counter_count("charge") == 2
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 1, putter="alice")
    assert bears.counter_count(Counter.PLUS_ONE) == 1


def test_quark_humble_proprietor_makes_treasure_each_upkeep_that_cannot_be_sacrificed() -> None:
    """Each upkeep (either player's) Quark's controller gets a Treasure, and
    "you can't sacrifice Treasure tokens" stops the Treasure paying its own
    sacrifice cost (CR 701.21a: a player can't sacrifice what a rule forbids)."""
    scenario = (
        Scenario()
        .player("alice", library=["Forest", "Forest"], battlefield=["Quark, Humble Proprietor"])
        .player("bob", library=["Forest", "Forest"])
        .build()
    )
    scenario.advance()  # alice's upkeep
    scenario.pass_until_resolved()
    treasures = [
        c for c in scenario.game.permanents_controlled_by("alice") if c.name == "Treasure Token"
    ]
    assert len(treasures) == 1
    with pytest.raises(ValueError, match="can't be sacrificed"):
        scenario.activate(treasures[0], sacrificing=[treasures[0]])
    assert treasures[0].zone is Zone.BATTLEFIELD
    # Without Quark the very same token can be activated.
    scenario.game.exile_permanent(scenario.creature("Quark, Humble Proprietor", "alice"))
    scenario.activate(treasures[0], sacrificing=[treasures[0]], color=Color.RED)
    assert treasures[0].zone is not Zone.BATTLEFIELD


def test_deep_space_scan_draws_per_differently_named_land_and_lifts_hand_size_until_next_turn() -> (
    None
):
    """Draw X where X counts differently named lands (two Islands are one name),
    and no maximum hand size lasts through the opponent's turn only (CR 611.2a:
    "until your next turn" ends as that player's next turn begins)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Deep Space Scan"],
            library=["Forest"] * 12,
            battlefield=["Island"] * 4 + ["Forest", "Mountain"],
        )
        .player("bob", library=["Forest"] * 12)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    assert not alice.has_no_maximum_hand_size
    scenario.cast_and_resolve(
        "Deep Space Scan", *scenario.untapped_sources(*["Island"] * 4, "Forest", "Mountain")
    )
    assert len(alice.hand) == 3, "Island, Forest, Mountain are three differently named lands"
    assert alice.has_no_maximum_hand_size
    for _ in range(40):
        scenario.advance()
        if scenario.turn.turns_taken >= 2 and scenario.turn.active_player == "bob":
            break
    assert alice.has_no_maximum_hand_size, "still lifted during the opponent's turn"
    for _ in range(40):
        scenario.advance()
        if scenario.turn.active_player == "alice":
            break
    assert not alice.has_no_maximum_hand_size, "ended as alice's next turn began"


def test_branching_timeline_reveals_one_card_per_differently_named_land() -> None:
    """Four differently named lands (five Forests are one name): reveal the top
    four, permanents enter tapped, the nonpermanent goes to the bottom, the
    fifth card is untouched."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Branching Timeline"],
            library=["Grizzly Bears", "Lightning Bolt", "Forest", "Llanowar Elves", "Plains"],
            battlefield=["Forest"] * 5 + ["Island", "Mountain", "Swamp"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Forest"] * 5, "Island", "Mountain", "Swamp")
    scenario.cast_and_resolve("Branching Timeline", *sources)
    new = [c for c in scenario.game.permanents_controlled_by("alice") if c not in sources]
    assert sorted(c.name for c in new) == ["Forest", "Grizzly Bears", "Llanowar Elves"]
    assert all(c.tapped for c in new), "revealed permanents enter tapped"
    library = [c.name for c in scenario.player("alice").library]
    assert library == ["Plains", "Lightning Bolt"], (
        "unrevealed card on top, the nonpermanent on the bottom"
    )


def test_captain_pike_fullness_of_time_size_is_the_differently_named_land_count() -> None:
    """Power and toughness are each equal to the number of differently named
    lands you control (CDA, sublayer 7a): it tracks lands arriving."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Captain Pike, Fullness of Time", "Forest", "Forest", "Island"],
            hand=["Mountain"],
        )
        .player("bob", battlefield=["Swamp"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    pike = scenario.creature("Captain Pike, Fullness of Time", "alice")
    assert (pike.power, pike.toughness) == (2, 2), (
        "Forest and Island; the opponent's Swamp is not yours"
    )
    scenario.play_land("Mountain")
    assert (pike.power, pike.toughness) == (3, 3)


def test_the_traveler_power_is_the_differently_named_land_count() -> None:
    """Only power is defined by the count; toughness stays a printed 3."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["The Traveler", "Forest", "Island", "Island", "Plains"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    traveler = scenario.creature("The Traveler", "alice")
    assert (traveler.power, traveler.toughness) == (3, 3)


def test_seven_of_nine_unassimilated_grows_to_seven_nine_only_with_seven_land_names() -> None:
    """{6}{U}: base power and toughness become 7/9 (no duration: it lasts), but
    only while you control seven or more differently named lands."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Snow-Covered Plains"],
            battlefield=[
                "Seven of Nine, Unassimilated",
                "Island",
                "Island",
                "Forest",
                "Plains",
                "Mountain",
                "Swamp",
                "Wastes",
            ],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    seven = scenario.creature("Seven of Nine, Unassimilated", "alice")
    assert (seven.power, seven.toughness) == (0, 4)
    assert scenario.why_cannot_activate(seven) is not None, "six land names is not seven"
    scenario.play_land("Snow-Covered Plains")
    assert scenario.why_cannot_activate(seven) is None, "seven differently named lands"
    mana = scenario.untapped_sources(
        "Island", "Island", "Forest", "Plains", "Mountain", "Swamp", "Wastes"
    )
    scenario.activate(seven, *mana)
    scenario.pass_until_resolved()
    assert (seven.power, seven.toughness) == (7, 9)
    for _ in range(40):  # indefinite: it survives the turn ending
        scenario.advance()
        if scenario.turn.active_player == "bob":
            break
    assert (seven.power, seven.toughness) == (7, 9)


def test_seven_of_nine_unassimilated_first_main_draws_and_discards_unless_five_land_names() -> None:
    """At the beginning of your first main phase: draw a card, then discard a
    card unless you control five or more differently named lands."""

    def board(lands: list[str]) -> Scenario:
        return (
            Scenario()
            .player(
                "alice",
                library=["Grizzly Bears", "Llanowar Elves", "Forest"],
                hand=["Lightning Bolt"],
                battlefield=["Seven of Nine, Unassimilated", *lands],
            )
            .player("bob", library=["Forest"] * 5)
        )

    four = board(["Island", "Forest", "Plains", "Mountain"]).build()
    four.start_at(Step.UPKEEP)
    four.advance()  # the first player skips the draw; first main, the trigger waits
    bolt = four.find("Lightning Bolt", Zone.HAND, "alice")
    four.will_discard(bolt, username="alice")
    four.pass_until_resolved()
    assert [c.name for c in four.player("alice").hand] == ["Grizzly Bears"], "drew, then discarded"
    assert bolt.zone is Zone.GRAVEYARD

    five = board(["Island", "Forest", "Plains", "Mountain", "Swamp"]).build()
    five.start_at(Step.UPKEEP)
    five.advance()
    five.pass_until_resolved()
    assert sorted(c.name for c in five.player("alice").hand) == ["Grizzly Bears", "Lightning Bolt"]


def test_70000_light_years_from_home_exiles_a_creature_then_its_controller_fetches_a_land() -> None:
    """Exile target creature; its controller (bob, not the caster) may search
    for a basic land card and put it into their hand."""
    scenario = (
        Scenario()
        .player("alice", hand=["70,000 Light-Years from Home"], battlefield=["Plains", "Plains"])
        .player("bob", library=["Mountain", "Grizzly Bears"], battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.will_take_the_may(True, username="bob")
    scenario.cast_and_resolve(
        "70,000 Light-Years from Home",
        *scenario.untapped_sources("Plains", "Plains"),
        targets=[bears],
    )
    assert bears.zone is Zone.EXILE
    assert [c.name for c in scenario.player("bob").hand] == ["Mountain"], (
        "bob fetched, alice did not"
    )
    assert scenario.player("alice").hand == []


def test_70000_light_years_from_home_can_exile_a_spacecraft_and_the_search_is_optional() -> None:
    """A Spacecraft that is not a creature is a legal target - here alice's own,
    since the opposing one would have hexproof while it is not a creature;
    alice declines the search, so nothing reaches her hand."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["70,000 Light-Years from Home"],
            library=["Mountain"],
            battlefield=["Plains", "Plains", "Romulan Bird-of-Prey"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ship = scenario.find("Romulan Bird-of-Prey", Zone.BATTLEFIELD, "alice")
    scenario.will_take_the_may(False, username="alice")
    scenario.cast_and_resolve(
        "70,000 Light-Years from Home",
        *scenario.untapped_sources("Plains", "Plains"),
        targets=[ship],
    )
    # The ship's own "whenever you cast a noncreature spell" trigger resolves
    # first; the spell is still on the stack beneath it.
    scenario.pass_until_resolved()
    assert ship.zone is Zone.EXILE
    assert scenario.player("alice").hand == []


def test_genesis_device_fetches_a_basic_land_tapped_when_it_enters() -> None:
    """Enters: search your library for a basic land card or Planet card, put it
    onto the battlefield tapped, then shuffle."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Genesis Device"],
            library=["Grizzly Bears", "Island", "Mountain"],
            battlefield=["Forest", "Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest", "Forest")
    scenario.cast_onto_stack("Genesis Device", *sources)
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    fetched = [
        c
        for c in scenario.game.permanents_controlled_by("alice")
        if c not in sources and c.name != "Genesis Device"
    ]
    assert len(fetched) == 1 and fetched[0].name in {"Island", "Mountain"}
    assert fetched[0].tapped, "put onto the battlefield tapped"
    assert "Grizzly Bears" in [c.name for c in scenario.player("alice").library], (
        "only lands fetched"
    )


def test_genesis_device_sacrifices_lands_for_that_many_land_cards() -> None:
    """{3}{G}{G}, {T}, Sacrifice: sacrifice any number of lands you control (here
    two), then search for up to that many land cards, onto the battlefield
    tapped."""
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Island", "Mountain", "Plains", "Swamp"],
            battlefield=["Genesis Device"] + ["Forest"] * 7,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    device = scenario.find("Genesis Device", Zone.BATTLEFIELD, "alice")
    forests = scenario.untapped_sources(*["Forest"] * 7)
    scenario.will_choose_cards(*forests[:2], username="alice")
    scenario.activate(device, *forests[2:], sacrificing=[device])
    scenario.pass_until_resolved()
    names = sorted(c.name for c in scenario.game.permanents_controlled_by("alice"))
    assert device.zone is Zone.GRAVEYARD
    assert names.count("Forest") == 5
    assert len(names) == 7, "two Forests sacrificed, two land cards fetched"
    fetched = [c for c in scenario.game.permanents_controlled_by("alice") if c.name != "Forest"]
    assert all(c.tapped for c in fetched)


def test_warp_speed_fetches_a_land_untaps_entering_lands_and_cycles_cheaply() -> None:
    """Enters: search for a basic land or Planet card into hand. Lands you control
    enter untapped. {7}{U}{U}, sacrifice: draw two, costing {X} less where X is
    the number of differently named lands (here Forest, Island, Azorius
    Guildgate = three)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Warp Speed", "Azorius Guildgate", "Azorius Guildgate"],
            library=["Grizzly Bears", "Plains", "Forest", "Forest", "Forest"],
            battlefield=["Forest"] * 3 + ["Island"] * 6,
        )
        .player("bob", battlefield=["Azorius Guildgate"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    # Control: without Warp Speed, a guildgate enters tapped.
    gate = scenario.play_land("Azorius Guildgate")
    assert gate.tapped
    sources = scenario.untapped_sources("Forest", "Forest", "Forest")
    scenario.cast_onto_stack("Warp Speed", *sources)
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    hand = [c.name for c in scenario.player("alice").hand]
    assert "Plains" in hand, "the first basic land card found goes to hand"
    second_gate = scenario.put_onto_battlefield("Azorius Guildgate", "alice")
    assert not second_gate.tapped, "Warp Speed: lands you control enter untapped"
    # Forest, Island and Azorius Guildgate: three names, so {7}{U}{U} costs {4}{U}{U}.
    warp_speed = scenario.find("Warp Speed", Zone.BATTLEFIELD, "alice")
    paying = scenario.untapped_sources(*["Island"] * 6)
    hand_before = len(scenario.player("alice").hand)
    scenario.activate(warp_speed, *paying, sacrificing=[warp_speed])
    scenario.pass_until_resolved()
    assert warp_speed.zone is Zone.GRAVEYARD
    assert len(scenario.player("alice").hand) == hand_before + 2, "draw two cards"


def test_miles_obrien_returns_a_creature_on_enter_and_draws_at_end_step() -> None:
    """Enters: return up to one other target creature or artifact you control to
    hand. At each end step, if a permanent was returned to your hand from the
    battlefield this turn, draw a card."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Miles O'Brien, Transporter Ops"],
            library=["Island", "Island"],
            battlefield=["Plains"] * 3 + ["Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.will_choose_targets(bears, username="alice")
    scenario.cast_onto_stack(
        "Miles O'Brien, Transporter Ops", *scenario.untapped_sources(*["Plains"] * 3)
    )
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    assert bears.zone is Zone.HAND
    hand_before = len(scenario.player("alice").hand)
    while scenario.step is not Step.END_STEP:
        scenario.advance()
    scenario.pass_until_resolved()
    assert len(scenario.player("alice").hand) == hand_before + 1, "end step draw"


def test_miles_obrien_draws_nothing_when_nothing_was_returned() -> None:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Miles O'Brien, Transporter Ops"],
            library=["Island", "Island"],
            battlefield=["Plains"] * 3,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_onto_stack(
        "Miles O'Brien, Transporter Ops", *scenario.untapped_sources(*["Plains"] * 3)
    )
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    hand_before = len(scenario.player("alice").hand)
    while scenario.step is not Step.END_STEP:
        scenario.advance()
    scenario.pass_until_resolved()
    assert len(scenario.player("alice").hand) == hand_before


def test_shields_up_grants_hexproof_indestructible_and_a_counter_to_a_creature() -> None:
    scenario = (
        Scenario()
        .player("alice", hand=["Shields Up!"], battlefield=["Plains", "Plains", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_and_resolve(
        "Shields Up!", *scenario.untapped_sources("Plains", "Plains"), targets=[bears]
    )
    assert has_keyword(bears, "hexproof", scenario.game)
    assert has_keyword(bears, "indestructible", scenario.game)
    assert bears.counter_count(Counter.PLUS_ONE) == 1


def test_shields_up_on_a_noncreature_artifact_puts_no_counter() -> None:
    scenario = (
        Scenario()
        .player("alice", hand=["Shields Up!"], battlefield=["Plains", "Plains", "Sol Ring"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")
    scenario.cast_and_resolve(
        "Shields Up!", *scenario.untapped_sources("Plains", "Plains"), targets=[ring]
    )
    assert has_keyword(ring, "hexproof", scenario.game)
    assert has_keyword(ring, "indestructible", scenario.game)
    assert ring.counter_count(Counter.PLUS_ONE) == 0


def test_starfleet_spanner_jockey_attacks_only_after_a_noncreature_spell() -> None:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Shock"],
            battlefield=["Starfleet Spanner Jockey", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    jockey = scenario.creature("Starfleet Spanner Jockey", "alice")
    jockey.summoning_sick = False
    assert not scenario.can_attack(jockey), "defender"
    scenario.cast_and_resolve("Shock", *scenario.untapped_sources("Mountain"), targets=["bob"])
    assert scenario.can_attack(jockey), "a noncreature spell was cast this turn"


def test_culber_and_stamets_counter_mode() -> None:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Culber and Stamets, Star-Crossed"],
            battlefield=["Forest"] * 4 + ["Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.will_choose_mode("Put a +1/+1 counter on target creature.", username="alice")
    scenario.will_choose_targets(bears, username="alice")
    scenario.cast_onto_stack(
        "Culber and Stamets, Star-Crossed", *scenario.untapped_sources(*["Forest"] * 4)
    )
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    assert bears.counter_count(Counter.PLUS_ONE) == 1


def test_culber_and_stamets_mana_mode_adds_two_mana_of_one_color() -> None:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Culber and Stamets, Star-Crossed"],
            battlefield=["Forest"] * 4,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose_mode("Add two mana of any one color.", username="alice")
    scenario.will_choose("R", username="alice")
    scenario.cast_onto_stack(
        "Culber and Stamets, Star-Crossed", *scenario.untapped_sources(*["Forest"] * 4)
    )
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    assert scenario.player("alice").mana_pool.total == 2


LORE_PUMP = "Target creature gets +1/+0 until end of turn and can't be blocked this turn."
LORE_SURVEIL = "Surveil 2."


def test_lore_positronic_provocateur_pump_mode_makes_a_creature_unblockable() -> None:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lore, Positronic Provocateur"],
            battlefield=["Island"] * 3 + ["Grizzly Bears"],
        )
        .player("bob", battlefield=["Wurmcoil Engine"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    wurm = scenario.creature("Wurmcoil Engine", "bob")
    scenario.will_choose_mode(LORE_PUMP, username="alice")
    scenario.will_choose_targets(bears, username="alice")
    scenario.cast_onto_stack(
        "Lore, Positronic Provocateur", *scenario.untapped_sources(*["Island"] * 3)
    )
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    assert scenario.game.power_of(bears) == 3
    while scenario.step is not Step.DECLARE_ATTACKERS:
        scenario.advance()
    scenario.attack_with(bears)
    assert not scenario.game.can_block(wurm, bears)


def test_lore_positronic_provocateur_surveil_mode_surveils_two() -> None:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lore, Positronic Provocateur"],
            library=["Mountain", "Island", "Forest"],
            battlefield=["Island"] * 3,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    top = scenario.top_of_library(2, "alice")
    scenario.will_choose_mode(LORE_SURVEIL, username="alice")
    scenario.surveil_to_graveyard(*top, username="alice")
    scenario.cast_onto_stack(
        "Lore, Positronic Provocateur", *scenario.untapped_sources(*["Island"] * 3)
    )
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    assert all(card.zone is Zone.GRAVEYARD for card in top)
    assert len(scenario.player("alice").library) == 1


def test_the_doctor_emh_counters_a_target_then_every_creature_with_a_counter() -> None:
    """Enters: a +1/+1 counter on target creature, then one on each creature you
    control with a counter on it (the target included, so it ends with two)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["The Doctor, EMH"],
            battlefield=["Forest"] * 5 + ["Grizzly Bears", "Llanowar Elves"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    elves = scenario.creature("Llanowar Elves", "alice")
    elves.add_counters(Counter.PLUS_ONE, 1)
    scenario.will_choose_targets(bears, username="alice")
    scenario.cast_onto_stack("The Doctor, EMH", *scenario.untapped_sources(*["Forest"] * 5))
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    assert bears.counter_count(Counter.PLUS_ONE) == 2
    assert elves.counter_count(Counter.PLUS_ONE) == 2
    assert scenario.creature("The Doctor, EMH", "alice").counter_count(Counter.PLUS_ONE) == 0


WESLEY_UNBLOCKABLE = "Target creature can't be blocked this turn."
WESLEY_LOOT = "Target player draws two cards, then discards two cards."
WESLEY_BOUNCE = "Return target creature with mana value 2 or less to its owner's hand."


def test_wesley_crusher_starfleet_cadet_chooses_two_modes_on_enter() -> None:
    """Flash; enters: choose two. Here the unblockable mode and the bounce mode
    (mana value 2 or less): both resolve, and a creature above the cap is not
    a legal bounce target."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Wesley Crusher, Starfleet Cadet"],
            battlefield=["Island"] * 4 + ["Grizzly Bears"],
        )
        .player("bob", battlefield=["Wurmcoil Engine", "Llanowar Elves"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    elves = scenario.creature("Llanowar Elves", "bob")
    scenario.will_choose_mode(WESLEY_UNBLOCKABLE, username="alice")
    scenario.will_choose_mode(WESLEY_BOUNCE, username="alice")
    scenario.will_choose_targets(bears, username="alice")
    scenario.will_choose_targets(elves, username="alice")
    scenario.cast_onto_stack(
        "Wesley Crusher, Starfleet Cadet", *scenario.untapped_sources(*["Island"] * 4)
    )
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    assert elves.zone is Zone.HAND
    assert has_keyword(
        scenario.creature("Wesley Crusher, Starfleet Cadet", "alice"), "flash", scenario.game
    )
    wurm = scenario.creature("Wurmcoil Engine", "bob")
    while scenario.step is not Step.DECLARE_ATTACKERS:
        scenario.advance()
    scenario.attack_with(bears)
    assert not scenario.game.can_block(wurm, bears), "unblockable mode resolved"


def test_wesley_crusher_starfleet_cadet_loots_two_with_the_draw_mode() -> None:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Wesley Crusher, Starfleet Cadet"],
            library=["Island", "Mountain", "Forest"],
            battlefield=["Island"] * 4 + ["Grizzly Bears"],
        )
        .player("bob", battlefield=["Llanowar Elves"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.will_choose_mode(WESLEY_LOOT, username="alice")
    scenario.will_choose_mode(WESLEY_UNBLOCKABLE, username="alice")
    scenario.will_choose_targets("alice", username="alice")
    scenario.will_choose_targets(bears, username="alice")
    scenario.cast_onto_stack(
        "Wesley Crusher, Starfleet Cadet", *scenario.untapped_sources(*["Island"] * 4)
    )
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    drawn = [card for card in scenario.player("alice").graveyard]
    assert len(drawn) == 2, "drew two, discarded two"
    assert scenario.player("alice").hand == []


VGER_LOOK = "Look at target opponent's hand, then draw a card."
VGER_SHRINK = "Creatures your opponents control get -1/-0 until your next turn."


def test_vger_the_intruder_enters_and_looks_at_a_hand_then_draws() -> None:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["V'Ger, the Intruder"],
            library=["Forest", "Island"],
            battlefield=["Island"] * 7,
        )
        .player("bob", hand=["Lightning Bolt"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose_mode(VGER_LOOK, username="alice")
    scenario.will_choose_targets("bob", username="alice")
    scenario.cast_onto_stack("V'Ger, the Intruder", *scenario.untapped_sources(*["Island"] * 7))
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    assert [c.name for c in scenario.player("alice").hand] == ["Forest"]


def test_vger_the_intruder_shrinks_opposing_creatures_when_it_attacks() -> None:
    scenario = (
        Scenario()
        .player("alice", battlefield=["V'Ger, the Intruder"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vger = scenario.creature("V'Ger, the Intruder", "alice")
    bob_bears = scenario.creature("Grizzly Bears", "bob")
    scenario.will_choose_mode(VGER_SHRINK, username="alice")
    while scenario.step is not Step.DECLARE_ATTACKERS:
        scenario.advance()
    scenario.attack_with(vger)
    scenario.pass_until_resolved()
    assert scenario.game.power_of(bob_bears) == 1
    assert scenario.game.power_of(vger) == 5, "only opponents' creatures shrink"


def _cast_rules_of_acquisition(scenario, mode, targets):
    casting = scenario.cast("Rules of Acquisition", username="alice")
    casting.choose_modes([mode])
    casting.choose_targets(targets)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*["Island"] * 5, username="alice"))
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()


def test_rules_of_acquisition_third_rule_steals_a_permanent_and_its_old_owner_draws_three() -> None:
    scenario = (
        Scenario()
        .player("alice", hand=["Rules of Acquisition"], battlefield=["Island"] * 5)
        .player("bob", library=["Forest"] * 4, battlefield=["Grizzly Bears", "Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    _cast_rules_of_acquisition(scenario, 1, [bears])
    assert scenario.game.controller_of(bears).username == "alice"
    assert len(scenario.player("bob").hand) == 3, "that opponent draws three cards"
    assert scenario.player("alice").hand == []


def test_rules_of_acquisition_third_rule_cannot_target_a_land() -> None:
    scenario = (
        Scenario()
        .player("alice", hand=["Rules of Acquisition"], battlefield=["Island"] * 5)
        .player("bob", battlefield=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "bob")
    casting = scenario.cast("Rules of Acquisition", username="alice")
    casting.choose_modes([1])
    with pytest.raises(ValueError):
        casting.choose_targets([forest])


def test_rules_of_acquisition_ninety_eighth_rule_gives_a_permanent_and_draws_three() -> None:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Rules of Acquisition"],
            library=["Island"] * 4,
            battlefield=["Island"] * 5 + ["Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast_rules_of_acquisition(scenario, 2, ["bob", bears])
    assert scenario.game.controller_of(bears).username == "bob"
    assert len(scenario.player("alice").hand) == 3, "if they do, you draw three cards"


KOBAYASHI_HAIL = (
    "Hail \u2014 Return up to one target creature an opponent controls with mana value 3 "
    "or less to its owner's hand."
)
KOBAYASHI_SENSORS = "Sensors \u2014 Draw two cards."


KOBAYASHI_TRANSPORT = "Transport \u2014 Create two 1/1 red Officer creature tokens."
KOBAYASHI_ABANDON = "Abandon Ship \u2014 You lose the game."


def _kobayashi_board() -> Scenario:
    return (
        Scenario()
        .player("alice", library=["Island"] * 8, battlefield=["Kobayashi Maru Scenario"])
        .player("bob", library=["Island"] * 8, battlefield=["Grizzly Bears"])
    )


def test_kobayashi_maru_scenario_sensors_draws_two_and_is_not_offered_again() -> None:
    scenario = _kobayashi_board().build()
    scenario.will_choose_mode(KOBAYASHI_SENSORS, username="alice")
    scenario.advance()  # alice's upkeep
    scenario.pass_until_resolved()
    assert len(scenario.player("alice").hand) == 2
    maru = scenario.find("Kobayashi Maru Scenario", Zone.BATTLEFIELD, "alice")
    assert KOBAYASHI_SENSORS in maru.chosen_modal_options, "a chosen mode is used up"
    assert KOBAYASHI_HAIL not in maru.chosen_modal_options


def test_kobayashi_maru_scenario_hail_bounces_a_cheap_opposing_creature() -> None:
    scenario = _kobayashi_board().build()
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.will_choose_mode(KOBAYASHI_HAIL, username="alice")
    scenario.will_choose_targets(bears, username="alice")
    scenario.advance()
    scenario.pass_until_resolved()
    assert bears.zone is Zone.HAND


def test_kobayashi_maru_scenario_transport_makes_two_officers() -> None:
    scenario = _kobayashi_board().build()
    scenario.will_choose_mode(KOBAYASHI_TRANSPORT, username="alice")
    scenario.advance()
    scenario.pass_until_resolved()
    officers = [c for c in scenario.game.permanents_controlled_by("alice") if "Officer" in c.name]
    assert len(officers) == 2


def test_kobayashi_maru_scenario_abandon_ship_loses_the_game() -> None:
    scenario = _kobayashi_board().build()
    scenario.will_choose_mode(KOBAYASHI_ABANDON, username="alice")
    scenario.advance()
    scenario.pass_until_resolved()
    assert scenario.game.winner == "bob"


def test_georgiou_terran_emperor_survives_zero_life_and_makes_ten_officers() -> None:
    """At your end step: lose 3 life, draw a card; then if life is 0 or less,
    ten 1/1 red Officer tokens. At exactly 0 life she keeps the game alive."""
    scenario = (
        Scenario()
        .player(
            "alice", life=3, library=["Island", "Island"], battlefield=["Georgiou, Terran Emperor"]
        )
        .player("bob", library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    while scenario.step is not Step.END_STEP:
        scenario.advance()
    scenario.pass_until_resolved()
    alice = scenario.player("alice")
    assert alice.life == 0
    assert scenario.game.winner is None, "0 life without losing"
    officers = [c for c in scenario.game.permanents_controlled_by("alice") if "Officer" in c.name]
    assert len(officers) == 10
    assert len(alice.hand) == 1


def test_georgiou_terran_emperor_makes_no_officers_while_life_stays_positive() -> None:
    scenario = (
        Scenario()
        .player("alice", life=20, library=["Island"] * 2, battlefield=["Georgiou, Terran Emperor"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    while scenario.step is not Step.END_STEP:
        scenario.advance()
    scenario.pass_until_resolved()
    assert scenario.player("alice").life == 17
    assert not [c for c in scenario.game.permanents_controlled_by("alice") if "Officer" in c.name]


def test_gul_dukat_colonial_prefect_doubles_the_life_opponents_lost_and_drains_it() -> None:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Shock"],
            battlefield=["Gul Dukat, Colonial Prefect", "Mountain"],
        )
        .player("bob", library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Shock", *scenario.untapped_sources("Mountain"), targets=["bob"])
    assert scenario.player("bob").life == 18
    while scenario.step is not Step.END_STEP:
        scenario.advance()
    scenario.pass_until_resolved()
    assert scenario.player("bob").life == 16, "lost 2 more, equal to the 2 lost this turn"
    assert scenario.player("alice").life == 22, "gains the life lost this way"


def test_gowron_eager_for_battle_grows_and_draws_only_for_a_sacrificed_klingon() -> None:
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Island", "Island"],
            battlefield=[
                "Gowron, Eager for Battle",
                "Worf, Intelligence Contractor",
                "Grizzly Bears",
            ],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gowron = scenario.creature("Gowron, Eager for Battle", "alice")
    worf = scenario.creature("Worf, Intelligence Contractor", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.activate(gowron, sacrificing=[bears])
    scenario.pass_until_resolved()  # Gowron's own "another creature dies" trigger
    scenario.pass_until_resolved()
    assert has_keyword(gowron, "trample", scenario.game)
    assert scenario.player("alice").hand == [], "a Bear is not a Klingon"
    scenario.activate(gowron, sacrificing=[worf])
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    assert [c.name for c in scenario.player("alice").hand] == ["Island"]
    assert scenario.player("alice").life == 19, "lose 1 life for the Klingon"
    assert gowron.counter_count(Counter.PLUS_ONE) == 2, "one per other creature that died"


def test_sylvia_tilly_joy_of_discovery_pays_one_and_exiles_a_card_for_a_counter() -> None:
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Island"] * 3,
            graveyard=["Mountain"],
            battlefield=["Sylvia Tilly, Joy of Discovery", "Forest", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tilly = scenario.creature("Sylvia Tilly, Joy of Discovery", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    mountain = scenario.find("Mountain", Zone.GRAVEYARD, "alice")
    scenario.will_take_the_may(True, username="alice")
    scenario.will_choose_cards(mountain, username="alice")
    scenario.will_choose_targets(bears, username="alice")
    scenario.advance()  # beginning of combat
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    assert mountain.zone is Zone.EXILE
    assert scenario.find("Forest", Zone.BATTLEFIELD, "alice").tapped, "paid {1}"
    assert bears.counter_count(Counter.PLUS_ONE) == 1
    assert tilly.counter_count(Counter.PLUS_ONE) == 0


def test_jadzia_dax_living_legacy_grows_and_adds_green_equal_to_her_counters() -> None:
    scenario = (
        Scenario().player("alice", battlefield=["Jadzia Dax, Living Legacy"]).player("bob").build()
    )
    jadzia = scenario.creature("Jadzia Dax, Living Legacy", "alice")
    while scenario.step is not Step.PRECOMBAT_MAIN:
        scenario.advance()
    scenario.pass_until_resolved()
    assert jadzia.counter_count(Counter.PLUS_ONE) == 1
    assert scenario.player("alice").mana_pool.total == 1


def test_jadzia_dax_living_legacy_transfer_symbiont_counters_a_creature_from_hand() -> None:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Jadzia Dax, Living Legacy"],
            battlefield=["Forest"] * 3 + ["Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    jadzia = scenario.find("Jadzia Dax, Living Legacy", Zone.HAND, "alice")
    scenario.activate(
        jadzia,
        *scenario.untapped_sources(*["Forest"] * 3),
        discarding=[jadzia],
        targets=[bears],
    )
    scenario.pass_until_resolved()
    assert bears.counter_count(Counter.PLUS_ONE) == 2
    assert jadzia.zone is Zone.GRAVEYARD


def _station_romulan(scenario, spacecraft, tapped, username="alice"):
    from magic_cards_model.machines.keywords import station_activation

    activation = station_activation(scenario.game, spacecraft, tapped, username)
    activation.begin_paying()
    activation.payment.pay()
    activation.activate()
    activation.resolve()


def test_romulan_bird_of_prey_cloaks_and_charges_until_it_becomes_a_creature() -> None:
    """Not a creature: hexproof, and each noncreature spell you cast puts two
    charge counters on it. Stationed to 8, it is a 4/4 flying creature: no
    hexproof, and no more counters."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Shock", "Shock"],
            battlefield=[
                "Romulan Bird-of-Prey",
                "Mountain",
                "Mountain",
                "Craw Wurm",
                "Grizzly Bears",
            ],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ship = scenario.find("Romulan Bird-of-Prey", Zone.BATTLEFIELD, "alice")
    assert has_keyword(ship, "hexproof", scenario.game), "cloaked while not a creature"
    mountains = scenario.untapped_sources("Mountain", "Mountain")
    scenario.cast_and_resolve("Shock", mountains[0], targets=["bob"])
    scenario.pass_until_resolved()
    assert ship.counter_count(Counter.CHARGE) == 2, "a noncreature spell: two charge counters"
    _station_romulan(scenario, ship, scenario.creature("Craw Wurm", "alice"))
    assert ship.counter_count(Counter.CHARGE) == 8
    assert scenario.game.characteristics_of(ship).is_creature
    assert not has_keyword(ship, "hexproof", scenario.game), "a creature is not cloaked"
    assert has_keyword(ship, "flying", scenario.game)
    scenario.cast_and_resolve("Shock", mountains[1], targets=["bob"])
    scenario.pass_until_resolved()
    assert ship.counter_count(Counter.CHARGE) == 8, "no counters while it is a creature"


def test_erica_ortegas_plucky_pilot_puts_a_land_in_when_tapped_and_returns_one_at_end_step() -> (
    None
):
    """Haste; whenever she becomes tapped (here by attacking) you may put a
    land card from hand onto the battlefield; if you do, return a land you
    control to hand at the beginning of the next end step."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Forest"],
            battlefield=["Erica Ortegas, Plucky Pilot", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    erica = scenario.creature("Erica Ortegas, Plucky Pilot", "alice")
    forest = scenario.find("Forest", Zone.HAND, "alice")
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "alice")
    scenario.will_take_the_may(True, username="alice")
    scenario.will_choose_cards(forest, username="alice")
    while scenario.step is not Step.DECLARE_ATTACKERS:
        scenario.advance()
    scenario.attack_with(erica)
    scenario.pass_until_resolved()
    assert forest.zone is Zone.BATTLEFIELD, "put onto the battlefield from hand"
    scenario.will_choose_cards(forest, username="alice")
    while scenario.step is not Step.END_STEP:
        scenario.advance()
    scenario.pass_until_resolved()
    assert forest.zone is Zone.HAND, "a land you control returned at the next end step"
    assert mountain.zone is Zone.BATTLEFIELD


def test_erica_ortegas_plucky_pilot_returns_nothing_when_the_may_is_declined() -> None:
    scenario = (
        Scenario()
        .player("alice", hand=["Forest"], battlefield=["Erica Ortegas, Plucky Pilot", "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    erica = scenario.creature("Erica Ortegas, Plucky Pilot", "alice")
    scenario.will_take_the_may(False, username="alice")
    while scenario.step is not Step.DECLARE_ATTACKERS:
        scenario.advance()
    scenario.attack_with(erica)
    scenario.pass_until_resolved()
    assert [c.name for c in scenario.player("alice").hand] == ["Forest"]
    while scenario.step is not Step.END_STEP:
        scenario.advance()
    scenario.pass_until_resolved()
    assert scenario.find("Mountain", Zone.BATTLEFIELD, "alice").zone is Zone.BATTLEFIELD


def test_worf_intelligence_contractor_borrows_a_cheap_creature_until_end_of_turn() -> None:
    """Enters: for each opponent, gain control of up to one target creature that
    player controls with mana value 3 or less until end of turn, untap it, and
    until end of turn it is a Warrior in addition and has haste."""
    scenario = (
        Scenario()
        .player("alice", hand=["Worf, Intelligence Contractor"], battlefield=["Mountain"] * 3)
        .player("bob", battlefield=["Grizzly Bears", "Wurmcoil Engine"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    bears.tapped = True
    wurm = scenario.creature("Wurmcoil Engine", "bob")
    scenario.will_choose_targets(bears, username="alice")
    scenario.cast_onto_stack(
        "Worf, Intelligence Contractor",
        *scenario.untapped_sources("Mountain", "Mountain", "Mountain"),
    )
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    assert scenario.game.controller_of(bears).username == "alice"
    assert not bears.tapped, "untapped"
    assert "Warrior" in scenario.game.characteristics_of(bears).subtypes
    assert "Bear" in scenario.game.characteristics_of(bears).subtypes, "in addition to its types"
    assert has_keyword(bears, "haste", scenario.game)
    assert scenario.game.controller_of(wurm).username == "bob", "mana value 6 is out of range"
    while scenario.step is not Step.CLEANUP:
        scenario.advance()
    scenario.advance()
    assert scenario.game.controller_of(bears).username == "bob", "control ends with the turn"


def test_nog_ambitious_cadet_levels_from_rogue_to_scout_to_officer() -> None:
    """{1}: if he is a Rogue he becomes a Ferengi Scout 3/4 that surveils 2
    whenever he becomes tapped. {3}: if he is a Scout he becomes a Ferengi
    Officer and may play lands from the graveyard and an additional land."""
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Island"] * 4,
            graveyard=["Forest"],
            battlefield=["Nog, Ambitious Cadet"] + ["Forest"] * 12,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    nog = scenario.creature("Nog, Ambitious Cadet", "alice")
    forests = scenario.untapped_sources(*["Forest"] * 12)
    chars = scenario.game.characteristics_of(nog)
    assert "Rogue" in chars.subtypes and scenario.game.power_of(nog) == 2
    # {3} does nothing while he is still a Rogue.
    scenario.activate(nog, *forests[:3], index=1)
    scenario.pass_until_resolved()
    assert "Officer" not in scenario.game.characteristics_of(nog).subtypes
    scenario.activate(nog, forests[3])
    scenario.pass_until_resolved()
    chars = scenario.game.characteristics_of(nog)
    assert "Scout" in chars.subtypes and "Rogue" not in chars.subtypes
    assert "Ferengi" in chars.subtypes
    assert (scenario.game.power_of(nog), scenario.game.toughness_of(nog)) == (3, 4)
    # {1} again does nothing: he is no longer a Rogue.
    scenario.activate(nog, forests[4])
    scenario.pass_until_resolved()
    assert (scenario.game.power_of(nog), scenario.game.toughness_of(nog)) == (3, 4)
    # The granted trigger: becoming tapped surveils 2.
    top = scenario.top_of_library(2, "alice")
    scenario.surveil_to_graveyard(*top, username="alice")
    while scenario.step is not Step.DECLARE_ATTACKERS:
        scenario.advance()
    scenario.attack_with(nog)
    scenario.pass_until_resolved()
    assert all(card.zone is Zone.GRAVEYARD for card in top), (
        "Whenever Nog becomes tapped, surveil 2"
    )
    # {3}: now a Scout, he becomes an Officer.
    scenario.activate(nog, *forests[5:8], index=1)
    scenario.pass_until_resolved()
    chars = scenario.game.characteristics_of(nog)
    assert "Officer" in chars.subtypes and "Scout" not in chars.subtypes
    assert scenario.game.power_of(nog) == 3, "base 3/4 persists"
    # The Officer plays lands from the graveyard, and a second land each turn.
    graveyard_forest = scenario.find("Forest", Zone.GRAVEYARD, "alice")
    while scenario.step is not Step.POSTCOMBAT_MAIN:
        scenario.advance()
    played = scenario.play_land("Forest", "alice", from_zone=Zone.GRAVEYARD)
    assert played is graveyard_forest and played.zone is Zone.BATTLEFIELD


def test_worf_honor_bound_warrior_doubles_his_power_only_when_the_team_has_eight_power() -> None:
    """Whenever you attack while creatures you control have total power 8 or
    greater, double Worf's power until end of turn."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Worf, Honor-Bound Warrior", "Craw Wurm", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    worf = scenario.creature("Worf, Honor-Bound Warrior", "alice")
    wurm = scenario.creature("Craw Wurm", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    assert scenario.game.power_of(worf) == 1
    while scenario.step is not Step.DECLARE_ATTACKERS:
        scenario.advance()
    scenario.attack_with(wurm)
    scenario.pass_until_resolved()
    assert scenario.game.power_of(worf) == 2, "total power 1 + 6 + 2 = 9 is 8 or greater: doubled"
    assert bears.damage == 0


def test_worf_honor_bound_warrior_does_not_double_below_eight_total_power() -> None:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Worf, Honor-Bound Warrior", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    worf = scenario.creature("Worf, Honor-Bound Warrior", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    while scenario.step is not Step.DECLARE_ATTACKERS:
        scenario.advance()
    scenario.attack_with(bears)
    scenario.pass_until_resolved()
    assert scenario.game.power_of(worf) == 1


def test_worf_honor_bound_warrior_taps_two_to_grow_at_sorcery_speed() -> None:
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Worf, Honor-Bound Warrior", "Grizzly Bears", "Llanowar Elves"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    worf = scenario.creature("Worf, Honor-Bound Warrior", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    elves = scenario.creature("Llanowar Elves", "alice")
    scenario.activate(worf, tapping_for_cost=[bears, elves])
    scenario.pass_until_resolved()
    assert worf.counter_count(Counter.PLUS_ONE) == 1
    assert bears.tapped and elves.tapped
