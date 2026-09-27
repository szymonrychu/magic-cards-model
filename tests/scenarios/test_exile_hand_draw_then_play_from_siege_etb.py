"""Invasion of Kaldheim's Siege ETB: "exile all cards from your hand, then
draw that many cards. Until the end of your next turn, you may play cards
exiled this way." - the identical instruction chain `test_hex_magic.py`
already proves on Hex Magic's own spell text, this time as a triggered
ability, with a real, differently-worded printing of the leading sentence.

Card text, confirmed with `resolve_cards` in the session that wrote this
file:

Invasion of Kaldheim (Battle - Siege, defense 4):
    When this Siege enters, exile all cards from your hand, then draw that
    many cards. Until the end of your next turn, you may play cards exiled
    this way.

Hex Magic (Sorcery, Modern legal):
    Exile all the cards from your hand, then draw that many cards. Until
    the end of your next turn, you may play cards exiled this way.

"all the cards" (Hex Magic) vs. "all cards" (Invasion of Kaldheim, no
"the") - a real, structurally different printing of the same instruction,
and it was not readable before this session: `_EXILE_HAND_DRAW_THEN_PLAY_
UNTIL_NEXT_TURN_RE` (`machines/effects.py`) matched only "all the cards"/
"all of the cards", so Kaldheim's own wording fell through it entirely, and
- separately - the whole shape was only ever read as a *spell* effect
(`effect_for`), never as a *triggered ability*'s (`trigger_effect_for`),
which a Siege's own printed "When this Siege enters, ..." always is. Both
gaps are closed generally: the regex now accepts "the" being absent, and
`_parse_exile_hand_draw_then_play_until_next_turn_ability_clause` shares the
identical `_exile_hand_draw_then_play_until_next_turn` implementation Hex
Magic's own spell reader already used - see that function's own docstring.

CR numbers looked up with `mise run rules:find` in the session that wrote
this file: CR 601.3, CR 611.2a, CR 121.1 (draw), CR 608.2c (the "then").
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

KALDHEIM = "Invasion of Kaldheim"


def test_the_hand_is_exiled_and_that_many_cards_are_drawn_with_play_permission():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[KALDHEIM, "Lightning Bolt", "Grizzly Bears"],
            library=["Mountain"] * 6,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.put_onto_battlefield(KALDHEIM, "alice")
    scenario.pass_until_resolved()  # the Siege's own ETB

    alice = scenario.player("alice")
    bolt = scenario.find("Lightning Bolt", Zone.EXILE)
    bears = scenario.find("Grizzly Bears", Zone.EXILE)
    assert bolt.zone is Zone.EXILE
    assert bears.zone is Zone.EXILE
    # Two cards exiled (Lightning Bolt, Grizzly Bears - Invasion of Kaldheim
    # itself was already on the battlefield, not in hand, when this
    # counted), so two drawn.
    assert len(alice.hand) == 2
    assert all(card.name == "Mountain" for card in alice.hand)

    permission = scenario.game.play_permissions
    granted_ids = {granted.card_id for granted in permission}
    assert bolt.id in granted_ids
    assert bears.id in granted_ids
