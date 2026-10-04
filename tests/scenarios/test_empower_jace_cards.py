"""The rest of the Reality Fracture Jace cards, each proven on its own real
printing and whole text: Way of the Mentor, Way of the Necromancer, Inspired
Tethermage, Jace's Machinations, Jace, Reality Sculptor, and the empower
corner cases every one of them shares.

Read out of the Comprehensive Rules on disk with `mise run rules:find`:

- **CR 701.71a** - empower Jace N: create the Jace token only if you control
  none, choose one, put N loyalty counters on it.
- **CR 306.5c / 704.5i** - a planeswalker's loyalty is its loyalty counters;
  at 0 it goes to its owner's graveyard (a token then ceases to exist).
- **CR 606.3 / 606.4** - loyalty abilities: once per permanent per turn at
  sorcery speed (loosened only by Jace's Machinations), cost counters.
- **CR 305.2** - additional land plays are cumulative.
- **CR 603.2** - one trigger per event.
- **CR 506.4/508** - attacking creature triggers; CR 613 for -5/-0.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import CardState, Zone
from magic_cards_model.models.card_state import Counter

from .harness import Scenario


def _tokens(scenario, username: str = "alice") -> list[CardState]:
    return [p for p in scenario.game.battlefield if p.name == "Jace" and p.controller == username]


def _resolve_all(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _enter(scenario, name: str) -> None:
    scenario.put_onto_battlefield(name)
    _resolve_all(scenario)


# -- empower corner cases -----------------------------------------------------


def test_a_non_token_jace_planeswalker_does_not_count_as_the_token():
    """CR 701.71a asks for a Jace planeswalker *token*; Jace, Reality
    Sculptor on the battlefield does not stop the token being created, and
    its own loyalty is untouched."""
    scenario = (
        Scenario()
        .player("alice", hand=["Way of the Necromancer"], battlefield=["Jace, Reality Sculptor"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sculptor = scenario.find("Jace, Reality Sculptor", Zone.BATTLEFIELD, "alice")

    _enter(scenario, "Way of the Necromancer")

    (token,) = _tokens(scenario)
    assert token.loyalty == 2
    assert sculptor.loyalty == 5


def test_a_token_left_at_zero_loyalty_is_put_into_the_graveyard_and_ceases_to_exist():
    scenario = (
        Scenario()
        .player("alice", hand=["Way of the Necromancer"], library=["Island"] * 3)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _enter(scenario, "Way of the Necromancer")
    (token,) = _tokens(scenario)
    scenario.game.add_counters(token, Counter.LOYALTY, 1)  # 3, so [-3] empties it

    scenario.activate(token, index=1)  # [-3]: Draw a card.
    _resolve_all(scenario)

    assert _tokens(scenario) == []
    assert token.zone is not Zone.BATTLEFIELD


def test_the_tokens_minus_one_surveils_one():
    scenario = (
        Scenario()
        .player("alice", hand=["Way of the Necromancer"], library=["Island", "Forest", "Swamp"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _enter(scenario, "Way of the Necromancer")
    (token,) = _tokens(scenario)
    (top,) = scenario.top_of_library(1)
    scenario.surveil_to_graveyard(top)

    scenario.activate(token, index=0)  # [-1]: Surveil 1.
    _resolve_all(scenario)

    assert token.loyalty == 1
    assert [s.name for s in scenario.player("alice").graveyard] == ["Island"]


# -- Way of the Mentor --------------------------------------------------------


def test_way_of_the_mentor_adds_a_counter_to_every_planeswalker_once_per_life_gain():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Way of the Mentor"],
            battlefield=["Ajani Unrelenting"],
        )
        .player("bob", battlefield=["Ajani Unrelenting"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _enter(scenario, "Way of the Mentor")
    (token,) = _tokens(scenario)
    assert token.loyalty == 5
    mine = scenario.find("Ajani Unrelenting", Zone.BATTLEFIELD, "alice")
    theirs = scenario.find("Ajani Unrelenting", Zone.BATTLEFIELD, "bob")
    before, theirs_before = mine.loyalty, theirs.loyalty

    scenario.game.gain_life("alice", 3)  # one event, however much
    _resolve_all(scenario)

    assert token.loyalty == 6
    assert mine.loyalty == before + 1
    assert theirs.loyalty == theirs_before, "only planeswalkers alice controls"

    scenario.game.gain_life("bob", 2)  # an opponent's gain is not "you gain life"
    _resolve_all(scenario)
    assert token.loyalty == 6


# -- Way of the Necromancer ---------------------------------------------------


def test_way_of_the_necromancer_counts_every_creature_that_dies_tokens_included():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Way of the Necromancer"],
            battlefield=["Grizzly Bears", "Ajani Unrelenting"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _enter(scenario, "Way of the Necromancer")
    (token,) = _tokens(scenario)
    assert token.loyalty == 2
    ajani = scenario.find("Ajani Unrelenting", Zone.BATTLEFIELD, "alice")
    ajani_before = ajani.loyalty

    scenario.game.destroy(scenario.creature("Grizzly Bears", "alice"))
    _resolve_all(scenario)
    assert token.loyalty == 3
    assert ajani.loyalty == ajani_before + 1

    scenario.game.destroy(scenario.creature("Grizzly Bears", "bob"))  # not "you control"
    _resolve_all(scenario)
    assert token.loyalty == 3


# -- Inspired Tethermage ------------------------------------------------------


def test_inspired_tethermage_grows_once_when_empower_puts_counters_on_the_token():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Inspired Tethermage"] + ["Forest"] * 6)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tethermage = scenario.creature("Inspired Tethermage", "alice")
    sources = scenario.untapped_sources(*["Forest"] * 6)

    scenario.activate(tethermage, *sources)  # {6}: Empower Jace 2.
    _resolve_all(scenario)

    assert _tokens(scenario)[0].loyalty == 2
    assert tethermage.counter_count("+1/+1") == 1, "one event, one trigger"


def test_inspired_tethermage_counts_a_plus_one_loyalty_cost_as_putting_counters():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Inspired Tethermage", "Ajani Unrelenting"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tethermage = scenario.creature("Inspired Tethermage", "alice")
    ajani = scenario.find("Ajani Unrelenting", Zone.BATTLEFIELD, "alice")

    scenario.activate(ajani, index=0)  # +1
    _resolve_all(scenario)

    assert tethermage.counter_count("+1/+1") == 1


# -- Jace's Machinations ------------------------------------------------------


def _machinations_board():
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Jace's Machinations"],
            library=["Forest"] * 5,
            battlefield=["Island", "Island", "Island", "Ajani Unrelenting"],
        )
        .player("bob")
        .build()
    )


def test_machinations_empowers_eight_and_the_new_token_may_act_on_the_opponents_turn_once():
    scenario = _machinations_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Island", "Island", "Island")
    scenario.cast_and_resolve("Jace's Machinations", *sources)
    (token,) = _tokens(scenario)
    assert token.loyalty == 8

    while scenario.turn.active_player != "bob":
        scenario.advance()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("bob")

    assert scenario.why_cannot_activate(token, index=0) is None, "the new token qualifies"
    ajani = scenario.find("Ajani Unrelenting", Zone.BATTLEFIELD, "alice")
    assert "CR 606.3" in (scenario.why_cannot_activate(ajani, index=0) or "")

    scenario.activate(token, index=0)  # [-1]: Surveil 1.
    _resolve_all(scenario)
    assert token.loyalty == 7

    reason = scenario.why_cannot_activate(token, index=1)
    assert reason is not None, "CR 606.3's once-per-turn limit still applies"


# -- Jace, Reality Sculptor ---------------------------------------------------


def test_reality_sculptor_minus_three_shrinks_attackers_of_you_until_your_next_turn():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Jace, Reality Sculptor"], library=["Island"] * 5)
        .player("bob", battlefield=["Serra Angel"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sculptor = scenario.find("Jace, Reality Sculptor", Zone.BATTLEFIELD, "alice")

    scenario.activate(sculptor, index=1)  # -3
    _resolve_all(scenario)

    while scenario.turn.active_player != "bob":
        scenario.advance()
    while scenario.step is not Step.DECLARE_ATTACKERS:
        scenario.advance()
    angel = scenario.creature("Serra Angel", "bob")
    scenario.attack_with(angel, defending="alice")
    _resolve_all(scenario)

    assert scenario.game.power_of(angel) == 4 - 5


def test_a_nontoken_and_a_token_jace_both_count_toward_the_twenty_five():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Way of the Necromancer"],
            battlefield=["Jace, Reality Sculptor"],
            library=["Island"] * 3,
        )
        .player("bob", library=["Island", "Forest", "Swamp"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sculptor = scenario.find("Jace, Reality Sculptor", Zone.BATTLEFIELD, "alice")
    _enter(scenario, "Way of the Necromancer")
    (token,) = _tokens(scenario)  # 2
    scenario.game.add_counters(token, Counter.LOYALTY, 17)  # 5 + 19 = 24
    assert scenario.why_cannot_activate(sculptor, index=2) is not None

    scenario.game.add_counters(token, Counter.LOYALTY, 1)  # 25

    assert scenario.why_cannot_activate(sculptor, index=2) is None


def test_reality_sculptor_zero_exiles_all_but_the_bottom_card_of_each_opponents_library():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Jace, Reality Sculptor"], library=["Island"] * 5)
        .player("bob", library=["Island", "Forest", "Swamp", "Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sculptor = scenario.find("Jace, Reality Sculptor", Zone.BATTLEFIELD, "alice")
    scenario.game.add_counters(sculptor, Counter.LOYALTY, 20)  # 25 among Jaces

    scenario.activate(sculptor, index=2)  # 0
    _resolve_all(scenario)

    assert [s.name for s in scenario.player("bob").library] == ["Plains"]
    assert sum(1 for s in scenario.game.exile if s.owner == "bob") == 3
