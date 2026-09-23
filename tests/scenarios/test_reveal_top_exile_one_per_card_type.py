"""Scenario: reveal the top N, exile one card per card type, bin the rest, and a
free cast gated on how many cards were exiled this way.

Portent of Calamity, {X}{U} sorcery: "Reveal the top X cards of your library.
For each card type, you may exile a card of that type from among them. Put the
rest into your graveyard. You may cast a spell from among the exiled cards
without paying its mana cost if you exiled four or more cards this way. Then
put the rest of the exiled cards into your hand."

A live game on engine f26408a resolved it straight to the graveyard doing
nothing: no parser read any of its five sentences. The per-card-type pick is
the same reader Atraxa, Grand Unifier's trigger goes through
(`test_reveal_one_per_card_type.py`), with a different verb and destination.

Every CR number here was read in full with `mise run rules:find` in the session
that wrote this file:

- **CR 107.3a** - X in the mana cost is announced while casting and "any X in
  its mana cost ... equals the announced value" while the spell is on the stack.
- **CR 701.20a / 701.20b** - revealing shows the cards and moves nothing.
- **CR 205.2a** - the card types the per-type loop runs over. Scryfall's
  Portent ruling (2024-07-26) lists the ones a revealed card can carry, and
  Atraxa's (2023-02-04): a card with several types may be chosen for any one
  of them, and choosing it for one leaves the other type's pick open.
- **CR 608.2c** - the sentences run in the order written.
- **CR 608.2d** - each pick and the cast are choices made while resolving; an
  impossible option is not offered.
- **CR 608.2g** - the free spell is cast during the resolution and becomes the
  topmost object on the stack.
- **CR 107.3b** - cast without paying its mana cost, an {X} in that spell's cost
  is 0.
- **CR 305.9** - a land card can't be cast as a spell.
- **CR 609.3** - a library shorter than X reveals what it has.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone
from tests.scenarios.harness import PlayedScenario, Scenario

PORTENT = "Portent of Calamity"


def _board(library: list[str], *, islands: int = 8) -> PlayedScenario:
    scenario = (
        Scenario()
        .player("alice", hand=[PORTENT], library=library, battlefield=["Island"] * islands)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_portent(scenario: PlayedScenario, x: int):
    casting = scenario.cast(PORTENT)
    payment = casting.determine_cost(x_value=x)
    scenario.pay_with(payment, *scenario.untapped_sources(*["Island"] * (x + 1)))
    spell = scenario.put_on_stack(casting)
    scenario.resolve_top()
    return spell


def _names(cards) -> list[str]:
    return sorted(state.name for state in cards)


def _portent_questions(scenario: PlayedScenario):
    return [q for q in scenario.questions_asked() if q.source == PORTENT]


#: Five card types, top first; Island is a second land, left for the graveyard.
FIVE_TYPES = ["Lightning Bolt", "Grizzly Bears", "Sol Ring", "Forest", "Rancor", "Island"]


def test_exiling_four_or_more_offers_the_free_cast_and_the_spell_cast_resolves():
    """Five types revealed, five exiled: the free cast is offered, Grizzly Bears
    is cast during Portent's resolution (CR 608.2g), the other exiled cards go
    to hand, the unexiled Island to the graveyard, and the Bears then resolve."""
    scenario = _board(FIVE_TYPES)
    alice = scenario.player("alice")
    bears = scenario.find("Grizzly Bears", Zone.LIBRARY, "alice")
    forest = scenario.find("Forest", Zone.LIBRARY, "alice")
    scenario.will_take_the_may(True, source=PORTENT, times=6)
    scenario.will_choose_cards(forest, source=PORTENT)
    scenario.will_choose_cards(bears, source=PORTENT)

    portent = _cast_portent(scenario, 6)

    assert portent.zone is Zone.GRAVEYARD
    assert scenario.stack_names() == ["Grizzly Bears"], "cast during the resolution"
    assert _names(alice.hand) == ["Forest", "Lightning Bolt", "Rancor", "Sol Ring"]
    assert _names(alice.graveyard) == ["Island", PORTENT]
    assert alice.library == []
    assert scenario.game.exile == []
    assert scenario.game.cast_record(bears).x_value == 0

    scenario.resolve_top()
    assert bears.zone is Zone.BATTLEFIELD


def test_every_choice_reaches_the_controller_with_a_prompt_naming_it():
    """One "you may exile" per card type present, naming the type and the
    candidates, a card choice where a type has two, then the free-cast "you
    may" and its card choice."""
    scenario = _board(FIVE_TYPES)
    bears = scenario.find("Grizzly Bears", Zone.LIBRARY, "alice")
    forest = scenario.find("Forest", Zone.LIBRARY, "alice")
    scenario.will_take_the_may(True, source=PORTENT, times=6)
    scenario.will_choose_cards(forest, source=PORTENT)
    scenario.will_choose_cards(bears, source=PORTENT)

    _cast_portent(scenario, 6)

    asked = _portent_questions(scenario)
    prompts = [(q.kind, q.prompt) for q in asked]
    assert prompts == [
        (DecisionKind.MAY, "exile an artifact card from among the revealed cards"),
        (DecisionKind.MAY, "exile a creature card from among the revealed cards"),
        (DecisionKind.MAY, "exile an enchantment card from among the revealed cards"),
        (DecisionKind.MAY, "exile a land card from among the revealed cards"),
        (DecisionKind.CHOOSE_CARDS, "choose a land card to exile"),
        (DecisionKind.MAY, "exile an instant card from among the revealed cards"),
        (
            DecisionKind.MAY,
            "cast a spell from among the exiled cards without paying its mana cost",
        ),
        (DecisionKind.CHOOSE_CARDS, "choose a spell to cast without paying its mana cost"),
    ]
    assert all(q.cards for q in asked), "every question shows the cards it is about"


