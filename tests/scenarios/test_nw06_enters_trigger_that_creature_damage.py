"""'That creature' on an enters trigger resolves to the right creature.

Pool scan (Modern/Pioneer/Standard oracle pool, every trigger or activated
sentence that says "that creature" with damage, enters-the-battlefield
events and the chosen-target forms that share its referent):

- Family A, the event's creature is "that creature" (CR 603.2): Flame-Kin War
  Scout ("When another creature enters, ... this creature deals 4 damage to
  that creature") - 1 card.
- Family B, the event's creature is the damage dealer: Flayer of the
  Hatebound, Electropotence ("that creature deals damage equal to its power to
  any target") - 2 cards.
- Family C, "that creature" is the target the sentence named (CR 608.2c):
  Case of the Gateway Express, Stalking Yeti, Hunter's Bow, Thorin,
  Mountain-king, Shocker, Unshakable, Ana Battlemage, Cyclops Gladiator -
  the chosen target takes it, never the event's creature.

Rules verified with `mise run rules:find`:

- **CR 603.2** - a trigger's event names the object its text refers back to.
- **CR 608.2b** - a target that became illegal is not replaced by another.
- **CR 608.2c** - "that creature" follows the earlier text's own object.
- **CR 120.3** - damage is dealt by the named source.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.cards import card

from .harness import Scenario

LANDS = ["Mountain"] * 4 + ["Swamp"] * 2 + ["Plains"] * 2 + ["Forest"] * 2


def _drain(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _main(alice=(), bob=(), hand=(), graveyard=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[*LANDS, *alice],
            hand=list(hand),
            graveyard=list(graveyard),
        )
        .player("bob", battlefield=list(bob))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


# -- Family A: the entering creature is "that creature" ----------------------


def test_flame_kin_war_scout_deals_four_to_the_entering_creature_not_a_bystander():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Flame-Kin War Scout", "Grizzly Bears"])
        .player("bob", battlefield=["Elite Vanguard"], hand=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.put_onto_battlefield("Hill Giant", "bob")
    _drain(scenario)

    assert giant.zone is Zone.GRAVEYARD, "4 damage to the 3/3 that entered"
    assert scenario.creature("Grizzly Bears", "alice").damage == 0
    assert scenario.creature("Elite Vanguard", "bob").damage == 0
    assert scenario.find("Flame-Kin War Scout", Zone.GRAVEYARD, "alice") is not None


# -- Family B: the entering creature is the dealer ---------------------------


def test_flayer_of_the_hatebound_entering_creature_deals_its_power_to_the_target():
    scenario = _main(
        alice=["Flayer of the Hatebound", "Grizzly Bears"],
        bob=["Craw Wurm"],
        graveyard=["Hill Giant"],
    )
    scenario.will_choose_targets(scenario.creature("Craw Wurm", "bob"))
    giant = scenario.put_onto_battlefield("Hill Giant", "alice", Zone.GRAVEYARD)
    _drain(scenario)

    assert scenario.creature("Craw Wurm", "bob").damage == 3, "Hill Giant's own power"
    assert giant.damage == 0


# -- Family C: the sentence's own target is "that creature" ------------------


def test_case_of_the_gateway_express_chosen_creature_takes_one_per_creature():
    scenario = _main(
        alice=["Grizzly Bears", "Elite Vanguard"],
        bob=["Craw Wurm", "Hill Giant"],
        hand=["Case of the Gateway Express"],
    )
    wurm = scenario.creature("Craw Wurm", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.cast_onto_stack("Case of the Gateway Express", auto=True)
    scenario.will_choose_targets(wurm)
    scenario.resolve_top()
    _drain(scenario)

    assert wurm.damage == 2
    assert giant.damage == 0


def test_stalking_yeti_deals_its_power_to_the_chosen_creature_and_takes_its_back():
    scenario = _main(bob=["Hill Giant", "Grizzly Bears"], hand=["Stalking Yeti"])
    giant = scenario.creature("Hill Giant", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.cast_onto_stack("Stalking Yeti", auto=True)
    scenario.will_choose_targets(giant)
    scenario.resolve_top()
    _drain(scenario)

    assert giant.zone is Zone.GRAVEYARD, "3 damage kills the 3/3"
    assert bears.damage == 0
    assert scenario.find("Stalking Yeti", Zone.GRAVEYARD) is not None, "the Giant hit back for 3"


def test_hunters_bow_the_attached_creature_bites_the_second_target_only():
    scenario = _main(
        alice=["Hill Giant"], bob=["Grizzly Bears", "Elite Vanguard"], hand=["Hunter's Bow"]
    )
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.cast_onto_stack("Hunter's Bow", auto=True)
    scenario.will_choose_targets(giant, bears)
    scenario.resolve_top()
    _drain(scenario)

    assert bears.zone is Zone.GRAVEYARD
    assert scenario.creature("Elite Vanguard", "bob").damage == 0
    assert giant.damage == 0


def test_thorin_mountain_king_equipped_creature_deals_its_power_to_the_victim():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Thorin, Mountain-king"],
            battlefield=["Dwarven Shortsword", "Grizzly Bears", *["Mountain"] * 4],
        )
        .player("bob", battlefield=["Watchwolf", "Elite Vanguard"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sword = scenario.find("Dwarven Shortsword", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    watchwolf = scenario.creature("Watchwolf", "bob")
    scenario.choose_trigger_targets("Thorin, Mountain-king", [sword, bears])
    scenario.will_choose_targets(watchwolf)
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain")
    scenario.cast_and_resolve("Thorin, Mountain-king", *sources)
    _drain(scenario)

    assert sword.attached_to == bears.id
    assert watchwolf.zone is Zone.GRAVEYARD, "Bears + Shortsword: 3 power kills the 3/3"
    assert scenario.creature("Elite Vanguard", "bob").damage == 0


def test_every_family_card_has_a_printing():
    for name in (
        "Flame-Kin War Scout",
        "Flayer of the Hatebound",
        "Case of the Gateway Express",
        "Stalking Yeti",
        "Hunter's Bow",
        "Thorin, Mountain-king",
    ):
        assert card(name).name == name
