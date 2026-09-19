"""Scenario: Gix, Yawgmoth Praetor's two abilities - a combat-damage trigger
whose "its controller" refers to whichever creature dealt the damage, not
Gix's own controller, and an X-cost activated ability whose "exile the top X
... you may play lands and cast spells ... without paying their mana costs"
must be played immediately, during the same resolution (Gatherer ruling:
"You must play the cards as you resolve the last ability. You can't wait and
play them later").

Both abilities used to leave a matching condition doing nothing: the trigger
fired (`machines/triggers.condition_matches`'s own general `DEALS_DAMAGE`
reading already covers "a creature ... deals combat damage to one of your
opponents" - no code written for this card specifically), but its own effect
- "its controller may pay 1 life. If they do, they draw a card." - had no
parser anywhere; the activated ability's `{X}` cost paid correctly, but its
own effect had no parser either.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 120.1** - "An object that deals damage is the source of that damage" -
  "its controller" is the controller of the creature that dealt combat
  damage, not necessarily Gix's own controller.
- **CR 118.12** - the "may [cost]. If they do, [consequence]" reflexive
  shape.
- **CR 119.4** - paying life, and CR 119.4b's "players can always pay 0
  life".
- **CR 121.1** - drawing a card.
- **CR 701.9a** - discarding, Gix's own activation cost.
- **CR 608.2g** - casting a spell (or, CR 305.1/CR 117.1's own special-action
  exception, playing a land) during a resolution rather than through
  priority.
- **CR 305.2b/CR 305.3** - a land play still obeys the once-per-turn count
  and the active-player restriction even inside a CR 608.2g window.
- **CR 110.2a** - an object put onto the battlefield this way enters under
  the player who put it there's control, not its owner's.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_gix_combat_trigger_lets_the_damaging_creatures_controller_pay_and_draw():
    """Alice's own Serra Angel deals combat damage to bob, one of alice's
    opponents - "its controller" is alice, who may pay 1 life to draw a
    card.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Gix, Yawgmoth Praetor", "Serra Angel"], library=["Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    serra = scenario.creature("Serra Angel", "alice")
    scenario.attack_with(serra, defending="bob")
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.will_pay_the_life(True, source="Gix, Yawgmoth Praetor")

    scenario.resolve_top()

    alice = scenario.player("alice")
    assert alice.life == 19, "CR 119.4: paid 1 life"
    assert [c.name for c in alice.hand] == ["Mountain"], "CR 121.1: drew the card"


def test_gix_combat_trigger_declines_the_life_payment():
    """CR 118.12's "may" is a real choice - declining pays nothing and draws
    nothing."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Gix, Yawgmoth Praetor", "Serra Angel"], library=["Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    serra = scenario.creature("Serra Angel", "alice")
    scenario.attack_with(serra, defending="bob")
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.will_pay_the_life(False, source="Gix, Yawgmoth Praetor")

    scenario.resolve_top()

    alice = scenario.player("alice")
    assert alice.life == 20
    assert alice.hand == []


def test_gix_exiles_top_x_and_plays_a_land_and_casts_a_spell_mid_resolution():
    """ "{4}{B}{B}{B}, Discard X cards: Exile the top X cards of target
    opponent's library. You may play lands and cast spells from among cards
    exiled this way without paying their mana costs." X=2 exiles bob's top
    two library cards (Forest, Opt); alice plays the Forest (CR 305.1's
    special action, no mana spent, entering under her own control per CR
    110.2a) and casts Opt for free, which goes on the stack and is resolved
    afterward like any other spell (CR 608.2g).
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Mountain", "Island"],
            battlefield=["Gix, Yawgmoth Praetor"] + ["Swamp"] * 7,
            library=["Plains"],
        )
        .player("bob", library=["Forest", "Opt"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gix = scenario.find("Gix, Yawgmoth Praetor", Zone.BATTLEFIELD, "alice")
    discards = list(scenario.player("alice").hand)
    swamps = scenario.untapped_sources(*(["Swamp"] * 7))
    forest = scenario.find("Forest", Zone.LIBRARY, "bob")
    opt = scenario.find("Opt", Zone.LIBRARY, "bob")

    ability = scenario.activate(gix, *swamps, discarding=discards, x_value=2, targets=["bob"])
    assert ability is not None
    assert {c.name for c in scenario.player("alice").graveyard} == {"Mountain", "Island"}

    scenario.will_take_the_may(True, source="Gix, Yawgmoth Praetor", times=None)
    scenario.will_choose_cards(opt, username="alice", source="Gix, Yawgmoth Praetor")
    scenario.will_choose_cards(forest, username="alice", source="Gix, Yawgmoth Praetor")
    scenario.scry_keeping_everything_on_top()

    scenario.resolve_top()  # Gix's own ability: exile, play the land, cast Opt
    scenario.resolve_top()  # Opt, now on the stack per CR 608.2g

    alice = scenario.player("alice")
    assert forest.zone is Zone.BATTLEFIELD
    assert forest.controller == "alice", "CR 110.2a: under the player who played it"
    assert forest.owner == "bob", "CR 108.3: ownership never moved"
    assert opt.zone is Zone.GRAVEYARD
    assert [c.name for c in alice.hand] == ["Plains"], "Opt drew alice's own top card"
    assert scenario.player("bob").library == []
