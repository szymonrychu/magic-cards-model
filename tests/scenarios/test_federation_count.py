"""Scenario: the Federation count, "the number of creature types among non-Borg
creatures you control" (trk).

CR 207.2c: "federation" is an ability word, no rules meaning of its own. The
count is CR 205.3m's creature types among the controller's creatures, read
off the computed board: CR 702.73a makes a changeling every creature type
(Borg included, so "non-Borg" leaves it out), duplicates count once and no
creatures count 0.

The reader is proven on six differently worded trk cards that consume the
count in six positions: an ETB damage amount (Saavik), a look-at-the-top-X
(Hoshi Sato), a copy count (Infinite Diversity), an activated pump (Captain
Jonathan Archer), a "for every five" draw with a threshold rider (Sarek) and
a mana ability amount (Starfleet Academy). No non-trk printing legal in
Modern prints the phrase (Scryfall `o:"creature types among" legal:modern`,
2026-11-11).

CR rules cited here were looked up with `mise run rules:find` in the writing session.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.effects.amounts import creature_types_among
from magic_cards_model.models.card import Color
from magic_cards_model.models.card_state import Counter
from magic_cards_model.models.zone import Zone
from tests.scenarios.harness import Scenario


def _count(scenario, username: str = "alice") -> int:
    return creature_types_among(scenario.game, username, "Borg")


# -- corner cases ------------------------------------------------------------


def test_duplicate_creature_types_count_once() -> None:
    """Two Humans and two Druids still count Human and Druid once each."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Thalia, Guardian of Thraben", "Llanowar Elves", "Llanowar Elves"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert _count(scenario) == 4  # Human, Soldier, Elf, Druid


