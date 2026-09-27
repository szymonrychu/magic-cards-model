"""Keywords a permanent grants to spells and to cards in hand
(`machines/spell_grants.py`).

The printed shapes, each a CR 604.2 static ability reaching out at objects
its controller casts or holds:

- "Instant and sorcery spells you cast have storm." (Prismari, the
  Inspiration) - CR 702.40a: "Storm is a triggered ability that functions on
  the stack. 'Storm' means 'When you cast this spell, copy it for each other
  spell that was cast before it this turn. ...'"
- "Instant and sorcery spells you cast from your hand have cascade."
  (Quandrix, the Proof), "Sliver spells you cast have cascade." (The First
  Sliver) and "The first spell you cast each turn has cascade." (Maelstrom
  Nexus) - CR 702.85a: "Cascade is a triggered ability that functions only
  while the spell with cascade is on the stack." CR 702.85c: "If a spell has
  multiple instances of cascade, each triggers separately."
- "Instant and sorcery spells you cast have affinity for creatures."
  (Witherbloom, the Balancer) and "Spells you cast have affinity for
  artifacts." (Sami, Wildcat Captain) - CR 702.41a: "Affinity is a static
  ability that functions while the spell with affinity is on the stack.
  'Affinity for [text]' means 'This spell costs {1} less to cast for each
  [text] you control.'" Applied during total cost determination, CR 601.2f.
- "Each instant and sorcery spell you cast has casualty 1." (Silverquill,
  the Disputant) - CR 702.153a, the additional cost chosen as the spell is
  cast (CR 601.2b).
- "Each instant and sorcery card in your hand has miracle {2}." (Lorehold,
  the Historian) - CR 702.94a: "You may reveal this card from your hand as
  you draw it if it's the first card you've drawn this turn." The grant has
  to be in force *as the card is drawn*.

CR 707.10: "a copy of a spell isn't cast", so no copy is ever one of "the
spells you cast". CR 611.3a: a static ability's effect "isn't 'locked in';
it applies at any given moment to whatever its text indicates".

Every CR number here was read whole with `mise run rules:find` in the
session that wrote this file: 601.2b, 601.2f, 611.3a, 702.40a, 702.41a,
702.85a, 702.85c, 702.94a, 702.153a, 707.10.

Proof printings off the api deck pool: Sami, Wildcat Captain (affinity for
artifacts on every spell), The First Sliver (a subtype-quality cascade grant)
and Maelstrom Nexus (the first-spell-each-turn shape).
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.spell_grants import (
    reads_spell_keyword_grant_line,
    spell_keyword_grant,
)
from magic_cards_model.models import ManaCost, Zone
from tests.scenarios.harness import PlayedScenario, Scenario


def resolve_everything(scenario: PlayedScenario) -> None:
    while scenario.game.stack:
        scenario.resolve_top()


def keyword_triggers(scenario: PlayedScenario, keyword: str) -> list:
    return [
        item
        for item in [*scenario.game.stack, *scenario.game.pending_triggers]
        if getattr(item, "is_ability", False)
        and (getattr(item.ability, "keyword", None) or "").lower() == keyword
    ]


# -- the reader ----------------------------------------------------------------


def test_each_printed_grant_reads_as_its_keyword_line():
    assert spell_keyword_grant("Instant and sorcery spells you cast have storm.").line == "Storm"
    cascade = spell_keyword_grant(
        "Instant and sorcery spells you cast from your hand have cascade."
    )
    assert cascade.line == "Cascade" and cascade.from_zone is Zone.HAND
    assert (
        spell_keyword_grant("Each instant and sorcery spell you cast has casualty 1.").line
        == "Casualty 1"
    )
    assert (
        spell_keyword_grant("Instant and sorcery spells you cast have affinity for creatures.").line
        == "Affinity for creatures"
    )
    assert (
        spell_keyword_grant("Each instant and sorcery card in your hand has miracle {2}.").line
        == "Miracle {2}"
    )
    assert spell_keyword_grant("The first spell you cast each turn has cascade.").subject == (
        "first_spell"
    )


def test_a_keyword_no_machine_here_executes_is_not_read_as_a_grant():
    """Convoke and an affinity whose "[text]" nothing counts are left to
    whatever reads them - never credited on a guess. (Conspire is read since
    ecl T7: `tests/scenarios/test_conspire_grant.py`.)"""
    assert not reads_spell_keyword_grant_line("Creature spells you cast have convoke.")
    assert not reads_spell_keyword_grant_line(
        "Enchantment spells you cast have affinity for Auras."
    )


# -- storm (Prismari, the Inspiration) ----------------------------------------------


def storm_board(**alice: object) -> PlayedScenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=alice.get("hand", ["Lightning Bolt", "Lightning Bolt", "Lightning Bolt"]),
            battlefield=alice.get(
                "battlefield", ["Prismari, the Inspiration", "Mountain", "Mountain", "Mountain"]
            ),
        )
        .player("bob", life=20, hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def bolt_bob(scenario: PlayedScenario) -> None:
    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.cast_onto_stack("Lightning Bolt", mountain, targets=["bob"])


def test_an_instant_cast_under_prismari_has_storm():
    """Third Bolt of the turn: its granted storm copies it twice."""
    scenario = storm_board()
    bob = scenario.player("bob")
    bolt_bob(scenario)
    resolve_everything(scenario)
    bolt_bob(scenario)
    resolve_everything(scenario)
    assert bob.life == 20 - 3 - 6

    bolt_bob(scenario)
    assert len(keyword_triggers(scenario, "storm")) == 1
    resolve_everything(scenario)

    assert bob.life == 20 - 3 - 6 - 9


def test_the_first_spell_of_the_turn_storms_for_nothing():
    scenario = storm_board()
    bob = scenario.player("bob")
    bolt_bob(scenario)
    assert len(keyword_triggers(scenario, "storm")) == 1
    resolve_everything(scenario)
    assert bob.life == 17


def test_a_creature_spell_is_not_an_instant_or_sorcery_spell():
    scenario = storm_board(
        hand=["Grizzly Bears"],
        battlefield=["Prismari, the Inspiration", "Forest", "Forest"],
    )
    scenario.cast_onto_stack("Grizzly Bears", *scenario.untapped_sources("Forest", "Forest"))
    assert keyword_triggers(scenario, "storm") == []


def test_an_opponents_spell_is_not_a_spell_you_cast():
    scenario = storm_board()
    scenario.pass_priority("alice")
    (bob_mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_onto_stack("Lightning Bolt", bob_mountain, username="bob", targets=["alice"])
    assert keyword_triggers(scenario, "storm") == []


def test_without_prismari_on_the_battlefield_nothing_is_granted():
    scenario = storm_board(battlefield=["Mountain", "Mountain", "Mountain"])
    bolt_bob(scenario)
    resolve_everything(scenario)
    bolt_bob(scenario)
    assert keyword_triggers(scenario, "storm") == []


def test_a_printed_storm_and_a_granted_one_each_trigger():
    """Grapeshot already has storm; Prismari gives it a second instance, and
    each instance triggers on its own - two copies per earlier spell."""
    scenario = storm_board(
        hand=["Lightning Bolt", "Grapeshot"],
        battlefield=["Prismari, the Inspiration", "Mountain", "Mountain", "Mountain"],
    )
    bob = scenario.player("bob")
    bolt_bob(scenario)
    resolve_everything(scenario)
    scenario.cast_onto_stack(
        "Grapeshot", *scenario.untapped_sources("Mountain", "Mountain"), targets=["bob"]
    )
    assert len(keyword_triggers(scenario, "storm")) == 2
    resolve_everything(scenario)
    # Bolt 3, then Grapeshot plus one copy from each storm instance: 3 more.
    assert bob.life == 20 - 3 - 3


def test_storm_copies_are_not_cast_so_they_never_storm_again():
    scenario = storm_board()
    bob = scenario.player("bob")
    bolt_bob(scenario)
    resolve_everything(scenario)
    bolt_bob(scenario)
    # One trigger for the one cast Bolt; its copy puts no second one up.
    scenario.resolve_top()
    assert len(keyword_triggers(scenario, "storm")) == 0
    resolve_everything(scenario)
    assert bob.life == 20 - 3 - 6


def test_the_storm_trigger_resolves_even_if_prismari_leaves():
    """CR 611.3a asks the grant as the spell is cast; once storm has
    triggered, losing Prismari takes nothing back."""
    scenario = storm_board()
    bob = scenario.player("bob")
    bolt_bob(scenario)
    resolve_everything(scenario)
    bolt_bob(scenario)
    prismari = scenario.creature("Prismari, the Inspiration", "alice")
    scenario.game.sacrifice(prismari)
    resolve_everything(scenario)
    assert bob.life == 20 - 3 - 6


# -- cascade (Quandrix, the Proof) ---------------------------------------------------


def quandrix_board(*library: str, hand: list[str], graveyard: list[str] | None = None):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=hand,
            graveyard=graveyard or [],
            library=list(library),
            battlefield=["Quandrix, the Proof", "Island", "Island", "Island", "Island"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_a_sorcery_cast_from_hand_under_quandrix_cascades():
    scenario = quandrix_board("Island", "Opt", "Island", hand=["Divination"])
    scenario.cast_onto_stack("Divination", *scenario.untapped_sources("Island", "Island", "Island"))
    assert len(keyword_triggers(scenario, "cascade")) == 1

    scenario.resolve_top()

    assert [state.name for state in scenario.game.stack] == ["Divination", "Opt"]


def test_the_cascade_hit_is_cast_from_exile_so_it_does_not_cascade_again():
    """The hit is cast from exile, not from a hand: Quandrix's "from your
    hand" does not reach it."""
    scenario = quandrix_board("Opt", "Island", hand=["Divination"])
    scenario.cast_onto_stack("Divination", *scenario.untapped_sources("Island", "Island", "Island"))
    scenario.resolve_top()
    assert scenario.game.stack[-1].name == "Opt"
    assert keyword_triggers(scenario, "cascade") == []


