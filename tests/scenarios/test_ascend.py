"""Ascend and the city's blessing (CR 702.131), through Ocelot Pride:

    First strike, lifelink
    Ascend (If you control ten or more permanents, you get the city's
    blessing for the rest of the game.)
    At the beginning of your end step, if you gained life this turn, create a
    1/1 white Cat creature token. Then if you have the city's blessing, for
    each token you control that entered this turn, create a token that's a
    copy of it.

Every rule cited here was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 702.131b** - "Ascend on a permanent represents a static ability. It
  means 'Any time you control ten or more permanents and you don't have the
  city's blessing, you get the city's blessing for the rest of the game.'"
- **CR 702.131c** - "The city's blessing is a designation that has no rules
  meaning other than to act as a marker that other rules and effects can
  identify." Nothing in the rules ever takes it away.
- **CR 702.131a** - ascend on an instant or sorcery is a spell ability
  instead, checked once as the spell resolves. Not modelled: nothing in the
  card pool prints ascend on a non-permanent.
- **CR 603.4, CR 608.2a** - the intervening *if* ("if you gained life this
  turn") that gates whether the whole ability triggers at all.
- **CR 608.2c** - "The controller of the spell or ability follows its
  instructions in the order written" - what makes "if you have the city's
  blessing" (mid-effect, not the ability's own intervening *if*) an ordinary
  conditional instruction, and what forbids running one sentence of this
  ability while dropping the other.
- **CR 707.2** - a token copy "acquires the copiable values of the original
  object's characteristics" - what makes a copy of a Cat token itself a 1/1
  white Cat.

This project's engine used to keep a `TRIGGER_EFFECTS` row for this ability
specifically so the second sentence could be silently dropped while the first
still ran every turn - a real game hit exactly that bug: a player with 11+
permanents got one Cat a turn instead of the doubling ascend promises, with no
notice anywhere. The row is gone now that ascend, the city's blessing, and
"entered this turn" tracking are all built (see
`tests/scenarios/test_token_effect_parser.py` for the parser-level proof that
the whole paragraph reads as one ability). This file is the mechanic end to
end, and the corner cases are the point of it.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models.card import Color
from tests.scenarios.harness import Scenario


def _cats(scenario, username: str = "alice") -> list:
    return [
        state
        for state in scenario.game.permanents_controlled_by(username)
        if state.name == "Cat Token"
    ]


# --------------------------------------------------------------------------
# CR 702.131b: exactly nine, exactly ten, eleven or more permanents
# --------------------------------------------------------------------------


def test_nine_permanents_does_not_grant_the_blessing():
    """CR 702.131b's threshold is "ten or more" - nine is not enough, however
    often the check runs."""
    scenario = Scenario().player("alice", battlefield=["Ocelot Pride", *["Plains"] * 8]).build()
    assert len(scenario.game.permanents_controlled_by("alice")) == 9
    scenario.game.check_state_based_actions()
    assert scenario.player("alice").has_citys_blessing is False


def test_ten_permanents_grants_the_blessing():
    """Ocelot Pride itself counts toward its own "ten or more permanents" -
    nothing in CR 702.131b excludes the permanent ascend is printed on."""
    scenario = Scenario().player("alice", battlefield=["Ocelot Pride", *["Plains"] * 9]).build()
    assert len(scenario.game.permanents_controlled_by("alice")) == 10
    scenario.game.check_state_based_actions()
    assert scenario.player("alice").has_citys_blessing is True


def test_eleven_or_more_permanents_grants_the_blessing():
    scenario = Scenario().player("alice", battlefield=["Ocelot Pride", *["Plains"] * 10]).build()
    assert len(scenario.game.permanents_controlled_by("alice")) == 11
    scenario.game.check_state_based_actions()
    assert scenario.player("alice").has_citys_blessing is True


def test_the_blessing_persists_after_dropping_back_under_ten():
    """CR 702.131c: the city's blessing is a designation, and nothing in the
    rules ever takes it away - dropping back under ten permanents does not
    lose it, unlike a static continuous effect that would stop applying the
    moment its condition goes false.
    """
    scenario = Scenario().player("alice", battlefield=["Ocelot Pride", *["Plains"] * 9]).build()
    scenario.game.check_state_based_actions()
    assert scenario.player("alice").has_citys_blessing is True

    # Sacrifice lands until only Ocelot Pride itself is left - eight
    # permanents down to one, well under the threshold.
    for land in list(scenario.game.permanents_controlled_by("alice")):
        if land.name == "Plains":
            scenario.game.sacrifice(land)
    assert len(scenario.game.permanents_controlled_by("alice")) == 1

    scenario.game.check_state_based_actions()
    assert scenario.player("alice").has_citys_blessing is True


def test_a_player_without_ascend_never_gets_the_blessing():
    """Ten-plus permanents alone is not enough - CR 702.131b's static ability
    has to be granted by something the player controls. Bob controls plenty of
    permanents and no ascend anywhere.
    """
    scenario = Scenario().player("bob", battlefield=["Plains"] * 10).build()
    assert len(scenario.game.permanents_controlled_by("bob")) == 10
    scenario.game.check_state_based_actions()
    assert scenario.player("bob").has_citys_blessing is False


# --------------------------------------------------------------------------
# The intervening *if* still gates the whole ability (regression: CR 603.4)
# --------------------------------------------------------------------------


def test_no_life_gained_means_no_trigger_at_all_even_with_the_blessing():
    """The blessing does not create a trigger of its own - "if you gained life
    this turn" still has to hold before anything in this ability runs, cats
    included. A genuine zero: no life gained this turn, so nothing on the
    stack and no tokens of any kind, even though alice already has the
    blessing.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ocelot Pride", *["Plains"] * 9])
        .player("bob")
        .manual_turn_based_actions()
        .build()
    )
    scenario.game.check_state_based_actions()
    assert scenario.player("alice").has_citys_blessing is True

    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.advance()  # the end step begins

    assert scenario.game.stack_is_empty
    assert scenario.pending_triggers == []
    assert _cats(scenario) == []


