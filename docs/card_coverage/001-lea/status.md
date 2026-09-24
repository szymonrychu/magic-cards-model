# Limited Edition Alpha (lea)

- Expansion: 001
- Set code: `lea`
- Release date: 1993-08-05
- Cards in scope (Modern/Pioneer/Standard-legal): 116

## Legality

| Format | Legal cards |
|---|---|
| Modern | 116 |
| Pioneer | 33 |
| Standard | 14 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 24 | 20.7% |
| Works (untested) | 59 | 50.9% |
| Partial (unaudited) | 5 | 4.3% |
| Not working | 28 | 24.1% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Bad Moon | silent | Black creatures get +1/+1. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Blessing | silent | {W}: Enchanted creature gets +1/+1 until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Circle of Protection: Blue | silent | {1}: The next time a blue source of your choice would deal damage to you this turn, prevent that damage. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Circle of Protection: Green | silent | {1}: The next time a green source of your choice would deal damage to you this turn, prevent that damage. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Circle of Protection: Red | silent | {1}: The next time a red source of your choice would deal damage to you this turn, prevent that damage. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Circle of Protection: White | silent | {1}: The next time a white source of your choice would deal damage to you this turn, prevent that damage. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Dingus Egg | silent | Whenever a land is put into a graveyard from the battlefield, this artifact deals 2 damage to that land's controller. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Earthquake | silent | Earthquake deals X damage to each creature without flying and each player. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Evil Presence | silent | Enchanted land is a Swamp. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Firebreathing | silent | {R}: Enchanted creature gets +1/+0 until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Flashfires | silent | Destroy all Plains. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Force of Nature | silent | At the beginning of your upkeep, this creature deals 8 damage to you unless you pay {G}{G}{G}{G}. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Gaea's Liege | silent | As long as Gaea's Liege isn't attacking, its power and toughness are each equal to the number of Forests you control. As long as Gaea's Liege is attacking, its  | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Goblin King | silent | Other Goblins get +1/+1 and have mountainwalk. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Hurricane | silent | Hurricane deals X damage to each creature with flying and each player. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Hypnotic Specter | silent | Whenever this creature deals damage to an opponent, that player discards a card at random. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Jade Statue | silent | {2}: This artifact becomes a 3/6 Golem artifact creature until end of combat. Activate only during combat. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Lord of Atlantis | silent | Other Merfolk get +1/+1 and have islandwalk. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Lord of the Pit | silent | At the beginning of your upkeep, sacrifice a creature other than this creature. If you can't, this creature deals 7 damage to you. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Orcish Artillery | silent | {T}: This creature deals 2 damage to any target and 3 damage to you. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Pirate Ship | silent | When you control no Islands, sacrifice this creature. | the engine does not recognise this trigger's condition - it never triggers | Y/-/- | not_working |
| Psionic Blast | silent | Psionic Blast deals 4 damage to any target and 2 damage to you. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Regeneration | silent | {G}: Regenerate enchanted creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Reverse Damage | silent | The next time a source of your choice would deal damage to you this turn, prevent that damage. You gain life equal to the damage prevented this way. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Cockatrice | notice | Whenever this creature blocks or becomes blocked by a non-Wall creature, destroy that creature at end of combat. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Disintegrate | notice | Disintegrate deals X damage to any target. If it's a creature, it can't be regenerated this turn, and if it would die this turn, exile it instead. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Dragon Whelp | notice | {R}: This creature gets +1/+0 until end of turn. If this ability has been activated four or more times this turn, sacrifice this creature at the beginning of th | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Stone Giant | notice | {T}: Target creature you control with toughness less than this creature's power gains flying until end of turn. Destroy that creature at the beginning of the ne | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Consecrate Land | unaudited | Enchanted land has indestructible and can't be enchanted by other Auras. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Fear | unaudited | Enchanted creature has fear. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Invisibility | unaudited | Enchanted creature can't be blocked except by Walls. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Juggernaut | unaudited | This creature can't be blocked by Walls. | a static ability no support check audits - not verified either way | Y/Y/Y | partial |
| Lure | unaudited | All creatures able to block enchanted creature do so. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Air Elemental | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Black Knight | handled | First strike | machines/combat.py | Y/-/- | not_tested |
| Bog Wraith | handled | Landwalk | no code needed | Y/-/- | not_tested |
| Crystal Rod | handled | Whenever a player casts a blue spell, you may pay {1}. If you do, you gain 1 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Disenchant | handled | Destroy target artifact or enchantment. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Disrupting Scepter | handled | {3}, {T}: Target player discards a card. Activate only during your turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Drudge Skeletons | handled | {B}: Regenerate this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Dwarven Demolition Team | handled | {T}: Destroy target Wall. | the engine reads this text and performs it | Y/-/- | not_tested |
| Earth Elemental | handled |  |  | Y/-/- | not_tested |
| Fire Elemental | handled |  |  | Y/Y/Y | not_tested |
| Flight | handled | Enchanted creature has flying. | the engine reads this text and performs it | Y/-/- | not_tested |
| Fungusaur | handled | Whenever this creature is dealt damage, put a +1/+1 counter on it. | the engine reads this text and performs it | Y/-/- | not_tested |
| Goblin Balloon Brigade | handled | {R}: This creature gains flying until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Healing Salve | handled | Choose one — • Target player gains 3 life. • Prevent the next 3 damage that would be dealt to any target this turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Holy Strength | handled | Enchanted creature gets +1/+2. | the engine reads this text and performs it | Y/-/- | not_tested |
| Howling Mine | handled | At the beginning of each player's draw step, if this artifact is untapped, that player draws an additional card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Iron Star | handled | Whenever a player casts a red spell, you may pay {1}. If you do, you gain 1 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ivory Cup | handled | Whenever a player casts a white spell, you may pay {1}. If you do, you gain 1 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Jayemdae Tome | handled | {4}, {T}: Draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Jump | handled | Target creature gains flying until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ley Druid | handled | {T}: Untap target land. | the engine reads this text and performs it | Y/-/- | not_tested |
| Mahamoti Djinn | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Manabarbs | handled | Whenever a player taps a land for mana, this enchantment deals 1 damage to that player. | the engine reads this text and performs it | Y/-/- | not_tested |
| Merfolk of the Pearl Trident | handled |  |  | Y/-/- | not_tested |
| Nevinyrral's Disk | handled | This artifact enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Nightmare | handled | Nightmare's power and toughness are each equal to the number of Swamps you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Prodigal Sorcerer | handled | {T}: This creature deals 1 damage to any target. | the engine reads this text and performs it | Y/-/- | not_tested |
| Regrowth | handled | Return target card from your graveyard to your hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Resurrection | handled | Return target creature card from your graveyard to the battlefield. | the engine reads this text and performs it | Y/-/- | not_tested |
| Righteousness | handled | Target blocking creature gets +7/+7 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Rod of Ruin | handled | {3}, {T}: This artifact deals 1 damage to any target. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Royal Assassin | handled | {T}: Destroy target tapped creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Samite Healer | handled | {T}: Prevent the next 1 damage that would be dealt to any target this turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Scathe Zombies | handled |  |  | Y/-/- | not_tested |
| Sengir Vampire | handled | Whenever a creature dealt damage by this creature this turn dies, put a +1/+1 counter on this creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Shatter | handled | Destroy target artifact. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Shivan Dragon | handled | {R}: This creature gets +1/+0 until end of turn. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Spell Blast | handled | Counter target spell with mana value X. (For example, if that spell's mana cost is {3}{U}{U}, X is 5.) | the engine reads this text and performs it | Y/Y/- | not_tested |
| Steal Artifact | handled | You control enchanted artifact. | the engine reads this text and performs it | Y/-/- | not_tested |
| Stone Rain | handled | Destroy target land. | the engine reads this text and performs it | Y/-/- | not_tested |
| Stream of Life | handled | Target player gains X life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Terror | handled | Destroy target nonartifact, nonblack creature. It can't be regenerated. | the engine reads this text and performs it | Y/-/- | not_tested |
| The Hive | handled | {5}, {T}: Create a 1/1 colorless Insect artifact creature token with flying named Wasp. | the engine reads this text and performs it | Y/-/- | not_tested |
| Throne of Bone | handled | Whenever a player casts a black spell, you may pay {1}. If you do, you gain 1 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Twiddle | handled | You may tap or untap target artifact, creature, or land. | the engine reads this text and performs it | Y/-/- | not_tested |
| Unholy Strength | handled | Enchanted creature gets +2/+1. | the engine reads this text and performs it | Y/-/- | not_tested |
| Uthden Troll | handled | {R}: Regenerate this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Verduran Enchantress | handled | Whenever you cast an enchantment spell, you may draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Wall of Air | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Wall of Bone | handled | {B}: Regenerate this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Wall of Fire | handled | {R}: This creature gets +1/+0 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Wall of Stone | handled | Defender | machines/combat.py | Y/-/- | not_tested |
| Wall of Swords | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Wall of Wood | handled | Defender | machines/combat.py | Y/-/- | not_tested |
| Weakness | handled | Enchanted creature gets -2/-1. | the engine reads this text and performs it | Y/-/- | not_tested |
| Web | handled | Enchanted creature gets +0/+2 and has reach. | the engine reads this text and performs it | Y/-/- | not_tested |
| White Knight | handled | First strike | machines/combat.py | Y/-/- | not_tested |
| Will-o'-the-Wisp | handled | {B}: Regenerate this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Wooden Sphere | handled | Whenever a player casts a green spell, you may pay {1}. If you do, you gain 1 life. | the engine reads this text and performs it | Y/-/- | not_tested |

## Fully supported

<details>
<summary>24 cards</summary>

- Birds of Paradise
- Clone
- Counterspell
- Craw Wurm
- Fireball
- Fog
- Forest
- Giant Growth
- Giant Spider
- Grizzly Bears
- Hill Giant
- Icy Manipulator
- Island
- Karma
- Lightning Bolt
- Llanowar Elves
- Mountain
- Plains
- Raise Dead
- Savannah Lions
- Serra Angel
- Swamp
- Unsummon
- Wrath of God

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| {M}: enchanted creature gets +N/+N until end of turn. | 2 | Blessing, Firebreathing | lea |
| all creatures able to block enchanted creature do so. | 1 | Lure | lea |
| as long as ~ isn't attacking, its power and toughness are each equal to the number of forests you control. as long as ~ is attacking, its power and toughness ar | 1 | Gaea's Liege | lea |
| at the beginning of your upkeep, sacrifice a creature other than ~. if you can't, ~ deals N damage to you. | 1 | Lord of the Pit | lea |
| at the beginning of your upkeep, ~ deals N damage to you unless you pay {M}{M}{M}{M}. | 1 | Force of Nature | lea |
| black creatures get +N/+N. | 1 | Bad Moon | lea |
| destroy all plains. | 1 | Flashfires | lea |
| enchanted creature can't be blocked except by walls. | 1 | Invisibility | lea |
| enchanted creature has ~. | 1 | Fear | lea |
| enchanted land has indestructible and can't be enchanted by other auras. | 1 | Consecrate Land | lea |
| enchanted land is a swamp. | 1 | Evil Presence | lea |
| other goblins get +N/+N and have mountainwalk. | 1 | Goblin King | lea |
| other merfolk get +N/+N and have islandwalk. | 1 | Lord of Atlantis | lea |
| the next time a source of your choice would deal damage to you ~, prevent that damage. you gain life equal to the damage prevented ~. | 1 | Reverse Damage | lea |
| when you control no islands, sacrifice ~. | 1 | Pirate Ship | lea |
| whenever a land is put into a graveyard from the battlefield, ~ deals N damage to that land's controller. | 1 | Dingus Egg | lea |
| whenever ~ blocks or becomes blocked by a non-wall creature, destroy that creature at end of combat. | 1 | Cockatrice | lea |
| whenever ~ deals damage to an opponent, that player discards a card at random. | 1 | Hypnotic Specter | lea |
| {M}: regenerate enchanted creature. | 1 | Regeneration | lea |
| {M}: target creature you control with toughness less than ~ power gains flying until end of turn. destroy that creature at the beginning of the next end step. | 1 | Stone Giant | lea |
| {M}: the next time a blue source of your choice would deal damage to you ~, prevent that damage. | 1 | Circle of Protection: Blue | lea |
| {M}: the next time a green source of your choice would deal damage to you ~, prevent that damage. | 1 | Circle of Protection: Green | lea |
| {M}: the next time a red source of your choice would deal damage to you ~, prevent that damage. | 1 | Circle of Protection: Red | lea |
| {M}: the next time a white source of your choice would deal damage to you ~, prevent that damage. | 1 | Circle of Protection: White | lea |
| {M}: ~ becomes a N/N golem artifact creature until end of combat. activate only during combat. | 1 | Jade Statue | lea |
| {M}: ~ deals N damage to any target and N damage to you. | 1 | Orcish Artillery | lea |
| {M}: ~ gets +N/+N until end of turn. if ~ has been activated four or more times ~, sacrifice ~ at the beginning of the next end step. | 1 | Dragon Whelp | lea |
| ~ can't be blocked by walls. | 1 | Juggernaut | lea |
| ~ deals N damage to any target and N damage to you. | 1 | Psionic Blast | lea |
| ~ deals N damage to any target. if it"..."t be regenerated ~, and if it would die ~, exile it instead. | 1 | Disintegrate | lea |
| ~ deals N damage to each creature with flying and each player. | 1 | Hurricane | lea |
| ~ deals N damage to each creature without flying and each player. | 1 | Earthquake | lea |

## Notes


