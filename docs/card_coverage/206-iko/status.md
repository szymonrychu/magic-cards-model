# Ikoria: Lair of Behemoths (iko)

- Expansion: 206
- Set code: `iko`
- Release date: 2020-04-24
- Cards in scope (Modern/Pioneer/Standard-legal): 228

## Legality

| Format | Legal cards |
|---|---|
| Modern | 228 |
| Pioneer | 228 |
| Standard | 6 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 14 | 6.1% |
| Partial (unaudited) | 21 | 9.2% |
| Not tested (handled, untested) | 92 | 40.4% |
| Not working (silent / notice / error) | 101 | 44.3% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Alert Heedbonder | silent | At the beginning of your end step, you gain 1 life for each creature you control with vigilance. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Archipelagore | silent | Whenever this creature mutates, tap up to X target creatures, where X is the number of times this creature has mutated. Those creatures don't untap during their | the engine does not recognise this trigger's condition - it never triggers | Y/Y/- | not_working |
| Auspicious Starrix | silent | Whenever this creature mutates, exile cards from the top of your library until you exile X permanent cards, where X is the number of times this creature has mut | the engine does not recognise this trigger's condition - it never triggers | Y/Y/- | not_working |
| Blitz of the Thunder-Raptor | silent | Blitz of the Thunder-Raptor deals damage to target creature or planeswalker equal to the number of instant and sorcery cards in your graveyard. If that creature | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Blood Curdle | silent | Destroy target creature. Put a menace counter on a creature you control. (It can't be blocked except by two or more creatures.) | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Boneyard Lurker | silent | Whenever this creature mutates, return target permanent card from your graveyard to your hand. | the engine does not recognise this trigger's condition - it never triggers | Y/Y/- | not_working |
| Brokkos, Apex of Forever | silent | Mutate | no machine in the engine executes this keyword | Y/Y/- | not_working |
| Cavern Whisperer | silent | Whenever this creature mutates, each opponent discards a card. | the engine does not recognise this trigger's condition - it never triggers | Y/Y/- | not_working |
| Charge of the Forever-Beast | silent | As an additional cost to cast this spell, reveal a creature card from your hand. Charge of the Forever-Beast deals damage to target creature or planeswalker equ | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Chittering Harvester | silent | Whenever this creature mutates, each opponent sacrifices a creature of their choice. | the engine does not recognise this trigger's condition - it never triggers | Y/Y/- | not_working |
| Clash of Titans | silent | Target creature fights another target creature. (Each deals damage equal to its power to the other.) | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Cloudpiercer | silent | Whenever this creature mutates, you may discard a card. If you do, draw a card. | the engine does not recognise this trigger's condition - it never triggers | Y/Y/- | not_working |
| Crystalline Giant | silent | At the beginning of combat on your turn, choose a kind of counter at random that this creature doesn't have on it from among flying, first strike, deathtouch, h | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Cubwarden | silent | Whenever this creature mutates, create two 1/1 white Cat creature tokens with lifelink. | the engine does not recognise this trigger's condition - it never triggers | Y/Y/- | not_working |
| Death's Oasis | silent | Whenever a nontoken creature you control dies, mill two cards. Then return a creature card with lesser mana value than the creature that died from your graveyar | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Dirge Bat | silent | Whenever this creature mutates, destroy target creature or planeswalker an opponent controls. | the engine does not recognise this trigger's condition - it never triggers | Y/Y/- | not_working |
| Dreamtail Heron | silent | Whenever this creature mutates, draw a card. | the engine does not recognise this trigger's condition - it never triggers | Y/Y/- | not_working |
| Duskfang Mentor | silent | {1}{B}, {T}: Put a +1/+1 counter on each creature you control with lifelink. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Eerie Ultimatum | silent | Return any number of permanent cards with different names from your graveyard to the battlefield. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Emergent Ultimatum | silent | Search your library for up to three monocolored cards with different names and exile them. An opponent chooses one of those cards. Shuffle that card into your l | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Essence Symbiote | silent | Whenever a creature you control mutates, put a +1/+1 counter on that creature and you gain 2 life. | the engine does not recognise this trigger's condition - it never triggers | Y/Y/- | not_working |
| Everquill Phoenix | silent | Whenever this creature mutates, create a red artifact token named Feather with "{1}, Sacrifice this token: Return target Phoenix card from your graveyard to the | the engine does not recognise this trigger's condition - it never triggers | Y/Y/- | not_working |
| Extinction Event | silent | Choose odd or even. Exile each creature with mana value of the chosen quality. (Zero is even.) | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Exuberant Wolfbear | silent | Whenever this creature attacks, you may have the base power and toughness of target Human you control become equal to this creature's power and toughness until  | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Fire Prophecy | silent | Fire Prophecy deals 3 damage to target creature. You may put a card from your hand on the bottom of your library. If you do, draw a card. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Footfall Crater | silent | Enchanted land has "{T}: Target creature gains trample and haste until end of turn." | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Frillscare Mentor | silent | {2}{R}, {T}: Put a +1/+1 counter on each creature you control with menace. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Gemrazer | silent | Whenever this creature mutates, destroy target artifact or enchantment an opponent controls. | the engine does not recognise this trigger's condition - it never triggers | Y/Y/- | not_working |
| Genesis Ultimatum | silent | Look at the top five cards of your library. Put any number of permanent cards from among them onto the battlefield and the rest into your hand. Exile Genesis Ul | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Glowstone Recluse | silent | Whenever this creature mutates, put two +1/+1 counters on it. | the engine does not recognise this trigger's condition - it never triggers | Y/Y/- | not_working |
| Hornbash Mentor | silent | {2}{G}, {T}: Put a +1/+1 counter on each creature you control with trample. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Hunted Nightmare | silent | When this creature enters, target opponent puts a deathtouch counter on a creature they control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Huntmaster Liger | silent | Whenever this creature mutates, other creatures you control get +X/+X until end of turn, where X is the number of times this creature has mutated. | the engine does not recognise this trigger's condition - it never triggers | Y/Y/- | not_working |
| Illuna, Apex of Wishes | silent | Whenever this creature mutates, exile cards from the top of your library until you exile a nonland permanent card. Put that card onto the battlefield or into yo | the engine does not recognise this trigger's condition - it never triggers | Y/Y/- | not_working |
| Insatiable Hemophage | silent | Whenever this creature mutates, each opponent loses X life and you gain X life, where X is the number of times this creature has mutated. | the engine does not recognise this trigger's condition - it never triggers | Y/Y/- | not_working |
| Keensight Mentor | silent | {1}{W}, {T}: Put a +1/+1 counter on each creature you control with vigilance. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Keep Safe | silent | Counter target spell that targets a permanent you control. Draw a card. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Labyrinth Raptor | silent | Whenever a creature you control with menace becomes blocked, defending player sacrifices a creature of their choice that's blocking it. | this trigger's condition can never be satisfied - it never triggers | Y/Y/- | not_working |
| Lore Drakkis | silent | Whenever this creature mutates, return target instant or sorcery card from your graveyard to your hand. | the engine does not recognise this trigger's condition - it never triggers | Y/Y/- | not_working |
| Lukka, Coppercoat Outcast | silent | +1: Exile the top three cards of your library. Creature cards exiled this way gain "You may cast this card from exile as long as you control a Lukka planeswalke | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Majestic Auricorn | silent | Whenever this creature mutates, you gain 4 life. | the engine does not recognise this trigger's condition - it never triggers | Y/Y/- | not_working |
| Memory Leak | silent | Target opponent reveals their hand. You choose a nonland card from that player's graveyard or hand and exile it. Cycling {1} ({1}, Discard this card: Draw a car | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Migratory Greathorn | silent | Whenever this creature mutates, search your library for a basic land card, put it onto the battlefield tapped, then shuffle. | the engine does not recognise this trigger's condition - it never triggers | Y/Y/- | not_working |
| Momentum Rumbler | silent | Whenever this creature attacks, if it doesn't have first strike, put a first strike counter on it. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Mutual Destruction | silent | This spell has flash as long as you control a permanent with flash. As an additional cost to cast this spell, sacrifice a creature. Destroy target creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Mysterious Egg | silent | Whenever this creature mutates, put a +1/+1 counter on it. | the engine does not recognise this trigger's condition - it never triggers | Y/Y/- | not_working |
| Mystic Subdual | silent | Enchanted creature gets -2/-0 and loses all abilities. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Mythos of Brokkos | silent | If {U}{B} was spent to cast this spell, search your library for a card, put that card into your graveyard, then shuffle. Return up to two permanent cards from y | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Mythos of Nethroi | silent | Destroy target nonland permanent if it's a creature or if {G}{W} was spent to cast this spell. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Mythos of Snapdax | silent | Each player chooses an artifact, a creature, an enchantment, and a planeswalker from among the nonland permanents they control, then sacrifices the rest. If {B} | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Mythos of Vadrok | silent | Mythos of Vadrok deals 5 damage divided as you choose among any number of target creatures and/or planeswalkers. If {W}{U} was spent to cast this spell, until y | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Narset of the Ancient Way | silent | +1: You gain 2 life. Add {U}, {R}, or {W}. Spend this mana only to cast a noncreature spell. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Necropanther | silent | Whenever this creature mutates, return target creature card with mana value 3 or less from your graveyard to the battlefield. | the engine does not recognise this trigger's condition - it never triggers | Y/Y/- | not_working |
| Nethroi, Apex of Death | silent | Whenever this creature mutates, return any number of target creature cards with total power 10 or less from your graveyard to the battlefield. | the engine does not recognise this trigger's condition - it never triggers | Y/Y/- | not_working |
| Parcelbeast | silent | Mutate | no machine in the engine executes this keyword | Y/Y/- | not_working |
| Patagia Tiger | silent | When this creature enters, target Human you control gets +2/+2 until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Perimeter Sergeant | silent | Whenever this creature attacks, other Humans you control get +1/+0 until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Porcuparrot | silent | {T}: This creature deals X damage to any target, where X is the number of times this creature has mutated. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Pouncing Shoreshark | silent | Whenever this creature mutates, you may return target creature an opponent controls to its owner's hand. | the engine does not recognise this trigger's condition - it never triggers | Y/Y/- | not_working |
| Primal Empathy | silent | At the beginning of your upkeep, draw a card if you control a creature with the greatest power among creatures on the battlefield. Otherwise, put a +1/+1 counte | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Quartzwood Crasher | silent | Whenever one or more creatures you control with trample deal combat damage to a player, create an X/X green Dinosaur Beast creature token with trample, where X  | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Regal Leosaur | silent | Whenever this creature mutates, other creatures you control get +2/+1 until end of turn. | the engine does not recognise this trigger's condition - it never triggers | Y/Y/- | not_working |
| Reptilian Reflection | silent | Whenever you cycle a card, you may have this enchantment become a 5/4 Dinosaur creature with trample and haste in addition to its other types until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Ruinous Ultimatum | silent | Destroy all nonland permanents your opponents control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Sanctuary Smasher | silent | When you cycle this card, put a first strike counter on target creature you control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Sea-Dasher Octopus | silent | Mutate | no machine in the engine executes this keyword | Y/Y/- | not_working |
| Shark Typhoon | silent | Whenever you cast a noncreature spell, create an X/X blue Shark creature token with flying, where X is that spell's mana value. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Sleeper Dart | silent | {T}, Sacrifice this artifact: Target creature doesn't untap during its controller's next untap step. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Snapdax, Apex of the Hunt | silent | Whenever this creature mutates, it deals 4 damage to target creature or planeswalker an opponent controls and you gain 4 life. | the engine does not recognise this trigger's condition - it never triggers | Y/Y/- | not_working |
| Solid Footing | silent | As long as enchanted creature has vigilance, it assigns combat damage equal to its toughness rather than its power. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| The Ozolith | silent | Whenever a creature you control leaves the battlefield, if it had counters on it, put those counters on The Ozolith. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Thwart the Enemy | silent | Prevent all damage that would be dealt this turn by creatures your opponents control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Trumpeting Gnarr | silent | Whenever this creature mutates, create a 3/3 green Beast creature token. | the engine does not recognise this trigger's condition - it never triggers | Y/Y/- | not_working |
| Unexpected Fangs | silent | Put a +1/+1 counter and a lifelink counter on target creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Vadrok, Apex of Thunder | silent | Whenever this creature mutates, you may cast target noncreature card with mana value 3 or less from your graveyard without paying its mana cost. | the engine does not recognise this trigger's condition - it never triggers | Y/Y/- | not_working |
| Vivien, Monsters' Advocate | silent | +1: Create a 3/3 green Beast creature token. Put your choice of a reach counter, a vigilance counter, or a trample counter on it. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Vulpikeet | silent | Whenever this creature mutates, put a +1/+1 counter on it. | the engine does not recognise this trigger's condition - it never triggers | Y/Y/- | not_working |
| Whisper Squad | silent | {1}{B}: Search your library for a card named Whisper Squad, put it onto the battlefield tapped, then shuffle. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Wingspan Mentor | silent | {2}{U}, {T}: Put a +1/+1 counter on each creature you control with flying. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Winota, Joiner of Forces | silent | Whenever a non-Human creature you control attacks, look at the top six cards of your library. You may put a Human creature card from among them onto the battlef | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Yidaro, Wandering Monster | silent | When you cycle this card, shuffle it into your library from your graveyard. If you've cycled a card named Yidaro, Wandering Monster four or more times this game | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Zagoth Mamba | silent | Whenever this creature mutates, target creature an opponent controls gets -2/-2 until end of turn. | the engine does not recognise this trigger's condition - it never triggers | Y/Y/- | not_working |
| Zenith Flare | silent | Zenith Flare deals X damage to any target and you gain X life, where X is the number of cards with a cycling ability in your graveyard. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Zirda, the Dawnwaker | silent | {1}, {T}: Target creature can't block this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Back for More | notice | Return target creature card from your graveyard to the battlefield. When you do, it fights up to one target creature you don't control. (Each deals damage equal | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Bushmeat Poacher | notice | {1}, {T}, Sacrifice another creature: You gain life equal to the sacrificed creature's toughness. Draw a card. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Call of the Death-Dweller | notice | Return up to two target creature cards with total mana value 3 or less from your graveyard to the battlefield. Put a deathtouch counter on either of them. Then  | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Dire Tactics | notice | Exile target creature. If you don't control a Human, you lose life equal to that creature's toughness. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Flame Spill | notice | Flame Spill deals 4 damage to target creature. Excess damage is dealt to that creature's controller instead. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Heightened Reflexes | notice | Target creature gets +1/+0 until end of turn. Put a first strike counter on it. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Jubilant Skybonder | notice | Creatures you control with flying have "Spells your opponents cast that target this creature cost {2} more to cast." | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Kogla, the Titan Ape | notice | {1}{G}: Return target Human you control to its owner's hand. Kogla gains indestructible until end of turn. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Lavabrink Venturer | notice | This creature has protection from each mana value of the chosen quality. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Monstrous Step | notice | Target creature gets +7/+7 until end of turn. Up to one other target creature blocks it this turn if able. Cycling {2} ({2}, Discard this card: Draw a card.) | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Mythos of Illuna | notice | Create a token that's a copy of target permanent. If {R}{G} was spent to cast this spell, instead create a token that's a copy of that permanent, except the tok | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Ram Through | notice | Target creature you control deals damage equal to its power to target creature you don't control. If the creature you control has trample, excess damage is deal | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Rooting Moloch | notice | When this creature enters, exile target card with a cycling ability from your graveyard. Until the end of your next turn, you may play that card. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Skycat Sovereign | notice | This creature gets +1/+1 for each other creature you control with flying. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Spelleater Wolverine | notice | This creature has double strike as long as there are three or more instant and/or sorcery cards in your graveyard. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Will of the All-Hunter | notice | Target creature gets +2/+2 until end of turn. If it's blocking, instead put two +1/+1 counters on it. Cycling {2} ({2}, Discard this card: Draw a card.) | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Yorion, Sky Nomad | notice | When Yorion enters, exile any number of other nonland permanents you own and control. Return those cards to the battlefield at the beginning of the next end ste | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Boot Nipper | unaudited | This creature enters with your choice of a deathtouch counter or a lifelink counter on it. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Cunning Nightbonder | unaudited | Spells with flash you cast cost {1} less to cast and can't be countered. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Drannith Magistrate | unaudited | Your opponents can't cast spells from anywhere other than their hands. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Ferocious Tigorilla | unaudited | This creature enters with your choice of a trample counter or a menace counter on it. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Flycatcher Giraffid | unaudited | This creature enters with your choice of a reach counter or a vigilance counter on it. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Frondland Felidar | unaudited | Creatures you control with vigilance have "{1}, {T}: Tap target creature." | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| General's Enforcer | unaudited | Legendary Humans you control have indestructible. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Grimdancer | unaudited | This creature enters with your choice of two different counters on it from among menace, deathtouch, and lifelink. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Helica Glider | unaudited | This creature enters with your choice of a flying counter or a first strike counter on it. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Jegantha, the Wellspring | unaudited | Companion — No card in your starting deck has more than one of the same mana symbol in its mana cost. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Lurrus of the Dream-Den | unaudited | Once during each of your turns, you may cast a permanent spell with mana value 2 or less from your graveyard. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Lutri, the Spellchaser | unaudited | Companion — Each nonland card in your starting deck has a different name. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Obosh, the Preypiercer | unaudited | If a source you control with an odd mana value would deal damage to a permanent or player, it deals double that damage to that permanent or player instead. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Pollywog Symbiote | unaudited | Each creature spell you cast costs {1} less to cast if it has mutate. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Proud Wildbonder | unaudited | Creatures you control with trample have "You may have this creature assign its combat damage as though it weren't blocked." | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Sonorous Howlbonder | unaudited | Each creature you control with menace can't be blocked except by three or more creatures. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Stormwild Capridor | unaudited | If noncombat damage would be dealt to this creature, prevent that damage. Put a +1/+1 counter on this creature for each 1 damage prevented this way. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Umori, the Collector | unaudited | Companion — Each nonland card in your starting deck shares a card type. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Unpredictable Cyclone | unaudited | If a cycling ability of another nonland card would cause you to draw a card, instead exile cards from the top of your library until you exile a card that shares | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Wingfold Pteron | unaudited | This creature enters with your choice of a flying counter or a hexproof counter on it. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Zilortha, Strength Incarnate | unaudited | Lethal damage dealt to creatures you control is determined by their power rather than their toughness. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Adaptive Shimmerer | handled | This creature enters with three +1/+1 counters on it. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Aegis Turtle | handled |  |  | Y/Y/Y | not_tested |
| Almighty Brushwagg | handled | {3}{G}: This creature gets +3/+3 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Avian Oddity | handled | When you cycle this card, put a flying counter on target creature you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Barrier Breach | handled | Exile up to three target enchantments. Cycling {2} ({2}, Discard this card: Draw a card.) | the engine reads this text and performs it | Y/Y/- | not_tested |
| Bastion of Remembrance | handled | When this enchantment enters, create a 1/1 white Human Soldier creature token. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Blisterspit Gremlin | handled | {1}, {T}: This creature deals 1 damage to each opponent. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Bonders' Enclave | handled | {3}, {T}: Draw a card. Activate only if you control a creature with power 4 or greater. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Boon of the Wish-Giver | handled | Draw four cards. Cycling {1} ({1}, Discard this card: Draw a card.) | the engine reads this text and performs it | Y/Y/- | not_tested |
| Channeled Force | handled | As an additional cost to cast this spell, discard X cards. Target player draws X cards. Channeled Force deals X damage to up to one target creature or planeswal | the engine reads this text and performs it | Y/Y/- | not_tested |
| Checkpoint Officer | handled | {1}{W}, {T}: Tap target creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Chevill, Bane of Monsters | handled | At the beginning of your upkeep, if your opponents control no permanents with bounty counters on them, put a bounty counter on target creature or planeswalker a | the engine reads this text and performs it | Y/Y/- | not_tested |
| Colossification | handled | When this Aura enters, tap enchanted creature. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Coordinated Charge | handled | Creatures you control get +2/+1 until end of turn. Cycling {2} ({2}, Discard this card: Draw a card.) | the engine reads this text and performs it | Y/Y/- | not_tested |
| Crystacean | handled | Flash | machines/casting.py (timing) | Y/Y/- | not_tested |
| Daysquad Marshal | handled | When this creature enters, create a 1/1 white Human Soldier creature token. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Drannith Healer | handled | Whenever you cycle another card, you gain 1 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Drannith Stinger | handled | Whenever you cycle another card, this creature deals 1 damage to each opponent. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Durable Coilbug | handled | {4}{B}: Return this card from your graveyard to your hand. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Easy Prey | handled | Destroy target creature with mana value 2 or less. Cycling {2} ({2}, Discard this card: Draw a card.) | the engine reads this text and performs it | Y/Y/- | not_tested |
| Escape Protocol | handled | Whenever you cycle a card, you may pay {1}. When you do, exile target artifact or creature you control, then return it to the battlefield under its owner's cont | the engine reads this text and performs it | Y/Y/- | not_tested |
| Excavation Mole | handled | When this creature enters, mill three cards. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Facet Reader | handled | {1}, {T}: Draw a card, then discard a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Farfinder | handled | When this creature enters, you may search your library for a basic land card, reveal it, put it into your hand, then shuffle. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Flourishing Fox | handled | Whenever you cycle another card, put a +1/+1 counter on this creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Forbidden Friendship | handled | Create a 1/1 red Dinosaur creature token with haste and a 1/1 white Human Soldier creature token. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Frostveil Ambush | handled | Tap up to two target creatures. Those creatures don't untap during their controller's next untap step. Cycling {1} ({1}, Discard this card: Draw a card.) | the engine reads this text and performs it | Y/Y/- | not_tested |
| Fully Grown | handled | Target creature gets +3/+3 until end of turn. Put a trample counter on it. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Garrison Cat | handled | When this creature dies, create a 1/1 white Human Soldier creature token. | the engine reads this text and performs it | Y/Y/- | not_tested |
| General Kudro of Drannith | handled | Other Humans you control get +1/+1. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Glimmerbell | handled | {1}{U}: Untap this creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Gloom Pangolin | handled |  |  | Y/Y/- | not_tested |
| Go for Blood | handled | Target creature you control fights target creature you don't control. (Each deals damage equal to its power to the other.) Cycling {1} ({1}, Discard this card:  | the engine reads this text and performs it | Y/Y/- | not_tested |
| Gust of Wind | handled | This spell costs {2} less to cast if you control a creature with flying. Return target nonland permanent you don't control to its owner's hand. Draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Hampering Snare | handled | Creatures your opponents control get -2/-0 until end of turn. Cycling {2} ({2}, Discard this card: Draw a card.) | the engine reads this text and performs it | Y/Y/- | not_tested |
| Honey Mammoth | handled | When this creature enters, you gain 4 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Humble Naturalist | handled |  |  | Y/Y/- | not_tested |
| Imposing Vantasaur | handled | Vigilance | machines/combat.py | Y/Y/- | not_tested |
| Indatha Crystal | handled | Cycling | machines/keywords.py (off_zone_abilities: cycling) | Y/Y/- | not_tested |
| Inspired Ultimatum | handled | Target player gains 5 life, Inspired Ultimatum deals 5 damage to any target, then you draw five cards. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Ketria Crystal | handled | Cycling | machines/keywords.py (off_zone_abilities: cycling) | Y/Y/- | not_tested |
| Ketria Triome | handled | This land enters tapped. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Kinnan, Bonder Prodigy | handled | Whenever you tap a nonland permanent for mana, add one mana of any type that permanent produced. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Lava Serpent | handled | Haste | machines/combat.py | Y/Y/- | not_tested |
| Light of Hope | handled | Choose one — • You gain 4 life. • Destroy target enchantment. • Put a +1/+1 counter on target creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Luminous Broodmoth | handled | Whenever a creature you control without flying dies, return it to the battlefield under its owner's control with a flying counter on it. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Lurking Deadeye | handled | When this creature enters, destroy target creature that was dealt damage this turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Maned Serval | handled | Vigilance | machines/combat.py | Y/Y/- | not_tested |
| Migration Path | handled | Search your library for up to two basic land cards, put them onto the battlefield tapped, then shuffle. Cycling {2} ({2}, Discard this card: Draw a card.) | the engine reads this text and performs it | Y/Y/- | not_tested |
| Mosscoat Goriak | handled | Vigilance | machines/combat.py | Y/Y/- | not_tested |
| Neutralize | handled | Counter target spell. Cycling {2} ({2}, Discard this card: Draw a card.) | the engine reads this text and performs it | Y/Y/- | not_tested |
| Nightsquad Commando | handled | When this creature enters, if you attacked this turn, create a 1/1 white Human Soldier creature token. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Of One Mind | handled | This spell costs {2} less to cast if you control a Human creature and a non-Human creature. Draw two cards. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Ominous Seas | handled | Whenever you draw a card, put a foreshadow counter on this enchantment. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Phase Dolphin | handled | Whenever this creature attacks, another target attacking creature can't be blocked this turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Prickly Marmoset | handled | Whenever you cycle a card, this creature gets +2/+0 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Pyroceratops | handled | Whenever you cast a noncreature spell, put a +1/+1 counter on this creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Raking Claws | handled | Target creature gains double strike until end of turn. Cycling {2} ({2}, Discard this card: Draw a card.) | the engine reads this text and performs it | Y/Y/- | not_tested |
| Raugrin Crystal | handled | Cycling | machines/keywords.py (off_zone_abilities: cycling) | Y/Y/- | not_tested |
| Reconnaissance Mission | handled | Whenever a creature you control deals combat damage to a player, you may draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Rielle, the Everwise | handled | Rielle gets +1/+0 for each instant and sorcery card in your graveyard. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Rumbling Rockslide | handled | Rumbling Rockslide deals damage to target creature equal to the number of lands you control. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Sanctuary Lockdown | handled | Humans you control get +1/+1. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Savai Crystal | handled | Cycling | machines/keywords.py (off_zone_abilities: cycling) | Y/Y/- | not_tested |
| Savai Sabertooth | handled |  |  | Y/Y/- | not_tested |
| Savai Thundermane | handled | Whenever you cycle a card, you may pay {2}. When you do, this creature deals 2 damage to target creature and you gain 2 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Savai Triome | handled | This land enters tapped. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Serrated Scorpion | handled | When this creature dies, it deals 2 damage to each opponent and you gain 2 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Shredded Sails | handled | Choose one — • Destroy target artifact. • Shredded Sails deals 4 damage to target creature with flying. Cycling {2} ({2}, Discard this card: Draw a card.) | the engine reads this text and performs it | Y/Y/- | not_tested |
| Skull Prophet | handled | {T}: Mill two cards. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Slitherwisp | handled | Whenever you cast another spell that has flash, you draw a card and each opponent loses 1 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Snare Tactician | handled | Whenever you cycle a card, tap target creature an opponent controls. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Song of Creation | handled | You may play an additional land on each of your turns. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Splendor Mare | handled | When you cycle this card, put a lifelink counter on target creature you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Spontaneous Flight | handled | Target creature gets +2/+2 until end of turn. Put a flying counter on it. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Springjaw Trap | handled | {4}, {T}, Sacrifice this artifact: It deals 3 damage to any target. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sprite Dragon | handled | Whenever you cast a noncreature spell, put a +1/+1 counter on this creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sudden Spinnerets | handled | Target creature gets +1/+3 until end of turn. Put a reach counter on it. Untap it. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Suffocating Fumes | handled | Creatures your opponents control get -1/-1 until end of turn. Cycling {2} ({2}, Discard this card: Draw a card.) | the engine reads this text and performs it | Y/Y/- | not_tested |
| Survivors' Bond | handled | Choose one or both — • Return target Human creature card from your graveyard to your hand. • Return target non-Human creature card from your graveyard to your h | the engine reads this text and performs it | Y/Y/- | not_tested |
| Tentative Connection | handled | This spell costs {3} less to cast if you control a creature with menace. Gain control of target creature until end of turn. Untap that creature. It gains haste  | the engine reads this text and performs it | Y/Y/- | not_tested |
| Thieving Otter | handled | Whenever this creature deals damage to an opponent, draw a card. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Titanoth Rex | handled | When you cycle this card, put a trample counter on target creature you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Titans' Nest | handled | At the beginning of your upkeep, surveil 1. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Valiant Rescuer | handled | Whenever you cycle another card for the first time each turn, create a 1/1 white Human Soldier creature token. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Void Beckoner | handled | When you cycle this card, put a deathtouch counter on target creature you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Voracious Greatshark | handled | When this creature enters, counter target artifact or creature spell. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Weaponize the Monsters | handled | {2}, Sacrifice a creature: This enchantment deals 2 damage to any target. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Whirlwind of Thought | handled | Whenever you cast a noncreature spell, draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Wilt | handled | Destroy target artifact or enchantment. Cycling {2} ({2}, Discard this card: Draw a card.) | the engine reads this text and performs it | Y/Y/- | not_tested |
| Zagoth Crystal | handled | Cycling | machines/keywords.py (off_zone_abilities: cycling) | Y/Y/- | not_tested |
| Zagoth Triome | handled | This land enters tapped. | the engine reads this text and performs it | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>14 cards</summary>

- Blade Banish
- Blitz Leech
- Fiend Artisan
- Fight as One
- Gyruda, Doom of Depths
- Heartless Act
- Indatha Triome
- Kaheera, the Orphanguard
- Keruga, the Macrosage
- Offspring's Revenge
- Raugrin Triome
- Startling Development
- Swallow Whole
- Unbreakable Bond

</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| This creature enters with your choice of two different counters on it from among menace, deathtouch, and lifelink. | Boot Nipper, Ferocious Tigorilla, Flycatcher Giraffid, Grimdancer, Helica Glider, Wingfold Pteron | 6 |
| {1}{W}, {T}: Put a +1/+1 counter on each creature you control with vigilance. | Duskfang Mentor, Frillscare Mentor, Hornbash Mentor, Keensight Mentor, Wingspan Mentor | 5 |
| Whenever this creature mutates, return any number of target creature cards with total power 10 or less from your graveyard to the battlefield. | Boneyard Lurker, Lore Drakkis, Necropanther, Nethroi, Apex of Death | 4 |
| Whenever this creature mutates, you may cast target noncreature card with mana value 3 or less from your graveyard without paying its mana cost. | Cloudpiercer, Majestic Auricorn, Pouncing Shoreshark, Vadrok, Apex of Thunder | 4 |
| Mutate | Brokkos, Apex of Forever, Parcelbeast, Sea-Dasher Octopus | 3 |
| Target creature gets +7/+7 until end of turn. Up to one other target creature blocks it this turn if able. Cycling {2} ({2}, Discard this card: Draw a card.) | Heightened Reflexes, Monstrous Step, Will of the All-Hunter | 3 |
| Whenever a creature you control with menace becomes blocked, defending player sacrifices a creature of their choice that's blocking it. | Essence Symbiote, Labyrinth Raptor, The Ozolith | 3 |
| Whenever this creature mutates, create a red artifact token named Feather with "{1}, Sacrifice this token: Return target Phoenix card from your graveyard to the | Cubwarden, Everquill Phoenix, Trumpeting Gnarr | 3 |
| Whenever this creature mutates, each opponent loses X life and you gain X life, where X is the number of times this creature has mutated. | Cavern Whisperer, Chittering Harvester, Insatiable Hemophage | 3 |
| Whenever this creature mutates, put two +1/+1 counters on it. | Glowstone Recluse, Mysterious Egg, Vulpikeet | 3 |
| At the beginning of your upkeep, draw a card if you control a creature with the greatest power among creatures on the battlefield. Otherwise, put a +1/+1 counte | Alert Heedbonder, Primal Empathy | 2 |
| Companion — Each nonland card in your starting deck has a different name. | Lutri, the Spellchaser, Umori, the Collector | 2 |
| When this creature enters, target opponent puts a deathtouch counter on a creature they control. | Hunted Nightmare, Patagia Tiger | 2 |
| When you cycle this card, shuffle it into your library from your graveyard. If you've cycled a card named Yidaro, Wandering Monster four or more times this game | Sanctuary Smasher, Yidaro, Wandering Monster | 2 |
| Whenever this creature mutates, destroy target creature or planeswalker an opponent controls. | Dirge Bat, Gemrazer | 2 |
| Whenever this creature mutates, exile cards from the top of your library until you exile X permanent cards, where X is the number of times this creature has mut | Auspicious Starrix, Illuna, Apex of Wishes | 2 |
| Whenever this creature mutates, other creatures you control get +X/+X until end of turn, where X is the number of times this creature has mutated. | Huntmaster Liger, Regal Leosaur | 2 |
| As an additional cost to cast this spell, reveal a creature card from your hand. Charge of the Forever-Beast deals damage to target creature or planeswalker equ | Charge of the Forever-Beast | 1 |
| As long as enchanted creature has vigilance, it assigns combat damage equal to its toughness rather than its power. | Solid Footing | 1 |
| At the beginning of combat on your turn, choose a kind of counter at random that this creature doesn't have on it from among flying, first strike, deathtouch, h | Crystalline Giant | 1 |
| Blitz of the Thunder-Raptor deals damage to target creature or planeswalker equal to the number of instant and sorcery cards in your graveyard. If that creature | Blitz of the Thunder-Raptor | 1 |
| Choose odd or even. Exile each creature with mana value of the chosen quality. (Zero is even.) | Extinction Event | 1 |
| Companion — No card in your starting deck has more than one of the same mana symbol in its mana cost. | Jegantha, the Wellspring | 1 |
| Counter target spell that targets a permanent you control. Draw a card. | Keep Safe | 1 |
| +1: Create a 3/3 green Beast creature token. Put your choice of a reach counter, a vigilance counter, or a trample counter on it. | Vivien, Monsters' Advocate | 1 |
| Create a token that's a copy of target permanent. If {R}{G} was spent to cast this spell, instead create a token that's a copy of that permanent, except the tok | Mythos of Illuna | 1 |
| Creatures you control with flying have "Spells your opponents cast that target this creature cost {2} more to cast." | Jubilant Skybonder | 1 |
| Creatures you control with trample have "You may have this creature assign its combat damage as though it weren't blocked." | Proud Wildbonder | 1 |
| Creatures you control with vigilance have "{1}, {T}: Tap target creature." | Frondland Felidar | 1 |
| Destroy all nonland permanents your opponents control. | Ruinous Ultimatum | 1 |
| Destroy target creature. Put a menace counter on a creature you control. (It can't be blocked except by two or more creatures.) | Blood Curdle | 1 |
| Destroy target nonland permanent if it's a creature or if {G}{W} was spent to cast this spell. | Mythos of Nethroi | 1 |
| Each creature spell you cast costs {1} less to cast if it has mutate. | Pollywog Symbiote | 1 |
| Each creature you control with menace can't be blocked except by three or more creatures. | Sonorous Howlbonder | 1 |
| Each player chooses an artifact, a creature, an enchantment, and a planeswalker from among the nonland permanents they control, then sacrifices the rest. If {B} | Mythos of Snapdax | 1 |
| Enchanted creature gets -2/-0 and loses all abilities. | Mystic Subdual | 1 |
| Enchanted land has "{T}: Target creature gains trample and haste until end of turn." | Footfall Crater | 1 |
| Exile target creature. If you don't control a Human, you lose life equal to that creature's toughness. | Dire Tactics | 1 |
| +1: Exile the top three cards of your library. Creature cards exiled this way gain "You may cast this card from exile as long as you control a Lukka planeswalke | Lukka, Coppercoat Outcast | 1 |
| Fire Prophecy deals 3 damage to target creature. You may put a card from your hand on the bottom of your library. If you do, draw a card. | Fire Prophecy | 1 |
| Flame Spill deals 4 damage to target creature. Excess damage is dealt to that creature's controller instead. | Flame Spill | 1 |
| If a cycling ability of another nonland card would cause you to draw a card, instead exile cards from the top of your library until you exile a card that shares | Unpredictable Cyclone | 1 |
| If a source you control with an odd mana value would deal damage to a permanent or player, it deals double that damage to that permanent or player instead. | Obosh, the Preypiercer | 1 |
| If noncombat damage would be dealt to this creature, prevent that damage. Put a +1/+1 counter on this creature for each 1 damage prevented this way. | Stormwild Capridor | 1 |
| If {U}{B} was spent to cast this spell, search your library for a card, put that card into your graveyard, then shuffle. Return up to two permanent cards from y | Mythos of Brokkos | 1 |
| Legendary Humans you control have indestructible. | General's Enforcer | 1 |
| Lethal damage dealt to creatures you control is determined by their power rather than their toughness. | Zilortha, Strength Incarnate | 1 |
| Look at the top five cards of your library. Put any number of permanent cards from among them onto the battlefield and the rest into your hand. Exile Genesis Ul | Genesis Ultimatum | 1 |
| Mythos of Vadrok deals 5 damage divided as you choose among any number of target creatures and/or planeswalkers. If {W}{U} was spent to cast this spell, until y | Mythos of Vadrok | 1 |
| Once during each of your turns, you may cast a permanent spell with mana value 2 or less from your graveyard. | Lurrus of the Dream-Den | 1 |
| Prevent all damage that would be dealt this turn by creatures your opponents control. | Thwart the Enemy | 1 |
| Put a +1/+1 counter and a lifelink counter on target creature. | Unexpected Fangs | 1 |
| Return any number of permanent cards with different names from your graveyard to the battlefield. | Eerie Ultimatum | 1 |
| Return target creature card from your graveyard to the battlefield. When you do, it fights up to one target creature you don't control. (Each deals damage equal | Back for More | 1 |
| {1}{G}: Return target Human you control to its owner's hand. Kogla gains indestructible until end of turn. | Kogla, the Titan Ape | 1 |
| Return up to two target creature cards with total mana value 3 or less from your graveyard to the battlefield. Put a deathtouch counter on either of them. Then  | Call of the Death-Dweller | 1 |
| {1}, {T}, Sacrifice another creature: You gain life equal to the sacrificed creature's toughness. Draw a card. | Bushmeat Poacher | 1 |
| {T}, Sacrifice this artifact: Target creature doesn't untap during its controller's next untap step. | Sleeper Dart | 1 |
| {1}{B}: Search your library for a card named Whisper Squad, put it onto the battlefield tapped, then shuffle. | Whisper Squad | 1 |
| Search your library for up to three monocolored cards with different names and exile them. An opponent chooses one of those cards. Shuffle that card into your l | Emergent Ultimatum | 1 |
| Spells with flash you cast cost {1} less to cast and can't be countered. | Cunning Nightbonder | 1 |
| {1}, {T}: Target creature can't block this turn. | Zirda, the Dawnwaker | 1 |
| Target creature fights another target creature. (Each deals damage equal to its power to the other.) | Clash of Titans | 1 |
| Target creature you control deals damage equal to its power to target creature you don't control. If the creature you control has trample, excess damage is deal | Ram Through | 1 |
| Target opponent reveals their hand. You choose a nonland card from that player's graveyard or hand and exile it. Cycling {1} ({1}, Discard this card: Draw a car | Memory Leak | 1 |
| {T}: This creature deals X damage to any target, where X is the number of times this creature has mutated. | Porcuparrot | 1 |
| This creature gets +1/+1 for each other creature you control with flying. | Skycat Sovereign | 1 |
| This creature has double strike as long as there are three or more instant and/or sorcery cards in your graveyard. | Spelleater Wolverine | 1 |
| This creature has protection from each mana value of the chosen quality. | Lavabrink Venturer | 1 |
| This spell has flash as long as you control a permanent with flash. As an additional cost to cast this spell, sacrifice a creature. Destroy target creature. | Mutual Destruction | 1 |
| When this creature enters, exile target card with a cycling ability from your graveyard. Until the end of your next turn, you may play that card. | Rooting Moloch | 1 |
| When Yorion enters, exile any number of other nonland permanents you own and control. Return those cards to the battlefield at the beginning of the next end ste | Yorion, Sky Nomad | 1 |
| Whenever a non-Human creature you control attacks, look at the top six cards of your library. You may put a Human creature card from among them onto the battlef | Winota, Joiner of Forces | 1 |
| Whenever a nontoken creature you control dies, mill two cards. Then return a creature card with lesser mana value than the creature that died from your graveyar | Death's Oasis | 1 |
| Whenever one or more creatures you control with trample deal combat damage to a player, create an X/X green Dinosaur Beast creature token with trample, where X  | Quartzwood Crasher | 1 |
| Whenever this creature attacks, if it doesn't have first strike, put a first strike counter on it. | Momentum Rumbler | 1 |
| Whenever this creature attacks, other Humans you control get +1/+0 until end of turn. | Perimeter Sergeant | 1 |
| Whenever this creature attacks, you may have the base power and toughness of target Human you control become equal to this creature's power and toughness until  | Exuberant Wolfbear | 1 |
| Whenever this creature mutates, draw a card. | Dreamtail Heron | 1 |
| Whenever this creature mutates, it deals 4 damage to target creature or planeswalker an opponent controls and you gain 4 life. | Snapdax, Apex of the Hunt | 1 |
| Whenever this creature mutates, search your library for a basic land card, put it onto the battlefield tapped, then shuffle. | Migratory Greathorn | 1 |
| Whenever this creature mutates, tap up to X target creatures, where X is the number of times this creature has mutated. Those creatures don't untap during their | Archipelagore | 1 |
| Whenever this creature mutates, target creature an opponent controls gets -2/-2 until end of turn. | Zagoth Mamba | 1 |
| Whenever you cast a noncreature spell, create an X/X blue Shark creature token with flying, where X is that spell's mana value. | Shark Typhoon | 1 |
| Whenever you cycle a card, you may have this enchantment become a 5/4 Dinosaur creature with trample and haste in addition to its other types until end of turn. | Reptilian Reflection | 1 |
| +1: You gain 2 life. Add {U}, {R}, or {W}. Spend this mana only to cast a noncreature spell. | Narset of the Ancient Way | 1 |
| Your opponents can't cast spells from anywhere other than their hands. | Drannith Magistrate | 1 |
| Zenith Flare deals X damage to any target and you gain X life, where X is the number of cards with a cycling ability in your graveyard. | Zenith Flare | 1 |

## Notes


