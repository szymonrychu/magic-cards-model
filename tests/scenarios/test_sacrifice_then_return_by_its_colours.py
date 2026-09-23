"""Bound (Bound // Determined): "Sacrifice a creature. Return up to X cards
from your graveyard to your hand, where X is the number of colors that
creature was. Exile this card." - `_parse_mandatory_sacrifice_then_return_to_
hand_clause` in `machines/effects.py`.

Three CR 608.2c instructions that share one referent and end in a
non-default zone:

- "Sacrifice a creature" is a mandatory action (no "may", no "if you do") -
  `_sacrifice_restriction`'s own general "a `<type>`" grammar, reused rather
  than duplicated.
- "Return up to X cards ... where X is the number of colors that creature
  was" is CR 400.7 anaphora back to whatever the first sentence just
  sacrificed, fixed at CR 608.2h's moment (the creature has already left the
  battlefield by the time this second sentence asks about its colours) -
  `CardState.last_known_colors`, falling back to `CardState.colors` when no
  continuous effect ever made those differ.
- "Exile this card" (CR 201.5's self-reference) replaces CR 608.2n's default
  graveyard step for this resolving spell.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 701.21a** - "To sacrifice a permanent, its controller moves it from
  the battlefield directly to its owner's graveyard." Bound has already
  chosen a target-free "a creature", so this is the controller's own choice
  among creatures they control.
- **CR 609.3** - "If an effect attempts to do something impossible, it does
  only as much as possible" - a mandatory sacrifice with no legal creature
  sacrifices nothing rather than failing the whole spell.
- **CR 608.2h** - "If the effect requires information from a specific
  object ... if it's no longer in that [public] zone ... the effect uses the
  object's last known information." The colour count is read as the
  creature last had it on the battlefield, not as a graveyard card computes
  now.
- **CR 105.2/202.2** - an object's colour count: how many of the five
  colours it is.
- **CR 608.2d** - the "up to X" choice of which graveyard cards return is
  made as the effect resolves, and the sacrificed creature - now sitting in
  the graveyard - is as legal a choice as anything else there.
- **CR 201.5** - "Text that refers to the object it's on by name means just
  that particular object" - "Exile this card" names the resolving spell
  itself.
- **CR 608.2n** - the instant/sorcery-to-graveyard default this "Exile this
  card" replaces.

No off-pool proof card exists for the exact "the number of colors that
`<X>` was" expression: a live Scryfall `o:/number of colors.{0,40}was/`
search (this session) returns exactly two cards in all of Magic's history -
Bound // Determined itself and Jared Carthalion, a silver-border card legal
in none of Standard, Pioneer, or Modern. `docs/engine-coverage.md` carries
the documented exemption this earns, the same kind D2/T12 already carries
for Veil of Summer's player hexproof-from. The *readers this shape composes
from* are each proven generally elsewhere: `_sacrifice_restriction`
(mandatory-sacrifice's own type grammar) already has its own off-pool
proofs (Grist, the Hunger Tide; Sanctum of Ugin), and `_is_referent_power_
expression`'s sibling shape is proven on Disciple of Freyalise.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

BOUND = "Bound"


def board(**kwargs) -> Scenario:
    return Scenario().manual_turn_based_actions().player("alice", **kwargs).player("bob")


def test_sacrificing_a_two_colour_creature_returns_up_to_two_chosen_cards():
    """Putrid Leech is B/G - two colours - so X = 2. The player chooses two
    of the (now three) graveyard cards: Grizzly Bears, already there, and
    Putrid Leech itself, which the first sentence just put there (CR
    608.2d: the sacrificed creature is a legal choice for the second
    sentence, since it is sitting right in the graveyard by the time that
    sentence runs)."""
    scenario = board(
        hand=["Bound // Determined"],
        battlefield=["Putrid Leech", "Swamp", "Swamp", "Forest", "Forest", "Forest"],
        graveyard=["Grizzly Bears"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    leech = scenario.creature("Putrid Leech", username="alice")
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")

    # First CHOOSE_CARDS: which creature to sacrifice - only Putrid Leech is
    # a legal candidate, but CR 701.21a's choice is still asked.
    scenario.will_choose_cards(leech, source=BOUND)
    # Second CHOOSE_CARDS: which up-to-two graveyard cards return to hand -
    # both, including the creature the first sentence just sacrificed.
    scenario.will_choose_cards(leech, bears, source=BOUND)

    bound = scenario.cast_and_resolve(BOUND, username="alice", auto=True)

    assert leech.zone is Zone.HAND
    assert bears.zone is Zone.HAND
    assert leech in alice.hand
    assert bears in alice.hand
    assert bound.zone is Zone.EXILE  # CR 201.5/608.2n - never the graveyard
    assert bound not in alice.graveyard


def test_sacrificing_a_colourless_creature_returns_nothing():
    """Ornithopter has no colour (CR 105.2c) - {0}, no colour indicator - so
    X = 0 and "up to zero" is never even asked (CR 608.2d offers no choice
    with nothing to choose from). The pre-existing graveyard card, and the
    now-sacrificed Ornithopter, both stay right where they are."""
    scenario = board(
        hand=["Bound // Determined"],
        battlefield=["Ornithopter", "Swamp", "Swamp", "Forest", "Forest", "Forest"],
        graveyard=["Grizzly Bears"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    thopter = scenario.creature("Ornithopter", username="alice")
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")

    scenario.will_choose_cards(thopter, source=BOUND)

    bound = scenario.cast_and_resolve(BOUND, username="alice", auto=True)

    assert thopter.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.GRAVEYARD
    assert thopter in alice.graveyard
    assert bears in alice.graveyard
    assert not alice.hand
    assert bound.zone is Zone.EXILE  # exiled even when nothing came back
    assert bound not in alice.graveyard


def test_with_no_legal_creature_bound_still_exiles_itself():
    """CR 609.3: an empty battlefield sacrifices nothing - not a refused
    cast (Bound names no target and no additional cost, so CR 601.2h never
    checks for one), and not a fizzle. The spell still resolves, still asks
    no CHOOSE_CARDS at all (no creature to choose, nothing to return), and
    still exiles itself."""
    scenario = board(
        hand=["Bound // Determined"],
        battlefield=["Swamp", "Swamp", "Forest", "Forest", "Forest"],
        graveyard=["Grizzly Bears"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")

    bound = scenario.cast_and_resolve(BOUND, username="alice", auto=True)

    assert bears.zone is Zone.GRAVEYARD
    assert not alice.hand
    assert bound.zone is Zone.EXILE
    assert bound not in alice.graveyard
