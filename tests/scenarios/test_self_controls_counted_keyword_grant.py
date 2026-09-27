""" "`<Name>`/"This creature" has `<keyword(s)>` as long as you control at
least N other `<type>`." - a self-conditional keyword grant (CR 613.1f) gated
on a *counted* board condition (CR 611.3a) rather than the bare "a/another
`<quality>`" `_SELF_CONTROLS_KEYWORD_GRANT_RE` already read.

- **Svyelun of Sea and Sky** - "Svyelun has indestructible as long as you
  control at least two other Merfolk." Its own name is CR 201.5's self-
  reference, rewritten to "this permanent" by `self_normalized_effect_text`
  before `_SELF_CONTROLS_COUNTED_KEYWORD_GRANT_RE` ever sees the sentence.
- **Invasion of Theros // Ephara, Ever-Sheltering** (the reported card,
  proven on the actual transformed battle back face) - "Ephara has lifelink
  and indestructible as long as you control at least three other
  enchantments." Ephara herself is a Legendary Enchantment Creature - a God -
  so "other" (CR 700.4) has to exclude her from her own count, the identical
  exclusion Svyelun's "other Merfolk" needs and the same
  `ControlledCountRequirement.other` flag both go through.

CR numbers verified this session with `mise run rules:find` against the
current CR:

- **CR 611.3a** - a continuous effect from a static ability "isn't 'locked
  in'; it applies at any given moment to whatever its text indicates."
- **CR 613.1f** - layer 6: ability-adding and ability-removing effects.
- **CR 700.4** - "other" excludes the object itself.
- **CR 702.12b** - indestructible: can't be destroyed, ignores the lethal-
  damage state-based action.
- **CR 702.15b** - lifelink: damage dealt by the source gains its controller
  that much life.
- **CR 310.12b** / **CR 115.4** / **CR 310.6** - a Siege's own defeat
  trigger; damage to a battle removes defense counters.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.machines.keywords import is_indestructible
from magic_cards_model.models import Zone
from tests.scenarios.harness import PlayedScenario, Scenario

# -- Svyelun of Sea and Sky: "... as long as you control at least two other Merfolk." --


def test_svyelun_is_not_indestructible_with_only_one_other_merfolk():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Svyelun of Sea and Sky", "Merfolk Looter"])
        .player("bob")
        .build()
    )
    svyelun = scenario.creature("Svyelun of Sea and Sky", "alice")

    assert not is_indestructible(svyelun, scenario.game)


def test_svyelun_gains_indestructible_with_two_other_merfolk():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Svyelun of Sea and Sky", "Merfolk Looter", "Cursecatcher"],
        )
        .player("bob")
        .build()
    )
    svyelun = scenario.creature("Svyelun of Sea and Sky", "alice")

    assert is_indestructible(svyelun, scenario.game)


def test_svyelun_loses_indestructible_once_a_merfolk_leaves():
    """CR 611.3a: the condition is re-asked live, never locked in."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Svyelun of Sea and Sky", "Merfolk Looter", "Cursecatcher"],
        )
        .player("bob")
        .build()
    )
    svyelun = scenario.creature("Svyelun of Sea and Sky", "alice")
    looter = scenario.creature("Merfolk Looter", "alice")
    assert is_indestructible(svyelun, scenario.game)

    scenario.game.destroy(looter)

    assert not is_indestructible(svyelun, scenario.game)


def test_svyelun_does_not_count_herself_toward_her_own_condition():
    """CR 700.4: "other Merfolk" excludes Svyelun, a Merfolk God herself -
    two *other* Merfolk are still required even though she is one too."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Svyelun of Sea and Sky", "Merfolk Looter"])
        .player("bob")
        .build()
    )
    svyelun = scenario.creature("Svyelun of Sea and Sky", "alice")

    # Only one *other* Merfolk (Svyelun herself would be a second, but CR
    # 700.4's "other" excludes her from her own count).
    assert not is_indestructible(svyelun, scenario.game)


# -- Invasion of Theros // Ephara, Ever-Sheltering: the reported card --------


def _defeat_siege_with_bolts(scenario: PlayedScenario, siege, mountains: list) -> None:
    """Defeats a Siege with two Lightning Bolts (CR 115.4/310.6) rather than
    combat, so the only enchantments on the battlefield when Ephara
    transforms in are the ones the test sets up."""
    scenario.cast_and_resolve("Lightning Bolt", mountains[0], username="alice", targets=[siege])
    scenario.cast_and_resolve("Lightning Bolt", mountains[1], username="alice", targets=[siege])
    scenario.game.check_state_based_actions()
    assert siege.counter_count("defense") == 0
    scenario.will_take_the_may(True, username="alice")
    scenario.pass_until_resolved()  # CR 310.12b's defeat trigger: exile, then cast
    scenario.pass_until_resolved()  # the transformed spell resolves and enters


def test_ephara_needs_three_other_enchantments_for_lifelink_and_indestructible():
    """Ephara is herself a Legendary Enchantment Creature - a God - so "at
    least three OTHER enchantments" (CR 700.4) must not count her. Two
    Pacifisms besides her are not enough."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Invasion of Theros", "Lightning Bolt", "Lightning Bolt"],
            battlefield=["Mountain", "Mountain", "Pacifism", "Pacifism"],
        )
        .player("bob", battlefield=["Grizzly Bears", "Grizzly Bears"])
        .build()
    )
    # CR 704.5m: an unattached Aura is a state-based action, not this test -
    # both Pacifisms enchant one of bob's Grizzly Bears (CR 704.5m places no
    # limit on how many Auras enchant the same permanent).
    bears = scenario.creature("Grizzly Bears", "bob")
    for pacifism in scenario.creatures("Pacifism", "Pacifism", username="alice"):
        pacifism.attach_to(bears)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    siege = scenario.put_onto_battlefield("Invasion of Theros", "alice")
    # "search your library for an Aura, God, or Demigod card" - none in an
    # empty library, so the search finds nothing and nothing else to answer.
    scenario.pass_until_resolved()  # the Siege's own enters trigger

    mountains = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    _defeat_siege_with_bolts(scenario, siege, mountains)

    assert siege.zone is Zone.BATTLEFIELD
    assert siege.transformed
    assert siege.name == "Ephara, Ever-Sheltering"
    assert not is_indestructible(siege, scenario.game)
    assert not has_keyword(siege, Keyword.LIFELINK, scenario.game)


def test_ephara_gains_lifelink_and_indestructible_with_three_other_enchantments():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Invasion of Theros", "Lightning Bolt", "Lightning Bolt"],
            battlefield=["Mountain", "Mountain", "Pacifism", "Pacifism", "Pacifism"],
        )
        .player("bob", battlefield=["Grizzly Bears", "Grizzly Bears"])
        .build()
    )
    # CR 704.5m: an unattached Aura is a state-based action, not this test.
    bears = scenario.creature("Grizzly Bears", "bob")
    for pacifism in scenario.creatures("Pacifism", "Pacifism", "Pacifism", username="alice"):
        pacifism.attach_to(bears)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    siege = scenario.put_onto_battlefield("Invasion of Theros", "alice")
    scenario.pass_until_resolved()  # the Siege's own enters trigger

    mountains = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    _defeat_siege_with_bolts(scenario, siege, mountains)

    assert siege.zone is Zone.BATTLEFIELD
    assert siege.transformed
    assert siege.name == "Ephara, Ever-Sheltering"
    assert is_indestructible(siege, scenario.game)
    assert has_keyword(siege, Keyword.LIFELINK, scenario.game)
