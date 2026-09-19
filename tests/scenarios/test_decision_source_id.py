"""Scenario: every question the engine asks names the object that asked it.

`Decision.source` has always carried the asking card's *name*. A name does not
identify an object: two Steam Vents on one battlefield are two objects, and a
client that wants to point at "the card asking" (the api's pending decision,
the play UI anchoring a popover to that card) has nothing to point with.
`Decision.source_id` is the object id - the `CardState`/`TokenState` id, or
for an ability on the stack the id of the card behind it - of the game object
whose spell, ability, trigger, replacement effect or cost produced the
question, and `None` only when no object asks.

Every CR number here was read in full with `mise run rules:find` from the
2026-08-19 Comprehensive Rules release, in the session that wrote this file:

- **CR 608.2d** - a resolving spell or ability's choices are announced while
  applying the effect; the asking object is that spell or ability.
- **CR 103.5** - the mulligan declaration: "A player who is dissatisfied with
  their initial hand may take a mulligan." Asked by the rules, of a player,
  about a hand - no object asks it.
- **CR 103.6** - "Some cards allow a player to take actions with them from
  their opening hand." The card allowing it is the source.
- **CR 508.1** / **CR 509.1** - declaring attackers and blockers are
  turn-based actions ("This turn-based action doesn't use the stack"); no
  object asks either.
- **CR 603.3b** - ordering one player's simultaneous triggered abilities: one
  question about several abilities, each with its own source, so no single
  object is the asker.
- **CR 514.1** - the cleanup discard is a turn-based action of the active
  player, not any card's effect.
- **CR 704.5j** - the legend rule is a state-based action: "that player
  chooses one of them".

`CHOOSE_A_MODE` is asked by exactly one path in this engine - a modal
*triggered* ability's "choose one" (Elder Gargaroth). A modal *spell* chooses
its modes while it is cast, as part of `Casting`'s announcement, and never
asks a `Decision` at all, so the triggered ability is the only real scenario
that kind has.
"""

from collections.abc import Callable

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import Decision, DecisionKind, ScriptedAnswer
from magic_cards_model.models import Color, Game, Zone
from magic_cards_model.models.card_state import CardState, Counter
from tests.scenarios.harness import PlayedScenario, Scenario
from tests.scenarios.test_combat_turn_based_actions import attacking_board, queue_declaration
from tests.scenarios.test_counterspells import censor_board
from tests.scenarios.test_energy_payment import walk_to
from tests.scenarios.test_opening_hand_actions import broodscale, dealt, devoted, series, will_take
from tests.scenarios.test_turn_based_actions import advance_to, driven


def _asked(decisions: list[Decision], kind: DecisionKind) -> list[Decision]:
    asked = [decision for decision in decisions if decision.kind is kind]
    assert asked, f"no {kind.value} question was asked at all"
    return asked


def _resolve_all(scenario: PlayedScenario) -> None:
    while scenario.game.stack:
        scenario.resolve_top()


# -- one real scenario per kind that has an asking object --------------------
#
# Each returns every question of its kind the scenario asked, and the object
# that should be named as asking it.

Probe = Callable[[], tuple[list[Decision], CardState]]


