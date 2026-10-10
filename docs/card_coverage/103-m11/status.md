# Magic 2011 (m11)

- Expansion: 103
- Set code: `m11`
- Release date: 2010-07-16
- Cards in scope (Modern/Pioneer/Standard-legal): 105

## Legality

| Format | Legal cards |
|---|---|
| Modern | 105 |
| Pioneer | 36 |
| Standard | 3 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 20 | 19.0% |
| Works (untested) | 63 | 60.0% |
| Partial (unaudited) | 3 | 2.9% |
| Not working | 19 | 18.1% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Autumn's Veil | silent | Spells you control can't be countered by blue or black spells this turn, and creatures you control can't be the targets of blue or black spells this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Blood Tithe | silent | Each opponent loses 3 life. You gain life equal to the life lost this way. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Cyclops Gladiator | silent | Whenever this creature attacks, you may have it deal damage equal to its power to target creature defending player controls. If you do, that creature deals dama | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Elixir of Immortality | silent | {2}, {T}: You gain 5 life. Shuffle this artifact and your graveyard into their owner's library. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Gargoyle Sentinel | silent | {3}: Until end of turn, this creature loses defender and gains flying. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Hunters' Feast | silent | Any number of target players each gain 6 life. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Incite | silent | Target creature becomes red until end of turn and attacks this turn if able. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Jace's Erasure | silent | Whenever you draw a card, you may have target player mill a card. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Knight Exemplar | silent | Other Knight creatures you control get +1/+1 and have indestructible. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Mass Polymorph | silent | Exile all creatures you control, then reveal cards from the top of your library until you reveal that many creature cards. Put all creature cards revealed this  | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Merfolk Spy | silent | Whenever this creature deals combat damage to a player, that player reveals a card at random from their hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Necrotic Plague | silent | When enchanted creature dies, its controller chooses target creature one of their opponents controls. Return this card from its owner's graveyard to the battlef | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Phylactery Lich | silent | When you control no permanents with phylactery counters on them, sacrifice this creature. | the engine does not recognise this trigger's condition - it never triggers | Y/Y/- | not_working |
| Primal Cocoon | silent | At the beginning of your upkeep, put a +1/+1 counter on enchanted creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Redirect | silent | You may choose new targets for target spell. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Squadron Hawk | silent | When this creature enters, you may search your library for up to three cards named Squadron Hawk, reveal them, put them into your hand, then shuffle. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Steel Overseer | silent | {T}: Put a +1/+1 counter on each artifact creature you control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Stormtide Leviathan | silent | All lands are Islands in addition to their other types. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Wild Evocation | silent | At the beginning of each player's upkeep, that player reveals a card at random from their hand. If it's a land card, the player puts it onto the battlefield. Ot | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Angelic Arbiter | unaudited | Each opponent who cast a spell this turn can't attack with creatures. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Gaea's Revenge | unaudited | This creature can't be the target of nongreen spells or abilities from nongreen sources. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Obstinate Baloth | unaudited | If a spell or ability an opponent controls causes you to discard this card, put it onto the battlefield instead of putting it into your graveyard. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Air Servant | handled | {2}{U}: Tap target creature with flying. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Ajani's Pridemate | handled | Whenever you gain life, put a +1/+1 counter on this creature. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Ancient Hellkite | handled | {R}: This creature deals 1 damage to target creature defending player controls. Activate only if this creature is attacking. | the engine reads this text and performs it | Y/-/- | not_tested |
| Arc Runner | handled | At the beginning of the end step, sacrifice this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Armored Cancrix | handled |  |  | Y/Y/- | not_tested |
| Assault Griffin | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Augury Owl | handled | When this creature enters, scry 3. | the engine reads this text and performs it | Y/-/- | not_tested |
| Back to Nature | handled | Destroy all enchantments. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Barony Vampire | handled |  |  | Y/Y/- | not_tested |
| Brindle Boar | handled | Sacrifice this creature: You gain 4 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Call to Mind | handled | Return target instant or sorcery card from your graveyard to your hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Chandra's Spitfire | handled | Whenever an opponent is dealt noncombat damage, this creature gets +3/+0 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Cloud Crusader | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Crystal Ball | handled | {1}, {T}: Scry 2. | the engine reads this text and performs it | Y/-/- | not_tested |
| Dark Tutelage | handled | At the beginning of your upkeep, reveal the top card of your library and put that card into your hand. You lose life equal to its mana value. | the engine reads this text and performs it | Y/-/- | not_tested |
| Demon of Death's Gate | handled | You may pay 6 life and sacrifice three black creatures rather than pay this spell's mana cost. | the engine reads this text and performs it | Y/-/- | not_tested |
| Destructive Force | handled | Each player sacrifices five lands of their choice. Destructive Force deals 5 damage to each creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Diminish | handled | Target creature has base power and toughness 1/1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Dryad's Favor | handled | Enchanted creature has forestwalk. | the engine reads this text and performs it | Y/-/- | not_tested |
| Earth Servant | handled | This creature gets +0/+1 for each Mountain you control. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ember Hauler | handled | {1}, Sacrifice this creature: It deals 2 damage to any target. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Fauna Shaman | handled | {G}, {T}, Discard a creature card: Search your library for a creature card, reveal it, put it into your hand, then shuffle. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Garruk's Companion | handled | Trample | machines/combat.py | Y/-/- | not_tested |
| Garruk's Packleader | handled | Whenever another creature you control with power 3 or greater enters, you may draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Grave Titan | handled | Whenever this creature enters or attacks, create two 2/2 black Zombie creature tokens. | the engine reads this text and performs it | Y/-/- | not_tested |
| Greater Basilisk | handled | Deathtouch | machines/combat.py | Y/-/- | not_tested |
| Hoarding Dragon | handled | When this creature enters, you may search your library for an artifact card, exile it, then shuffle. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Hornet Sting | handled | Hornet Sting deals 1 damage to any target. | the engine reads this text and performs it | Y/-/- | not_tested |
| Inspired Charge | handled | Creatures you control get +2/+1 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Jace's Ingenuity | handled | Draw three cards. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Leyline of Anticipation | handled | If this card is in your opening hand, you may begin the game with it on the battlefield. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Leyline of Vitality | handled | If this card is in your opening hand, you may begin the game with it on the battlefield. | the engine reads this text and performs it | Y/-/- | not_tested |
| Liliana's Caress | handled | Whenever an opponent discards a card, that player loses 2 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Liliana's Specter | handled | When this creature enters, each opponent discards a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Manic Vandal | handled | When this creature enters, destroy target artifact. | the engine reads this text and performs it | Y/-/- | not_tested |
| Maritime Guard | handled |  |  | Y/Y/- | not_tested |
| Mighty Leap | handled | Target creature gets +2/+2 and gains flying until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Mitotic Slime | handled | When this creature dies, create two 2/2 green Ooze creature tokens. They have "When this token dies, create two 1/1 green Ooze creature tokens." | the engine reads this text and performs it | Y/-/- | not_tested |
| Mystifying Maze | handled | {4}, {T}: Exile target attacking creature an opponent controls. At the beginning of the next end step, return it to the battlefield tapped under its owner's con | the engine reads this text and performs it | Y/-/- | not_tested |
| Nether Horror | handled |  |  | Y/-/- | not_tested |
| Nightwing Shade | handled | {1}{B}: This creature gets +1/+1 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Overwhelming Stampede | handled | Until end of turn, creatures you control gain trample and get +X/+X, where X is the greatest power among creatures you control. | the engine reads this text and performs it | Y/-/- | not_tested |
| Phantom Beast | handled | When this creature becomes the target of a spell or ability, sacrifice it. | the engine reads this text and performs it | Y/-/- | not_tested |
| Quag Sickness | handled | Enchanted creature gets -1/-1 for each Swamp you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Roc Egg | handled | When this creature dies, create a 3/3 white Bird creature token with flying. | the engine reads this text and performs it | Y/-/- | not_tested |
| Rotting Legion | handled | This creature enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Sacred Wolf | handled | Hexproof | machines/casting.py (target legality) | Y/-/- | not_tested |
| Scroll Thief | handled | Whenever this creature deals combat damage to a player, draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Stabbing Pain | handled | Target creature gets -1/-1 until end of turn. Tap that creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Stone Golem | handled |  |  | Y/Y/- | not_tested |
| Sun Titan | handled | Whenever this creature enters or attacks, you may return target permanent card with mana value 3 or less from your graveyard to the battlefield. | the engine reads this text and performs it | Y/-/- | not_tested |
| Sword of Vengeance | handled | Equipped creature gets +2/+0 and has first strike, vigilance, trample, and haste. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Sylvan Ranger | handled | When this creature enters, you may search your library for a basic land card, reveal it, put it into your hand, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Temple Bell | handled | {T}: Each player draws a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Thunder Strike | handled | Target creature gets +2/+0 and gains first strike until end of turn. (It deals combat damage before creatures without first strike.) | the engine reads this text and performs it | Y/Y/- | not_tested |
| Time Reversal | handled | Each player shuffles their hand and graveyard into their library, then draws seven cards. Exile Time Reversal. | the engine reads this text and performs it | Y/-/- | not_tested |
| Tireless Missionaries | handled | When this creature enters, you gain 3 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Viscera Seer | handled | Sacrifice a creature: Scry 1. | the engine reads this text and performs it | Y/-/- | not_tested |
| Volcanic Strength | handled | Enchanted creature gets +2/+2 and has mountainwalk. | the engine reads this text and performs it | Y/-/- | not_tested |
| Wall of Vines | handled | Reach | machines/combat.py | Y/Y/- | not_tested |
| War Priest of Thune | handled | When this creature enters, you may destroy target enchantment. | the engine reads this text and performs it | Y/-/- | not_tested |
| Warlord's Axe | handled | Equipped creature gets +3/+1. | the engine reads this text and performs it | Y/-/- | not_tested |
| Water Servant | handled | {U}: This creature gets +1/-1 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>20 cards</summary>

