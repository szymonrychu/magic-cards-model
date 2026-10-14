# Shadows over Innistrad (soi)

- Expansion: 171
- Set code: `soi`
- Release date: 2016-04-08
- Cards in scope (Modern/Pioneer/Standard-legal): 261

## Legality

| Format | Legal cards |
|---|---|
| Modern | 261 |
| Pioneer | 261 |
| Standard | 3 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 43 | 16.5% |
| Works (untested) | 189 | 72.4% |
| Partial (unaudited) | 0 | 0.0% |
| Not working | 29 | 11.1% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Breakneck Rider // Neck Breaker | silent | Attacking creatures you control get +1/+0 and have trample. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Corrupted Grafstone | silent | {T}: Choose a color of a card in your graveyard. Add one mana of that color. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Creeping Dread | silent | At the beginning of your upkeep, each player discards a card. Each opponent who discarded a card that shares a card type with the card you discarded loses 3 lif | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Cult of the Waxing Moon | silent | Whenever a permanent you control transforms into a non-Human creature, create a 2/2 green Wolf creature token. | the engine does not recognise this trigger's condition - it never triggers | Y/Y/- | not_working |
| Epiphany at the Drownyard | silent | Reveal the top X plus one cards of your library and separate them into two piles. An opponent chooses one of those piles. Put that pile into your hand and the o | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Erdwal Illuminator | silent | Whenever you investigate for the first time each turn, investigate an additional time. | the engine does not recognise this trigger's condition - it never triggers | Y/Y/- | not_working |
| Ever After | silent | Return up to two target creature cards from your graveyard to the battlefield. Each of those creatures is a black Zombie in addition to its other colors and typ | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Flameblade Angel | silent | Whenever a source an opponent controls deals damage to you or a permanent you control, you may have this creature deal 1 damage to that source's controller. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Fork in the Road | silent | Search your library for up to two basic land cards and reveal them. Put one into your hand and the other into your graveyard. Then shuffle. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| From Under the Floorboards | silent | Madness {X}{B}{B} (If you discard this card, discard it into exile. When you do, cast it for its madness cost or put it into your graveyard.) Create three tappe | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Geier Reach Bandit // Vildin-Pack Alpha | silent | Whenever a Werewolf you control enters, you may transform it. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Harness the Storm | silent | Whenever you cast an instant or sorcery spell from your hand, you may cast target card with the same name as that spell from your graveyard. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Invasive Surgery | silent | Counter target sorcery spell. Delirium — If there are four or more card types among cards in your graveyard, search the graveyard, hand, and library of that spe | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Neglected Heirloom // Ashmouth Blade | silent | When equipped creature transforms, transform this Equipment. | the engine does not recognise this trigger's condition - it never triggers | Y/Y/- | not_working |
| Not Forgotten | silent | Put target card from a graveyard on your choice of the top or bottom of its owner's library. Create a 1/1 white Spirit creature token with flying. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Olivia, Mobilized for War | silent | Whenever another creature you control enters, you may discard a card. If you do, put a +1/+1 counter on that creature, it gains haste until end of turn, and it  | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Sage of Ancient Lore // Werewolf of Ancient Hunger | silent | Werewolf of Ancient Hunger's power and toughness are each equal to the total number of cards in all players' hands. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Seasons Past | silent | Return any number of cards with different mana values from your graveyard to your hand. Put Seasons Past on the bottom of its owner's library. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Second Harvest | silent | For each token you control, create a token that's a copy of that permanent. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Startled Awake // Persistent Nightmare | silent | {3}{U}{U}: Put this card from your graveyard onto the battlefield transformed. Activate only as a sorcery. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| The Gitrog Monster | silent | At the beginning of your upkeep, sacrifice The Gitrog Monster unless you sacrifice a land. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Vessel of Nascency | silent | {1}{G}, Sacrifice this enchantment: Reveal the top four cards of your library. You may put an artifact, creature, enchantment, land, or planeswalker card from a | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Welcome to the Fold | silent | Madness {X}{U}{U} (If you discard this card, discard it into exile. When you do, cast it for its madness cost or put it into your graveyard.) Gain control of ta | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Altered Ego | notice | You may have this creature enter as a copy of any creature on the battlefield, except it enters with X additional +1/+1 counters on it. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Avacyn's Judgment | notice | Madness {X}{R} (If you discard this card, discard it into exile. When you do, cast it for its madness cost or put it into your graveyard.) Avacyn's Judgment dea | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Essence Flux | notice | Exile target creature you control, then return that card to the battlefield under its owner's control. If it's a Spirit, put a +1/+1 counter on it. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Malevolent Whispers | notice | Gain control of target creature until end of turn. Untap that creature. It gets +2/+0 and gains haste until end of turn. Madness {3}{R} (If you discard this car | unparsed remainder: Untap that creature. It gets +2/+0 and gains haste until end of turn. | Y/Y/- | not_working |
| Pick the Brain | notice | Target opponent reveals their hand. You choose a nonland card from it and exile that card. Delirium — If there are four or more card types among cards in your g | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Triskaidekaphobia | notice | At the beginning of your upkeep, choose one — • Each player with exactly 13 life loses the game, then each player gains 1 life. • Each player with exactly 13 li | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Aberrant Researcher // Perfected Form | handled | At the beginning of your upkeep, mill a card. If an instant or sorcery card was milled this way, transform this creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Aim High | handled | Untap target creature. It gets +2/+2 and gains reach until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Alms of the Vein | handled | Target opponent loses 3 life and you gain 3 life. Madness {B} (If you discard this card, discard it into exile. When you do, cast it for its madness cost or put | the engine reads this text and performs it | Y/Y/- | not_tested |
| Angel of Deliverance | handled | Delirium — Whenever this creature deals damage, if there are four or more card types among cards in your graveyard, exile target creature an opponent controls. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Angelic Purge | handled | As an additional cost to cast this spell, sacrifice a permanent. Exile target artifact, creature, or enchantment. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Anguished Unmaking | handled | Exile target nonland permanent. You lose 3 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Apothecary Geist | handled | When this creature enters, if you control another Spirit, you gain 3 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Arlinn Kord // Arlinn, Embraced by the Moon | handled | +1: Until end of turn, up to one target creature gets +2/+2 and gains vigilance and haste. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Asylum Visitor | handled | At the beginning of each player's upkeep, if that player has no cards in hand, you draw a card and you lose 1 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Autumnal Gloom // Ancient of the Equinox | handled | {B}: Mill a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Behind the Scenes | handled | Creatures you control have skulk. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Biting Rain | handled | All creatures get -2/-2 until end of turn. Madness {2}{B} (If you discard this card, discard it into exile. When you do, cast it for its madness cost or put it  | the engine reads this text and performs it | Y/Y/- | not_tested |
| Bloodmad Vampire | handled | Whenever this creature deals combat damage to a player, put a +1/+1 counter on it. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Broken Concentration | handled | Counter target spell. Madness {3}{U} (If you discard this card, discard it into exile. When you do, cast it for its madness cost or put it into your graveyard.) | the engine reads this text and performs it | Y/Y/- | not_tested |
| Bygone Bishop | handled | Whenever you cast a creature spell with mana value 3 or less, investigate. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Byway Courier | handled | When this creature dies, investigate. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Call the Bloodline | handled | {1}, Discard a card: Create a 1/1 black Vampire Knight creature token with lifelink. Activate only once each turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Cathar's Companion | handled | Whenever you cast a noncreature spell, this creature gains indestructible until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Chaplain's Blessing | handled | You gain 5 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Choked Estuary | handled | As this land enters, you may reveal an Island or Swamp card from your hand. If you don't, this land enters tapped. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Confirm Suspicions | handled | Counter target spell. Investigate three times. (To investigate, create a Clue token. It's an artifact with "{2}, Sacrifice this token: Draw a card.") | the engine reads this text and performs it | Y/Y/- | not_tested |
| Confront the Unknown | handled | Investigate, then target creature gets +1/+1 until end of turn for each Clue you control. (Create a Clue token. It's an artifact with "{2}, Sacrifice this token | the engine reads this text and performs it | Y/Y/- | not_tested |
| Convicted Killer // Branded Howler | handled | At the beginning of each upkeep, if no spells were cast last turn, transform this creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Crawling Sensation | handled | At the beginning of your upkeep, you may mill two cards. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Crow of Dark Tidings | handled | When this creature enters or dies, mill two cards. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Dance with Devils | handled | Create two 1/1 red Devil creature tokens. They have "When this token dies, it deals 1 damage to any target." | the engine reads this text and performs it | Y/Y/- | not_tested |
| Daring Sleuth // Bearer of Overwhelming Truths | handled | When you sacrifice a Clue, transform this creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Dauntless Cathar | handled | {1}{W}, Exile this card from your graveyard: Create a 1/1 white Spirit creature token with flying. Activate only as a sorcery. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Deathcap Cultivator | handled | Delirium — This creature has deathtouch as long as there are four or more card types among cards in your graveyard. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Deny Existence | handled | Counter target creature spell. If that spell is countered this way, exile it instead of putting it into its owner's graveyard. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Descend upon the Sinful | handled | Exile all creatures. Delirium — Create a 4/4 white Angel creature token with flying if there are four or more card types among cards in your graveyard. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Devils' Playground | handled | Create four 1/1 red Devil creature tokens. They have "When this token dies, it deals 1 damage to any target." | the engine reads this text and performs it | Y/Y/- | not_tested |
| Devilthorn Fox | handled |  |  | Y/Y/- | not_tested |
| Dissension in the Ranks | handled | Target blocking creature fights another target blocking creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Drogskol Cavalry | handled | Whenever another Spirit you control enters, you gain 2 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Drownyard Explorers | handled | When this creature enters, investigate. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Drownyard Temple | handled | {3}: Return this card from your graveyard to the battlefield tapped. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Drunau Corpse Trawler | handled | When this creature enters, create a 2/2 black Zombie creature token. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Elusive Tormentor // Insidious Mist | handled | {1}, Discard a card: Transform this creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Ember-Eye Wolf | handled | {1}{R}: This creature gets +2/+0 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Emissary of the Sleepless | handled | When this creature enters, if a creature died this turn, create a 1/1 white Spirit creature token with flying. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Epitaph Golem | handled | {2}: Put target card from your graveyard on the bottom of your library. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Equestrian Skill | handled | Enchanted creature gets +3/+3. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Ethereal Guidance | handled | Creatures you control get +2/+1 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Explosive Apparatus | handled | {3}, {T}, Sacrifice this artifact: It deals 2 damage to any target. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Expose Evil | handled | Tap up to two target creatures. Investigate. (Create a Clue token. It's an artifact with "{2}, Sacrifice this token: Draw a card.") | the engine reads this text and performs it | Y/Y/- | not_tested |
| Farbog Revenant | handled | Lifelink | machines/combat.py | Y/Y/- | not_tested |
| Fleeting Memories | handled | When this enchantment enters, investigate. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Foreboding Ruins | handled | As this land enters, you may reveal a Swamp or Mountain card from your hand. If you don't, this land enters tapped. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Forgotten Creation | handled | At the beginning of your upkeep, you may discard all the cards in your hand. If you do, draw that many cards. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Forsaken Sanctuary | handled | This land enters tapped. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Fortified Village | handled | As this land enters, you may reveal a Forest or Plains card from your hand. If you don't, this land enters tapped. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Foul Orchard | handled | This land enters tapped. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Furtive Homunculus | handled | Skulk | machines/keywords.py | Y/Y/- | not_tested |
| Game Trail | handled | As this land enters, you may reveal a Mountain or Forest card from your hand. If you don't, this land enters tapped. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Gatstaf Arsonists // Gatstaf Ravagers | handled | At the beginning of each upkeep, if no spells were cast last turn, transform this creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Geistblast | handled | Geistblast deals 2 damage to any target. {2}{U}, Exile this card from your graveyard: Copy target instant or sorcery spell you control. You may choose new targe | the engine reads this text and performs it | Y/Y/- | not_tested |
| Ghoulcaller's Accomplice | handled | {3}{B}, Exile this card from your graveyard: Create a 2/2 black Zombie creature token. Activate only as a sorcery. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Ghoulsteed | handled | {2}{B}, Discard two cards: Return this card from your graveyard to the battlefield tapped. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Gibbering Fiend | handled | When this creature enters, it deals 1 damage to each opponent. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Gisa's Bidding | handled | Create two 2/2 black Zombie creature tokens. Madness {2}{B} (If you discard this card, discard it into exile. When you do, cast it for its madness cost or put i | the engine reads this text and performs it | Y/Y/- | not_tested |
| Gone Missing | handled | Put target permanent on top of its owner's library. Investigate. (Create a Clue token. It's an artifact with "{2}, Sacrifice this token: Draw a card.") | the engine reads this text and performs it | Y/Y/- | not_tested |
| Graf Mole | handled | Whenever you sacrifice a Clue, you gain 3 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Grotesque Mutation | handled | Target creature gets +3/+1 and gains lifelink until end of turn. (Damage dealt by the creature also causes its controller to gain that much life.) | the engine reads this text and performs it | Y/Y/- | not_tested |
| Hanweir Militia Captain // Westvale Cult Leader | handled | At the beginning of your upkeep, if you control four or more creatures, transform this creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Harvest Hand // Scrounged Scythe | handled | When this creature dies, return it to the battlefield transformed under your control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Haunted Cloak | handled | Equipped creature has vigilance, trample, and haste. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Heir of Falkenrath // Heir to the Night | handled | Discard a card: Transform this creature. Activate only once each turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Hermit of the Natterknolls // Lone Wolf of the Natterknolls | handled | Whenever an opponent casts a spell during your turn, draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Highland Lake | handled | This land enters tapped. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Hinterland Logger // Timber Shredder | handled | At the beginning of each upkeep, if no spells were cast last turn, transform this creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Hope Against Hope | handled | Enchanted creature gets +1/+1 for each creature you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Hound of the Farbogs | handled | Delirium — This creature has menace as long as there are four or more card types among cards in your graveyard. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Howlpack Resurgence | handled | Each creature you control that's a Wolf or a Werewolf gets +1/+1 and has trample. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Howlpack Wolf | handled | This creature can't block unless you control another Wolf or Werewolf. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Hulking Devil | handled |  |  | Y/Y/- | not_tested |
| Humble the Brute | handled | Destroy target creature with power 4 or greater. Investigate.(Create a Clue token. It's an artifact with "{2}, Sacrifice this token: Draw a card.") | the engine reads this text and performs it | Y/Y/- | not_tested |
| Incorrigible Youths | handled | Madness | machines/casting.py | Y/Y/- | not_tested |
| Indulgent Aristocrat | handled | {2}, Sacrifice a creature: Put a +1/+1 counter on each Vampire you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Inexorable Blob | handled | Delirium — Whenever this creature attacks, if there are four or more card types among cards in your graveyard, create a 3/3 green Ooze creature token that's tap | the engine reads this text and performs it | Y/Y/- | not_tested |
| Inner Struggle | handled | Target creature deals damage to itself equal to its power. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Inquisitor's Ox | handled | Delirium — This creature gets +1/+0 and has vigilance as long as there are four or more card types among cards in your graveyard. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Insolent Neonate | handled | Discard a card, Sacrifice this creature: Draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Inspiring Captain | handled | When this creature enters, creatures you control get +1/+1 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Intrepid Provisioner | handled | When this creature enters, another target Human you control gets +2/+2 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Invocation of Saint Traft | handled | Enchanted creature has "Whenever this creature attacks, create a 4/4 white Angel creature token with flying that's tapped and attacking. Exile that token at end | the engine reads this text and performs it | Y/Y/- | not_tested |
| Jace's Scrutiny | handled | Target creature gets -4/-0 until end of turn. Investigate. (Create a Clue token. It's an artifact with "{2}, Sacrifice this token: Draw a card.") | the engine reads this text and performs it | Y/Y/- | not_tested |
| Jace, Unraveler of Secrets | handled | +1: Scry 1, then draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Just the Wind | handled | Return target creature to its owner's hand. Madness {U} (If you discard this card, discard it into exile. When you do, cast it for its madness cost or put it in | the engine reads this text and performs it | Y/Y/- | not_tested |
| Kessig Dire Swine | handled | Delirium — This creature has trample as long as there are four or more card types among cards in your graveyard. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Kessig Forgemaster // Flameheart Werewolf | handled | Whenever this creature blocks or becomes blocked by a creature, this creature deals 1 damage to that creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Kindly Stranger // Demon-Possessed Witch | handled | Delirium — {2}{B}: Transform this creature. Activate only if there are four or more card types among cards in your graveyard. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Lamplighter of Selhoff | handled | When this creature enters, if you control another Zombie, you may draw a card. If you do, discard a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Loam Dryad | handled |  |  | Y/Y/- | not_tested |
| Magnifying Glass | handled | {4}, {T}: Investigate. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Manic Scribe | handled | When this creature enters, each opponent mills three cards. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Markov Dreadknight | handled | {2}{B}, Discard a card: Put two +1/+1 counters on this creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Merciless Resolve | handled | As an additional cost to cast this spell, sacrifice a creature or land. Draw two cards. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Might Beyond Reason | handled | Put two +1/+1 counters on target creature. Delirium — Put three +1/+1 counters on that creature instead if there are four or more card types among cards in your | the engine reads this text and performs it | Y/Y/- | not_tested |
| Militant Inquisitor | handled | This creature gets +1/+0 for each Equipment you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Moldgraf Scavenger | handled | Delirium — This creature gets +3/+0 as long as there are four or more card types among cards in your graveyard. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Moorland Drifter | handled | Delirium — This creature has flying as long as there are four or more card types among cards in your graveyard. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Morkrut Necropod | handled | Whenever this creature attacks or blocks, sacrifice another creature or land. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Murderer's Axe | handled | Equipped creature gets +2/+2. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Murderous Compulsion | handled | Destroy target tapped creature. Madness {1}{B} (If you discard this card, discard it into exile. When you do, cast it for its madness cost or put it into your g | the engine reads this text and performs it | Y/Y/- | not_tested |
| Nagging Thoughts | handled | Look at the top two cards of your library. Put one of them into your hand and the other into your graveyard. Madness {1}{U} (If you discard this card, discard i | the engine reads this text and performs it | Y/Y/- | not_tested |
| Nahiri's Machinations | handled | At the beginning of combat on your turn, target creature you control gains indestructible until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Nearheath Chaplain | handled | {2}{W}, Exile this card from your graveyard: Create two 1/1 white Spirit creature tokens with flying. Activate only as a sorcery. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Nephalia Moondrakes | handled | When this creature enters, target creature gains flying until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Niblis of Dusk | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Obsessive Skinner | handled | When this creature enters, put a +1/+1 counter on target creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Olivia's Bloodsworn | handled | This creature can't block. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Ongoing Investigation | handled | Whenever one or more creatures you control deal combat damage to a player, investigate. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Open the Armory | handled | Search your library for an Aura or Equipment card, reveal it, put it into your hand, then shuffle. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Pack Guardian | handled | When this creature enters, you may discard a land card. If you do, create a 2/2 green Wolf creature token. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Pale Rider of Trostad | handled | When this creature enters, discard a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Paranoid Parish-Blade | handled | Delirium — This creature gets +1/+0 and has first strike as long as there are four or more card types among cards in your graveyard. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Pieces of the Puzzle | handled | Reveal the top five cards of your library. Put up to two instant and/or sorcery cards from among them into your hand and the rest into your graveyard. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Pious Evangel // Wayward Disciple | handled | Whenever this creature or another creature you control enters, you gain 1 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Press for Answers | handled | Tap target creature. It doesn't untap during its controller's next untap step. Investigate. (Create a Clue token. It's an artifact with "{2}, Sacrifice this tok | the engine reads this text and performs it | Y/Y/- | not_tested |
| Pyre Hound | handled | Whenever you cast an instant or sorcery spell, put a +1/+1 counter on this creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Quilled Wolf | handled | {5}{G}: This creature gets +4/+4 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Rancid Rats | handled | Skulk | machines/keywords.py | Y/Y/- | not_tested |
| Ravenous Bloodseeker | handled | Discard a card: This creature gets +2/-2 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Reaper of Flight Moonsilver | handled | Delirium — Sacrifice another creature: This creature gets +2/+1 until end of turn. Activate only if there are four or more card types among cards in your gravey | the engine reads this text and performs it | Y/Y/- | not_tested |
| Reduce to Ashes | handled | Reduce to Ashes deals 5 damage to target creature. If that creature would die this turn, exile it instead. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Relentless Dead | handled | When this creature dies, you may pay {B}. If you do, return it to its owner's hand. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Rise from the Tides | handled | Create a tapped 2/2 black Zombie creature token for each instant and sorcery card in your graveyard. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Root Out | handled | Destroy target artifact or enchantment. Investigate. (Create a Clue token. It's an artifact with "{2}, Sacrifice this token: Draw a card.") | the engine reads this text and performs it | Y/Y/- | not_tested |
| Rottenheart Ghoul | handled | When this creature dies, target player discards a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Runaway Carriage | handled | When this creature attacks or blocks, sacrifice it at end of combat. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Rush of Adrenaline | handled | Target creature gets +2/+1 and gains trample until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sanguinary Mage | handled | Prowess | machines/keywords.py | Y/Y/- | not_tested |
| Sanitarium Skeleton | handled | {2}{B}: Return this card from your graveyard to your hand. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Scourge Wolf | handled | Delirium — This creature has double strike as long as there are four or more card types among cards in your graveyard. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Seagraf Skaab | handled |  |  | Y/Y/- | not_tested |
| Senseless Rage | handled | Enchanted creature gets +2/+2. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Shamble Back | handled | Exile target creature card from a graveyard. Create a 2/2 black Zombie creature token. You gain 2 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Shard of Broken Glass | handled | Equipped creature gets +1/+0. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Silent Observer | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Silverfur Partisan | handled | Whenever a Wolf or Werewolf you control becomes the target of an instant or sorcery spell, create a 2/2 green Wolf creature token. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Silverstrike | handled | Destroy target attacking creature. You gain 3 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sinister Concoction | handled | {B}, Pay 1 life, Mill a card, Discard a card, Sacrifice this enchantment: Destroy target creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Skeleton Key | handled | Equipped creature has skulk. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sleep Paralysis | handled | When this Aura enters, tap enchanted creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Solitary Hunter // One of the Pack | handled | At the beginning of each upkeep, if no spells were cast last turn, transform this creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Soul Swallower | handled | Delirium — At the beginning of your upkeep, if there are four or more card types among cards in your graveyard, put three +1/+1 counters on this creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Spectral Shepherd | handled | {1}{U}: Return target Spirit you control to its owner's hand. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Spiteful Motives | handled | Enchanted creature gets +3/+0 and has first strike. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Stallion of Ashmouth | handled | Delirium — {1}{B}: This creature gets +1/+1 until end of turn. Activate only if there are four or more card types among cards in your graveyard. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Stensia Masquerade | handled | Attacking creatures you control have first strike. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Stern Constable | handled | {T}, Discard a card: Tap target creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Stitched Mangler | handled | This creature enters tapped. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Stitchwing Skaab | handled | {1}{U}, Discard two cards: Return this card from your graveyard to the battlefield tapped. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Stoic Builder | handled | When this creature enters, you may return target land card from your graveyard to your hand. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Stone Quarry | handled | This land enters tapped. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Stormrider Spirit | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Strength of Arms | handled | Target creature gets +2/+2 until end of turn. If you control an Equipment, create a 1/1 white Human Soldier creature token. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Stromkirk Mentor | handled | When this creature enters, put a +1/+1 counter on another target Vampire you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Structural Distortion | handled | Exile target artifact or land. Structural Distortion deals 2 damage to that permanent's controller. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Survive the Night | handled | Target creature gets +1/+0 and gains indestructible until end of turn. (Damage and effects that say "destroy" don't destroy it.) Investigate. (Create a Clue tok | the engine reads this text and performs it | Y/Y/- | not_tested |
| Tamiyo's Journal | handled | At the beginning of your upkeep, investigate. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Thalia's Lieutenant | handled | When this creature enters, put a +1/+1 counter on each other Human you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Thornhide Wolves | handled |  |  | Y/Y/- | not_tested |
| Thraben Gargoyle // Stonewing Antagonizer | handled | {6}: Transform this creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Tireless Tracker | handled | Landfall — Whenever a land you control enters, investigate. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Town Gossipmonger // Incited Rabble | handled | {T}, Tap an untapped creature you control: Transform this creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Trail of Evidence | handled | Whenever you cast an instant or sorcery spell, investigate. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Traverse the Ulvenwald | handled | Search your library for a basic land card, reveal it, put it into your hand, then shuffle. Delirium — If there are four or more card types among cards in your g | the engine reads this text and performs it | Y/Y/- | not_tested |
| Twins of Maurer Estate | handled | Madness | machines/casting.py | Y/Y/- | not_tested |
| Ulrich's Kindred | handled | {3}{G}: Target attacking Wolf or Werewolf gains indestructible until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Ulvenwald Hydra | handled | Ulvenwald Hydra's power and toughness are each equal to the number of lands you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Ulvenwald Mysteries | handled | Whenever a nontoken creature you control dies, investigate. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Uncaged Fury | handled | Target creature gets +1/+1 and gains double strike until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Uninvited Geist // Unimpeded Trespasser | handled | When this creature deals combat damage to a player, transform it. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Vampire Noble | handled |  |  | Y/Y/- | not_tested |
| Vessel of Ephemera | handled | {2}{W}, Sacrifice this enchantment: Create two 1/1 white Spirit creature tokens with flying. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Vessel of Malignity | handled | {1}{B}, Sacrifice this enchantment: Target opponent exiles two cards from their hand. Activate only as a sorcery. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Vessel of Paramnesia | handled | {U}, Sacrifice this enchantment: Target player mills three cards. Draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Vessel of Volatility | handled |  |  | Y/Y/- | not_tested |
| Veteran Cathar | handled | {3}{W}: Target Human gains double strike until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Village Messenger // Moonrise Intruder | handled | At the beginning of each upkeep, if no spells were cast last turn, transform this creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Voldaren Duelist | handled | When this creature enters, target creature can't block this turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Warped Landscape | handled | {2}, {T}, Sacrifice this land: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Weirding Wood | handled | When this Aura enters, investigate. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Westvale Abbey // Ormendahl, Profane Prince | handled | {5}, {T}, Pay 1 life: Create a 1/1 white and black Human Cleric creature token. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Wicker Witch | handled |  |  | Y/Y/- | not_tested |
| Wild-Field Scarecrow | handled | {2}, Sacrifice this creature: Search your library for up to two basic land cards, reveal them, put them into your hand, then shuffle. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Woodland Stream | handled | This land enters tapped. | the engine reads this text and performs it | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>43 cards</summary>

- Accursed Witch // Infectious Curse
- Always Watching
- Archangel Avacyn // Avacyn, the Purifier
- Avacynian Missionaries // Lunarch Inquisitors
- Behold the Beyond
- Bound by Moonsilver
- Brain in a Jar
- Briarbridge Patrol
- Burn from Within
- Clip Wings
- Cryptolith Rite
- Declaration in Stone
- Diregraf Colossus
- Dual Shot
- Duskwatch Recruiter // Krallenhorde Howler
- Engulf the Shore
- Falkenrath Gorger
- Fevered Visions
- Geralf's Masterpiece
- Goldnight Castigator
- Gryff's Boon
- Lambholt Pacifist // Lambholt Butcher
- Liliana's Indignation
- Moonlight Hunt
- Nahiri, the Harbinger
- Odric, Lunarch Marshal
- Port Town
- Prized Amalgam
- Rabid Bite
- Rattlechains
- Sigarda, Heron's Grace
- Silburlind Snapper
- Sin Prodder
- Skin Invasion // Skin Shedder
- Slayer's Plate
- Sorin, Grim Nemesis
- Tenacity
- Thing in the Ice // Awoken Horror
- Thraben Inspector
- To the Slaughter
- True-Faith Censer
- Watcher in the Web
- Wolf of Devil's Breach

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| at the beginning of your upkeep, choose one — • each player with exactly N life loses the game, then each player gains N life. • each player with exactly N life | 1 | Triskaidekaphobia | soi |
| at the beginning of your upkeep, each player discards a card. each opponent who discarded a card that shares a card type with the card you discarded loses N lif | 1 | Creeping Dread | soi |
| at the beginning of your upkeep, sacrifice ~ unless you sacrifice a land. | 1 | The Gitrog Monster | soi |
| attacking creatures you control get +N/+N and have trample. | 1 | Breakneck Rider // Neck Breaker | soi |
| counter target sorcery spell. delirium — if there are four or more card types among cards in your graveyard, search the graveyard, hand, and library of that spe | 1 | Invasive Surgery | soi |
| exile target creature you control, then return that card to the battlefield under its owner"..."s a spirit, put a +N/+N counter on it. | 1 | Essence Flux | soi |
| for each token you control, create a token that's a copy of that permanent. | 1 | Second Harvest | soi |
| gain control of target creature until end of turn. untap that creature. it gets +N/+N and gains haste until end of turn. madness {M}{M} (if you discard ~, disca | 1 | Malevolent Whispers | soi |
| madness {M}{M} (if you discard ~, discard it into exile. when you do, cast it for its madness cost or put it into your graveyard.) ~ deals N damage divided as y | 1 | Avacyn's Judgment | soi |
| madness {M}{M}{M} (if you discard ~, discard it into exile. when you do, cast it for its madness cost or put it into your graveyard.) create three tapped N/N bl | 1 | From Under the Floorboards | soi |
| madness {M}{M}{M} (if you discard ~, discard it into exile. when you do, cast it for its madness cost or put it into your graveyard.) gain control of target cre | 1 | Welcome to the Fold | soi |
| put target card from a graveyard on your choice of the top or bottom of its owner's library. create a N/N white spirit creature token with flying. | 1 | Not Forgotten | soi |
| return any number of cards with different mana values from your graveyard to your hand. put ~ on the bottom of its owner's library. | 1 | Seasons Past | soi |
| return up to two target creature cards from your graveyard to the battlefield. each of those creatures is a black zombie in addition to its other colors and typ | 1 | Ever After | soi |
| reveal the top N plus one cards of your library and separate them into two piles. an opponent chooses one of those piles. put that pile into your hand and the o | 1 | Epiphany at the Drownyard | soi |
| search your library for up to two basic land cards and reveal them. put one into your hand and the other into your graveyard. then shuffle. | 1 | Fork in the Road | soi |
| target opponent reveals their hand. you choose a nonland card from it and exile that card. delirium — if there are four or more card types among cards in your g | 1 | Pick the Brain | soi |
| werewolf of ancient hunger"..." hands. | 1 | Sage of Ancient Lore // Werewolf of Ancient Hunger | soi |
| when equipped creature transforms, transform ~. | 1 | Neglected Heirloom // Ashmouth Blade | soi |
| whenever a permanent you control transforms into a non-human creature, create a N/N green wolf creature token. | 1 | Cult of the Waxing Moon | soi |
| whenever a source an opponent controls deals damage to you or a permanent you control, you may have ~ deal N damage to that source's controller. | 1 | Flameblade Angel | soi |
| whenever a werewolf you control enters, you may transform it. | 1 | Geier Reach Bandit // Vildin-Pack Alpha | soi |
| whenever another creature you control enters, you may discard a card. if you do, put a +N/+N counter on that creature, it gains haste until end of turn, and it  | 1 | Olivia, Mobilized for War | soi |
| whenever you cast an instant or sorcery spell from your hand, you may cast target card with the same name as that spell from your graveyard. | 1 | Harness the Storm | soi |
| whenever you investigate for the first time each turn, investigate an additional time. | 1 | Erdwal Illuminator | soi |
| you may have ~ enter as a copy of any creature on the battlefield, except it enters with N additional +N/+N counters on it. | 1 | Altered Ego | soi |
| {M}: choose a color of a card in your graveyard. add one mana of that color. | 1 | Corrupted Grafstone | soi |
| {M}{M}, sacrifice ~: reveal the top four cards of your library. you may put an artifact, creature, enchantment, land, or planeswalker card from among them into  | 1 | Vessel of Nascency | soi |
| {M}{M}{M}: put ~ from your graveyard onto the battlefield transformed. activate only as a sorcery. | 1 | Startled Awake // Persistent Nightmare | soi |

## Notes


