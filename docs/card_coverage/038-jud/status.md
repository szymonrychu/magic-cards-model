# Judgment (jud)

- Expansion: 038
- Set code: `jud`
- Release date: 2002-05-27
- Cards in scope (Modern/Pioneer/Standard-legal): 20

## Legality

| Format | Legal cards |
|---|---|
| Modern | 20 |
| Pioneer | 2 |
| Standard | 0 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 1 | 5.0% |
| Works (untested) | 8 | 40.0% |
| Partial (unaudited) | 2 | 10.0% |
| Not working | 9 | 45.0% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Ancestor's Chosen | silent | When this creature enters, you gain 1 life for each card in your graveyard. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Browbeat | silent | Any player may have Browbeat deal 5 damage to them. If no one does, target player draws three cards. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Chastise | silent | Destroy target attacking creature. You gain life equal to its power. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Fledgling Dragon | silent | Threshold — As long as there are seven or more cards in your graveyard, this creature gets +3/+3 and has "{R}: This creature gets +1/+0 until end of turn." | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Nomad Mythmaker | silent | {W}, {T}: Put target Aura card from a graveyard onto the battlefield under your control attached to a creature you control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Scalpelexis | silent | Whenever this creature deals combat damage to a player, that player exiles the top four cards of their library. If two or more of those cards have the same name | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Cephalid Constable | notice | Whenever this creature deals combat damage to a player, return up to that many target permanents that player controls to their owner's hand. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Valor | notice | As long as this card is in your graveyard and you control a Plains, creatures you control have first strike. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Wonder | notice | As long as this card is in your graveyard and you control an Island, creatures you control have flying. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Solitary Confinement | unaudited | Skip your draw step. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Sutured Ghoul | unaudited | As this creature enters, exile any number of creature cards from your graveyard. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Arcane Teachings | handled | Enchanted creature gets +2/+2 and has "{T}: This creature deals 1 damage to any target." | the engine reads this text and performs it | Y/-/- | not_tested |
| Battle Screech | handled | Create two 1/1 white Bird creature tokens with flying. Flashback—Tap three untapped white creatures you control. (You may cast this card from your graveyard for | the engine reads this text and performs it | Y/-/- | not_tested |
| Genesis | handled | At the beginning of your upkeep, if this creature is in your graveyard, you may pay {2}{G}. If you do, return target creature card from your graveyard to your h | the engine reads this text and performs it | Y/-/- | not_tested |
| Ironshell Beetle | handled | When this creature enters, put a +1/+1 counter on target creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Mirari's Wake | handled | Creatures you control get +1/+1. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ray of Revelation | handled | Destroy target enchantment. Flashback {G} (You may cast this card from your graveyard for its flashback cost. Then exile it.) | the engine reads this text and performs it | Y/-/- | not_tested |
| Suntail Hawk | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Sylvan Safekeeper | handled | Sacrifice a land: Target creature you control gains shroud until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |

## Fully supported

<details>
<summary>1 cards</summary>

- Lava Dart

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| Threshold | 1 | Fledgling Dragon | jud |
| any player may have ~ deal N damage to them. if no one does, target player draws three cards. | 1 | Browbeat | jud |
| as long as ~ is in your graveyard and you control a plains, creatures you control have first strike. | 1 | Valor | jud |
| as long as ~ is in your graveyard and you control an island, creatures you control have flying. | 1 | Wonder | jud |
| as ~ enters, exile any number of creature cards from your graveyard. | 1 | Sutured Ghoul | jud |
| destroy target attacking creature. you gain life equal to its power. | 1 | Chastise | jud |
| skip your draw step. | 1 | Solitary Confinement | jud |
| when ~ enters, you gain N life for each card in your graveyard. | 1 | Ancestor's Chosen | jud |
| whenever ~ deals combat damage to a player, return up to that many target permanents that player controls to their owner's hand. | 1 | Cephalid Constable | jud |
| whenever ~ deals combat damage to a player, that player exiles the top four cards of their library. if two or more of those cards have the same name, repeat ~. | 1 | Scalpelexis | jud |
| {M}, {M}: put target aura card from a graveyard onto the battlefield under your control attached to a creature you control. | 1 | Nomad Mythmaker | jud |

## Notes


