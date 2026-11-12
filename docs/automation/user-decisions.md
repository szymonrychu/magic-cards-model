# User decisions for the play-magic automation

Shared memory of the user's decisions. Both automation skills
(`.claude/skills/play-magic-daily-sync`, `.claude/skills/play-magic-card-implementor`)
read this file first, on every run. Decisions here override the skills.

Rules:

- Whenever the user answers a question (via the superleader, a task decision, or a
  session message), the agent that learned it appends an entry and lands it in its next
  PR (or in a tiny docs PR).
- Entries are append-only and never edited. Newest at the bottom of the log.
- Until a question is answered, follow the skill text.

Entry format:

```
### YYYY-MM-DD - <short topic>
Question: <verbatim>
Answer: <verbatim>
Source: <T-134 decision id | session slug | PR>
```

All setup questions are answered; new ones are appended to the log below.

## Log (append below)

### 2026-11-12 - decklists
Question: "Q1. Which decklists should the daily worker (A) pull and where should they land?"
Answer: "A: refresh metagame.json daily (engine PR, self-merge on green CI); new top Modern lists go to API decks/ via B"
Option description: "Recommended. A stays cheap: data-only PR. New tournament lists whose cards are all supported are added by A to API decks/; lists needing new cards are handed to B. mtg-decks untouched."
Source: T-134 decision 448

### 2026-11-12 - formats
Question: "Q2. Which formats count for decklists and new-card detection?"
Answer: "Modern only"
Source: T-134 decision 449

### 2026-11-12 - implementation scope
Question: "Q3. Which new cards must B implement?"
Answer: "All Not-working cards of each new Modern-legal set, plus any card in current metagame lists"
Source: T-134 decision 450

### 2026-11-12 - previews
Question: "Q4. Previewed (unreleased) cards: when should they be reported and implemented?"
Answer: "As soon as previewed on Scryfall; A reports a set once a day while new previews keep arriving"
Source: T-134 decision 451

### 2026-11-12 - hard cards
Question: "Q5. How far should B go with hard cards that need an unmodelled subsystem (battles, phasing, flip, layer-1 sublayers, block requirements...)?"
Answer: "Build the subsystem generally (the engine rule: fix the mechanic, never the card); only if truly impossible, strict xfail with a reason and list it in the summary"
Source: T-134 decision 452

### 2026-11-12 - merging
Question: "Q6. May the agents merge their own PRs without human review?"
Answer: "Yes: self-merge (squash) once the owner gate and CI are green and an independent sonnet reviewer subagent found no real issue"
Source: T-134 decision 453

### 2026-11-12 - release and deploy
Question: "Q7. Release and deploy after B merges engine changes?"
Answer: "B releases (API PR, e.g. new decks or a chore(engine) bump commit) and runs k8s:deploy of the new semver, then smoke-checks play-magic; preset B gets kube_namespace_access {mtg-engine: [edit]}"
Source: T-134 decision 454

### 2026-11-12 - questions
Question: "Q8. When B hits a question it cannot settle from code, rules or the decisions file, what should it do?"
Answer: "Send it to the superleader (who posts it as a decision for you), keep working on other cards, and record your answer in the decisions file"
Source: T-134 decision 455

### 2026-11-12 - All Good Things share a card type
Question: All Good Things... chapter IV ("If all cards exiled with this Saga share a card type, you gain 10 life"): how should the engine judge it when fewer than two cards were exiled with the Saga (e.g. empty hand on some chapters)? No rulings exist yet and the CR has no definition of "share a card type".
Answer: "0 cards: no life; 1 card: true; 2+: true when their card-type sets intersect"
Source: T-136 decision 464
