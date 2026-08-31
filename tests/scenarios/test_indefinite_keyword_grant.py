"""Scenario: "[Other] creatures [you control|your opponents control] have
<keyword(s)>." - the anthem shape's keyword-granting twin, with no "until end
of turn" (CR 611.3, CR 611.3b).

True Conviction ("Creatures you control have double strike and lifelink.") is
the real card this shape was generalised from. Unlike the temporary
`_KEYWORD_GRANT_RE` shape (`test_parsed_layer_effects.py`'s Assault Strobe), a
static ability's effect exists exactly as long as its source does (CR 611.3b),
so this file's other half is proving that: the grant switches off the moment
True Conviction leaves the battlefield (CR 613.6), which a duration can never
do because there is no duration to expire.

`_split_and_validate_keywords` also gets its own coverage here: a card with
more than one granted keyword (True Conviction) reads both, and a card
granting a keyword outside `_KNOWN_KEYWORDS`'s whitelist (Asceticism's
hexproof - not modelled by `machines/combat.py`'s `Keyword`) fails closed with
a `LayerNotice` instead of granting nothing silently.

Every CR number here was looked up with `knowledge_search(type="rules")` in
the session that wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from tests.scenarios.harness import Scenario


def computed(scenario: Scenario):
    """The board with static abilities and stored durational effects applied."""
    return scenario.game.continuous_effects.board(scenario.game.battlefield)


def test_true_conviction_grants_both_printed_keywords():
    """CR 613.1f: both "double strike" and "lifelink" are read out of the one
    sentence, not just the first.
    """
    scenario = Scenario().player("alice", battlefield=["True Conviction", "Grizzly Bears"]).build()
    bears = scenario.creature("Grizzly Bears", "alice")

    board = computed(scenario)

    assert board.of(bears).has_ability("Double strike")
    assert board.of(bears).has_ability("Lifelink")
    assert has_keyword(bears, Keyword.DOUBLE_STRIKE, scenario.game)
    assert has_keyword(bears, Keyword.LIFELINK, scenario.game)


def test_the_granted_double_strike_and_lifelink_are_functional_in_combat():
    """CR 510.4 (two combat damage steps) and CR 702.15b (life gain) both pay
    off from a grant, not a printed keyword - Grizzly Bears has neither.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["True Conviction", "Grizzly Bears"])
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(bears)
    scenario.no_blocks()
    alice = scenario.player("alice")
    bob = scenario.player("bob")
    alice_life_before, bob_life_before = alice.life, bob.life

    dealt = scenario.combat_damage()

    assert len(dealt) == 2, "double strike means two combat damage steps (CR 510.4)"
    assert bob_life_before - bob.life == 4, "a 2-power double striker deals 2 damage twice"
    assert alice.life - alice_life_before == 4, "lifelink gains life equal to all of that damage"


def test_the_grant_switches_off_the_moment_true_conviction_leaves():
    """CR 611.3b: "The effect applies at all times that the permanent
    generating it is on the battlefield." Unlike a duration-based grant, there
    is nothing here to run out - the effect is simply not generated once the
    source is gone (CR 613.6 fixes the reasoning at the ability, not at a
    clock).
    """
    scenario = Scenario().player("alice", battlefield=["True Conviction", "Grizzly Bears"]).build()
    bears = scenario.creature("Grizzly Bears", "alice")
    assert has_keyword(bears, Keyword.DOUBLE_STRIKE, scenario.game)

    conviction = scenario.creature("True Conviction", "alice")
    scenario.game.destroy(conviction)

    assert not has_keyword(bears, Keyword.DOUBLE_STRIKE, scenario.game)
    assert not has_keyword(bears, Keyword.LIFELINK, scenario.game)


def test_asceticisms_hexproof_grant_applies():
    """Asceticism: "Creatures you control have hexproof." (verified with
    `resolve_cards`) reads exactly like True Conviction's shape, and now grants
    exactly like it too.

    Hexproof (CR 702.11a: "Hexproof is a static ability"; CR 702.11b: "This
    permanent can't be the target of spells or abilities your opponents
    control") is not in `machines/combat.py`'s `Keyword` vocabulary, because no
    combat rule reads it - but `machines/casting.py` reads it off the *computed*
    board when it checks target legality, so a layer 6 grant (CR 613.1f) of it
    is a real one. This used to fail closed with a `LayerNotice` purely because
    `machines/layers.py`'s whitelist was the combat vocabulary verbatim.

    The card's other line, the regeneration activated ability, is not a
    continuous effect and records nothing either way.
    """
    scenario = Scenario().player("alice", battlefield=["Asceticism", "Grizzly Bears"]).build()
    bears = scenario.creature("Grizzly Bears", "alice")

    board = computed(scenario)

    assert board.of(bears).has_ability("Hexproof")
    assert scenario.game.continuous_effects.layer_notices == []
