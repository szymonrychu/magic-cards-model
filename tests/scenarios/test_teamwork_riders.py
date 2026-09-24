"""Every "If this spell was cast using teamwork, ..." rider in the pool -
CR 601.2b's optional additional cost (`machines/teamwork.py`) read back at
resolution (`Game.condition_holds`'s own `_CONDITION_CAST_USING_TEAMWORK`)
or at announcement (`machines/casting.Casting._alternative_mode_count`,
`teamwork_instead_target_text`), one shape per card.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file.

- **CR 601.2b** - a modal spell's "choose one[, ...]" announcement, and the
  alternative count a paid additional cost may raise (CR 700.2, CR 601.4).
- **CR 601.2c** - which targets a spell needs, decided by what was chosen
  at announcement (modes, or an alternative target restriction).
- **CR 608.2b** - a spell's targets are rechecked as it resolves.
- **CR 608.2c** - a resolving instruction runs as its text says, in order.
- **CR 608.2h** - CR 400.7's "that <noun>"/"that creature's controller"
  anaphora, fixed once, to what an earlier instruction already found.
- **CR 118.12a** - "[Do something] unless [a player does something else]".
- **CR 701.20a/701.20b** - revealing cards; CR 111.2 - who creates/owns a
  token; CR 110.2a - who controls a permanent put onto the battlefield.

Widow's Bite proves the "choose one. If cast using teamwork, choose both
instead." modal rider (Atlantis Attacks, Go Nuts!, HULK SMASH!, Murdock's
Crusade all share the identical modal shape, already exercised by the
ordinary modal machinery `tests/scenarios/test_modal_spells.py` covers).
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario, mana_from

# --------------------------------------------------------------------------
# Widow's Bite: "Choose one. If this spell was cast using teamwork, choose
# both instead." - the modal rider template shared by five pool cards.
# --------------------------------------------------------------------------


def test_widows_bite_without_teamwork_only_the_chosen_mode_runs():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Widow's Bite"], battlefield=["Swamp", "Swamp"])
        .player("bob", battlefield=["Grizzly Bears", "Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    giant = scenario.creature("Hill Giant", "bob")

    casting = scenario.cast("Widow's Bite")
    casting.choose_modes([2])  # "-2/-2" only
    casting.choose_targets([bears])
    payment = casting.begin_paying()
    for source in scenario.untapped_sources("Swamp", "Swamp"):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bears.zone is Zone.GRAVEYARD  # base 2/2, -2/-2 makes it 0/0 (CR 704.5f)
    assert not scenario.game.characteristics_of(giant).has_ability("Deathtouch")


def test_widows_bite_cast_using_teamwork_runs_both_modes():
    """CR 601.4: the alternative "choose both instead" is read off `self.
    teamwork_paid`, live, while modes are still being chosen - `pay_teamwork`
    has to run before `choose_modes`."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Widow's Bite"],
            battlefield=["Swamp", "Swamp", "Grizzly Bears", "Hill Giant"],
        )
        .player("bob", battlefield=["Elvish Mystic", "Llanowar Elves"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    mystic = scenario.creature("Elvish Mystic", "bob")
    elves = scenario.creature("Llanowar Elves", "bob")

    casting = scenario.cast("Widow's Bite")
    casting.pay_teamwork([bears, giant])  # 2 + 3 = 5 power, Teamwork 3
    casting.choose_modes([1, 2])
    casting.choose_targets([mystic, elves])
    payment = casting.begin_paying()
    for source in scenario.untapped_sources("Swamp", "Swamp"):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert scenario.game.characteristics_of(mystic).has_ability("Deathtouch")
    assert elves.zone is Zone.GRAVEYARD  # -2/-2 on a 1/1


# --------------------------------------------------------------------------
# Cruel Alliance: "Exile target creature with mana value 3 or less. If this
# spell was cast using teamwork, instead exile target creature and you gain
# 3 life." - a target-restriction swap plus an additive life gain.
# --------------------------------------------------------------------------


def cruel_alliance_board() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Cruel Alliance"],
            battlefield=["Swamp", "Swamp", "Swamp", "Grizzly Bears", "Hill Giant"],
        )
        .player("bob", battlefield=["Serra Angel"])  # 4 mana value - over the unteamworked cap
    )


