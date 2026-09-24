# Apocalypse (apc)

- Expansion: 035
- Set code: `apc`
- Release date: 2001-06-04
- Cards in scope (Modern/Pioneer/Standard-legal): 21

## Legality

| Format | Legal cards |
|---|---|
| Modern | 21 |
| Pioneer | 10 |
| Standard | 1 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 3 | 14.3% |
| Partial (unaudited) | 2 | 9.5% |
| Not tested (handled, untested) | 13 | 61.9% |
| Not working (silent / notice / error) | 3 | 14.3% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Bloodfire Colossus | silent | {R}, Sacrifice this creature: It deals 6 damage to each creature and each player. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Brass Herald | silent | When this creature enters, reveal the top four cards of your library. Put all creature cards of the chosen type revealed this way into your hand and the rest on | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Desolation Giant | silent | When this creature enters, destroy all other creatures you control. If it was kicked, destroy all other creatures instead. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Dodecapod | unaudited | If a spell or ability an opponent controls causes you to discard this card, put it onto the battlefield with two +1/+1 counters on it instead of putting it into | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Legacy Weapon | unaudited | If Legacy Weapon would be put into a graveyard from anywhere, reveal Legacy Weapon and shuffle it into its owner's library instead. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Battlefield Forge | handled |  |  | Y/Y/- | not_tested |
| Caves of Koilos | handled |  |  | Y/Y/- | not_tested |
| Goblin Ringleader | handled | When this creature enters, reveal the top four cards of your library. Put all Goblin cards revealed this way into your hand and the rest on the bottom of your l | the engine reads this text and performs it | Y/Y/- | not_tested |
| Lay of the Land | handled | Search your library for a basic land card, reveal it, put it into your hand, then shuffle. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Lightning Angel | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Llanowar Wastes | handled |  |  | Y/Y/- | not_tested |
| Mystic Snake | handled | When this creature enters, counter target spell. | the engine reads this text and performs it | Y/-/- | not_tested |
| Phyrexian Arena | handled | At the beginning of your upkeep, you draw a card and lose 1 life. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Phyrexian Gargantua | handled | When this creature enters, you draw two cards and you lose 2 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Smash | handled | Destroy target artifact. Draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Sylvan Messenger | handled | When this creature enters, reveal the top four cards of your library. Put all Elf cards revealed this way into your hand and the rest on the bottom of your libr | the engine reads this text and performs it | Y/Y/- | not_tested |
| Vindicate | handled | Destroy target permanent. | the engine reads this text and performs it | Y/-/- | not_tested |
| Yavimaya Coast | handled |  |  | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>3 cards</summary>

- Fire // Ice
- Index
- Shivan Reef

</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| If a spell or ability an opponent controls causes you to discard this card, put it onto the battlefield with two +1/+1 counters on it instead of putting it into | Dodecapod | 1 |
| If Legacy Weapon would be put into a graveyard from anywhere, reveal Legacy Weapon and shuffle it into its owner's library instead. | Legacy Weapon | 1 |
| {R}, Sacrifice this creature: It deals 6 damage to each creature and each player. | Bloodfire Colossus | 1 |
| When this creature enters, destroy all other creatures you control. If it was kicked, destroy all other creatures instead. | Desolation Giant | 1 |
| When this creature enters, reveal the top four cards of your library. Put all creature cards of the chosen type revealed this way into your hand and the rest on | Brass Herald | 1 |

## Notes


