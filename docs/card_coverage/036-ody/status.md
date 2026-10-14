# Odyssey (ody)

- Expansion: 036
- Set code: `ody`
- Release date: 2001-10-01
- Cards in scope (Modern/Pioneer/Standard-legal): 51

## Legality

| Format | Legal cards |
|---|---|
| Modern | 51 |
| Pioneer | 9 |
| Standard | 2 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 14 | 27.5% |
| Works (untested) | 32 | 62.7% |
| Partial (unaudited) | 0 | 0.0% |
| Not working | 5 | 9.8% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Aura Graft | silent | Gain control of target Aura that's attached to a permanent. Attach it to another permanent it can enchant. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Aven Windreader | silent | {1}{U}: Target player reveals the top card of their library. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Chance Encounter | silent | Whenever you win a coin flip, put a luck counter on this enchantment. | the engine does not recognise this trigger's condition - it never triggers | Y/-/- | not_working |
| Deluge | silent | Tap all creatures without flying. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Time Stretch | silent | Target player takes two extra turns after this one. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Afflict | handled | Target creature gets -1/-1 until end of turn. Draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Auramancer | handled | When this creature enters, you may return target enchantment card from your graveyard to your hand. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Aven Cloudchaser | handled | When this creature enters, destroy target enchantment. | the engine reads this text and performs it | Y/-/- | not_tested |
| Aven Fisher | handled | When this creature dies, you may draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Aven Flock | handled | {W}: This creature gets +0/+1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Blessed Orator | handled | Other creatures you control get +0/+1. | the engine reads this text and performs it | Y/-/- | not_tested |
| Braids, Cabal Minion | handled | At the beginning of each player's upkeep, that player sacrifices an artifact, creature, or land of their choice. | the engine reads this text and performs it | Y/-/- | not_tested |
| Call of the Herd | handled | Create a 3/3 green Elephant creature token. Flashback {3}{G} (You may cast this card from your graveyard for its flashback cost. Then exile it.) | the engine reads this text and performs it | Y/-/- | not_tested |
| Caustic Tar | handled | Enchanted land has "{T}: Target player loses 3 life." | the engine reads this text and performs it | Y/Y/- | not_tested |
| Cephalid Coliseum | handled | Threshold — {U}, {T}, Sacrifice this land: Target player draws three cards, then discards three cards. Activate only if there are seven or more cards in your gr | the engine reads this text and performs it | Y/-/- | not_tested |
| Concentrate | handled | Draw three cards. | the engine reads this text and performs it | Y/-/- | not_tested |
| Crypt Creeper | handled | Sacrifice this creature: Exile target card from a graveyard. | the engine reads this text and performs it | Y/-/- | not_tested |
| Demolish | handled | Destroy target artifact or land. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Deserted Temple | handled | {1}, {T}: Untap target land. | the engine reads this text and performs it | Y/-/- | not_tested |
| Dusk Imp | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Execute | handled | Destroy target white creature. It can't be regenerated. Draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Firebolt | handled | Firebolt deals 2 damage to any target. Flashback {4}{R} (You may cast this card from your graveyard for its flashback cost. Then exile it.) | the engine reads this text and performs it | Y/-/- | not_tested |
| Ivy Elemental | handled | This creature enters with X +1/+1 counters on it. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Kamahl, Pit Fighter | handled | {T}: Kamahl deals 3 damage to any target. | the engine reads this text and performs it | Y/-/- | not_tested |
| Mortivore | handled | Mortivore's power and toughness are each equal to the number of creature cards in all graveyards. | the engine reads this text and performs it | Y/-/- | not_tested |
| Mystic Enforcer | handled | Threshold — As long as there are seven or more cards in your graveyard, this creature gets +3/+3 and has flying. | the engine reads this text and performs it | Y/-/- | not_tested |
| Nantuko Disciple | handled | {G}, {T}: Target creature gets +2/+2 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Nimble Mongoose | handled | Threshold — This creature gets +2/+2 as long as there are seven or more cards in your graveyard. | the engine reads this text and performs it | Y/-/- | not_tested |
| Persuasion | handled | You control enchanted creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Puppeteer | handled | {U}, {T}: You may tap or untap target creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Reckless Charge | handled | Target creature gets +3/+0 and gains haste until end of turn. Flashback {2}{R} (You may cast this card from your graveyard for its flashback cost. Then exile it | the engine reads this text and performs it | Y/-/- | not_tested |
| Shadowmage Infiltrator | handled | Whenever this creature deals combat damage to a player, you may draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Shelter | handled | Target creature you control gains protection from the color of your choice until end of turn. Draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Squirrel Nest | handled | Enchanted land has "{T}: Create a 1/1 green Squirrel creature token." | the engine reads this text and performs it | Y/-/- | not_tested |
| Upheaval | handled | Return all permanents to their owners' hands. | the engine reads this text and performs it | Y/-/- | not_tested |
| Zombie Infestation | handled | Discard two cards: Create a 2/2 black Zombie creature token. | the engine reads this text and performs it | Y/-/- | not_tested |
| Zombify | handled | Return target creature card from your graveyard to the battlefield. | the engine reads this text and performs it | Y/Y/Y | not_tested |

## Fully supported

<details>
<summary>14 cards</summary>

- Barbarian Ring
- Battle of Wits
- Diabolic Tutor
- Ember Beast
- Ground Seal
- Haunting Echoes
- Magnivore
- Millikin
- Mindslicer
- Mirari
- Peek
- Squirrel Mob
- Syncopate
- Traumatize

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| gain control of target aura that's attached to a permanent. attach it to another permanent it can enchant. | 1 | Aura Graft | ody |
| tap all creatures without flying. | 1 | Deluge | ody |
| target player takes two extra turns after ~. | 1 | Time Stretch | ody |
| whenever you win a coin flip, put a luck counter on ~. | 1 | Chance Encounter | ody |
| {M}{M}: target player reveals the top card of their library. | 1 | Aven Windreader | ody |

## Notes


