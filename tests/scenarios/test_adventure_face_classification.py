"""Adventure face classification (`support.py`'s `_spell_faces`).

CR 715.1: an adventurer card's inset Adventure half has its own name, mana
cost, and printed text, cast on its own (CR 715.3/715.3a) and read on the
stack as "only its alternative characteristics" (CR 715.3b). Before this
fix, `support._spell_faces` had no branch for `Layout.ADVENTURE`, so every
adventure face fell through to the "everything else" arm, which reads only
`printing.front_face` - the permanent creature half. The Adventure half's
printed text never reached `effect_for` as a spell clause at all; instead
`machines.abilities.parse_abilities` had already parsed it as a bare
`AbilityKind.STATIC` line (nothing on an instant/sorcery's own sentence
marks it triggered or activated), keyed to the Adventure face's own name via
`ability.face`, and `classify_clauses`' static-ability loop - gated only on
whether the *card* has a permanent type, true for every adventurer card -
picked it up and judged it as though it were a static ability of the
creature. `_static_ability_category` cannot parse spell resolution text as
a layer effect, so every adventure face in the pool read `static_unaudited`
regardless of whether `effect_for` could actually read it - Bonecrusher
Giant // Stomp's own "Stomp deals 2 damage to any target." included, even
though that exact sentence was already fully readable once routed through
the right dispatcher.

The fix has two parts, both in `support.py`:

1. `_spell_faces` grows a `Layout.ADVENTURE` branch (mirroring the existing
   `Layout.PREPARE` one): both faces are returned, each read off its own
   `card_faces` entry, so the Adventure half's own name/text/mana_cost reach
   `effect_for` as a real "[spell]" clause.
2. `spell_only_face_names` (which already excludes a modal DFC's own
   non-permanent back face from the static-ability loop, CR 712.11b) is
   widened to `Layout.ADVENTURE` too, so the Adventure face's now-`handled`
   spell clause is never scored a second time as an unaudited static line
   of the creature front.

`_card_description_is_readable` also gained a fix in the same pass, for a
bug the Arkenstone // Seek the Heart's own Adventure face exposed once
routed through `effect_for` at all: "Search your library for a legendary
creature card ..." matches `_SEARCH_AND_PUT_RE` and `_quality_matcher`
already reads "legendary creature" correctly (CR 205.4a's supertype
stacked on the card type), but the separate readability pre-check
(`_card_description_is_readable`) had never learned the same "legendary "/
"snow " prefixes `_quality_matcher` already special-cases, so the search
was sent to a `NOTICE`-worthy `SearchDescriptionNotice` even though the
search itself worked. Fixed by mirroring `_quality_matcher`'s own prefix
stacking.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 715.1** - "Adventurer cards have a two-part card frame ... The inset
  half is the one whose type line says Adventure."
- **CR 715.3** - "As a player plays an adventurer card, the player chooses
  whether they play the card normally or as an Adventure."
- **CR 715.3a** - casting an adventurer card as an Adventure evaluates
  only the alternative (Adventure) characteristics.
- **CR 715.3b** - "While on the stack as an Adventure, the spell has only its
  alternative characteristics."
- **CR 712.11b** - a modal double-faced card whose front is a permanent can
  still be cast as its instant or sorcery back face; that face's printed
  lines are its own resolution text, not a static ability of the front.
- **CR 205.4a** - "The supertypes are basic, legendary, ongoing, snow, and
  world."
- **CR 701.23a** - "To search for a card in a zone ... find a card that
  matches the given description."

Proof printings, both real Scryfall data added with `scripts/add_card.py`,
neither a listed card nor in any `magic-cards-model-api/decks/*.txt` list,
legality confirmed against the fetched Scryfall JSON (Modern/Pioneer/
Standard all `legal`):

- **Glamdring, Foe-hammer // Gleam of Death** - a second adventure card
  entirely outside this task's own list, whose Adventure half ("Mill six
  cards, then put all instant and sorcery cards from among them into your
  hand.") is a spell clause the same classifier bug would have misrouted.
- **The Seriema** (Modern/Pioneer/Standard legal) - not an adventure card at
  all, proving the `_card_description_is_readable` fix generalizes past the
  one adventure face that exposed it: its own triggered ability prints the
  byte-identical "search your library for a legendary creature card, reveal
  it, put it into your hand, then shuffle." sentence.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import classify_clauses
from tests.cards import card
from tests.scenarios.harness import Scenario

ADVENTURE_CARDS = (
    "Bonecrusher Giant",
    "Bilbo Baggins, Burglar // Take a Glance",
    "Velvetwing Butterflies // Gaze in Wonder",
    "Most Decrepit Old Bird // Speak Secrets",
    "The Arkenstone // Seek the Heart",
    "Thranduil, Sindarin Liege // Silvan Rally",
    "Glamdring, Foe-hammer // Gleam of Death",
)


def test_every_adventure_faces_own_clauses_are_handled_not_static_unaudited():
    """No adventure card in the pool has its Adventure half's own printed
    text misfiled as an unaudited static ability of the creature front -
    every clause reads `handled` (Glamdring's own front-face cost-reduction
    static line is a separate, pre-existing gap unrelated to this fix, which
    is why it is excluded here rather than asserted against)."""
    for name in ADVENTURE_CARDS:
        outcomes = classify_clauses(card(name))
        assert outcomes, name
        spell_outcomes = [outcome for outcome in outcomes if outcome.source == "spell"]
        assert spell_outcomes, (name, outcomes)
        for outcome in spell_outcomes:
            assert outcome.category == "handled", (name, outcome)


def test_the_seriema_search_for_a_legendary_creature_card_also_reads():
    """Non-adventure proof that `_card_description_is_readable`'s own
    "legendary "/"snow " prefix fix generalizes past the one Adventure face
    that exposed it."""
    outcomes = classify_clauses(card("The Seriema"))
    search_outcomes = [outcome for outcome in outcomes if "search your library" in outcome.text]
    assert search_outcomes
    for outcome in search_outcomes:
        assert outcome.category == "handled", outcome


def test_casting_take_a_glance_scries_two():
    """Bilbo Baggins, Burglar // Take a Glance's Adventure half: "Scry 2."
    (CR 701.22a) actually resolves once dispatched through `effect_for`."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Bilbo Baggins, Burglar // Take a Glance"],
            battlefield=["Island"],
            library=["Grizzly Bears", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bears, mountain = alice.library[0], alice.library[1]
    scenario.scry_bottoming(bears, username="alice")
    (source,) = scenario.untapped_sources("Island")

    casting = scenario.cast("Bilbo Baggins, Burglar")
    casting.cast_as_adventure()
    assert casting.face == "Take a Glance"
    scenario.pay_with(casting.begin_paying(), source)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert alice.library[0] is mountain, "the scried-away Grizzly Bears went to the bottom"
    assert alice.library[-1] is bears


def test_casting_gaze_in_wonder_taps_two_target_creatures():
    """Velvetwing Butterflies // Gaze in Wonder's Adventure half: "Tap one or
    two target creatures." (CR 701.26a)."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice", hand=["Velvetwing Butterflies // Gaze in Wonder"], battlefield=["Plains"] * 2
        )
        .player("bob", battlefield=["Grizzly Bears", "Elvish Mystic"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    mystic = scenario.creature("Elvish Mystic", "bob")
    sources = scenario.untapped_sources("Plains", "Plains")

    casting = scenario.cast("Velvetwing Butterflies")
    casting.cast_as_adventure()
    assert casting.face == "Gaze in Wonder"
    casting.choose_targets([bears, mystic])
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bears.tapped
    assert mystic.tapped


def test_casting_seek_the_heart_finds_a_legendary_creature():
    """The Arkenstone // Seek the Heart's Adventure half: "Search your
    library for a legendary creature card, reveal it, put it into your
    hand, then shuffle." - exercising both fixes at once, on a listed card."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["The Arkenstone // Seek the Heart"],
            battlefield=["Plains"] * 3,
            library=["Grizzly Bears", "Bilbo Baggins, Burglar // Take a Glance"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bilbo = next(state for state in alice.library if "Bilbo" in state.name)
    scenario.will_choose_cards(bilbo, username="alice", source="Seek the Heart")
    sources = scenario.untapped_sources("Plains", "Plains", "Plains")

    casting = scenario.cast("The Arkenstone")
    casting.cast_as_adventure()
    assert casting.face == "Seek the Heart"
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bilbo in alice.hand
    assert bilbo.zone is Zone.HAND
