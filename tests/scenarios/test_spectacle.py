"""Spectacle: an alternative cost unlocked by an opponent's life loss (CR 702.137).

Read whole in this session with `mise run rules:find 702.137` (rules effective
September 25, 2026):

- **CR 702.137a** - "Spectacle is a static ability that functions on the
  stack. 'Spectacle [cost]' means 'You may pay [cost] rather than pay this
  spell's mana cost if an opponent lost life this turn.' Casting a spell for
  its spectacle cost follows the rules for paying alternative costs in rules
  601.2b and 601.2f-h."

That condition is exactly `Player.life_lost_this_turn` (CR 119.2 damage, CR
118.3b a life cost, CR 701.12c an exchange's losing half - all already
counted there, proven in `test_life_lost_this_turn.py`), asked of every
player who is not the caster (`Game.spectacle_condition_holds`). Structurally
the same shape prowl (CR 702.76a, `test_prowl.py`) already has: a
`KeywordCastOption` with no zone permission of its own, gated by a `why_not`
condition read off the board rather than off a printed count.

Light Up the Stage and Skewer the Critics (Rivals of Ixalan, Modern and
Pioneer legal) are the two required proof printings - a card-advantage
sorcery and a burn sorcery, so the same keyword line drives two different
resolutions. Rix Maadi Reveler (Rivals of Ixalan too, Modern/Pioneer legal,
off pool and not one of the two required cards) proves the option is read
off the keyword rather than off either required card's own text: a creature
spell, with its own differently priced spectacle cost ({2}{B}{R} against a
{1}{R} mana cost, rather than {R} against {2}{R}). Its own triggered ability
("If this creature's spectacle cost was paid, instead discard your hand,
then draw three cards.") is a resolution-time conditional on a *permanent's*
own trigger, a different reader from spectacle's alternative-cost keyword
this file exercises (`_IF_KEYWORD_COST_PAID_RE` in `machines/effects.py` is
spell-only, CR 608.2c's business, not CR 702.137a's) - out of scope here, so
this file asserts only what spectacle itself governs: the option, its board
condition, and the mana actually paid.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import keyword_cast_options
from magic_cards_model.models import Zone
from magic_cards_model.models.mana import ManaCost
from tests.cards import card
from tests.scenarios.harness import Scenario

STAGE = "Light Up the Stage"
SKEWER = "Skewer the Critics"
REVELER = "Rix Maadi Reveler"


def board(hand: tuple[str, ...], *, alice_lands: int = 4) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            battlefield=["Mountain"] * alice_lands,
            hand=list(hand),
            library=["Island"] * 10,
        )
        .player("bob", library=["Island"] * 6)
        .build()
    )


# -- the option itself --------------------------------------------------


def test_spectacle_hands_out_an_alternative_cost_from_hand():
    (option,) = [o for o in keyword_cast_options(card(STAGE)) if o.keyword == "Spectacle"]
    assert option.zone is Zone.HAND
    assert option.rule == "CR 702.137a"
    assert not option.pays_mana_cost
    assert option.spectacle is True
    assert option.cost is not None and option.cost.mana == ManaCost.parse("{R}")


def test_spectacle_is_no_longer_an_ignored_keyword():
    from scripts.sweep_pool import ignored_keywords

    assert "Spectacle" not in ignored_keywords(card(STAGE))
    assert "Spectacle" not in ignored_keywords(card(SKEWER))
    assert "Spectacle" not in ignored_keywords(card(REVELER))


# -- unavailable until an opponent has lost life this turn --------------


def test_no_opponent_has_lost_life_spectacle_is_refused():
    scenario = board((STAGE,))
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast(STAGE)

    import pytest

    with pytest.raises(ValueError, match="lost life"):
        casting.use_keyword("Spectacle")


def test_the_casters_own_life_loss_does_not_count():
    """CR 702.137a says "an opponent" - the caster losing life is not that."""
    scenario = board((STAGE,))
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.player("alice").lose_life(6)
    casting = scenario.cast(STAGE)

    import pytest

    with pytest.raises(ValueError, match="lost life"):
        casting.use_keyword("Spectacle")


def test_an_opponents_life_loss_last_turn_does_not_carry_over():
    """ "This turn" means this one (CR 702.137a), the same clock
    `Player.life_lost_this_turn` already keeps."""
    scenario = board((STAGE,))
    bob = scenario.player("bob")
    bob.lose_life(3)
    # Two full turns (bob's, then alice's again) rather than one - `advance`
    # cycles the active player, and this needs alice back on the stack side
    # of a cast, the same round-trip `test_life_lost_this_turn.py`'s own
    # turn-boundary tests take one leg of.
    target_turns = scenario.turn.turns_taken + 2
    while scenario.turn.turns_taken < target_turns:
        scenario.advance()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert scenario.turn.active_player == "alice"
    assert scenario.game.spectacle_condition_holds("alice") is False

    casting = scenario.cast(STAGE, username="alice")

    import pytest

    with pytest.raises(ValueError, match="lost life"):
        casting.use_keyword("Spectacle")


# -- Light Up the Stage: cast for spectacle, exile-and-play ------------------


def test_light_up_the_stage_via_lightning_bolt_damage_then_spectacle():
    """A real damage source (Lightning Bolt), not a bare life-total edit, is
    what makes an opponent's life loss "this turn" for the first, primary
    proof of the mechanic."""
    scenario = board((STAGE, "Lightning Bolt"), alice_lands=5)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (bolt_source,) = scenario.untapped_sources("Mountain")
    scenario.cast_and_resolve("Lightning Bolt", bolt_source, targets=["bob"])
    assert scenario.player("bob").life == 17

    casting = scenario.cast(STAGE)
    casting.use_keyword("Spectacle")
    assert casting.total_cost.mana == ManaCost.parse("{R}")
    payment = casting.begin_paying()
    (source,) = scenario.untapped_sources("Mountain")
    scenario.pay_with(payment, source)
    stage = scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert stage.zone is Zone.GRAVEYARD
    # Every remaining Mountain stayed untapped: {R} was paid, not {2}{R}.
    mountains = scenario.game.permanents_controlled_by("alice")
    untapped = [state for state in mountains if state.name == "Mountain" and not state.tapped]
    assert len(untapped) == 3


def test_light_up_the_stage_cast_for_its_mana_cost_needs_no_life_loss():
    scenario = board((STAGE,), alice_lands=3)
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast(STAGE)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Mountain", "Mountain", "Mountain"))
    stage = scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert stage.zone is Zone.GRAVEYARD


# -- Skewer the Critics: cast for spectacle, deal damage ---------------------


def test_skewer_the_critics_via_spectacle_after_an_opponent_loses_life():
    scenario = board((SKEWER,))
    bob = scenario.player("bob")
    bob.lose_life(1)
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast(SKEWER)
    casting.use_keyword("Spectacle")
    casting.choose_targets(["bob"])
    assert casting.total_cost.mana == ManaCost.parse("{R}")
    payment = casting.begin_paying()
    (source,) = scenario.untapped_sources("Mountain")
    scenario.pay_with(payment, source)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bob.life == 20 - 1 - 3


def test_skewer_the_critics_spectacle_is_available_mid_combat_too():
    """Spectacle names no timing restriction of its own (CR 702.137a) - unlike
    prowl's own declare-blockers window, so a sorcery's ordinary timing
    (CR 117.1a) is the only limit and this simply proves the keyword adds
    none of its own on top."""
    scenario = board((SKEWER,))
    bob = scenario.player("bob")
    bob.lose_life(2)
    scenario.start_at(Step.DECLARE_ATTACKERS)

    import pytest

    with pytest.raises(ValueError, match="main phase"):
        # Refused for being a sorcery outside a main phase (CR 117.1a,
        # 702.8a) - spectacle does not waive that, it only changes the cost,
        # and CR 601.2 announcement refuses the cast before any keyword is
        # even chosen.
        scenario.cast(SKEWER, targets=["bob"])


# -- Rix Maadi Reveler: the keyword generalises off a second, off-pool card --


def test_rix_maadi_reveler_spectacle_option_reads_its_own_cost():
    (option,) = [o for o in keyword_cast_options(card(REVELER)) if o.keyword == "Spectacle"]
    assert option.zone is Zone.HAND
    assert option.cost is not None and option.cost.mana == ManaCost.parse("{2}{B}{R}")


def test_rix_maadi_reveler_cast_for_spectacle_pays_its_own_cost_and_resolves():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Mountain", "Mountain", "Swamp", "Swamp"],
            hand=[REVELER],
            library=["Island"] * 8,
        )
        .player("bob", library=["Island"] * 6)
        .build()
    )
    bob = scenario.player("bob")
    bob.lose_life(4)
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast(REVELER)
    casting.use_keyword("Spectacle")
    assert casting.total_cost.mana == ManaCost.parse("{2}{B}{R}")
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Mountain", "Mountain", "Swamp", "Swamp"))
    reveler = scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert reveler.zone is Zone.BATTLEFIELD
