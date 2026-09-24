# Dark Ascension Promos (pdka)

- Expansion: 121
- Set code: `pdka`
- Release date: 2012-01-28
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
| Partial (unaudited) | 1 | 20.0% |
| Not tested (handled, untested) | 1 | 20.0% |
| Not working (silent / notice / error) | 3 | 60.0% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Ravenous Demon // Archdemon of Greed | silent | At the beginning of your upkeep, sacrifice a Human. If you can't, tap this creature and it deals 9 damage to you. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Strangleroot Geist | silent | Undying | no machine in the engine executes this keyword | Y/-/- | not_working |
| Zombie Apocalypse | silent | Return all Zombie creature cards from your graveyard to the battlefield tapped, then destroy all Humans. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Gravecrawler | unaudited | You may cast this card from your graveyard as long as you control a Zombie. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Mondronen Shaman // Tovolar's Magehunter | handled | At the beginning of each upkeep, if no spells were cast last turn, transform this creature. | the engine reads this text and performs it | Y/-/- | not_tested |

## Fully supported

<details>
<summary>0 cards</summary>


</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| At the beginning of your upkeep, sacrifice a Human. If you can't, tap this creature and it deals 9 damage to you. | Ravenous Demon // Archdemon of Greed | 1 |
| Return all Zombie creature cards from your graveyard to the battlefield tapped, then destroy all Humans. | Zombie Apocalypse | 1 |
| Undying | Strangleroot Geist | 1 |
| You may cast this card from your graveyard as long as you control a Zombie. | Gravecrawler | 1 |

## Notes


