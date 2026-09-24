"""Scenario: two attack-trigger templates scaled by a count taken as the
ability resolves (CR 608.2h) - neither a mass pump nor a target-count
multiplier, both new readers in `machines/effects.py`.

- **Eagle of the Great Shelf**: "Whenever this creature attacks, it gets
  +1/+1 until end of turn for each other creature you control."
  (`_parse_self_pump_for_each_clause`) - a self pump, "it" read the plain
  CR 700.7 way. Proven generic on Sigil of Valor's real, modern/pioneer-legal
  "Whenever equipped creature attacks alone, it gets +1/+1 until end of turn
  for each other creature you control.", which also exercises
  `_attack_trigger_pump_subject`'s other branch: "it" there names whatever
  the Equipment is attached to (CR 301.5a), not the Equipment itself.
- **Smaug the Magnificent**: "Whenever Smaug attacks, he deals damage equal
  to the number of Treasures you control to any target."
  (`_parse_self_damage_equal_to_count_clause`) - `count_expression`'s own
  "the number of `<qualifier>` you control" grammar, reached from a "deals
  damage equal to ..." opening rather than a "for each" one. Proven generic
  on Eivor, Battle-Ready's real, modern-legal "Whenever Eivor attacks, it
  deals damage equal to the number of Equipment you control to each
  opponent." - the identical magnitude grammar with a different printed
  recipient (mass, to every opponent, rather than one chosen target).

CR 608.2h ("the ability's controller announces the value of that count ...
at that time, and that value doesn't change") was verified with `mise run
rules:find` in the session that wrote this file - see `machines/effects.py`'s
own docstrings for the exact wording it already cites for the pre-existing
`count_expression`/`_for_each_multiplier` readers this reuses.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import equip_activation
from magic_cards_model.models import Zone

from .harness import Scenario, mana_from

# -- Eagle of the Great Shelf -------------------------------------------


def test_the_pump_scales_with_the_number_of_other_creatures_attacking_does_not_matter():
    """Two other creatures on the board (only one of which also attacks)
    give a +2/+2 pump - the count is "other creatures you control", not
    "other attacking creatures"."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Eagle of the Great Shelf", "Grizzly Bears", "Wurmcoil Engine"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    eagle = scenario.creature("Eagle of the Great Shelf")
    bears = scenario.creature("Grizzly Bears")

    scenario.attack_with(eagle, bears)
    scenario.resolve_top()

    assert scenario.game.characteristics_of(eagle).power_toughness == (4, 7), (
        "base 2/5, +2/+2 for the two other creatures (Bears, Wurmcoil Engine)"
    )


def test_no_other_creatures_means_no_pump_at_all():
    scenario = (
        Scenario().player("alice", battlefield=["Eagle of the Great Shelf"]).player("bob").build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    eagle = scenario.creature("Eagle of the Great Shelf")

    scenario.attack_with(eagle)
    scenario.resolve_top()

    assert scenario.game.characteristics_of(eagle).power_toughness == (2, 5)
    assert scenario.game.continuous_effects.effects == []


def test_sigil_of_valor_pumps_the_equipped_creature_not_the_equipment():
    """A second, real, modern/pioneer-legal printing of the identical effect
    sentence - "Whenever equipped creature attacks alone, it gets +1/+1
    until end of turn for each other creature you control." - whose subject
    is the equipped creature (CR 301.5a), proving `_attack_trigger_pump_
    subject`'s "equipped creature" branch, not only the bare self-reference
    Eagle of the Great Shelf exercises above."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Sigil of Valor", "Grizzly Bears", "Wurmcoil Engine"] + ["Plains"] * 2,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sigil = scenario.find("Sigil of Valor", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears")

    activation = equip_activation(scenario.game, sigil, bears, "alice")
    payment = activation.begin_paying()
    (plains,) = scenario.untapped_sources("Plains")
    payment.tap_for_mana(plains, mana_from(plains))
    payment.pay()
    activation.activate()
    scenario.resolve_top()

    scenario.advance()  # -> declare attackers
    scenario.attack_with(bears)
    scenario.resolve_top()

    assert scenario.game.characteristics_of(bears).power_toughness == (3, 3), (
        "base 2/2, +1/+1 for the one other creature (Wurmcoil Engine) - Sigil of Valor "
        "itself never gets pumped, it isn't a creature"
    )


# -- Smaug the Magnificent ------------------------------------------------


def test_smaug_deals_damage_equal_to_the_number_of_treasures_to_any_target():
    scenario = (
        Scenario().player("alice", battlefield=["Smaug the Magnificent"]).player("bob").build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    smaug = scenario.creature("Smaug the Magnificent")
    from magic_cards_model.models.token import TokenDefinition, create_tokens

    create_tokens(
        scenario.game,
        TokenDefinition(types=(), subtypes=("Treasure",)),
        "alice",
        count=3,
    )

    bob = scenario.player("bob")
    life_before = bob.life
    scenario.choose_trigger_targets("Smaug the Magnificent", [bob])
    scenario.attack_with(smaug)
    scenario.resolve_top()

    assert bob.life == life_before - 3


def test_no_treasures_means_no_damage():
    scenario = (
        Scenario().player("alice", battlefield=["Smaug the Magnificent"]).player("bob").build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    smaug = scenario.creature("Smaug the Magnificent")
    bob = scenario.player("bob")
    life_before = bob.life

    scenario.choose_trigger_targets("Smaug the Magnificent", [bob])
    scenario.attack_with(smaug)
    scenario.resolve_top()

    assert bob.life == life_before


def test_eivor_deals_damage_equal_to_the_number_of_equipment_to_each_opponent():
    """A second, real, modern-legal printing - "Whenever Eivor attacks, it
    deals damage equal to the number of Equipment you control to each
    opponent." - the same magnitude grammar reaching a mass, untargeted
    recipient instead of Smaug's single chosen target."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Eivor, Battle-Ready", "Bonesplitter", "Bonesplitter"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    eivor = scenario.creature("Eivor, Battle-Ready")
    bob = scenario.player("bob")
    life_before = bob.life

    scenario.attack_with(eivor)
    scenario.resolve_top()

    assert bob.life == life_before - 2
