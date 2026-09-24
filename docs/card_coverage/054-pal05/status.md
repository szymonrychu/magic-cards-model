# Arena League 2005 (pal05)

- Expansion: 054
- Set code: `pal05`
- Release date: 2005-01-01
- Cards in scope (Modern/Pioneer/Standard-legal): 3

## Legality

| Format | Legal cards |
|---|---|
| Modern | 3 |
| Pioneer | 1 |
| Standard | 0 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 0 | 0.0% |
| Partial (unaudited) | 0 | 0.0% |
| Not tested (handled, untested) | 1 | 33.3% |
| Not working (silent / notice / error) | 2 | 66.7% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Genju of the Spires | silent | {2}: Enchanted Mountain becomes a 6/1 red Spirit creature until end of turn. It's still a land. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Okina Nightwatch | silent | As long as you have more cards in hand than each opponent, this creature gets +3/+3. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Skyknight Legionnaire | handled | Flying | machines/combat.py | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>0 cards</summary>


</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| As long as you have more cards in hand than each opponent, this creature gets +3/+3. | Okina Nightwatch | 1 |
| {2}: Enchanted Mountain becomes a 6/1 red Spirit creature until end of turn. It's still a land. | Genju of the Spires | 1 |

## Notes


