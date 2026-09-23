"""CR 603.12's reflexive trigger conditioned on *what kind of card* a
discard moved: "`<antecedent, ending in a discard>`. When you discard a
`<quality>` card this way, `<consequence>`."

The singular sibling of `test_fra_s8_reflexive_discard_count.py`'s "one or
more `<quality>` cards" shape. Every CR number below was looked up with
`mise run rules:find` in the session that wrote this file.

- **CR 603.12** - "a triggered ability that triggers ... 'when [something
  happens] this way.' These reflexive triggered abilities ... are checked
  immediately after being created and trigger based on whether the trigger
  event or events occurred earlier during the resolution of the spell or
  ability that created them." A discard of the wrong kind of card means the
  event never occurred, so no reflexive ability exists at all.
- **CR 603.12a** - "if the trigger event or events occur multiple times
  during the resolution ..., the reflexive triggered ability will trigger once
  for each of those times" - the singular "a `<quality>` card" is one event
  per qualifying card, unlike "one or more".
- **CR 603.3d** - the reflexive ability's own target ("target creature you
  control") is chosen as it is put on the stack, not when the parent ability
  was activated.
- **CR 509.1b** - "can't be blocked" is a restriction the blocking
  declaration has to obey.

Evie Frye is the reported card: "{1}, {T}: Draw a card, then discard a card.
When you discard a creature card this way, target creature you control can't
be blocked this turn." Teo, Spirited Glider (Standard/Pioneer/Modern legal,
not in the api deck pool) is the off-pool proof: a triggered ability rather
than an activated one, a different quality word ("nonland") and a different
consequence ("put a +1/+1 counter on target creature you control").
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _evie_board(library: list[str]):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Evie Frye", "Grizzly Bears", "Mountain"],
            library=library,
        )
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_evie_frye_discarding_a_creature_card_makes_target_creature_unblockable():
    scenario = _evie_board(["Craw Wurm", "Forest", "Forest"])
    alice = scenario.player("alice")
    evie = scenario.creature("Evie Frye", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    (mountain,) = scenario.untapped_sources("Mountain")
    wurm = alice.library[0]
    assert wurm.name == "Craw Wurm"

    scenario.will_discard(wurm, username="alice")
    scenario.will_choose_targets(bears, username="alice")
    scenario.activate(evie, mountain)
    scenario.pass_until_resolved()
    assert wurm.zone is Zone.GRAVEYARD, "the drawn creature card was discarded (CR 701.9a)"

    # CR 603.12: the reflexive ability exists only now, and CR 603.3d asks its
    # target as it goes on the stack.
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names(), "a creature card was discarded this way: it triggered"
    scenario.pass_until_resolved()

    scenario.advance()  # beginning of combat
    scenario.advance()  # declare attackers
    scenario.attack_with(bears)
    scenario.advance()  # declare blockers
    with pytest.raises(ValueError, match="blocked"):
        scenario.block(bears, giant)


def test_evie_frye_discarding_a_noncreature_card_creates_no_reflexive_ability():
    """CR 603.12: a land discarded is not "a creature card this way" - the
    event never occurred, so nothing triggers and the bears stay blockable."""
    scenario = _evie_board(["Forest", "Forest", "Forest"])
    alice = scenario.player("alice")
    evie = scenario.creature("Evie Frye", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    (mountain,) = scenario.untapped_sources("Mountain")
    forest = alice.library[0]

    scenario.will_discard(forest, username="alice")
    scenario.activate(evie, mountain)
    scenario.pass_until_resolved()
    assert forest.zone is Zone.GRAVEYARD
    scenario.game.put_triggers_on_stack()
    assert not scenario.stack_names(), "no creature card discarded: no reflexive ability"

    scenario.advance()
    scenario.advance()
    scenario.attack_with(bears)
    scenario.advance()
    scenario.block(bears, giant)
    assert giant in scenario.blockers()


def test_evie_frye_discarding_a_creature_already_in_hand_still_counts():
    """ "This way" is the discard, not the draw: the creature card discarded
    need not be the card just drawn (CR 608.2c reads the whole instruction)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Craw Wurm"],
            battlefield=["Evie Frye", "Grizzly Bears", "Mountain"],
            library=["Forest", "Forest", "Forest"],
        )
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    evie = scenario.creature("Evie Frye", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    (mountain,) = scenario.untapped_sources("Mountain")
    wurm = scenario.find("Craw Wurm", Zone.HAND, "alice")

    scenario.will_discard(wurm, username="alice")
    scenario.will_choose_targets(bears, username="alice")
    scenario.activate(evie, mountain)
    scenario.pass_until_resolved()
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    scenario.advance()
    scenario.advance()
    scenario.attack_with(bears)
    scenario.advance()
    with pytest.raises(ValueError, match="blocked"):
        scenario.block(bears, giant)


def test_evie_frye_reflexive_target_must_be_a_creature_you_control():
    """CR 603.3d / CR 601.2c: the reflexive ability's "target creature you
    control" refuses an opponent's creature."""
    scenario = _evie_board(["Craw Wurm", "Forest", "Forest"])
    alice = scenario.player("alice")
    evie = scenario.creature("Evie Frye", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    (mountain,) = scenario.untapped_sources("Mountain")
    wurm = alice.library[0]

    scenario.will_discard(wurm, username="alice")
    scenario.will_choose_targets(giant, username="alice")
    scenario.activate(evie, mountain)
    with pytest.raises(ValueError, match="not a legal target"):
        scenario.pass_until_resolved()
        scenario.game.put_triggers_on_stack()


def _teo_board(library: list[str]):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Teo, Spirited Glider", "Grizzly Bears"],
            library=library,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario


def test_teo_discarding_a_nonland_card_puts_a_counter_on_target_creature():
    scenario = _teo_board(["Lightning Bolt", "Forest", "Forest"])
    alice = scenario.player("alice")
    teo = scenario.creature("Teo, Spirited Glider", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    bolt = alice.library[0]

    scenario.will_discard(bolt, username="alice")
    scenario.will_choose_targets(bears, username="alice")
    scenario.attack_with(teo)
    scenario.pass_until_resolved()
    assert bolt.zone is Zone.GRAVEYARD
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert bears.counters[Counter.PLUS_ONE] == 1


def test_teo_discarding_a_land_creates_no_reflexive_ability():
    scenario = _teo_board(["Forest", "Forest", "Forest"])
    alice = scenario.player("alice")
    teo = scenario.creature("Teo, Spirited Glider", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    forest = alice.library[0]

    scenario.will_discard(forest, username="alice")
    scenario.attack_with(teo)
    scenario.pass_until_resolved()
    assert forest.zone is Zone.GRAVEYARD
    scenario.game.put_triggers_on_stack()
    assert not scenario.stack_names()
    assert bears.counters[Counter.PLUS_ONE] == 0