def _shockland_pay_life() -> tuple[list[Decision], CardState]:
    """Steam Vents' "As this land enters, you may pay 2 life" (CR 614.12a)."""
    scenario = Scenario().manual_turn_based_actions().player("alice", hand=["Steam Vents"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_pay_the_life(True)

    vents = scenario.play_land("Steam Vents")

    return _asked(scenario.questions_asked(), DecisionKind.PAY_LIFE), vents


def _fetchland_search() -> tuple[list[Decision], CardState]:
    """Flooded Strand's search, asked while its ability resolves - after the
    land itself was sacrificed to pay for it, so the id names a card that is
    already in the graveyard."""
    scenario = (
        Scenario()
        .player("alice", library=["Forest"], battlefield=["Forest"])
        .player("bob", library=["Plains"], battlefield=["Flooded Strand"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    strand = scenario.find("Flooded Strand", Zone.BATTLEFIELD, "bob")
    scenario.pass_priority()
    scenario.activate(strand, username="bob")
    scenario.pass_until_resolved()

    return _asked(scenario.questions_asked(), DecisionKind.CHOOSE_CARDS), strand


def _proliferate_choose_players() -> tuple[list[Decision], CardState]:
    """Fuel for the Cause's own "Counter target spell, then proliferate."
    (CR 701.34a), with bob poisoned so the `CHOOSE_PLAYERS` question has
    someone real to offer."""
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Fuel for the Cause"], library=["Island"] * 3, battlefield=["Island"] * 4
        )
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"], life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.game.player("bob")
    scenario.game.add_player_counters(bob, Counter.POISON, 1)
    scenario.pass_priority("alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=["alice"])
    scenario.pass_priority("bob")

    scenario.will_choose_players(bob)
    sources = scenario.untapped_sources("Island", "Island", "Island", "Island")
    fuel = scenario.cast_and_resolve(
        "Fuel for the Cause", *sources, username="alice", targets=[bolt]
    )

    return _asked(scenario.questions_asked(), DecisionKind.CHOOSE_PLAYERS), fuel


def _preordain_scry() -> tuple[list[Decision], CardState]:
    """Preordain's scry 2, asked by the spell while it is on the stack."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            library=["Island", "Mountain", "Forest"],
            hand=["Preordain"],
            battlefield=["Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    preordain = scenario.find("Preordain", Zone.HAND, "alice")
    (island,) = scenario.untapped_sources("Island", username="alice")

    scenario.cast_and_resolve("Preordain", island, username="alice")

    return _asked(scenario.questions_asked(), DecisionKind.SCRY), preordain


def _surveil_land_trigger() -> tuple[list[Decision], CardState]:
    """Commercial District's "When this land enters, surveil 1." (CR 603)."""
    scenario = (
        Scenario()
        .player("alice", hand=["Commercial District"], library=["Mountain", "Island"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    district = scenario.play_land("Commercial District")
    scenario.pass_until_resolved()

    return _asked(scenario.questions_asked(), DecisionKind.SURVEIL), district


def _may_trigger() -> tuple[list[Decision], CardState]:
    """Dragon Appeasement's "Whenever you sacrifice a creature, you may draw a card." """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Dragon Appeasement", "Grizzly Bears"], library=["Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    appeasement = scenario.find("Dragon Appeasement", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.will_take_the_may(True, source="Dragon Appeasement")

    scenario.game.sacrifice(bears)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    return _asked(scenario.questions_asked(), DecisionKind.MAY), appeasement


def _modal_trigger_mode() -> tuple[list[Decision], CardState]:
    """Elder Gargaroth's "Whenever this creature attacks or blocks, choose one -"."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Elder Gargaroth"], library=["Forest"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gargaroth = scenario.creature("Elder Gargaroth", "alice")
    scenario.will_choose_mode("You gain 3 life.")

    scenario.attack_with(gargaroth)
    _resolve_all(scenario)

    return _asked(scenario.questions_asked(), DecisionKind.CHOOSE_A_MODE), gargaroth


def _static_prison_pay_energy() -> tuple[list[Decision], CardState]:
    """Static Prison's "sacrifice this enchantment unless you pay {E}"."""
    scenario = (
        Scenario()
        .player("alice", library=["Plains"], battlefield=["Static Prison"])
        .player("bob", library=["Plains"])
        .build()
    )
    scenario.player("alice").add_counters(Counter.ENERGY, 1)
    prison = scenario.find("Static Prison", Zone.BATTLEFIELD, "alice")
    scenario.start_at(Step.UPKEEP)
    scenario.will_pay_the_energy(True)

    walk_to(scenario, Step.PRECOMBAT_MAIN)

    return _asked(scenario.questions_asked(), DecisionKind.PAY_ENERGY), prison


def _censor_pay_mana() -> tuple[list[Decision], CardState]:
    """Censor's "Counter target spell unless its controller pays {1}" - asked
    of the *target's* controller, by Censor."""
    scenario = censor_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    censor = scenario.find("Censor", Zone.HAND, "bob")
    opt = scenario.cast_onto_stack("Opt", username="alice", auto=True)
    scenario.pass_priority("alice")

    islands = scenario.untapped_sources("Island", "Island", username="bob")
    scenario.cast_and_resolve("Censor", *islands, username="bob", targets=[opt])

    return _asked(scenario.game.decisions.asked, DecisionKind.PAY_MANA), censor


def _galvanic_discharge_energy_amount() -> tuple[list[Decision], CardState]:
    """Galvanic Discharge's "you may pay any amount of {E}"."""
    scenario = (
        Scenario()
        .player("alice", hand=["Galvanic Discharge"], battlefield=["Mountain"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    discharge = scenario.find("Galvanic Discharge", Zone.HAND, "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.will_pay_energy_amount(3)

    scenario.cast_and_resolve("Galvanic Discharge", mountain, targets=[bears])

    return _asked(scenario.questions_asked(), DecisionKind.PAY_ENERGY_AMOUNT), discharge


def _necrodominance_life_amount() -> tuple[list[Decision], CardState]:
    """Necrodominance's end step "you may pay any amount of life"."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Necrodominance"], life=10, library=["Forest"] * 6)
        .player("bob")
        .manual_turn_based_actions()
        .build()
    )
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    necrodominance = scenario.find("Necrodominance", Zone.BATTLEFIELD, "alice")
    scenario.will_pay_life_amount(2, source="Necrodominance")

    scenario.advance()
    _resolve_all(scenario)

    return _asked(scenario.questions_asked(), DecisionKind.PAY_LIFE_AMOUNT), necrodominance


def _opening_hand_action() -> tuple[list[Decision], CardState]:
    """Leyline of Abundance's CR 103.6a offer, asked about the card in hand."""
    match = series(devoted(), broodscale())
    game = dealt(match, {"alice": "Leyline of Abundance"})
    leyline = next(s for s in game.player("alice").hand if s.name == "Leyline of Abundance")
    will_take(game, "alice", "Leyline of Abundance")

    match.run_mulligans(game)

    # Every card in either opening hand that offers an action is asked about,
    # each naming itself; this Leyline's own question is the one about it.
    offers = _asked(game.decisions.asked, DecisionKind.OPENING_HAND_ACTION)
    return [decision for decision in offers if decision.card == leyline.id], leyline


def _activated_ability_targets() -> tuple[list[Decision], CardState]:
    """Karn, the Great Creator's +1, activated with no targets supplied."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Karn, the Great Creator", "Sol Ring"],
            library=["Mountain"] * 5,
        )
        .player("bob", library=["Mountain"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    karn = scenario.creature("Karn, the Great Creator", "alice")
    sol_ring = scenario.creature("Sol Ring", "alice")
    scenario.game.decisions.add(
        ScriptedAnswer(kind=DecisionKind.CHOOSE_TARGETS, value=(sol_ring,), player="alice")
    )

    scenario.activate(karn, index=0)

    return _asked(scenario.questions_asked(), DecisionKind.CHOOSE_TARGETS), karn


def _choose_a_color() -> tuple[list[Decision], CardState]:
    """Utopia Sprawl's "As this Aura enters, choose a color" (CR 614.12a)."""
    scenario = (
        Scenario()
        .player("alice", hand=["Utopia Sprawl"], battlefield=["Forest", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sprawl = scenario.find("Utopia Sprawl", Zone.HAND, "alice")
    payer, forest = scenario.untapped_sources("Forest", "Forest", username="alice")
    scenario.will_choose(Color.BLUE.value, source="Utopia Sprawl")

    scenario.cast_and_resolve("Utopia Sprawl", payer, targets=[forest])

    return _asked(scenario.questions_asked(), DecisionKind.CHOOSE_A_QUALITY), sprawl


def _top_or_bottom() -> tuple[list[Decision], CardState]:
    """Subtlety's enters trigger: the target spell's owner chooses top or bottom."""
    scenario = (
        Scenario()
        .player("bob", hand=["Grizzly Bears"], battlefield=["Forest", "Forest"])
        .player("alice", hand=["Subtlety"], battlefield=["Island"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forests = scenario.untapped_sources("Forest", "Forest", username="bob")
    islands = scenario.untapped_sources(*(["Island"] * 4), username="alice")
    bears = scenario.cast_onto_stack("Grizzly Bears", *forests, username="bob")
    scenario.pass_priority("bob")
    scenario.choose_trigger_targets("Subtlety", [bears])
    scenario.will_choose_top(True, username="bob")

    subtlety = scenario.cast_onto_stack("Subtlety", *islands, username="alice")
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()

    return _asked(scenario.questions_asked(), DecisionKind.PUT_ON_TOP_OR_BOTTOM), subtlety


def _choose_pile() -> tuple[list[Decision], CardState]:
    """Liliana of the Veil's own `-6`: bob, the target, picks a whole pile."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Liliana of the Veil"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    liliana = scenario.find("Liliana of the Veil", Zone.BATTLEFIELD, "alice")
    liliana.add_counters(Counter.LOYALTY, 3)
    scenario.will_choose_cards(username="alice", source="Liliana of the Veil")
    scenario.will_choose_pile(True, username="bob", source="Liliana of the Veil")

    scenario.activate(liliana, index=2, targets=["bob"])
    scenario.pass_until_resolved()

    return _asked(scenario.questions_asked(), DecisionKind.CHOOSE_PILE), liliana


SOURCED: dict[DecisionKind, Probe] = {
    DecisionKind.MAY: _may_trigger,
    DecisionKind.PAY_LIFE: _shockland_pay_life,
    DecisionKind.PAY_ENERGY: _static_prison_pay_energy,
    DecisionKind.PAY_MANA: _censor_pay_mana,
    DecisionKind.PAY_ENERGY_AMOUNT: _galvanic_discharge_energy_amount,
    DecisionKind.PAY_LIFE_AMOUNT: _necrodominance_life_amount,
    DecisionKind.SCRY: _preordain_scry,
    DecisionKind.SURVEIL: _surveil_land_trigger,
    DecisionKind.OPENING_HAND_ACTION: _opening_hand_action,
    DecisionKind.CHOOSE_CARDS: _fetchland_search,
    DecisionKind.CHOOSE_PLAYERS: _proliferate_choose_players,
    DecisionKind.CHOOSE_TARGETS: _activated_ability_targets,
    DecisionKind.CHOOSE_A_QUALITY: _choose_a_color,
    DecisionKind.CHOOSE_A_MODE: _modal_trigger_mode,
    DecisionKind.PUT_ON_TOP_OR_BOTTOM: _top_or_bottom,
    DecisionKind.CHOOSE_PILE: _choose_pile,
}


# -- the kinds no object ever asks, each with the reason ---------------------


def _mulligan() -> list[Decision]:
    match = series(devoted(), broodscale())
    game = dealt(match, {})
    match.run_mulligans(game)
    return _asked(game.decisions.asked, DecisionKind.MULLIGAN)


def _combat(kind: DecisionKind) -> Callable[[], list[Decision]]:
    def probe() -> list[Decision]:
        scenario = attacking_board().build()
        bears = scenario.creature("Grizzly Bears")
        queue_declaration(scenario, DecisionKind.DECLARE_ATTACKERS, [(bears, "bob")])
        scenario.start_at(Step.BEGINNING_OF_COMBAT)
        scenario.advance()
        scenario.advance()
        return _asked(scenario.questions_asked(), kind)

    return probe


def _trigger_order() -> list[Decision]:
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Dragon Appeasement", "Dragon Appeasement", "Grizzly Bears"],
            library=["Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.sacrifice(scenario.creature("Grizzly Bears", "alice"))
    scenario.game.put_triggers_on_stack()
    return _asked(scenario.questions_asked(), DecisionKind.ORDER_TRIGGERS)


def _combat_damage_assignment() -> list[Decision]:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Colossal Dreadmaw"])
        .player("bob", battlefield=["Grizzly Bears", "Hill Giant"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    dreadmaw = scenario.creature("Colossal Dreadmaw", "alice")
    scenario.attack_with(dreadmaw)
    scenario.block(
        dreadmaw, scenario.creature("Grizzly Bears", "bob"), scenario.creature("Hill Giant", "bob")
    )
    scenario.combat_damage()
    return _asked(scenario.questions_asked(), DecisionKind.ASSIGN_COMBAT_DAMAGE)


SOURCELESS: dict[DecisionKind, tuple[str, Callable[[], list[Decision]]]] = {
    DecisionKind.ASSIGN_COMBAT_DAMAGE: (
        "CR 703.4k: assigning combat damage is a turn-based action, not any object's",
        _combat_damage_assignment,
    ),
    DecisionKind.MULLIGAN: (
        "CR 103.5: the rules ask a player about their hand; no object asks it",
        _mulligan,
    ),
    DecisionKind.DECLARE_ATTACKERS: (
        "CR 508.1: declaring attackers is a turn-based action, not any object's",
        _combat(DecisionKind.DECLARE_ATTACKERS),
    ),
    DecisionKind.DECLARE_BLOCKERS: (
        "CR 509.1: declaring blockers is a turn-based action, not any object's",
        _combat(DecisionKind.DECLARE_BLOCKERS),
    ),
    DecisionKind.ORDER_TRIGGERS: (
        "CR 603.3b: one question about several abilities, each with its own "
        "source, so no single object is the asker",
        _trigger_order,
    ),
}


def test_every_decision_kind_is_either_sourced_or_listed_as_sourceless():
    """A new `DecisionKind` has to say which it is, here, before it ships."""
    assert set(SOURCED) | set(SOURCELESS) == set(DecisionKind)
    assert not set(SOURCED) & set(SOURCELESS)


@pytest.mark.parametrize("kind", list(DecisionKind), ids=lambda kind: kind.value)
def test_each_kind_names_its_asking_object_or_none(kind: DecisionKind):
    """Every kind, played through a real scenario: the asking object's id when
    an object asks, `None` when the rules do."""
    if kind in SOURCED:
        asked, source = SOURCED[kind]()
        assert [decision.source_id for decision in asked] == [str(source.id)] * len(asked)
    else:
        _reason, probe = SOURCELESS[kind]
        assert [decision.source_id for decision in probe()] == [None] * len(probe())


# -- the named cases ----------------------------------------------------------


def test_a_shocklands_pay_life_names_the_land():
    (question,), vents = _shockland_pay_life()
    assert question.source == "Steam Vents"
    assert question.source_id == str(vents.id)


def test_a_fetchlands_search_names_the_fetchland():
    (question,), strand = _fetchland_search()
    assert strand.zone is Zone.GRAVEYARD, "sacrificed as a cost before the search"
    assert question.source_id == str(strand.id)


def test_a_scry_spell_names_the_spell_on_the_stack():
    (question,), preordain = _preordain_scry()
    assert question.source == "Preordain"
    assert question.source_id == str(preordain.id)


def test_a_surveil_lands_enters_trigger_names_the_land():
    (question,), district = _surveil_land_trigger()
    assert question.source_id == str(district.id)


def test_a_may_trigger_names_the_permanent_it_triggered_from():
    (question,), appeasement = _may_trigger()
    assert question.source_id == str(appeasement.id)


def test_choose_a_mode_names_the_modal_abilitys_source():
    (question,), gargaroth = _modal_trigger_mode()
    assert question.source_id == str(gargaroth.id)


def test_two_copies_of_one_card_are_told_apart_by_id():
    """The reason a name is not enough: two Dragon Appeasements both ask "you
    may draw a card", with the same `source`, and only the id says which."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Dragon Appeasement", "Dragon Appeasement", "Grizzly Bears"],
            library=["Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    copies = {
        str(state.id) for state in scenario.game.battlefield if state.name == "Dragon Appeasement"
    }
    scenario.will_take_the_may(True, source="Dragon Appeasement", times=None)

    scenario.game.sacrifice(scenario.creature("Grizzly Bears", "alice"))
    scenario.game.put_triggers_on_stack()
    _resolve_all(scenario)

    asked = _asked(scenario.questions_asked(), DecisionKind.MAY)
    assert len(asked) == 2, "one question per trigger"
    assert {decision.source for decision in asked} == {"Dragon Appeasement"}
    assert {decision.source_id for decision in asked} == copies


def test_the_cleanup_discard_has_no_source_object():
    """CR 514.1: a turn-based action, not any card's effect."""
    scenario = driven(alice={"hand": ["Mountain"] * 9}, bob={})
    advance_to(scenario, "alice", Step.CLEANUP)

    (question,) = _asked(scenario.questions_asked(), DecisionKind.CHOOSE_CARDS)
    assert question.source is None
    assert question.source_id is None


def test_the_legend_rule_choice_has_no_source_object():
    """CR 704.5j: a state-based action, not any card's effect."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Karn, the Great Creator", "Karn, the Great Creator"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.game.check_state_based_actions()

    (question,) = _asked(scenario.questions_asked(), DecisionKind.CHOOSE_CARDS)
    assert question.source_id is None


def test_the_mulligan_bottoming_has_no_source_object():
    """CR 103.5: the cards a kept hand puts on the bottom are the rules' question."""
    match = series(devoted(), broodscale())
    game = dealt(match, {})
    game.decisions.add(
        ScriptedAnswer(kind=DecisionKind.MULLIGAN, value=True, player="alice", uses=1)
    )

    match.run_mulligans(game)

    (question,) = _asked(game.decisions.asked, DecisionKind.CHOOSE_CARDS)
    assert question.source_id is None


def test_source_id_survives_a_snapshot_round_trip():
    """Plain data: the recorded question decodes back with its id intact."""
    scenario = Scenario().manual_turn_based_actions().player("alice", hand=["Steam Vents"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_pay_the_life(True)
    vents = scenario.play_land("Steam Vents")

    dumped = scenario.game.model_dump(mode="json")
    decoded = Game.model_validate(dumped)

    (question,) = _asked(decoded.decisions.asked, DecisionKind.PAY_LIFE)
    assert question.source_id == str(vents.id)
    (recorded,) = [q for q in dumped["decisions"]["asked"] if q["kind"] == "pay_life"]
    assert recorded["source_id"] == str(vents.id)
