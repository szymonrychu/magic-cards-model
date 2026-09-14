"""G1-1/G1-2: counted player clauses (`machines/effects.py`'s
`parse_clause_effect` region) - a card printing "N `<effect>` for each
`<qualifier>`" or "`<verb>` X, where X is `<expr>`" used to leave the count
pinned at a bare number, no "for each" tail and no X-where evaluation at all.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 608.2h** - "If an effect requires information from the game ... the
  answer is determined only once, when the effect is applied." - a "for
  each" count and an X-where count are both taken exactly once.
- **CR 119.3** - "If an effect causes a player to gain life or lose life,
  that player's life total is adjusted accordingly."
- **CR 121.1** - drawing a card.
- **CR 701.22a** - scry: "look at the top N cards ... put any number of them
  on the bottom ... and the rest on top".
- **CR 701.25a** - surveil: the graveyard/top-of-library twin of scry.
- **CR 107.3a** - X "isn't defined by the text of that spell or ability" is
  announced; "X, where X is `<expr>`" instead defines it from the text
  itself, evaluated through `count_expression`.

Keruga, the Macrosage and Mastery of the Unseen are the pool cards a "for
each" clause used to leave silent. Atlas, Sizable Stooge, Cerebral Download,
and Oath of Jace are real Modern printings of the same shapes with a
different number, none of them in the pool.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.machines.effects import parse_clause_effect
from tests.scenarios.harness import Scenario

# --------------------------------------------------------------------------
# G1-1: "N <effect> for each <qualifier>"
# --------------------------------------------------------------------------


def test_keruga_draws_a_card_for_each_other_qualifying_permanent_you_control():
    """Keruga, the Macrosage: "When Keruga enters, draw a card for each
    other permanent you control with mana value 3 or greater." Keruga
    itself (mana value 5) is excluded by "other"; a land (mana value 0) and
    a low-cost creature are excluded by the mana value floor; Serra Angel
    (mana value 5) counts.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Keruga, the Macrosage"],
            battlefield=["Forest"] * 5 + ["Serra Angel", "Grizzly Bears"],
            library=["Mountain", "Plains", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Forest"] * 5)
    alice = scenario.player("alice")
    hand_after_cast = len(alice.hand) - 1

    scenario.cast_and_resolve("Keruga, the Macrosage", *sources)
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    # Serra Angel (mana value 5) counts; Grizzly Bears (mana value 2) and
    # the five Forests (mana value 0) do not; Keruga itself is "other"-excluded.
    assert len(alice.hand) == hand_after_cast + 1


def test_mastery_of_the_unseen_gains_life_for_each_creature_with_no_condition():
    """Mastery of the Unseen: "Whenever a permanent you control is turned
    face up, you gain 1 life for each creature you control." No attribute
    filter at all - every creature alice controls counts.

    `machines/triggers.py`'s own `TURNED_FACE_UP` condition match is
    hardcoded self-referential ("mine and event.subject_id == source.id" -
    Brine Elemental's own "when **this creature** is turned face up"), so
    Mastery's own non-self "a permanent you control" phrasing never reaches
    the stack through the real trigger pipeline - a pre-existing gap in
    `triggers.py`'s condition matching, not a number this wave's families
    touch, out of this wave's scope to fix. `parse_clause_effect` is called
    directly instead, on Mastery's own printed clause, and run against a
    real board (CR 608.2h's own board read) the same way `parse_player_
    effect`'s own returned callable would if the trigger fired for real -
    `tests/test_effects.py`'s own "call the parser, not the whole card"
    convention, extended to a live board so the *count* is proven, not just
    that the clause parses.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Mastery of the Unseen", "Serra Angel", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    life_before = alice.life

    effect = parse_clause_effect("you gain 1 life for each creature you control.")
    assert effect is not None
    effect(scenario.game, alice, "Mastery of the Unseen", None)

    # Two creatures alice controls: Serra Angel and Grizzly Bears.
    assert alice.life == life_before + 2


def test_atlas_gains_life_for_each_creature_with_power_four_or_greater():
    """Atlas, Sizable Stooge (off-pool, a different verb-and-attribute
    combination than Keruga's mana value): "Whenever Atlas attacks or
    blocks, you gain 1 life for each creature you control with power 4 or
    greater." Atlas (power 5) and Serra Angel (power 4) qualify; Grizzly
    Bears (power 2) does not.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Atlas, Sizable Stooge", "Serra Angel", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    alice = scenario.player("alice")
    life_before = alice.life
    atlas = scenario.creature("Atlas, Sizable Stooge", "alice")

    scenario.attack_with(atlas, defending="bob")
    scenario.pass_until_resolved()

    assert alice.life == life_before + 2


# --------------------------------------------------------------------------
# G1-2: "<verb> X, where X is <expr>"
# --------------------------------------------------------------------------


def test_oath_of_jaces_upkeep_scries_x_where_x_is_planeswalkers_you_control():
    """Oath of Jace: "At the beginning of your upkeep, scry X, where X is
    the number of planeswalkers you control." One planeswalker on the
    battlefield reads back as a scry of exactly 1."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Oath of Jace", "Narset, Parter of Veils"],
            library=["Forest", "Mountain", "Plains"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.UNTAP)
    scenario.scry_keeping_everything_on_top()

    scenario.advance()
    assert scenario.stack_names() == ["Oath of Jace's triggered ability"]
    scenario.resolve_top()

    scries = [d for d in scenario.questions_asked() if d.kind is DecisionKind.SCRY]
    assert len(scries) == 1
    assert len(scries[0].cards) == 1


def test_cerebral_download_surveils_x_where_x_is_artifacts_you_control():
    """Cerebral Download (off-pool, a different verb and qualifier than
    Oath of Jace's): "Surveil X, where X is the number of artifacts you
    control. Then draw three cards." Two artifacts read back as a surveil
    of exactly 2; the fixed "draw three cards" after it is unaffected."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Cerebral Download"],
            battlefield=["Island"] * 5 + ["Mishra's Bauble", "Mishra's Bauble"],
            library=["Forest"] * 6,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Island"] * 5)
    alice = scenario.player("alice")
    hand_after_cast = len(alice.hand) - 1

    scenario.surveil_keeping_everything_on_top()
    scenario.cast_and_resolve("Cerebral Download", *sources)

    surveils = [d for d in scenario.questions_asked() if d.kind is DecisionKind.SURVEIL]
    assert len(surveils) == 1
    assert len(surveils[0].cards) == 2
    assert len(alice.hand) == hand_after_cast + 3