def test_cruel_alliance_without_teamwork_exiles_and_gains_no_life():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Cruel Alliance"], battlefield=["Swamp", "Swamp", "Swamp"])
        .player("bob", battlefield=["Grizzly Bears"])  # mana value 2, legal unteamworked
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    life_before = alice.life

    casting = scenario.cast("Cruel Alliance")
    casting.choose_targets([bears])
    payment = casting.begin_paying()
    for source in scenario.untapped_sources("Swamp", "Swamp", "Swamp"):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bears.zone is Zone.EXILE
    assert alice.life == life_before


def test_cruel_alliance_cast_using_teamwork_lifts_the_mana_value_cap_and_gains_life():
    """The teamwork rider's own target sentence names no mana value cap at
    all, read at announcement (CR 601.2c) through `machines/teamwork.
    teamwork_instead_target_text`."""
    scenario = cruel_alliance_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    angel = scenario.creature("Serra Angel", "bob")
    life_before = alice.life

    casting = scenario.cast("Cruel Alliance")
    casting.pay_teamwork([bears, giant])  # 2 + 3 = 5 power, Teamwork 2
    casting.choose_targets([angel])  # mana value 4 - illegal without teamwork
    payment = casting.begin_paying()
    for source in scenario.untapped_sources("Swamp", "Swamp", "Swamp"):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert angel.zone is Zone.EXILE
    assert alice.life == life_before + 3


# --------------------------------------------------------------------------
# Helicarrier Strike: "... deals 2 damage to target attacking or blocking
# creature. If this spell was cast using teamwork, it deals 4 damage to
# that creature instead." - a plain CR 614.1a "instead" amount override.
# --------------------------------------------------------------------------


def helicarrier_board() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Helicarrier Strike"],
            battlefield=["Plains", "Grizzly Bears", "Hill Giant", "Craw Wurm"],
        )
        .player("bob")
    )


def _declare_attacker(scenario, attacker, defending="bob"):
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(attacker, defending=defending)


def test_helicarrier_strike_without_teamwork_deals_2():
    """Craw Wurm's 4 toughness survives 2 damage - not lethal (CR 704.5g)."""
    scenario = helicarrier_board().build()
    wurm = scenario.creature("Craw Wurm", "alice")
    _declare_attacker(scenario, wurm)

    casting = scenario.cast("Helicarrier Strike")
    casting.choose_targets([wurm])
    payment = casting.begin_paying()
    for source in scenario.untapped_sources("Plains"):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert wurm.damage == 2
    assert wurm.zone is Zone.BATTLEFIELD


def test_helicarrier_strike_cast_using_teamwork_deals_4_instead():
    """Craw Wurm's own 4 toughness makes 4 damage lethal (CR 704.5g), where
    2 was not - the state-based action is the observable proof that the
    full 4, not 2, was actually dealt."""
    scenario = helicarrier_board().build()
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    wurm = scenario.creature("Craw Wurm", "alice")
    _declare_attacker(scenario, wurm)

    casting = scenario.cast("Helicarrier Strike")
    casting.pay_teamwork([bears, giant])  # 5 power, Teamwork 2
    casting.choose_targets([wurm])
    payment = casting.begin_paying()
    for source in scenario.untapped_sources("Plains"):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert not scenario.game.conditional_clause_notices, "the condition must read, not fail closed"
    assert wurm.zone is Zone.GRAVEYARD


# --------------------------------------------------------------------------
# Repulsor Blast: "... deals 5 damage to target creature. If this spell was
# cast using teamwork, it also deals 2 damage to that creature's
# controller." - an additive rider, never a replacement.
# --------------------------------------------------------------------------


