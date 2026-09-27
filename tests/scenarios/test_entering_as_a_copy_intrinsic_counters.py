"""A permanent entering as a copy enters with the copied object's intrinsic
counters: a planeswalker's loyalty, a Saga's lore counter, a battle's defense.

Verified this session with `mise run rules:find` against the current CR:

- **CR 707.2** - the copiable values are the values derived from the printed
  text, "name, mana cost, color indicator, card type, subtype, supertype,
  rules text, power, toughness, and/or loyalty", as modified by other copy
  effects.
- **CR 614.1c** - "[This permanent] enters as ..." is a replacement effect,
  so the copy's characteristics are fixed before it enters.
- **CR 306.5b** - a planeswalker has the intrinsic ability "This permanent
  enters with a number of loyalty counters on it equal to its printed
  loyalty number."
- **CR 714.3a** - each Saga without read ahead has the intrinsic ability
  "This Saga enters with a lore counter on it."
- **CR 310.4b** - a battle enters with defense counters equal to its printed
  defense number.
- **CR 707.9e** - a copy effect's "enters with additional counters" exception
  is an additional effect, not a copiable value.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

IMPERSONATOR = "Clever Impersonator"
MORITTE = "Moritte of the Frost"
LILIANA = "Liliana of the Veil"  # loyalty 3
BENALIA = "History of Benalia"
ERGAMON = "Invasion of Ergamon"  # Siege, defense 5


def _copy(copier: str, original: str, *, alice: tuple[str, ...] = (), bob: tuple[str, ...] = ()):
    scenario = (
        Scenario()
        .player("alice", hand=[copier], battlefield=list(alice))
        .player("bob", battlefield=list(bob))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    owner = "alice" if original in alice else "bob"
    target = scenario.find(original, Zone.BATTLEFIELD, owner)
    scenario.will_choose_cards(target, username="alice", source=copier)
    copy = scenario.put_onto_battlefield(copier, "alice")
    return scenario, copy


def test_a_copy_of_a_planeswalker_enters_with_its_printed_loyalty():
    _, copy = _copy(IMPERSONATOR, LILIANA, bob=(LILIANA,))

    assert copy.zone is Zone.BATTLEFIELD
    assert copy.counter_count("loyalty") == 3


def test_moritte_copying_a_planeswalker_enters_with_its_loyalty():
    """Moritte's "if it's a creature" exception does not apply to Liliana, and
    the copy still has CR 306.5b's intrinsic loyalty. (Before state-based
    actions: the two same-named legendaries then meet the legend rule.)"""
    _, copy = _copy(MORITTE, LILIANA, alice=(LILIANA,))

    assert copy.counter_count("loyalty") == 3
    assert copy.counter_count("+1/+1") == 0


def test_doubling_season_doubles_a_copied_planeswalkers_loyalty():
    _, copy = _copy(IMPERSONATOR, LILIANA, alice=("Doubling Season",), bob=(LILIANA,))

    assert copy.counter_count("loyalty") == 6


def test_a_copy_of_a_saga_enters_with_one_lore_counter():
    _, copy = _copy(IMPERSONATOR, BENALIA, bob=(BENALIA,))

    assert copy.counter_count("lore") == 1


def test_a_copy_of_a_siege_gets_its_defense_once_under_doubling_season():
    """The copied defense is put on once, as one event Doubling Season
    doubles - never the copy's own printed value plus the copied one."""
    _, copy = _copy(IMPERSONATOR, ERGAMON, alice=("Doubling Season",), bob=(ERGAMON,))

    assert copy.counter_count("defense") == 10


def test_a_copy_of_a_copy_of_a_planeswalker_has_the_copied_loyalty():
    """CR 707.2: copiable values "as modified by other copy effects" - a copy
    of an Impersonator that entered as Liliana is a Liliana with loyalty 3."""
    scenario = (
        Scenario()
        .player("alice", hand=[IMPERSONATOR, IMPERSONATOR])
        .player("bob", battlefield=[LILIANA])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    liliana = scenario.find(LILIANA, Zone.BATTLEFIELD, "bob")
    scenario.will_choose_cards(liliana, username="alice", source=IMPERSONATOR)
    first = scenario.put_onto_battlefield(IMPERSONATOR, "alice")
    scenario.will_choose_cards(first, username="alice", source=IMPERSONATOR)

    second = scenario.put_onto_battlefield(IMPERSONATOR, "alice")

    assert second is not first
    assert second.counter_count("loyalty") == 3
