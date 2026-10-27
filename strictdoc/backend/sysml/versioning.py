"""
Item versions and version-pinned traces in SysML files.

An item is a requirement or a design element. Its version is a metadata
usage, the first member of its body:

    requirement <'SYS-1'> 'Child' {
        @StrictDocVersioning::ItemVersion { version = 3; contentHash = "..."; }
        ...
    }

A trace records the version of its target in its own body:

    dependency from 'SYS-1' to 'STK-1' {
        @StrictDocVersioning::TracedVersion { version = 2; }
    }

The same works for `satisfy` and `verify`. The `metadata def`s live in the
library package StrictDocVersioning (see LIBRARY_TEXT). The qualified names
resolve without an import, so the files keep their import statements.

contentHash is computed from the text of the item without any versioning
metadata (see content_hash()). StrictDoc compares it with the stored hash to
find items that changed without a version bump.
"""

import hashlib
import os
import re
from dataclasses import dataclass
from typing import List, Optional

from strictdoc.backend.sysml.model import (
    SysMLDependency,
    SysMLElement,
    SysMLMember,
    SysMLMetadataUsage,
    SysMLPackage,
    SysMLSatisfy,
    SysMLSpan,
    SysMLVerify,
)
from strictdoc.helpers.exception import StrictDocException

LIBRARY_PACKAGE = "StrictDocVersioning"
LIBRARY_FILE_NAME = f"{LIBRARY_PACKAGE}.sysml"
ITEM_VERSION_NAME = "ItemVersion"
TRACED_VERSION_NAME = "TracedVersion"
ITEM_VERSION_METADATA = f"{LIBRARY_PACKAGE}::{ITEM_VERSION_NAME}"
TRACED_VERSION_METADATA = f"{LIBRARY_PACKAGE}::{TRACED_VERSION_NAME}"
ITEM_VERSION_FIELD = "ITEM_VERSION"

LIBRARY_TEXT = f"""\
package {LIBRARY_PACKAGE} {{
    doc /*
     * Metadata that StrictDoc uses for item versions and for traces that
     * record the version of their target. StrictDoc writes this file.
     */

    private import ScalarValues::*;

    metadata def {ITEM_VERSION_NAME} {{
        attribute version : Natural;
        attribute contentHash : String;
    }}

    metadata def {TRACED_VERSION_NAME} {{
        attribute version : Natural;
    }}
}}
"""

_HASH_LENGTH = 16
_EMPTY_BODY_PATTERN = re.compile(r"\s*\{\s*\}")


class SysMLVersioningError(StrictDocException):
    """Versioning metadata with a missing or invalid value."""


@dataclass
class ItemVersion:
    version: int
    content_hash: Optional[str]


def is_item_version(member: SysMLMember) -> bool:
    return isinstance(member, SysMLMetadataUsage) and member.name in (
        ITEM_VERSION_METADATA,
        ITEM_VERSION_NAME,
    )


def is_traced_version(member: SysMLMember) -> bool:
    return isinstance(member, SysMLMetadataUsage) and member.name in (
        TRACED_VERSION_METADATA,
        TRACED_VERSION_NAME,
    )


def is_versioning_metadata(member: SysMLMember) -> bool:
    return is_item_version(member) or is_traced_version(member)


def find_item_version(
    members: List[SysMLMember],
) -> Optional[SysMLMetadataUsage]:
    for member_ in members:
        if is_item_version(member_):
            assert isinstance(member_, SysMLMetadataUsage)
            return member_
    return None


def find_traced_version(
    members: List[SysMLMember],
) -> Optional[SysMLMetadataUsage]:
    for member_ in members:
        if is_traced_version(member_):
            assert isinstance(member_, SysMLMetadataUsage)
            return member_
    return None


def read_item_version(members: List[SysMLMember]) -> Optional[ItemVersion]:
    """Return the item version in members, or None. Raises on bad values."""
    usage = find_item_version(members)
    if usage is None:
        return None
    content_hash = usage.values.get("contentHash")
    if content_hash is not None:
        content_hash = content_hash.strip('"')
        if len(content_hash) == 0:
            content_hash = None
    return ItemVersion(version=_version_value(usage), content_hash=content_hash)


def read_traced_version(members: List[SysMLMember]) -> Optional[int]:
    """Return the version that a trace records, or None."""
    usage = find_traced_version(members)
    if usage is None:
        return None
    return _version_value(usage)


def item_version_text(item_version: ItemVersion) -> str:
    text = f"@{ITEM_VERSION_METADATA} {{ version = {item_version.version};"
    if item_version.content_hash is not None:
        text += f' contentHash = "{item_version.content_hash}";'
    return text + " }"


def traced_version_text(version: int) -> str:
    return f"@{TRACED_VERSION_METADATA} {{ version = {version}; }}"


def content_hash(text: str) -> str:
    """
    Hash the text of an item, ignoring layout.

    Runs of whitespace count as one space, and an empty body `{ }` counts as
    `;`. Remove the versioning metadata from the text before hashing it, so
    that a new version or a new trace pin does not change the hash.
    """
    normalized = " ".join(text.split())
    normalized = _EMPTY_BODY_PATTERN.sub(";", normalized)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return digest[:_HASH_LENGTH]


def element_hash(
    file_data: bytes, element: SysMLElement, span: SysMLSpan
) -> str:
    """
    Hash a design element: its source text, given by span, without any
    versioning metadata, including that of nested elements and traces.
    """
    removed = sorted(
        (span_.byte_start, span_.byte_end)
        for span_ in versioning_metadata_spans(element.members)
    )
    parts: List[bytes] = []
    position = span.byte_start
    for start_, end_ in removed:
        parts.append(file_data[position:start_])
        position = end_
    parts.append(file_data[position : span.byte_end])
    return content_hash(b"".join(parts).decode("utf-8"))


def versioning_metadata_spans(members: List[SysMLMember]) -> List[SysMLSpan]:
    """The spans of all versioning metadata in members, recursively."""
    spans: List[SysMLSpan] = []
    for member_ in members:
        if is_versioning_metadata(member_):
            spans.append(member_.span)
        elif isinstance(
            member_,
            (
                SysMLElement,
                SysMLPackage,
                SysMLDependency,
                SysMLSatisfy,
                SysMLVerify,
            ),
        ):
            spans.extend(versioning_metadata_spans(member_.members))
    return spans


def ensure_library(directory: str) -> Optional[str]:
    """
    Write the library file to directory unless it exists there.

    Returns the path of the file when it was written, or None.
    """
    path = os.path.join(directory, LIBRARY_FILE_NAME)
    if os.path.isfile(path):
        return None
    with open(path, "w", encoding="utf8") as file_:
        file_.write(LIBRARY_TEXT)
    return path


def _version_value(usage: SysMLMetadataUsage) -> int:
    raw_version = usage.values.get("version")
    if raw_version is None or not raw_version.isdigit():
        raise SysMLVersioningError(
            f"Invalid @{usage.name} at line {usage.span.line_start}: "
            "'version' must be a whole number, for example 'version = 1;'."
        )
    return int(raw_version)
