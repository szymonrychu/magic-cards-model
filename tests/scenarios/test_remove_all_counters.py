"""Scenario: "tap enchanted creature and remove all counters from it" - an
Aura's enters trigger acting on the permanent it enchants, and "remove all
counters from `<anaphor>`" as a rider on whatever its antecedent acted on.

Readers under test (`machines/effects.py`):

- `_parse_tap_attached_clause` - "tap enchanted creature" (also "equipped
  creature"), acting on the object the Aura is attached to (CR 303.4b), not
  a target of its own (CR 115.1b: an Aura permanent targets nothing).
- `_referent_reader`'s attached-object shape - "it" after "enchanted
  creature" is that same object (CR 400.7 anaphora), read only when no
  other referent shape applies.
- `_RIDER_REMOVE_ALL_COUNTERS_RE` - "remove all counters from it / that
  creature", every kind at once.

Cards: **Enchanted River's Grasp** (the listed card); **Honest Work**
(off-set, the same trigger on an Aura that can only enchant an opponent's
creature); **Charmed Sleep** (off-set, "tap enchanted creature." standing
alone); **Blitz Leech** (off-set, "Remove all counters from that creature."
after a targeted -2/-2 layer antecedent, a different referent shape). All
Modern-legal, none in a deck.

Rules, each read with `mise run rules:find` in the session that wrote this
file:

- **CR 303.4b** - "The object or player an Aura is attached to is called
  enchanted."
- **CR 701.26a** - only untapped permanents can be tapped; an already
  tapped creature is left alone and the rest of the sentence still applies.
- **CR 122.1** - counters of every kind are markers on the object; removing
  them all leaves none of any kind.
- **CR 608.2c** - the instructions happen in the order written: Blitz
  Leech's -2/-2 applies before the counters come off.
- **CR 608.2h** - the effect uses the enchanted object as it is now; one that
  has left the battlefield is not acted on.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _load_counters(scenario, creature, plus=2, stun=1, oil=3):
    game = scenario.game
    game.add_counters(creature, Counter.PLUS_ONE, plus)
    game.add_counters(creature, Counter.STUN, stun)
    game.add_counters(creature, "oil", oil)


def _total_counters(creature) -> int:
    return sum(creature.counter_count(kind) for kind in list(creature.counters))


def _grasp_board(aura="Enchanted River's Grasp", lands=("Island",) * 3):
    scenario = (
        Scenario()
        .player("alice", hand=[aura], battlefield=list(lands) + ["Memnite"])
        .player("bob", battlefield=["Grizzly Bears", "Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _enchant(scenario, aura, target, lands):
    scenario.cast_and_resolve(
        aura, *scenario.untapped_sources(*lands, username="alice"), targets=[target]
    )
    scenario.pass_until_resolved()  # the Aura's own "When this Aura enters" trigger


# --------------------------------------------------------------------------
# Enchanted River's Grasp
# --------------------------------------------------------------------------


def test_rivers_grasp_taps_and_strips_every_counter_kind():
    scenario = _grasp_board()
    bears = scenario.creature("Grizzly Bears", "bob")
    _load_counters(scenario, bears)
    assert _total_counters(bears) == 6

    _enchant(scenario, "Enchanted River's Grasp", bears, ["Island"] * 3)

    assert bears.tapped
    assert _total_counters(bears) == 0
    assert bears.counter_count(Counter.PLUS_ONE) == 0
    assert bears.counter_count(Counter.STUN) == 0
    assert bears.counter_count("oil") == 0
    assert scenario.game.characteristics_of(bears).power_toughness == (2, 2)


def test_rivers_grasp_leaves_other_creatures_alone():
    scenario = _grasp_board()
    bears = scenario.creature("Grizzly Bears", "bob")
    angel = scenario.creature("Serra Angel", "bob")
    _load_counters(scenario, angel)

    _enchant(scenario, "Enchanted River's Grasp", bears, ["Island"] * 3)

    assert not angel.tapped
    assert _total_counters(angel) == 6


def test_an_already_tapped_creature_still_loses_its_counters():
    """CR 701.26a: the tap does nothing to a tapped creature, and the rest of
    the sentence is not skipped for it."""
    scenario = _grasp_board()
    angel = scenario.creature("Serra Angel", "bob")
    angel.tapped = True
    _load_counters(scenario, angel)

    _enchant(scenario, "Enchanted River's Grasp", angel, ["Island"] * 3)

    assert angel.tapped
    assert _total_counters(angel) == 0


def test_a_creature_with_no_counters_is_just_tapped():
    scenario = _grasp_board()
    bears = scenario.creature("Grizzly Bears", "bob")

    _enchant(scenario, "Enchanted River's Grasp", bears, ["Island"] * 3)

    assert bears.tapped
    assert _total_counters(bears) == 0


def test_rivers_grasp_on_your_own_creature_works_the_same():
    """ "Enchant creature" - alice may enchant her own Memnite."""
    scenario = _grasp_board()
    memnite = scenario.creature("Memnite", "alice")
    _load_counters(scenario, memnite, plus=1, stun=0, oil=2)

    _enchant(scenario, "Enchanted River's Grasp", memnite, ["Island"] * 3)

    assert memnite.tapped
    assert _total_counters(memnite) == 0


def test_the_enchanted_creature_leaving_first_means_nothing_happens():
    """The creature is gone before the trigger resolves: there is no enchanted
    creature to tap or strip (CR 608.2h), and nothing else is touched."""
    scenario = _grasp_board()
    bears = scenario.creature("Grizzly Bears", "bob")
    angel = scenario.creature("Serra Angel", "bob")
    _load_counters(scenario, angel)
    scenario.cast_and_resolve(
        "Enchanted River's Grasp",
        *scenario.untapped_sources("Island", "Island", "Island", username="alice"),
        targets=[bears],
    )
    scenario.game.return_to_hand(bears)

    scenario.pass_until_resolved()

    assert bears.zone is Zone.HAND
    assert not angel.tapped
    assert _total_counters(angel) == 6


def test_the_aura_leaving_first_still_taps_and_strips_what_it_enchanted():
    """Answering the trigger by bouncing the Grasp itself does not save the
    creature: the ability exists independently of its source (CR 113.7a), and
    "enchanted creature" is read off the Aura's last known information (CR
    608.2h) - the creature it was attached to as it left."""
    scenario = _grasp_board()
    angel = scenario.creature("Serra Angel", "bob")
    _load_counters(scenario, angel)
    scenario.cast_and_resolve(
        "Enchanted River's Grasp",
        *scenario.untapped_sources("Island", "Island", "Island", username="alice"),
        targets=[angel],
    )
    grasp = scenario.find("Enchanted River's Grasp", Zone.BATTLEFIELD, "alice")
    scenario.game.return_to_hand(grasp)

    scenario.pass_until_resolved()

    assert grasp.zone is Zone.HAND
    assert angel.tapped
    assert _total_counters(angel) == 0


def test_the_stripped_creature_stays_tapped_through_its_untap_step():
    """The Grasp's own static - "doesn't untap during its controller's untap
    step" - on top of the trigger: alice enchants her own Memnite, then her
    own untap step leaves it tapped."""
    scenario = _grasp_board()
    memnite = scenario.creature("Memnite", "alice")

    _enchant(scenario, "Enchanted River's Grasp", memnite, ["Island"] * 3)
    scenario.game.untap_step()

    assert memnite.tapped


# --------------------------------------------------------------------------
# Honest Work (off-set: same trigger, "Enchant creature an opponent controls")
# --------------------------------------------------------------------------


def test_honest_work_taps_and_strips_the_opponents_creature():
    scenario = _grasp_board(aura="Honest Work", lands=("Island",))
    angel = scenario.creature("Serra Angel", "bob")
    _load_counters(scenario, angel)

    _enchant(scenario, "Honest Work", angel, ["Island"])

    assert angel.tapped
    assert _total_counters(angel) == 0


# --------------------------------------------------------------------------
# Charmed Sleep (off-set: "tap enchanted creature." alone)
# --------------------------------------------------------------------------


def test_charmed_sleep_taps_the_enchanted_creature_and_keeps_its_counters():
    scenario = _grasp_board(aura="Charmed Sleep", lands=("Island",) * 3)
    angel = scenario.creature("Serra Angel", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    _load_counters(scenario, angel)

    _enchant(scenario, "Charmed Sleep", angel, ["Island"] * 3)

    assert angel.tapped
    assert not bears.tapped
    assert _total_counters(angel) == 6, "no counter clause on Charmed Sleep"


# --------------------------------------------------------------------------
# Blitz Leech (off-set: "Remove all counters from that creature." after a
# targeted -2/-2)
# --------------------------------------------------------------------------


def _leech(scenario, target):
    scenario.will_choose_targets(target, username="alice")
    scenario.put_onto_battlefield("Blitz Leech", "alice")
    scenario.pass_until_resolved()


def test_blitz_leech_shrinks_then_strips_the_target():
    """Serra Angel with one +1/+1 counter is 5/5; -2/-2 then no counters
    leaves a 2/2 that survives."""
    scenario = (
        Scenario()
        .player("alice", hand=["Blitz Leech"])
        .player("bob", battlefield=["Serra Angel", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    _load_counters(scenario, angel, plus=1, stun=1, oil=1)
    _load_counters(scenario, bears)

    _leech(scenario, angel)

    assert _total_counters(angel) == 0
    assert scenario.game.characteristics_of(angel).power_toughness == (2, 2)
    assert angel.zone is Zone.BATTLEFIELD
    assert _total_counters(bears) == 6, "only the target"


def test_blitz_leech_can_kill_a_creature_the_counters_were_keeping_alive():
    """Grizzly Bears with two +1/+1 counters is 4/4: -2/-2 leaves 2/2, and
    stripping the counters leaves a 0/0 that dies to CR 704.5f."""
    scenario = (
        Scenario()
        .player("alice", hand=["Blitz Leech"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    _load_counters(scenario, bears, plus=2, stun=0, oil=0)

    _leech(scenario, bears)
    scenario.state_based_actions()

    assert bears.zone is Zone.GRAVEYARD
