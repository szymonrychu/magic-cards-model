"""Scenario: flanking (CR 702.25), a declare-blockers trigger that shrinks an
unqualified blocker.

Every CR number below was read with `mise run rules:find` in the session that
wrote this file:

- **CR 702.25a** - "Flanking is a triggered ability that triggers during the
  declare blockers step. (See rule 509, "Declare Blockers Step.") 'Flanking'
  means 'Whenever this creature becomes blocked by a creature without
  flanking, the blocking creature gets -1/-1 until end of turn.'"
- **CR 702.25b** - "If a creature has multiple instances of flanking, each
  triggers separately."
- **CR 509.3d** - "An ability that reads 'Whenever [a creature] becomes
  blocked by a creature, . . .' triggers once for each creature that blocks
  the specified creature." `Game.declare_blockers` already emits one
  `TriggerEvent.BLOCKS` event per blocking pair (`subject_id` the blocker),
  which is what gives CR 702.25b's "each triggers separately" and this rule's
  "once for each blocker" the same one mechanism, with no flanking-specific
  code needed for either.
- **CR 509.3f** - the "without flanking" qualifier is read off the blocker "at
  the point it becomes a blocking creature" - i.e. off the block-declaration
  event itself, never re-evaluated afterward.
- **CR 704.5f** - "If a creature has toughness 0 or less, it's put into its
  owner's graveyard." - the 1-toughness blocker below dies to this well
  before combat damage is ever dealt.
- **CR 611.2c** - the object a resolving ability's continuous effect modifies
  is fixed when that effect begins, never recomputed - the same reasoning
  `test_battle_cry.py` already exercises for battle cry's own pumped set,
  here fixing the reduction onto the one blocker that triggered it.

Knight of the Holy Nimbus is the listed card; Suq'Ata Lancer (Haste, Flanking)
is the proof-of-generality printing added with `scripts/add_card.py` this
session - a different mana cost, color and a second keyword riding beside
flanking, so the shape below is read off the rule text
(`_TRIGGER_EXPANSIONS['flanking']`), never off either card's own reminder
text.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import TriggerEvent
from magic_cards_model.machines.keywords import keyword_triggered_abilities
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support, ignored_keywords
from tests.cards import card

from .harness import PlayedScenario, Scenario

KNIGHT = "Knight of the Holy Nimbus"
LANCER = "Suq'Ata Lancer"


def _board(alice_battlefield: list[str], bob_battlefield: list[str]) -> PlayedScenario:
    scenario = (
        Scenario()
        .player("alice", battlefield=list(alice_battlefield))
        .player("bob", battlefield=list(bob_battlefield))
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario


def _resolve_everything(scenario: PlayedScenario) -> None:
    scenario.game.put_triggers_on_stack()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


# -- the ability expansion itself (CR 702.25a/b) -----------------------------


def test_knight_of_the_holy_nimbus_flanking_expands_to_the_cr_702_25a_trigger():
    (ability,) = [a for a in keyword_triggered_abilities(card(KNIGHT)) if a.keyword == "flanking"]
    assert ability.event is TriggerEvent.BLOCKS
    assert ability.condition == "this creature becomes blocked by a creature without flanking"
    assert ability.effect == "the blocking creature gets -1/-1 until end of turn"


def test_suq_ata_lancer_flanking_expands_to_the_same_trigger():
    """A second, differently-costed, differently-colored printing with a
    second keyword (Haste) riding beside flanking - the same rule text, not
    read off either card."""
    (ability,) = [a for a in keyword_triggered_abilities(card(LANCER)) if a.keyword == "flanking"]
    assert ability.event is TriggerEvent.BLOCKS
    assert ability.condition == "this creature becomes blocked by a creature without flanking"
    assert ability.effect == "the blocking creature gets -1/-1 until end of turn"


# -- the trigger fires in the declare blockers step (CR 702.25a) ------------


def test_the_trigger_goes_on_the_stack_in_the_declare_blockers_step():
    scenario = _board([KNIGHT], ["Grizzly Bears"])
    knight = scenario.creature(KNIGHT, "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(knight, defending="bob")
    scenario.advance()  # declare blockers

    scenario.block(knight, bears)

    assert scenario.step is Step.DECLARE_BLOCKERS
    assert scenario.stack_names() == [f"{KNIGHT}'s triggered ability"]


# -- a blocker without flanking is shrunk (CR 702.25a) -----------------------


def test_a_blocker_without_flanking_gets_minus_one_minus_one_until_end_of_turn():
    scenario = _board([KNIGHT], ["Craw Wurm"])
    knight = scenario.creature(KNIGHT, "alice")
    wurm = scenario.creature("Craw Wurm", "bob")
    assert scenario.game.characteristics_of(wurm).power_toughness == (6, 4)

    scenario.attack_with(knight, defending="bob")
    scenario.advance()
    scenario.block(knight, wurm)
    _resolve_everything(scenario)

    assert scenario.game.characteristics_of(wurm).power_toughness == (5, 3)


def test_a_one_toughness_blocker_dies_to_state_based_actions_before_damage():
    """CR 704.5f: nothing waits for the combat damage step to check a
    0-toughness creature - it dies as soon as the flanking trigger resolves
    and a player would next receive priority, during declare blockers."""
    scenario = _board([KNIGHT], ["Llanowar Elves"])
    knight = scenario.creature(KNIGHT, "alice")
    elves = scenario.creature("Llanowar Elves", "bob")

    scenario.attack_with(knight, defending="bob")
    scenario.advance()
    scenario.block(knight, elves)
    _resolve_everything(scenario)
    scenario.state_based_actions()

    assert elves.zone is Zone.GRAVEYARD
    assert scenario.step is Step.DECLARE_BLOCKERS, "died well before combat damage"


def test_the_reduction_wears_off_at_cleanup():
    """The listed printing proves this half - the reduction is real and
    temporary, not a permanent characteristic change."""
    scenario = _board([KNIGHT], ["Craw Wurm"])
    knight = scenario.creature(KNIGHT, "alice")
    wurm = scenario.creature("Craw Wurm", "bob")

    scenario.attack_with(knight, defending="bob")
    scenario.advance()
    scenario.block(knight, wurm)
    _resolve_everything(scenario)
    assert scenario.game.characteristics_of(wurm).power_toughness == (5, 3)

    while scenario.step is not Step.CLEANUP:
        scenario.advance()
        _resolve_everything(scenario)

    assert scenario.game.characteristics_of(wurm).power_toughness == (6, 4)


# -- a blocker with flanking of its own does not trigger it (CR 702.25a) ----


def test_a_blocker_with_flanking_is_not_shrunk_and_triggers_nothing():
    scenario = _board([KNIGHT], [LANCER])
    knight = scenario.creature(KNIGHT, "alice")
    lancer = scenario.creature(LANCER, "bob")

    scenario.attack_with(knight, defending="bob")
    scenario.advance()
    scenario.block(knight, lancer)

    assert scenario.stack_names() == []
    assert scenario.game.characteristics_of(lancer).power_toughness == (2, 2)


# -- two blockers without flanking each trigger separately (CR 702.25b/509.3d)


def test_two_blockers_without_flanking_each_trigger_separately():
    scenario = _board([KNIGHT], ["Craw Wurm", "Craw Wurm"])
    knight = scenario.creature(KNIGHT, "alice")
    first, second = scenario.creatures("Craw Wurm", "Craw Wurm", username="bob")

    scenario.attack_with(knight, defending="bob")
    scenario.advance()
    scenario.block(knight, first, second)

    assert scenario.stack_names() == [f"{KNIGHT}'s triggered ability"] * 2
    _resolve_everything(scenario)

    assert scenario.game.characteristics_of(first).power_toughness == (5, 3)
    assert scenario.game.characteristics_of(second).power_toughness == (5, 3)


# -- a flanking creature that blocks does not trigger its own flanking ------


def test_a_flanking_creature_that_blocks_does_not_trigger_its_own_flanking():
    scenario = _board(["Grizzly Bears"], [KNIGHT])
    bears = scenario.creature("Grizzly Bears", "alice")
    knight = scenario.creature(KNIGHT, "bob")

    scenario.attack_with(bears, defending="bob")
    scenario.advance()
    scenario.block(bears, knight)

    assert scenario.stack_names() == []
    assert scenario.game.characteristics_of(bears).power_toughness == (2, 2)


# -- the second printing behaves the same -------------------------------


def test_suq_ata_lancer_shrinks_its_own_blocker_the_same_way():
    scenario = _board([LANCER], ["Craw Wurm"])
    lancer = scenario.creature(LANCER, "alice")
    wurm = scenario.creature("Craw Wurm", "bob")

    scenario.attack_with(lancer, defending="bob")
    scenario.advance()
    scenario.block(lancer, wurm)
    _resolve_everything(scenario)

    assert scenario.game.characteristics_of(wurm).power_toughness == (5, 3)


# -- coverage: both printings' flanking is fully handled ---------------------


def test_both_printings_flanking_is_reported_as_handled():
    """`ignored_keywords` no longer lists Flanking for either printing, and
    `card_support`'s own keyword clause for it reads "handled" - Knight of the
    Holy Nimbus's card-level status stays `silent` regardless, over its own
    unrelated, pre-existing gap ("{2}: This creature can't be regenerated this
    turn. Only your opponents may activate this ability." - nothing in
    `machines/effects.py` reads that sentence), which this keyword's own work
    neither caused nor is asked to close."""
    for name in (KNIGHT, LANCER):
        printing = card(name)
        assert ignored_keywords(printing) == [], name
        (flanking_clause,) = [c for c in card_support(printing).clauses if c.text == "Flanking"]
        assert flanking_clause.status == "handled", name
