"""The Mycotyrant's own characteristic-defining ability (CR 604.3a, CR
613.4a): "The Mycotyrant's power and toughness are each equal to the number
of creatures you control that are Fungi and/or Saprolings."

Read generally rather than as a `Boneyard Wurm`-shaped hardcoded row: any
number of subtypes joined by "and/or" (CR 205.3's own inclusive reading - a
creature with both subtypes counts once, not twice), a plain "or", or a
comma list, all count a creature that has *any* of them.
`CountCreaturesWithSubtypesControlledBy` is the live board count;
`_singular_subtype_word` reads "Fungi" as "fungus" - the one Latin-plural
irregularity in the subtype vocabulary that a bare trailing-"s" strip does
not cover (every other subtype, "Saproling" -> "Saprolings", does).

The Mycotyrant is itself a Fungus creature (`type_line`: "Legendary Creature
— Elder Fungus"), so it counts itself - the same self-inclusive reading
Tarmogoyf's own card-type CDA already gives when its source matches its own
condition.
"""

from magic_cards_model.machines import Step

from .harness import Scenario


def test_mycotyrant_counts_itself_and_every_fungus_or_saproling_it_controls():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "The Mycotyrant",
                "Broodrage Mycoid",  # Fungus
                "Shroofus Sproutsire",  # Saproling
                "Grizzly Bears",  # neither
            ],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mycotyrant = scenario.creature("The Mycotyrant", "alice")

    chars = scenario.game.computed_board().of(mycotyrant)
    # The Mycotyrant (Fungus) + Broodrage Mycoid (Fungus) + Shroofus
    # Sproutsire (Saproling) = 3. Grizzly Bears does not count.
    assert chars.power == 3
    assert chars.toughness == 3


def test_mycotyrant_shrinks_as_its_own_fungi_and_saprolings_leave():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["The Mycotyrant", "Broodrage Mycoid"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mycotyrant = scenario.creature("The Mycotyrant", "alice")
    mycoid = scenario.creature("Broodrage Mycoid", "alice")

    before = scenario.game.computed_board().of(mycotyrant)
    assert before.power == 2  # itself + Broodrage Mycoid

    scenario.game.destroy(mycoid)

    after = scenario.game.computed_board().of(mycotyrant)
    assert after.power == 1  # itself alone
