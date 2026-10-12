# Homelands (hml)

- Expansion: 010
- Set code: `hml`
- Release date: 1995-10-01
- Cards in scope (Modern/Pioneer/Standard-legal): 8

## Legality

| Format | Legal cards |
|---|---|
| Modern | 8 |
| Pioneer | 0 |
| Standard | 0 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 2 | 25.0% |
| Works (untested) | 5 | 62.5% |
| Partial (unaudited) | 0 | 0.0% |
| Not working | 1 | 12.5% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Sengir Autocrat | silent | When this creature leaves the battlefield, exile all Serf tokens. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Anaba Bodyguard | handled | First strike | machines/combat.py | Y/-/- | not_tested |
| Anaba Shaman | handled | {R}, {T}: This creature deals 1 damage to any target. | the engine reads this text and performs it | Y/-/- | not_tested |
| Eron the Relentless | handled | {R}{R}{R}: Regenerate Eron. | the engine reads this text and performs it | Y/-/- | not_tested |
| Merchant Scroll | handled | Search your library for a blue instant card, reveal that card, put it into your hand, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Torture | handled | {1}{B}: Put a -1/-1 counter on enchanted creature. | the engine reads this text and performs it | Y/-/- | not_tested |

## Fully supported

<details>
<summary>2 cards</summary>

- Giant Oyster
- Serrated Arrows

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| when ~ leaves the battlefield, exile all serf tokens. | 1 | Sengir Autocrat | hml |

## Notes


