"""The mana tap plan, reported alongside the action rather than discarded.

`auto_tap` has always solved *which* sources to tap and *which* colour each
makes before tapping anything, and `could_pay_mana_cost` has always run that
identical solve and thrown the answer away to return a bare `True`. This file
covers the surfaced version: `plan_mana_payment` returns the plan itself, the
predicate is that function's `is not None`, and `legal_actions` carries the
plan on `Action.pays_with` for every affordable action that owes mana.

The plan is **purely informational**. Nothing here asks a seat to name its
mana sources - `auto_tap` still chooses, still stops as soon as the pool can
pay, and still never taps more than that. What the plan answers is a question
a seat cannot otherwise ask without casting the spell: *which* of my sources
does this spell eat. "This Bolt takes the Cavern of Souls I was holding for
the creature I actually want to cast" is a strategic fact; "how do I pay for a
Bolt" is not.

Every CR number written below was looked up in the session that wrote this
file, with `mise run rules:pull` and `mise run rules:find <number>` against
the Comprehensive Rules effective August 7, 2026:

- **CR 601.2g** - "If the total cost includes a mana payment, the player then
  has a chance to activate mana abilities... Mana abilities must be activated
  before costs are paid." The plan is a prediction of exactly that window.
- **CR 118.3c** - "Activating mana abilities is not mandatory, even if paying
  a cost is." Why the plan never names more sources than the cost needs.
- **CR 106.6** - "Some spells or abilities that produce mana restrict how that
  mana can be spent..." The restriction rides on the mana, so the plan reports
  it per entry, quoting the card's own sentence.
- **CR 605.1a** - what makes an activated ability a mana ability at all; the
  `ability_index` each entry carries is that ability's index in
  `Game.activated_abilities`, the same number `Game.activate_ability` takes.
- **CR 118.6** - "Attempting to cast a spell or activate an ability that has
  an unpayable cost is a legal action." An unaffordable action is still
  enumerated, and simply carries no plan.
- **CR 107.3a** - X is announced by the caster as part of casting, so before
  it is announced there is no cost to plan against and the verdict is
  `UNKNOWN` with no plan.
- **CR 601.2f** - the sentence that defines a total cost; an action with no
  total cost at all (a land drop, passing priority) has nothing to plan.
- **CR 702.51a** - convoke, one of the object-cost offers `_widen_for_object_
  costs` turns a mana-only `NO` into an honest `UNKNOWN` for.

**Target the mechanic, never the card.** Cavern of Souls is the printing the
protocol's own example names, so it cannot be the only restricted source
proven here. Tablet of Discovery carries the same mechanic on a different card
type (an artifact, not a land), with a different production (`{R}{R}`, not one
mana of any colour), a different clause shape ("instant and sorcery spells" -
a joined *type list*, not "a creature spell of the chosen type"), and its
restricted ability at a different position beside a *different* unrestricted
one. It is not in any decklist this suite plays.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.cost import (
    could_pay_mana_cost,
    mana_ability_index,
    mana_candidate_scan,
    plan_mana_payment,
)
from magic_cards_model.machines.legal_actions import legal_actions
from magic_cards_model.models import Color, Zone
from magic_cards_model.models.action import Action, ActionKind, Affordability
from magic_cards_model.models.mana import ManaCost, ManaSpend
from tests.scenarios.harness import Scenario

_CAVERN_RESTRICTION = (
    "Spend this mana only to cast a creature spell of the chosen type, "
    "and that spell can't be countered."
)
_TABLET_RESTRICTION = "Spend this mana only to cast instant and sorcery spells."


def _cast_action(scenario, name: str, username: str = "alice") -> Action:
    """The one `CAST` action for `name` in `username`'s legal actions."""
    card = scenario.find(name, Zone.HAND, username)
    (action,) = [
        action
        for action in legal_actions(scenario.game, username)
        if action.kind is ActionKind.CAST and action.card_id == card.id
    ]
    return action


def _plan_shape(action: Action) -> list[tuple[str, int | None, str, str | None]]:
    """`pays_with` as `(name, ability_index, adds, restriction)` tuples."""
    return [
        (entry.name, entry.ability_index, entry.adds, entry.restriction)
        for entry in action.pays_with
    ]


# --------------------------------------------------------------------------
# The plan is the taps the cast actually makes
# --------------------------------------------------------------------------


