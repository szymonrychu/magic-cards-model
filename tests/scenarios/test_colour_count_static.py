"""A static pump counted in colors among a group of permanents you control.

One mechanic: Sisay, Weatherlight Captain's "Sisay gets +1/+1 for each color
among other legendary permanents you control." and its proof printing Earthen
Ally's "This creature gets +1/+0 for each color among Allies you control."

Every CR number below was read with `mise run rules:find` in the session that
wrote this file:

- **CR 105.1** - the five colors; **CR 105.2** - an object is each color in
  its mana cost (or color indicator), so a multicolored permanent adds every
  one of its colors, a color shared by two permanents is still one color, and
  a colorless permanent adds none.
- **CR 611.3a** - a static ability's effect is not locked in: the count
  follows the board.
- **CR 613.4c** - the pump is a sublayer 7c modification.

"Other" leaves Sisay herself out; Earthen Ally, printed without it, counts
itself. Earthen Ally (Modern, Pioneer and Standard legal per Scryfall,
2026-09-23; not in any api deck) is the proof printing: a subtype group
("Allies") instead of a supertype one, +1/+0 instead of +1/+1, and no "other".
Chromatic Orrery, named as a candidate, is an artifact whose count is a
one-shot draw, not a static pump; see MEMORY.md.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

SISAY = "Sisay, Weatherlight Captain"
ALLY = "Earthen Ally"


def _pt(scenario: Scenario, permanent) -> tuple[int | None, int | None]:
    return scenario.game.characteristics_of(permanent).power_toughness


def _sisay(alice: list[str], bob: list[str] | None = None) -> tuple[Scenario, object]:
    scenario = (
        Scenario()
        .player("alice", battlefield=[SISAY, *alice])
        .player("bob", battlefield=bob or [])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario, scenario.creature(SISAY, "alice")


def test_sisay_alone_does_not_count_herself():
    """ "Other": with no other legendary permanent Sisay is her printed 2/2."""
    scenario, sisay = _sisay([])

    assert _pt(scenario, sisay) == (2, 2)


def test_sisay_counts_each_color_among_other_legends():
    """Isamaru (white) and Azusa (green): two colors, 4/4."""
    scenario, sisay = _sisay(["Isamaru, Hound of Konda", "Azusa, Lost but Seeking"])

    assert _pt(scenario, sisay) == (4, 4)


def test_a_shared_color_counts_once():
    """CR 105.2: Isamaru and Thalia are both white - one color, 3/3."""
    scenario, sisay = _sisay(["Isamaru, Hound of Konda", "Thalia, Guardian of Thraben"])

    assert _pt(scenario, sisay) == (3, 3)


def test_a_multicolored_legend_counts_every_one_of_its_colors():
    """Iroh, Grand Lotus is green, blue and red: three colors, 5/5."""
    scenario, sisay = _sisay(["Iroh, Grand Lotus"])

    assert _pt(scenario, sisay) == (5, 5)


def test_a_legendary_noncreature_permanent_counts():
    """ "Legendary permanents", not creatures: Honden of Infinite Rage, a red
    legendary enchantment, adds red."""
    scenario, sisay = _sisay(["Honden of Infinite Rage"])

    assert _pt(scenario, sisay) == (3, 3)


def test_a_colorless_legend_adds_nothing():
    """Minamo, School at Water's Edge is a legendary land with no color."""
    scenario, sisay = _sisay(["Minamo, School at Water's Edge"])

    assert _pt(scenario, sisay) == (2, 2)


def test_nonlegendary_and_opposing_permanents_do_not_count():
    """Grizzly Bears is not legendary; bob's Azusa is not alice's."""
    scenario, sisay = _sisay(["Grizzly Bears"], bob=["Azusa, Lost but Seeking"])

    assert _pt(scenario, sisay) == (2, 2)


def test_the_count_follows_the_board():
    """CR 611.3a: Azusa leaving takes green away at once."""
    scenario, sisay = _sisay(["Isamaru, Hound of Konda", "Azusa, Lost but Seeking"])

    scenario.game.destroy(scenario.creature("Azusa, Lost but Seeking", "alice"))

    assert _pt(scenario, sisay) == (3, 3)


def test_sisays_search_reads_her_counted_power():
    """Her second ability, "a legendary permanent card with mana value less
    than Sisay's power", reads the pumped power: with Isamaru and Azusa out
    she is 4/4, so Thalia (mana value 2) is findable."""
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Thalia, Guardian of Thraben", "Forest"],
            battlefield=[
                SISAY,
                "Isamaru, Hound of Konda",
                "Azusa, Lost but Seeking",
                "Plains",
                "Island",
                "Swamp",
                "Mountain",
                "Forest",
            ],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sisay = scenario.creature(SISAY, "alice")
    scenario.will_choose_cards(scenario.find("Thalia, Guardian of Thraben", Zone.LIBRARY, "alice"))

    scenario.activate(sisay, auto=True)
    scenario.resolve_top()

    assert scenario.find("Thalia, Guardian of Thraben", Zone.BATTLEFIELD, "alice") is not None
    assert _pt(scenario, sisay) == (4, 4), "Thalia is white, a color already counted"


# --------------------------------------------------------------------------
# Earthen Ally (proof printing)
# --------------------------------------------------------------------------


def _ally(alice: list[str]) -> tuple[Scenario, object]:
    scenario = Scenario().player("alice", battlefield=[ALLY, *alice]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario, scenario.creature(ALLY, "alice")


def test_earthen_ally_counts_itself():
    """No "other": Earthen Ally is a green Ally, so alone it is 1/2."""
    scenario, ally = _ally([])

    assert _pt(scenario, ally) == (1, 2)


def test_earthen_ally_counts_colors_among_allies_only():
    """Flexible Waterbender (blue Ally) and Wartime Protestors (red Ally)
    add blue and red; Grizzly Bears (green, not an Ally) adds nothing: 3/2."""
    scenario, ally = _ally(["Flexible Waterbender", "Wartime Protestors", "Grizzly Bears"])

    assert _pt(scenario, ally) == (3, 2)


def test_earthen_ally_pumps_power_only():
    """+1/+0 per color: Iroh, Grand Lotus (green, blue, red Ally) makes it
    3/2 - green counted once alongside Earthen Ally's own green."""
    scenario, ally = _ally(["Iroh, Grand Lotus"])

    assert _pt(scenario, ally) == (3, 2)
