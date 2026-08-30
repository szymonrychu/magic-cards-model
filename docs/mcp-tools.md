# The spellslinger MCP server

Configured in `.mcp.json` at the repo root, so it is available in any session
started in this project. It serves card lookup and a rules knowledge base, which
is how a mechanic gets researched before it gets modelled.

**If the tools are missing from your session**, `.mcp.json` was added or changed
after the session started. Run `/reload-plugins`, or restart Claude Code. Writing
the file is not enough on its own - the server has to be registered, and the
first call may prompt for approval. Subagents inherit whatever the parent session
has, so a parent without the server hands its children the same gap.

    https://mcp.szymonrichert.pl/mcp

Home network only. The ingress that exposes it is `deploy/mcp-ingress.yaml`; see
the bottom of this file.

## Use it before modelling a mechanic

The engine is being built against the actual Comprehensive Rules, not from
memory. Before implementing or testing a mechanic, look up the rule and the
corner cases. A scenario test that cites a CR number in its docstring should
have got that number from here.

### Rules

- **`knowledge_search`** - the Comprehensive Rules, plus wiki and deck content.
  Takes `q`, and `type="rules"` narrows it to rules text.

  ```
  knowledge_search(q="lethal damage state-based action", type="rules")
  -> 704.5g, 302.7, 120.6 with the text of each
  ```

  **The excerpts truncate at roughly 150 characters, and the operative clause of
  a rule is very often in the tail that gets cut.** Verified repeatedly:

  | Rule | What the excerpt showed | What was cut off |
  |---|---|---|
  | CR 500.7 | extra turns are added directly after the specified turn | "The most recently created turn will be taken first" |
  | CR 723.1 | a player controls another during their next turn | "the effect doesn't end until the beginning of the next turn" |
  | CR 601.2f | the total cost is determined | "the resulting total cost becomes 'locked in'" |
  | CR 603.7b | triggers only once - the next time its trigger event occurs | "unless it has a stated duration" and the simultaneous-events clause |
  | CR 613.7a | a static ability's effect has the object's timestamp | the whole "or the timestamp of the effect that created the ability, whichever is later" half |

  A truncated excerpt that reads as a complete sentence is the dangerous case,
  because there is nothing to tell you something is missing. **For any rule
  whose detail decides the code, use `knowledge_search` to get the rule
  *number*, then read the full text out of the CR release that
  `knowledge_search(type="cr_versions")` names as current** - `2026-08-19` at
  the time of writing, at the `source_url` that call returns. Never fill in a
  truncated tail from memory; that is the exact failure this project exists to
  avoid.

  A second, quieter trap: the search ranks by similarity, so it will happily
  return a *neighbouring* rule with high confidence. Sacrificing is CR 701.21a,
  not 701.17a; ability categories are CR 113.3, not 112.3. Read the rule number
  off the result rather than off the query you had in mind.

  **The excerpts truncate, and the truncation is dangerous.** Results are cut at
  roughly 150 characters, and the operative clause of a rule is very often in the
  tail that gets dropped. A truncated excerpt reads as though it were the whole
  rule, so this misleads by omission rather than by error. Real examples from
  this repo, where the deciding sentence was entirely invisible in the excerpt:

  | Rule | The part that was cut off |
  |---|---|
  | CR 500.7 | "The most recently created turn will be taken first." |
  | CR 723.1 | "the effect doesn't end until the beginning of the next turn" |
  | CR 601.2f | "Then the resulting total cost becomes 'locked in'." |
  | CR 611.2a | "If no duration is stated, it lasts ..." |

  Use `knowledge_search` to find the rule *number* and confirm the rule exists,
  then **read the full text** for anything where the detail matters. The reliable
  way: the knowledge base publishes the CR release it serves under `cr_versions`
  along with a checksum, so download that exact release and verify it before
  reading from it. An agent doing this got sha256 `4381ad1b…423f` for the
  `2026-08-19` release. Never complete a truncated tail from memory - that is the
  precise failure this project's central rule exists to prevent.

  Two things the corpus does **not** contain, both discovered the hard way: there
  is no numbered rule defining the `non-` prefix (CR 109.2/109.2a/109.2b decide
  what `noncreature` reaches, and CR 300.1 is the type list), and layer 7 has
  sublayers 7a-7d only - there is no 613.4e, however strongly you remember one.