def test_the_reported_plan_is_the_taps_the_cast_actually_makes():
    """Lightning Helix (`{R}{W}`) with a Mountain, a Plains and a Sacred
    Foundry available.

    The plan names two sources and the cast taps exactly those two, in that
    order - and the Foundry the plan did not name is still untapped
    afterwards, which is CR 118.3c's "activating mana abilities is not
    mandatory" showing up as a fact a seat can read *before* committing.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Helix"],
            battlefield=["Mountain", "Plains", "Sacred Foundry"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain, plains, foundry) = scenario.untapped_sources("Mountain", "Plains", "Sacred Foundry")

    action = _cast_action(scenario, "Lightning Helix")
    assert action.affordable is Affordability.YES
    assert _plan_shape(action) == [
        ("Mountain", 0, "R", None),
        ("Plains", 0, "W", None),
    ]

    casting = scenario.cast("Lightning Helix", "alice", targets=["bob"])
    payment = casting.begin_paying()
    payment.auto_tap(scenario.game.permanents_controlled_by("alice"))
    payment.pay()
    scenario.put_on_stack(casting)

    # The same permanents, in the same order, and nothing else.
    assert payment.tapped_for_mana == [entry.card_id for entry in action.pays_with]
    assert mountain.tapped is True
    assert plains.tapped is True
    assert foundry.tapped is False
    assert scenario.player("alice").mana_pool.floating == {}


def test_the_plan_names_the_flexible_source_when_it_is_the_only_one_that_fits():
    """The plan is the solver's answer, not a guess at it: with only a
    Mountain and a Sacred Foundry for `{R}{W}`, the dual has to make the
    colour the Mountain cannot, and the plan says which colour that is."""
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Helix"], battlefield=["Mountain", "Sacred Foundry"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    action = _cast_action(scenario, "Lightning Helix")
    assert _plan_shape(action) == [
        ("Mountain", 0, "R", None),
        ("Sacred Foundry", 0, "W", None),
    ]

    casting = scenario.cast("Lightning Helix", "alice", targets=["bob"])
    payment = casting.begin_paying()
    payment.auto_tap(scenario.game.permanents_controlled_by("alice"))
    payment.pay()
    scenario.put_on_stack(casting)

    assert payment.tapped_for_mana == [entry.card_id for entry in action.pays_with]
    assert scenario.player("alice").mana_pool.floating == {}


def test_floating_mana_that_already_covers_the_cost_leaves_the_plan_empty():
    """CR 118.3c again, at the other end: a pool that already pays owes no
    taps at all, so the plan is empty rather than absent - and the cast that
    follows taps nothing."""
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain", "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (first, second) = scenario.untapped_sources("Mountain", "Mountain")
    scenario.game.activate_ability(first, 0, "alice")
    assert scenario.player("alice").mana_pool.floating == {Color.RED: 1}

    action = _cast_action(scenario, "Lightning Bolt")
    assert action.affordable is Affordability.YES
    assert action.pays_with == ()

    casting = scenario.cast("Lightning Bolt", "alice", targets=["bob"])
    payment = casting.begin_paying()
    payment.auto_tap(scenario.game.permanents_controlled_by("alice"))
    payment.pay()
    scenario.put_on_stack(casting)

    assert payment.tapped_for_mana == []
    assert second.tapped is False


# --------------------------------------------------------------------------
# CR 106.6: the plan reports the restriction the engine enforces
# --------------------------------------------------------------------------


def test_the_plan_quotes_the_restriction_on_a_cavern_of_souls_tap():
    """Cavern of Souls with Elf chosen, paying for Llanowar Elves.

    Two things are being asserted at once. The plan reaches for ability index
    1 - the restricted "one mana of any color" - and not index 0's free `{C}`,
    which cannot make green at all; and it quotes CR 106.6's printed sentence
    verbatim, so a seat reading the plan learns the mana it is about to spend
    is the mana that can do less.
    """
    scenario = (
        Scenario().player("alice", hand=["Cavern of Souls", "Llanowar Elves"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose("Elf", source="Cavern of Souls")
    cavern = scenario.play_land("Cavern of Souls")

    action = _cast_action(scenario, "Llanowar Elves")
    assert action.affordable is Affordability.YES
    assert _plan_shape(action) == [("Cavern of Souls", 1, "G", _CAVERN_RESTRICTION)]

    casting = scenario.cast("Llanowar Elves", "alice")
    payment = casting.begin_paying()
    payment.auto_tap(scenario.game.permanents_controlled_by("alice"))
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert payment.tapped_for_mana == [entry.card_id for entry in action.pays_with]
    assert cavern.tapped is True
    assert scenario.find("Llanowar Elves", Zone.BATTLEFIELD).zone is Zone.BATTLEFIELD


def test_the_plan_quotes_a_restriction_on_a_printing_that_is_not_cavern_of_souls():
    """The mechanic, proven on a card that shares no wording with the one the
    protocol's example names.

    Tablet of Discovery is an artifact, its restricted ability adds `{R}{R}`
    rather than one mana of any colour, and its sentence names a *type list*
    ("instant and sorcery spells") rather than a chosen creature type.
    Pyroclasm costs `{1}{R}`, which only the restricted ability can cover
    alone, so the plan has to reach past the unrestricted `{T}: Add {R}` at
    index 0 to index 1 - and report both mana it adds.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Pyroclasm"], battlefield=["Tablet of Discovery"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (tablet,) = scenario.untapped_sources("Tablet of Discovery")

    action = _cast_action(scenario, "Pyroclasm")
    assert action.affordable is Affordability.YES
    assert _plan_shape(action) == [("Tablet of Discovery", 1, "RR", _TABLET_RESTRICTION)]

    casting = scenario.cast("Pyroclasm", "alice")
    payment = casting.begin_paying()
    payment.auto_tap(scenario.game.permanents_controlled_by("alice"))
    payment.pay()
    scenario.put_on_stack(casting)

    assert payment.tapped_for_mana == [tablet.id]
    assert scenario.player("alice").mana_pool.floating == {}