def test_repulsor_blast_cast_using_teamwork_also_damages_the_controller():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Repulsor Blast"],
            battlefield=[
                "Mountain",
                "Mountain",
                "Mountain",
                "Mountain",
                "Grizzly Bears",
                "Hill Giant",
            ],
        )
        .player("bob", battlefield=["Elvish Mystic"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    mystic = scenario.creature("Elvish Mystic", "bob")
    bob_life_before = scenario.player("bob").life

    casting = scenario.cast("Repulsor Blast")
    casting.pay_teamwork([bears, giant])  # 5 power, Teamwork 2
    casting.choose_targets([mystic])
    payment = casting.begin_paying()
    for source in scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain"):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert mystic.zone is Zone.GRAVEYARD  # 5 damage to a 0/1
    assert scenario.player("bob").life == bob_life_before - 2


def test_repulsor_blast_without_teamwork_does_not_damage_the_controller():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Repulsor Blast"],
            battlefield=["Mountain", "Mountain", "Mountain", "Mountain"],
        )
        .player("bob", battlefield=["Elvish Mystic"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mystic = scenario.creature("Elvish Mystic", "bob")
    bob_life_before = scenario.player("bob").life

    casting = scenario.cast("Repulsor Blast")
    casting.choose_targets([mystic])
    payment = casting.begin_paying()
    for source in scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain"):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert scenario.player("bob").life == bob_life_before


# --------------------------------------------------------------------------
# Team Tactics: "Target creature gains double strike until end of turn. If
# this spell was cast using teamwork, that creature also gains trample
# until end of turn." - the `_CONDITIONAL_REFERENT_LEADING_RE` shape.
# --------------------------------------------------------------------------


def test_team_tactics_cast_using_teamwork_also_grants_trample():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Team Tactics"],
            battlefield=["Mountain", "Mountain", "Grizzly Bears", "Hill Giant"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")

    casting = scenario.cast("Team Tactics")
    casting.pay_teamwork([giant])  # 3 power, Teamwork 1
    casting.choose_targets([bears])
    payment = casting.begin_paying()
    for source in scenario.untapped_sources("Mountain", "Mountain"):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert scenario.game.characteristics_of(bears).has_ability("Double strike")
    assert scenario.game.characteristics_of(bears).has_ability("Trample")


def test_team_tactics_without_teamwork_grants_only_double_strike():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice", hand=["Team Tactics"], battlefield=["Mountain", "Mountain", "Grizzly Bears"]
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    casting = scenario.cast("Team Tactics")
    casting.choose_targets([bears])
    payment = casting.begin_paying()
    for source in scenario.untapped_sources("Mountain", "Mountain"):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert scenario.game.characteristics_of(bears).has_ability("Double strike")
    assert not scenario.game.characteristics_of(bears).has_ability("Trample")


# --------------------------------------------------------------------------
# We Say Thee Nay!: "Counter target spell unless its controller pays {2}.
# Counter that spell unless its controller pays {4} instead if this spell
# was cast using teamwork." - the counter-unless-pay amount, overridden.
# --------------------------------------------------------------------------


def we_say_thee_nay_board() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["We Say Thee Nay!"],
            battlefield=["Island", "Island", "Grizzly Bears", "Hill Giant"],
        )
        .player("bob", hand=["Opt"], battlefield=["Island"])
    )


def test_we_say_thee_nay_without_teamwork_asks_for_2():
    scenario = we_say_thee_nay_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")  # bob needs priority to cast anything
    opt = scenario.cast_onto_stack("Opt", username="bob", auto=True)
    scenario.pass_priority("bob")

    scenario.will_pay_the_mana_cost(False, username="bob", source="We Say Thee Nay!")
    casting = scenario.cast("We Say Thee Nay!")
    casting.choose_targets([opt])
    payment = casting.begin_paying()
    for source in scenario.untapped_sources("Island", "Island"):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    asked = scenario.game.decisions.asked
    (decision,) = [
        q for q in asked if q.kind is DecisionKind.PAY_MANA and q.source == "We Say Thee Nay!"
    ]
    assert decision.amount == 2
    assert opt.zone is Zone.GRAVEYARD


def test_we_say_thee_nay_cast_using_teamwork_asks_for_4():
    scenario = we_say_thee_nay_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    scenario.pass_priority("alice")  # bob needs priority to cast anything
    opt = scenario.cast_onto_stack("Opt", username="bob", auto=True)
    scenario.pass_priority("bob")

    scenario.will_pay_the_mana_cost(False, username="bob", source="We Say Thee Nay!")
    casting = scenario.cast("We Say Thee Nay!")
    casting.pay_teamwork([bears, giant])  # 5 power, Teamwork 2
    casting.choose_targets([opt])
    payment = casting.begin_paying()
    for source in scenario.untapped_sources("Island", "Island"):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    asked = scenario.game.decisions.asked
    (decision,) = [
        q for q in asked if q.kind is DecisionKind.PAY_MANA and q.source == "We Say Thee Nay!"
    ]
    assert decision.amount == 4
    assert opt.zone is Zone.GRAVEYARD


# --------------------------------------------------------------------------
# Too Evil to Stay Dead: "Choose target creature card in your graveyard
# with mana value 4 or less. If this spell was cast using teamwork, instead
# choose target creature card in your graveyard. Return the chosen card to
# the battlefield." - target restriction swap, reanimation shared either way.
# --------------------------------------------------------------------------


def test_too_evil_to_stay_dead_without_teamwork_enforces_the_mana_value_cap():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Too Evil to Stay Dead"],
            battlefield=["Swamp", "Swamp", "Swamp"],
            graveyard=["Grizzly Bears"],  # mana value 2, legal unteamworked
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")

    casting = scenario.cast("Too Evil to Stay Dead")
    casting.choose_targets([bears])
    payment = casting.begin_paying()
    for source in scenario.untapped_sources("Swamp", "Swamp", "Swamp"):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bears.zone is Zone.BATTLEFIELD


def test_too_evil_to_stay_dead_cast_using_teamwork_lifts_the_mana_value_cap():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Too Evil to Stay Dead"],
            battlefield=["Swamp", "Swamp", "Swamp", "Grizzly Bears", "Hill Giant"],
            graveyard=["Serra Angel"],  # mana value 5 - illegal without teamwork
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    angel = scenario.find("Serra Angel", Zone.GRAVEYARD, "alice")

    casting = scenario.cast("Too Evil to Stay Dead")
    casting.pay_teamwork([bears, giant])  # 5 power, Teamwork 4
    casting.choose_targets([angel])
    payment = casting.begin_paying()
    for source in scenario.untapped_sources("Swamp", "Swamp", "Swamp"):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert angel.zone is Zone.BATTLEFIELD


# --------------------------------------------------------------------------
# Earth's Mightiest Heroes: "Reveal the top eight cards of your library. You
# may put a creature card from among them onto the battlefield. If this
# spell was cast using teamwork, put any number of creature cards from
# among them onto the battlefield instead. Put the rest into your
# graveyard."
# --------------------------------------------------------------------------


def earths_mightiest_board() -> Scenario:
    library = [
        "Grizzly Bears",
        "Hill Giant",
        "Elvish Mystic",
        "Llanowar Elves",
        "Mountain",
        "Island",
        "Swamp",
        "Plains",
    ]
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Earth's Mightiest Heroes"],
            battlefield=["Forest", "Forest", "Forest", "Forest", "Forest", "Forest"],
            library=library,
        )
    )


