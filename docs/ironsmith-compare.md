# MCM vs ironsmith comparison (local, on demand)

`scripts/ironsmith_compare/` compares magic-cards-model with a pinned, unmodified checkout of
[ironsmith](https://github.com/Chiplis/ironsmith) on your own machine, for
Modern/Pioneer/Standard-legal cards only. It answers two questions:

1. **Coverage:** does each engine claim the card? MCM: `handled` / `notice` / `silent`
   (`card_support`). ironsmith: its own compile status, read from the SQLite its
   `sync_card_status_db` writes (`supported` = `strict_compiled` with no unimplemented,
   lossy or semantic-mismatch flag; `partial` = strict but flagged; `unsupported` =
   anything else; `unknown` = no row).
2. **Behaviour:** replayed in ironsmith's scenario runner, does each MCM golden
   (`tests/golden/`) reach the result MCM recorded?

The main product is a ranked, cluster-grouped worklist of the cards MCM leaves `silent`.
It never runs in CI and is not a gate: `compare` always exits 0.

## Licence boundary

ironsmith is `BUSL-1.1 OR AGPL-3.0-or-later`; we elect AGPL-3.0-or-later (`pin.toml`).
Nothing in this repo imports, contains or copies ironsmith code or text. The tool starts
ironsmith's own unmodified binaries and runner as separate processes, gives them our data
files, and reads their output files as data. The per-spec `.mjs` shim that hands a spec
to the runner is generated at run time into the gitignored out dir and never committed.
Never commit any file from the ironsmith checkout, from `.ironsmith-compare/`, or text
copied out of either. See `memory/ironsmith-compare-process-boundary.md`.

## Running it

You need git, a Rust toolchain (rustup), Node, Python 3 and pnpm (ironsmith's own
prerequisites), plus this repo set up (`mise run install`).

1. Clone ironsmith once, next to this repo, without its UI images, at the pin
   (`scripts/ironsmith_compare/pin.toml`):

   ```sh
   git clone --filter=blob:none --no-checkout https://github.com/Chiplis/ironsmith ../ironsmith
   git -C ../ironsmith sparse-checkout set --no-cone '/*' '!/web/ui/public/'
   git -C ../ironsmith checkout a59720c3966b02437c50807b8ed664496862810b
   ```

   Elsewhere? Pass `--ironsmith PATH` or set `IRONSMITH_DIR`.

2. Check it: `mise run compare:ironsmith:doctor`. It refuses a checkout at another
   commit or with local changes (build outputs are gitignored upstream, so they do not
   count), lists missing tools, and warns if ironsmith's `LICENSE.md` stops naming the
   elected licence.

3. Build ironsmith (its own build, inside the checkout):

   ```sh
   mise run compare:ironsmith:build                 # cargo: the two status binaries
   mise run compare:ironsmith:build -- --behaviour  # also ./rebuild-wasm.sh for the runner
   ```

   `--behaviour` runs ironsmith's `./rebuild-wasm.sh`, which downloads Scryfall and
   compiles every card on its first run: expect a long first build.

4. Collect:

   ```sh
   mise run compare:ironsmith:collect -- coverage   # our card pool -> ironsmith status DB
   mise run compare:ironsmith:collect -- behaviour  # MCM goldens -> ironsmith runner
   ```

   `coverage` writes our Modern/Pioneer/Standard pool (Scryfall `oracle-cards`, cached in
   `.scryfall-cache/`, or `--bulk PATH`) to `cards.json`, runs `sync_registry_db` and
   `sync_card_status_db` with `--cards cards.json --db-path ironsmith-status.sqlite3`, and
   normalises the result. `behaviour` translates every golden into a scenario spec, runs
   `node --test --test-reporter=junit` on the generated shims from inside the checkout
   (`--concurrency N`, default 8), and reads the JUnit report back.

5. Compare: `mise run compare:ironsmith` (options after `--`: `--format
   modern|pioneer|standard`, default modern; `--status silent|notice|both`, default silent;
   `--live` to classify every card now instead of reading
   `docs/card_coverage/support-baseline.json`; `--workers N`).

`collect` and `build` refuse to run against anything but the clean pin unless you pass
`--allow-unpinned`; every report records the ironsmith sha it actually read.

## Outputs

Everything lands in `.ironsmith-compare/<ironsmith sha12>-<mcm sha12>/` (gitignored; `--out
DIR` overrides):

| File | What |
|---|---|
| `cards.json` | the card pool handed to ironsmith |
| `ironsmith-status.sqlite3` | ironsmith's status DB, written by its own binaries |
| `ironsmith-coverage.jsonl` | our normalised rows: name, join key, status, parse status, reason |
| `behaviour/` | generated scenario specs, shims and `manifest.json` (translated / untranslated) |
| `behaviour.junit.xml` | the runner's JUnit report |
| `ironsmith-behaviour.jsonl` | one row per golden: `agree` / `disagree` / `ironsmith-error` / `untranslated` |
| `report.json` | schema-versioned: meta, quadrants, behaviour, every card, the worklist |
| `report.md` | quadrant table, top of the worklist by cluster, behaviour summary, disagreements |
| `worklist.csv` | the full ranked worklist |
| `logs/` | build, coverage and behaviour logs |

## How to read it

- **Quadrants:** `both`, `mcm_only`, `iron_only` (the T-109 targets), `neither`. Only
  `handled` counts as MCM support and only `supported` as ironsmith's.
- **Worklist ranking:** metagame weight (highest inclusion rate in
  `docs/card_coverage/metagame.json`) first, then ironsmith `supported` first, then the
  size of the oracle-template cluster (`card_coverage.clause_signature`) the card shares,
  then name. One cluster is one T-109 sub-task: one parser fix lifts every card in it.
- **Behaviour:** the translator maps quiet precombat-main boards with no decisions, modes or
  X, and either an activated ability (selected by its cost text) or an enters trigger
  (raised by casting the source from hand). It asserts life, permanent counts (tokens
  included), hand / graveyard / exile counts, counters, power/toughness and tapped state
  that MCM recorded; library counts are not asserted (the runner sizes libraries itself).
  Everything else is `untranslated`, with the reason counted in the report. A failure
  whose message is one of the runner's `expected ..., got ...` assertions is a
  `disagree`; any other failure is `ironsmith-error`. A disagreement is a lead to check
  against the Comprehensive Rules, never proof MCM is wrong.
- ironsmith `supported` is its own compile acceptance, not proof of correct play.

## Bumping the pin

Change `commit` and `date` in `scripts/ironsmith_compare/pin.toml` in a reviewed PR,
then re-run `doctor`. If ironsmith changed its status schema, `collect coverage` stops
with the unknown `PRAGMA user_version`; extend `KNOWN_SCHEMA_VERSIONS` in
`coverage.py` only after checking the status columns still mean the same.
