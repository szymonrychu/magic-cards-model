# magic-cards-model

A Magic: the Gathering rules engine, built on pydantic. See
[docs/engine-coverage.md](docs/engine-coverage.md) for what is modelled so far
and what is not.

## Setup

```sh
mise trust
mise install
mise run install
```

## Tasks

- `mise run install` - sync venv from lockfile
- `mise run test` - pytest, without the behavioural pool sweep
- `mise run test:behaviour` - the behavioural pool sweep alone (several minutes)
- `mise run test:full` - everything; with `mise run lint`, the gate that must
  be green before any merge to `main`
- `mise run lint` / `mise run fmt` - ruff

## Layout

- `models/` - `Card` (the gameplay subset of the Scryfall card object),
  `CardState`, `Player`, `Game`, `Match`, `ManaCost`, `ManaPool`, `Zone`
- `machines/` - `TurnMachine` (turn structure), `Casting` (CR 601.2),
  `CostPayment` (tap, pool, pay, overflow)

## Testing

Unit tests cover each machine in isolation. Mechanics and rules corner cases are
covered by **scenario tests**, which build a real board state and play it out:

```python
scenario = (
    Scenario()
    .player("alice", library=["Questing Beast"], battlefield=["Forest", "Forest", "Sol Ring"])
    .build()
)
scenario.start_at(Step.PRECOMBAT_MAIN)
scenario.draw()
sources = scenario.untapped_sources("Forest", "Forest", "Sol Ring")
beast = scenario.cast_and_resolve("Questing Beast", *sources)
assert beast.zone is Zone.BATTLEFIELD
```

See [docs/scenario-tests.md](docs/scenario-tests.md) before writing one. Card
data is always a real Scryfall printing; add one with
`uv run python scripts/add_card.py "Card Name"`.

## Rules lookup

The `spellslinger` MCP server is configured in `.mcp.json` and serves the
Comprehensive Rules, curated rulings, and card data. Use it to research a
mechanic before modelling it - see [docs/mcp-tools.md](docs/mcp-tools.md). It is
exposed to the home network by `deploy/mcp-ingress.yaml`.
