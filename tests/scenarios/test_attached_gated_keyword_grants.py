"""Scenario: an Aura or Equipment that grants a keyword to the creature it is
attached to "as long as `<condition>`".

Read with `mise run rules:find` this session:

- **CR 702.13b** - "A creature with intimidate can't be blocked except by
  artifact creatures and/or creatures that share a color with it."
- **CR 303.4b** - the object an Aura is attached to is called enchanted;
  **CR 301.5a** - likewise the equipped creature (the subject is the source's
  `attached_to` link).
- **CR 613.1f** - layer 6 adds the keyword; **CR 611.3a** / **CR 613.5** -
  the condition is re-asked on every board computation, so the grant stops
  the instant the condition stops holding.
- **CR 700.4** - "other" excludes the object itself.

Predator's Gambit ("... has intimidate as long as its controller controls no
other creatures.") is the reported card. Its "its controller" is the *enchanted
creature's* controller, which is the Aura's controller only when the Aura sits
on its own creature. Temur Runemark ("... has trample as long as you control a
blue or red permanent.", "you" = the Aura's controller, a colour alternative)
and Brass Knuckles ("... has double strike as long as two or more Equipment are
attached to it.", a count of attachments) are the same sentence family with
different wording, so the reader is exercised past the one sentence.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.layers import compute_board, static_effects
from magic_cards_model.models import Zone
from tests.cards import card_state
from tests.scenarios.harness import Scenario


def permanent(name: str, controller: str = "alice"):
    return card_state(name, zone=Zone.BATTLEFIELD, controller=controller, owner=controller)


def board_of(*permanents):
    cards = list(permanents)
    return compute_board(cards, static_effects(cards))


# -- Predator's Gambit: "its controller controls no other creatures" ----------


def test_gambit_grants_intimidate_while_the_enchanted_creature_is_alone():
    gambit = permanent("Predator's Gambit")
    bears = permanent("Grizzly Bears")
    gambit.attach_to(bears)
    board = board_of(gambit, bears)
    assert board.of(bears).has_ability("Intimidate")
    assert board.of(bears).power_toughness == (4, 3), "the unconditional +2/+1 is unaffected"


def test_gambit_grants_nothing_once_its_controller_has_another_creature():
    gambit = permanent("Predator's Gambit")
    bears = permanent("Grizzly Bears")
    friend = permanent("Goblin Guide")
    gambit.attach_to(bears)
    board = board_of(gambit, bears, friend)
    assert not board.of(bears).has_ability("Intimidate")
    assert board.of(bears).power_toughness == (4, 3), "the pump stays; only intimidate is gated"


def test_an_opponents_creatures_do_not_count_as_other_creatures():
    gambit = permanent("Predator's Gambit")
    bears = permanent("Grizzly Bears")
    enemy = permanent("Goblin Guide", "bob")
    gambit.attach_to(bears)
    assert board_of(gambit, bears, enemy).of(bears).has_ability("Intimidate")


def test_a_noncreature_permanent_does_not_count_as_another_creature():
    gambit = permanent("Predator's Gambit")
    bears = permanent("Grizzly Bears")
    land = permanent("Swamp")
    gambit.attach_to(bears)
    assert board_of(gambit, bears, land).of(bears).has_ability("Intimidate")


def test_gambit_on_an_opponents_creature_uses_that_creatures_controller():
    """alice's Aura on bob's creature: "its controller" is bob. Bob's other
    creature switches it off; alice's own creatures are not bob's and do not."""
    gambit = permanent("Predator's Gambit", "alice")
    bears = permanent("Grizzly Bears", "bob")
    alices_creature = permanent("Goblin Guide", "alice")
    bobs_other = permanent("Dark Confidant", "bob")
    gambit.attach_to(bears)
    assert board_of(gambit, bears, alices_creature).of(bears).has_ability("Intimidate")
    assert (
        not board_of(gambit, bears, alices_creature, bobs_other).of(bears).has_ability("Intimidate")
    )


def test_the_grant_follows_the_board_not_a_snapshot():
    gambit = permanent("Predator's Gambit")
    bears = permanent("Grizzly Bears")
    friend = permanent("Goblin Guide")
    gambit.attach_to(bears)
    assert not board_of(gambit, bears, friend).of(bears).has_ability("Intimidate")
    assert board_of(gambit, bears).of(bears).has_ability("Intimidate")


def test_an_unattached_gambit_grants_nothing():
    gambit = permanent("Predator's Gambit")
    bears = permanent("Grizzly Bears")
    assert not board_of(gambit, bears).of(bears).has_ability("Intimidate")


def _gambit_in_combat(*, blocker: str, alone: bool = True):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Predator's Gambit"],
            battlefield=["Grizzly Bears", "Swamp", "Swamp", "Swamp", "Swamp"]
            + ([] if alone else ["Goblin Guide"]),
            library=["Island"] * 3,
        )
        .player("bob", battlefield=[blocker], library=["Island"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_and_resolve("Predator's Gambit", auto=True, targets=[bears])
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    return scenario, bears, scenario.creature(blocker, "bob")


def test_enchanted_alone_it_is_blockable_only_per_702_13b():
    scenario, bears, blocker = _gambit_in_combat(blocker="Memnite")
    assert scenario.game.why_cannot_block(blocker, bears) is None, "an artifact creature may block"

    scenario, bears, blocker = _gambit_in_combat(blocker="Serra Angel")
    refusal = scenario.game.why_cannot_block(blocker, bears)
    assert refusal is not None and "702.13b" in refusal


def test_enchanted_alone_a_creature_sharing_a_color_may_block():
    """Grizzly Bears is green; Llanowar Elves is green."""
    scenario, bears, blocker = _gambit_in_combat(blocker="Llanowar Elves")
    assert scenario.game.why_cannot_block(blocker, bears) is None


def test_with_a_second_creature_the_enchanted_one_is_blockable_by_anything():
    scenario, bears, blocker = _gambit_in_combat(blocker="Serra Angel", alone=False)
    assert scenario.game.why_cannot_block(blocker, bears) is None


# -- Temur Runemark: "as long as you control a blue or red permanent" ---------


def test_runemark_grants_trample_only_with_a_blue_or_red_permanent():
    runemark = permanent("Temur Runemark")
    bears = permanent("Grizzly Bears")
    runemark.attach_to(bears)
    assert not board_of(runemark, bears).of(bears).has_ability("Trample")
    assert board_of(runemark, bears, permanent("Goblin Guide")).of(bears).has_ability("Trample")
    assert board_of(runemark, bears, permanent("Serra Angel")).of(bears).power_toughness == (
        4,
        4,
    ), "the pump is ungated"
    assert (
        not board_of(runemark, bears, permanent("Dark Confidant")).of(bears).has_ability("Trample")
    ), "a black permanent is neither blue nor red"


def test_runemark_counts_only_the_auras_controllers_permanents():
    runemark = permanent("Temur Runemark")
    bears = permanent("Grizzly Bears")
    runemark.attach_to(bears)
    enemy_red = permanent("Goblin Guide", "bob")
    assert not board_of(runemark, bears, enemy_red).of(bears).has_ability("Trample")


# -- Brass Knuckles: "as long as two or more Equipment are attached to it" ----


def test_brass_knuckles_grants_double_strike_with_two_equipment_attached():
    knuckles = permanent("Brass Knuckles")
    bonesplitter = permanent("Bonesplitter")
    bears = permanent("Grizzly Bears")
    knuckles.attach_to(bears)
    assert not board_of(knuckles, bears).of(bears).has_ability("Double strike")
    bonesplitter.attach_to(bears)
    assert board_of(knuckles, bonesplitter, bears).of(bears).has_ability("Double strike")


def test_brass_knuckles_ignores_equipment_attached_to_another_creature():
    knuckles = permanent("Brass Knuckles")
    bonesplitter = permanent("Bonesplitter")
    bears = permanent("Grizzly Bears")
    other = permanent("Goblin Guide")
    knuckles.attach_to(bears)
    bonesplitter.attach_to(other)
    assert not board_of(knuckles, bonesplitter, bears, other).of(bears).has_ability("Double strike")
