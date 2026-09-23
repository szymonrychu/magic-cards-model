"""Put or create a permanent, give it haste, and take it away again at the
beginning of the next end step.

One printed tail, many antecedents:

    <antecedent>. [<It|That token|That creature|They> gain(s) haste.]
    <Sacrifice|Exile|Return> <it|them|that creature> [to your hand]
    at the beginning of the next end step.

The antecedent is whatever the paragraph's first sentence puts onto the
battlefield - a token copy (Reflection of Kiki-Jiki, Kiki-Jiki, Mirror
Breaker), a created token (Lagomos, Hand of Hatred; Lightning Coils; Feral
Lightning), a searched-for card (Nahiri, the Harbinger's -8) or a card put
from hand (Through the Breach). The pronoun means exactly the object(s) that
sentence produced, discovered as it runs.

Every CR number here was read in full with `mise run rules:find` in the
session that wrote this file:

- **CR 603.7a** - a delayed triggered ability is created during the
  resolution of a spell or ability, and only triggers once it exists.
- **CR 603.7b** - it triggers only once, the next time its event occurs.
- **CR 603.7c** - it affects the object it refers to even if that object
  changed characteristics, but not once the object left the zone it is
  expected in; one that left and came back is a new object (CR 400.7).
- **CR 707.9a** - "except it has haste" makes haste part of the copy's
  copiable values.
- **CR 701.21a** - sacrifice moves a permanent its controller controls from
  the battlefield to its owner's graveyard.
- **CR 603.4** - Lightning Coils' intervening "if" is checked as the ability
  triggers and again as it resolves.

Kiki-Jiki, Mirror Breaker, Feral Lightning and Through the Breach are the
proof printings: legal in Modern (Scryfall legalities, 2026-09-23), in no
deck under `magic-cards-model-api/decks/`, and each worded differently from
the listed card that shares its template.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _walk_to(scenario, step: Step) -> None:
    """Advance step by step until `step`, resolving whatever fires on the way.
    `start_at` emits no "step began" event (CR 500.6), which is exactly what a
    delayed trigger waits for, so the walk has to be a real one."""
    while scenario.step is not step:
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()


def _resolve_stack(scenario) -> None:
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()


def _has_haste(scenario, permanent) -> bool:
    return has_keyword(permanent, "Haste", scenario.game)


def _new_tokens(scenario, name: str, before: set) -> list:
    return [
        state
        for state in scenario.game.battlefield
        if state.name == name and state.token and state.id not in before
    ]


# --------------------------------------------------------------------------
# Reflection of Kiki-Jiki (Fable of the Mirror-Breaker's back face)
# --------------------------------------------------------------------------


def _reflection_board():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Fable of the Mirror-Breaker"],
            battlefield=["Grizzly Bears", "Mountain", "Mountain"],
            library=["Mountain"] * 5,
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    fable = scenario.find("Fable of the Mirror-Breaker", Zone.HAND, "alice")
    reflection = scenario.game.put_onto_battlefield(fable, "alice", transformed=True)
    reflection.summoning_sick = False
    return scenario, reflection


def test_reflection_copies_a_nonlegendary_creature_with_haste_and_sacrifices_it():
    scenario, reflection = _reflection_board()
    bears = scenario.creature("Grizzly Bears")
    before = {state.id for state in scenario.game.battlefield}

    scenario.activate(reflection, scenario.untapped_sources("Mountain")[0], targets=[bears])
    _resolve_stack(scenario)

    (copy,) = _new_tokens(scenario, "Grizzly Bears", before)
    assert _has_haste(scenario, copy), "CR 707.9a: haste is part of the copy"

    _walk_to(scenario, Step.END_STEP)

    assert copy.zone is not Zone.BATTLEFIELD, "sacrificed at the next end step"
    assert bears.zone is Zone.BATTLEFIELD, "the original is never touched"


def test_reflection_sacrifices_only_once_and_only_the_copy():
    """CR 603.7b: the delayed ability triggers once; after the first end step
    nothing is left waiting."""
    scenario, reflection = _reflection_board()
    bears = scenario.creature("Grizzly Bears")

    scenario.activate(reflection, scenario.untapped_sources("Mountain")[0], targets=[bears])
    _resolve_stack(scenario)
    _walk_to(scenario, Step.END_STEP)

    assert scenario.game.delayed_triggers.triggers == []
    assert bears.zone is Zone.BATTLEFIELD


# --------------------------------------------------------------------------
# Kiki-Jiki, Mirror Breaker - the proof printing ("target", not "another
# target"; {T} with no mana)
# --------------------------------------------------------------------------


def test_kiki_jiki_copy_has_haste_can_attack_and_is_sacrificed():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Kiki-Jiki, Mirror Breaker", "Hill Giant"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    kiki = scenario.creature("Kiki-Jiki, Mirror Breaker")
    kiki.summoning_sick = False
    giant = scenario.creature("Hill Giant")
    before = {state.id for state in scenario.game.battlefield}

    scenario.activate(kiki, targets=[giant])
    _resolve_stack(scenario)

    (copy,) = _new_tokens(scenario, "Hill Giant", before)
    assert _has_haste(scenario, copy)
    assert scenario.can_attack(copy), "CR 702.10b: haste lets a new creature attack"

    _walk_to(scenario, Step.END_STEP)

    assert copy.zone is not Zone.BATTLEFIELD
    assert giant.zone is Zone.BATTLEFIELD


def test_a_copy_that_already_died_is_not_affected_by_the_delayed_sacrifice():
    """CR 603.7c: a token copy destroyed before the end step is gone; the
    delayed ability resolves and does nothing to anything else."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Kiki-Jiki, Mirror Breaker", "Hill Giant"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    kiki = scenario.creature("Kiki-Jiki, Mirror Breaker")
    kiki.summoning_sick = False
    giant = scenario.creature("Hill Giant")
    before = {state.id for state in scenario.game.battlefield}
    scenario.activate(kiki, targets=[giant])
    _resolve_stack(scenario)
    (copy,) = _new_tokens(scenario, "Hill Giant", before)

    scenario.game.destroy(copy)
    _walk_to(scenario, Step.END_STEP)

    assert giant.zone is Zone.BATTLEFIELD
    assert kiki.zone is Zone.BATTLEFIELD


