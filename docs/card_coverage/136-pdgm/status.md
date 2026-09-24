# Dragon's Maze Promos (pdgm)

- Expansion: 136
- Set code: `pdgm`
- Release date: 2013-04-27
- Cards in scope (Modern/Pioneer/Standard-legal): 5

## Legality

| Format | Legal cards |
|---|---|
| Modern | 5 |
| Pioneer | 5 |
| Standard | 1 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 1 | 20.0% |
| Partial (unaudited) | 1 | 20.0% |
| Not tested (handled, untested) | 1 | 20.0% |
| Not working (silent / notice / error) | 2 | 40.0% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Breaking // Entering | silent | Put a creature card from a graveyard onto the battlefield under your control. It gains haste until end of turn. Fuse (You may cast one or both halves of this ca | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Render Silent | silent | Counter target spell. Its controller can't cast spells this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Melek, Izzet Paragon | unaudited | Play with the top card of your library revealed. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Maze's End | handled | This land enters tapped. | the engine reads this text and performs it | Y/Y/Y | not_tested |

## Fully supported

<details>
<summary>1 cards</summary>

- Trostani's Summoner

</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| Counter target spell. Its controller can't cast spells this turn. | Render Silent | 1 |
| Play with the top card of your library revealed. | Melek, Izzet Paragon | 1 |
| Put a creature card from a graveyard onto the battlefield under your control. It gains haste until end of turn. Fuse (You may cast one or both halves of this ca | Breaking // Entering | 1 |

## Notes