# --------------------------------------------------------------------------
# The second sentence: tokens that entered this turn, copied (CR 707.2)
# --------------------------------------------------------------------------


def test_without_the_blessing_only_the_cat_is_created():
    """Fewer than ten permanents: the first sentence still runs (regression -
    see `test_tokens.py::test_ocelot_pride_creates_a_cat_at_the_end_step`), and
    the second is a no-op because "if you have the city's blessing" is false -
    an ordinary conditional instruction (CR 608.2c), not a second intervening
    *if* that would have stopped the whole ability from triggering.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ocelot Pride"])
        .player("bob")
        .manual_turn_based_actions()
        .build()
    )
    scenario.game.check_state_based_actions()
    assert scenario.player("alice").has_citys_blessing is False

    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.gain_life("alice", 1)
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.advance()  # the end step begins
    while scenario.game.stack:
        scenario.resolve_top()

    assert len(_cats(scenario)) == 1


def test_with_the_blessing_the_new_cat_is_doubled():
    """Ten-plus permanents and life gained this turn: both sentences run. The
    Cat the first sentence just created "entered this turn" (`turn_entered`
    was stamped the moment `create_tokens` put it on the battlefield through
    `Game.enter_the_battlefield`), so the second sentence's "for each token
    you control that entered this turn" counts it and creates one copy
    (CR 707.2) - two Cats total from one trigger, not one.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ocelot Pride", *["Plains"] * 9])
        .player("bob")
        .manual_turn_based_actions()
        .build()
    )
    scenario.game.check_state_based_actions()
    assert scenario.player("alice").has_citys_blessing is True

    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.gain_life("alice", 1)
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.advance()  # the end step begins
    while scenario.game.stack:
        scenario.resolve_top()

    cats = _cats(scenario)
    assert len(cats) == 2
    for cat in cats:
        assert (cat.power, cat.toughness) == (1, 1)
        assert cat.card.colors == [Color.WHITE]


def test_a_cat_from_an_earlier_turn_is_not_copied():
    """ "Entered this turn" means *this* turn - the Cats a previous end step
    created keep the turn number they were stamped with (`CardState.turn_entered`,
    set once in `Game.enter_the_battlefield`), so a later end step's "for each
    token you control that entered this turn" does not fold them back in and
    copy them again.

    `Game.advance()`, not `start_at`, walks real turns here (the same
    convention `test_intervening_if.py::test_life_gained_last_turn_does_not_carry_into_this_turn`
    uses) so `turns_taken` genuinely changes between the two end steps this
    test checks.
    """
    scenario = (
        Scenario()
        .player("alice", library=["Forest"], battlefield=["Ocelot Pride", *["Plains"] * 9])
        .player("bob", library=["Forest"])
        .manual_turn_based_actions()
        .build()
    )
    scenario.game.check_state_based_actions()
    assert scenario.player("alice").has_citys_blessing is True

    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.gain_life("alice", 1)
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.advance()  # alice's first end step
    while scenario.game.stack:
        scenario.resolve_top()

    # The blessing was already held, so turn one's Cat is immediately
    # doubled: one from the trigger, one copy of it.
    assert len(_cats(scenario)) == 2
    first_turn_cat_ids = {cat.id for cat in _cats(scenario)}

    for _ in range(40):
        if scenario.game.turn.active_player == "alice" and scenario.step is Step.POSTCOMBAT_MAIN:
            break
        scenario.advance()
    else:
        raise AssertionError("never made it back to alice's postcombat main")

    scenario.game.gain_life("alice", 1)
    scenario.advance()  # alice's second end step
    while scenario.game.stack:
        scenario.resolve_top()

    # Two more Cats from turn two - the new one and its copy - not four:
    # turn one's pair is untouched by this end step's count.
    cats = _cats(scenario)
    assert len(cats) == 4
    assert first_turn_cat_ids <= {cat.id for cat in cats}


def test_two_ocelot_prides_each_copy_everything_that_entered_this_turn():
    """Two Ocelot Prides both trigger at the same end step (CR 603.3b's APNAP
    order - one controller here, so alice orders her own two triggers however
    she likes) and resolve one at a time (CR 608.2c has no notion of
    resolving them together). Each ability's "for each token ... that entered
    this turn" is read fresh, at the moment *that* ability resolves - so the
    second Ocelot Pride's trigger sees and copies everything the first one's
    already put on the battlefield this turn, cats and copies alike.

    Whichever ability resolves first: it creates one Cat, then copies the one
    token that has entered this turn so far (itself) - two tokens. The second
    ability then creates its own Cat (three tokens have now entered this
    turn) and copies all three - three more tokens. Six new Cats in total,
    regardless of which Ocelot Pride's trigger happens to resolve first.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Ocelot Pride", "Ocelot Pride", *["Plains"] * 8],
        )
        .player("bob")
        .manual_turn_based_actions()
        .build()
    )
    scenario.game.check_state_based_actions()
    assert scenario.player("alice").has_citys_blessing is True

    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.gain_life("alice", 1)
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.advance()  # the end step begins
    assert len(scenario.stack_names()) == 2

    while scenario.game.stack:
        scenario.resolve_top()

    assert len(_cats(scenario)) == 6
