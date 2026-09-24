"""Scenario: "Whenever <this> attacks, you may cast <a spell | target card>
from your graveyard[ without paying its mana cost]. If <an instant or
sorcery spell cast this way | that spell> would be put into your graveyard,
exile it instead." - and "Spells you cast from anywhere other than your hand
cost {1} less to cast."

The cast happens while the trigger resolves (CR 608.2g: "they do so by
following the steps in rules 601.2a-i, except no player receives priority
after it's cast"), paying its own mana cost unless waived. The graveyard
rider is a replacement (CR 614.1a) that applies to the spell cast this way
(the same `CastRecord.exile_instead_of_graveyard` S26's graveyard permissions
set), and on Bilbo only to an instant or sorcery - an artifact spell cast
this way is untouched. The cost reduction is CR 601.2f's, and it asks where
the spell was cast from (CR 601.2a: "from where it is to the stack"): a spell
cast from a hand is not reduced; one cast from a graveyard or exile is.

Printings: Bilbo, Thief in the Night ("an artifact, instant, or sorcery
spell", pays its cost, "an instant or sorcery spell cast this way", the
reduction), off-set The Dawning Archaic ("target instant or sorcery card",
free, "that spell").

CR numbers verified with `mise run rules:find`: 608.2g, 614.1a, 601.2f,
601.2a.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario

BILBO = "Bilbo, Thief in the Night"
ARCHAIC = "The Dawning Archaic"


def test_both_printings_read_their_attack_trigger():
    for name in (BILBO, ARCHAIC):
        triggered = [c for c in card_support(card(name)).clauses if c.kind == "triggered"]
        assert [c.outcome for c in triggered] == ["handled"], name
    statics = [c for c in card_support(card(BILBO)).clauses if c.kind == "static"]
    assert [c.outcome for c in statics] == ["handled"]


def _bilbo_attacks(graveyard, lands, *, take=True, choose=None, targets=None):
    scenario = (
        Scenario()
        .player("alice", battlefield=[BILBO, *lands], graveyard=graveyard, library=["Island"] * 5)
        .player("bob", library=["Island"] * 5)
        .build()
    )
    bilbo = scenario.creature(BILBO)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.will_take_the_may(take)
    if choose is not None:
        scenario.will_choose_cards(scenario.find(choose, Zone.GRAVEYARD, "alice"))
    if targets is not None:
        scenario.will_choose_targets(*targets)
    scenario.attack_with(bilbo, defending="bob")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()  # the trigger: the spell is cast and put on the stack
    return scenario


def test_bilbo_casts_an_instant_from_the_graveyard_and_it_is_exiled_after():
    scenario = _bilbo_attacks(
        ["Lightning Bolt"], ["Mountain"], choose="Lightning Bolt", targets=["bob"]
    )
    assert scenario.stack_names() == ["Lightning Bolt"]
    scenario.resolve_top()
    assert scenario.player("bob").life == 17
    assert scenario.player("alice").graveyard == []
    assert [c.name for c in scenario.game.exile] == ["Lightning Bolt"]


def test_bilbo_casts_an_artifact_for_one_less_and_it_stays_a_permanent():
    """Mind Stone costs {2}; Bilbo's own static takes {1} off a spell cast
    from a graveyard, so one Mountain pays it."""
    scenario = _bilbo_attacks(["Mind Stone"], ["Mountain"], choose="Mind Stone")
    scenario.resolve_top()
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "alice")
    scenario.game.destroy(stone)
    # The rider names only instants and sorceries: the artifact is not exiled.
    assert [c.name for c in scenario.player("alice").graveyard] == ["Mind Stone"]


def test_declining_casts_nothing():
    scenario = _bilbo_attacks(["Lightning Bolt"], ["Mountain"], take=False)
    assert scenario.stack_names() == []
    assert [c.name for c in scenario.player("alice").graveyard] == ["Lightning Bolt"]


def test_a_creature_card_is_not_on_offer():
    """CR 608.2d: with only a creature card there, "yes" is not a legal answer."""
    scenario = _bilbo_attacks(["Grizzly Bears"], ["Forest", "Forest"], take=False)
    (may,) = [q for q in scenario.questions_asked() if q.kind.value == "may"]
    assert may.affirmative_is_legal is False
    assert scenario.stack_names() == []
    assert [c.name for c in scenario.player("alice").graveyard] == ["Grizzly Bears"]


# -- Bilbo's static: spells cast from anywhere other than your hand ----------


def test_a_spell_cast_from_hand_is_not_reduced():
    scenario = (
        Scenario()
        .player("alice", battlefield=[BILBO, "Island", "Island"], hand=["Mind Stone"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Mind Stone")
    assert casting.total_cost.mana.converted == 2


def test_a_flashback_from_the_graveyard_is_reduced_by_one():
    scenario = (
        Scenario()
        .player(
            "alice", battlefield=[BILBO], graveyard=["Faithless Looting"], library=["Island"] * 3
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Faithless Looting", from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Flashback")
    # Flashback {2}{R} less {1}.
    assert casting.total_cost.mana.converted == 2


def test_an_opponents_graveyard_cast_is_not_reduced():
    scenario = (
        Scenario()
        .player("alice", battlefield=[BILBO])
        .player("bob", graveyard=["Faithless Looting"], library=["Island"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")
    casting = scenario.cast("Faithless Looting", username="bob", from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Flashback")
    assert casting.total_cost.mana.converted == 3


# -- The Dawning Archaic: a targeted card, free, "that spell" ----------------


def test_the_dawning_archaic_casts_its_target_free_and_exiles_it_after():
    scenario = (
        Scenario()
        .player(
            "alice", battlefield=[ARCHAIC], graveyard=["Lightning Bolt"], library=["Island"] * 5
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    archaic = scenario.creature(ARCHAIC)
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.choose_trigger_targets(ARCHAIC, [bolt])
    scenario.will_take_the_may(True)
    scenario.will_choose_targets("bob")
    scenario.attack_with(archaic, defending="bob")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()
    assert scenario.stack_names() == ["Lightning Bolt"]
    scenario.resolve_top()
    assert scenario.player("bob").life == 17
    assert [c.name for c in scenario.game.exile] == ["Lightning Bolt"]


def test_the_dawning_archaic_costs_one_less_per_instant_and_sorcery_card_in_your_graveyard():
    """Its own CR 601.2f self-reduction: three of the four graveyard cards are
    instants or sorceries, the creature card does not count."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[ARCHAIC],
            graveyard=["Lightning Bolt", "Opt", "Faithless Looting", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert scenario.cast(ARCHAIC).total_cost.mana.converted == 7
