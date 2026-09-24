# Media and Collaboration Promos (pmei)

- Expansion: 014
- Set code: `pmei`
- Release date: 1996-12-01
- Cards in scope (Modern/Pioneer/Standard-legal): 6

## Legality

| Format | Legal cards |
|---|---|
| Modern | 6 |
| Pioneer | 4 |
| Standard | 3 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 1 | 16.7% |
| Partial (unaudited) | 2 | 33.3% |
| Not tested (handled, untested) | 2 | 33.3% |
| Not working (silent / notice / error) | 1 | 16.7% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Shrieking Drake | silent | When this creature enters, return a creature you control to its owner's hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Iroh, Grand Lotus | unaudited | During your turn, each non-Lesson instant and sorcery card in your graveyard has flashback. The flashback cost is equal to that card's mana cost. | a static ability no support check audits - not verified either way | Y/Y/Y | partial |
| Peter Parker // Amazing Spider-Man | unaudited | Each legendary spell you cast that's one or more colors has web-slinging {G}{W}{U}. | a static ability no support check audits - not verified either way | Y/Y/Y | partial |
| Phantasmal Dragon | handled | When this creature becomes the target of a spell or ability, sacrifice it. | the engine reads this text and performs it | Y/-/- | not_tested |
| Phyrexian Rager | handled | When this creature enters, you draw a card and you lose 1 life. | the engine reads this text and performs it | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>1 cards</summary>

- Loki, God of Mischief

</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| During your turn, each non-Lesson instant and sorcery card in your graveyard has flashback. The flashback cost is equal to that card's mana cost. | Iroh, Grand Lotus | 1 |
| Each legendary spell you cast that's one or more colors has web-slinging {G}{W}{U}. | Peter Parker // Amazing Spider-Man | 1 |
| When this creature enters, return a creature you control to its owner's hand. | Shrieking Drake | 1 |

## Notes