# --------------------------------------------------------------------------
# Nahiri, the Harbinger's -8 - a searched-for card, returned to hand
# --------------------------------------------------------------------------


def _harbinger_board():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Nahiri, the Harbinger"],
            library=["Hill Giant", "Mountain", "Plains"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    nahiri = scenario.put_onto_battlefield("Nahiri, the Harbinger")
    scenario.game.add_counters(nahiri, Counter.LOYALTY, 4)
    assert nahiri.loyalty == 8
    return scenario, nahiri


def test_harbinger_minus_eight_puts_a_creature_with_haste_and_returns_it_to_hand():
    scenario, nahiri = _harbinger_board()
    giant = scenario.find("Hill Giant", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(giant)

    scenario.activate(nahiri, index=2)
    _resolve_stack(scenario)

    assert giant.zone is Zone.BATTLEFIELD
    assert _has_haste(scenario, giant)

    _walk_to(scenario, Step.END_STEP)

    assert giant.zone is Zone.HAND, "CR 603.7c: returned to its owner's hand"


def test_harbinger_return_skips_a_card_that_was_flickered():
    """CR 400.7 / 603.7c: the searched card left the battlefield and came
    back - it is a new object, so the delayed return leaves it alone."""
    scenario, nahiri = _harbinger_board()
    giant = scenario.find("Hill Giant", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(giant)
    scenario.activate(nahiri, index=2)
    _resolve_stack(scenario)
    assert giant.zone is Zone.BATTLEFIELD

    scenario.game.exile_permanent(giant)
    scenario.game.put_onto_battlefield(giant, "alice")
    _walk_to(scenario, Step.END_STEP)

    assert giant.zone is Zone.BATTLEFIELD


def test_harbinger_with_no_legal_card_to_find_creates_no_return():
    scenario = (
        Scenario()
        .player("alice", hand=["Nahiri, the Harbinger"], library=["Mountain", "Plains"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    nahiri = scenario.put_onto_battlefield("Nahiri, the Harbinger")
    scenario.game.add_counters(nahiri, Counter.LOYALTY, 4)

    scenario.activate(nahiri, index=2)
    _resolve_stack(scenario)

    assert scenario.game.delayed_triggers.triggers == []


# --------------------------------------------------------------------------
# Through the Breach - the spell-side proof: put from hand, sacrifice
# --------------------------------------------------------------------------


def _breach_board():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Through the Breach", "Hill Giant"],
            battlefield=["Mountain"] * 5,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_through_the_breach_puts_a_creature_with_haste_and_sacrifices_it():
    scenario = _breach_board()
    giant = scenario.find("Hill Giant", Zone.HAND, "alice")
    scenario.will_take_the_may(True)
    scenario.will_choose_cards(giant)

    scenario.cast_and_resolve("Through the Breach", *scenario.untapped_sources(*["Mountain"] * 5))

    assert giant.zone is Zone.BATTLEFIELD
    assert _has_haste(scenario, giant)
    assert scenario.can_attack(giant)

    _walk_to(scenario, Step.END_STEP)

    assert giant.zone is Zone.GRAVEYARD


def test_through_the_breach_declined_puts_nothing_and_creates_no_sacrifice():
    scenario = _breach_board()
    giant = scenario.find("Hill Giant", Zone.HAND, "alice")
    scenario.will_take_the_may(False)

    scenario.cast_and_resolve("Through the Breach", *scenario.untapped_sources(*["Mountain"] * 5))

    assert giant.zone is Zone.HAND
    assert scenario.game.delayed_triggers.triggers == []


# --------------------------------------------------------------------------
# Lagomos, Hand of Hatred - a created token, sacrificed
# --------------------------------------------------------------------------


def test_lagomos_token_has_trample_and_haste_and_is_sacrificed_at_end_step():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Lagomos, Hand of Hatred"], library=["Swamp"] * 5)
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _walk_to(scenario, Step.BEGINNING_OF_COMBAT)

    (token,) = [state for state in scenario.game.battlefield if state.token]
    assert (token.power, token.toughness) == (2, 1)
    assert _has_haste(scenario, token)
    assert has_keyword(token, "Trample", scenario.game)

    _walk_to(scenario, Step.END_STEP)

    assert not [state for state in scenario.game.battlefield if state.token]


# --------------------------------------------------------------------------
# Lightning Coils - "remove all of them ... create that many ... Exile them"
# --------------------------------------------------------------------------


def _coils_board(charge: int):
    scenario = (
        Scenario()
        .player("alice", battlefield=["Lightning Coils"], library=["Mountain"] * 5)
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.UNTAP)
    coils = scenario.creature("Lightning Coils")
    if charge:
        scenario.game.add_counters(coils, "charge", charge)
    return scenario, coils


def _elementals(scenario) -> list:
    return [s for s in scenario.game.battlefield if s.token and s.name.startswith("Elemental")]


def test_coils_with_five_counters_removes_them_and_makes_five_hasty_elementals():
    scenario, coils = _coils_board(5)

    _walk_to(scenario, Step.DRAW)

    tokens = _elementals(scenario)
    assert len(tokens) == 5
    assert coils.counter_count("charge") == 0
    assert all((t.power, t.toughness) == (3, 1) for t in tokens)
    assert all(_has_haste(scenario, t) for t in tokens)

    _walk_to(scenario, Step.END_STEP)

    assert _elementals(scenario) == [], "one delayed ability exiles every one of them"


def test_coils_with_seven_counters_makes_seven():
    scenario, coils = _coils_board(7)

    _walk_to(scenario, Step.DRAW)

    assert len(_elementals(scenario)) == 7
    assert coils.counter_count("charge") == 0


def test_coils_with_four_counters_does_not_trigger():
    """CR 603.4: the intervening "if" is false, so nothing triggers."""
    scenario, coils = _coils_board(4)

    _walk_to(scenario, Step.DRAW)

    assert _elementals(scenario) == []
    assert coils.counter_count("charge") == 4


def test_coils_exile_leaves_a_token_that_already_died_alone():
    scenario, _ = _coils_board(5)
    _walk_to(scenario, Step.DRAW)
    first = _elementals(scenario)[0]

    scenario.game.destroy(first)
    _walk_to(scenario, Step.END_STEP)

    assert _elementals(scenario) == []


# --------------------------------------------------------------------------
# Feral Lightning - the plural proof printing on a spell
# --------------------------------------------------------------------------


def test_feral_lightning_makes_three_hasty_elementals_exiled_at_end_step():
    scenario = (
        Scenario()
        .player("alice", hand=["Feral Lightning"], battlefield=["Mountain"] * 6)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("Feral Lightning", *scenario.untapped_sources(*["Mountain"] * 6))

    tokens = _elementals(scenario)
    assert len(tokens) == 3
    assert all(_has_haste(scenario, t) for t in tokens)

    _walk_to(scenario, Step.END_STEP)

    assert _elementals(scenario) == []


def test_every_listed_clause_is_handled_by_the_sweep():
    from magic_cards_model.support import HANDLED, card_support
    from tests.cards import card

    for name in (
        "Fable of the Mirror-Breaker",
        "Nahiri, the Harbinger",
        "Lagomos, Hand of Hatred",
        "Lightning Coils",
        "Kiki-Jiki, Mirror Breaker",
        "Feral Lightning",
        "Through the Breach",
    ):
        support = card_support(card(name))
        for clause in support.clauses:
            if clause.kind == "keyword":
                continue
            assert clause.outcome == HANDLED, (name, clause.text, clause.outcome)
