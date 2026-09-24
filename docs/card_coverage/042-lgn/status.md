# Legions (lgn)

- Expansion: 042
- Set code: `lgn`
- Release date: 2003-02-03
- Cards in scope (Modern/Pioneer/Standard-legal): 16

## Legality

| Format | Legal cards |
|---|---|
| Modern | 16 |
| Pioneer | 1 |
| Standard | 0 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 0 | 0.0% |
| Partial (unaudited) | 2 | 12.5% |
| Not tested (handled, untested) | 9 | 56.2% |
| Not working (silent / notice / error) | 5 | 31.2% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Dreamborn Muse | silent | At the beginning of each player's upkeep, that player mills X cards, where X is the number of cards in their hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Essence Sliver | silent | Whenever a Sliver deals damage, its controller gains that much life. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Graveborn Muse | silent | At the beginning of your upkeep, you draw X cards and lose X life, where X is the number of Zombies you control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Krosan Cloudscraper | silent | At the beginning of your upkeep, sacrifice this creature unless you pay {G}{G}. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Phage the Untouchable | silent | When Phage enters, if you didn't cast it from your hand, you lose the game. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Mistform Ultimus | unaudited | Mistform Ultimus is every creature type . | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Seedborn Muse | unaudited | Untap all permanents you control during each other player's untap step. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Akroma, Angel of Wrath | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Enormous Baloth | handled |  |  | Y/-/- | not_tested |
| Flamewave Invoker | handled | {7}{R}: This creature deals 5 damage to target player or planeswalker. | the engine reads this text and performs it | Y/-/- | not_tested |
| Fugitive Wizard | handled |  |  | Y/Y/- | not_tested |
| Lavaborn Muse | handled | At the beginning of each opponent's upkeep, if that player has two or fewer cards in hand, this creature deals 3 damage to that player. | the engine reads this text and performs it | Y/-/- | not_tested |
| Merchant of Secrets | handled | When this creature enters, draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Starlight Invoker | handled | {7}{W}: You gain 5 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Willbender | handled | When this creature is turned face up, change the target of target spell or ability with a single target. | the engine reads this text and performs it | Y/-/- | not_tested |
| Windborn Muse | handled | Creatures can't attack you unless their controller pays {2} for each creature they control that's attacking you. | the engine reads this text and performs it | Y/-/- | not_tested |

## Fully supported

<details>
<summary>0 cards</summary>


</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| At the beginning of your upkeep, you draw X cards and lose X life, where X is the number of Zombies you control. | Graveborn Muse, Krosan Cloudscraper | 2 |
| At the beginning of each player's upkeep, that player mills X cards, where X is the number of cards in their hand. | Dreamborn Muse | 1 |
| Mistform Ultimus is every creature type . | Mistform Ultimus | 1 |
| Untap all permanents you control during each other player's untap step. | Seedborn Muse | 1 |
| When Phage enters, if you didn't cast it from your hand, you lose the game. | Phage the Untouchable | 1 |
| Whenever a Sliver deals damage, its controller gains that much life. | Essence Sliver | 1 |

## Notes