- **`knowledge_search(q="...", type="youtube")`** - **judge transcripts, and the
  best corner-case source this project has.** A judge podcast indexed `DDR#1`
  through at least `DDR#1000`, each episode a real ruling on a real interaction.
  Results carry a title (`DDR#466 - Village Rites + Eidolon of the Great Revel`),
  the judge's reasoning, and usually a `related` list naming the exact cards.

  Two cautions. **Filter out tournament policy** - a large share of episodes are
  judge procedure (angle shooting, playing the wrong opponent, missed-trigger
  warnings, deck checks) and are not modellable here. And **the transcripts are
  people talking**: verify every conclusion against `type="rules"` before writing
  a test around it. Where they disagree, the rules win.

  `tests/scenarios/judge/` holds the tests mined from this corpus.

- **`reveries_search`** - **not useful for this project. Do not use it for rules
  work.** Verified 2026-08-26: the LightRAG corpus is roughly 200 documents, all
  of them deck-research artifacts from a handful of past analysis runs (GR Tooth
  and Nail, Esper Control). It holds no general rules or interaction knowledge.
  Asked how deathtouch and trample interact it correctly answered "not enough
  information" - and then returned twenty large unrelated deck documents, which
  is an enormous waste of context. It has also been observed replying in Chinese.
  Use `knowledge_search` for rules instead.

### Cards

- **`resolve_cards`** - batch name to full card data, including legalities.
- **`card_search`** - filter by oracle text, type, colours, CMC, mechanic. Useful
  for finding a card that exercises a specific mechanic.
- **`card_pool`** - the legal pool for a format.

Card data for tests still comes from Scryfall via `scripts/add_card.py`, since
the fixtures need the exact Scryfall response shape. Use the MCP tools to *find*
the right card, then add it to the pool.

**The card database has holes.** Verified 2026-08-26: `resolve_cards` could not
find **Sol Ring** or **Black Lotus**, while obscure cards resolved fine. Never
conclude a card does not exist because this server missed it - check Scryfall.
`card_search`'s `oracle_text` filter is also not a substring match: searching
`Add {C}{C}` returned cards reading `Add {C}`, alphabetically ordered, 16 hits
for a query that should have hundreds. Treat it as a fuzzy hint, not a filter.

### Verified state of the tools, 2026-08-26

| Tool | Verdict |
|---|---|
| `knowledge_search(type="rules")` | **Excellent.** Precise, correct CR retrieval. The one that matters here. |
| `resolve_cards` | Oracle text accurate where present, but the card pool is incomplete. |
| `card_search` | Finds cards; filters are loose. Do not trust the result count. |
| `synergy_hypothetical` | Scores relatedness, **not** synergy direction - see below. |
| `reveries_search` | Wrong corpus for rules work. Avoid. |

**Synergy scores do not distinguish synergy from anti-synergy.** Leyline of the
Void plus Snapcaster Mage scored **0.7**, in the same band as the genuinely
synergistic Ragavan plus Dragon's Rage Channeler at 0.8 - even though the tool's
own explanation correctly said Leyline exiles what Snapcaster wants to flash
back. Known anti-synergies like Rest in Peace plus Tarmogoyf score 0.05, but
only because the mechanical screen drops them before the LLM ever runs: the
right answer for the wrong reason. A card pair that fights itself while sharing
a strategy axis scores HIGH. Read the `mechanism` prose, never the number alone.

### Meta and deckbuilding

`statistics_*`, `synergy_*`, `meta_*`, and `decklist_import` cover tournament
data, archetypes, and deck analysis. Not needed for the rules engine, but there
if the project grows that way.

## The ingress

`deploy/mcp-ingress.yaml` exposes the in-cluster service
`spellslinger-mcp-http.spellslinger-development.svc.cluster.local:8080` at
`mcp.szymonrichert.pl`.

```sh
kubectl apply -f deploy/mcp-ingress.yaml
```

It is applied by hand rather than by the `spellslinger-mcp-http` helm chart,
which ships no ingress of its own. Two things to know:

- **LAN only.** The whitelist is `192.168.0.0/16,10.0.0.0/8,172.16.0.0/12`,
  matching the `lightrag-tmp` ingresses in the `tatara` namespace. The MCP
  endpoint has no authentication, so that source range is the only thing keeping
  it off the public internet. Do not widen it without putting auth in front.
- **DNS already works.** `*.szymonrichert.pl` resolves to 192.168.1.25 on the
  LAN and to the public IP outside it, so no new record was needed.
