"""The "nontoken" substring collision in `machines/triggers.condition_matches`,
and the effect misparse it exposed (CR 603.2's condition matching, CR 111.1's
token).

Adjudicated in `docs/2026-09-08-trigger-findings.md`. `"nontoken"` contains
`"token"` as a substring, so the ENTERS_THE_BATTLEFIELD guard - written for
Caretaker's Talent's "one or more tokens you control enter" - matched
"nontoken" too, and since the guard demands the entering permanent *be* a
token, it inverted every "nontoken X enters" condition in the pool: Weapons
Manufacturing and Miirym, Sentinel Wyrm fired only on the exact class of
permanent their own text excludes. Ashling, the Limitless's "you sacrifice a
nontoken Elemental" (IS_SACRIFICED, a different event) carried the identical
unmodelled restriction without the substring collision - nothing anywhere
read "nontoken" at all.

Weapons Manufacturing's own effect was doubly broken. With no `Munitions`
token definition and no parser for "create a ... token named X with '<quoted
ability>'" off oracle text, `trigger_effect_for` fell through to a
mixed-effect parser whose damage regex - unanchored under `fullmatch` - read
*inside* the quoted granted ability and turned the trigger into a burn spell:
CR 608.2b's "any target" prompt and 2 damage, with no Munitions ever created.
Fixing only the condition ships that burn spell; `test_a_nontoken_artifact_
entering_creates_munitions_not_a_burn_spell` is what catches it.

CR numbers looked up with `knowledge_search(type="rules")`/`mise run
rules:find` in this session: CR 111.1, 111.4, 205.3a, 603.2, 701.21a.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.effects import ELEMENTAL
from magic_cards_model.models import Type
from magic_cards_model.models.token import create_tokens
from tests.scenarios.harness import Scenario


def resolve_all(scenario: Scenario) -> None:
    """Drain pending triggers onto the stack and resolve everything,
    repeatedly. Unlike a spell's own `resolve_top` (CR 603.3, `Game._resolve_
    top`'s own trailing `_before_priority`), `put_onto_battlefield`,
    `create_tokens` and `sacrifice` do not queue a trigger onto the stack by
    themselves - this is the harness-side stand-in for "the next time a
    player would receive priority."
    """
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def pending_sources(scenario: Scenario) -> list[str]:
    """The source names of everything that has triggered but not gone on the
    stack yet. What a condition-matching test checks instead of a resolved
    effect, so it never depends on an effect shape this file does not own -
    Miirym's own "create a token that's a copy of it" is a pre-existing,
    separate gap (see `docs/engine-coverage.md`'s new row), not something
    fixed here."""
    return [item.source_name for item in scenario.pending_triggers]


# -- Weapons Manufacturing (CR 603.6a, 111.1, 111.3, 111.4) -----------------


def weapons_manufacturing_board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Mind Stone"],
            battlefield=["Weapons Manufacturing"],
        )
        .player("bob")
    )


def test_a_nontoken_artifact_entering_creates_munitions_not_a_burn_spell():
    """Traps 1 and 2 in the findings doc: fixing only the substring collision
    ships a burn spell (the trigger resolves straight into
    `damage_ability_targets`, and with no legal target chosen the trigger is
    simply removed per CR 608.2b - which reads exactly like the original bug
    and would hide this fix). The real card creates a token and deals no
    damage at all."""
    scenario = weapons_manufacturing_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob_life_before = scenario.player("bob").life

    scenario.put_onto_battlefield("Mind Stone", "alice")
    resolve_all(scenario)

    assert scenario.player("bob").life == bob_life_before, "not a burn spell"
    munitions = [state for state in scenario.game.battlefield if state.name == "Munitions"]
    assert len(munitions) == 1
    (token,) = munitions
    assert token.token is True
    assert token.types == (Type.ARTIFACT,), "Munitions is an artifact, never a creature"
    assert "leaves the battlefield" in (token.card.oracle_text or "").lower()


def test_munitions_itself_entering_does_not_retrigger_it():
    """Trap 4: Munitions is an artifact. Without the nontoken restriction
    enforced, each Munitions entering re-triggers Weapons Manufacturing -
    Munitions creating Munitions creating Munitions. Exactly one Munitions
    exists after the chain settles, and nothing is left pending."""
    scenario = weapons_manufacturing_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.put_onto_battlefield("Mind Stone", "alice")
    resolve_all(scenario)

    assert scenario.pending_triggers == []
    assert scenario.game.stack == []
    munitions = [state for state in scenario.game.battlefield if state.name == "Munitions"]
    assert len(munitions) == 1


def test_munitions_own_leaves_the_battlefield_ability_deals_damage_when_sacrificed():
    """Trap 6: `TokenDefinition.to_card()` synthesises a real `Card` whose
    `oracle_text` feeds `parse_abilities`, so Munitions' own "When this token
    leaves the battlefield, it deals 2 damage to any target." has to actually
    parse and resolve, not just look like it does. Proven end to end through
    the one leaves-the-battlefield route that already fires correctly today
    (`Game.sacrifice`/`put_into_graveyard`, CR 701.21a) - the exile and bounce
    routes are a separate, pre-existing defect
    (`docs/2026-09-08-trigger-findings.md`'s third defect, owned elsewhere),
    and this test does not depend on either."""
    scenario = weapons_manufacturing_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Mind Stone", "alice")
    resolve_all(scenario)
    (munitions,) = [state for state in scenario.game.battlefield if state.name == "Munitions"]
    bob_life_before = scenario.player("bob").life
    scenario.choose_trigger_targets("Munitions", ["bob"])

    scenario.game.sacrifice(munitions)
    resolve_all(scenario)

    assert scenario.player("bob").life == bob_life_before - 2


# -- Miirym, Sentinel Wyrm (CR 205.3a's Dragon subtype) ----------------------


def miirym_board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Archive Dragon", "Grizzly Bears"],
            battlefield=["Miirym, Sentinel Wyrm"],
        )
        .player("bob")
    )


def test_a_nontoken_dragon_entering_fires_miirym():
    scenario = miirym_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.put_onto_battlefield("Archive Dragon", "alice")

    assert "Miirym, Sentinel Wyrm" in pending_sources(scenario)


def test_a_nontoken_non_dragon_entering_does_not_fire_miirym():
    """Miirym's own condition is scoped to the Dragon subtype (CR 205.3a),
    not merely to "nontoken" - a nontoken creature of some other type must
    not fire it either."""
    scenario = miirym_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.put_onto_battlefield("Grizzly Bears", "alice")

    assert "Miirym, Sentinel Wyrm" not in pending_sources(scenario)


def test_miirym_does_not_trigger_off_her_own_entry():
    """ "another nontoken Dragon" excludes the source itself - the generic
    "another"/"other" self-exclusion `condition_matches` already applies to
    every ENTERS_THE_BATTLEFIELD condition, unrelated to the nontoken fix
    itself but load-bearing for this exact card."""
    scenario = Scenario().player("alice", hand=["Miirym, Sentinel Wyrm"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.put_onto_battlefield("Miirym, Sentinel Wyrm", "alice")

    assert pending_sources(scenario) == []


# -- Ashling, the Limitless (IS_SACRIFICED, CR 701.21a) ----------------------


def test_sacrificing_a_nontoken_elemental_fires_ashling():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ashling, the Limitless", "Hearth Elemental"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    elemental = scenario.creature("Hearth Elemental", "alice")

    scenario.game.sacrifice(elemental)

    assert "Ashling, the Limitless" in pending_sources(scenario)


def test_sacrificing_a_token_elemental_does_not_fire_ashling():
    """Nothing in `machines/triggers.py` read "nontoken" at all before this
    fix, substring collision or not - Ashling's own restriction was simply
    unmodelled, and would over-fire on a token Elemental once Weapons
    Manufacturing's and Miirym's collision was fixed elsewhere (the findings
    doc's own warning). `ELEMENTAL` is the real `TokenDefinition` Seasoned
    Pyromancer's own printed effect creates from - CR 701.7a's `create_tokens`
    called directly, not a hand-written token."""
    scenario = (
        Scenario().player("alice", battlefield=["Ashling, the Limitless"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (spirit,) = create_tokens(scenario.game, ELEMENTAL, "alice")
    assert spirit.token is True

    scenario.game.sacrifice(spirit)

    assert "Ashling, the Limitless" not in pending_sources(scenario)


# -- Belladonna Took (regression: "a token you control enters") -------------


def test_belladonna_took_still_fires_on_a_token_entering():
    """Do-not-regress: Belladonna Took's "a token you control enters" is the
    correct, intended user of the token-only guard - the same word-boundary
    fix that stops "nontoken" from matching it must not stop "token" either.
    """
    scenario = Scenario().player("alice", battlefield=["Belladonna Took"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    create_tokens(scenario.game, ELEMENTAL, "alice")

    assert "Belladonna Took" in pending_sources(scenario)


def test_belladonna_took_does_not_fire_on_a_nontoken_creature_entering():
    scenario = (
        Scenario()
        .player("alice", hand=["Grizzly Bears"], battlefield=["Belladonna Took"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.put_onto_battlefield("Grizzly Bears", "alice")

    assert "Belladonna Took" not in pending_sources(scenario)
