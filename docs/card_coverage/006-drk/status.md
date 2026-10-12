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
| Tested | 6 | 30.0% |
| Works (untested) | 11 | 55.0% |
| Partial (unaudited) | 0 | 0.0% |
| Not working | 3 | 15.0% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Mana Clash | silent | You and target opponent each flip a coin. Mana Clash deals 1 damage to each player whose coin comes up tails. Repeat this process until both players' coins come | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Safe Haven | notice | At the beginning of your upkeep, you may sacrifice this land. If you do, return each card exiled with this land to the battlefield under its owner's control. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| War Barge | notice | {3}: Target creature gains islandwalk until end of turn. When this artifact leaves the battlefield this turn, destroy that creature. A creature destroyed this w | unparsed remainder: When this artifact leaves the battlefield this turn, destroy that creature. A creature destroyed this way can't be regenerated. | Y/-/- | not_working |
| Bog Imp | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Dark Heart of the Wood | handled | Sacrifice a Forest: You gain 3 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Elves of Deep Shadow | handled |  |  | Y/-/- | not_tested |
| Fellwar Stone | handled |  |  | Y/-/- | not_tested |
| Fountain of Youth | handled | {2}, {T}: You gain 1 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ghost Ship | handled | {U}{U}{U}: Regenerate this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Merfolk Assassin | handled | {T}: Destroy target creature with islandwalk. | the engine reads this text and performs it | Y/-/- | not_tested |
| Skull of Orm | handled | {5}, {T}: Return target enchantment card from your graveyard to your hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Spitting Slug | handled | Whenever this creature blocks or becomes blocked, you may pay {1}{G}. If you do, this creature gains first strike until end of turn. Otherwise, each creature bl | the engine reads this text and performs it | Y/-/- | not_tested |
| Squire | handled |  |  | Y/-/- | not_tested |
| Witch Hunter | handled | {T}: This creature deals 1 damage to target player or planeswalker. | the engine reads this text and performs it | Y/-/- | not_tested |

## Fully supported

<details>
<summary>6 cards</summary>

- Ball Lightning
- Blood Moon
- Inferno
- Leviathan
- Tormod's Crypt
- Uncle Istvan

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| at the beginning of your upkeep, you may sacrifice ~. if you do, return each card exiled with ~ to the battlefield under its owner's control. | 1 | Safe Haven | drk |
| you and target opponent each flip a coin. ~ deals N damage to each player whose coin comes up tails. repeat ~ until both players' coins come up heads on the sam | 1 | Mana Clash | drk |
| {M}: target creature gains islandwalk until end of turn. when ~ leaves the battlefield ~, destroy that creature. a creature destroyed ~ can't be regenerated. | 1 | War Barge | drk |

## Notes