def test_declining_the_free_cast_puts_every_exiled_card_into_hand():
    scenario = _board(FIVE_TYPES)
    alice = scenario.player("alice")
    forest = scenario.find("Forest", Zone.LIBRARY, "alice")
    scenario.will_take_the_may(True, source=PORTENT, times=5)
    scenario.will_take_the_may(False, source=PORTENT)
    scenario.will_choose_cards(forest, source=PORTENT)

    _cast_portent(scenario, 6)

    assert scenario.stack_names() == []
    assert _names(alice.hand) == ["Forest", "Grizzly Bears", "Lightning Bolt", "Rancor", "Sol Ring"]
    assert _names(alice.graveyard) == ["Island", PORTENT]


def test_exiling_fewer_than_four_offers_no_free_cast_and_the_exiled_go_to_hand():
    """Three types revealed, three exiled: no cast question at all."""
    scenario = _board(["Grizzly Bears", "Sol Ring", "Forest", "Island", "Island"])
    alice = scenario.player("alice")
    forest = scenario.find("Forest", Zone.LIBRARY, "alice")
    scenario.will_take_the_may(True, source=PORTENT, times=3)
    scenario.will_choose_cards(forest, source=PORTENT)

    _cast_portent(scenario, 5)

    assert not any("without paying" in q.prompt for q in _portent_questions(scenario))
    assert scenario.stack_names() == []
    assert _names(alice.hand) == ["Forest", "Grizzly Bears", "Sol Ring"]
    assert _names(alice.graveyard) == ["Island", "Island", PORTENT]


def test_a_declined_pick_counts_against_the_four_even_with_four_types_revealed():
    """ "If you exiled four or more cards this way" counts the cards exiled, not
    the types revealed: four types, one pick declined, no free cast."""
    scenario = _board(["Grizzly Bears", "Sol Ring", "Forest", "Rancor"])
    alice = scenario.player("alice")
    scenario.will_take_the_may(False, source=PORTENT)  # the artifact pick
    scenario.will_take_the_may(True, source=PORTENT, times=3)

    _cast_portent(scenario, 4)

    assert not any("without paying" in q.prompt for q in _portent_questions(scenario))
    assert _names(alice.hand) == ["Forest", "Grizzly Bears", "Rancor"]
    assert _names(alice.graveyard) == [PORTENT, "Sol Ring"]


