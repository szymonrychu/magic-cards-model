# Planar Chaos (plc)

- Expansion: 072
- Set code: `plc`
- Release date: 2007-02-02
- Cards in scope (Modern/Pioneer/Standard-legal): 161

## Legality

| Format | Legal cards |
|---|---|
| Modern | 161 |
| Pioneer | 1 |
| Standard | 0 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 6 | 3.7% |
| Partial (unaudited) | 13 | 8.1% |
| Not tested (handled, untested) | 56 | 34.8% |
| Not working (silent / notice / error) | 86 | 53.4% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Aeon Chronicler | silent | Aeon Chronicler's power and toughness are each equal to the number of cards in your hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Auramancer's Guise | silent | Enchanted creature gets +2/+2 for each Aura attached to it and has vigilance. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Aven Riftwatcher | silent | Vanishing | no machine in the engine executes this keyword | Y/-/- | not_working |
| Battering Sliver | silent | All Sliver creatures have trample. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Benalish Commander | silent | Whenever a time counter is removed from this card while it's exiled, create a 1/1 white Soldier creature token. | the engine does not recognise this trigger's condition - it never triggers | Y/-/- | not_working |
| Bog Serpent | silent | When you control no Swamps, sacrifice this creature. | the engine does not recognise this trigger's condition - it never triggers | Y/-/- | not_working |
| Braids, Conjurer Adept | silent | At the beginning of each player's upkeep, that player may put an artifact, creature, or land card from their hand onto the battlefield. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Brain Gorgers | silent | When you cast this spell, any player may sacrifice a creature of their choice. If a player does, counter Brain Gorgers. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Calciderm | silent | Vanishing | no machine in the engine executes this keyword | Y/-/- | not_working |
| Chronozoa | silent | Vanishing | no machine in the engine executes this keyword | Y/-/- | not_working |
| Crovax, Ascendant Hero | silent | Other white creatures get +1/+1. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Dash Hopes | silent | When you cast this spell, any player may pay 5 life. If a player does, counter Dash Hopes. Counter target spell. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Deadly Grub | silent | When this creature dies, if it had no time counters on it, create a 6/1 green Insect creature token with shroud. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Deadwood Treefolk | silent | Vanishing | no machine in the engine executes this keyword | Y/-/- | not_working |
| Detritivore | silent | Detritivore's power and toughness are each equal to the number of nonbasic land cards in your opponents' graveyards. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Dichotomancy | silent | For each tapped nonland permanent target opponent controls, search that player's library for a card with the same name as that permanent. Put those cards onto t | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Dismal Failure | silent | Counter target spell. Its controller discards a card. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Dormant Sliver | silent | All Sliver creatures have defender. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Dust Corona | silent | Enchanted creature gets +2/+0 and can't be blocked by creatures with flying. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Dust Elemental | silent | When this creature enters, return three creatures you control to their owner's hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Enslave | silent | At the beginning of your upkeep, enchanted creature deals 1 damage to its owner. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Erratic Mutation | silent | Choose target creature. Reveal cards from the top of your library until you reveal a nonland card. That creature gets +X/-X until end of turn, where X is that c | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Extirpate | silent | Split second (As long as this spell is on the stack, players can't cast spells or activate abilities that aren't mana abilities.) Choose target card in a gravey | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Fa'adiyah Seer | silent | {T}: Draw a card and reveal it. If it isn't a land card, discard it. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Firefright Mage | silent | {1}{R}, {T}, Discard a card: Target creature can't be blocked this turn except by artifact creatures and/or red creatures. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Fungal Behemoth | silent | Fungal Behemoth's power and toughness are each equal to the number of +1/+1 counters on creatures you control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Hammerheim Deadeye | silent | Echo | no machine in the engine executes this keyword | Y/-/- | not_working |
| Hunting Wilds | silent | Kicker {3}{G} (You may pay an additional {3}{G} as you cast this spell.) Search your library for up to two Forest cards, put them onto the battlefield tapped, t | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Imp's Mischief | silent | Change the target of target spell with a single target. You lose life equal to that spell's mana value. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Intet, the Dreamer | silent | Whenever Intet deals combat damage to a player, you may pay {2}{U}. If you do, exile the top card of your library face down. You may look at that card for as lo | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Jodah's Avenger | silent | {0}: Until end of turn, this creature gets -1/-1 and gains your choice of double strike, protection from red, vigilance, or shadow. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Keldon Marauders | silent | Vanishing | no machine in the engine executes this keyword | Y/-/- | not_working |
| Kor Dirge | silent | All damage that would be dealt this turn to target creature you control by a source of your choice is dealt to another target creature instead. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Lavacore Elemental | silent | Vanishing | no machine in the engine executes this keyword | Y/-/- | not_working |
| Life and Limb | silent | All Forests and all Saprolings are 1/1 green Saproling creatures and Forest lands in addition to their other types. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Mantle of Leadership | silent | Whenever a creature enters, enchanted creature gets +2/+2 until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Melancholy | silent | At the beginning of your upkeep, sacrifice this Aura unless you pay {B}. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Merfolk Thaumaturgist | silent | {T}: Switch target creature's power and toughness until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Molten Firebird | silent | {4}{R}: Exile this creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Null Profusion | silent | Whenever you play a card, draw a card. | the engine does not recognise this trigger's condition - it never triggers | Y/-/- | not_working |
| Ovinize | silent | Until end of turn, target creature loses all abilities and has base power and toughness 0/1. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Pallid Mycoderm | silent | Sacrifice a Saproling: Each creature you control that's a Fungus or a Saproling gets +1/+1 until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Phantasmagorian | silent | When you cast this spell, any player may discard three cards. If a player does, counter Phantasmagorian. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Porphyry Nodes | silent | At the beginning of your upkeep, destroy the creature with the least power. It can't be regenerated. If two or more creatures are tied for least power, you choo | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Pyrohemia | silent | {R}: This enchantment deals 1 damage to each creature and each player. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Reality Acid | silent | When this Aura leaves the battlefield, enchanted permanent's controller sacrifices it. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Rebuff the Wicked | silent | Counter target spell that targets a permanent you control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Reflex Sliver | silent | All Sliver creatures have haste. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Retether | silent | Return each Aura card from your graveyard to the battlefield. Only creatures can be enchanted this way. (Aura cards that can't enchant a creature on the battlef | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Riftmarked Knight | silent | When the last time counter is removed from this card while it's exiled, create a 2/2 black Knight creature token with flanking, protection from white, and haste | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Roiling Horror | silent | Roiling Horror's power and toughness are each equal to your life total minus the life total of an opponent with the most life. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Serra's Boon | silent | Enchanted creature gets +1/+2 as long as it's white. Otherwise, it gets -2/-1. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Shaper Parasite | silent | When this creature is turned face up, target creature gets +2/-2 or -2/+2 until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Shivan Wumpus | silent | When this creature enters, any player may sacrifice a land of their choice. If a player does, put this creature on top of its owner's library. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Shrouded Lore | silent | Target opponent chooses a card in your graveyard. You may pay {B}. If you do, repeat this process except that opponent can't choose a card already chosen for Sh | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Sinew Sliver | silent | All Sliver creatures get +1/+1. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Sophic Centaur | silent | {2}{G}{G}, {T}, Discard a card: You gain 2 life for each card in your hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Spellshift | silent | Counter target instant or sorcery spell. Its controller reveals cards from the top of their library until they reveal an instant or sorcery card. That player ma | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Spitting Sliver | silent | All Sliver creatures have first strike. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Stingscourger | silent | Echo | no machine in the engine executes this keyword | Y/-/- | not_working |
| Stonecloaker | silent | When this creature enters, return a creature you control to its owner's hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Stormfront Riders | silent | When this creature enters, return two creatures you control to their owner's hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Sulfur Elemental | silent | White creatures get +1/-1. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Synchronous Sliver | silent | All Sliver creatures have vigilance. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Temporal Extortion | silent | When you cast this spell, any player may pay half their life, rounded up. If a player does, counter Temporal Extortion. Take an extra turn after this one. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Teneb, the Harvester | silent | Whenever Teneb deals combat damage to a player, you may pay {2}{B}. If you do, put target creature card from a graveyard onto the battlefield under your control | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Tidewalker | silent | Tidewalker's power and toughness are each equal to the number of time counters on it. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Timbermare | silent | When this creature enters, tap all other creatures. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Uktabi Drake | silent | Echo | no machine in the engine executes this keyword | Y/-/- | not_working |
| Vampiric Link | silent | Whenever enchanted creature deals damage, you gain that much life. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Veiling Oddity | silent | When the last time counter is removed from this card while it's exiled, creatures can't be blocked this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Venarian Glimmer | silent | Target player reveals their hand. You choose a nonland card with mana value X or less from it. That player discards that card. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Volcano Hellion | silent | When this creature enters, it deals an amount of damage of your choice to you and target creature. The damage can't be prevented. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Waning Wurm | silent | Vanishing | no machine in the engine executes this keyword | Y/-/- | not_working |
| Wild Pair | silent | Whenever a creature enters, if you cast it from your hand, you may search your library for a creature card with the same total power and toughness, put it onto  | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Ana Battlemage | notice | When this creature enters, if it was kicked with its {1}{B} kicker, tap target untapped creature and that creature deals damage equal to its power to its contro | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Blightspeaker | notice | {4}, {T}: Search your library for a Rebel permanent card with mana value 3 or less, put it onto the battlefield, then shuffle. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Dawn Charm | notice | Choose one — • Prevent all combat damage that would be dealt this turn. • Regenerate target creature. • Counter target spell that targets you. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Fatal Frenzy | notice | Until end of turn, target creature you control gains trample and gets +X/+0, where X is its power. Sacrifice it at the beginning of the next end step. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Fury Charm | notice | Choose one — • Destroy target artifact. • Target creature gets +1/+1 and gains trample until end of turn. • Remove two time counters from target permanent or su | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Hedge Troll | notice | This creature gets +1/+1 as long as you control a Plains. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Magus of the Arena | notice | {3}, {T}: Tap target creature you control and target creature of an opponent's choice they control. Those creatures fight each other. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Pongify | notice | Destroy target creature. It can't be regenerated. Its controller creates a 3/3 green Ape creature token. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Timebender | notice | When this creature is turned face up, choose one — • Remove two time counters from target permanent or suspended card. • Put two time counters on target permane | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Timecrafting | notice | Choose one — • Remove X time counters from target permanent or suspended card. • Put X time counters on target permanent with a time counter on it or suspended  | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Treacherous Urge | notice | Target opponent reveals their hand. You may put a creature card from it onto the battlefield under your control. That creature gains haste. Sacrifice it at the  | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Aquamorph Entity | unaudited | As this creature enters or is turned face up, it becomes your choice of 5/1 or 1/5. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Cautery Sliver | unaudited | All Slivers have "{1}, Sacrifice this permanent: This permanent deals 1 damage to any target." | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Darkheart Sliver | unaudited | All Slivers have "Sacrifice this permanent: You gain 3 life." | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Frenetic Sliver | unaudited | All Slivers have "{0}: If this permanent is on the battlefield, flip a coin. If you win the flip, exile this permanent and return it to the battlefield under it | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Frozen Aether | unaudited | Artifacts, creatures, and lands your opponents control enter tapped. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Magus of the Tabernacle | unaudited | All creatures have "At the beginning of your upkeep, sacrifice this creature unless you pay {1}." | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Necrotic Sliver | unaudited | All Slivers have "{3}, Sacrifice this permanent: Destroy target permanent." | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Poultice Sliver | unaudited | All Slivers have "{2}, {T}: Regenerate target Sliver." | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Pouncing Wurm | unaudited | If this creature was kicked, it enters with three +1/+1 counters on it and with haste. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Primal Plasma | unaudited | As this creature enters, it becomes your choice of a 3/3 creature, a 2/2 creature with flying, or a 1/6 creature with defender. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Skirk Shaman | unaudited | This creature can't be blocked except by artifact creatures and/or red creatures. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Utopia Vow | unaudited | Enchanted creature can't attack or block. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Voidstone Gargoyle | unaudited | Spells with the chosen name can't be cast. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Akroma, Angel of Fury | handled | This spell can't be countered. | the engine reads this text and performs it | Y/-/- | not_tested |
| Big Game Hunter | handled | When this creature enters, destroy target creature with power 4 or greater. It can't be regenerated. | the engine reads this text and performs it | Y/-/- | not_tested |
| Blood Knight | handled | First strike | machines/combat.py | Y/-/- | not_tested |
| Body Double | handled | You may have this creature enter as a copy of any creature card in a graveyard. | the engine reads this text and performs it | Y/-/- | not_tested |
| Boom // Bust | handled | Destroy target land you control and target land you don't control. | the engine reads this text and performs it | Y/-/- | not_tested |
| Brute Force | handled | Target creature gets +3/+3 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Circle of Affliction | handled | As this enchantment enters, choose a color. | the engine reads this text and performs it | Y/-/- | not_tested |
| Citanul Woodreaders | handled | When this creature enters, if it was kicked, draw two cards. | the engine reads this text and performs it | Y/-/- | not_tested |
| Damnation | handled | Destroy all creatures. They can't be regenerated. | the engine reads this text and performs it | Y/-/- | not_tested |
| Dead // Gone | handled | Dead deals 2 damage to target creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Dreamscape Artist | handled | {2}{U}, {T}, Discard a card, Sacrifice a land: Search your library for up to two basic land cards, put them onto the battlefield, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Dunerider Outlaw | handled | At the beginning of each end step, if this creature dealt damage to an opponent this turn, put a +1/+1 counter on it. | the engine reads this text and performs it | Y/-/- | not_tested |
| Essence Warden | handled | Whenever another creature enters, you gain 1 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Evolution Charm | handled | Choose one — • Search your library for a basic land card, reveal it, put it into your hand, then shuffle. • Return target creature card from your graveyard to y | the engine reads this text and performs it | Y/-/- | not_tested |
| Gaea's Anthem | handled | Creatures you control get +1/+1. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ghost Tactician | handled | {W}, {T}, Discard a card: Creatures you control get +1/+0 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Giant Dustwasp | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Gossamer Phantasm | handled | When this creature becomes the target of a spell or ability, sacrifice it. | the engine reads this text and performs it | Y/-/- | not_tested |
| Groundbreaker | handled | At the beginning of the end step, sacrifice this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Healing Leaves | handled | Choose one — • Target player gains 3 life. • Prevent the next 3 damage that would be dealt to any target this turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Heroes Remembered | handled | You gain 20 life. Suspend 10—{W} (Rather than cast this card from your hand, you may pay {W} and exile it with ten time counters on it. At the beginning of your | the engine reads this text and performs it | Y/-/- | not_tested |
| Kavu Predator | handled | Whenever an opponent gains life, put that many +1/+1 counters on this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Keen Sense | handled | Whenever enchanted creature deals damage to an opponent, you may draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Magus of the Bazaar | handled | {T}: Draw two cards, then discard three cards. | the engine reads this text and performs it | Y/-/- | not_tested |
| Magus of the Coffers | handled |  |  | Y/-/- | not_tested |
| Magus of the Library | handled | {T}: Draw a card. Activate only if you have exactly seven cards in hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Malach of the Dawn | handled | {W}{W}{W}: Regenerate this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Mana Tithe | handled | Counter target spell unless its controller pays {1}. | the engine reads this text and performs it | Y/-/- | not_tested |
| Mesa Enchantress | handled | Whenever you cast an enchantment spell, you may draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Midnight Charm | handled | Choose one — • Midnight Charm deals 1 damage to target creature and you gain 1 life. • Target creature gains first strike until end of turn. • Tap target creatu | the engine reads this text and performs it | Y/-/- | not_tested |
| Mire Boa | handled | {G}: Regenerate this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Mirri the Cursed | handled | Whenever Mirri deals combat damage to a creature, put a +1/+1 counter on Mirri. | the engine reads this text and performs it | Y/-/- | not_tested |
| Muck Drubb | handled | When this creature enters, change the target of target spell that targets only a single creature to this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Mycologist | handled | At the beginning of your upkeep, put a spore counter on this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Needlepeak Spider | handled | Reach | machines/combat.py | Y/-/- | not_tested |
| Numot, the Devastator | handled | Whenever Numot deals combat damage to a player, you may pay {2}{R}. If you do, destroy up to two target lands. | the engine reads this text and performs it | Y/-/- | not_tested |
| Piracy Charm | handled | Choose one — • Target creature gains islandwalk until end of turn. (It can't be blocked as long as defending player controls an Island.) • Target creature gets  | the engine reads this text and performs it | Y/-/- | not_tested |
| Prodigal Pyromancer | handled | {T}: This creature deals 1 damage to any target. | the engine reads this text and performs it | Y/-/- | not_tested |
| Psychotrope Thallid | handled | At the beginning of your upkeep, put a spore counter on this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Radha, Heir to Keld | handled | Whenever Radha attacks, you may add {R}{R}. | the engine reads this text and performs it | Y/-/- | not_tested |
| Rathi Trapper | handled | {B}, {T}: Tap target creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Reckless Wurm | handled | Madness | machines/casting.py | Y/-/- | not_tested |
| Revered Dead | handled | {W}: Regenerate this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ridged Kusite | handled | {1}{B}, {T}, Discard a card: Target creature gets +1/+0 and gains first strike until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Riptide Pilferer | handled | Whenever this creature deals combat damage to a player, that player discards a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Saltfield Recluse | handled | {T}: Target creature gets -2/-0 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Seal of Primordium | handled | Sacrifice this enchantment: Destroy target artifact or enchantment. | the engine reads this text and performs it | Y/-/- | not_tested |
| Serendib Sorcerer | handled | {T}: Target creature other than this creature has base power and toughness 0/2 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Serra Sphinx | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Shade of Trokair | handled | {W}: This creature gets +1/+1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Shivan Meteor | handled | Shivan Meteor deals 13 damage to target creature. Suspend 2—{1}{R}{R} (Rather than cast this card from your hand, you may pay {1}{R}{R} and exile it with two ti | the engine reads this text and performs it | Y/-/- | not_tested |
| Simian Spirit Guide | handled |  |  | Y/-/- | not_tested |
| Torchling | handled | {R}: Untap this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Vitaspore Thallid | handled | At the beginning of your upkeep, put a spore counter on this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Vorosh, the Hunter | handled | Whenever Vorosh deals combat damage to a player, you may pay {2}{G}. If you do, put six +1/+1 counters on Vorosh. | the engine reads this text and performs it | Y/-/- | not_tested |
| Wistful Thinking | handled | Target player draws two cards, then discards four cards. | the engine reads this text and performs it | Y/-/- | not_tested |

## Fully supported

<details>
<summary>6 cards</summary>

- Aether Membrane
- Cradle to Grave
- Harmonize
- Rough // Tumble
- Sunlance
- Urborg, Tomb of Yawgmoth

</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| Vanishing | Aven Riftwatcher, Calciderm, Chronozoa, Deadwood Treefolk, Keldon Marauders, Lavacore Elemental, Waning Wurm | 7 |
| All Slivers have "{0}: If this permanent is on the battlefield, flip a coin. If you win the flip, exile this permanent and return it to the battlefield under it | Cautery Sliver, Darkheart Sliver, Frenetic Sliver, Necrotic Sliver, Poultice Sliver | 5 |
| When you cast this spell, any player may pay half their life, rounded up. If a player does, counter Temporal Extortion. Take an extra turn after this one. | Brain Gorgers, Dash Hopes, Phantasmagorian, Temporal Extortion | 4 |
| At the beginning of your upkeep, destroy the creature with the least power. It can't be regenerated. If two or more creatures are tied for least power, you choo | Enslave, Melancholy, Porphyry Nodes | 3 |
| Echo | Hammerheim Deadeye, Stingscourger, Uktabi Drake | 3 |
| When this creature enters, return three creatures you control to their owner's hand. | Dust Elemental, Stonecloaker, Stormfront Riders | 3 |
| Until end of turn, target creature you control gains trample and gets +X/+0, where X is its power. Sacrifice it at the beginning of the next end step. | Fatal Frenzy, Ovinize | 2 |
| When the last time counter is removed from this card while it's exiled, create a 2/2 black Knight creature token with flanking, protection from white, and haste | Riftmarked Knight, Veiling Oddity | 2 |
| When this creature is turned face up, choose one — • Remove two time counters from target permanent or suspended card. • Put two time counters on target permane | Shaper Parasite, Timebender | 2 |
| Aeon Chronicler's power and toughness are each equal to the number of cards in your hand. | Aeon Chronicler | 1 |
| All creatures have "At the beginning of your upkeep, sacrifice this creature unless you pay {1}." | Magus of the Tabernacle | 1 |
| All damage that would be dealt this turn to target creature you control by a source of your choice is dealt to another target creature instead. | Kor Dirge | 1 |
| All Forests and all Saprolings are 1/1 green Saproling creatures and Forest lands in addition to their other types. | Life and Limb | 1 |
| All Sliver creatures get +1/+1. | Sinew Sliver | 1 |
| All Sliver creatures have defender. | Dormant Sliver | 1 |
| All Sliver creatures have first strike. | Spitting Sliver | 1 |
| All Sliver creatures have haste. | Reflex Sliver | 1 |
| All Sliver creatures have trample. | Battering Sliver | 1 |
| All Sliver creatures have vigilance. | Synchronous Sliver | 1 |
| Artifacts, creatures, and lands your opponents control enter tapped. | Frozen Aether | 1 |
| As this creature enters, it becomes your choice of a 3/3 creature, a 2/2 creature with flying, or a 1/6 creature with defender. | Primal Plasma | 1 |
| As this creature enters or is turned face up, it becomes your choice of 5/1 or 1/5. | Aquamorph Entity | 1 |
| At the beginning of each player's upkeep, that player may put an artifact, creature, or land card from their hand onto the battlefield. | Braids, Conjurer Adept | 1 |
| Change the target of target spell with a single target. You lose life equal to that spell's mana value. | Imp's Mischief | 1 |
| Choose one — • Destroy target artifact. • Target creature gets +1/+1 and gains trample until end of turn. • Remove two time counters from target permanent or su | Fury Charm | 1 |
| Choose one — • Prevent all combat damage that would be dealt this turn. • Regenerate target creature. • Counter target spell that targets you. | Dawn Charm | 1 |
| Choose one — • Remove X time counters from target permanent or suspended card. • Put X time counters on target permanent with a time counter on it or suspended  | Timecrafting | 1 |
| Choose target creature. Reveal cards from the top of your library until you reveal a nonland card. That creature gets +X/-X until end of turn, where X is that c | Erratic Mutation | 1 |
| Counter target instant or sorcery spell. Its controller reveals cards from the top of their library until they reveal an instant or sorcery card. That player ma | Spellshift | 1 |
| Counter target spell. Its controller discards a card. | Dismal Failure | 1 |
| Counter target spell that targets a permanent you control. | Rebuff the Wicked | 1 |
| Destroy target creature. It can't be regenerated. Its controller creates a 3/3 green Ape creature token. | Pongify | 1 |
| Detritivore's power and toughness are each equal to the number of nonbasic land cards in your opponents' graveyards. | Detritivore | 1 |
| {1}{R}, {T}, Discard a card: Target creature can't be blocked this turn except by artifact creatures and/or red creatures. | Firefright Mage | 1 |
| {2}{G}{G}, {T}, Discard a card: You gain 2 life for each card in your hand. | Sophic Centaur | 1 |
| {T}: Draw a card and reveal it. If it isn't a land card, discard it. | Fa'adiyah Seer | 1 |
| Enchanted creature can't attack or block. | Utopia Vow | 1 |
| Enchanted creature gets +2/+0 and can't be blocked by creatures with flying. | Dust Corona | 1 |
| Enchanted creature gets +1/+2 as long as it's white. Otherwise, it gets -2/-1. | Serra's Boon | 1 |
| Enchanted creature gets +2/+2 for each Aura attached to it and has vigilance. | Auramancer's Guise | 1 |
| {4}{R}: Exile this creature. | Molten Firebird | 1 |
| For each tapped nonland permanent target opponent controls, search that player's library for a card with the same name as that permanent. Put those cards onto t | Dichotomancy | 1 |
| Fungal Behemoth's power and toughness are each equal to the number of +1/+1 counters on creatures you control. | Fungal Behemoth | 1 |
| If this creature was kicked, it enters with three +1/+1 counters on it and with haste. | Pouncing Wurm | 1 |
| Kicker {3}{G} (You may pay an additional {3}{G} as you cast this spell.) Search your library for up to two Forest cards, put them onto the battlefield tapped, t | Hunting Wilds | 1 |
| Other white creatures get +1/+1. | Crovax, Ascendant Hero | 1 |
| Return each Aura card from your graveyard to the battlefield. Only creatures can be enchanted this way. (Aura cards that can't enchant a creature on the battlef | Retether | 1 |
| Roiling Horror's power and toughness are each equal to your life total minus the life total of an opponent with the most life. | Roiling Horror | 1 |
| Sacrifice a Saproling: Each creature you control that's a Fungus or a Saproling gets +1/+1 until end of turn. | Pallid Mycoderm | 1 |
| {4}, {T}: Search your library for a Rebel permanent card with mana value 3 or less, put it onto the battlefield, then shuffle. | Blightspeaker | 1 |
| Spells with the chosen name can't be cast. | Voidstone Gargoyle | 1 |
| Split second (As long as this spell is on the stack, players can't cast spells or activate abilities that aren't mana abilities.) Choose target card in a gravey | Extirpate | 1 |
| {T}: Switch target creature's power and toughness until end of turn. | Merfolk Thaumaturgist | 1 |
| {3}, {T}: Tap target creature you control and target creature of an opponent's choice they control. Those creatures fight each other. | Magus of the Arena | 1 |
| Target opponent chooses a card in your graveyard. You may pay {B}. If you do, repeat this process except that opponent can't choose a card already chosen for Sh | Shrouded Lore | 1 |
| Target opponent reveals their hand. You may put a creature card from it onto the battlefield under your control. That creature gains haste. Sacrifice it at the  | Treacherous Urge | 1 |
| Target player reveals their hand. You choose a nonland card with mana value X or less from it. That player discards that card. | Venarian Glimmer | 1 |
| This creature can't be blocked except by artifact creatures and/or red creatures. | Skirk Shaman | 1 |
| This creature gets +1/+1 as long as you control a Plains. | Hedge Troll | 1 |
| {R}: This enchantment deals 1 damage to each creature and each player. | Pyrohemia | 1 |
| Tidewalker's power and toughness are each equal to the number of time counters on it. | Tidewalker | 1 |
| {0}: Until end of turn, this creature gets -1/-1 and gains your choice of double strike, protection from red, vigilance, or shadow. | Jodah's Avenger | 1 |
| When this Aura leaves the battlefield, enchanted permanent's controller sacrifices it. | Reality Acid | 1 |
| When this creature dies, if it had no time counters on it, create a 6/1 green Insect creature token with shroud. | Deadly Grub | 1 |
| When this creature enters, any player may sacrifice a land of their choice. If a player does, put this creature on top of its owner's library. | Shivan Wumpus | 1 |
| When this creature enters, if it was kicked with its {1}{B} kicker, tap target untapped creature and that creature deals damage equal to its power to its contro | Ana Battlemage | 1 |
| When this creature enters, it deals an amount of damage of your choice to you and target creature. The damage can't be prevented. | Volcano Hellion | 1 |
| When this creature enters, tap all other creatures. | Timbermare | 1 |
| When you control no Swamps, sacrifice this creature. | Bog Serpent | 1 |
| Whenever a creature enters, enchanted creature gets +2/+2 until end of turn. | Mantle of Leadership | 1 |
| Whenever a creature enters, if you cast it from your hand, you may search your library for a creature card with the same total power and toughness, put it onto  | Wild Pair | 1 |
| Whenever a time counter is removed from this card while it's exiled, create a 1/1 white Soldier creature token. | Benalish Commander | 1 |
| Whenever enchanted creature deals damage, you gain that much life. | Vampiric Link | 1 |
| Whenever Intet deals combat damage to a player, you may pay {2}{U}. If you do, exile the top card of your library face down. You may look at that card for as lo | Intet, the Dreamer | 1 |
| Whenever Teneb deals combat damage to a player, you may pay {2}{B}. If you do, put target creature card from a graveyard onto the battlefield under your control | Teneb, the Harvester | 1 |
| Whenever you play a card, draw a card. | Null Profusion | 1 |
| White creatures get +1/-1. | Sulfur Elemental | 1 |

## Notes


