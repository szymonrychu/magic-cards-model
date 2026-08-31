"""Returning permanents to their owners' *hands* - the plural half of the
return-to-hand verb, in both of the shapes that print it.

- **Sunderflock**, "When this creature enters, if you cast it, return all
  non-Elemental creatures to their owners' hands." - no target at all: a group
  read off the whole battlefield, with a subtype carved out of it. This is
  `_parse_mass_return_to_hand_clause` in `machines/effects.py`.
- **Marang River Regent**, "When this creature enters, return up to two other
  target nonland permanents to their owners' hands." - the *targeted* plural,
  which is `_RETURN_TARGET_RE` reaching the printed "their owners' hands"
  alongside the singular "its owner's hand" it already read.

The happy path is the first test. Everything after it is a corner: the subtype
negation on both sides of the board, the noncreature permanents the mass return
must not touch, a token that has nowhere to be returned to, and the three ways
a targeted return can come up short - zero targets chosen, the source itself
named, and one of two targets gone by the time the ability resolves.

Every CR number below was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 603.6a** - "Enters-the-battlefield abilities trigger when a permanent
  enters the battlefield."
- **CR 603.4** - "When the trigger event occurs, the ability checks whether the
  stated condition is true. The ability triggers only if it's true." - the
  intervening *if* on Sunderflock's "if you cast it".
- **CR 608.2a** - the same intervening *if*, checked again on resolution.
- **CR 601.2 / CR 701.5a** - "To cast a spell is to take it from where it is
  (usually the hand), put it on the stack, and pay its costs" - the defined
  action "if you cast it" asks about.
- **CR 608.2b** - "If the spell or ability specifies targets, it checks whether
  the targets are still legal. ... The spell or ability is countered if all its
  targets ... are now illegal."
- **CR 608.2c** - "The controller of the spell or ability follows its
  instructions in the order written."
- **CR 608.2f** - "Some spells and abilities include actions taken on multiple
  players and/or objects. In most cases, each such action is processed
  simultaneously."
- **CR 115.2** - "Only permanents are legal targets for spells and abilities,
  unless a spell or ability (a) specifies that it can target an object in
  another zone or a player ..."
- **CR 115.6** - "A spell or ability that requires targets may allow zero
  targets to be chosen."
- **CR 601.2c** - the player announces their choice of an appropriate object
  for each target the spell requires.
- **CR 400.3** - "If an object would go to any library, graveyard, or hand
  other than its owner's, it goes to its owner's corresponding zone."
- **CR 400.7** - "An object that moves from one zone to another becomes a new
  object with no memory of, or relation to, its previous existence."
- **CR 111.7** - "A token that's in a zone other than the battlefield ceases to
  exist. This is a state-based action."
- **CR 704.5d** - the same rule from the state-based action's side.
- **CR 704.3** / **CR 117.5** - state-based actions are performed each time a
  player would get priority, which is what makes the returned token vanish
  without anybody asking.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color
from magic_cards_model.models.token import TokenDefinition, create_tokens
from tests.scenarios.harness import Scenario

#: Sunderflock is `{7}{U}{U}`. Its own cost reduction ("this spell costs {X}
#: less to cast, where X is the greatest mana value among Elementals you
#: control") is a separate mechanic and is not what this file is about, so
#: every board here simply holds the nine Islands the printed cost wants.
ISLANDS = ["Island"] * 9


def _resolve_the_trigger(scenario) -> None:
    """Put the pending enters trigger on the stack (CR 603.3) and resolve it."""
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()


# --------------------------------------------------------------------------
# The happy path
# --------------------------------------------------------------------------


def test_casting_sunderflock_returns_every_non_elemental_creature_to_its_owner():
    """CR 603.6a's enters trigger with CR 603.4's intervening *if* satisfied:
    Sunderflock was cast, so "return all non-Elemental creatures to their
    owners' hands" happens.

    "All ... creatures" is the whole battlefield, not one side of it, and
    CR 400.3 sends each returned card to the hand of *its own* owner rather
    than to the trigger controller's. CR 608.2f makes the group one
    simultaneous action, so nothing here depends on which creature is looked
    at first.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Sunderflock"], battlefield=ISLANDS + ["Grizzly Bears"])
        .player("bob", battlefield=["Memnite"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    islands = scenario.untapped_sources(*ISLANDS)
    flock = scenario.cast_and_resolve("Sunderflock", *islands)
    _resolve_the_trigger(scenario)

    assert flock.zone is Zone.BATTLEFIELD
    assert [state.name for state in scenario.player("alice").hand] == ["Grizzly Bears"]
    assert [state.name for state in scenario.player("bob").hand] == ["Memnite"]
    assert "Grizzly Bears" not in scenario.battlefield_names()
    assert "Memnite" not in scenario.battlefield_names()


# --------------------------------------------------------------------------
# The group Sunderflock names: the subtype it carves out, and the card types
# it never reaches
# --------------------------------------------------------------------------


def test_elementals_are_excluded_on_both_players_sides_of_the_board():
    """The word "non-Elemental" describes each creature, not its controller.

    Sunderflock is itself an Elemental, so the obvious reading - "it spares its
    own team" - passes a one-sided board by accident. This board puts an
    Elemental and a non-Elemental under each player, so the negation has to be
    read off the creature rather than off who controls it. Brine Elemental
    (Creature - Elemental) and Endurance (Creature - Elemental Incarnation)
    both carry the subtype; Grizzly Bears (Bear) and Memnite (Construct) do
    not.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Sunderflock"],
            battlefield=ISLANDS + ["Brine Elemental", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Endurance", "Memnite"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    islands = scenario.untapped_sources(*ISLANDS)
    scenario.cast_and_resolve("Sunderflock", *islands)
    _resolve_the_trigger(scenario)

    battlefield = scenario.battlefield_names()
    assert "Brine Elemental" in battlefield, "alice's own Elemental stayed"
    assert "Endurance" in battlefield, "and so did bob's"
    assert "Sunderflock" in battlefield, "Sunderflock is an Elemental too"
    assert [state.name for state in scenario.player("alice").hand] == ["Grizzly Bears"]
    assert [state.name for state in scenario.player("bob").hand] == ["Memnite"]


def test_noncreature_permanents_are_untouched_by_the_mass_return():
    """The group "all non-Elemental *creatures*" is a card-type restriction as
    much as a subtype one (CR 205.2a's card types).

    An artifact that is not a creature, an enchantment, and every land stay
    exactly where they are. This is the case a negation-only reading gets
    wrong: Sol Ring is not an Elemental either, and a group parsed as "all
    non-Elementals" would bounce it.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Sunderflock"], battlefield=ISLANDS)
        .player("bob", battlefield=["Sol Ring", "Blood Moon", "Forest", "Memnite"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    islands = scenario.untapped_sources(*ISLANDS)
    scenario.cast_and_resolve("Sunderflock", *islands)
    _resolve_the_trigger(scenario)

    battlefield = scenario.battlefield_names()
    assert "Sol Ring" in battlefield, "an artifact that is not a creature"
    assert "Blood Moon" in battlefield, "an enchantment"
    assert "Forest" in battlefield, "a land"
    assert battlefield.count("Island") == 9, "and alice's own lands"
    assert [state.name for state in scenario.player("bob").hand] == ["Memnite"]


def test_a_returned_token_ceases_to_exist_rather_than_sitting_in_a_hand():
    """CR 111.7: "A token that's in a zone other than the battlefield ceases to
    exist. This is a state-based action; see rule 704." CR 704.5d states the
    same thing from the state-based action's side.

    So the mass return really does move the token - it is a non-Elemental
    creature like any other, and the return is not refused (CR 111.8's refusal
    only applies to a token that has *already* left the battlefield). It
    reaches its owner's hand and is then swept away by CR 704.3's check, which
    CR 117.5 runs before anybody next gets priority. The observable end state
    is a token that is in no zone at all, and an owner whose hand holds only
    the real card that came back beside it.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Sunderflock"], battlefield=ISLANDS)
        .player("bob", battlefield=["Memnite"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    spirit = TokenDefinition(subtypes=("Spirit",), colors=(Color.WHITE,), power=1, toughness=1)
    (token,) = create_tokens(scenario.game, spirit, "bob")

    islands = scenario.untapped_sources(*ISLANDS)
    scenario.cast_and_resolve("Sunderflock", *islands)
    _resolve_the_trigger(scenario)

    assert scenario.zones_containing(token) == [], "the token is in no zone at all"
    assert [state.name for state in scenario.player("bob").hand] == ["Memnite"]
    assert "Spirit Token" not in scenario.battlefield_names()


# --------------------------------------------------------------------------
# Sunderflock's intervening *if*: "if you cast it"
# --------------------------------------------------------------------------


def test_sunderflock_put_onto_the_battlefield_returns_nothing():
    """CR 603.4: "When the trigger event occurs, the ability checks whether the
    stated condition is true. The ability triggers only if it's true."

    CR 601.2 and CR 701.5a define casting as taking the card from where it is,
    putting it on the stack and paying its costs. A Sunderflock that arrived
    some other way - here, straight from the hand, standing in for the
    reanimation or the cheat this pool has no dedicated card for - was never
    cast, so "if you cast it" is false and nothing goes on the stack at all.
    Nobody's creatures move.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Sunderflock"], battlefield=["Grizzly Bears"])
        .player("bob", battlefield=["Memnite"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    flock = scenario.put_onto_battlefield("Sunderflock", "alice")
    scenario.game.put_triggers_on_stack()

    assert flock.zone is Zone.BATTLEFIELD
    assert scenario.stack_names() == [], "the intervening *if* stopped it triggering"
    assert sorted(scenario.battlefield_names()) == ["Grizzly Bears", "Memnite", "Sunderflock"]
    assert scenario.player("alice").hand == []
    assert scenario.player("bob").hand == []


# --------------------------------------------------------------------------
# Marang River Regent: the *targeted* plural, "up to two other target nonland
# permanents to their owners' hands"
# --------------------------------------------------------------------------

#: Marang River Regent is `{4}{U}{U}`, and the card is an Omen - its front face
#: is the creature this file casts, the back half ("Coil and Catch") is not.
REGENT = "Marang River Regent"
REGENT_ISLANDS = ["Island"] * 6


def test_two_targets_go_to_two_different_owners_hands():
    """The printed plural, "to their owners' hands", with two owners to prove
    the apostrophe is doing work: CR 400.3 sends each returned card to *its
    own* owner's hand, so one card lands in alice's and the other in bob's.

    "Nonland permanent" is CR 115.2's permanent narrowed by card type, which is
    why the Islands paying for the Regent were never candidates.
    """
    scenario = (
        Scenario()
        .player("alice", hand=[REGENT], battlefield=REGENT_ISLANDS + ["Grizzly Bears"])
        .player("bob", battlefield=["Memnite"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bears = scenario.creature("Grizzly Bears", "alice")
    memnite = scenario.creature("Memnite", "bob")
    scenario.choose_trigger_targets(REGENT, [bears, memnite])

    islands = scenario.untapped_sources(*REGENT_ISLANDS)
    regent = scenario.cast_and_resolve(REGENT, *islands)
    _resolve_the_trigger(scenario)

    assert regent.zone is Zone.BATTLEFIELD
    assert bears.zone is Zone.HAND
    assert memnite.zone is Zone.HAND
    assert scenario.zones_containing(bears) == ["alice:hand"]
    assert scenario.zones_containing(memnite) == ["bob:hand"]


def test_choosing_zero_targets_returns_nothing():
    """CR 115.6: "A spell or ability that requires targets may allow zero
    targets to be chosen. Such a spell or ability is still said to require
    targets, but that spell or ability is targeted only if one or more targets
    have been chosen for it."

    "Up to two" is exactly that permission, so naming nothing is a legal
    announcement rather than a refusal to announce. The trigger still goes on
    the stack and still resolves; it simply returns nothing.
    """
    scenario = (
        Scenario()
        .player("alice", hand=[REGENT], battlefield=REGENT_ISLANDS)
        .player("bob", battlefield=["Grizzly Bears", "Memnite"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.choose_trigger_targets(REGENT, [])

    islands = scenario.untapped_sources(*REGENT_ISLANDS)
    scenario.cast_and_resolve(REGENT, *islands)
    _resolve_the_trigger(scenario)

    assert "Grizzly Bears" in scenario.battlefield_names()
    assert "Memnite" in scenario.battlefield_names()
    assert scenario.player("bob").hand == []


def test_the_regent_cannot_target_itself():
    """The word "*other*" in "up to two other target nonland permanents" is
    what keeps the Regent's own trigger from bouncing the Regent back into the
    hand it was just cast from.

    The restriction is part of the printed target requirement, so CR 601.2c's
    announcement is where it bites: choosing the source is refused with the
    rule's reason and nothing at all is put on the stack targeting it.
    """
    scenario = (
        Scenario()
        .player("alice", hand=[REGENT], battlefield=REGENT_ISLANDS)
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    islands = scenario.untapped_sources(*REGENT_ISLANDS)
    regent = scenario.cast_and_resolve(REGENT, *islands)

    try:
        scenario.choose_trigger_targets(REGENT, [regent])
    except ValueError as error:
        assert "illegal target" in str(error)
    else:  # pragma: no cover - the assertion below reports the failure
        raise AssertionError("the Regent was allowed to target itself")

    assert regent.zone is Zone.BATTLEFIELD


def test_one_target_illegal_by_resolution_still_returns_the_other():
    """CR 608.2b: "If the spell or ability specifies targets, it checks whether
    the targets are still legal. A target that's no longer in the zone it was
    in when it was targeted is illegal. ... The spell or ability is countered
    if all its targets ... are now illegal."

    Two targets were named; bob answers by killing one of his own creatures in
    response. That target is no longer on the battlefield, so it is skipped -
    but the ability is not countered, because *not all* of its targets are
    illegal, and the survivor is still returned.
    """
    scenario = (
        Scenario()
        .player("alice", hand=[REGENT], battlefield=REGENT_ISLANDS)
        .player(
            "bob",
            hand=["Lightning Bolt"],
            battlefield=["Mountain", "Grizzly Bears", "Memnite"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bears = scenario.creature("Grizzly Bears", "bob")
    memnite = scenario.creature("Memnite", "bob")
    scenario.choose_trigger_targets(REGENT, [bears, memnite])

    islands = scenario.untapped_sources(*REGENT_ISLANDS)
    scenario.cast_and_resolve(REGENT, *islands)
    scenario.game.put_triggers_on_stack()

    scenario.pass_priority("alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="bob", targets=[bears])
    assert bears.zone is Zone.GRAVEYARD, "bob answered by killing his own Bears"

    while scenario.game.stack:
        scenario.resolve_top()

    assert bears.zone is Zone.GRAVEYARD, "an illegal target is skipped, not chased"
    assert memnite.zone is Zone.HAND, "the ability was not countered; the survivor came back"
    assert [state.name for state in scenario.player("bob").hand] == ["Memnite"]
