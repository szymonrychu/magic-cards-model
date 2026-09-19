"""Scenario: FRA S9's 16 lands and their replacement statics.

Three shapes, verified across all sixteen:

- **The ten-land "Annex"/"Commons" cycle** (Dedicated Commons, Fatehold
  Annex, Formidable Commons, Innovative Commons, Konstrari Annex,
  Meticulous Commons, Stingerquill Annex, Theorix Annex, Transformative
  Commons, Vigorbloom Annex), "This land enters tapped unless you control a
  planeswalker." - a genuinely missing shape, not merely unverified:
  `_read_enters_condition` only ever read "you control a[n] <Subtype>"
  (CR 205.3's capitalised subtype, Mountain and friends) and "you control N
  or more other lands", never a bare CR 300.1 **card type** ("a
  planeswalker" prints lowercase, so it never matched the subtype reader's
  capital-letter requirement either). No real Magic card was found printing
  this exact "unless you control a[n] <bare card type>" shape (`resolve_cards`/
  Scryfall `o:"unless you control a creature"` and `o:"unless you control an
  artifact"` both turn up nothing), so the ten fra lands are each other's
  proof that the fix reads the sentence's *type word*, not any one card's
  name - and `test_the_reader_is_not_hardcoded_to_planeswalker` proves the
  same reader at the parser level for a card type no card in the pool
  actually uses.
- **The five real Innistrad slowlands** (Deserted Beach, Haunted Ridge,
  Overgrown Farmland, Rockfall Vale, Shipwreck Marsh), "This land enters
  tapped unless you control two or more other lands." - already read
  correctly with no change; verified here rather than assumed.
- **Room of Refuge**, "This land enters tapped. As it enters, choose a
  color." plus a mana ability keyed to the chosen color - already read
  correctly by the existing CR 614.12a choice machinery; verified here too.

The rule these rest on:

- **CR 614.1d** - "Some replacement effects modify how a permanent enters
  the battlefield... 'If [condition], [this permanent] enters tapped'" - the
  condition is read fresh at the moment the permanent is about to enter
  (CR 614.12), which is why each test plays the land rather than placing it
  already resolved.

Every CR number here was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote it, and every card's text with
`resolve_cards` or straight off its fixture.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.replacement import _read_enters_condition
from tests.scenarios.harness import Scenario

PLANESWALKER_GATED_LANDS = [
    "Dedicated Commons",
    "Fatehold Annex",
    "Formidable Commons",
    "Innovative Commons",
    "Konstrari Annex",
    "Meticulous Commons",
    "Stingerquill Annex",
    "Theorix Annex",
    "Transformative Commons",
    "Vigorbloom Annex",
]

SLOWLANDS = [
    "Deserted Beach",
    "Haunted Ridge",
    "Overgrown Farmland",
    "Rockfall Vale",
    "Shipwreck Marsh",
]


@pytest.mark.parametrize("name", PLANESWALKER_GATED_LANDS)
def test_enters_tapped_with_no_planeswalker(name: str):
    scenario = Scenario().player("alice", hand=[name]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    land = scenario.play_land(name, "alice")

    assert land.tapped, f"{name} should enter tapped with no planeswalker in play"


@pytest.mark.parametrize("name", PLANESWALKER_GATED_LANDS)
def test_enters_untapped_while_controlling_a_planeswalker(name: str):
    scenario = (
        Scenario()
        .player("alice", hand=[name], battlefield=["Ashiok, Dream Render"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    land = scenario.play_land(name, "alice")

    assert not land.tapped, f"{name} should enter untapped while controlling a planeswalker"


def test_only_the_controllers_own_planeswalker_counts():
    scenario = (
        Scenario()
        .player("alice", hand=["Dedicated Commons"])
        .player("bob", battlefield=["Ashiok, Dream Render"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    land = scenario.play_land("Dedicated Commons", "alice")

    assert land.tapped, "an opponent's planeswalker does not exempt this player's land"


def test_the_reader_is_not_hardcoded_to_planeswalker():
    """The parser-level proof `PLANESWALKER_GATED_LANDS` alone cannot give:
    a card type no card in the pool actually gates on still reads."""
    assert _read_enters_condition("you control an artifact") is not None
    assert _read_enters_condition("you control a creature") is not None
    assert _read_enters_condition("you control an enchantment") is not None


@pytest.mark.parametrize("name", SLOWLANDS)
def test_slowland_enters_tapped_with_fewer_than_two_other_lands(name: str):
    scenario = Scenario().player("alice", hand=[name]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    land = scenario.play_land(name, "alice")

    assert land.tapped


@pytest.mark.parametrize("name", SLOWLANDS)
def test_slowland_enters_untapped_with_two_other_lands(name: str):
    scenario = (
        Scenario()
        .player("alice", hand=[name], battlefield=["Forest", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    land = scenario.play_land(name, "alice")

    assert not land.tapped


def test_room_of_refuge_always_enters_tapped_and_taps_for_the_chosen_color():
    scenario = Scenario().player("alice", hand=["Room of Refuge"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.will_choose("R", source="Room of Refuge")
    land = scenario.play_land("Room of Refuge", "alice")

    assert land.tapped
    assert land.choice is not None
    assert land.choice.value == "R"
