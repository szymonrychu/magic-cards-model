"""Companion's type-disjunction condition shape (CR 702.139a) - Kaheera, the
Orphanguard's own "Each creature card in your starting deck is a `<type>`,
`<type>`, ... or `<type>` card." - plus the CR 116.2g put-into-hand action.

Read whole in this session with `mise run rules:find`:

- **CR 702.139a** - "Companion is a keyword ability that functions outside
  the game. It's written as 'Companion-[Condition].' Before the game
  begins, you may reveal one card you own from outside the game with a
  companion ability whose condition is fulfilled by your starting deck. ...
  Once during the game, any time you have priority and the stack is empty,
  but only during a main phase of your turn, you may pay {3} and put that
  card into your hand. This is a special action that doesn't use the stack
  (see rule 116.2g)."
- **CR 702.139b** - "your starting deck" is the mainboard, after sideboard
  cards are set aside.
- **CR 116.2g** - the {3}, once-per-game special action itself.

`machines/companion.py`'s `_TYPE_DISJUNCTION_RE`/`companion_condition_
satisfied` is pre-existing, not work this task adds or widens, and already
has thorough dedicated coverage in `test_companion.py` (the deck-legality
half, including Kaheera's own positive and negative cases, and the CR
116.2g special action's every corner case: once per game, stack must be
empty, only in a main phase, no companion chosen). This file is this task's
own required-card coverage, kept to what `test_companion.py` does not
already prove for the type-disjunction shape specifically: a changeling
creature satisfying it through every creature type at once (CR 702.73a), a
deck with more than one offending creature, and one round of the CR 116.2g
action tied to Kaheera by name so this task's own required card is on
record exercising it, not only Kaheera's condition-checking half.
"""

from magic_cards_model.machines.turn import Step
from magic_cards_model.models import Deck
from tests.cards import card
from tests.scenarios.harness import Scenario

KAHEERA = "Kaheera, the Orphanguard"


def test_kaheeras_condition_is_the_type_disjunction_shape():
    from magic_cards_model.machines.companion import companion_condition_text

    condition = companion_condition_text(card(KAHEERA))

    assert condition == (
        "Each creature card in your starting deck is a Cat, Elemental, "
        "Nightmare, Dinosaur, or Beast card"
    )


def test_every_creature_satisfying_the_disjunction_is_legal():
    deck = Deck(
        mainboard={
            "Mountain": 20,
            "Plains": 16,
            "Ocelot Pride": 4,
            "Savannah Lions": 4,
            "Steppe Lynx": 4,
            "Elder Gargaroth": 4,
            "Questing Beast": 4,
            "Swords to Plowshares": 4,
        },
        companion=KAHEERA,
    )

    assert deck.companion_problems(card) == []


def test_a_changeling_creature_satisfies_every_disjunction_option_at_once():
    """CR 702.73a: "This ability works everywhere, even outside the game" -
    Fire-Belly Changeling is every creature type, Cat/Elemental/Nightmare/
    Dinosaur/Beast among them, off the pool and not one of the printings
    `test_companion.py` already exercises for Kaheera."""
    deck = Deck(
        mainboard={
            "Mountain": 20,
            "Plains": 16,
            "Fire-Belly Changeling": 4,
            "Savannah Lions": 4,
            "Steppe Lynx": 4,
            "Elder Gargaroth": 4,
            "Questing Beast": 4,
            "Swords to Plowshares": 4,
        },
        companion=KAHEERA,
    )

    assert deck.companion_problems(card) == []


def test_a_changeling_outcast_creature_also_satisfies_the_condition():
    """A second changeling printing, an aggressively costed one with no
    activated ability at all, so the disjunction is read off the creature's
    subtypes and not off anything else Fire-Belly Changeling happens to
    print."""
    deck = Deck(
        mainboard={
            "Mountain": 20,
            "Plains": 16,
            "Changeling Outcast": 4,
            "Savannah Lions": 4,
            "Steppe Lynx": 4,
            "Elder Gargaroth": 4,
            "Questing Beast": 4,
            "Swords to Plowshares": 4,
        },
        companion=KAHEERA,
    )

    assert deck.companion_problems(card) == []


def test_more_than_one_offending_creature_is_named_in_the_refusal():
    """CR 702.139a's condition fails on either Grizzly Bears (a Bear) or
    Runeclaw Bear (also a Bear, a second real off-pool printing of the exact
    same failure) - both are named, not just the first one found."""
    deck = Deck(
        mainboard={
            "Mountain": 20,
            "Plains": 16,
            "Grizzly Bears": 4,
            "Runeclaw Bear": 4,
            "Steppe Lynx": 4,
            "Questing Beast": 4,
            "Swords to Plowshares": 4,
        },
        companion=KAHEERA,
    )

    problems = deck.companion_problems(card)

    assert len(problems) == 1
    assert "Grizzly Bears" in problems[0]
    assert "Runeclaw Bear" in problems[0]


# -- CR 116.2g's special action, tied to Kaheera by name --------------------


def test_kaheera_is_paid_for_and_put_into_hand():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Mountain", "Mountain", "Mountain"],
            companion=KAHEERA,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain")

    kaheera = scenario.bring_companion_to_hand(*sources)

    assert kaheera.name == KAHEERA
    from magic_cards_model.models.zone import Zone

    assert kaheera.zone is Zone.HAND
    assert scenario.player("alice").companion_action_used is True
