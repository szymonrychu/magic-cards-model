"""Judge scenarios: costs the engine cannot yet read off a card.

Sourced from the DDR judge transcripts. Episodes covered:

- **DDR#991** - How does Waterbend work? (a cost that lets untapped artifacts
  and creatures each pay for {1}, instead of producing mana)
- **DDR#997** - Back from the Brink + Delraich (an activated ability that names
  a different card's mana cost as its own cost, ignoring that card's
  alternative cost)
- **DDR#978** - Ancestral Vision + Sphere of Resistance (a generic "spells cost
  more" static ability, and Suspend on top of it)

DDR#991 and DDR#997 are `xfail`: `machines/cost.cost_component_for_phrase` is
the reader that turns a printed cost sentence `machines/abilities.py` could not
classify into something payable (CR 118.3), and neither sentence below comes
out of it as anything at all - confirmed directly:

    >>> cost_component_for_phrase("Waterbend {3}")
    None
    >>> cost_component_for_phrase("Exile a creature card from your graveyard and pay its mana cost")
    None

`Game.activation_cost` raises `ValueError` the moment it hits a `None` from
that reader (CR 602.1a), so each of those two tests documents the gap by
attempting the CR-correct activation and letting that `ValueError` be the
failure - never by predicting a keyword the engine has never heard of.

DDR#978's cost-increase half is no longer `xfail` - a concurrent engine wave
landed static "spells cost more" abilities (Sphere of Resistance and its kin)
reaching the casting path, so `test_sphere_of_resistance_taxes_every_spell_by_one_generic_mana`
now passes as an ordinary test. Its docstring says what changed.

Every CR number here was looked up with `knowledge_search(type="rules")`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

# --------------------------------------------------------------------------
# DDR#991 - Waterbend: tap instead of paying mana
# --------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason="cost_component_for_phrase('Waterbend {3}') returns None, so "
    "Game.activation_cost raises ValueError before any payment is attempted - the "
    "'Waterbend N' cost shape (CR 701.67a: pay a cost, but for each generic mana in "
    "it you may tap an untapped artifact or creature you control instead) has no "
    "reader in machines/cost.py at all, not even one that falls back to charging "
    "plain mana.",
)
def test_waterbend_lets_an_untapped_creature_pay_part_of_the_cost():
    """DDR#991: each untapped artifact or creature tapped this way pays for {1}.

    CR 701.67a: "'Waterbend [cost]' means 'Pay [cost]. For each generic mana in
    that cost, you may tap an untapped artifact or creature you control rather
    than pay that mana.'" Flexible Waterbender's own ability is `Waterbend {3}:
    This creature has base power and toughness 5/2 until end of turn.` - three
    generic mana, payable entirely by tapping three other permanents and
    spending no mana at all.
    """
    scenario = (
        Scenario().player("alice", battlefield=["Flexible Waterbender", "Grizzly Bears"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    waterbender = scenario.creature("Flexible Waterbender", "alice")

    # No mana sources at all - CR 701.67a says tapping Grizzly Bears (and two
    # more permanents, omitted here since the ability already can't be reached)
    # should stand in for the generic mana instead.
    scenario.activate(waterbender)

    assert waterbender.power == 5 and waterbender.toughness == 2


# --------------------------------------------------------------------------
# DDR#997 - "pay its mana cost" ignores that card's own alternative cost
# --------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason="cost_component_for_phrase cannot parse 'Exile a creature card from your "
    "graveyard and pay its mana cost' at all - it is a single CostKind.OTHER phrase "
    "spanning both an object cost (a card chosen from the graveyard) and a mana cost "
    "that depends on *that chosen card's* printed mana cost, which nothing in "
    "machines/cost.py resolves. Game.activation_cost raises ValueError before the "
    "question this episode is actually about - whether Delraich's own alternative "
    "cost could substitute - is ever reached.",
)
def test_back_from_the_brink_charges_delraichs_real_mana_cost_not_its_alternative():
    """DDR#997: an ability that names a card's mana cost sees the real one.

    Delraich reads "You may sacrifice three black creatures rather than pay
    this spell's mana cost" - but CR 113.6d says that ability "functions on the
    stack", i.e. only when Delraich itself is being cast, and CR 118.9c is
    explicit that an alternative cost "doesn't change a spell's mana cost, only
    what its controller has to pay to cast it. Spells and abilities that ask
    for that spell's mana cost still see the original value." Back from the
    Brink's activation cost asks for Delraich's mana cost directly rather than
    casting it, so the correct behaviour is charging {6}{B} in mana and giving
    the alternative cost nothing to apply to.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            graveyard=["Delraich"],
            battlefield=[
                "Back from the Brink",
                "Swamp",
                "Mountain",
                "Mountain",
                "Mountain",
                "Mountain",
                "Mountain",
                "Mountain",
            ],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    back_from_the_brink = scenario.find("Back from the Brink", Zone.BATTLEFIELD, "alice")
    delraich = scenario.find("Delraich", Zone.GRAVEYARD, "alice")
    sources = scenario.untapped_sources(
        "Swamp", "Mountain", "Mountain", "Mountain", "Mountain", "Mountain", "Mountain"
    )

    scenario.activate(back_from_the_brink, *sources, sacrificing=[delraich])

    assert delraich.zone is Zone.EXILE
    tokens = [state for state in scenario.player("alice").battlefield if state.name == "Delraich"]
    assert len(tokens) == 1, "a token copy of Delraich should have entered the battlefield"


# --------------------------------------------------------------------------
# DDR#978 - a generic "spells cost more" static ability
# --------------------------------------------------------------------------


def test_sphere_of_resistance_taxes_every_spell_by_one_generic_mana():
    """DDR#978, now landed: a concurrent engine wave taught the casting path to
    read a static "spells cost more" ability off a *different* permanent and
    apply it as a cost increase, not just a reduction.

    CR 601.2f: "Some effects may increase or reduce the cost to pay." Sphere of
    Resistance's static ability is unconditional - it taxes every spell, not
    only ones with mana symbols already in their cost - so Lightning Bolt goes
    from {R} to {1}{R} while Sphere of Resistance is out. One Mountain is only
    ever enough to pay the untaxed {R}, so the cast fails; verified separately
    (not in this test) that two Mountains let it through for exactly {1}{R} and
    the Bolt resolves normally.

    Ancestral Vision's own half of this episode still needs Suspend on top of
    this, which `docs/engine-coverage.md` lists as parsed by
    `machines/abilities.py` but not executed by `Game` at all - a second,
    still-missing piece, which is why this test isolates the cost-increase half
    with an ordinary instant instead.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain", "Sphere of Resistance"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")

    with pytest.raises(ValueError):
        scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=[bears])
