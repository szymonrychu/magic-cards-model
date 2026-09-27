"""Song of Totentanz: "Create X 1/1 black Rat creature tokens with 'This
token can't block.' Creatures you control gain haste until end of turn." -
CR 107.3a's announced X, CR 111.1's token creation with a quoted granted
ability, and CR 702.10a's haste, all in one sentence
`machines/spell_texts_r0a.py`'s `parse_token_with_quoted_ability_then_rest_
clause` reads whole (the quoted ability's own closing period sits inside the
quote, so `split_effect_clauses`'s ordinary sentence split never separates
the token clause from the haste grant that follows it).

Ogre Chitterlord (Modern/Pioneer/Standard-legal, not this task's own card,
not in the deck pool) is the generalisation proof: the identical quote-then-
more-text shape on a *triggered ability* rather than a spell, with a fixed
count rather than X.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 111.1** - "A token is a marker used to represent a permanent that
  isn't represented by a card."
- **CR 107.3a** - "If an object's cost or effect uses a variable, ... its
  value is determined by the appropriate player as the object is cast."
- **CR 702.10a** - "Haste is a static ability... A permanent with haste
  ignores the timing restriction ... that's normally applied to abilities
  with the tap symbol or the untap symbol in their activation costs, as well
  as the restriction that a player can't attack with it unless they've
  controlled it continuously since their most recent turn began."
- **CR 509.1b** - "This token can't block" is a restriction, read the same
  way for a token as for any other creature.
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def test_song_of_totentanz_creates_x_rat_tokens_that_cant_block():
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Song of Totentanz"], battlefield=["Mountain", "Mountain", "Mountain"]
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Song of Totentanz")
    casting.determine_cost(x_value=2)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Mountain", "Mountain", "Mountain"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    rats = [state for state in scenario.game.battlefield if state.token and "Rat" in state.name]
    assert len(rats) == 2
    for rat in rats:
        chars = scenario.game.characteristics_of(rat)
        assert chars.power == 1
        assert chars.toughness == 1
        assert "This token can't block." in chars.abilities


def test_song_of_totentanz_gives_creatures_you_control_haste():
    """A freshly-created Rat (summoning sick, CR 302.6) can attack the same
    turn it entered - CR 702.10a's own exemption - once the same resolution
    grants haste."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Song of Totentanz"],
            battlefield=["Mountain", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Song of Totentanz")
    casting.determine_cost(x_value=1)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Mountain", "Mountain"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    (rat,) = [state for state in scenario.game.battlefield if state.token and "Rat" in state.name]
    assert rat.summoning_sick

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(rat)
    assert scenario.attackers() == [rat]


def test_ogre_chitterlord_creates_rat_tokens_off_pool():
    """Ogre Chitterlord's own attack trigger: "create two 1/1 black Rat
    creature tokens with 'This token can't block.' Then if you control five
    or more Rats, each Rat you control gets +2/+0 until end of turn." - a
    fixed count, no X, and a trailing conditional rider this reader also
    composes."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ogre Chitterlord"], library=["Forest"] * 10)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    chitterlord = scenario.creature("Ogre Chitterlord", "alice")
    chitterlord.summoning_sick = False
    scenario.attack_with(chitterlord)
    scenario.game._before_priority()  # CR 603.3: stack the attack trigger
    scenario.resolve_top()

    rats = [state for state in scenario.game.battlefield if state.token and "Rat" in state.name]
    assert len(rats) == 2
    for rat in rats:
        chars = scenario.game.characteristics_of(rat)
        assert "This token can't block." in chars.abilities
