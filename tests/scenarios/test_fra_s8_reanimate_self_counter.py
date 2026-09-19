"""FRA stream S8: Liliana the Repentant's own Exhaust ability - "Return
target creature or planeswalker card from your graveyard to the
battlefield. Put a +1/+1 counter on Liliana." Two independent clauses, not
an anaphoric pair: the counter lands on the ability's own *source*
(Liliana herself), never on whatever was just returned.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file.

- **CR 201.5** - "Text that refers to the object it's on by name means just
  that particular object" - here spelled with just "Liliana", the card's own
  short form, rather than its full printed name "Liliana the Repentant".
- **CR 110.2a** - the returned card enters under its controller's control.
- **CR 122.1** - the counter, placed on the ability's source (CR 608.2c's
  own second instruction, run after the first).
- **CR 702.177** (Exhaust) is a different stream's own scope (S10) - this
  card's own activation-limit enforcement is not built here; the ability
  itself parses (`ability_word='Exhaust'`, cost `{5}{B}`, the effect text
  isolated correctly) and is activated directly below the way the pool's
  own pre-existing self-referential-cost tests already route around a
  narrower, separately-documented `why_cannot_activate` gap.

`machines.abilities.self_normalized_effect_text` already reads CR 201.5's
short form for a comma-separated name ("Jace, Reality Sculptor" -> "Jace"),
but had no reading at all for a legendary permanent's own multi-word name
with an epithet and *no* comma ("Liliana the Repentant") - the identical
short-form convention, spelled without one. Liliana the Repentant is the
reported card; the fix is proven general (not a name-keyed table) directly
against the function itself below, on a second, structurally identical name
this pool does not print.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import self_normalized_effect_text
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_self_normalized_effect_text_reads_a_no_comma_epithet_name():
    """The general fix, isolated from any one card: a "Name lowercase-word
    ..." shape reads "Name" as the short form, the structural rule Liliana
    the Repentant's own printing exercises - checked here against a second,
    differently-worded name to show it is the *shape* that is read, not the
    string "Liliana"."""
    assert (
        self_normalized_effect_text("Liliana the Repentant", "Put a +1/+1 counter on Liliana.")
        == "Put a +1/+1 counter on this permanent."
    )
    assert (
        self_normalized_effect_text(
            "Kediss the Emerald Warden", "Kediss deals 2 damage to any target."
        )
        == "this permanent deals 2 damage to any target."
    )


def test_liliana_the_repentants_exhaust_returns_a_target_and_counters_herself():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Liliana the Repentant",
                "Swamp",
                "Swamp",
                "Swamp",
                "Swamp",
                "Swamp",
                "Swamp",
            ],
            graveyard=["Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    liliana = scenario.creature("Liliana the Repentant", "alice")
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp", "Swamp", "Swamp")

    scenario.activate(liliana, *sources, targets=[bears])
    scenario.pass_until_resolved()

    assert bears.zone is Zone.BATTLEFIELD
    assert bears.controller == "alice"
    assert bears.counter_count("+1/+1") == 0, "the counter lands on Liliana, not the target"
    assert liliana.counter_count("+1/+1") == 1
