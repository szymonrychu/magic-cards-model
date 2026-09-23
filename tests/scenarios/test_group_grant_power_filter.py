"""Scenario: a general "creatures you control with power N or greater gain
`<keyword(s)>` until end of turn" one-shot group grant (CR 611.2, CR 611.2c) -
the mass-pump/keyword-grant family's own bare "creatures you control"
subject narrowed by a power filter.

Smuggler's Surprise's own third Spree mode - "Creatures you control with
power 4 or greater gain hexproof and indestructible until end of turn." -
exposed two real gaps once its own text finally reached the reader at all
(the bullet fix, `test_spree_bullets.py`):

- `_mass_creature_group_targets`'s own plain-prefix `startswith("creatures
  you control")` check silently swallowed the whole filtered subject and
  handed back *every* creature the caster controls, dropping the power
  restriction entirely rather than reading it.
- `_CLAUSE_SEPARATOR`'s bare " and " (between "hexproof" and
  "indestructible") cut a filtered, multi-keyword grant into two clause
  fragments before `_parse_mass_pump_group_clause` ever saw it whole, the
  same shape `_CONTINUOUS_PUMP_OR_KEYWORD_RE`'s own whole-text try already
  fixed for a single *targeted* creature's pump.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 611.2** - a one-shot continuous effect from a spell or ability's
  resolution.
- **CR 611.2c** - "the set of objects it affects ... is determined when the
  effect begins to apply. ... Later changes to the game state are not
  taken into account, unless the effect specifically says otherwise" - the
  filter is read **once**, at resolution, never re-checked afterward.
- **CR 613.1f** - "Layer 6: Ability-adding effects ... are applied" (the
  keyword grant itself).
- **CR 702.172a** - Spree: "Choose one or more modes. As an additional cost
  to cast this spell, pay the costs associated with those modes."

Gustrider Exuberant (off-pool, confirmed with `scripts/add_card.py`,
Modern-legal) is the proof this reads generally and proves the power filter
is genuinely *locked in at resolution* rather than re-evaluated: a single
keyword ("flying", not Smuggler's Surprise's own two), on an *activated*
ability rather than a spell, with a threshold of 5 rather than 4.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.machines.keywords import is_indestructible
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_smugglers_surprise_mode_three_alone_grants_only_to_creatures_with_power_four_or_greater():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Smuggler's Surprise", "Giant Growth"],
            battlefield=["Forest"] * 4 + ["Grizzly Bears", "Hill Giant"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")  # 2/2, pumped to 5/5 below
    giant = scenario.creature("Hill Giant", "alice")  # 3/3, stays under the threshold
    forests = scenario.untapped_sources(*(["Forest"] * 4))

    scenario.cast_and_resolve("Giant Growth", forests[0], targets=[bears])
    casting = scenario.cast("Smuggler's Surprise")
    casting.choose_modes([3])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *forests[1:3])
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert has_keyword(bears, "hexproof", scenario.game)
    assert is_indestructible(bears, scenario.game)
    assert not has_keyword(giant, "hexproof", scenario.game)
    assert not is_indestructible(giant, scenario.game)


def test_smugglers_surprise_modes_two_and_three_together_puts_a_creature_and_grants_the_group():
    """Modes 2 and 3 chosen together (CR 700.2a): mode 2's own "put up to
    two creature cards from your hand onto the battlefield" alongside mode
    3's own power-filtered group grant, over Craw Wurm (6/4, already on the
    battlefield and well past the power-4 threshold)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Smuggler's Surprise", "Grizzly Bears"],
            battlefield=["Forest"] * 7 + ["Craw Wurm"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wurm = scenario.creature("Craw Wurm", "alice")
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")
    sources = scenario.untapped_sources(*(["Forest"] * 7))
    scenario.will_choose_cards(bears, username="alice", source="Smuggler's Surprise")

    casting = scenario.cast("Smuggler's Surprise")
    casting.choose_modes([2, 3])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert any(state.name == "Grizzly Bears" for state in scenario.game.battlefield), (
        "mode 2's own put-onto-the-battlefield ran"
    )
    assert has_keyword(wurm, "hexproof", scenario.game)
    assert is_indestructible(wurm, scenario.game)


def test_gustrider_exuberant_locks_the_power_filter_at_the_moment_it_resolves():
    """Off-pool, activated-ability proof, and the file's own corner case:
    CR 611.2c fixes the *set* of creatures a one-shot group effect affects
    the moment it begins to apply, not a live filter re-checked as power
    changes afterward. Grizzly Bears is pumped to power 5 with Giant Growth
    *before* the ability resolves and gains flying; Hill Giant is pumped to
    power 6 with a second Giant Growth *after* the ability has already
    resolved and does not - if the filter re-evaluated power live instead of
    locking the group in at resolution, Hill Giant would gain flying too.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Giant Growth", "Giant Growth"],
            battlefield=[
                "Forest",
                "Forest",
                "Gustrider Exuberant",
                "Grizzly Bears",
                "Hill Giant",
            ],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gustrider = scenario.creature("Gustrider Exuberant", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    (forest1, forest2) = scenario.untapped_sources("Forest", "Forest")

    scenario.cast_and_resolve("Giant Growth", forest1, targets=[bears])
    scenario.activate(gustrider, sacrificing=[gustrider])
    scenario.resolve_top()
    scenario.cast_and_resolve("Giant Growth", forest2, targets=[giant])

    assert has_keyword(bears, Keyword.FLYING, scenario.game), (
        "power 5 at the moment the ability resolved"
    )
    assert not has_keyword(giant, Keyword.FLYING, scenario.game), (
        "power 3 at resolution - pumped to 6 only afterward, too late to be swept in"
    )
