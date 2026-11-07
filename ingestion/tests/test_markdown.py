"""Unit tests for the Markdown renderer, run against small inline XML snippets."""

import xml.etree.ElementTree as ET

import pytest

from ingestion.markdown import (
    UnknownMarkup,
    render_block,
    render_inline,
    slugify,
)

AID_XMLNS = 'xmlns:aid="http://ns.adobe.com/AdobeInDesign/4.0/"'


def _parse(xml: str) -> ET.Element:
    return ET.fromstring(f"<root {AID_XMLNS}>{xml}</root>")


def test_emphasis_tags_render_as_markdown() -> None:
    el = _parse("<p>a <em>b</em> <strong>c</strong> <Strong>d</Strong></p>").find("p")
    assert el is not None
    unknown = UnknownMarkup()
    assert render_inline(el, unknown, "test.xml") == "a *b* **c** **d**"
    assert unknown.total == 0


def test_whitespace_star_glyph_and_zero_width_space_are_normalised() -> None:
    el = _parse(
        "<p>roll+Str. ✴On a 10+,\tchoose​ 3</p>",
    ).find("p")
    assert el is not None
    unknown = UnknownMarkup()
    assert render_inline(el, unknown, "test.xml") == "roll+Str. On a 10+, choose 3"


def test_markdown_metacharacters_are_escaped() -> None:
    el = _parse("<p>b[2d6] and ___</p>").find("p")
    assert el is not None
    unknown = UnknownMarkup()
    assert render_inline(el, unknown, "test.xml") == r"b\[2d6\] and \_\_\_"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("- a", r"\- a"),
        ("+2 damage", "+2 damage"),
    ],
)
def test_leading_block_marker_is_escaped(text: str, expected: str) -> None:
    el = _parse(f"<p>{text}</p>").find("p")
    assert el is not None
    unknown = UnknownMarkup()
    assert render_block(el, unknown, "test.xml") == expected


def test_tags_span_is_italic_and_spellname_span_is_plain() -> None:
    el = _parse(
        '<p>a <span aid:cstyle="Tags">b</span> '
        '<span aid:cstyle="SpellName">c</span> <span>d</span></p>'
    ).find("p")
    assert el is not None
    unknown = UnknownMarkup()
    assert render_inline(el, unknown, "test.xml") == "a *b* c d"
    assert unknown.total == 0


@pytest.mark.parametrize("pstyle", ["MonsterName", "SpellName", "MagicItem"])
def test_monster_spell_and_magic_item_paragraphs_render_as_h4(pstyle: str) -> None:
    el = _parse(f'<p aid:pstyle="{pstyle}">Giant Rat</p>').find("p")
    assert el is not None
    unknown = UnknownMarkup()
    assert render_block(el, unknown, "test.xml") == "#### Giant Rat"


@pytest.mark.parametrize(
    "pstyle",
    [
        "Example",
        "ExampleDialogue",
        "ExampleDialogueFirstLine",
        "ExampleDialogueLastLine",
    ],
)
def test_example_paragraphs_render_as_blockquote(pstyle: str) -> None:
    el = _parse(f'<p aid:pstyle="{pstyle}">Roll the dice.</p>').find("p")
    assert el is not None
    unknown = UnknownMarkup()
    assert render_block(el, unknown, "test.xml") == "> Roll the dice."


def test_requirement_paragraph_renders_italic() -> None:
    el = _parse('<p aid:pstyle="Requirement">You must be level 6+.</p>').find("p")
    assert el is not None
    unknown = UnknownMarkup()
    assert render_block(el, unknown, "test.xml") == "*You must be level 6+.*"


def test_lists_render_bulleted_and_numbered() -> None:
    ul = _parse("<ul><li>one</li><li>two</li></ul>").find("ul")
    assert ul is not None
    unknown = UnknownMarkup()
    assert render_block(ul, unknown, "test.xml") == "- one\n- two"

    ol_a = _parse("<ol><li>first</li><li>second</li></ol>").find("ol")
    ol_b = _parse("<ol><li>restarted</li></ol>").find("ol")
    assert ol_a is not None
    assert ol_b is not None
    assert render_block(ol_a, unknown, "test.xml") == "1. first\n2. second"
    assert render_block(ol_b, unknown, "test.xml") == "1. restarted"


def test_stat_table_with_mixed_cell_tags_renders_gfm_table() -> None:
    xml = (
        '<Center><StatTable aid:tcols="2">'
        '<Cell aid:theader=""><TableHeader>Score</TableHeader></Cell>'
        '<TableHeader aid:theader=""><TableHeader>Modifier</TableHeader></TableHeader>'
        "<Cell><TableBody>1–3</TableBody></Cell>"
        "<Cell><TableBody>-3</TableBody></Cell>"
        "<TableBody><TableBody>4–5</TableBody></TableBody>"
        "<Cell><TableBody>-2</TableBody></Cell>"
        "</StatTable></Center>"
    )
    center = _parse(xml).find("Center")
    assert center is not None
    unknown = UnknownMarkup()
    result = render_block(center, unknown, "test.xml")
    lines = result.split("\n")
    assert lines[0] == "| Score | Modifier |"
    assert lines[1] == "| --- | --- |"
    assert lines[2] == "| 1–3 | -3 |"
    assert lines[3] == "| 4–5 | -2 |"
    assert unknown.total == 0


def test_loose_container_text_becomes_paragraph() -> None:
    unknown = UnknownMarkup()
    assert render_block("  Choose one:  \n", unknown, "test.xml") == "Choose one:"


def test_unknown_tag_is_counted_and_its_text_kept() -> None:
    el = _parse("<p>x <Blink>y</Blink></p>").find("p")
    assert el is not None
    unknown = UnknownMarkup()
    assert render_block(el, unknown, "test.xml") == "x y"
    assert unknown.counts == {"tag:Blink": 1}


def test_unknown_attribute_pstyle_and_cstyle_are_counted() -> None:
    el = _parse(
        '<p aid:pstyle="Bogus" foo="x">x <span aid:cstyle="Bogus">y</span></p>'
    ).find("p")
    assert el is not None
    unknown = UnknownMarkup()
    render_block(el, unknown, "test.xml")
    assert unknown.counts == {"attr:foo": 1, "pstyle:Bogus": 1, "cstyle:Bogus": 1}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Hack and Slash", "hack-and-slash"),
        ("What’s Dungeon World Like to Play?", "whats-dungeon-world-like-to-play"),
        ("1. Choose a Class", "1-choose-a-class"),
        ("Magic & Treasure", "magic-and-treasure"),
        ("Viertiö", "viertio"),
    ],
)
def test_slugify(text: str, expected: str) -> None:
    assert slugify(text) == expected
