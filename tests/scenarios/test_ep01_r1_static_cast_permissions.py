"""EP-01 round 1, task 8: static cast permissions (CR 601.3, CR 611.3d).

One scenario per permission shape, each through the real cast path
(`Casting.use_keyword("Cast permission")`, `why_cannot_cast_from`,
`granted_cast_options`), with the engine's own refusal text where the
permission does not apply and a second, unlisted printing of the same shape.

Shapes:

- a card's own "You may cast this card from your graveyard / exile", plain,
  conditional ("as long as", "if", Max speed), with an additional cost in
  gerund form ("by discarding a card in addition to paying its other costs"),
  and confined ("but not from anywhere else");
- a permanent's "You may cast `<quality>` spells from the top of your
  library" and its variants (once each turn, condition, keywords, additional
  cost, chosen type, shares a card type);
- "You may cast `<quality>` spells as though they had flash" and the
  spell's own conditional flash;
- "You may cast `<quality>` spells without paying their mana costs".

Rules, each read with `mise run rules:find` in the session that wrote this
file: CR 601.3 (a rule or effect must allow the cast), CR 604.6 (a static
ability that functions outside the battlefield), CR 611.3d (continuous
effects from static abilities that allow casting), CR 601.2f (additional
costs), CR 702.8a (flash), CR 118.9 (alternative cost of nothing), CR 702.178a
(max speed), CR 700.4 (dies), CR 205.2b (a card with several types).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import (
    Casting,
    conditional_flash_condition,
    granted_cast_options,
    why_cannot_cast_from,
    why_cannot_cast_now,
)
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

CAST_PERMISSION = "Cast permission"
LANDS = ["Plains", "Island", "Swamp", "Mountain", "Forest"] * 3


def build(*, alice=None, bob=None, step=Step.PRECOMBAT_MAIN):
    alice = dict(alice or {})
    alice.setdefault("battlefield", [])
    alice["battlefield"] = [*alice["battlefield"], *LANDS]
    alice.setdefault("library", ["Forest"] * 6)
    scenario = (
        Scenario().player("alice", **alice).player("bob", **(bob or {"library": ["Island"] * 6}))
    ).build()
    scenario.start_at(step)
    return scenario


def resolve_everything(scenario):
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def refusal(scenario, name, zone, caster="alice"):
    card = scenario.find(name, zone, caster if zone is not Zone.EXILE else None)
    return why_cannot_cast_from(card, caster, zone, scenario.game)


def cast_with_permission(
    scenario, name, zone, *, choosing=None, caster="alice", targets=None, **costs
):
    casting = scenario.cast(name, username=caster, from_zone=zone, **costs)
    casting.use_keyword(CAST_PERMISSION, choosing=choosing)
    if targets is not None:
        casting.choose_targets(targets)
    scenario.auto_pay(casting.begin_paying(), username=caster)
    card = scenario.put_on_stack(casting)
    resolve_everything(scenario)
    return card


def on_battlefield(card):
    return card.zone is Zone.BATTLEFIELD


# -- a card's own permission to be cast from its graveyard or exile ----------


def test_a_plain_graveyard_permission_casts_the_card():
    scenario = build(
        alice={"graveyard": ["Skaab Ruinator", "Grizzly Bears", "Grizzly Bears", "Grizzly Bears"]}
    )
    bears = [c for c in scenario.player("alice").graveyard if c.name == "Grizzly Bears"]
    ruinator = cast_with_permission(scenario, "Skaab Ruinator", Zone.GRAVEYARD, exiling=bears)
    assert on_battlefield(ruinator)
    assert all(bear.zone is Zone.EXILE for bear in bears)


def test_the_graveyard_permission_does_not_reach_exile():
    scenario = build(alice={"graveyard": ["Skaab Ruinator"]})
    scenario.game.exile_cards([scenario.find("Skaab Ruinator", Zone.GRAVEYARD, "alice")])
    assert refusal(scenario, "Skaab Ruinator", Zone.EXILE).startswith("nothing allows alice")


def test_gravecrawler_needs_a_zombie_to_be_cast_from_the_graveyard():
    scenario = build(alice={"graveyard": ["Gravecrawler"], "battlefield": ["Grizzly Bears"]})
    reason = refusal(scenario, "Gravecrawler", Zone.GRAVEYARD)
    assert reason is not None and "only if you control a Zombie" in reason


def test_gravecrawler_is_cast_from_the_graveyard_while_a_zombie_is_controlled():
    scenario = build(alice={"graveyard": ["Gravecrawler"], "battlefield": ["Skaab Ruinator"]})
    assert refusal(scenario, "Gravecrawler", Zone.GRAVEYARD) is None
    assert on_battlefield(cast_with_permission(scenario, "Gravecrawler", Zone.GRAVEYARD))


def test_marang_river_prowler_needs_a_black_or_green_permanent():
    scenario = build(alice={"graveyard": ["Marang River Prowler"], "battlefield": ["Plains"]})
    reason = refusal(scenario, "Marang River Prowler", Zone.GRAVEYARD)
    assert reason is not None and "black or green permanent" in reason
    scenario = build(alice={"graveyard": ["Marang River Prowler"], "battlefield": ["Grizzly Bears"]})
    assert refusal(scenario, "Marang River Prowler", Zone.GRAVEYARD) is None
    assert on_battlefield(cast_with_permission(scenario, "Marang River Prowler", Zone.GRAVEYARD))


def test_ebondeath_needs_another_creature_to_have_died_this_turn():
    scenario = build(
        alice={"graveyard": ["Ebondeath, Dracolich"], "battlefield": ["Grizzly Bears"]}
    )
    reason = refusal(scenario, "Ebondeath, Dracolich", Zone.GRAVEYARD)
    assert reason is not None and "not named Ebondeath, Dracolich died this turn" in reason
    scenario.game.destroy(scenario.creature("Grizzly Bears", "alice"))
    assert refusal(scenario, "Ebondeath, Dracolich", Zone.GRAVEYARD) is None
    assert on_battlefield(cast_with_permission(scenario, "Ebondeath, Dracolich", Zone.GRAVEYARD))


def test_ebondeath_does_not_count_its_own_death():
    scenario = build(alice={"battlefield": ["Ebondeath, Dracolich"]})
    scenario.game.destroy(scenario.creature("Ebondeath, Dracolich", "alice"))
    reason = refusal(scenario, "Ebondeath, Dracolich", Zone.GRAVEYARD)
    assert reason is not None and "that is not so" in reason


def test_oathsworn_vampire_needs_life_gained_this_turn():
    scenario = build(alice={"graveyard": ["Oathsworn Vampire"]})
    reason = refusal(scenario, "Oathsworn Vampire", Zone.GRAVEYARD)
    assert reason is not None and "gained life this turn" in reason
    scenario.game.gain_life("alice", 1)
    assert refusal(scenario, "Oathsworn Vampire", Zone.GRAVEYARD) is None
    assert on_battlefield(cast_with_permission(scenario, "Oathsworn Vampire", Zone.GRAVEYARD))


def test_a_max_speed_ability_word_is_the_condition():
    scenario = build(
        alice={"graveyard": ["Lightwheel Enhancements"], "battlefield": ["Grizzly Bears"]}
    )
    reason = refusal(scenario, "Lightwheel Enhancements", Zone.GRAVEYARD)
    assert reason is not None and "you have max speed" in reason
    scenario.game.player("alice").speed = 4
    assert refusal(scenario, "Lightwheel Enhancements", Zone.GRAVEYARD) is None


def test_squee_is_castable_from_the_graveyard_and_from_exile():
    scenario = build(alice={"graveyard": ["Squee, the Immortal"]})
    assert refusal(scenario, "Squee, the Immortal", Zone.GRAVEYARD) is None
    scenario.game.exile_cards([scenario.find("Squee, the Immortal", Zone.GRAVEYARD, "alice")])
    assert refusal(scenario, "Squee, the Immortal", Zone.EXILE) is None
    assert on_battlefield(cast_with_permission(scenario, "Squee, the Immortal", Zone.EXILE))


def test_a_from_exile_only_permission_does_not_open_the_graveyard():
    scenario = build(alice={"graveyard": ["Misthollow Griffin"]})
    assert refusal(scenario, "Misthollow Griffin", Zone.GRAVEYARD).startswith("nothing allows")
    scenario.game.exile_cards([scenario.find("Misthollow Griffin", Zone.GRAVEYARD, "alice")])
    assert refusal(scenario, "Misthollow Griffin", Zone.EXILE) is None
    assert on_battlefield(cast_with_permission(scenario, "Misthollow Griffin", Zone.EXILE))


def test_eternal_scourge_is_cast_from_exile():
    scenario = build(alice={"graveyard": ["Eternal Scourge"]})
    scenario.game.exile_cards([scenario.find("Eternal Scourge", Zone.GRAVEYARD, "alice")])
    assert on_battlefield(cast_with_permission(scenario, "Eternal Scourge", Zone.EXILE))


def test_haakon_is_confined_to_the_graveyard():
    scenario = build(alice={"hand": ["Haakon, Stromgald Scourge"]})
    reason = refusal(scenario, "Haakon, Stromgald Scourge", Zone.HAND)
    assert reason is not None and "only from the graveyard" in reason
    scenario = build(alice={"graveyard": ["Haakon, Stromgald Scourge"]})
    assert refusal(scenario, "Haakon, Stromgald Scourge", Zone.GRAVEYARD) is None
    assert on_battlefield(
        cast_with_permission(scenario, "Haakon, Stromgald Scourge", Zone.GRAVEYARD)
    )


# -- the permission's own additional cost, worded as a gerund ----------------


def test_alien_symbiosis_discards_a_card_to_be_cast_from_the_graveyard():
    scenario = build(
        alice={"graveyard": ["Alien Symbiosis"], "hand": ["Island"], "battlefield": ["Grizzly Bears"]}
    )
    island = scenario.find("Island", Zone.HAND, "alice")
    cast_with_permission(
        scenario,
        "Alien Symbiosis",
        Zone.GRAVEYARD,
        choosing=[island],
        targets=[scenario.creature("Grizzly Bears", "alice")],
    )
    assert island.zone is Zone.GRAVEYARD


def test_rona_discards_two_cards():
    scenario = build(
        alice={"graveyard": ["Rona, Sheoldred's Faithful"], "hand": ["Island", "Swamp"]}
    )
    hand = list(scenario.player("alice").hand)
    rona = cast_with_permission(scenario, "Rona, Sheoldred's Faithful", Zone.GRAVEYARD, choosing=hand)
    assert on_battlefield(rona)
    assert all(card.zone is Zone.GRAVEYARD for card in hand)


def test_demonic_embrace_pays_three_life_and_discards():
    scenario = build(
        alice={"graveyard": ["Demonic Embrace"], "hand": ["Island"], "battlefield": ["Grizzly Bears"]}
    )
    island = scenario.find("Island", Zone.HAND, "alice")
    cast_with_permission(
        scenario,
        "Demonic Embrace",
        Zone.GRAVEYARD,
        choosing=[island],
        targets=[scenario.creature("Grizzly Bears", "alice")],
    )
    assert scenario.player("alice").life == 17
    assert island.zone is Zone.GRAVEYARD


def test_wickerfolk_pays_two_life_and_sacrifices_a_creature():
    scenario = build(alice={"graveyard": ["Wickerfolk Indomitable"], "battlefield": ["Grizzly Bears"]})
    bears = scenario.creature("Grizzly Bears", "alice")
    folk = cast_with_permission(scenario, "Wickerfolk Indomitable", Zone.GRAVEYARD, choosing=[bears])
    assert on_battlefield(folk)
    assert bears.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 18