def test_the_same_permanent_reports_a_different_ability_for_a_spell_the_restriction_refuses():
    """The plan is read against CR 106.6, not off the permanent's name.

    Goblin Guide is a creature spell costing exactly the `{R}` Tablet of
    Discovery's restricted ability would happily make - and cannot have it.
    The plan drops to index 0's unrestricted `{T}: Add {R}` and carries no
    restriction at all, on the same physical permanent that reported one for
    Pyroclasm above.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Goblin Guide", "Pyroclasm"], battlefield=["Tablet of Discovery"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (tablet,) = scenario.untapped_sources("Tablet of Discovery")

    guide = _cast_action(scenario, "Goblin Guide")
    assert _plan_shape(guide) == [("Tablet of Discovery", 0, "R", None)]

    pyroclasm = _cast_action(scenario, "Pyroclasm")
    assert _plan_shape(pyroclasm) == [("Tablet of Discovery", 1, "RR", _TABLET_RESTRICTION)]

    # Same permanent, two plans, two abilities - and the one the engine
    # actually executes for the creature spell is the unrestricted one.
    assert guide.pays_with[0].card_id == pyroclasm.pays_with[0].card_id == tablet.id

    casting = scenario.cast("Goblin Guide", "alice")
    payment = casting.begin_paying()
    payment.auto_tap(scenario.game.permanents_controlled_by("alice"))
    payment.pay()
    scenario.put_on_stack(casting)

    assert payment.tapped_for_mana == [tablet.id]
    assert scenario.player("alice").mana_pool.floating == {}
    assert scenario.player("alice").mana_pool.restricted == []


# --------------------------------------------------------------------------
# When there is no plan to report
# --------------------------------------------------------------------------


def test_an_unaffordable_cast_is_still_enumerated_and_carries_no_plan():
    """CR 118.6: the attempt stays legal, so the action is still listed - with
    `affordable=NO`, the engine's own reason, and no plan."""
    scenario = Scenario().player("alice", hand=["Lightning Bolt"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    action = _cast_action(scenario, "Lightning Bolt")
    assert action.affordable is Affordability.NO
    assert action.unaffordable_reason is not None
    assert action.pays_with == ()


def test_an_unannounced_x_carries_no_plan():
    """CR 107.3a: X is announced as part of casting, so there is no cost to
    plan against yet and the verdict is `UNKNOWN`."""
    scenario = (
        Scenario()
        .player("alice", hand=["Green Sun's Zenith"], battlefield=["Forest"] * 4)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    action = _cast_action(scenario, "Green Sun's Zenith")
    assert action.affordable is Affordability.UNKNOWN
    assert action.unaffordable_reason == "X has not been announced yet (CR 107.3a)"
    assert action.pays_with == ()


def test_an_unknown_widened_out_of_a_no_still_carries_no_plan():
    """CR 702.51a: convoke could pay part of `{3}{W}` by tapping creatures,
    which this affordability check does not evaluate, so a mana-only `NO`
    becomes an honest `UNKNOWN`. The plan was never built (the mana verdict
    was `NO`) and the widening must not conjure one."""
    scenario = (
        Scenario()
        .player("alice", hand=["Conclave Tribunal"], battlefield=["Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    action = _cast_action(scenario, "Conclave Tribunal")
    assert action.affordable is Affordability.UNKNOWN
    assert action.pays_with == ()


def test_actions_that_owe_no_mana_carry_no_plan():
    """A land drop, passing priority and conceding have no total cost at all
    (CR 601.2f) - there is nothing to tap and so nothing to report."""
    scenario = (
        Scenario()
        .player("alice", hand=["Mountain"], battlefield=["Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    free = [action for action in legal_actions(scenario.game, "alice") if action.mana_cost is None]
    assert free  # the land drop, priority, concede, and the Mountain's own tap
    assert all(action.pays_with == () for action in free)


def test_no_action_in_a_whole_enumeration_breaks_the_two_gates():
    """The invariant, asserted across every action a busy board produces
    rather than one at a time: a plan appears only where there is a mana cost
    to plan *and* the engine said the cost is payable."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt", "Green Sun's Zenith", "Cavern of Souls", "Pyroclasm"],
            battlefield=["Mountain", "Forest", "Tablet of Discovery"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    actions = legal_actions(scenario.game, "alice")
    assert actions
    for action in actions:
        if action.mana_cost is None or action.affordable is not Affordability.YES:
            assert action.pays_with == (), action
    assert any(action.pays_with for action in actions)


# --------------------------------------------------------------------------
# `could_pay_mana_cost` is `plan_mana_payment(...) is not None`
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("battlefield", "cost", "expected"),
    [
        (["Mountain"], "{R}", True),
        (["Mountain"], "{W}", False),
        (["Mountain"], "{R}{R}", False),
        (["Mountain", "Mountain"], "{R}{R}", True),
        (["Sacred Foundry"], "{W}", True),
        (["Sacred Foundry", "Mountain"], "{R}{W}", True),
        (["Sacred Foundry", "Mountain"], "{W}{W}", False),
        (["Mountain", "Mountain", "Mountain"], "{2}{R}", True),
        ([], "{R}", False),
        (["Mountain"], "", True),
    ],
)
def test_could_pay_mana_cost_still_answers_exactly_what_it_used_to(battlefield, cost, expected):
    """The predicate's verdict is unchanged by the refactor, and it is now
    *literally* the plan's own answer - the two cannot disagree because there
    is only one implementation left."""
    scenario = Scenario().player("alice", battlefield=list(battlefield)).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    parsed = ManaCost.parse(cost)

    verdict = could_pay_mana_cost(
        parsed, scenario.game.battlefield, game=scenario.game, payer="alice"
    )
    plan = plan_mana_payment(parsed, scenario.game.battlefield, game=scenario.game, payer="alice")

    assert verdict is expected
    assert verdict is (plan is not None)


def test_the_predicate_and_the_plan_agree_on_a_restricted_source():
    """CR 106.6's filter is part of the one implementation too: the same board
    and the same cost answer differently depending on what the mana is *for*,
    and the predicate and the plan move together."""
    scenario = (
        Scenario()
        .player("alice", hand=["Goblin Guide", "Pyroclasm"], battlefield=["Tablet of Discovery"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cost = ManaCost.parse("{1}{R}")
    sorcery = ManaSpend.casting(scenario.find("Pyroclasm", Zone.HAND).card, zone=Zone.HAND)
    creature = ManaSpend.casting(scenario.find("Goblin Guide", Zone.HAND).card, zone=Zone.HAND)

    for spend, expected in ((sorcery, True), (creature, False)):
        verdict = could_pay_mana_cost(
            cost, scenario.game.battlefield, game=scenario.game, payer="alice", spend=spend
        )
        plan = plan_mana_payment(
            cost, scenario.game.battlefield, game=scenario.game, payer="alice", spend=spend
        )
        assert verdict is expected
        assert verdict is (plan is not None)

    plan = plan_mana_payment(
        cost, scenario.game.battlefield, game=scenario.game, payer="alice", spend=sorcery
    )
    assert plan is not None
    ((source, colors, restriction),) = plan
    assert source.name == "Tablet of Discovery"
    assert colors == [Color.RED, Color.RED]
    assert restriction is not None
    assert restriction.text == _TABLET_RESTRICTION


def test_a_hoisted_candidate_scan_gives_the_plan_the_same_answer():
    """`legal_actions` hoists `mana_candidate_scan` out of its loop and hands
    it to every affordability question it asks. The plan has to be identical
    to the one a fresh scan produces, or the enumeration would report a plan
    the cast then contradicts."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Mountain", "Plains", "Sacred Foundry"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cost = ManaCost.parse("{R}{W}")
    scan = mana_candidate_scan(scenario.game.battlefield, game=scenario.game, payer="alice")

    fresh = plan_mana_payment(cost, scenario.game.battlefield, game=scenario.game, payer="alice")
    hoisted = plan_mana_payment(
        cost,
        scenario.game.battlefield,
        game=scenario.game,
        payer="alice",
        candidate_scan=scan,
    )

    assert fresh is not None and hoisted is not None
    assert [(source.id, colors, restriction) for source, colors, restriction in fresh] == [
        (source.id, colors, restriction) for source, colors, restriction in hoisted
    ]


def test_the_ability_index_is_the_same_with_and_without_a_hoisted_scan():
    """`mana_ability_index` has a fast path (read the ability back off the
    scan the plan was solved from) and a slow one (ask `_activated_mana_
    ability`, the function `tap_for_mana` itself uses). Both are real code
    paths and both have to give the number `Game.activate_ability` takes -
    index 1, Cavern of Souls's restricted mana of any colour, not index 0's
    free `{C}`."""
    scenario = (
        Scenario().player("alice", hand=["Cavern of Souls", "Llanowar Elves"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose("Elf", source="Cavern of Souls")
    cavern = scenario.play_land("Cavern of Souls")

    elves = scenario.find("Llanowar Elves", Zone.HAND)
    spend = ManaSpend.casting(elves.card, zone=Zone.HAND)
    plan = plan_mana_payment(
        ManaCost.parse("{G}"),
        scenario.game.battlefield,
        game=scenario.game,
        payer="alice",
        spend=spend,
    )
    assert plan is not None
    ((source, colors, restriction),) = plan
    scan = mana_candidate_scan(scenario.game.battlefield, game=scenario.game, payer="alice")

    slow = mana_ability_index(source, colors, restriction, game=scenario.game, payer="alice")
    fast = mana_ability_index(
        source, colors, restriction, game=scenario.game, payer="alice", candidate_scan=scan
    )

    assert slow == fast == 1
    # And it is the index the engine itself takes for that ability.
    scenario.game.activate_ability(cavern, fast, "alice", color=Color.GREEN)
    (restricted,) = scenario.player("alice").mana_pool.restricted
    assert restricted.restriction.text == _CAVERN_RESTRICTION


# --------------------------------------------------------------------------
# The wire shape the agent protocol reads
# --------------------------------------------------------------------------


def test_pays_with_serializes_as_the_protocol_says():
    """One entry per tap: the permanent's id and name, which of its abilities
    is activated, what that adds, and CR 106.6's sentence when there is one.

    The unrestricted entry carries no `restriction` key at all - the field is
    dropped rather than serialized as null, because this rides on every
    affordable action in an enumeration and the null would be pure weight.
    """
    scenario = (
        Scenario().player("alice", hand=["Cavern of Souls", "Llanowar Elves"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose("Elf", source="Cavern of Souls")
    cavern = scenario.play_land("Cavern of Souls")

    action = _cast_action(scenario, "Llanowar Elves")
    assert action.model_dump(mode="json")["pays_with"] == [
        {
            "card_id": str(cavern.id),
            "name": "Cavern of Souls",
            "ability_index": 1,
            "adds": "G",
            "restriction": _CAVERN_RESTRICTION,
        }
    ]


def test_an_unrestricted_entry_drops_the_restriction_key():
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain")

    action = _cast_action(scenario, "Lightning Bolt")
    assert action.model_dump(mode="json")["pays_with"] == [
        {
            "card_id": str(mountain.id),
            "name": "Mountain",
            "ability_index": 0,
            "adds": "R",
        }
    ]


def test_an_action_round_trips_through_json_with_its_plan():
    """`Action` is a log row before it is anything else - the plan has to
    survive a dump and a decode intact."""
    scenario = (
        Scenario()
        .player("alice", hand=["Pyroclasm"], battlefield=["Tablet of Discovery"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    action = _cast_action(scenario, "Pyroclasm")
    assert Action.model_validate_json(action.model_dump_json()) == action
