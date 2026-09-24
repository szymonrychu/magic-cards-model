# Duel Decks: Heroes vs. Monsters (ddl)

- Expansion: 141
- Set code: `ddl`
- Release date: 2013-09-06
- Cards in scope (Modern/Pioneer/Standard-legal): 6

## Legality

| Format | Legal cards |
|---|---|
| Modern | 6 |
| Pioneer | 6 |
| Standard | 0 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 2 | 33.3% |
| Partial (unaudited) | 0 | 0.0% |
| Not tested (handled, untested) | 2 | 33.3% |
| Not working (silent / notice / error) | 2 | 33.3% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Cavalry Pegasus | silent | Whenever this creature attacks, each attacking Human gains flying until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Ordeal of Purphoros | silent | Whenever enchanted creature attacks, put a +1/+1 counter on it. Then if it has three or more +1/+1 counters on it, sacrifice this Aura. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Anax and Cymede | handled | Heroic — Whenever you cast a spell that targets Anax and Cymede, creatures you control get +1/+1 and gain trample until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Satyr Hedonist | handled |  |  | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>2 cards</summary>

- Destructive Revelry
- Polukranos, World Eater

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| whenever enchanted creature attacks, put a +N/+N counter on it. then if it has three or more +N/+N counters on it, sacrifice ~. | 1 | Ordeal of Purphoros | ddl |
| whenever ~ attacks, each attacking human gains flying until end of turn. | 1 | Cavalry Pegasus | ddl |

## Notes


