# The Dark (drk)

- Expansion: 006
- Set code: `drk`
- Release date: 1994-08-01
- Cards in scope (Modern/Pioneer/Standard-legal): 20

## Legality

| Format | Legal cards |
|---|---|
| Modern | 20 |
| Pioneer | 2 |
| Standard | 1 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 3 | 15.0% |
| Partial (unaudited) | 2 | 10.0% |
| Not tested (handled, untested) | 10 | 50.0% |
| Not working (silent / notice / error) | 5 | 25.0% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Inferno | silent | Inferno deals 6 damage to each creature and each player. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Mana Clash | silent | You and target opponent each flip a coin. Mana Clash deals 1 damage to each player whose coin comes up tails. Repeat this process until both players' coins come | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Spitting Slug | silent | Whenever this creature blocks or becomes blocked, you may pay {1}{G}. If you do, this creature gains first strike until end of turn. Otherwise, each creature bl | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Safe Haven | notice | At the beginning of your upkeep, you may sacrifice this land. If you do, return each card exiled with this land to the battlefield under its owner's control. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| War Barge | notice | {3}: Target creature gains islandwalk until end of turn. When this artifact leaves the battlefield this turn, destroy that creature. A creature destroyed this w | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Leviathan | unaudited | This creature enters tapped and doesn't untap during your untap step. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Uncle Istvan | unaudited | Prevent all damage that would be dealt to this creature by creatures. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Bog Imp | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Dark Heart of the Wood | handled | Sacrifice a Forest: You gain 3 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Elves of Deep Shadow | handled |  |  | Y/-/- | not_tested |
| Fellwar Stone | handled |  |  | Y/-/- | not_tested |
| Fountain of Youth | handled | {2}, {T}: You gain 1 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ghost Ship | handled | {U}{U}{U}: Regenerate this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Merfolk Assassin | handled | {T}: Destroy target creature with islandwalk. | the engine reads this text and performs it | Y/-/- | not_tested |
| Skull of Orm | handled | {5}, {T}: Return target enchantment card from your graveyard to your hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Squire | handled |  |  | Y/-/- | not_tested |
| Witch Hunter | handled | {T}: This creature deals 1 damage to target player or planeswalker. | the engine reads this text and performs it | Y/-/- | not_tested |

## Fully supported

<details>
<summary>3 cards</summary>

- Ball Lightning
- Blood Moon
- Tormod's Crypt

</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| At the beginning of your upkeep, you may sacrifice this land. If you do, return each card exiled with this land to the battlefield under its owner's control. | Safe Haven | 1 |
| Inferno deals 6 damage to each creature and each player. | Inferno | 1 |
| Prevent all damage that would be dealt to this creature by creatures. | Uncle Istvan | 1 |
| {3}: Target creature gains islandwalk until end of turn. When this artifact leaves the battlefield this turn, destroy that creature. A creature destroyed this w | War Barge | 1 |
| This creature enters tapped and doesn't untap during your untap step. | Leviathan | 1 |
| Whenever this creature blocks or becomes blocked, you may pay {1}{G}. If you do, this creature gains first strike until end of turn. Otherwise, each creature bl | Spitting Slug | 1 |
| You and target opponent each flip a coin. Mana Clash deals 1 damage to each player whose coin comes up tails. Repeat this process until both players' coins come | Mana Clash | 1 |

## Notes


