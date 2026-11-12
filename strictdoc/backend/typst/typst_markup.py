"""
Helpers for writing Typst source text.
"""

import re

# Characters that start Typst markup syntax. A backslash before any of them
# makes Typst print the character itself. The slash is included because two
# slashes start a comment, and the hyphen because "--" and "---" become
# dashes and "- " at the start of a line becomes a list item.
_MARKUP_SPECIAL_CHARACTERS = set("\\#*_`$<>@[]~/=-+")

# "1." at the start of a line starts a numbered list in Typst markup.
_ENUMERATION_MARKER_REGEX = re.compile(r"(^|\n)(\s*\d+)\.")


def escape_markup(text: str) -> str:
    """Escape plain text so that Typst markup prints it as is."""
    escaped = "".join(
        "\\" + char_ if char_ in _MARKUP_SPECIAL_CHARACTERS else char_
        for char_ in text
    )
    return _ENUMERATION_MARKER_REGEX.sub(r"\1\2\\.", escaped)


def string_literal(text: str) -> str:
    """Write text as a Typst string literal, quotes included."""
    escaped = (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def label_for(uid: str) -> str:
    """A label for a node or anchor UID, in a form that accepts any UID."""
    return f"label({string_literal(uid)})"
