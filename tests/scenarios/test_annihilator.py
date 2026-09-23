"""Scenario: annihilator, fixed and variable.

CR 702.86a: "Annihilator is a triggered ability. 'Annihilator N' means
'Whenever this creature attacks, defending player sacrifices N
permanents.'" CR 702.86b: "If a creature has multiple instances of
annihilator, each triggers separately."

Two printings, two shapes of N:

- **Ulamog's Crusher** (off-pool proof printing) prints the keyword with a
  fixed N: "Annihilator 2".
- **Ulamog, the Defiler** grants itself the keyword through a static
  ability with a variable N: "Ulamog has annihilator X, where X is the
  number of +1/+1 counters on it." X is counted when the trigger resolves
  (CR 608.2h), not when it triggers.

Every CR number below was read with `mise run rules:find` in the session
that wrote this file:

- **CR 702.86a/b** - as quoted above.
- **CR 508.5** - "If an ability of an attacking creature refers to a
  defending player ... the defending player it's referring to is the player
  that creature is attacking".
- **CR 608.2h** - "If an effect requires information from the game ... the
  answer is determined only once, when the effect is applied."
- **CR 701.21a** - "To sacrifice a permanent, its controller moves it from
  the battlefield directly to its owner's graveyard." Indestructible does not
  stop it: nothing is destroyed.
- **CR 613.1f** - layer 6, where Ulamog's self-granted keyword is added.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

CRUSHER = "Ulamog's Crusher"
ULAMOG = "Ulamog, the Defiler"


def _board(alices: list[str], bobs: list[str]):
    scenario = (
        Scenario()
        .player("alice", battlefield=alices, hand=[ULAMOG] if ULAMOG in alices else [])
        .player("bob", battlefield=bobs, library=["Forest"] * 5)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario


def _bobs_names(scenario) -> list[str]:
    return sorted(state.name for state in scenario.game.battlefield if state.controller == "bob")


# -- the fixed form: Ulamog's Crusher --------------------------------------


def test_annihilator_two_makes_the_defending_player_sacrifice_two_of_their_choice():
    scenario = _board([CRUSHER], ["Forest", "Island", "Grizzly Bears"])
    crusher = scenario.creature(CRUSHER, "alice")
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "bob")
    island = scenario.find("Island", Zone.BATTLEFIELD, "bob")
    scenario.will_choose_cards(forest, island, username="bob")

    scenario.attack_with(crusher, defending="bob")
    scenario.pass_until_resolved()

    assert _bobs_names(scenario) == ["Grizzly Bears"]
    assert sorted(state.name for state in scenario.player("bob").graveyard) == [
        "Forest",
        "Island",
    ]


def test_the_choice_is_the_defending_players_not_the_attackers():
    """Bob picks: whatever he names goes, the rest stays."""
    scenario = _board([CRUSHER], ["Forest", "Island", "Grizzly Bears"])
    crusher = scenario.creature(CRUSHER, "alice")
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    island = scenario.find("Island", Zone.BATTLEFIELD, "bob")
    scenario.will_choose_cards(bears, island, username="bob")

    scenario.attack_with(crusher, defending="bob")
    scenario.pass_until_resolved()

    assert _bobs_names(scenario) == ["Forest"]
    (question,) = [
        decision for decision in scenario.questions_asked() if decision.source == CRUSHER
    ]
    assert question.player == "bob"


def test_exactly_n_permanents_are_all_sacrificed_without_a_question():
    scenario = _board([CRUSHER], ["Forest", "Grizzly Bears"])
    crusher = scenario.creature(CRUSHER, "alice")

    scenario.attack_with(crusher, defending="bob")
    scenario.pass_until_resolved()

    assert _bobs_names(scenario) == []
    assert not [d for d in scenario.questions_asked() if d.source == CRUSHER]


def test_fewer_than_n_permanents_sacrifices_what_there_is():
    scenario = _board([CRUSHER], ["Forest"])
    crusher = scenario.creature(CRUSHER, "alice")

    scenario.attack_with(crusher, defending="bob")
    scenario.pass_until_resolved()

    assert _bobs_names(scenario) == []
    assert [state.name for state in scenario.player("bob").graveyard] == ["Forest"]


def test_a_defending_player_with_no_permanents_sacrifices_nothing():
    scenario = _board([CRUSHER], [])
    crusher = scenario.creature(CRUSHER, "alice")

    scenario.attack_with(crusher, defending="bob")
    scenario.pass_until_resolved()

    assert scenario.player("bob").graveyard == []


def test_an_indestructible_permanent_is_still_sacrificed():
    """CR 701.21a: sacrifice is not destruction."""
    scenario = _board([CRUSHER], ["Darksteel Relic", "Forest"])
    crusher = scenario.creature(CRUSHER, "alice")

    scenario.attack_with(crusher, defending="bob")
    scenario.pass_until_resolved()

    assert sorted(state.name for state in scenario.player("bob").graveyard) == [
        "Darksteel Relic",
        "Forest",
    ]


def test_the_attackers_own_permanents_are_untouched():
    scenario = _board([CRUSHER, "Mountain", "Mountain"], ["Forest", "Island"])
    crusher = scenario.creature(CRUSHER, "alice")

    scenario.attack_with(crusher, defending="bob")
    scenario.pass_until_resolved()

    assert scenario.player("alice").graveyard == []
    assert _bobs_names(scenario) == []


def test_the_trigger_goes_on_the_stack_when_the_creature_attacks():
    scenario = _board([CRUSHER], ["Forest", "Island"])
    crusher = scenario.creature(CRUSHER, "alice")

    scenario.attack_with(crusher, defending="bob")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == [f"{CRUSHER}'s triggered ability"]


def test_counters_do_not_change_a_fixed_annihilator():
    """The X/fixed split: +1/+1 counters grow Ulamog's X, but the Crusher's
    printed 2 stays 2."""
    scenario = _board([CRUSHER], ["Forest", "Island", "Swamp", "Plains"])
    crusher = scenario.creature(CRUSHER, "alice")
    scenario.game.add_counters(crusher, Counter.PLUS_ONE, 3)

    scenario.attack_with(crusher, defending="bob")
    scenario.pass_until_resolved()

    assert len(_bobs_names(scenario)) == 2


# -- the variable form: Ulamog, the Defiler --------------------------------


def _ulamog_with(counters: int, bobs: list[str], *, frog: bool = False):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[ULAMOG, *(["Turn to Frog"] if frog else [])],
            battlefield=["Island", "Island"] if frog else [],
        )
        .player("bob", battlefield=bobs, library=["Forest"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ulamog = scenario.put_onto_battlefield(ULAMOG, "alice")
    # Nothing in exile, so it entered with none (CR 107.2's empty maximum).
    assert ulamog.counters[Counter.PLUS_ONE] == 0
    if counters:
        scenario.game.add_counters(ulamog, Counter.PLUS_ONE, counters)
    ulamog.summoning_sick = False
    if frog:
        islands = scenario.untapped_sources("Island", "Island", username="alice")
        scenario.cast_and_resolve("Turn to Frog", *islands, targets=[ulamog])
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario, ulamog


def test_ulamog_has_annihilator_equal_to_its_counters():
    scenario, ulamog = _ulamog_with(3, ["Forest", "Island", "Swamp", "Plains", "Grizzly Bears"])

    scenario.attack_with(ulamog, defending="bob")
    scenario.pass_until_resolved()

    assert len(_bobs_names(scenario)) == 2
    assert len(scenario.player("bob").graveyard) == 3


def test_ulamogs_x_is_counted_as_the_trigger_resolves():
    """CR 608.2h: two more counters put on Ulamog while its trigger waits
    raise X from two to four."""
    scenario, ulamog = _ulamog_with(2, ["Forest", "Island", "Swamp", "Plains", "Grizzly Bears"])

    scenario.attack_with(ulamog, defending="bob")
    scenario.game.put_triggers_on_stack()
    scenario.game.add_counters(ulamog, Counter.PLUS_ONE, 2)
    scenario.pass_until_resolved()

    assert len(scenario.player("bob").graveyard) == 4


def test_ulamog_with_no_counters_has_annihilator_zero():
    """X is zero: the ability still triggers, and sacrifices nothing."""
    scenario, ulamog = _ulamog_with(0, ["Forest", "Island"])

    scenario.attack_with(ulamog, defending="bob")
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == [f"{ULAMOG}'s triggered ability"]
    scenario.pass_until_resolved()

    assert scenario.player("bob").graveyard == []
    assert _bobs_names(scenario) == ["Forest", "Island"]


def test_ulamog_that_lost_its_abilities_has_no_annihilator():
    """CR 613.1f: the keyword comes from Ulamog's own static ability. Turned
    into a Frog that "loses all abilities" until end of turn, Ulamog grants
    itself nothing, so its attack triggers nothing."""
    scenario, ulamog = _ulamog_with(3, ["Forest", "Island", "Swamp"], frog=True)

    scenario.attack_with(ulamog, defending="bob")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []
