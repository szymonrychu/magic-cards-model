""" "`<self>` is all colors." (CR 604.3's characteristic-defining ability): a
card's own name, self-referential (CR 201.5), functions in every zone -
including on the stack, where colour has nothing to compute against
(CR 112.6a).

Card text, confirmed with `resolve_cards` in the session that wrote this
file:

Sphinx of the Guildpact (Artifact Creature, Modern/Pioneer legal):
    Sphinx of the Guildpact is all colors.
    Flying
    Hexproof from monocolored

Invasion of Alara // Awaken the Maelstrom's back face carries the identical
sentence, "Awaken the Maelstrom is all colors.", printed ahead of its own
five-clause spell body (tested for those clauses in
`test_awaken_the_maelstrom_spell_effects.py`) - a Scryfall search for
`o:"is all colors."` turns up only these two Modern/Pioneer-legal printings
plus this same battle. Sphinx of the Guildpact is a permanent, so its own
line is a real, always-on `ContinuousEffect` (`machines/layers.
_self_all_colors_builder`) exactly like Leyline of the Guildpact's board-wide
twin, narrowed to just the one object. Awaken the Maelstrom is a sorcery,
never a permanent, so there is no battlefield object for a layer to compute
against while it is on the stack; `machines/effects.
_strip_self_is_all_colors_sentence` reads the identical sentence off a
spell's own resolution text and drops it before `effect_for` ever sees it,
the same way a keyword line already is - CR 604.3's own ability never goes
on the stack and never "runs", so there is nothing here to run twice.

Every rule below was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 604.3** - a characteristic-defining ability "functions in all zones,
  and functions all the time" it applies, including while the object is on
  the stack.
- **CR 201.5** - a card's own printed text naming itself by name means that
  object.
- **CR 613.1e** - layer 5: colour-changing effects, where "is all colors"
  applies.
- **CR 105.2** - the five colors, all at once.
"""

from magic_cards_model.models.card import Color
from tests.scenarios.harness import Scenario


def test_sphinx_of_the_guildpact_is_all_five_colors_on_the_battlefield():
    scenario = Scenario().player("alice", battlefield=["Sphinx of the Guildpact"]).build()
    sphinx = scenario.creature("Sphinx of the Guildpact", "alice")

    colors = set(scenario.game.characteristics_of(sphinx).colors)

    assert colors == {Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN}
