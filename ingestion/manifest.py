"""The chapter manifest: the ordered, hand-written list of source XML files.

The source XML has no reliable chapter title or book order (see docs/source-notes.md),
so the manifest is the single source of truth for both. The ingestion build fails if
the set of files listed here ever disagrees with the ``*.xml`` files actually present
under the source directory.
"""

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class Chapter:
    """One chapter of the source, in book order.

    ``file`` is the path to the chapter's XML file, relative to the source directory
    (``--source``, default ``vendor/dungeon-world/text``), using forward slashes.
    """

    file: str
    id: str
    title: str


CHAPTERS: Final[tuple[Chapter, ...]] = (
    Chapter("Introduction.xml", "introduction", "Introduction"),
    Chapter("Playing_the_Game.xml", "playing-the-game", "Playing the Game"),
    Chapter("Example.xml", "example", "Example of Play"),
    Chapter("Character_Creation.xml", "character-creation", "Character Creation"),
    Chapter("Moves.xml", "moves", "Moves"),
    Chapter("Moves_Discussion.xml", "moves-discussion", "Moves Discussion"),
    Chapter("Bard.xml", "bard", "The Bard"),
    Chapter("Cleric.xml", "cleric", "The Cleric"),
    Chapter("Cleric_Spells.xml", "cleric-spells", "Cleric Spells"),
    Chapter("Druid.xml", "druid", "The Druid"),
    Chapter("Fighter.xml", "fighter", "The Fighter"),
    Chapter("Paladin.xml", "paladin", "The Paladin"),
    Chapter("Ranger.xml", "ranger", "The Ranger"),
    Chapter("Thief.xml", "thief", "The Thief"),
    Chapter("Wizard.xml", "wizard", "The Wizard"),
    Chapter("Wizard_Spells.xml", "wizard-spells", "Wizard Spells"),
    Chapter("Class_Moves_Discussion.xml", "class-moves-discussion", "Moves in Detail"),
    Chapter("Equipment.xml", "equipment", "Equipment"),
    Chapter("GM.xml", "gm", "The GM"),
    Chapter("First_Session.xml", "first-session", "First Session"),
    Chapter("Fronts.xml", "fronts", "Fronts"),
    Chapter("The_World.xml", "the-world", "The World"),
    Chapter("Monsters.xml", "monsters", "Monsters"),
    Chapter("monster_settings/Caverns.xml", "caverns", "Cavern Dwellers"),
    Chapter("monster_settings/Depths.xml", "depths", "Lower Depths"),
    Chapter("monster_settings/Experiments.xml", "experiments", "Twisted Experiments"),
    Chapter("monster_settings/Folk.xml", "folk", "Folk of the Realm"),
    Chapter("monster_settings/Hordes.xml", "hordes", "Ravenous Hordes"),
    Chapter("monster_settings/Planes.xml", "planes", "Planar Powers"),
    Chapter("monster_settings/Swamp.xml", "swamp", "Swamp Denizens"),
    Chapter("monster_settings/Undead.xml", "undead", "Undead Legions"),
    Chapter("monster_settings/Woods.xml", "woods", "Dark Woods"),
    Chapter("Advanced_Delving.xml", "advanced-delving", "Advanced Delving"),
    Chapter("appendices/Teaching.xml", "teaching", "Teaching the Game"),
    Chapter("appendices/Conversion.xml", "conversion", "Adventure Conversion"),
    Chapter("appendices/NPCs.xml", "npcs", "Instant NPCs"),
    Chapter("appendices/Thanks.xml", "thanks", "Thanks"),
)

CLASS_CHAPTER_IDS: Final[tuple[str, ...]] = (
    "bard",
    "cleric",
    "druid",
    "fighter",
    "paladin",
    "ranger",
    "thief",
    "wizard",
)
