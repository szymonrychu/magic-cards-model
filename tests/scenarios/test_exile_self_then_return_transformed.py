"""Scenario: "`<cost>`: Exile `<name>`, then return it to the battlefield
transformed under its owner's control. Activate only as a sorcery." - a
mandatory (no "you may") self-referential transform-return activated ability,
read generally by `machines/effects.py` off the printed sentence, not pinned
to one card.

Oracle text pulled with `scripts/add_card.py` and verified against
`src/magic_cards_model/data/printings/`:

- **Vorinclex // The Grand Evolution** (the follow-up's own named card):
  "{6}{G}{G}: Exile Vorinclex, then return it to the battlefield transformed
  under its owner's control. Activate only as a sorcery."
- **Jill, Shiva's Dominant // Shiva, Warden of Ice** (off-pool, proves the
  parser generalises): "{3}{U}{U}, {T}: Exile Jill, then return it to the
  battlefield transformed under its owner's control. Activate only as a
  sorcery." A different cost shape (a `{T}` component Vorinclex's own
  activation cost does not have) and a different name.

Rules verified with `mise run rules:find` in this session:

- **CR 701.27a** - "To transform a permanent, turn it over so that its other
  face is up."
- **CR 712.14a** - a permanent put onto the battlefield "transformed" enters
  with its back face up.
- **CR 400.7** - the returned permanent is a new object: no memory of counters
  or summoning sickness survives the round trip (CR 122.2).
- **CR 201.5** - "text that refers to the object it's on by name means just
  that particular object" - the self-reference `named.lower() in source.name`
  checks.
- **CR 608.2b** / **CR 111.8** - a token that has already left the battlefield
  once does not return; the exile-then-return halves are gated on the object
  actually reaching exile.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def test_vorinclex_exiles_and_returns_itself_transformed():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Vorinclex // The Grand Evolution"] + ["Forest"] * 8,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vorinclex = scenario.find("Vorinclex", Zone.BATTLEFIELD, "alice")

    scenario.activate(vorinclex, auto=True)
    scenario.pass_until_resolved()

    assert vorinclex.zone is Zone.BATTLEFIELD
    assert vorinclex.controller == "alice"
    assert vorinclex.transformed is True
    assert vorinclex.name == "The Grand Evolution"


def test_off_pool_jill_exiles_and_returns_itself_transformed_with_a_tap_cost():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Jill, Shiva's Dominant // Shiva, Warden of Ice"] + ["Island"] * 5,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    jill = scenario.find("Jill, Shiva's Dominant", Zone.BATTLEFIELD, "alice")

    scenario.activate(jill, auto=True)
    scenario.pass_until_resolved()

    assert jill.zone is Zone.BATTLEFIELD
    assert jill.controller == "alice"
    assert jill.transformed is True
    assert jill.name == "Shiva, Warden of Ice"
