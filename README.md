# magic-cards-model

A Magic: the Gathering rules engine, built on pydantic. See
[docs/engine-coverage.md](docs/engine-coverage.md) for what is modelled so far
and what is not.

Automation (daily sync of metagame, decklists and new sets; card implementor): see
[docs/automation/](docs/automation/user-decisions.md) and the skills
`.claude/skills/play-magic-daily-sync` and `.claude/skills/play-magic-card-implementor`.

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
- `mise run compare:ironsmith` - local, on-demand comparison with a pinned ironsmith
  checkout; see [Comparing with ironsmith](#comparing-with-ironsmith)

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

## Comparing with ironsmith

A local, on-demand comparison with [ironsmith](https://github.com/Chiplis/ironsmith): per-card
coverage of Modern/Pioneer/Standard-legal cards and a ranked worklist of the cards MCM
leaves silent. It never runs in CI, and ironsmith is only ever run as separate, unmodified
processes on your machine. Full guide: [docs/ironsmith-compare.md](docs/ironsmith-compare.md).

```sh
# once: clone ironsmith next to this repo at the pin (scripts/ironsmith_compare/pin.toml)
git clone --filter=blob:none --no-checkout https://github.com/Chiplis/ironsmith ../ironsmith
git -C ../ironsmith sparse-checkout set --no-cone '/*' '!/web/ui/public/'
git -C ../ironsmith checkout a59720c3966b02437c50807b8ed664496862810b

mise run compare:ironsmith:doctor                  # pin, clean tree, tools
mise run compare:ironsmith:build                         # ironsmith's own cargo build
mise run compare:ironsmith:collect                       # card pool -> ironsmith status DB
mise run compare:ironsmith                         # report.md, report.json, worklist.csv
```

Outputs land in the gitignored `.ironsmith-compare/<ironsmith sha12>-<mcm sha12>/`.

## Rules lookup

The `spellslinger` MCP server is configured in `.mcp.json` and serves the
Comprehensive Rules, curated rulings, and card data. Use it to research a
mechanic before modelling it - see [docs/mcp-tools.md](docs/mcp-tools.md). It is
exposed to the home network by `deploy/mcp-ingress.yaml`.

## Fan Content notice

unofficial Fan Content permitted under the Fan Content Policy. Not approved/endorsed by Wizards. Portions of the materials used are property of Wizards of the Coast. (c)Wizards of the Coast LLC.

Card data comes from [Scryfall](https://scryfall.com).
