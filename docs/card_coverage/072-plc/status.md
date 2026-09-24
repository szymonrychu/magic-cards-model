# Planar Chaos (plc)

- Expansion: 072
- Set code: `plc`
- Release date: 2007-02-02
- Cards in scope (Modern/Pioneer/Standard-legal): 162

## Legality

| Format | Legal cards |
|---|---|
| Modern | 162 |
| Pioneer | 1 |
| Standard | 0 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 6 | 3.7% |
| Partial (unaudited) | 13 | 8.0% |
| Not tested (handled, untested) | 56 | 34.6% |
| Not working (silent / notice / error) | 87 | 53.7% |

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
| Oros, the Avenger | silent | Whenever Oros deals combat damage to a player, you may pay {2}{W}. If you do, Oros deals 3 damage to each nonwhite creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
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

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| vanishing | 7 | Aven Riftwatcher, Calciderm, Chronozoa, Deadwood Treefolk, Keldon Marauders | plc |
| all slivers have "..." | 5 | Cautery Sliver, Darkheart Sliver, Frenetic Sliver, Necrotic Sliver, Poultice Sliver | plc |
| Choose one | 3 | Dawn Charm, Fury Charm, Timecrafting | plc |
| echo | 3 | Hammerheim Deadeye, Stingscourger, Uktabi Drake | plc |
| all creatures have "..." | 1 | Magus of the Tabernacle | plc |
| all damage that would be dealt ~ to target creature you control by a source of your choice is dealt to another target creature instead. | 1 | Kor Dirge | plc |
| all forests and all saprolings are N/N green saproling creatures and forest lands in addition to their other types. | 1 | Life and Limb | plc |
| all sliver creatures get +N/+N. | 1 | Sinew Sliver | plc |
| all sliver creatures have defender. | 1 | Dormant Sliver | plc |
| all sliver creatures have first strike. | 1 | Spitting Sliver | plc |
| all sliver creatures have haste. | 1 | Reflex Sliver | plc |
| all sliver creatures have trample. | 1 | Battering Sliver | plc |
| all sliver creatures have vigilance. | 1 | Synchronous Sliver | plc |
| artifacts, creatures, and lands your opponents control enter tapped. | 1 | Frozen Aether | plc |
| as ~ enters or is turned face up, it becomes your choice of N/N or N/N. | 1 | Aquamorph Entity | plc |
| as ~ enters, it becomes your choice of a N/N creature, a N/N creature with flying, or a N/N creature with defender. | 1 | Primal Plasma | plc |
| at the beginning of each player's upkeep, that player may put an artifact, creature, or land card from their hand onto the battlefield. | 1 | Braids, Conjurer Adept | plc |
| at the beginning of your upkeep, destroy the creature with the least power. it can't be regenerated. if two or more creatures are tied for least power, you choo | 1 | Porphyry Nodes | plc |
| at the beginning of your upkeep, enchanted creature deals N damage to its owner. | 1 | Enslave | plc |
| at the beginning of your upkeep, sacrifice ~ unless you pay {M}. | 1 | Melancholy | plc |
| change the target of target spell with a single target. you lose life equal to that spell's mana value. | 1 | Imp's Mischief | plc |
| choose target creature. reveal cards from the top of your library until you reveal a nonland card. that creature gets +N/-N until end of turn, where N is that c | 1 | Erratic Mutation | plc |
| counter target instant or sorcery spell. its controller reveals cards from the top of their library until they reveal an instant or sorcery card. that player ma | 1 | Spellshift | plc |
| counter target spell that targets a permanent you control. | 1 | Rebuff the Wicked | plc |
| counter target spell. its controller discards a card. | 1 | Dismal Failure | plc |
| destroy target creature. it can't be regenerated. its controller creates a N/N green ape creature token. | 1 | Pongify | plc |
| enchanted creature can't attack or block. | 1 | Utopia Vow | plc |
| enchanted creature gets +N/+N and can't be blocked by creatures with flying. | 1 | Dust Corona | plc |
| enchanted creature gets +N/+N as long as it's white. otherwise, it gets -N/-N. | 1 | Serra's Boon | plc |
| enchanted creature gets +N/+N for each aura attached to it and has vigilance. | 1 | Auramancer's Guise | plc |
| for each tapped nonland permanent target opponent controls, search that player's library for a card with the same name as that permanent. put those cards onto t | 1 | Dichotomancy | plc |
| if ~ was kicked, it enters with three +N/+N counters on it and with haste. | 1 | Pouncing Wurm | plc |
| kicker {M}{M} (you may pay an additional {M}{M} as you cast ~.) search your library for up to two forest cards, put them onto the battlefield tapped, then shuff | 1 | Hunting Wilds | plc |
| other white creatures get +N/+N. | 1 | Crovax, Ascendant Hero | plc |
| return each aura card from your graveyard to the battlefield. only creatures can be enchanted ~. (aura cards that can't enchant a creature on the battlefield re | 1 | Retether | plc |
| sacrifice a saproling: each creature you control that's a fungus or a saproling gets +N/+N until end of turn. | 1 | Pallid Mycoderm | plc |
| spells with the chosen name can't be cast. | 1 | Voidstone Gargoyle | plc |
| split second (as long as ~ is on the stack, players can"..."t mana abilities.) choose target card in a graveyard other than a basic land card. search its owner' | 1 | Extirpate | plc |
| target opponent chooses a card in your graveyard. you may pay {M}. if you do, repeat ~ except that opponent can't choose a card already chosen for ~. then put t | 1 | Shrouded Lore | plc |
| target opponent reveals their hand. you may put a creature card from it onto the battlefield under your control. that creature gains haste. sacrifice it at the  | 1 | Treacherous Urge | plc |
| target player reveals their hand. you choose a nonland card with mana value N or less from it. that player discards that card. | 1 | Venarian Glimmer | plc |
| until end of turn, target creature loses all abilities and has base power and toughness N/N. | 1 | Ovinize | plc |
| until end of turn, target creature you control gains trample and gets +N/+N, where N is its power. sacrifice it at the beginning of the next end step. | 1 | Fatal Frenzy | plc |
| when the last time counter is removed from ~ while it"..."t be blocked ~. | 1 | Veiling Oddity | plc |
| when the last time counter is removed from ~ while it's exiled, create a N/N black knight creature token with flanking, protection from white, and haste. | 1 | Riftmarked Knight | plc |
| when you cast ~, any player may discard three cards. if a player does, counter ~. | 1 | Phantasmagorian | plc |
| when you cast ~, any player may pay N life. if a player does, counter ~. counter target spell. | 1 | Dash Hopes | plc |
| when you cast ~, any player may pay half their life, rounded up. if a player does, counter ~. take an extra turn after ~. | 1 | Temporal Extortion | plc |
| when you cast ~, any player may sacrifice a creature of their choice. if a player does, counter ~. | 1 | Brain Gorgers | plc |
| when you control no swamps, sacrifice ~. | 1 | Bog Serpent | plc |
| when ~ dies, if it had no time counters on it, create a N/N green insect creature token with shroud. | 1 | Deadly Grub | plc |
| when ~ enters, any player may sacrifice a land of their choice. if a player does, put ~ on top of its owner's library. | 1 | Shivan Wumpus | plc |
| when ~ enters, if it was kicked with its {M}{M} kicker, tap target untapped creature and that creature deals damage equal to its power to its controller. | 1 | Ana Battlemage | plc |
| when ~ enters, it deals an amount of damage of your choice to you and target creature. the damage can't be prevented. | 1 | Volcano Hellion | plc |
| when ~ enters, return a creature you control to its owner's hand. | 1 | Stonecloaker | plc |
| when ~ enters, return three creatures you control to their owner's hand. | 1 | Dust Elemental | plc |
| when ~ enters, return two creatures you control to their owner's hand. | 1 | Stormfront Riders | plc |
| when ~ enters, tap all other creatures. | 1 | Timbermare | plc |
| when ~ is turned face up, choose one — • remove two time counters from target permanent or suspended card. • put two time counters on target permanent with a ti | 1 | Timebender | plc |
| when ~ is turned face up, target creature gets +N/-N or -N/+N until end of turn. | 1 | Shaper Parasite | plc |
| when ~ leaves the battlefield, enchanted permanent's controller sacrifices it. | 1 | Reality Acid | plc |
| whenever a creature enters, enchanted creature gets +N/+N until end of turn. | 1 | Mantle of Leadership | plc |
| whenever a creature enters, if you cast it from your hand, you may search your library for a creature card with the same total power and toughness, put it onto  | 1 | Wild Pair | plc |
| whenever a time counter is removed from ~ while it's exiled, create a N/N white soldier creature token. | 1 | Benalish Commander | plc |
| whenever enchanted creature deals damage, you gain that much life. | 1 | Vampiric Link | plc |
| whenever intet deals combat damage to a player, you may pay {M}{M}. if you do, exile the top card of your library face down. you may look at that card for as lo | 1 | Intet, the Dreamer | plc |
| whenever oros deals combat damage to a player, you may pay {M}{M}. if you do, oros deals N damage to each nonwhite creature. | 1 | Oros, the Avenger | plc |
| whenever teneb deals combat damage to a player, you may pay {M}{M}. if you do, put target creature card from a graveyard onto the battlefield under your control | 1 | Teneb, the Harvester | plc |
| whenever you play a card, draw a card. | 1 | Null Profusion | plc |
| white creatures get +N/-N. | 1 | Sulfur Elemental | plc |
| {M}, {M}: search your library for a rebel permanent card with mana value N or less, put it onto the battlefield, then shuffle. | 1 | Blightspeaker | plc |
| {M}, {M}: tap target creature you control and target creature of an opponent's choice they control. those creatures fight each other. | 1 | Magus of the Arena | plc |
| {M}: draw a card and reveal it. if it isn't a land card, discard it. | 1 | Fa'adiyah Seer | plc |
| {M}: switch target creature's power and toughness until end of turn. | 1 | Merfolk Thaumaturgist | plc |
| {M}: until end of turn, ~ gets -N/-N and gains your choice of double strike, protection from red, vigilance, or shadow. | 1 | Jodah's Avenger | plc |
| {M}: ~ deals N damage to each creature and each player. | 1 | Pyrohemia | plc |
| {M}{M}, {M}, discard a card: target creature can't be blocked ~ except by artifact creatures and/or red creatures. | 1 | Firefright Mage | plc |
| {M}{M}: exile ~. | 1 | Molten Firebird | plc |
| {M}{M}{M}, {M}, discard a card: you gain N life for each card in your hand. | 1 | Sophic Centaur | plc |
| ~ can't be blocked except by artifact creatures and/or red creatures. | 1 | Skirk Shaman | plc |
| ~ gets +N/+N as long as you control a plains. | 1 | Hedge Troll | plc |
| ~"..." graveyards. | 1 | Detritivore | plc |
| ~'s power and toughness are each equal to the number of +N/+N counters on creatures you control. | 1 | Fungal Behemoth | plc |
| ~'s power and toughness are each equal to the number of cards in your hand. | 1 | Aeon Chronicler | plc |
| ~'s power and toughness are each equal to the number of time counters on it. | 1 | Tidewalker | plc |
| ~'s power and toughness are each equal to your life total minus the life total of an opponent with the most life. | 1 | Roiling Horror | plc |

## Notes


