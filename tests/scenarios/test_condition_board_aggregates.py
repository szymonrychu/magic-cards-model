"""Board aggregates: a condition on a total, a spread or a superlative across
permanents - "creatures you control have total power 8 or greater", "there are
five colors among permanents you control", "a creature with the greatest power
among creatures on the battlefield", "four or more Demons with different
names".

Rules verified with `mise run rules:find` in the session that wrote this file:

- **CR 613.5** - every total reads the board with every continuous effect
  applied: an Aura's own bonus counts the moment it is attached.
- **CR 603.4** / **CR 608.2a** - the intervening "if" is checked as the event
  occurs and again as the ability resolves.
- **CR 602.5b** - an activation restriction keeps applying after the
  object's controller changes; **CR 109.5** makes "you" the activator.
- **CR 105.2c** - a colorless object has no color, so it adds none to "colors
  among permanents".
- **CR 303.4** - an Aura's "enchanted permanent" is the object it is attached
  to.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.triggers import intervening_if_answer, triggered_abilities_of
from tests.cards import card
from tests.scenarios.harness import Scenario

RESTRICTION_NOT_MET = "{}'s activation restriction is not met (CR 602.5b)"


def _board(alice, bob=None, *, hand=None, bob_hand=None, library=None):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=alice, hand=hand or [], library=library or ["Plains"] * 6)
        .player("bob", battlefield=bob or [], hand=bob_hand or [], library=["Plains"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _holds(scenario, name: str, owner: str = "alice") -> bool | None:
    (ability,) = [a for a in triggered_abilities_of(card(name)) if a.intervening_if]
    return intervening_if_answer(scenario.game, ability, scenario.creature(name, owner), None)


# -- "Activate only if creatures you control have total power 8 or greater" ----


def test_total_power_below_eight_refuses_formidable():
    """Dragon-Scarred Bear: "Formidable - {1}{G}: Regenerate this creature.
    Activate only if creatures you control have total power 8 or greater."
    3 + 3 is 6."""
    scenario = _board(["Dragon-Scarred Bear", "Hill Giant", "Forest", "Forest"])
    bear = scenario.creature("Dragon-Scarred Bear")
    assert scenario.why_cannot_activate(bear) == RESTRICTION_NOT_MET.format("Dragon-Scarred Bear")


def test_total_power_of_eight_allows_formidable():
    """3 + 6 is 9: activatable, and the regeneration shield lands."""
    scenario = _board(["Dragon-Scarred Bear", "Craw Wurm", "Forest", "Forest"])
    bear = scenario.creature("Dragon-Scarred Bear")
    assert scenario.why_cannot_activate(bear) is None
    scenario.activate(bear, *scenario.untapped_sources("Forest", "Forest"))
    scenario.pass_until_resolved()
    assert bear.regeneration_shields == 1


def test_total_power_reads_the_computed_board():
    """CR 613.5: Giant Growth's +3/+3 lifts 3 + 3 to 9 until end of turn."""
    scenario = _board(
        ["Dragon-Scarred Bear", "Hill Giant", "Forest", "Forest", "Forest"],
        hand=["Giant Growth"],
    )
    bear = scenario.creature("Dragon-Scarred Bear")
    assert scenario.why_cannot_activate(bear) is not None
    scenario.cast_and_resolve("Giant Growth", *scenario.untapped_sources("Forest"), targets=[bear])
    assert scenario.why_cannot_activate(bear) is None


def test_only_creatures_you_control_are_totalled():
    """An opponent's Craw Wurm adds nothing to alice's total."""
    scenario = _board(["Dragon-Scarred Bear", "Hill Giant"], ["Craw Wurm"])
    assert scenario.why_cannot_activate(scenario.creature("Dragon-Scarred Bear")) is not None


def test_total_power_follows_the_activator_after_a_control_change():
    """CR 602.5b: bob takes Dragon-Scarred Bear with Act of Treason; alice's
    Craw Wurm is no longer on the activator's side."""
    scenario = _board(
        ["Dragon-Scarred Bear", "Craw Wurm"],
        ["Mountain", "Mountain", "Mountain", "Forest", "Forest"],
        bob_hand=["Act of Treason"],
    )
    bear = scenario.creature("Dragon-Scarred Bear")
    assert scenario.why_cannot_activate(bear) is None
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Act of Treason",
        *scenario.untapped_sources("Mountain", "Mountain", "Mountain", username="bob"),
        targets=[bear],
        username="bob",
    )
    assert scenario.why_cannot_activate(bear, username="bob") == RESTRICTION_NOT_MET.format(
        "Dragon-Scarred Bear"
    )