def test_no_creatures_count_zero() -> None:
    """CR 107.2's nothing-to-count is 0; lands are not creatures."""
    scenario = Scenario().player("alice", battlefield=["Forest"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert _count(scenario) == 0


def test_a_borg_creature_is_left_out() -> None:
    """Tenacious Drone is a Borg; "non-Borg" leaves out every type it has."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Tenacious Drone", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert _count(scenario) == 1  # Bear only


def test_a_changeling_is_borg_and_is_left_out() -> None:
    """CR 702.73a: a changeling is every creature type, Borg among them, so it
    is not a non-Borg creature and adds nothing - not every type."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Changeling Outcast", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    outcast = scenario.creature("Changeling Outcast", "alice")
    assert "Borg" in scenario.game.characteristics_of(outcast).subtypes
    assert _count(scenario) == 1


def test_only_creatures_you_control_count() -> None:
    """An opponent's creatures add nothing to your count."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears"])
        .player("bob", battlefield=["Llanowar Elves", "Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert _count(scenario) == 1
    assert _count(scenario, "bob") == 3


def test_a_token_counts() -> None:
    """Captain Archer's Porthos token is a Dog, and tokens are creatures you
    control like any other (CR 111.1)."""
    scenario = (
        Scenario()
        .player("alice", hand=["Captain Jonathan Archer"], battlefield=["Forest"] * 3)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_onto_stack("Captain Jonathan Archer", *scenario.untapped_sources(*["Forest"] * 3))
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    porthos = scenario.find("Porthos", Zone.BATTLEFIELD, "alice")
    assert porthos.zone is Zone.BATTLEFIELD
    assert _count(scenario) == 3  # Human, Officer, Dog


# -- one test per card ---------------------------------------------------------


def test_saavik_stoic_student_flashes_in_and_shoots_an_attacker() -> None:
    """Flash lets Saavik enter during bob's combat; her ETB deals X damage to
    target attacking creature an opponent controls, X = Vulcan, Advisor, Elf,
    Druid = 4, enough to kill a 3/3 Hill Giant."""
    scenario = (
        Scenario()
        .player("bob", battlefield=["Hill Giant"])
        .player(
            "alice",
            hand=["Saavik, Stoic Student"],
            battlefield=["Plains"] * 5 + ["Llanowar Elves"],
        )
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    giant = scenario.creature("Hill Giant", "bob")
    scenario.attack_with(giant, defending="alice")
    scenario.pass_priority("bob")
    scenario.cast_onto_stack(
        "Saavik, Stoic Student",
        *scenario.untapped_sources(*["Plains"] * 5, username="alice"),
        username="alice",
    )
    scenario.pass_until_resolved()
    scenario.choose_trigger_targets("Saavik, Stoic Student", [giant])
    scenario.pass_until_resolved()
    assert scenario.creature("Saavik, Stoic Student", "alice").zone is Zone.BATTLEFIELD
    assert giant.zone is Zone.GRAVEYARD


def test_hoshi_sato_exolinguist_looks_at_x_and_keeps_one() -> None:
    """X = Human, Scientist, Bear = 3: three cards seen, one to hand, two to the
    bottom; the fourth card stays on top."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Hoshi Sato, Exolinguist"],
            library=["Opt", "Shock", "Lightning Bolt", "Mountain"],
            battlefield=["Island"] * 5 + ["Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    shock = scenario.find("Shock", Zone.LIBRARY, "alice")
    scenario.cast_onto_stack("Hoshi Sato, Exolinguist", *scenario.untapped_sources(*["Island"] * 5))
    scenario.pass_until_resolved()
    scenario.scry_bottoming(shock)  # the look-and-split question: `moved` goes to hand
    scenario.pass_until_resolved()
    alice = scenario.player("alice")
    assert shock.zone is Zone.HAND
    assert alice.library[0].name == "Mountain"
    assert {card.name for card in alice.library[1:]} == {"Opt", "Lightning Bolt"}


def test_infinite_diversity_casts_x_free_copies() -> None:
    """X = Bear, Elf, Druid = 3: Lightning Bolt is exiled and copied three
    times, each copy cast free at bob (CR 707.12a: each copy on its own), and
    Infinite Diversity exiles itself."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Infinite Diversity"],
            graveyard=["Lightning Bolt"],
            battlefield=["Mountain"] * 9 + ["Grizzly Bears", "Llanowar Elves"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    scenario.will_take_the_may(times=None)
    scenario.will_choose_targets("bob", times=None)
    diversity = scenario.cast_onto_stack(
        "Infinite Diversity", *scenario.untapped_sources(*["Mountain"] * 9), targets=[bolt]
    )
    scenario.resolve_top()
    assert bolt.zone is Zone.EXILE
    assert diversity.zone is Zone.EXILE
    assert scenario.stack_names() == ["Lightning Bolt"] * 3
    for _ in range(3):
        scenario.pass_until_resolved()
    assert scenario.player("bob").life == 11
    assert not [card for card in scenario.game.exile if card.is_copy]


def test_captain_jonathan_archer_makes_porthos_and_pumps_by_the_count() -> None:
    """The ETB creates Porthos; "{G}, {T}: target creature you control gets
    +X/+X" at sorcery speed, X = Human, Officer, Dog, Bear = 4."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Captain Jonathan Archer"],
            battlefield=["Forest"] * 4 + ["Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_onto_stack("Captain Jonathan Archer", *scenario.untapped_sources(*["Forest"] * 3))
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    assert scenario.find("Porthos", Zone.BATTLEFIELD, "alice").zone is Zone.BATTLEFIELD
    archer = scenario.creature("Captain Jonathan Archer", "alice")
    archer.summoning_sick = False
    bears = scenario.creature("Grizzly Bears", "alice")
    (forest,) = scenario.untapped_sources("Forest")
    scenario.activate(archer, forest, targets=[bears])
    scenario.pass_until_resolved()
    assert (scenario.game.power_of(bears), scenario.game.toughness_of(bears)) == (6, 6)


def test_sarek_draws_for_every_five_types_and_counters_at_three_draws() -> None:
    """Fifteen types (Vulcan, Advisor, Elf, Druid, Bear, Monkey, Pirate,
    Vampire, Spirit, Goblin, Scout, Human, Soldier, Giant, Wurm) draw three
    cards at the beginning of combat, and three draws put two +1/+1 counters
    on each creature alice controls."""
    creatures = [
        "Sarek, Federation Ambassador",
        "Llanowar Elves",
        "Grizzly Bears",
        "Ragavan, Nimble Pilferer",
        "Bloodghast",
        "Goblin Guide",
        "Thalia, Guardian of Thraben",
        "Hill Giant",
        "Craw Wurm",
    ]
    scenario = (
        Scenario()
        .player("alice", library=["Island"] * 4, battlefield=creatures)
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert _count(scenario) == 15
    scenario.advance()  # beginning of combat
    scenario.pass_until_resolved()
    alice = scenario.player("alice")
    assert len(alice.hand) == 3
    for name in creatures:
        assert scenario.creature(name, "alice").counter_count(Counter.PLUS_ONE) == 2
    assert scenario.creature("Grizzly Bears", "bob").counter_count(Counter.PLUS_ONE) == 0


def test_sarek_draws_one_for_nine_types_and_puts_no_counters() -> None:
    """Nine types are one complete group of five: one card, under the three-card
    threshold, so no counters."""
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Island"] * 2,
            battlefield=[
                "Sarek, Federation Ambassador",
                "Llanowar Elves",
                "Grizzly Bears",
                "Ragavan, Nimble Pilferer",
                "Bloodghast",
            ],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert _count(scenario) == 9
    scenario.advance()
    scenario.pass_until_resolved()
    assert len(scenario.player("alice").hand) == 1
    sarek = scenario.creature("Sarek, Federation Ambassador", "alice")
    assert sarek.counter_count(Counter.PLUS_ONE) == 0


def test_starfleet_academy_taps_for_colorless_and_for_the_count() -> None:
    """ "{T}: Add {C}" and "{5}, {T}: Choose a color. Add an amount of mana of
    that color equal to" the count: Bear, Elf, Druid = 3 green."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Starfleet Academy"]
            + ["Forest"] * 5
            + ["Grizzly Bears", "Llanowar Elves"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    academy = scenario.find("Starfleet Academy", Zone.BATTLEFIELD, "alice")
    pool = scenario.player("alice").mana_pool
    scenario.activate(
        academy, *scenario.untapped_sources(*["Forest"] * 5), index=1, color=Color.GREEN
    )
    assert pool.floating.get(Color.GREEN, 0) == 3
    assert academy.tapped


def test_starfleet_academy_plain_colorless_ability() -> None:
    """The first ability is an ordinary "{T}: Add {C}"."""
    scenario = Scenario().player("alice", battlefield=["Starfleet Academy"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    academy = scenario.find("Starfleet Academy", Zone.BATTLEFIELD, "alice")
    scenario.activate(academy)
    assert scenario.player("alice").mana_pool.floating.get(Color.COLORLESS, 0) == 1


def test_starfleet_academy_with_no_creatures_adds_nothing() -> None:
    """X = 0 with no creatures: the mana is paid and nothing is added."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Starfleet Academy"] + ["Forest"] * 5)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    academy = scenario.find("Starfleet Academy", Zone.BATTLEFIELD, "alice")
    scenario.activate(
        academy, *scenario.untapped_sources(*["Forest"] * 5), index=1, color=Color.GREEN
    )
    assert scenario.player("alice").mana_pool.floating.get(Color.GREEN, 0) == 0