def test_a_spell_cast_from_the_graveyard_is_not_cast_from_your_hand():
    scenario = quandrix_board("Opt", "Island", hand=[], graveyard=["Plunder the Trollshaws"])
    casting = scenario.cast("Plunder the Trollshaws", from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Flashback")
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Island", "Island", "Island", "Island"))
    scenario.put_on_stack(casting)
    assert keyword_triggers(scenario, "cascade") == []


def test_a_printed_cascade_and_the_granted_one_each_trigger():
    """CR 702.85c: Violent Outburst prints cascade and Quandrix grants a
    second instance - two triggers."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Violent Outburst"],
            library=["Opt", "Opt", "Island"],
            battlefield=["Quandrix, the Proof", "Forest", "Mountain", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_onto_stack(
        "Violent Outburst", *scenario.untapped_sources("Forest", "Mountain", "Forest")
    )
    assert len(keyword_triggers(scenario, "cascade")) == 2


def test_a_creature_spell_under_quandrix_does_not_cascade():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Grizzly Bears"],
            library=["Opt", "Island"],
            battlefield=["Quandrix, the Proof", "Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_onto_stack("Grizzly Bears", *scenario.untapped_sources("Forest", "Forest"))
    assert keyword_triggers(scenario, "cascade") == []


def test_the_first_sliver_gives_only_sliver_spells_cascade():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Sliver Construct", "Grizzly Bears"],
            library=["Opt", "Island", "Island"],
            battlefield=["The First Sliver", "Forest", "Forest", "Forest", "Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_onto_stack(
        "Sliver Construct", *scenario.untapped_sources("Forest", "Forest", "Forest")
    )
    assert len(keyword_triggers(scenario, "cascade")) == 1
    resolve_everything(scenario)

    scenario.cast_onto_stack("Grizzly Bears", *scenario.untapped_sources("Forest", "Forest"))
    assert keyword_triggers(scenario, "cascade") == []


def nexus_board() -> PlayedScenario:
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Divination", "Divination"],
            library=["Island", "Opt", "Island", "Island", "Island", "Island"],
            battlefield=["Maelstrom Nexus"] + ["Island"] * 6,
        )
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_maelstrom_nexus_gives_the_first_spell_of_the_turn_cascade():
    scenario = nexus_board()
    scenario.cast_onto_stack("Divination", *scenario.untapped_sources("Island", "Island", "Island"))
    assert len(keyword_triggers(scenario, "cascade")) == 1


def test_maelstrom_nexus_leaves_the_second_spell_alone():
    scenario = nexus_board()
    scenario.cast_onto_stack("Divination", *scenario.untapped_sources("Island", "Island", "Island"))
    resolve_everything(scenario)
    scenario.cast_onto_stack("Divination", *scenario.untapped_sources("Island", "Island", "Island"))
    assert keyword_triggers(scenario, "cascade") == []


def test_maelstrom_nexus_counts_only_its_controllers_own_spells():
    """ "The first spell *you* cast": bob's Bolt earlier this turn does not
    make alice's Divination her second."""
    scenario = nexus_board()
    scenario.pass_priority("alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=["alice"])
    assert keyword_triggers(scenario, "cascade") == []
    resolve_everything(scenario)
    scenario.cast_onto_stack("Divination", *scenario.untapped_sources("Island", "Island", "Island"))
    assert len(keyword_triggers(scenario, "cascade")) == 1


# -- affinity (Witherbloom, the Balancer; Sami, Wildcat Captain) --------------------


def affinity_board(hand: list[str], battlefield: list[str]) -> PlayedScenario:
    scenario = (
        Scenario()
        .player("alice", hand=hand, battlefield=battlefield)
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_witherbloom_gives_a_sorcery_affinity_for_creatures():
    """Witherbloom and Grizzly Bears are two creatures: Divination {2}{U}
    costs {U}."""
    scenario = affinity_board(
        ["Divination"], ["Witherbloom, the Balancer", "Grizzly Bears", "Island"]
    )
    casting = scenario.cast("Divination")
    assert casting.total_cost.mana == ManaCost.parse("{U}")


def test_affinity_counts_creatures_the_caster_controls_only():
    scenario = affinity_board(["Divination"], ["Witherbloom, the Balancer", "Island"])
    casting = scenario.cast("Divination")
    # Bob's Grizzly Bears is not a creature alice controls.
    assert casting.total_cost.mana == ManaCost.parse("{1}{U}")


def test_affinity_reduces_generic_mana_only():
    scenario = affinity_board(
        ["Lightning Bolt"],
        ["Witherbloom, the Balancer", "Grizzly Bears", "Grizzly Bears", "Mountain"],
    )
    casting = scenario.cast("Lightning Bolt", targets=["bob"])
    assert casting.total_cost.mana == ManaCost.parse("{R}")


def test_witherbloom_does_not_reach_a_creature_spell():
    scenario = affinity_board(
        ["Grizzly Bears"], ["Witherbloom, the Balancer", "Grizzly Bears", "Forest"]
    )
    casting = scenario.cast("Grizzly Bears")
    assert casting.total_cost.mana == ManaCost.parse("{1}{G}")


def test_two_witherblooms_are_two_instances_of_affinity():
    """The ruling: "If a spell has multiple instances of affinity, each one
    applies." Two Witherblooms and nothing else: {4} less."""
    scenario = affinity_board(
        ["Reality Heist"],
        ["Witherbloom, the Balancer", "Witherbloom, the Balancer", "Island"],
    )
    casting = scenario.cast("Reality Heist")
    assert casting.total_cost.mana == ManaCost.parse("{1}{U}{U}")


def test_a_printed_affinity_and_the_granted_one_both_apply():
    """Reality Heist prints affinity for artifacts; Witherbloom adds
    affinity for creatures. {5}{U}{U} less one Ornithopter and two
    creatures (Witherbloom and the Ornithopter): {2}{U}{U}."""
    scenario = affinity_board(
        ["Reality Heist"], ["Witherbloom, the Balancer", "Ornithopter", "Island"]
    )
    casting = scenario.cast("Reality Heist")
    assert casting.total_cost.mana == ManaCost.parse("{2}{U}{U}")


def test_sami_gives_every_spell_affinity_for_artifacts():
    """A different grant: no quality at all, a different "[text]"."""
    scenario = affinity_board(
        ["Grizzly Bears", "Divination"], ["Sami, Wildcat Captain", "Ornithopter", "Memnite"]
    )
    assert scenario.cast("Grizzly Bears").total_cost.mana == ManaCost.parse("{G}")


def test_sami_counts_artifacts_not_creatures():
    scenario = affinity_board(["Divination"], ["Sami, Wildcat Captain", "Grizzly Bears"])
    assert scenario.cast("Divination").total_cost.mana == ManaCost.parse("{2}{U}")


def test_the_affinity_grant_really_pays_for_the_spell():
    """Observable in a payment, not only in the priced number: one Island
    casts Divination under Witherbloom with two creatures."""
    scenario = affinity_board(
        ["Divination"], ["Witherbloom, the Balancer", "Grizzly Bears", "Island"]
    )
    (island,) = scenario.untapped_sources("Island")
    divination = scenario.cast_and_resolve("Divination", island)
    assert divination.zone is Zone.GRAVEYARD


# -- miracle (Lorehold, the Historian) -----------------------------------------------


def lorehold_draw_step(top: str, *, alice_battlefield: list[str]) -> PlayedScenario:
    """Bob plays first and skips his draw (CR 103.8a); stop at alice's upkeep
    with her turn's first draw still to come."""
    scenario = (
        Scenario()
        .player("bob", library=["Island"] * 10, battlefield=["Grizzly Bears"])
        .player(
            "alice",
            library=[top] + ["Plains"] * 10,
            battlefield=alice_battlefield,
        )
        .build()
    )
    scenario.start_at(Step.CLEANUP)
    scenario.advance()  # alice's untap step
    scenario.advance()  # her upkeep
    assert scenario.turn.active_player == "alice" and scenario.step is Step.UPKEEP
    return scenario


def reveal_questions(scenario: PlayedScenario, name: str) -> list:
    return [
        question
        for question in scenario.questions_asked()
        if question.source == name and "reveal" in question.prompt
    ]


def test_lorehold_gives_a_drawn_sorcery_miracle_2():
    """Army of the Damned prints no miracle; under Lorehold it is revealed as
    the turn's first draw and cast for {2} instead of {5}{B}{B}{B}."""
    scenario = lorehold_draw_step(
        "Army of the Damned",
        alice_battlefield=["Lorehold, the Historian", "Mountain", "Mountain"],
    )
    scenario.will_take_the_may(True, username="alice", source="Army of the Damned", times=2)

    scenario.advance()  # the draw step: the draw asks as the card is drawn
    assert len(reveal_questions(scenario, "Army of the Damned")) == 1
    assert len(keyword_triggers(scenario, "miracle")) == 1

    scenario.resolve_top()
    army = scenario.find("Army of the Damned", Zone.STACK)
    assert scenario.game.cast_record_of(army).keyword == "Miracle"
    assert all(
        permanent.tapped for permanent in scenario.game.battlefield if permanent.name == "Mountain"
    )
    scenario.resolve_top()
    zombies = [p for p in scenario.game.battlefield if p.name == "Zombie Token"]
    assert len(zombies) == 13


def test_a_creature_card_in_hand_is_not_granted_miracle():
    scenario = lorehold_draw_step(
        "Grizzly Bears", alice_battlefield=["Lorehold, the Historian", "Mountain", "Mountain"]
    )
    scenario.advance()
    assert reveal_questions(scenario, "Grizzly Bears") == []
    assert keyword_triggers(scenario, "miracle") == []


def test_without_lorehold_the_drawn_sorcery_has_no_miracle():
    scenario = lorehold_draw_step("Army of the Damned", alice_battlefield=["Mountain", "Mountain"])
    scenario.advance()
    assert reveal_questions(scenario, "Army of the Damned") == []


def test_only_the_first_card_drawn_this_turn_can_be_revealed():
    """CR 702.94a: "if it's the first card you've drawn this turn" - the
    draw-step Plains was the first, so a Divination drawn afterwards is not."""
    scenario = (
        Scenario()
        .player("bob", library=["Island"] * 10)
        .player(
            "alice",
            hand=["Opt"],
            library=["Plains", "Army of the Damned"] + ["Plains"] * 10,
            battlefield=["Lorehold, the Historian", "Island", "Mountain", "Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.CLEANUP)
    scenario.advance()
    scenario.advance()
    scenario.advance()  # draw step: the Plains
    scenario.advance()  # main phase
    (island,) = scenario.untapped_sources("Island")
    scenario.cast_and_resolve("Opt", island)
    assert reveal_questions(scenario, "Army of the Damned") == []
    assert keyword_triggers(scenario, "miracle") == []


def test_declining_the_reveal_keeps_the_card_in_hand_and_triggers_nothing():
    scenario = lorehold_draw_step(
        "Army of the Damned", alice_battlefield=["Lorehold, the Historian", "Mountain", "Mountain"]
    )
    scenario.will_take_the_may(False, username="alice", source="Army of the Damned")
    scenario.advance()
    assert keyword_triggers(scenario, "miracle") == []
    assert scenario.find("Army of the Damned", Zone.HAND, "alice").zone is Zone.HAND


def test_a_printed_miracle_and_the_granted_one_are_two_offers():
    """Terminus prints Miracle {W}; Lorehold adds Miracle {2}. Declining the
    printed one's reveal still leaves the granted one to offer, and the cast
    it makes costs {2} - the linked ability's own cost (CR 607.2h's link)."""
    scenario = lorehold_draw_step(
        "Terminus", alice_battlefield=["Lorehold, the Historian", "Mountain", "Mountain"]
    )
    scenario.will_take_the_may(False, username="alice", source="Terminus")
    scenario.will_take_the_may(True, username="alice", source="Terminus", times=2)
    scenario.advance()
    assert len(reveal_questions(scenario, "Terminus")) == 2
    (trigger,) = keyword_triggers(scenario, "miracle")
    assert "{2}" in (trigger.ability.effect or "")

    scenario.resolve_top()
    assert scenario.find("Terminus", Zone.STACK).zone is Zone.STACK
    assert all(
        permanent.tapped for permanent in scenario.game.battlefield if permanent.name == "Mountain"
    )


def test_an_opponents_lorehold_grants_nothing_to_your_hand():
    scenario = (
        Scenario()
        .player("bob", library=["Island"] * 10, battlefield=["Lorehold, the Historian"])
        .player("alice", library=["Army of the Damned"] + ["Plains"] * 10)
        .build()
    )
    scenario.start_at(Step.CLEANUP)
    scenario.advance()  # alice's untap step
    scenario.advance()  # her upkeep: bob's Lorehold's own upkeep trigger
    resolve_everything(scenario)
    scenario.advance()  # her draw
    assert reveal_questions(scenario, "Army of the Damned") == []


# -- casualty (Silverquill, the Disputant) ------------------------------------------


def silverquill_board(hand: list[str], *creatures: str, lands: list[str]) -> PlayedScenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=hand,
            battlefield=["Silverquill, the Disputant", *creatures, *lands],
        )
        .player("bob", life=20, battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_silverquill_gives_an_instant_casualty_1():
    """Sacrifice Llanowar Elves (power 1) as Lightning Bolt is cast: one copy,
    both aimed at bob."""
    scenario = silverquill_board(["Lightning Bolt"], "Llanowar Elves", lands=["Mountain"])
    elves = scenario.creature("Llanowar Elves", "alice")
    casting = scenario.cast("Lightning Bolt")
    assert casting.casualty_numbers() == [1]
    casting.pay_casualty(elves)
    casting.choose_targets(["bob"])
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Mountain"))
    scenario.put_on_stack(casting)

    assert elves.zone is Zone.GRAVEYARD
    assert len(keyword_triggers(scenario, "casualty")) == 1
    resolve_everything(scenario)
    assert scenario.player("bob").life == 14


def test_the_casualty_copy_may_choose_new_targets():
    scenario = silverquill_board(["Lightning Bolt"], "Llanowar Elves", lands=["Mountain"])
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.will_take_the_may(True, username="alice", source="Lightning Bolt")
    scenario.will_choose_targets(bears, username="alice", source="Lightning Bolt")
    casting = scenario.cast("Lightning Bolt")
    casting.pay_casualty(scenario.creature("Llanowar Elves", "alice"))
    casting.choose_targets(["bob"])
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Mountain"))
    scenario.put_on_stack(casting)
    resolve_everything(scenario)
    assert bears.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 17


def test_silverquill_itself_can_be_the_casualty():
    """The grant is asked while the spell is being cast (CR 601.2b); the
    sacrifice is paid at CR 601.2h, so Silverquill paying for the spell it
    granted casualty to still copies it."""
    scenario = silverquill_board(["Lightning Bolt"], lands=["Mountain"])
    silverquill = scenario.creature("Silverquill, the Disputant", "alice")
    casting = scenario.cast("Lightning Bolt")
    casting.pay_casualty(silverquill)
    casting.choose_targets(["bob"])
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Mountain"))
    scenario.put_on_stack(casting)
    assert silverquill.zone is Zone.GRAVEYARD
    resolve_everything(scenario)
    assert scenario.player("bob").life == 14


def test_silverquill_does_not_give_a_creature_spell_casualty():
    scenario = silverquill_board(["Grizzly Bears"], "Llanowar Elves", lands=["Forest", "Forest"])
    casting = scenario.cast("Grizzly Bears")
    assert casting.casualty_numbers() == []


def test_a_printed_casualty_and_the_granted_one_are_paid_separately():
    """CR 702.153b: Join the Maestros prints casualty 2, Silverquill grants
    casualty 1 - two instances, each paid with its own creature and each
    triggering for its own payment. Paying both: three Ogres."""
    scenario = silverquill_board(
        ["Join the Maestros"], "Grizzly Bears", "Llanowar Elves", lands=["Swamp"] * 5
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    elves = scenario.creature("Llanowar Elves", "alice")
    casting = scenario.cast("Join the Maestros")
    assert casting.casualty_numbers() == [2, 1]
    casting.pay_casualty(bears)
    casting.pay_casualty(elves)
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources(*["Swamp"] * 5))
    scenario.put_on_stack(casting)
    assert len(keyword_triggers(scenario, "casualty")) == 2
    resolve_everything(scenario)
    assert len([p for p in scenario.game.battlefield if p.name == "Ogre Warrior Token"]) == 3


def test_paying_one_of_two_casualty_instances_copies_once():
    scenario = silverquill_board(["Join the Maestros"], "Grizzly Bears", lands=["Swamp"] * 5)
    casting = scenario.cast("Join the Maestros")
    casting.pay_casualty(scenario.creature("Grizzly Bears", "alice"))
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources(*["Swamp"] * 5))
    scenario.put_on_stack(casting)
    assert len(keyword_triggers(scenario, "casualty")) == 1
    resolve_everything(scenario)
    assert len([p for p in scenario.game.battlefield if p.name == "Ogre Warrior Token"]) == 2


def test_legal_actions_offer_the_granted_casualty():
    from magic_cards_model.machines.legal_actions import legal_actions

    scenario = silverquill_board(["Lightning Bolt"], "Llanowar Elves", lands=["Mountain"])
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    casts = [
        action
        for action in legal_actions(scenario.game, "alice")
        if action.kind.value == "cast" and action.card_id == bolt.id
    ]
    assert casts
    assert all(
        any(option.keyword == "casualty" for option in action.additional_cost_options)
        for action in casts
    )


def test_a_cast_made_during_resolution_is_offered_the_granted_casualty():
    """Violent Outburst's cascade casts Lightning Bolt while its trigger
    resolves (CR 608.2g); CR 601.2b's announcement there still offers the
    casualty Silverquill grants."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Violent Outburst"],
            library=["Lightning Bolt", "Island"],
            battlefield=[
                "Silverquill, the Disputant",
                "Llanowar Elves",
                "Forest",
                "Mountain",
                "Forest",
            ],
        )
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    elves = scenario.creature("Llanowar Elves", "alice")
    scenario.will_take_the_may(True, username="alice", source="Lightning Bolt", times=None)
    scenario.will_choose_cards(elves, username="alice", source="Lightning Bolt")
    scenario.will_choose_targets("bob", username="alice", source="Lightning Bolt")
    scenario.cast_onto_stack(
        "Violent Outburst", *scenario.untapped_sources("Forest", "Mountain", "Forest")
    )
    scenario.resolve_top()  # the cascade trigger: Bolt is cast, casualty paid
    assert elves.zone is Zone.GRAVEYARD
    assert len(keyword_triggers(scenario, "casualty")) == 1