def test_total_power_on_a_second_printing():
    """Atarka Beastbreaker prints the same restriction."""
    scenario = _board(["Atarka Beastbreaker", "Grizzly Bears", *["Forest"] * 5])
    assert scenario.why_cannot_activate(scenario.creature("Atarka Beastbreaker")) is not None
    scenario = _board(["Atarka Beastbreaker", "Craw Wurm", *["Forest"] * 5])
    assert scenario.why_cannot_activate(scenario.creature("Atarka Beastbreaker")) is None


def test_total_power_on_an_attack_trigger():
    """Stampeding Elk Herd (5): "Whenever this creature attacks, if creatures
    you control have total power 8 or greater" - with Hill Giant (3) it is 8."""
    scenario = _board(["Stampeding Elk Herd", "Grizzly Bears"])
    assert _holds(scenario, "Stampeding Elk Herd") is False
    scenario = _board(["Stampeding Elk Herd", "Hill Giant"])
    assert _holds(scenario, "Stampeding Elk Herd") is True


# -- formidable on an attack trigger: the three moments ------------------------


def _elk_board():
    scenario = _board(["Stampeding Elk Herd", "Hill Giant", "Mountain"], hand=["Lightning Bolt"])
    for name in ("Stampeding Elk Herd", "Hill Giant"):
        scenario.creature(name).summoning_sick = False
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario


def _has_trample(scenario, name: str) -> bool:
    from magic_cards_model.machines.combat import has_keyword

    return has_keyword(scenario.creature(name), "trample", scenario.game)


def test_formidable_false_as_it_attacks_never_triggers():
    """CR 603.4: the Elk Herd (5) attacks alone - Hill Giant stays home but
    still counts, so bolt it first: 5 is under 8."""
    scenario = _elk_board()
    scenario.cast_and_resolve(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain"),
        targets=[scenario.creature("Hill Giant")],
    )
    scenario.attack_with(scenario.creature("Stampeding Elk Herd"))
    assert scenario.stack_names() == []
    assert scenario.game.intervening_if_notices == []


def test_formidable_true_then_false_by_resolution_does_nothing():
    """CR 608.2a: 5 + 3 as it attacks; Hill Giant bolted with the trigger on
    the stack - no trample."""
    scenario = _elk_board()
    scenario.attack_with(scenario.creature("Stampeding Elk Herd"))
    assert scenario.stack_names() == ["Stampeding Elk Herd's triggered ability"]
    scenario.cast_and_resolve(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain"),
        targets=[scenario.creature("Hill Giant")],
    )
    scenario.pass_until_resolved()
    assert scenario.game.stack_is_empty
    assert not _has_trample(scenario, "Stampeding Elk Herd")


def test_formidable_true_at_both_times_resolves():
    scenario = _elk_board()
    scenario.attack_with(scenario.creature("Stampeding Elk Herd"))
    scenario.pass_until_resolved()
    assert _has_trample(scenario, "Stampeding Elk Herd")
    assert _has_trample(scenario, "Hill Giant")


def test_total_toughness():
    """Betor, Kin to All (7 toughness): "if creatures you control have total
    toughness 10 or greater" - Wall of Omens (4) makes 11."""
    scenario = _board(["Betor, Kin to All"])
    assert _holds(scenario, "Betor, Kin to All") is False
    scenario = _board(["Betor, Kin to All", "Wall of Omens"])
    assert _holds(scenario, "Betor, Kin to All") is True


# -- "there are five colors among permanents you control" ---------------------


FIVE_COLORS = ["Dawnhart Wardens", "Zegana, Utopian Speaker", "Goblin Bird-Grabber", "Ophiomancer"]


def test_five_colors_among_permanents_allows_the_draw():
    """Puca's Eye: "{3}, {T}: Draw a card. Activate only if there are five
    colors among permanents you control." - white and green, green and blue,
    red, black."""
    scenario = _board(["Puca's Eye", *FIVE_COLORS, *["Plains"] * 3])
    eye = scenario.creature("Puca's Eye")
    assert scenario.why_cannot_activate(eye) is None


def test_four_colors_refuses_it():
    scenario = _board(["Puca's Eye", *FIVE_COLORS[:3], *["Plains"] * 3])
    eye = scenario.creature("Puca's Eye")
    assert scenario.why_cannot_activate(eye) == RESTRICTION_NOT_MET.format("Puca's Eye")


def test_an_opponents_colors_do_not_count():
    scenario = _board(["Puca's Eye", *FIVE_COLORS[:3], *["Plains"] * 3], ["Ophiomancer"])
    assert scenario.why_cannot_activate(scenario.creature("Puca's Eye")) is not None


def test_colorless_is_not_a_sixth_color():
    """CR 105.2c: Ornithopter is colorless; with four colors it is still four."""
    scenario = _board(["Puca's Eye", *FIVE_COLORS[:3], "Ornithopter", *["Plains"] * 3])
    assert scenario.why_cannot_activate(scenario.creature("Puca's Eye")) is not None


