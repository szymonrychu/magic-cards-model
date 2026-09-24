# Avacyn Restored Promos (pavr)

- Expansion: 123
- Set code: `pavr`
- Release date: 2012-04-28
- Cards in scope (Modern/Pioneer/Standard-legal): 5

## Legality

| Format | Legal cards |
|---|---|
| Modern | 5 |
| Pioneer | 0 |
| Standard | 0 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 0 | 0.0% |
| Partial (unaudited) | 0 | 0.0% |
| Not tested (handled, untested) | 3 | 60.0% |
| Not working (silent / notice / error) | 2 | 40.0% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Killing Wave | silent | For each creature, its controller sacrifices it unless they pay X life. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Silverblade Paladin | silent | As long as this creature is paired with another creature, both creatures have double strike. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Latch Seeker | handled | This creature can't be blocked. | the engine reads this text and performs it | Y/-/- | not_tested |
| Moonsilver Spear | handled | Equipped creature has first strike. | the engine reads this text and performs it | Y/-/- | not_tested |
| Restoration Angel | handled | When this creature enters, you may exile target non-Angel creature you control, then return that card to the battlefield under your control. | the engine reads this text and performs it | Y/-/- | not_tested |

## Fully supported

<details>
<summary>0 cards</summary>


</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| As long as this creature is paired with another creature, both creatures have double strike. | Silverblade Paladin | 1 |
| For each creature, its controller sacrifices it unless they pay X life. | Killing Wave | 1 |

## Notes