def test_earths_mightiest_heroes_without_teamwork_puts_only_one_creature_into_play():
    scenario = earths_mightiest_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    top_eight = scenario.top_of_library(8)
    bears = next(state for state in top_eight if state.name == "Grizzly Bears")

    scenario.will_take_the_may(True, username="alice", source="Earth's Mightiest Heroes")
    scenario.will_choose_cards(bears, username="alice", source="Earth's Mightiest Heroes")
    casting = scenario.cast("Earth's Mightiest Heroes")
    payment = casting.begin_paying()
    for source in scenario.untapped_sources(
        "Forest", "Forest", "Forest", "Forest", "Forest", "Forest"
    ):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bears.zone is Zone.BATTLEFIELD
    other_creatures = [state for state in top_eight if state.is_creature and state.id != bears.id]
    assert all(state.zone is Zone.GRAVEYARD for state in other_creatures)


def test_earths_mightiest_heroes_cast_using_teamwork_puts_every_creature_into_play():
    library = [
        "Grizzly Bears",
        "Hill Giant",
        "Elvish Mystic",
        "Llanowar Elves",
        "Mountain",
        "Island",
        "Swamp",
        "Plains",
    ]
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Earth's Mightiest Heroes"],
            battlefield=[
                "Forest",
                "Forest",
                "Forest",
                "Forest",
                "Forest",
                "Forest",
                "Craw Wurm",  # 6/4, well past Teamwork 5 on its own
            ],
            library=library,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wurm = scenario.creature("Craw Wurm", "alice")
    top_eight = scenario.top_of_library(8)
    creatures_in_top_eight = [state for state in top_eight if state.is_creature]

    scenario.will_choose_cards(
        *creatures_in_top_eight, username="alice", source="Earth's Mightiest Heroes"
    )
    casting = scenario.cast("Earth's Mightiest Heroes")
    casting.pay_teamwork([wurm])
    payment = casting.begin_paying()
    for source in scenario.untapped_sources(
        "Forest", "Forest", "Forest", "Forest", "Forest", "Forest"
    ):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    for state in creatures_in_top_eight:
        assert state.zone is Zone.BATTLEFIELD
    noncreatures = [state for state in top_eight if not state.is_creature]
    assert all(state.zone is Zone.GRAVEYARD for state in noncreatures)
