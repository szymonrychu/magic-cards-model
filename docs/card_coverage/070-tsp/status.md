# Time Spiral (tsp)

- Expansion: 070
- Set code: `tsp`
- Release date: 2006-10-06
- Cards in scope (Modern/Pioneer/Standard-legal): 268

## Legality

| Format | Legal cards |
|---|---|
| Modern | 268 |
| Pioneer | 6 |
| Standard | 3 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 70 | 26.1% |
| Works (untested) | 141 | 52.6% |
| Partial (unaudited) | 0 | 0.0% |
| Not working | 57 | 21.3% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Aether Web | silent | Enchanted creature gets +1/+1, has reach, and can block creatures with shadow as though they didn't have shadow. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Aetherflame Wall | silent | This creature can block creatures with shadow as though they didn't have shadow. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Barbed Shocker | silent | Whenever this creature deals damage to a player, that player discards all the cards in their hand, then draws that many cards. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Candles of Leng | silent | {4}, {T}: Reveal the top card of your library. If it has the same name as a card in your graveyard, put it into your graveyard. Otherwise, draw a card. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Castle Raptors | silent | As long as this creature is untapped, it gets +0/+2. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Chronosavant | silent | {1}{W}: Return this card from your graveyard to the battlefield tapped. You skip your next turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Clockspinning | silent | Buyback {3} (You may pay an additional {3} as you cast this spell. If you do, put this card into your hand as it resolves.) Choose a counter on target permanent | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Crookclaw Transmuter | silent | When this creature enters, switch target creature's power and toughness until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Curse of the Cabal | silent | Target player sacrifices half the permanents they control of their choice, rounded down. Suspend 2—{2}{B}{B} (Rather than cast this card from your hand, you may | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Demonic Collusion | silent | Buyback | no machine in the engine executes this keyword | Y/-/- | not_working |
| Evangelize | silent | Buyback {2}{W}{W} (You may pay an additional {2}{W}{W} as you cast this spell. If you do, put this card into your hand as it resolves.) Gain control of target c | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Foriysian Totem | silent | As long as this artifact is a creature, it can block an additional creature each combat. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Gauntlet of Power | silent | Creatures of the chosen color get +1/+1. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Glass Asp | silent | Whenever this creature deals combat damage to a player, that player loses 2 life at the beginning of their next draw step unless they pay {2} before that step. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Hypergenesis | silent | Suspend 3—{1}{G}{G} Starting with you, each player may put an artifact, creature, enchantment, or land card from their hand onto the battlefield. Repeat this pr | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Ib Halfheart, Goblin Tactician | silent | Whenever another Goblin you control becomes blocked, sacrifice it. If you do, it deals 4 damage to each creature blocking it. | this trigger's condition can never be satisfied - it never triggers | Y/-/- | not_working |
| Jhoira's Timebug | silent | {T}: Choose target permanent you control or suspended card you own. If that permanent or card has a time counter on it, you may remove a time counter from it or | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Lim-Dûl the Necromancer | silent | Whenever a creature an opponent controls dies, you may pay {1}{B}. If you do, return that card to the battlefield under your control. If it's a creature, it's a | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Magus of the Scroll | silent | {3}, {T}: Choose a card name, then reveal a card at random from your hand. If that card has the chosen name, this creature deals 2 damage to any target. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Mangara of Corondor | silent | {T}: Exile Mangara and target permanent. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Mishra, Artificer Prodigy | silent | Whenever you cast an artifact spell, you may search your graveyard, hand, and/or library for a card with the same name as that spell and put it onto the battlef | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Moonlace | silent | Target spell or permanent becomes colorless. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Nightshade Assassin | silent | When this creature enters, you may reveal X black cards in your hand. If you do, target creature gets -X/-X until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Outrider en-Kor | silent | {0}: The next 1 damage that would be dealt to this creature this turn is dealt to target creature you control instead. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Paradox Haze | silent | At the beginning of enchanted player's first upkeep each turn, that player gets an additional upkeep step after this step. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Pardic Dragon | silent | Whenever an opponent casts a spell, if this card is suspended, that player may put a time counter on this card. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Pendelhaven Elder | silent | {T}: Each 1/1 creature you control gets +1/+2 until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Phyrexian Totem | silent | Whenever this permanent is dealt damage, if it's a creature, sacrifice that many permanents. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Psychotic Episode | silent | Target player reveals their hand and the top card of their library. You choose a card revealed this way. That player puts the chosen card on the bottom of their | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Pull from Eternity | silent | Put target face-up exiled card into its owner's graveyard. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Reiterate | silent | Buyback | no machine in the engine executes this keyword | Y/-/- | not_working |
| Restore Balance | silent | Suspend 6—{W} Each player chooses a number of lands they control equal to the number of lands controlled by the player who controls the fewest, then sacrifices  | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Saffi Eriksdotter | silent | Sacrifice Saffi Eriksdotter: When target creature is put into your graveyard this turn, return that card to the battlefield. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Sangrophage | silent | At the beginning of your upkeep, tap this creature unless you pay 2 life. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Scion of the Ur-Dragon | silent | {2}: Search your library for a Dragon permanent card and put it into your graveyard. If you do, Scion of the Ur-Dragon becomes a copy of that card until end of  | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Smallpox | silent | Each player loses 1 life, discards a card, sacrifices a creature of their choice, then sacrifices a land of their choice. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Spectral Force | silent | Whenever this creature attacks, if defending player controls no black permanents, it doesn't untap during your next untap step. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Spell Burst | silent | Buyback | no machine in the engine executes this keyword | Y/-/- | not_working |
| Spirit Loop | silent | Whenever enchanted creature deals damage, you gain that much life. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Stronghold Overseer | silent | {B}{B}: Creatures with shadow get +1/+0 until end of turn and creatures without shadow get -1/-0 until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Truth or Tale | silent | Reveal the top five cards of your library and separate them into two piles. An opponent chooses one of those piles. Put a card from the chosen pile into your ha | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Walk the Aeons | silent | Buyback—Sacrifice three Islands. (You may sacrifice three Islands in addition to any other costs as you cast this spell. If you do, put this card into your hand | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Weatherseed Totem | silent | When this artifact is put into a graveyard from the battlefield, if it was a creature, return this card to its owner's hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Wormwood Dryad | silent | {G}: This creature gains forestwalk until end of turn and deals 1 damage to you. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Wurmcalling | silent | Buyback | no machine in the engine executes this keyword | Y/-/- | not_working |
| Yavimaya Dryad | silent | When this creature enters, you may search your library for a Forest card, put it onto the battlefield tapped under target player's control, then shuffle. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Zealot il-Vec | silent | Whenever this creature attacks and isn't blocked, you may have it deal 1 damage to target creature. If you do, prevent all combat damage this creature would dea | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Chronatog Totem | notice | {0}: This creature gets +3/+3 until end of turn. You skip your next turn. Activate only once each turn and only if this permanent is a creature. | unparsed remainder: You skip your next turn. | Y/-/- | not_working |
| Cyclopean Giant | notice | When this creature dies, target land becomes a Swamp. Exile this card. | unparsed remainder: Exile this card. | Y/-/- | not_working |
| Gorgon Recluse | notice | Whenever this creature blocks or becomes blocked by a nonblack creature, destroy that creature at end of combat. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Gustcloak Cavalier | notice | Whenever this creature becomes blocked, you may untap this creature and remove it from combat. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Locket of Yesterdays | notice | Spells you cast cost {1} less to cast for each card with the same name as that spell in your graveyard. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Magus of the Jar | notice | {T}, Sacrifice this creature: Each player exiles all cards from their hand face down and draws seven cards. At the beginning of the next end step, each player d | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Norin the Wary | notice | When a player casts a spell or a creature attacks, exile Norin. Return it to the battlefield under its owner's control at the beginning of the next end step. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Traitor's Clutch | notice | Target creature gets +1/+0, becomes black, and gains shadow until end of turn. (It can block or be blocked by only creatures with shadow.) Flashback {1}{B} (You | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Trickbind | notice | Split second (As long as this spell is on the stack, players can't cast spells or activate abilities that aren't mana abilities.) Counter target activated or tr | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Word of Seizing | notice | Split second (As long as this spell is on the stack, players can't cast spells or activate abilities that aren't mana abilities.) Untap target permanent and gai | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Academy Ruins | handled | {1}{U}, {T}: Put target artifact card from your graveyard on top of your library. | the engine reads this text and performs it | Y/-/- | not_tested |
| Amrou Scout | handled | {4}, {T}: Search your library for a Rebel permanent card with mana value 3 or less, put it onto the battlefield, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ancient Grudge | handled | Destroy target artifact. Flashback {G} (You may cast this card from your graveyard for its flashback cost. Then exile it.) | the engine reads this text and performs it | Y/-/- | not_tested |
| Ashcoat Bear | handled | Flash | machines/casting.py (timing) | Y/-/- | not_tested |
| Aspect of Mongoose | handled | Enchanted creature has shroud. | the engine reads this text and performs it | Y/-/- | not_tested |
| Assassinate | handled | Destroy target tapped creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Basal Sliver | handled | All Slivers have "Sacrifice this permanent: Add {B}{B}." | the engine reads this text and performs it | Y/-/- | not_tested |
| Basalt Gargoyle | handled | {R}: This creature gets +0/+1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Benalish Cavalry | handled | Flanking | machines/keywords.py | Y/-/- | not_tested |
| Bewilder | handled | Target creature gets -3/-0 until end of turn. Draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Blazing Blade Askari | handled | {2}: This creature becomes colorless until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Bogardan Hellkite | handled | When this creature enters, it deals 5 damage divided as you choose among any number of targets. | the engine reads this text and performs it | Y/-/- | not_tested |
| Bogardan Rager | handled | When this creature enters, target creature gets +4/+0 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Bonesplitter Sliver | handled | All Sliver creatures get +2/+0. | the engine reads this text and performs it | Y/-/- | not_tested |
| Brass Gnat | handled | This creature doesn't untap during your untap step. | the engine reads this text and performs it | Y/-/- | not_tested |
| Call to the Netherworld | handled | Return target black creature card from your graveyard to your hand. Madness {0} (If you discard this card, discard it into exile. When you do, cast it for its m | the engine reads this text and performs it | Y/-/- | not_tested |
| Cancel | handled | Counter target spell. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Careful Consideration | handled | Target player draws four cards, then discards three cards. If you cast this spell during your main phase, instead that player draws four cards, then discards tw | the engine reads this text and performs it | Y/-/- | not_tested |
| Celestial Crusader | handled | Other white creatures get +1/+1. | the engine reads this text and performs it | Y/-/- | not_tested |
| Chromatic Star | handled | When this artifact is put into a graveyard from the battlefield, draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Cloudchaser Kestrel | handled | When this creature enters, destroy target enchantment. | the engine reads this text and performs it | Y/-/- | not_tested |
| Conflagrate | handled | Conflagrate deals X damage divided as you choose among any number of targets. Flashback—{R}{R}, Discard X cards. (You may cast this card from your graveyard for | the engine reads this text and performs it | Y/-/- | not_tested |
| Coral Trickster | handled | When this creature is turned face up, you may tap or untap target permanent. | the engine reads this text and performs it | Y/-/- | not_tested |
| Corpulent Corpse | handled | Suspend | machines/casting.py (MarkedExile.suspend, finish_suspend) | Y/-/- | not_tested |
| D'Avenant Healer | handled | {T}: This creature deals 1 damage to target attacking or blocking creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Dark Withering | handled | Destroy target nonblack creature. Madness {B} (If you discard this card, discard it into exile. When you do, cast it for its madness cost or put it into your gr | the engine reads this text and performs it | Y/-/- | not_tested |
| Deathspore Thallid | handled | At the beginning of your upkeep, put a spore counter on this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Deep-Sea Kraken | handled | This creature can't be blocked. | the engine reads this text and performs it | Y/-/- | not_tested |
| Dementia Sliver | handled | All Slivers have "{T}: Choose a card name. Target opponent reveals a card at random from their hand. If that card has the chosen name, that player discards it.  | the engine reads this text and performs it | Y/-/- | not_tested |
| Divine Congregation | handled | You gain 2 life for each creature target player controls. Suspend 5—{1}{W} (Rather than cast this card from your hand, you may pay {1}{W} and exile it with five | the engine reads this text and performs it | Y/-/- | not_tested |
| Draining Whelk | handled | When this creature enters, counter target spell. Put X +1/+1 counters on this creature, where X is that spell's mana value. | the engine reads this text and performs it | Y/-/- | not_tested |
| Dread Return | handled | Return target creature card from your graveyard to the battlefield. Flashback—Sacrifice three creatures. (You may cast this card from your graveyard for its fla | the engine reads this text and performs it | Y/-/- | not_tested |
| Dream Stalker | handled | When this creature enters, return a permanent you control to its owner's hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Drifter il-Dal | handled | At the beginning of your upkeep, sacrifice this creature unless you pay {U}. | the engine reads this text and performs it | Y/-/- | not_tested |
| Drudge Reavers | handled | {B}: Regenerate this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Durkwood Baloth | handled | Suspend | machines/casting.py (MarkedExile.suspend, finish_suspend) | Y/-/- | not_tested |
| Duskrider Peregrine | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Errant Doomsayers | handled | {T}: Tap target creature with toughness 2 or less. | the engine reads this text and performs it | Y/-/- | not_tested |
| Errant Ephemeron | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Eternity Snare | handled | When this Aura enters, draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Faceless Devourer | handled | When this creature enters, exile another target creature with shadow. | the engine reads this text and performs it | Y/-/- | not_tested |
| Fallen Ideal | handled | Enchanted creature has flying and "Sacrifice a creature: This creature gets +2/+1 until end of turn." | the engine reads this text and performs it | Y/-/- | not_tested |
| Fathom Seer | handled | When this creature is turned face up, draw two cards. | the engine reads this text and performs it | Y/-/- | not_tested |
| Feebleness | handled | Enchanted creature gets -2/-1. | the engine reads this text and performs it | Y/-/- | not_tested |
| Firemaw Kavu | handled | When this creature enters, it deals 2 damage to target creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Firewake Sliver | handled | All Sliver creatures have haste. | the engine reads this text and performs it | Y/-/- | not_tested |
| Fledgling Mawcor | handled | {T}: This creature deals 1 damage to any target. | the engine reads this text and performs it | Y/-/- | not_tested |
| Flickering Spirit | handled | {3}{W}: Exile this creature, then return it to the battlefield under its owner's control. | the engine reads this text and performs it | Y/-/- | not_tested |
| Flowstone Channeler | handled | {1}{R}, {T}, Discard a card: Target creature gets +1/-1 and gains haste until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Fool's Demise | handled | When enchanted creature dies, return that card to the battlefield under your control. | the engine reads this text and performs it | Y/-/- | not_tested |
| Fortune Thief | handled | Damage that would reduce your life total to less than 1 reduces it to 1 instead. | the engine reads this text and performs it | Y/-/- | not_tested |
| Fury Sliver | handled | All Sliver creatures have double strike. | the engine reads this text and performs it | Y/-/- | not_tested |
| Gaze of Justice | handled | As an additional cost to cast this spell, tap three untapped white creatures you control. Exile target creature. Flashback {5}{W} (You may cast this card from y | the engine reads this text and performs it | Y/-/- | not_tested |
| Gemhide Sliver | handled | All Slivers have "{T}: Add one mana of any color." | the engine reads this text and performs it | Y/-/- | not_tested |
| Ghitu Firebreathing | handled | {R}: Enchanted creature gets +1/+0 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ghostflame Sliver | handled | All Slivers are colorless. | the engine reads this text and performs it | Y/-/- | not_tested |
| Goblin Skycutter | handled | Sacrifice this creature: It deals 2 damage to target creature with flying. That creature loses flying until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Greenseeker | handled | {G}, {T}, Discard a card: Search your library for a basic land card, reveal it, put it into your hand, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Griffin Guide | handled | Enchanted creature gets +2/+2 and has flying. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ground Rift | handled | Target creature without flying can't block this turn. Storm (When you cast this spell, copy it for each spell cast before it this turn. You may choose new targe | the engine reads this text and performs it | Y/-/- | not_tested |
| Harmonic Sliver | handled | All Slivers have "When this permanent enters, destroy target artifact or enchantment." | the engine reads this text and performs it | Y/-/- | not_tested |
| Havenwood Wurm | handled | Trample | machines/combat.py | Y/-/- | not_tested |
| Hivestone | handled | Creatures you control are Slivers in addition to their other creature types. | the engine reads this text and performs it | Y/-/- | not_tested |
| Icatian Crier | handled | {1}{W}, {T}, Discard a card: Create two 1/1 white Citizen creature tokens. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ironclaw Buzzardiers | handled | This creature can't block creatures with power 2 or greater. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ivory Giant | handled | When this creature enters, tap all nonwhite creatures. | the engine reads this text and performs it | Y/-/- | not_tested |
| Kaervek the Merciless | handled | Whenever an opponent casts a spell, Kaervek deals damage equal to that spell's mana value to any target. | the engine reads this text and performs it | Y/-/- | not_tested |
| Keldon Halberdier | handled | Suspend | machines/casting.py (MarkedExile.suspend, finish_suspend) | Y/-/- | not_tested |
| Kher Keep | handled | {1}{R}, {T}: Create a 0/1 red Kobold creature token named Kobolds of Kher Keep. | the engine reads this text and performs it | Y/-/- | not_tested |
| Lightning Axe | handled | As an additional cost to cast this spell, discard a card or pay {5}. Lightning Axe deals 5 damage to target creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Looter il-Kor | handled | Whenever this creature deals damage to an opponent, draw a card, then discard a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Magus of the Candelabra | handled | {X}, {T}: Untap X target lands. | the engine reads this text and performs it | Y/-/- | not_tested |
| Magus of the Disk | handled | This creature enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Magus of the Mirror | handled | {T}, Sacrifice this creature: Exchange life totals with target opponent. Activate only during your upkeep. | the engine reads this text and performs it | Y/-/- | not_tested |
| Mana Skimmer | handled | Whenever this creature deals damage to a player, tap target land that player controls. That land doesn't untap during its controller's next untap step. | the engine reads this text and performs it | Y/-/- | not_tested |
| Might Sliver | handled | All Sliver creatures get +2/+2. | the engine reads this text and performs it | Y/-/- | not_tested |
| Might of Old Krosa | handled | Target creature gets +2/+2 until end of turn. If you cast this spell during your main phase, that creature gets +4/+4 until end of turn instead. | the engine reads this text and performs it | Y/-/- | not_tested |
| Mindlash Sliver | handled | All Slivers have "{1}, Sacrifice this permanent: Each player discards a card." | the engine reads this text and performs it | Y/-/- | not_tested |
| Mindstab | handled | Target player discards three cards. Suspend 4—{B} (Rather than cast this card from your hand, you may pay {B} and exile it with four time counters on it. At the | the engine reads this text and performs it | Y/-/- | not_tested |
| Mogg War Marshal | handled | When this creature enters or dies, create a 1/1 red Goblin creature token. | the engine reads this text and performs it | Y/-/- | not_tested |
| Molder | handled | Destroy target artifact or enchantment with mana value X. It can't be regenerated. You gain X life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Momentary Blink | handled | Exile target creature you control, then return it to the battlefield under its owner's control. Flashback {3}{U} (You may cast this card from your graveyard for | the engine reads this text and performs it | Y/-/- | not_tested |
| Mwonvuli Acid-Moss | handled | Destroy target land. Search your library for a Forest card, put that card onto the battlefield tapped, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Nantuko Shaman | handled | When this creature enters, if you control no tapped lands, draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Nether Traitor | handled | Whenever another creature is put into your graveyard from the battlefield, you may pay {B}. If you do, return this card from your graveyard to the battlefield. | the engine reads this text and performs it | Y/-/- | not_tested |
| Opaline Sliver | handled | All Slivers have "Whenever this permanent becomes the target of a spell an opponent controls, you may draw a card." | the engine reads this text and performs it | Y/-/- | not_tested |
| Ophidian Eye | handled | Whenever enchanted creature deals damage to an opponent, you may draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Paradise Plume | handled | As this artifact enters, choose a color. | the engine reads this text and performs it | Y/-/- | not_tested |
| Pentarch Paladin | handled | As this creature enters, choose a color. | the engine reads this text and performs it | Y/-/- | not_tested |
| Penumbra Spider | handled | When this creature dies, create a 2/4 black Spider creature token with reach. | the engine reads this text and performs it | Y/-/- | not_tested |
| Plague Sliver | handled | All Slivers have "At the beginning of your upkeep, this permanent deals 1 damage to you." | the engine reads this text and performs it | Y/-/- | not_tested |
| Plunder | handled | Destroy target artifact or land. Suspend 4—{1}{R} (Rather than cast this card from your hand, you may pay {1}{R} and exile it with four time counters on it. At  | the engine reads this text and performs it | Y/-/- | not_tested |
| Premature Burial | handled | Destroy target nonblack creature that entered since your last turn ended. | the engine reads this text and performs it | Y/-/- | not_tested |
| Prismatic Lens | handled |  |  | Y/-/- | not_tested |
| Psionic Sliver | handled | All Sliver creatures have "{T}: This creature deals 2 damage to any target and 3 damage to itself." | the engine reads this text and performs it | Y/-/- | not_tested |
| Quilled Sliver | handled | All Slivers have "{T}: This permanent deals 1 damage to target attacking or blocking creature." | the engine reads this text and performs it | Y/-/- | not_tested |
| Return to Dust | handled | Exile target artifact or enchantment. If you cast this spell during your main phase, you may exile up to one other target artifact or enchantment. | the engine reads this text and performs it | Y/-/- | not_tested |
| Riftwing Cloudskate | handled | When this creature enters, return target permanent to its owner's hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Sage of Epityr | handled | When this creature enters, look at the top four cards of your library, then put them back in any order. | the engine reads this text and performs it | Y/-/- | not_tested |
| Scarwood Treefolk | handled | This creature enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Screeching Sliver | handled | All Slivers have "{T}: Target player mills a card." | the engine reads this text and performs it | Y/-/- | not_tested |
| Scryb Ranger | handled | Return a Forest you control to its owner's hand: Untap target creature. Activate only once each turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Search for Tomorrow | handled | Search your library for a basic land card, put it onto the battlefield, then shuffle. Suspend 2—{G} (Rather than cast this card from your hand, you may pay {G}  | the engine reads this text and performs it | Y/-/- | not_tested |
| Sengir Nosferatu | handled | {1}{B}, Exile this creature: Create a 1/2 black Bat creature token with flying. It has "{1}{B}, Sacrifice this token: Return an exiled card named Sengir Nosfera | the engine reads this text and performs it | Y/-/- | not_tested |
| Shadow Sliver | handled | All Sliver creatures have shadow. | the engine reads this text and performs it | Y/-/- | not_tested |
| Skittering Monstrosity | handled | When you cast a creature spell, sacrifice this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Skulking Knight | handled | When this creature becomes the target of a spell or ability, sacrifice it. | the engine reads this text and performs it | Y/-/- | not_tested |
| Spike Tiller | handled | This creature enters with three +1/+1 counters on it. | the engine reads this text and performs it | Y/-/- | not_tested |
| Spiketail Drakeling | handled | Sacrifice this creature: Counter target spell unless its controller pays {2}. | the engine reads this text and performs it | Y/-/- | not_tested |
| Spinneret Sliver | handled | All Sliver creatures have reach. | the engine reads this text and performs it | Y/-/- | not_tested |
| Sprite Noble | handled | Other creatures you control with flying get +0/+1. | the engine reads this text and performs it | Y/-/- | not_tested |
| Stonebrow, Krosan Hero | handled | Whenever a creature you control with trample attacks, it gets +2/+2 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Stonewood Invocation | handled | Split second (As long as this spell is on the stack, players can't cast spells or activate abilities that aren't mana abilities.) Target creature gets +5/+5 and | the engine reads this text and performs it | Y/-/- | not_tested |
| Strangling Soot | handled | Destroy target creature with toughness 3 or less. Flashback {5}{R} (You may cast this card from your graveyard for its flashback cost. Then exile it.) | the engine reads this text and performs it | Y/-/- | not_tested |
| Subterranean Shambler | handled | When this creature enters or leaves the battlefield, it deals 1 damage to each creature without flying. | the engine reads this text and performs it | Y/-/- | not_tested |
| Sudden Death | handled | Split second (As long as this spell is on the stack, players can't cast spells or activate abilities that aren't mana abilities.) Target creature gets -4/-4 unt | the engine reads this text and performs it | Y/-/- | not_tested |
| Sulfurous Blast | handled | Sulfurous Blast deals 2 damage to each creature and each player. If you cast this spell during your main phase, Sulfurous Blast deals 3 damage to each creature  | the engine reads this text and performs it | Y/-/- | not_tested |
| Swarmyard | handled | {T}: Regenerate target Insect, Rat, Spider, or Squirrel. | the engine reads this text and performs it | Y/-/- | not_tested |
| Tectonic Fiend | handled | This creature attacks each combat if able. | the engine reads this text and performs it | Y/-/- | not_tested |
| Telekinetic Sliver | handled | All Slivers have "{T}: Tap target permanent." | the engine reads this text and performs it | Y/-/- | not_tested |
| Temporal Eddy | handled | Put target creature or land on top of its owner's library. | the engine reads this text and performs it | Y/-/- | not_tested |
| Tendrils of Corruption | handled | Tendrils of Corruption deals X damage to target creature and you gain X life, where X is the number of Swamps you control. | the engine reads this text and performs it | Y/-/- | not_tested |
| Think Twice | handled | Draw a card. Flashback {2}{U} (You may cast this card from your graveyard for its flashback cost. Then exile it.) | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Thrill of the Hunt | handled | Target creature gets +1/+2 until end of turn. Flashback {W} (You may cast this card from your graveyard for its flashback cost. Then exile it.) | the engine reads this text and performs it | Y/-/- | not_tested |
| Thunder Totem | handled | {1}{W}{W}: This artifact becomes a 2/2 white Spirit artifact creature with flying and first strike until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Tivadar of Thorn | handled | When Tivadar enters, destroy target Goblin. | the engine reads this text and performs it | Y/-/- | not_tested |
| Tolarian Sentinel | handled | {U}, {T}, Discard a card: Return target permanent you control to its owner's hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Trespasser il-Vec | handled | Discard a card: This creature gains shadow until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Triskelavus | handled | This creature enters with three +1/+1 counters on it. | the engine reads this text and performs it | Y/-/- | not_tested |
| Two-Headed Sliver | handled | All Sliver creatures have menace. | the engine reads this text and performs it | Y/-/- | not_tested |
| Unyaro Bees | handled | {G}: This creature gets +1/+1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Venser's Sliver | handled |  |  | Y/-/- | not_tested |
| Verdant Embrace | handled | Enchanted creature gets +3/+3 and has "At the beginning of each upkeep, create a 1/1 green Saproling creature token." | the engine reads this text and performs it | Y/-/- | not_tested |
| Viashino Bladescout | handled | When this creature enters, target creature gains first strike until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Viscerid Deepwalker | handled | {U}: This creature gets +1/+0 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Viscid Lemures | handled | {0}: This creature gets -1/-0 and gains swampwalk until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Voidmage Husher | handled | When this creature enters, counter target activated ability. | the engine reads this text and performs it | Y/-/- | not_tested |
| Volcanic Awakening | handled | Destroy target land. Storm (When you cast this spell, copy it for each spell cast before it this turn. You may choose new targets for the copies.) | the engine reads this text and performs it | Y/-/- | not_tested |
| Watcher Sliver | handled | All Sliver creatures get +0/+2. | the engine reads this text and performs it | Y/-/- | not_tested |
| Wheel of Fate | handled | Suspend 4—{1}{R} (Rather than cast this card from your hand, pay {1}{R} and exile it with four time counters on it. At the beginning of your upkeep, remove a ti | the engine reads this text and performs it | Y/-/- | not_tested |
| Wipe Away | handled | Split second (As long as this spell is on the stack, players can't cast spells or activate abilities that aren't mana abilities.) Return target permanent to its | the engine reads this text and performs it | Y/-/- | not_tested |

## Fully supported

<details>
<summary>70 cards</summary>

- Amrou Seekers
- Ancestral Vision
- Angel's Grace
- Assembly-Worker
- Brine Elemental
- Calciform Pools
- Cavalry Master
- Chameleon Blur
- Children of Korlis
- Clockwork Hydra
- Coal Stoker
- Dralnu, Lich Lord
- Dreadship Reef
- Durkwood Tracker
- Empty the Warrens
- Endrek Sahr, Master Breeder
- Evil Eye of Urborg
- Flagstones of Trokair
- Flamecore Elemental
- Foriysian Interceptor
- Fortify
- Fungal Reaches
- Fungus Sliver
- Gemstone Caverns
- Grapeshot
- Greater Gargadon
- Haunting Hymn
- Ignite Memories
- Ith, High Arcanist
- Ixidron
- Jaya Ballard, Task Mage
- Knight of the Holy Nimbus
- Krosan Grip
- Liege of the Pit
- Living End
- Lotus Bloom
- Molten Slagheap
- Mystical Teachings
- Opal Guardian
- Orcish Cannonade
- Pentarch Ward
- Phantom Wurm
- Phthisis
- Pit Keeper
- Plated Pegasus
- Pulmonic Sliver
- Rift Bolt
- Saltcrusted Steppe
- Sarpadian Empires, Vol. VII
- Sedge Sliver
- Serra Avenger
- Sidewinder Sliver
- Slipstream Serpent
- Snapback
- Squall Line
- Stormcloud Djinn
- Stuffy Doll
- Sudden Shock
- Sudden Spoiling
- Teferi, Mage of Zhalfir
- Temporal Isolation
- Thelon of Havenwood
- Thick-Skinned Goblin
- Tromp the Domains
- Urborg Syphon-Mage
- Urza's Factory
- Vampiric Sliver
- Vesuva
- Vesuvan Shapeshifter
- Weathered Bodyguards

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| buyback | 4 | Demonic Collusion, Reiterate, Spell Burst, Wurmcalling | tsp |
| as long as ~ is a creature, it can block an additional creature each combat. | 1 | Foriysian Totem | tsp |
| as long as ~ is untapped, it gets +N/+N. | 1 | Castle Raptors | tsp |
| at the beginning of enchanted player's first upkeep each turn, that player gets an additional upkeep step after ~. | 1 | Paradox Haze | tsp |
| at the beginning of your upkeep, tap ~ unless you pay N life. | 1 | Sangrophage | tsp |
| buyback {M} (you may pay an additional {M} as you cast ~. if you do, put ~ into your hand as it resolves.) choose a counter on target permanent or suspended car | 1 | Clockspinning | tsp |
| buyback {M}{M}{M} (you may pay an additional {M}{M}{M} as you cast ~. if you do, put ~ into your hand as it resolves.) gain control of target creature of an opp | 1 | Evangelize | tsp |
| buyback—sacrifice three islands. (you may sacrifice three islands in addition to any other costs as you cast ~. if you do, put ~ into your hand as it resolves.) | 1 | Walk the Aeons | tsp |
| creatures of the chosen color get +N/+N. | 1 | Gauntlet of Power | tsp |
| each player loses N life, discards a card, sacrifices a creature of their choice, then sacrifices a land of their choice. | 1 | Smallpox | tsp |
| enchanted creature gets +N/+N, has reach, and can block creatures with shadow as though they didn't have shadow. | 1 | Aether Web | tsp |
| put target face-up exiled card into its owner's graveyard. | 1 | Pull from Eternity | tsp |
| reveal the top five cards of your library and separate them into two piles. an opponent chooses one of those piles. put a card from the chosen pile into your ha | 1 | Truth or Tale | tsp |
| sacrifice ~: when target creature is put into your graveyard ~, return that card to the battlefield. | 1 | Saffi Eriksdotter | tsp |
| spells you cast cost {M} less to cast for each card with the same name as that spell in your graveyard. | 1 | Locket of Yesterdays | tsp |
| split second (as long as ~ is on the stack, players can"..."t mana abilities.) counter target activated or triggered ability. if a permanent"..."t be activated  | 1 | Trickbind | tsp |
| split second (as long as ~ is on the stack, players can"..."t mana abilities.) untap target permanent and gain control of it until end of turn. it gains haste u | 1 | Word of Seizing | tsp |
| suspend N—{M} each player chooses a number of lands they control equal to the number of lands controlled by the player who controls the fewest, then sacrifices  | 1 | Restore Balance | tsp |
| suspend N—{M}{M}{M} starting with you, each player may put an artifact, creature, enchantment, or land card from their hand onto the battlefield. repeat ~ until | 1 | Hypergenesis | tsp |
| target creature gets +N/+N, becomes black, and gains shadow until end of turn. (it can block or be blocked by only creatures with shadow.) flashback {M}{M} (you | 1 | Traitor's Clutch | tsp |
| target player reveals their hand and the top card of their library. you choose a card revealed ~. that player puts the chosen card on the bottom of their librar | 1 | Psychotic Episode | tsp |
| target player sacrifices half the permanents they control of their choice, rounded down. suspend N—{M}{M}{M} (rather than cast ~ from your hand, you may pay {M} | 1 | Curse of the Cabal | tsp |
| target spell or permanent becomes colorless. | 1 | Moonlace | tsp |
| when a player casts a spell or a creature attacks, exile norin. return it to the battlefield under its owner's control at the beginning of the next end step. | 1 | Norin the Wary | tsp |
| when ~ dies, target land becomes a swamp. exile ~. | 1 | Cyclopean Giant | tsp |
| when ~ enters, switch target creature's power and toughness until end of turn. | 1 | Crookclaw Transmuter | tsp |
| when ~ enters, you may reveal N black cards in your hand. if you do, target creature gets -N/-N until end of turn. | 1 | Nightshade Assassin | tsp |
| when ~ enters, you may search your library for a forest card, put it onto the battlefield tapped under target player's control, then shuffle. | 1 | Yavimaya Dryad | tsp |
| when ~ is put into a graveyard from the battlefield, if it was a creature, return ~ to its owner's hand. | 1 | Weatherseed Totem | tsp |
| whenever a creature an opponent controls dies, you may pay {M}{M}. if you do, return that card to the battlefield under your control. if it"..."s a zombie in ad | 1 | Lim-Dûl the Necromancer | tsp |
| whenever an opponent casts a spell, if ~ is suspended, that player may put a time counter on ~. | 1 | Pardic Dragon | tsp |
| whenever another goblin you control becomes blocked, sacrifice it. if you do, it deals N damage to each creature blocking it. | 1 | Ib Halfheart, Goblin Tactician | tsp |
| whenever enchanted creature deals damage, you gain that much life. | 1 | Spirit Loop | tsp |
| whenever you cast an artifact spell, you may search your graveyard, hand, and/or library for a card with the same name as that spell and put it onto the battlef | 1 | Mishra, Artificer Prodigy | tsp |
| whenever ~ attacks and isn't blocked, you may have it deal N damage to target creature. if you do, prevent all combat damage ~ would deal ~. | 1 | Zealot il-Vec | tsp |
| whenever ~ attacks, if defending player controls no black permanents, it doesn't untap during your next untap step. | 1 | Spectral Force | tsp |
| whenever ~ becomes blocked, you may untap ~ and remove it from combat. | 1 | Gustcloak Cavalier | tsp |
| whenever ~ blocks or becomes blocked by a nonblack creature, destroy that creature at end of combat. | 1 | Gorgon Recluse | tsp |
| whenever ~ deals combat damage to a player, that player loses N life at the beginning of their next draw step unless they pay {M} before that step. | 1 | Glass Asp | tsp |
| whenever ~ deals damage to a player, that player discards all the cards in their hand, then draws that many cards. | 1 | Barbed Shocker | tsp |
| whenever ~ is dealt damage, if it's a creature, sacrifice that many permanents. | 1 | Phyrexian Totem | tsp |
| {M}, sacrifice ~: each player exiles all cards from their hand face down and draws seven cards. at the beginning of the next end step, each player discards thei | 1 | Magus of the Jar | tsp |
| {M}, {M}: choose a card name, then reveal a card at random from your hand. if that card has the chosen name, ~ deals N damage to any target. | 1 | Magus of the Scroll | tsp |
| {M}, {M}: reveal the top card of your library. if it has the same name as a card in your graveyard, put it into your graveyard. otherwise, draw a card. | 1 | Candles of Leng | tsp |
| {M}: choose target permanent you control or suspended card you own. if that permanent or card has a time counter on it, you may remove a time counter from it or | 1 | Jhoira's Timebug | tsp |
| {M}: each N/N creature you control gets +N/+N until end of turn. | 1 | Pendelhaven Elder | tsp |
| {M}: exile mangara and target permanent. | 1 | Mangara of Corondor | tsp |
| {M}: search your library for a dragon permanent card and put it into your graveyard. if you do, ~ becomes a copy of that card until end of turn. then shuffle. | 1 | Scion of the Ur-Dragon | tsp |
| {M}: the next N damage that would be dealt to ~ ~ is dealt to target creature you control instead. | 1 | Outrider en-Kor | tsp |
| {M}: ~ gains forestwalk until end of turn and deals N damage to you. | 1 | Wormwood Dryad | tsp |
| {M}: ~ gets +N/+N until end of turn. you skip your next turn. activate only once each turn and only if ~ is a creature. | 1 | Chronatog Totem | tsp |
| {M}{M}: creatures with shadow get +N/+N until end of turn and creatures without shadow get -N/-N until end of turn. | 1 | Stronghold Overseer | tsp |
| {M}{M}: return ~ from your graveyard to the battlefield tapped. you skip your next turn. | 1 | Chronosavant | tsp |
| ~ can block creatures with shadow as though they didn't have shadow. | 1 | Aetherflame Wall | tsp |

## Notes