- Aether Adept
- Ajani's Mantra
- Bloodcrazed Goblin
- Brittle Effigy
- Captivating Vampire
- Combust
- Conundrum Sphinx
- Cultivate
- Fire Servant
- Frost Titan
- Harbor Serpent
- Inferno Titan
- Leyline of Punishment
- Leyline of Sanctity
- Preordain
- Primeval Titan
- Pyretic Ritual
- Reverberate
- Serra Ascendant
- Vengeful Archon

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| all lands are islands in addition to their other types. | 1 | Stormtide Leviathan | m11 |
| any number of target players each gain N life. | 1 | Hunters' Feast | m11 |
| at the beginning of each player"..."s a land card, the player puts it onto the battlefield. otherwise, the player casts it without paying its mana cost if able. | 1 | Wild Evocation | m11 |
| at the beginning of your upkeep, put a +N/+N counter on enchanted creature. | 1 | Primal Cocoon | m11 |
| each opponent loses N life. you gain life equal to the life lost ~. | 1 | Blood Tithe | m11 |
| each opponent who cast a spell ~ can't attack with creatures. | 1 | Angelic Arbiter | m11 |
| exile all creatures you control, then reveal cards from the top of your library until you reveal that many creature cards. put all creature cards revealed ~ ont | 1 | Mass Polymorph | m11 |
| if a spell or ability an opponent controls causes you to discard ~, put it onto the battlefield instead of putting it into your graveyard. | 1 | Obstinate Baloth | m11 |
| other knight creatures you control get +N/+N and have indestructible. | 1 | Knight Exemplar | m11 |
| spells you control can"..."t be the targets of blue or black spells ~. | 1 | Autumn's Veil | m11 |
| target creature becomes red until end of turn and attacks ~ if able. | 1 | Incite | m11 |
| when enchanted creature dies, its controller chooses target creature one of their opponents controls. return ~ from its owner's graveyard to the battlefield att | 1 | Necrotic Plague | m11 |
| when you control no permanents with phylactery counters on them, sacrifice ~. | 1 | Phylactery Lich | m11 |
| when ~ enters, you may search your library for up to three cards named ~, reveal them, put them into your hand, then shuffle. | 1 | Squadron Hawk | m11 |
| whenever you draw a card, you may have target player mill a card. | 1 | Jace's Erasure | m11 |
| whenever ~ attacks, you may have it deal damage equal to its power to target creature defending player controls. if you do, that creature deals damage equal to  | 1 | Cyclops Gladiator | m11 |
| whenever ~ deals combat damage to a player, that player reveals a card at random from their hand. | 1 | Merfolk Spy | m11 |
| you may choose new targets for target spell. | 1 | Redirect | m11 |
| {M}, {M}: you gain N life. shuffle ~ and your graveyard into their owner's library. | 1 | Elixir of Immortality | m11 |
| {M}: put a +N/+N counter on each artifact creature you control. | 1 | Steel Overseer | m11 |
| {M}: until end of turn, ~ loses defender and gains flying. | 1 | Gargoyle Sentinel | m11 |
| ~ can't be the target of nongreen spells or abilities from nongreen sources. | 1 | Gaea's Revenge | m11 |

## Notes