def test_x_of_zero_reveals_nothing_and_asks_nothing():
    scenario = _board(["Grizzly Bears", "Sol Ring"])
    alice = scenario.player("alice")

    portent = _cast_portent(scenario, 0)

    assert portent.zone is Zone.GRAVEYARD
    assert _portent_questions(scenario) == []
    assert [state.name for state in alice.library] == ["Grizzly Bears", "Sol Ring"]
    assert alice.hand == []
    assert scenario.game.unmodeled_trigger_effect_notices == []


def test_x_larger_than_the_library_reveals_what_is_there():
    """CR 609.3: two cards for an X of six. Both exiled, two is fewer than four,
    both go to hand."""
    scenario = _board(["Grizzly Bears", "Forest"])
    alice = scenario.player("alice")

    _cast_portent(scenario, 6)

    assert alice.library == []
    assert _names(alice.hand) == ["Forest", "Grizzly Bears"]
    assert _names(alice.graveyard) == [PORTENT]


def test_an_artifact_creature_fills_only_one_pick():
    """Memnite is an artifact and a creature. Taken as the artifact, it is no
    longer among the revealed cards, so the creature pick has no candidate and
    is not asked."""
    scenario = _board(["Memnite", "Island", "Island"])
    alice = scenario.player("alice")
    island = scenario.find("Island", Zone.LIBRARY, "alice")
    scenario.will_take_the_may(True, source=PORTENT, times=2)
    scenario.will_choose_cards(island, source=PORTENT)

    _cast_portent(scenario, 3)

    prompts = [q.prompt for q in _portent_questions(scenario)]
    assert not any("creature card" in prompt for prompt in prompts)
    assert _names(alice.hand) == ["Island", "Memnite"]
    assert _names(alice.graveyard) == ["Island", PORTENT]


def test_an_artifact_creature_can_be_the_creature_pick_beside_another_artifact():
    """Atraxa's ruling: a card with several types may be chosen for any one of
    them. Sol Ring is taken as the artifact, so Memnite fills the creature pick."""
    scenario = _board(["Memnite", "Sol Ring"])
    alice = scenario.player("alice")
    sol_ring = scenario.find("Sol Ring", Zone.LIBRARY, "alice")
    scenario.will_take_the_may(True, source=PORTENT, times=2)
    scenario.will_choose_cards(sol_ring, source=PORTENT)

    _cast_portent(scenario, 2)

    assert _names(alice.hand) == ["Memnite", "Sol Ring"]
    assert _names(alice.graveyard) == [PORTENT]


def test_an_exiled_land_counts_toward_four_but_is_never_offered_as_the_cast():
    """CR 305.9: the land is exiled for the land pick and counts toward four,
    but it is not a spell, so the cast offers only the nonland cards and the
    land goes to hand."""
    scenario = _board(["Forest", "Grizzly Bears", "Sol Ring", "Rancor"])
    alice = scenario.player("alice")
    forest = scenario.find("Forest", Zone.LIBRARY, "alice")
    scenario.will_take_the_may(True, source=PORTENT, times=4)
    scenario.will_take_the_may(False, source=PORTENT)

    _cast_portent(scenario, 4)

    (cast_question,) = [q for q in _portent_questions(scenario) if "without paying" in q.prompt]
    assert forest.id not in cast_question.cards
    # CR 303.4a: Rancor's Aura spell requires a target creature and there is
    # none on this board, so it is no more castable than the Forest.
    rancor = scenario.find("Rancor", Zone.HAND, "alice")
    assert rancor.id not in cast_question.cards
    assert len(cast_question.cards) == 2
    assert forest.zone is Zone.HAND
    assert _names(alice.hand) == ["Forest", "Grizzly Bears", "Rancor", "Sol Ring"]


def test_portent_no_longer_records_an_unmodeled_notice():
    scenario = _board(FIVE_TYPES)

    _cast_portent(scenario, 6)

    assert scenario.game.unmodeled_trigger_effect_notices == []
