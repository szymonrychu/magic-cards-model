"""EP-02-R3 T7: "for each <thing>" and "equal to the number of <things>" counts
that read a turn's history, a cast record, the Curses attached to a player or
the distinct mana values on a board.

Rules, each looked up with `mise run rules:find` in the session that wrote this
file:

- **CR 700.4** - "dies" means is put into a graveyard from the battlefield.
- **CR 608.2h** - information an effect needs is taken once, as the effect is
  applied.
- **CR 608.2c** - instructions are followed in the order written.
- **CR 107.3a** - X on a spell or ability.
- **CR 122.1** - counters.
- **CR 202.3** - mana value.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import Scenario

LISTED = [
    "Aetherspouts",
    "Agadeem Occultist",
    "Anticausal Vestige",
    "Ashen-Skin Zubera",
    "Biomantic Mastery",
    "Blinkmoth Urn",
    "Bloodhusk Ritualist",
    "Curse of Surveillance",
    "Curse of Thirst",
    "Dark Salvation",
    "Deadly Embrace",
    "Desert's Due",
    "Dream Salvage",
    "Engulf the Shore",
    "Fiery Bombardment",
    "Floating-Dream Zubera",
    "Hateful Eidolon",
    "Heirloom Epic",
    "Hobgoblin Bandit Lord",
    "Lightmine Field",
    "Lunar Insight",
    "Magebane Lizard",
    "Rending Vines",
    "Riptide Gearhulk",
    "Rumbling Aftershocks",
    "Sepulchral Primordial",
    "Shared Animosity",
    "Soul of Emancipation",
    "Squirming Emergence",
    "The Chain Veil",
]

PROOF = [
    "Silent-Chant Zubera",
]

LANDS = ["Plains"] * 6 + ["Swamp"] * 4 + ["Island"] * 4 + ["Forest"] * 3 + ["Mountain"] * 4


@pytest.mark.parametrize("name", LISTED + PROOF)
def test_every_clause_of_a_listed_card_is_handled(name: str) -> None:
    clauses = classify_clauses(card(name))
    assert clauses
    assert all(clause.category == HANDLED for clause in clauses), [
        (clause.text, clause.category) for clause in clauses if clause.category != HANDLED
    ]


def _scenario(
    alice: list[str],
    bob: list[str] | None = None,
    *,
    hand: list[str] | None = None,
    library: list[str] | None = None,
    bob_hand: list[str] | None = None,
    bob_library: list[str] | None = None,
    graveyard: list[str] | None = None,
    bob_graveyard: list[str] | None = None,
    step: Step = Step.PRECOMBAT_MAIN,
):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[*alice, *LANDS],
            hand=hand,
            graveyard=graveyard,
            library=library or ["Island"] * 12,
        )
        .player(
            "bob",
            battlefield=[*(bob or []), *LANDS],
            hand=bob_hand,
            graveyard=bob_graveyard,
            library=bob_library or ["Island"] * 12,
        )
        .build()
    )
    scenario.start_at(step)
    return scenario


def _resolve_all(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _cast_all(scenario, name: str, *, user: str = "alice", targets=None, x: int | None = None):
    """Cast `name` and resolve the spell, its triggers and everything they
    put on the stack."""
    if x is None:
        scenario.cast_onto_stack(name, username=user, targets=targets, auto=True)
    else:
        spell = scenario.find(name, Zone.HAND, user)
        scenario.game.cast(
            spell,
            user,
            x_value=x,
            targets=targets,
            mana_sources=scenario.untapped_sources(*LANDS, username=user),
        )
    _resolve_all(scenario)


def _named(scenario, name: str, zone: Zone = Zone.BATTLEFIELD, user: str | None = None) -> list:
    return [
        state
        for state in scenario.all_card_states()
        if state.name in (name, f"{name} Token")
        and state.zone is zone
        and (user is None or state.owner == user)
    ]


def _life(scenario, who: str) -> int:
    return scenario.player(who).life


def _hand(scenario, who: str) -> int:
    return len(scenario.player(who).hand)


# ---------------------------------------------------------------------------
# "for each <thing> that died this turn" (CR 700.4)
# ---------------------------------------------------------------------------


def test_deadly_embrace_draws_for_the_creature_it_destroyed() -> None:
    scenario = _scenario([], ["Grizzly Bears"], hand=["Deadly Embrace"])
    _cast_all(scenario, "Deadly Embrace", targets=[scenario.creature("Grizzly Bears", "bob")])
    assert scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob") is not None
    assert _hand(scenario, "alice") == 1


def test_deadly_embrace_counts_a_creature_that_died_earlier_this_turn() -> None:
    scenario = _scenario(
        ["Grizzly Bears"], ["Grizzly Bears"], hand=["Deadly Embrace", "Lightning Bolt"]
    )
    _cast_all(scenario, "Lightning Bolt", targets=[scenario.creature("Grizzly Bears", "alice")])
    _cast_all(scenario, "Deadly Embrace", targets=[scenario.creature("Grizzly Bears", "bob")])
    assert _hand(scenario, "alice") == 2  # both Bears died this turn, whoever controlled them


def test_deadly_embrace_counts_nothing_when_the_destroy_fails_to_kill() -> None:
    scenario = _scenario([], ["Grizzly Bears"], hand=["Deadly Embrace"])
    scenario.cast_onto_stack(
        "Deadly Embrace",
        username="alice",
        targets=[scenario.creature("Grizzly Bears", "bob")],
        auto=True,
    )
    # the target is gone before it resolves: the spell fizzles and draws nothing (CR 608.2b)
    scenario.game.destroy(scenario.creature("Grizzly Bears", "bob"))
    hand_before = _hand(scenario, "alice")
    _resolve_all(scenario)
    assert _hand(scenario, "alice") == hand_before


def test_floating_dream_zubera_draws_for_each_zubera_that_died() -> None:
    scenario = _scenario(
        ["Floating-Dream Zubera", "Floating-Dream Zubera"], hand=["Wrath of God"]
    )
    _cast_all(scenario, "Wrath of God")
    # each Zubera's trigger sees both deaths: two triggers x two Zubera
    assert _hand(scenario, "alice") == 4


def test_floating_dream_zubera_ignores_other_creatures_dying() -> None:
    scenario = _scenario(["Floating-Dream Zubera", "Grizzly Bears"], hand=["Wrath of God"])
    _cast_all(scenario, "Wrath of God")
    assert _hand(scenario, "alice") == 1


def test_ashen_skin_zubera_makes_the_opponent_discard_per_zubera() -> None:
    scenario = _scenario(
        ["Ashen-Skin Zubera"],
        ["Floating-Dream Zubera"],
        hand=["Wrath of God"],
        bob_hand=["Island", "Island", "Island", "Island"],
    )
    scenario.choose_trigger_targets("Ashen-Skin Zubera", [scenario.player("bob")])
    _cast_all(scenario, "Wrath of God")
    # two Zubera died this turn (either controller): bob discards two, and draws one from his own
    assert len(scenario.player("bob").graveyard) >= 2


def test_ashen_skin_zubera_discards_one_when_it_dies_alone() -> None:
    scenario = _scenario(
        ["Ashen-Skin Zubera"], hand=["Lightning Bolt"], bob_hand=["Island", "Island"]
    )
    scenario.choose_trigger_targets("Ashen-Skin Zubera", [scenario.player("bob")])
    _cast_all(scenario, "Lightning Bolt", targets=[scenario.creature("Ashen-Skin Zubera", "alice")])
    assert _hand(scenario, "bob") == 1


def test_silent_chant_zubera_gains_two_life_per_zubera_that_died() -> None:
    scenario = _scenario(
        ["Silent-Chant Zubera", "Floating-Dream Zubera"], hand=["Wrath of God"]
    )
    _cast_all(scenario, "Wrath of God")
    assert _life(scenario, "alice") == 20 + 2 * 2
