# M19 Gift Pack (g18)

- Expansion: 193
- Set code: `g18`
- Release date: 2018-11-16
- Cards in scope (Modern/Pioneer/Standard-legal): 5

## Legality

| Format | Legal cards |
|---|---|
| Modern | 5 |
| Pioneer | 5 |
| Standard | 0 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 0 | 0.0% |
| Partial (unaudited) | 1 | 20.0% |
| Not tested (handled, untested) | 3 | 60.0% |
| Not working (silent / notice / error) | 1 | 20.0% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Angelic Guardian | silent | Whenever one or more creatures you control attack, they gain indestructible until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Angler Turtle | unaudited | Creatures your opponents control attack each combat if able. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Immortal Phoenix | handled | When this creature dies, return it to its owner's hand. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Rampaging Brontodon | handled | Whenever this creature attacks, it gets +1/+1 until end of turn for each land you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Vengeant Vampire | handled | When this creature dies, destroy target creature an opponent controls and you gain 4 life. | the engine reads this text and performs it | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>0 cards</summary>


</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| Creatures your opponents control attack each combat if able. | Angler Turtle | 1 |
| Whenever one or more creatures you control attack, they gain indestructible until end of turn. | Angelic Guardian | 1 |

## Notes


