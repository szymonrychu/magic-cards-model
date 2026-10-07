""" "Deals that much damage to each opponent" - one reader, four ways to say
how much "that much" is, and who deals it.

- Pain for All: "Whenever enchanted creature is dealt damage, it deals that
  much damage to each opponent." - the damage dealt to the enchanted
  creature, and "it" (the enchanted creature) is the source.
- Imodane, the Pyrohammer: "Whenever an instant or sorcery spell you control
  that targets only a single creature deals damage to that creature, Imodane
  deals that much damage to each opponent."
- Valakut Exploration: "At the beginning of your end step, if there are
  cards exiled with this enchantment, put them into their owner's
  graveyard, then this enchantment deals that much damage to each opponent."
- Tellah, Great Sage: "... If eight or more mana was spent to cast that
  spell, sacrifice Tellah and it deals that much damage to each opponent."

Second printings: Spiteful Shadows ("Whenever enchanted creature is dealt
damage, it deals that much damage to its controller."), Coalhauler Swine
("Whenever this creature is dealt damage, it deals that much damage to each
player.") and Magmakin Artillerist ("Whenever you discard one or more cards,
this creature deals that much damage to each opponent."). No other legal
printing has Imodane's single-creature spell condition, Valakut's linked
"put them into their owner's graveyard, then" or Tellah's mana-spent "that
much" - see MEMORY.md.

Rules verified with `mise run rules:find`:

- **CR 120.3** - the source's characteristics (lifelink) shape the damage.
- **CR 303.4b** - "enchanted creature" is the object the Aura is attached to.
- **CR 607.1** - "cards exiled with this enchantment" is a linked pile.
- **CR 608.2h** - a source that has left deals damage as it last existed.
- **CR 603.2c** - one discard of two cards is one event.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.effects import attach_permanent
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario

LANDS = ["Mountain"] * 6 + ["Island"] * 2 + ["Swamp"] * 2


def _drain(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _notices(scenario) -> list[object]:
    game = scenario.game
    found: list[object] = list(game.continuous_effects.layer_notices)
    for name in type(game).model_fields:
        if name.endswith("_notices"):
            found.extend(getattr(game, name))
    return found


def _walk_to(scenario, step: Step) -> None:
    while scenario.step is not step:
        scenario.advance()
        _drain(scenario)


def _main(alice=(), bob=(), hand=(), library=(), bob_hand=()) -> object:
    scenario = (
        Scenario()
        .player("alice", battlefield=[*LANDS, *alice], hand=list(hand), library=list(library))
        .player("bob", battlefield=["Mountain", "Mountain", *bob], hand=list(bob_hand))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _outcomes(name: str) -> list[str]:
    return [c.outcome for c in card_support(card(name)).clauses if c.kind != "keyword"]


def test_every_listed_and_proof_card_reads_handled():
    for name in (
        "Pain for All",
        "Imodane, the Pyrohammer",
        "Valakut Exploration",
        "Tellah, Great Sage",
        "Spiteful Shadows",
        "Coalhauler Swine",
        "Magmakin Artillerist",
    ):
        assert set(_outcomes(name)) == {"handled"}, (name, _outcomes(name))


# -- Pain for All: "it" is the enchanted creature --------------------------------


def _pain_for_all(creature: str):
    scenario = _main(alice=["Pain for All", creature], hand=["Shock"])
    host = scenario.creature(creature, "alice")
    attach_permanent(scenario.game, scenario.find("Pain for All", Zone.BATTLEFIELD), host)
    return scenario, host


def test_pain_for_all_redeals_the_damage_to_each_opponent():
    scenario, host = _pain_for_all("Colossal Dreadmaw")
    scenario.cast_onto_stack("Shock", targets=[host], auto=True)
    _drain(scenario)
    assert host.damage == 2
    assert scenario.player("bob").life == 18
    assert scenario.player("alice").life == 20


def test_pain_for_all_the_enchanted_creature_is_the_source_lifelink():
    scenario, host = _pain_for_all("Vampire Nighthawk")
    scenario.cast_onto_stack("Shock", targets=[host], auto=True)
    _drain(scenario)
    assert scenario.player("bob").life == 18
    assert scenario.player("alice").life == 22


def test_pain_for_all_a_creature_killed_by_the_damage_still_deals_it():
    """CR 608.2h: the Bears die to the Shock; their last known self deals 2."""
    scenario, host = _pain_for_all("Grizzly Bears")
    scenario.cast_onto_stack("Shock", targets=[host], auto=True)
    _drain(scenario)
    assert host.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 18


def test_pain_for_all_damage_to_another_creature_does_nothing():
    scenario, host = _pain_for_all("Colossal Dreadmaw")
    scenario.cast_onto_stack("Shock", targets=["bob"], auto=True)
    _drain(scenario)
    assert host.damage == 0
    assert scenario.player("bob").life == 18, "only the Shock itself"


def test_spiteful_shadows_proof_redeals_to_the_creatures_controller():
    scenario = _main(alice=["Spiteful Shadows"], bob=["Colossal Dreadmaw"], hand=["Lightning Bolt"])
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    attach_permanent(scenario.game, scenario.find("Spiteful Shadows", Zone.BATTLEFIELD), dreadmaw)
    scenario.cast_onto_stack("Lightning Bolt", targets=[dreadmaw], auto=True)
    _drain(scenario)
    assert scenario.player("bob").life == 17
    assert scenario.player("alice").life == 20


def test_coalhauler_swine_proof_redeals_to_each_player():
    scenario = _main(bob=["Coalhauler Swine"], hand=["Lightning Bolt"])
    swine = scenario.creature("Coalhauler Swine", "bob")
    scenario.cast_onto_stack("Lightning Bolt", targets=[swine], auto=True)
    _drain(scenario)
    assert scenario.player("bob").life == 17
    assert scenario.player("alice").life == 17


def test_magmakin_artillerist_proof_one_discard_of_two_cards_is_one_trigger():
    scenario = _main(
        alice=["Magmakin Artillerist"],
        hand=["Faithless Looting"],
        library=["Grizzly Bears", "Hill Giant", "Craw Wurm"],
    )
    scenario.will_choose_cards(
        scenario.find("Grizzly Bears", Zone.LIBRARY), scenario.find("Hill Giant", Zone.LIBRARY)
    )
    scenario.cast_onto_stack("Faithless Looting", auto=True)
    _drain(scenario)
    assert scenario.player("bob").life == 18
    assert scenario.player("alice").life == 20


# -- Imodane ----------------------------------------------------------------------


def test_imodane_redeals_a_single_target_spells_damage_to_each_opponent():
    scenario = _main(
        alice=["Imodane, the Pyrohammer"], bob=["Colossal Dreadmaw"], hand=["Lightning Bolt"]
    )
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    scenario.cast_onto_stack("Lightning Bolt", targets=[dreadmaw], auto=True)
    _drain(scenario)
    assert dreadmaw.damage == 3
    assert scenario.player("bob").life == 17


def test_imodane_triggers_on_its_controllers_own_creature_too():
    scenario = _main(alice=["Imodane, the Pyrohammer", "Colossal Dreadmaw"], hand=["Shock"])
    dreadmaw = scenario.creature("Colossal Dreadmaw", "alice")
    scenario.cast_onto_stack("Shock", targets=[dreadmaw], auto=True)
    _drain(scenario)
    assert scenario.player("bob").life == 18
    assert scenario.player("alice").life == 20


def test_imodane_ignores_a_spell_aimed_at_a_player():
    scenario = _main(alice=["Imodane, the Pyrohammer"], hand=["Lightning Bolt"])
    scenario.cast_onto_stack("Lightning Bolt", targets=["bob"], auto=True)
    _drain(scenario)
    assert scenario.player("bob").life == 17, "the Bolt only"


def test_imodane_ignores_a_spell_with_two_targets():
    scenario = _main(
        alice=["Imodane, the Pyrohammer"], bob=["Colossal Dreadmaw"], hand=["Arc Trail"]
    )
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    scenario.cast_onto_stack("Arc Trail", targets=[dreadmaw, "bob"], auto=True)
    _drain(scenario)
    assert dreadmaw.damage == 2
    assert scenario.player("bob").life == 19, "Arc Trail's 1 only - it targets two things"


def test_imodane_ignores_an_opponents_spell():
    scenario = _main(alice=["Imodane, the Pyrohammer", "Colossal Dreadmaw"], bob_hand=["Shock"])
    dreadmaw = scenario.creature("Colossal Dreadmaw", "alice")
    scenario.pass_priority("alice")
    scenario.cast_onto_stack("Shock", username="bob", targets=[dreadmaw], auto=True)
    _drain(scenario)
    assert dreadmaw.damage == 2
    assert scenario.player("bob").life == 20 and scenario.player("alice").life == 20


# -- Valakut Exploration: the linked pile ---------------------------------------------


def _valakut(library: list[str]):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Valakut Exploration"],
            hand=["Mountain", "Mountain"],
            library=library,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_valakut_exploration_bins_the_pile_and_deals_that_much():
    scenario = _valakut(["Grizzly Bears", "Hill Giant"])
    scenario.play_land("Mountain")
    _drain(scenario)
    assert scenario.find("Grizzly Bears", Zone.EXILE) is not None
    _walk_to(scenario, Step.END_STEP)
    assert scenario.find("Grizzly Bears", Zone.GRAVEYARD) is not None
    assert scenario.player("bob").life == 19
    assert _notices(scenario) == []


def test_valakut_exploration_with_nothing_exiled_does_not_trigger():
    scenario = _valakut(["Grizzly Bears", "Hill Giant"])
    _walk_to(scenario, Step.END_STEP)
    assert scenario.player("bob").life == 20
    assert _notices(scenario) == []


def test_valakut_exploration_a_card_played_from_the_pile_does_not_count():
    """The land played from exile left the pile (CR 607.1): only what is
    still exiled with the enchantment is binned and counted."""
    scenario = _valakut(["Mountain", "Grizzly Bears"])
    scenario.play_land("Mountain")
    _drain(scenario)
    exiled = scenario.find("Mountain", Zone.EXILE)
    assert exiled is not None
    _walk_to(scenario, Step.END_STEP)
    assert scenario.player("bob").life == 19


# -- Tellah: mana spent on the triggering spell -------------------------------------------


def _tellah():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Tellah, Great Sage", *(["Mountain"] * 8)],
            hand=["Banefire"],
            library=["Island", "Island", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_banefire(scenario, x: int) -> None:
    casting = scenario.cast("Banefire", targets=["bob"])
    casting.determine_cost(x_value=x)
    scenario.auto_pay(casting.begin_paying(), username="alice")
    scenario.put_on_stack(casting)


def test_tellah_eight_mana_sacrifices_and_deals_that_much():
    scenario = _tellah()
    _cast_banefire(scenario, 7)
    _drain(scenario)
    assert scenario.find("Tellah, Great Sage", Zone.GRAVEYARD) is not None
    assert scenario.player("bob").life == 20 - 8 - 7
    assert len(scenario.player("alice").hand) == 2
    assert _notices(scenario) == []


def test_tellah_four_mana_draws_but_keeps_tellah():
    scenario = _tellah()
    _cast_banefire(scenario, 3)
    _drain(scenario)
    assert scenario.creature("Tellah, Great Sage", "alice").zone is Zone.BATTLEFIELD
    assert scenario.player("bob").life == 17
    assert len(scenario.player("alice").hand) == 2


def test_tellah_cheap_spell_only_makes_a_hero():
    scenario = _tellah()
    _cast_banefire(scenario, 1)
    _drain(scenario)
    assert scenario.player("bob").life == 19
    assert len(scenario.player("alice").hand) == 0
    heroes = [p for p in scenario.game.battlefield if p.name.startswith("Hero")]
    assert len(heroes) == 1
