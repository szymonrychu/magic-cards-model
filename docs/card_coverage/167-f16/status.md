# Friday Night Magic 2016 (f16)

- Expansion: 167
- Set code: `f16`
- Release date: 2016-01-01
- Cards in scope (Modern/Pioneer/Standard-legal): 4

## Legality

| Format | Legal cards |
|---|---|
| Modern | 4 |
| Pioneer | 4 |
| Standard | 0 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 1 | 25.0% |
| Partial (unaudited) | 0 | 0.0% |
| Not tested (handled, untested) | 2 | 50.0% |
| Not working (silent / notice / error) | 1 | 25.0% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Rise from the Tides | silent | Create a tapped 2/2 black Zombie creature token for each instant and sorcery card in your graveyard. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Flaying Tendrils | handled | Devoid (This card has no color.) All creatures get -2/-2 until end of turn. If a creature would die this turn, exile it instead. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Spatial Contortion | handled | ({C} represents colorless mana.) Target creature gets +3/-3 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>1 cards</summary>

- Crumbling Vestige

</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| Create a tapped 2/2 black Zombie creature token for each instant and sorcery card in your graveyard. | Rise from the Tides | 1 |

## Notes


