"""Scenario: a mass pump or grant followed by "Untap them." / "Untap those
creatures." / "Untap each creature you control." - the anaphora is the exact
group the leading sentence's own antecedent found (CR 608.2c, CR 611.2c), so
the untap reaches that set and nobody else.

Cards: Rally to Battle, Rallying Roar (untap them), War Flare, Gleam of
Resistance, Tenacity (untap those creatures), Jeskai Ascendancy (a trigger),
Ready // Willing (untap each creature you control; both halves and fused),
Essence of Antiquity (a face-up trigger: the hexproof grant, then untap).

Rules verified with `mise run rules:find` (on-disk CR effective 2026-09-25):

- **CR 611.2c** - a one-shot continuous effect affects only the objects there
  when it begins; a creature that enters afterwards is not pumped.
- **CR 608.2c** - instructions are followed in order; "them" is the group the
  prior instruction found.
- **CR 701.26b** - untapping a permanent turns it upright.
- **CR 702.102** - fuse: both halves resolve, left to right.
- **CR 702.168** - disguise: turned face up as a special action, which
  triggers "when this creature is turned face up".
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import Scenario


def computed(scenario):
    return scenario.game.continuous_effects.board(scenario.game.battlefield)


def _resolve_everything(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.pass_until_resolved()
        scenario.game.put_triggers_on_stack()


def _board(hand, lands):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=hand,
            battlefield=["Grizzly Bears", "Ornithopter", *lands],
            library=["Island"] * 5,
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


@pytest.mark.parametrize(
    "name",
    [
        "Rally to Battle",
        "Rallying Roar",
        "War Flare",
        "Gleam of Resistance",
        "Tenacity",
        "Ready // Willing",
        "Essence of Antiquity",
        "Jeskai Ascendancy",
    ],
)
def test_untap_clause_is_handled(name):
    clauses = [c for c in classify_clauses(card(name)) if "ntap" in c.text]
    assert clauses, name
    assert all(c.category == HANDLED for c in clauses), [(c.text, c.category) for c in clauses]


SPELLS = [
    ("Rally to Battle", ["Plains"] * 4, (3, 5)),
    ("Rallying Roar", ["Plains"] * 3, (3, 3)),
    ("War Flare", ["Plains", "Plains", "Mountain", "Mountain"], (4, 3)),
    ("Gleam of Resistance", ["Plains"] * 5, (3, 4)),
    ("Tenacity", ["Plains"] * 4, (3, 3)),
]


@pytest.mark.parametrize(("name", "lands", "grizzly"), SPELLS)
def test_spell_pumps_and_untaps_exactly_the_group(name, lands, grizzly):
    scenario = _board([name], lands)
    bears = scenario.creature("Grizzly Bears", "alice")
    ornithopter = scenario.creature("Ornithopter", "alice")
    foe = scenario.creature("Grizzly Bears", "bob")
    bears.tap()
    foe.tap()
    assert ornithopter.untapped

    scenario.cast_and_resolve(name, *scenario.untapped_sources(*lands))

    assert not bears.tapped, "tapped creature of the group untaps"
    assert not ornithopter.tapped
    assert foe.tapped, "an opponent's creature is untouched"
    assert computed(scenario).of(bears).power_toughness == grizzly
    assert computed(scenario).of(foe).power_toughness == (2, 2)


def test_creature_entering_after_resolution_is_neither_pumped_nor_untapped():
    scenario = _board(["Rally to Battle", "Savannah Lions"], ["Plains"] * 4)
    scenario.cast_and_resolve("Rally to Battle", *scenario.untapped_sources(*["Plains"] * 4))
    late = scenario.put_onto_battlefield("Savannah Lions", "alice", tapped=True)

    assert late.tapped
    assert computed(scenario).of(late).power_toughness == (2, 1)


def test_tenacity_group_also_gains_lifelink():
    scenario = _board(["Tenacity"], ["Plains"] * 4)
    bears = scenario.creature("Grizzly Bears", "alice")
    foe = scenario.creature("Grizzly Bears", "bob")
    scenario.cast_and_resolve("Tenacity", *scenario.untapped_sources(*["Plains"] * 4))
    assert has_keyword(bears, "lifelink", scenario.game)
    assert not has_keyword(foe, "lifelink", scenario.game)


def test_jeskai_ascendancy_pumps_and_untaps_on_a_noncreature_cast():
    scenario = _board(["Lightning Bolt"], ["Jeskai Ascendancy", "Mountain"])
    bears = scenario.creature("Grizzly Bears", "alice")
    foe = scenario.creature("Grizzly Bears", "bob")
    bears.tap()
    foe.tap()
    casting = scenario.cast("Lightning Bolt", targets=[scenario.player("bob")])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Mountain"))
    scenario.put_on_stack(casting)
    _resolve_everything(scenario)

    assert not bears.tapped
    assert foe.tapped
    assert computed(scenario).of(bears).power_toughness == (3, 3)
    assert computed(scenario).of(foe).power_toughness == (2, 2)


def test_ready_untaps_each_creature_you_control_and_grants_indestructible():
    scenario = _board(["Ready // Willing"], ["Plains", "Forest", "Swamp"])
    bears = scenario.creature("Grizzly Bears", "alice")
    foe = scenario.creature("Grizzly Bears", "bob")
    bears.tap()
    foe.tap()
    casting = scenario.cast("Ready")
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Plains", "Forest", "Swamp"))
    scenario.put_on_stack(casting)
    _resolve_everything(scenario)

    assert not bears.tapped
    assert foe.tapped
    assert has_keyword(bears, "indestructible", scenario.game)
    assert not has_keyword(foe, "indestructible", scenario.game)


def test_willing_alone_does_not_untap():
    scenario = _board(["Ready // Willing"], ["Plains", "Swamp", "Forest"])
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.tap()
    casting = scenario.cast("Ready")
    casting.cast_as_split_half("Willing")
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Plains", "Swamp", "Forest"))
    scenario.put_on_stack(casting)
    _resolve_everything(scenario)

    assert bears.tapped
    assert has_keyword(bears, "deathtouch", scenario.game)
    assert has_keyword(bears, "lifelink", scenario.game)


def test_fused_ready_willing_grants_all_and_untaps():
    lands = ["Plains", "Plains", "Forest", "Swamp", "Plains", "Forest"]
    scenario = _board(["Ready // Willing"], lands)
    bears = scenario.creature("Grizzly Bears", "alice")
    ornithopter = scenario.creature("Ornithopter", "alice")
    bears.tap()
    ornithopter.tap()
    casting = scenario.cast("Ready")
    casting.cast_fused()
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*lands))
    scenario.put_on_stack(casting)
    _resolve_everything(scenario)

    assert not bears.tapped
    assert not ornithopter.tapped
    for keyword in ("indestructible", "deathtouch", "lifelink"):
        assert has_keyword(bears, keyword, scenario.game)


def test_essence_of_antiquity_face_up_grants_hexproof_and_untaps():
    lands = ["Plains"] * 6
    scenario = _board(["Essence of Antiquity"], lands)
    bears = scenario.creature("Grizzly Bears", "alice")
    foe = scenario.creature("Grizzly Bears", "bob")
    casting = scenario.cast("Essence of Antiquity")
    casting.use_keyword("Disguise")
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*["Plains"] * 3))
    scenario.put_on_stack(casting)
    essence = scenario.resolve_top()
    bears.tap()
    foe.tap()
    essence.tap()
    scenario.turn_face_up(essence, *scenario.untapped_sources(*["Plains"] * 3))
    _resolve_everything(scenario)

    assert has_keyword(bears, "hexproof", scenario.game)
    assert not has_keyword(foe, "hexproof", scenario.game)
    assert not bears.tapped, "the hexproof group untaps"
    assert not essence.tapped, "the face-up creature is itself one of 'them'"
    assert foe.tapped