def test_five_colors_follows_the_activator_after_a_control_change():
    """CR 602.5b / CR 109.5: bob takes Puca's Eye with Hijack ("Gain control
    of target artifact or creature until end of turn"); alice's five colors
    are not his, so he cannot activate it."""
    scenario = _board(
        ["Puca's Eye", *FIVE_COLORS],
        ["Mountain", "Mountain", "Mountain", "Plains", "Plains", "Plains"],
        bob_hand=["Hijack"],
    )
    eye = scenario.creature("Puca's Eye")
    assert scenario.why_cannot_activate(eye) is None
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Hijack",
        *scenario.untapped_sources("Mountain", "Mountain", "Mountain", username="bob"),
        targets=[eye],
        username="bob",
    )
    assert scenario.game.controller_of(eye).username == "bob"
    assert scenario.why_cannot_activate(eye, username="bob") == RESTRICTION_NOT_MET.format(
        "Puca's Eye"
    )


def test_five_colors_on_a_second_printing():
    """Happily Ever After prints the same clause as one of its three halves;
    read alone through the shared reader."""
    scenario = _board(["Happily Ever After", *FIVE_COLORS])
    game = scenario.game
    assert game.condition_holds("alice", "there are five colors among permanents you control")
    scenario = _board(["Happily Ever After", *FIVE_COLORS[:2]])
    assert (
        scenario.game.condition_holds("alice", "there are five colors among permanents you control")
        is False
    )


# -- "enchanted permanent is a creature with the greatest power ..." ---------


def _wisdom_board(bob: list[str]):
    return _board(
        ["Grizzly Bears", "Forest", "Forest", "Forest"],
        bob,
        hand=["Historian's Wisdom"],
        library=["Plains"] * 6,
    )


def test_the_enchanted_creature_with_the_greatest_power_draws():
    """Historian's Wisdom: "When this Aura enters, if enchanted permanent is a
    creature with the greatest power among creatures on the battlefield, draw
    a card." - on Grizzly Bears (2) against bob's Llanowar Elves (1)."""
    scenario = _wisdom_board(["Llanowar Elves"])
    bears = scenario.creature("Grizzly Bears")
    hand_before = len(scenario.player("alice").hand)
    scenario.cast_and_resolve(
        "Historian's Wisdom",
        *scenario.untapped_sources("Forest", "Forest", "Forest"),
        targets=[bears],
    )
    assert scenario.stack_names() == ["Historian's Wisdom's triggered ability"]
    scenario.pass_until_resolved()
    # The Aura left the hand, the draw put a card back.
    assert len(scenario.player("alice").hand) == hand_before


def test_an_enchanted_noncreature_is_not_a_creature_with_the_greatest_power():
    """Historian's Wisdom enchants an artifact too: Ornithopter is a creature,
    Mind Stone is not."""
    scenario = _board(["Mind Stone", "Forest", "Forest", "Forest"], hand=["Historian's Wisdom"])
    scenario.cast_and_resolve(
        "Historian's Wisdom",
        *scenario.untapped_sources("Forest", "Forest", "Forest"),
        targets=[scenario.creature("Mind Stone")],
    )
    assert scenario.stack_names() == []
    assert scenario.game.intervening_if_notices == []


def test_a_bigger_creature_elsewhere_stops_it():
    """Bob's Craw Wurm (6) beats Grizzly Bears: no trigger (CR 603.4)."""
    scenario = _wisdom_board(["Craw Wurm"])
    bears = scenario.creature("Grizzly Bears")
    scenario.cast_and_resolve(
        "Historian's Wisdom",
        *scenario.untapped_sources("Forest", "Forest", "Forest"),
        targets=[bears],
    )
    assert scenario.stack_names() == []
    assert scenario.game.intervening_if_notices == []


def test_a_tie_for_the_greatest_is_the_greatest():
    """Bob's Grizzly Bears ties the enchanted Bears at 2."""
    scenario = _wisdom_board(["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_and_resolve(
        "Historian's Wisdom",
        *scenario.untapped_sources("Forest", "Forest", "Forest"),
        targets=[bears],
    )
    assert scenario.stack_names() == ["Historian's Wisdom's triggered ability"]


# -- "N or more <quality> with different names" ------------------------------


def test_demons_with_different_names():
    """Liliana's Contract: "if you control four or more Demons with different
    names" - two copies of one Demon count once."""
    demons = ["Griselbrand", "Archfiend of Ifnir", "Master of the Feast"]
    scenario = _board(["Liliana's Contract", *demons, "Griselbrand"])
    assert _holds(scenario, "Liliana's Contract") is False
    scenario = _board(["Liliana's Contract", *demons, "Curse-Marred Demon"])
    assert _holds(scenario, "Liliana's Contract") is True
