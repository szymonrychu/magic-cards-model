# Apocalypse (apc)

- Expansion: 035
- Set code: `apc`
- Release date: 2001-06-04
- Cards in scope (Modern/Pioneer/Standard-legal): 22

## Legality

| Format | Legal cards |
|---|---|
| Modern | 22 |
| Pioneer | 11 |
| Standard | 1 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 7 | 31.8% |
| Works (untested) | 14 | 63.6% |
| Partial (unaudited) | 0 | 0.0% |
| Not working | 1 | 4.5% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Brass Herald | silent | When this creature enters, reveal the top four cards of your library. Put all creature cards of the chosen type revealed this way into your hand and the rest on | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Battlefield Forge | handled |  |  | Y/Y/- | not_tested |
| Bloodfire Colossus | handled | {R}, Sacrifice this creature: It deals 6 damage to each creature and each player. | the engine reads this text and performs it | Y/-/- | not_tested |
| Desolation Giant | handled | When this creature enters, destroy all other creatures you control. If it was kicked, destroy all other creatures instead. | the engine reads this text and performs it | Y/-/- | not_tested |
| Goblin Ringleader | handled | When this creature enters, reveal the top four cards of your library. Put all Goblin cards revealed this way into your hand and the rest on the bottom of your l | the engine reads this text and performs it | Y/Y/- | not_tested |
| Lay of the Land | handled | Search your library for a basic land card, reveal it, put it into your hand, then shuffle. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Lightning Angel | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Mystic Snake | handled | When this creature enters, counter target spell. | the engine reads this text and performs it | Y/-/- | not_tested |
| Phyrexian Arena | handled | At the beginning of your upkeep, you draw a card and lose 1 life. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Phyrexian Gargantua | handled | When this creature enters, you draw two cards and you lose 2 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Phyrexian Rager | handled | When this creature enters, you draw a card and you lose 1 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Smash | handled | Destroy target artifact. Draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Sylvan Messenger | handled | When this creature enters, reveal the top four cards of your library. Put all Elf cards revealed this way into your hand and the rest on the bottom of your libr | the engine reads this text and performs it | Y/Y/- | not_tested |
| Vindicate | handled | Destroy target permanent. | the engine reads this text and performs it | Y/-/- | not_tested |
| Yavimaya Coast | handled |  |  | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>7 cards</summary>

- Caves of Koilos
- Dodecapod
- Fire // Ice
- Index
- Legacy Weapon
- Llanowar Wastes
- Shivan Reef

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| when ~ enters, reveal the top four cards of your library. put all creature cards of the chosen type revealed ~ into your hand and the rest on the bottom of your | 1 | Brass Herald | apc |

## Notes


