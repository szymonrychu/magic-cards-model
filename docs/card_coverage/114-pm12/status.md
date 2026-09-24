# Magic 2012 Promos (pm12)

- Expansion: 114
- Set code: `pm12`
- Release date: 2011-07-14
- Cards in scope (Modern/Pioneer/Standard-legal): 3

## Legality

| Format | Legal cards |
|---|---|
| Modern | 3 |
| Pioneer | 2 |
| Standard | 0 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 0 | 0.0% |
| Partial (unaudited) | 1 | 33.3% |
| Not tested (handled, untested) | 1 | 33.3% |
| Not working (silent / notice / error) | 1 | 33.3% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Bloodlord of Vaasgoth | silent | Whenever you cast a Vampire creature spell, it gains bloodthirst 3. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Garruk's Horde | unaudited | Play with the top card of your library revealed. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Chandra's Phoenix | handled | Whenever an opponent is dealt damage by a red instant or sorcery spell you control or by a red planeswalker you control, return this card from your graveyard to | the engine reads this text and performs it | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>0 cards</summary>


</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| Play with the top card of your library revealed. | Garruk's Horde | 1 |
| Whenever you cast a Vampire creature spell, it gains bloodthirst 3. | Bloodlord of Vaasgoth | 1 |

## Notes


