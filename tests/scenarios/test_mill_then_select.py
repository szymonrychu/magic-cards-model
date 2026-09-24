""" "Mill N cards, then put [all/a/up to K] `<quality>` card(s) from among
them into your hand" (`_MILL_THEN_MAY_TAKE_FROM_MILLED_RE`,
`_mill_then_may_take_from_milled_runner`, `machines/effects.py`).

The reader already existed (Rapid Rescue's own "Mill two cards. You may put
a permanent card from among the milled cards into your hand.") but read only
three of the shapes real cards print:

1. **The separator.** Rapid Rescue's own full stop ("Mill two cards. You may
   put ...") was the only one the mill sentence could end with; Cantankerous
   Keepers, Most Decrepit Old Bird // Speak Secrets and Thranduil, Sindarin
   Liege // Silvan Rally all print the identical instruction as one comma-
   joined sentence ("mill four cards, then put ..."), which is CR 608.2c's
   same single instruction, only punctuated differently.
2. **The referent.** "from among the milled cards" was the only phrasing
   read; "from among them" (CR 400.7's identical anaphora, back to the cards
   the same sentence's own mill just made) is the wording all three of this
   task's own cards print.
3. **The quantity.** "all `<quality>` cards" (Cantankerous Keepers) has no
   printed count at all - CR 608.2d never asks a question, every card among
   the milled ones that fits simply goes. `QUANTITY`
   (`numbers.py`) has no "all" in its own shared grammar, so it is read as a
   dedicated `take_all` alternative ahead of `quantity_pattern`, never by
   widening that shared vocabulary every other quantity-reading template
   also uses.
4. **The list connective.** "instant and sorcery cards" (Glamdring, Foe-
   hammer // Gleam of Death, the proof card below) joins its two type words
   with a bare "and", not "and/or" - the group capture and its "or"
   normalisation only read the latter. A card cannot itself be both an
   instant and a sorcery (CR 300.1), so this "and" means the same inclusive
   either-type reading `_parse_card_group_alternatives` already builds for
   "or" - CR 205.3's list connective for the same purpose.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 701.17a** - "To mill a card, a player puts the top card of their
  library into their graveyard."
- **CR 400.7** - "from among them" names the cards the same instruction's
  own mill just made, not the graveyard generally.
- **CR 608.2d** - "put all `<quality>` cards" asks no question; "put up to
  two" is a range with no separate "may" needed; a bare "a card" needs a
  printed "you may" to be optional at all.
- **CR 300.1 / CR 205.2a** - the seven card types; a card cannot be two of
  them "and" at once, so a printed "and" between two type words in a
  selection is read the same inclusive way "or" already is.

Proof printing: **Glamdring, Foe-hammer // Gleam of Death** (real Scryfall
data, added with `scripts/add_card.py`, not a listed card, not in any
`magic-cards-model-api/decks/*.txt` list, Modern/Pioneer/Standard all
`legal`) - its Adventure half "Mill six cards, then put all instant and
sorcery cards from among them into your hand." exercises every one of the
four widenings above at once, on wording none of this task's own three
cards print.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_cantankerous_keepers_mills_four_and_takes_all_elves():
    """ "put all Elf cards from among them into your hand" - CR 608.2d's no-
    choice "all", over a creature subtype rather than a card type."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Cantankerous Keepers"],
            battlefield=["Forest"] * 6,
            library=["Elvish Mystic", "Lightning Bolt", "Llanowar Elves", "Opt"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    mystic, bolt, llanowar, opt = alice.library
    sources = scenario.untapped_sources(*(["Forest"] * 6))

    scenario.cast_and_resolve("Cantankerous Keepers", *sources)
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()

    assert mystic in alice.hand
    assert llanowar in alice.hand
    assert bolt in alice.graveyard
    assert opt in alice.graveyard
    assert alice.library == []


def test_speak_secrets_mills_four_and_takes_the_one_instant_or_sorcery():
    """Most Decrepit Old Bird // Speak Secrets: "put an instant or sorcery
    card from among them into your hand" - CR 608.2d's mandatory single pick,
    no printed "you may" at all."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Most Decrepit Old Bird // Speak Secrets"],
            battlefield=["Island"] * 2,
            library=["Grizzly Bears", "Lightning Bolt", "Forest", "Elvish Mystic"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bears, bolt, forest, mystic = alice.library
    sources = scenario.untapped_sources("Island", "Island")

    casting = scenario.cast("Most Decrepit Old Bird")
    casting.cast_as_adventure()
    assert casting.face == "Speak Secrets"
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bolt in alice.hand, "the only instant/sorcery among the milled cards"
    assert bears in alice.graveyard
    assert forest in alice.graveyard
    assert mystic in alice.graveyard


def test_silvan_rally_mills_four_and_takes_up_to_two_lands():
    """Thranduil, Sindarin Liege // Silvan Rally: "put up to two land cards
    from among them into your hand" - CR 107.1c's own range, choosing fewer
    than the ceiling when fewer qualify."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Thranduil, Sindarin Liege // Silvan Rally"],
            battlefield=["Forest"] * 4,
            library=["Mountain", "Grizzly Bears", "Lightning Bolt", "Opt"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    mountain, bears, bolt, opt = alice.library
    scenario.will_choose_cards(mountain, username="alice", source="Silvan Rally")
    sources = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest")

    casting = scenario.cast("Thranduil, Sindarin Liege")
    casting.cast_as_adventure()
    assert casting.face == "Silvan Rally"
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert mountain in alice.hand, "the only land among the milled cards"
    assert bears in alice.graveyard
    assert bolt in alice.graveyard
    assert opt in alice.graveyard


def test_glamdring_mills_six_and_takes_every_instant_and_sorcery():
    """Proof card, off this task's own list: "Mill six cards, then put all
    instant and sorcery cards from among them into your hand." - the bare
    "and" list connective, a comma-joined sentence, and "from among them",
    all three at once."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Glamdring, Foe-hammer // Gleam of Death"],
            battlefield=["Island"] + ["Mountain"] * 3,
            library=[
                "Lightning Bolt",
                "Opt",
                "Grizzly Bears",
                "Elvish Mystic",
                "Forest",
                "Mountain",
            ],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bolt, opt, bears, mystic, forest, extra_mountain = alice.library
    sources = scenario.untapped_sources("Island", "Mountain", "Mountain", "Mountain")

    casting = scenario.cast("Glamdring, Foe-hammer")
    casting.cast_as_adventure()
    assert casting.face == "Gleam of Death"
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bolt in alice.hand, "an instant"
    assert opt in alice.hand, "a sorcery"
    for card_state in (bears, mystic, forest, extra_mountain):
        assert card_state.zone is Zone.GRAVEYARD
    assert alice.library == []
