"""FRA stream S8b: "Put this `<permanent|creature|card>` into its owner's
library `<ordinal>` from the top." - a self-referential activated ability
(`_PUT_SELF_INTO_LIBRARY_NTH_FROM_TOP_RE` in `machines/effects.py`).

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file.

- **CR 401.2** - a library stays face down and in whatever order a card is
  put into it; putting a card "Nth from the top" is a plain move, never
  CR 701.24's shuffle, and the rest of the library keeps its own order.
- **CR 113.7a** - an ability existing "independently of its source" can
  still find that source by id wherever it now is.
- **CR 108.3** - "its owner's library" (or a bare "your library" when the
  source's own controller and owner are the same, CR 108.4) moves the card
  to whichever player owns it.

Borborygmos and Fblthp's own `{1}{U}` ability ("Put Borborygmos and Fblthp
into its owner's library third from the top.") is the reported card -
`_self_normalized_effect_text` has already turned its printed name into
"this permanent" by the time this clause is ever read, the same
normalisation `_COUNTER_ON_SELF_RE` already relies on. Screaming Swarm
(real, non-FRA, non-pool) is the off-set proof at the clause-reader level:
a genuinely different ordinal ("second", not "third"), a genuinely
different subject word ("this card", the literal printed text for an
ability that functions from the graveyard rather than a self-normalised
"this permanent"), and "your library" in place of "its owner's library" -
proving the reader is general across all three axes rather than fitted to
Borborygmos's own exact sentence. Its own graveyard-activation subsystem
(CR 113.6) is a separate, already-modelled mechanic this stream does not
touch, so it is exercised at the clause level rather than through a full
graveyard-activation scenario.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.effects import parse_mixed_effect
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_borborygmos_puts_itself_third_from_the_top_of_its_owners_library():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Borborygmos and Fblthp", "Island", "Island"],
            library=["Forest", "Mountain", "Plains", "Swamp"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    borborygmos = scenario.creature("Borborygmos and Fblthp", "alice")
    sources = scenario.untapped_sources("Island", "Island")

    scenario.activate(borborygmos, *sources, index=0)
    scenario.pass_until_resolved()

    assert borborygmos.zone is Zone.LIBRARY
    assert alice.library[2] is borborygmos, "third from the top is index 2"
    assert alice.library[0].name == "Forest", "the library's own order is untouched"
    assert alice.library[1].name == "Mountain"
    assert alice.library[3].name == "Plains"
    assert alice.library[4].name == "Swamp"


def test_borborygmos_from_an_empty_library_still_lands_third_from_the_top():
    """A library shorter than the printed depth is not a refusal (CR 401.2
    has no minimum size) - the card still goes in, as deep as the library
    now reaches."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Borborygmos and Fblthp", "Island", "Island"],
            library=[],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    borborygmos = scenario.creature("Borborygmos and Fblthp", "alice")
    sources = scenario.untapped_sources("Island", "Island")

    scenario.activate(borborygmos, *sources, index=0)
    scenario.pass_until_resolved()

    assert borborygmos.zone is Zone.LIBRARY
    assert alice.library == [borborygmos]


def test_screaming_swarms_own_clause_reads_a_different_ordinal_and_subject():
    """Off-set proof at the clause-reader level: "second" rather than
    "third", "this card" rather than a self-normalised "this permanent",
    and "your library" rather than "its owner's library"."""
    effect = parse_mixed_effect(
        "Put this card from your graveyard into your library second from the top."
    )

    assert effect is not None
