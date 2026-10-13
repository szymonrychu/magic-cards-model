# Mercadian Masques (mmq)

- Expansion: 029
- Set code: `mmq`
- Release date: 1999-10-04
- Cards in scope (Modern/Pioneer/Standard-legal): 46

## Legality

| Format | Legal cards |
|---|---|
| Modern | 46 |
| Pioneer | 5 |
| Standard | 0 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 11 | 23.9% |
| Works (untested) | 26 | 56.5% |
| Partial (unaudited) | 0 | 0.0% |
| Not working | 9 | 19.6% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Bribery | silent | Search target opponent's library for a creature card and put that card onto the battlefield under your control. Then that player shuffles. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Cowardice | silent | Whenever a creature becomes the target of a spell or ability, return that creature to its owner's hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Hunted Wumpus | silent | When this creature enters, each other player may put a creature card from their hand onto the battlefield. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Natural Affinity | silent | All lands become 2/2 creatures until end of turn. They're still lands. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Nether Spirit | silent | At the beginning of your upkeep, if this card is the only creature card in your graveyard, you may return this card to the battlefield. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Noble Purpose | silent | Whenever a creature you control deals combat damage, you gain that much life. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Story Circle | silent | {W}: The next time a source of your choice of the chosen color would deal damage to you this turn, prevent that damage. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Thieves' Auction | silent | Exile all nontoken permanents. Starting with you, each player chooses one of the exiled cards and puts it onto the battlefield tapped under their control. Repea | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Deathgazer | notice | Whenever this creature blocks or becomes blocked by a nonblack creature, destroy that creature at end of combat. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Arms Dealer | handled | {1}{R}, Sacrifice a Goblin: This creature deals 4 damage to target creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ballista Squad | handled | {X}{W}, {T}: This creature deals X damage to target attacking or blocking creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Battle Rampart | handled | {T}: Target creature gains haste until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Cinder Elemental | handled | {X}{R}, {T}, Sacrifice this creature: It deals X damage to any target. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Coastal Piracy | handled | Whenever a creature you control deals combat damage to an opponent, you may draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Collective Unconscious | handled | Draw a card for each creature you control. | the engine reads this text and performs it | Y/-/- | not_tested |
| Crossbow Infantry | handled | {T}: This creature deals 1 damage to target attacking or blocking creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Deepwood Ghoul | handled | Pay 2 life: Regenerate this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Dehydration | handled | Enchanted creature doesn't untap during its controller's untap step. | the engine reads this text and performs it | Y/-/- | not_tested |
| Groundskeeper | handled | {1}{G}: Return target basic land card from your graveyard to your hand. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Highway Robber | handled | When this creature enters, target opponent loses 2 life and you gain 2 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Horned Troll | handled | {G}: Regenerate this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Larceny | handled | Whenever a creature you control deals combat damage to a player, that player discards a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Magistrate's Scepter | handled | {4}, {T}: Put a charge counter on this artifact. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Primeval Shambler | handled | {B}: This creature gets +1/+1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Revive | handled | Return target green card from your graveyard to your hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Rock Badger | handled | Landwalk | no code needed | Y/-/- | not_tested |
| Rushwood Dryad | handled | Landwalk | no code needed | Y/-/- | not_tested |
| Shock Troops | handled | Sacrifice this creature: It deals 2 damage to any target. | the engine reads this text and performs it | Y/-/- | not_tested |
| Sizzle | handled | Sizzle deals 3 damage to each opponent. | the engine reads this text and performs it | Y/-/- | not_tested |
| Squee, Goblin Nabob | handled | At the beginning of your upkeep, you may return this card from your graveyard to your hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Steadfast Guard | handled | Vigilance | machines/combat.py | Y/-/- | not_tested |
| Tidal Kraken | handled | This creature can't be blocked. | the engine reads this text and performs it | Y/-/- | not_tested |
| Trade Routes | handled | {1}: Return target land you control to its owner's hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Undertaker | handled | {B}, {T}, Discard a card: Return target creature card from your graveyard to your hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Vine Trellis | handled | Defender | machines/combat.py | Y/-/- | not_tested |

## Fully supported

<details>
<summary>11 cards</summary>

- Arrest
- Cho-Manno, Revolutionary
- Cloud Sprite
- Conspiracy
- Distorting Lens
- Ivory Mask
- Last Breath
- Midnight Ritual
- Sever Soul
- Two-Headed Dragon
- Vendetta

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| all lands become N/N creatures until end of turn. they're still lands. | 1 | Natural Affinity | mmq |
| at the beginning of your upkeep, if ~ is the only creature card in your graveyard, you may return ~ to the battlefield. | 1 | Nether Spirit | mmq |
| exile all nontoken permanents. starting with you, each player chooses one of the exiled cards and puts it onto the battlefield tapped under their control. repea | 1 | Thieves' Auction | mmq |
| search target opponent's library for a creature card and put that card onto the battlefield under your control. then that player shuffles. | 1 | Bribery | mmq |
| when ~ enters, each other player may put a creature card from their hand onto the battlefield. | 1 | Hunted Wumpus | mmq |
| whenever a creature becomes the target of a spell or ability, return that creature to its owner's hand. | 1 | Cowardice | mmq |
| whenever a creature you control deals combat damage, you gain that much life. | 1 | Noble Purpose | mmq |
| whenever ~ blocks or becomes blocked by a nonblack creature, destroy that creature at end of combat. | 1 | Deathgazer | mmq |
| {M}: the next time a source of your choice of the chosen color would deal damage to you ~, prevent that damage. | 1 | Story Circle | mmq |

## Notes


