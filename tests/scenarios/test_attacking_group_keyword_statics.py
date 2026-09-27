"""A layer 6 keyword grant (CR 613.1f) to a group filtered on combat state
(CR 508.1k, "attacking") rather than the token status `machines/layers.
AttackingTokensControlledBy` already covered - `machines/attacking_statics.py`
(new this round), read by `machines/layers._parse_layer_sentence`.

- **Raphael, the Nightwatcher** - "Attacking creatures you control have
  double strike." No subtype filter at all.
- **Dark Leo & Shredder** - "Attacking Ninjas you control have deathtouch." A
  subtype filter, and Dark Leo & Shredder is itself a Ninja (its own type
  line), so the self-inclusive case is exercised directly.
- **Crossway Troublemakers** (proof printing, verified Modern/Pioneer/
  Standard legal, not a listed tmt card, not in any `decks/*.txt`) - "Attacking
  Vampires you control have deathtouch and lifelink." A *different* subtype
  and *two* keywords in one grant, proving the reader generalises past one
  keyword and past Dark Leo & Shredder's own subject.

`AttackingGroupControlledBy` (`machines/layers.py`) reads `LayerContext.
attacking` fresh on every computation (CR 613.5), so the keyword is there
only while the creature is actually attacking (CR 508.1k) and gone the moment
it is removed from combat (CR 506.4) - proved here by checking a creature
that never attacked at all, and by leaving combat behind at end of combat.

CR numbers verified this session with `mise run rules:find`:

- **CR 508.1k** - a declared attacker remains one "until it's removed from
  combat or the combat phase ends".
- **CR 613.1f** - layer 6: ability-adding effects.
- **CR 702.2b** - deathtouch destroys via state-based action any creature
  dealt damage by its source.
- **CR 702.4b** - double strike creatures assign damage in both combat damage
  steps, "as the combat damage step begins".
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.models import Zone

from .harness import Scenario

# -- Raphael, the Nightwatcher: no subtype filter ----------------------------


def test_an_attacking_creature_has_double_strike():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Raphael, the Nightwatcher", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Hill Giant"])
    ).build()
    raphael = scenario.creature("Raphael, the Nightwatcher", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    assert not has_keyword(bears, Keyword.DOUBLE_STRIKE, scenario.game), "not attacking yet"

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(raphael, bears)

    assert has_keyword(raphael, Keyword.DOUBLE_STRIKE, scenario.game)
    assert has_keyword(bears, Keyword.DOUBLE_STRIKE, scenario.game)

    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.no_blocks()
    raphael_power = scenario.game.power_of(raphael)
    scenario.combat_damage()
    # CR 702.4b: double strike deals damage in both combat damage steps -
    # Raphael's own power hits twice; Grizzly Bears (also granted double
    # strike) hits twice too.
    assert scenario.player("bob").life == 20 - (raphael_power * 2) - 4


def test_a_creature_that_did_not_attack_never_gets_double_strike():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Raphael, the Nightwatcher", "Grizzly Bears"])
        .player("bob")
    ).build()
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Raphael, the Nightwatcher", "alice"))

    assert not has_keyword(bears, Keyword.DOUBLE_STRIKE, scenario.game)


def test_double_strike_is_gone_once_combat_ends():
    scenario = (
        Scenario().player("alice", battlefield=["Raphael, the Nightwatcher"]).player("bob")
    ).build()
    raphael = scenario.creature("Raphael, the Nightwatcher", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(raphael)
    assert has_keyword(raphael, Keyword.DOUBLE_STRIKE, scenario.game)

    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.start_at(Step.END_OF_COMBAT)
    assert has_keyword(raphael, Keyword.DOUBLE_STRIKE, scenario.game), (
        "still attacking - CR 508.1k: an attacker stays one until removed from "
        "combat or the combat phase ends, and end of combat is still part of it"
    )

    scenario.advance()  # into postcombat main - runs CombatMachine.clear()
    assert scenario.step is Step.POSTCOMBAT_MAIN
    assert not has_keyword(raphael, Keyword.DOUBLE_STRIKE, scenario.game), (
        "the combat phase has now ended (CR 508.1k)"
    )


# -- Dark Leo & Shredder: a Ninja-subtype filter ------------------------------


def test_attacking_ninjas_have_deathtouch_including_the_source_itself():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Dark Leo & Shredder", "Foot Ninjas", "Grizzly Bears"])
        .player("bob", battlefield=["Hill Giant"])
    ).build()
    dark_leo = scenario.creature("Dark Leo & Shredder", "alice")
    foot_ninjas = scenario.creature("Foot Ninjas", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(dark_leo, foot_ninjas, bears)

    assert has_keyword(dark_leo, Keyword.DEATHTOUCH, scenario.game), "a Ninja itself"
    assert has_keyword(foot_ninjas, Keyword.DEATHTOUCH, scenario.game), "another attacking Ninja"
    assert not has_keyword(bears, Keyword.DEATHTOUCH, scenario.game), "not a Ninja"


def test_deathtouch_actually_kills_a_bigger_blocker_for_one_damage():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Dark Leo & Shredder"])
        .player("bob", battlefield=["Craw Wurm"])
    ).build()
    dark_leo = scenario.creature("Dark Leo & Shredder", "alice")
    wurm = scenario.creature("Craw Wurm", "bob")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(dark_leo)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.block(dark_leo, wurm)

    scenario.combat_damage()
    scenario.state_based_actions()

    assert wurm.zone is Zone.GRAVEYARD, "CR 702.2b: any damage from a deathtouch source destroys it"


# -- Crossway Troublemakers: a second printing, a different subtype, two ----
# -- keywords in one grant ----------------------------------------------------


def test_crossway_troublemakers_grants_both_deathtouch_and_lifelink_to_attacking_vampires():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Crossway Troublemakers", "Alley Assailant"])
        .player("bob", battlefield=["Craw Wurm"])
    ).build()
    troublemakers = scenario.creature("Crossway Troublemakers", "alice")
    assailant = scenario.creature("Alley Assailant", "alice")

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(troublemakers, assailant)

    for vampire in (troublemakers, assailant):
        assert has_keyword(vampire, Keyword.DEATHTOUCH, scenario.game)
        assert has_keyword(vampire, Keyword.LIFELINK, scenario.game)
