"""Scenario: Ingris Stingerquill's own "{4}: Create a 2/2 colorless Wizard
Soldier creature token named Cadet. Then creatures you control gain haste
until end of turn." - the fra-survey misread ("token clause wins, trailing
group grant dropped") this file fixes, plus the three distinct gaps that
turned out to cause it.

Three separate bugs stacked to drop the haste grant, none of them specific
to this card:

1. `_parse_whole_text_token_clause` tries `_TOKEN_CLAUSE_RE` against the
   *whole* unsplit ability text before `split_effect_clauses` ever runs, on
   the documented assumption that "a card whose token clause is one
   instruction among several still falls through ... unaffected." That was
   never actually guaranteed: `_TOKEN_CLAUSE_RE`'s "named <name>" and "with
   <tail>" groups are both a bare, greedy `.+?` anchored only at the very
   end of the string, so against a genuinely multi-sentence text the "name"
   backtracks straight through the interior period and swallows the second
   sentence whole - which is why the token that got created was named
   "Cadet. Then creatures you control gain haste until end of turn" instead
   of "Cadet". Fixed with an explicit guard: a period anywhere in the
   stripped text refuses the whole-text attempt outright, leaving it to the
   ordinary per-clause path.
2. Once the token clause was read correctly and `split_effect_clauses` cut
   the text into two clauses, nothing in `_parse_mixed_clause`'s per-clause
   dispatch tried the CR 611.2 mass-pump/keyword-grant shape at all - only
   the whole-text special case did (`_mass_pump_ability_effect`/`_mass_pump_
   spell_effect`, tried in `_ability_effect_or_notice` before any splitting).
   `_parse_mass_pump_group_clause` reuses those exact readers one clause at a
   time, so a mass grant can now be one instruction among several rather than
   requiring the whole effect to be nothing else.
3. `machines/layers.py`'s `_MASS_PUMP_UNTIL_EOT_RE` required a "get +N/+N"
   pump on every mass CR 611.2 grant, even a pure keyword grant with no pump
   at all - "creatures you control gain haste until end of turn" has no
   "get" clause and matched nothing. **Bitter Reunion** (off-set, a real and
   unrelated card) is the proof: "{1}, Sacrifice this enchantment: Creatures
   you control gain haste until end of turn." is the identical keyword-only
   shape, with no token clause riding along at all.
4. `machines/effects.py`'s `_run_mass_pump` hands its literal sentence to
   `parsed_layer_effects`, which reads `_effect_sentences` - and that
   splitter needs a real sentence-terminating period to recognise anything
   at all. Fine for the whole-text callers, which still carry their own
   printed period; broken for a clause `split_effect_clauses` has already
   trimmed one from (CR 608.2c's own instruction-order splitter always
   strips a trailing "."). Fixed by restoring one before the text reaches
   `parsed_layer_effects`.

The rules these rest on:

- **CR 608.2c** - "The controller of the spell or ability follows its
  instructions in the order written" - the token and the haste grant are two
  instructions, not one opaque blob, and both must run.
- **CR 611.2** / **CR 611.2c** - a one-shot mass grant "until end of turn",
  whose affected group is fixed the moment the effect begins: the Cadet
  token exists by the time the *second* instruction runs (CR 608.2c's order
  again), so it is swept into "creatures you control" along with everything
  already on the battlefield.

Every CR number here was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote it, and every card's text with
`resolve_cards` or straight off its fixture.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.effects import activated_effect_for
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _activate_ingris(scenario: Scenario, ingris):
    sources = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest", username="alice")
    scenario.activate(ingris, *sources, index=0, username="alice")
    scenario.resolve_top()


def test_ingris_stingerquill_creates_the_token_correctly_named():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice", battlefield=["Ingris Stingerquill", "Forest", "Forest", "Forest", "Forest"]
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ingris = scenario.creature("Ingris Stingerquill", "alice")
    _activate_ingris(scenario, ingris)

    cadet = scenario.find("Cadet", Zone.BATTLEFIELD, "alice")
    assert cadet.name == "Cadet"
    assert scenario.game.characteristics_of(cadet).power_toughness == (2, 2)


def test_ingris_stingerquill_grants_haste_to_a_creature_already_on_the_battlefield():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=[
                "Ingris Stingerquill",
                "Grizzly Bears",
                "Forest",
                "Forest",
                "Forest",
                "Forest",
            ],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ingris = scenario.creature("Ingris Stingerquill", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    assert not scenario.game.characteristics_of(bears).has_ability("Haste")

    _activate_ingris(scenario, ingris)

    assert scenario.game.characteristics_of(bears).has_ability("Haste")


def test_ingris_stingerquill_also_grants_haste_to_the_token_it_just_made():
    """CR 608.2c's instruction order: the Cadet exists by the time the
    second instruction runs, so it is part of "creatures you control" too."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice", battlefield=["Ingris Stingerquill", "Forest", "Forest", "Forest", "Forest"]
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ingris = scenario.creature("Ingris Stingerquill", "alice")
    _activate_ingris(scenario, ingris)

    cadet = scenario.find("Cadet", Zone.BATTLEFIELD, "alice")
    assert scenario.game.characteristics_of(cadet).has_ability("Haste")


def test_ingris_stingerquill_does_not_grant_haste_to_an_opponents_creature():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice", battlefield=["Ingris Stingerquill", "Forest", "Forest", "Forest", "Forest"]
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ingris = scenario.creature("Ingris Stingerquill", "alice")
    theirs = scenario.creature("Grizzly Bears", "bob")

    _activate_ingris(scenario, ingris)

    assert not scenario.game.characteristics_of(theirs).has_ability("Haste")


def test_bitter_reunion_grants_haste_with_no_token_clause_at_all_off_set():
    """Off-set proof: the keyword-only mass grant shape read on its own, with
    no token clause riding along and a different card's own text driving it -
    a real, unrelated enchantment's sacrifice ability."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Bitter Reunion", "Grizzly Bears", "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    reunion = scenario.find("Bitter Reunion", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    assert not scenario.game.characteristics_of(bears).has_ability("Haste")

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.activate(reunion, mountain, index=0, username="alice")
    scenario.resolve_top()

    assert scenario.game.characteristics_of(bears).has_ability("Haste")


def test_the_legend_of_roku_token_clause_still_reads_whole_no_regression():
    """The exact shape `_parse_whole_text_token_clause` exists for -
    `_TOKEN_CLAUSE_RE`'s own "with <tail>" spanning a bare "and" that
    `split_effect_clauses` would otherwise cut apart - must still work: it
    has no internal period at all, so the new guard never refuses it."""
    effect = activated_effect_for(
        "The Legend of Roku",
        0,
        "Create a 4/4 red Dragon creature token with flying and firebending 4.",
    )
    assert effect is not None
