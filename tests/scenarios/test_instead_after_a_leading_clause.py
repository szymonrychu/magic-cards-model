"""Scenario: "`<leading sentence>`. `<base sentence>`. If `<condition>`,
`<alternative>` instead." - a CR 614.1a base-or-alternative pair that follows
an independent instruction in the same ability (T-136 b1).

The existing pair readers (`modal._parse_condition_instead_clause` and its
ability twin) read a text that is exactly "`<base>`. `<if> ... instead`";
a sentence before the base made the whole text unreadable, so a Mission read as
silent. `modal._parse_instead_pair_after_leading_clauses` reads each adjacent
base-and-"instead" sentence pair whole, and every other sentence through the
ordinary pipeline, in written order (CR 608.2c).

- Conquest Mission (trk): "... put a quest counter on this enchantment. Create
  a 1/1 colorless Borg artifact creature token. If this enchantment has six or
  more quest counters on it, create two of those tokens instead." - the
  alternative names "those tokens" and puts "instead" last.
- Support Mission (trk): "... put a quest counter on this enchantment. Put a
  +1/+1 counter on that creature. If this enchantment has five or more quest
  counters on it, instead put two +1/+1 counters on that creature." - an
  entirely different base (a counter on the triggering creature) and
  "instead" first.

The leading counter sentence must run first: the threshold is met by the very
counter this trigger puts on, which is what the boundary tests pin. No
non-trk printing has this shape (Scryfall checked 2026-11-12, see MEMORY.md),
so generality is shown by two differently worded Missions and by varying the
count, the trigger object and the controller.

Every CR number here was looked up with `mise run rules:find`:

- **CR 614.1a** - "instead" effects are replacement effects.
- **CR 608.2c** - instructions are followed in the order written.
- **CR 122.1** - a counter is a marker on an object, interchangeable by name.
- **CR 603.2** - a game event matching a trigger event triggers the ability.
- **CR 111.3** - a creating effect defines the token's characteristics.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import CardState, Zone

from .harness import PlayedScenario, Scenario


def _board(*, mission: str, hand: list[str]) -> PlayedScenario:
    scenario = (
        Scenario()
        .player("alice", battlefield=[mission], hand=hand, library=["Island"] * 3)
        .player("bob", hand=["Ornithopter", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _settle(scenario: PlayedScenario) -> None:
    """Put every pending trigger on the stack and resolve until it is empty."""
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _enter(scenario: PlayedScenario, name: str, username: str = "alice") -> CardState:
    card = scenario.put_onto_battlefield(name, username)
    _settle(scenario)
    return card


def _quest(scenario: PlayedScenario, mission: str) -> int:
    return scenario.find(mission, Zone.BATTLEFIELD, "alice").counter_count("quest")


def _borgs(scenario: PlayedScenario) -> list[CardState]:
    return [s for s in scenario.game.battlefield if s.name == "Borg Token"]


def _preload(scenario: PlayedScenario, mission: str, quest: int) -> None:
    if quest:
        scenario.game.add_counters(
            scenario.find(mission, Zone.BATTLEFIELD, "alice"), "quest", quest
        )


# ---------------------------------------------------------------------------
# Conquest Mission
# ---------------------------------------------------------------------------


def test_conquest_mission_counts_the_artifact_and_makes_one_borg():
    scenario = _board(mission="Conquest Mission", hand=["Ornithopter"])
    _enter(scenario, "Ornithopter")
    assert _quest(scenario, "Conquest Mission") == 1
    assert len(_borgs(scenario)) == 1


def test_conquest_mission_borg_token_is_the_described_creature():
    scenario = _board(mission="Conquest Mission", hand=["Ornithopter"])
    _enter(scenario, "Ornithopter")
    (borg,) = _borgs(scenario)
    chars = scenario.game.characteristics_of(borg)
    assert borg.token
    assert (chars.power, chars.toughness) == (1, 1)
    assert not chars.colors
    assert "Borg" in chars.subtypes


def test_conquest_mission_five_counters_after_this_one_is_still_one_borg():
    """4 + the new counter = 5: below "six or more", so the base runs."""
    scenario = _board(mission="Conquest Mission", hand=["Ornithopter"])
    _preload(scenario, "Conquest Mission", 4)
    _enter(scenario, "Ornithopter")
    assert _quest(scenario, "Conquest Mission") == 5
    assert len(_borgs(scenario)) == 1


def test_conquest_mission_the_counter_this_trigger_adds_reaches_six():
    """5 + the new counter = 6: the leading sentence ran first, so the
    condition sees six and the alternative replaces the base - two tokens,
    not three (CR 614.1a: instead, never in addition)."""
    scenario = _board(mission="Conquest Mission", hand=["Ornithopter"])
    _preload(scenario, "Conquest Mission", 5)
    _enter(scenario, "Ornithopter")
    assert _quest(scenario, "Conquest Mission") == 6
    assert len(_borgs(scenario)) == 2


def test_conquest_mission_stays_at_two_borgs_far_past_the_threshold():
    scenario = _board(mission="Conquest Mission", hand=["Ornithopter"])
    _preload(scenario, "Conquest Mission", 9)
    _enter(scenario, "Ornithopter")
    assert _quest(scenario, "Conquest Mission") == 10
    assert len(_borgs(scenario)) == 2


def test_conquest_mission_threshold_crossing_across_two_artifacts():
    """Counters 4 -> 5 (one Borg), then 5 -> 6 (two Borgs): three in all."""
    scenario = _board(mission="Conquest Mission", hand=["Ornithopter", "Ornithopter"])
    _preload(scenario, "Conquest Mission", 4)
    _enter(scenario, "Ornithopter")
    assert len(_borgs(scenario)) == 1
    _enter(scenario, "Ornithopter")
    assert _quest(scenario, "Conquest Mission") == 6
    assert len(_borgs(scenario)) == 3


def test_conquest_mission_ignores_its_own_borg_tokens():
    """The trigger watches a *nontoken* artifact: the Borg artifact creature
    tokens it makes never count a second time."""
    scenario = _board(mission="Conquest Mission", hand=["Ornithopter"])
    _enter(scenario, "Ornithopter")
    assert _quest(scenario, "Conquest Mission") == 1


def test_conquest_mission_ignores_an_opponents_artifact():
    scenario = _board(mission="Conquest Mission", hand=[])
    _enter(scenario, "Ornithopter", "bob")
    assert _quest(scenario, "Conquest Mission") == 0
    assert not _borgs(scenario)


def test_conquest_mission_ignores_a_nonartifact_permanent():
    scenario = _board(mission="Conquest Mission", hand=["Grizzly Bears"])
    _enter(scenario, "Grizzly Bears")
    assert _quest(scenario, "Conquest Mission") == 0
    assert not _borgs(scenario)


# ---------------------------------------------------------------------------
# Support Mission
# ---------------------------------------------------------------------------


def _plus_one_counters(card: CardState) -> int:
    return card.counter_count("+1/+1")


def test_support_mission_puts_one_plus_one_counter_on_the_creature_that_entered():
    scenario = _board(mission="Support Mission", hand=["Grizzly Bears"])
    bears = _enter(scenario, "Grizzly Bears")
    assert _quest(scenario, "Support Mission") == 1
    assert _plus_one_counters(bears) == 1
    assert scenario.game.characteristics_of(bears).power == 3


def test_support_mission_four_counters_after_this_one_is_still_one_counter():
    scenario = _board(mission="Support Mission", hand=["Grizzly Bears"])
    _preload(scenario, "Support Mission", 3)
    bears = _enter(scenario, "Grizzly Bears")
    assert _quest(scenario, "Support Mission") == 4
    assert _plus_one_counters(bears) == 1


def test_support_mission_the_counter_this_trigger_adds_reaches_five():
    """4 + the new counter = 5: two +1/+1 counters instead of one, never
    three (CR 614.1a)."""
    scenario = _board(mission="Support Mission", hand=["Grizzly Bears"])
    _preload(scenario, "Support Mission", 4)
    bears = _enter(scenario, "Grizzly Bears")
    assert _quest(scenario, "Support Mission") == 5
    assert _plus_one_counters(bears) == 2
    assert scenario.game.characteristics_of(bears).power == 4


def test_support_mission_keeps_two_counters_far_past_the_threshold():
    scenario = _board(mission="Support Mission", hand=["Grizzly Bears"])
    _preload(scenario, "Support Mission", 11)
    bears = _enter(scenario, "Grizzly Bears")
    assert _quest(scenario, "Support Mission") == 12
    assert _plus_one_counters(bears) == 2


def test_support_mission_grows_an_artifact_creature_too():
    scenario = _board(mission="Support Mission", hand=["Ornithopter"])
    thopter = _enter(scenario, "Ornithopter")
    assert _plus_one_counters(thopter) == 1
    assert scenario.game.characteristics_of(thopter).power == 1


def test_support_mission_counts_each_creature_separately_and_crosses_the_threshold():
    scenario = _board(mission="Support Mission", hand=["Grizzly Bears", "Ornithopter"])
    _preload(scenario, "Support Mission", 3)
    first = _enter(scenario, "Grizzly Bears")
    second = _enter(scenario, "Ornithopter")
    assert _plus_one_counters(first) == 1
    assert _plus_one_counters(second) == 2
    assert _quest(scenario, "Support Mission") == 5


def test_support_mission_ignores_an_opponents_creature():
    scenario = _board(mission="Support Mission", hand=[])
    bears = _enter(scenario, "Grizzly Bears", "bob")
    assert _quest(scenario, "Support Mission") == 0
    assert _plus_one_counters(bears) == 0


def test_support_mission_ignores_a_noncreature_permanent():
    scenario = _board(mission="Support Mission", hand=["Conquest Mission"])
    _enter(scenario, "Conquest Mission")
    assert _quest(scenario, "Support Mission") == 0
