"""
SysML-only data that StrictDoc objects carry for the writer.

These values have no StrictDoc field. They are stored as plain attributes on
SDocDocument and SDocNode instances, so they are picklable with the document
and the shared model classes stay unchanged.

- Attribute types: per requirement node, an ordered map from the SysML
  attribute name to its type text (or None). The map also records
  declarations without a value.
- Imports: per document or section, the import statements in file order.
- Derivation prefix: per document, whether dependencies use `#derivation`.
- Source hash: per design document, the SHA-256 of the text it was read
  from. The editor uses it to detect changes on disk.
- Member offset: per design node, the byte offset of its SysML element in
  the file. The editor uses it to find the element again.
"""

import hashlib
import re
from typing import Any, Dict, List, Optional, Union

from strictdoc.backend.sdoc.models.document import SDocDocument
from strictdoc.backend.sdoc.models.node import SDocNode

SysMLContainer = Union[SDocDocument, SDocNode]

_ATTRIBUTE_TYPES_KEY = "ng_sysml_attribute_types"
_IMPORTS_KEY = "ng_sysml_imports"
_DERIVATION_PREFIX_KEY = "ng_sysml_derivation_prefix"
_SOURCE_HASH_KEY = "ng_sysml_source_hash"
_MEMBER_OFFSET_KEY = "ng_sysml_member_offset"


def set_attribute_types(
    node: SDocNode, attribute_types: Dict[str, Optional[str]]
) -> None:
    setattr(node, _ATTRIBUTE_TYPES_KEY, dict(attribute_types))


def get_attribute_types(node: SDocNode) -> Dict[str, Optional[str]]:
    value: Any = getattr(node, _ATTRIBUTE_TYPES_KEY, None)
    if value is None:
        return {}
    return dict(value)


def set_imports(container: SysMLContainer, imports: List[str]) -> None:
    setattr(container, _IMPORTS_KEY, list(imports))


def get_imports(container: SysMLContainer) -> List[str]:
    value: Any = getattr(container, _IMPORTS_KEY, None)
    if value is None:
        return []
    return list(value)


def set_derivation_prefix(document: SDocDocument, is_enabled: bool) -> None:
    setattr(document, _DERIVATION_PREFIX_KEY, is_enabled)


def get_derivation_prefix(document: SDocDocument) -> bool:
    value: Any = getattr(document, _DERIVATION_PREFIX_KEY, False)
    return bool(value)


def source_hash(source_text: str) -> str:
    return hashlib.sha256(source_text.encode("utf-8")).hexdigest()


def set_source_hash(document: SDocDocument, source_text: str) -> None:
    setattr(document, _SOURCE_HASH_KEY, source_hash(source_text))


def get_source_hash(document: SDocDocument) -> Optional[str]:
    value: Any = getattr(document, _SOURCE_HASH_KEY, None)
    return value if isinstance(value, str) else None


def set_member_offset(node: SDocNode, byte_offset: int) -> None:
    setattr(node, _MEMBER_OFFSET_KEY, byte_offset)


def get_member_offset(node: SDocNode) -> Optional[int]:
    value: Any = getattr(node, _MEMBER_OFFSET_KEY, None)
    return value if isinstance(value, int) else None


def is_design_document(document: SDocDocument) -> bool:
    """True for a SysML design package, which the SysML editor can edit."""
    return document.autogen and get_source_hash(document) is not None


def is_design_element_node(node: SDocNode) -> bool:
    """True for a node of a SysML design element, e.g. a part def."""
    if get_member_offset(node) is None:
        return False
    document = node.get_document()
    return isinstance(document, SDocDocument) and is_design_document(document)


def attribute_field_title(attribute_name: str) -> str:
    """
    Map a SysML attribute name to its StrictDoc field title.

    Example: requiredSamplesPerShift -> REQUIRED_SAMPLES_PER_SHIFT.
    """
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", attribute_name).upper()


def attribute_name_from_field_title(field_title: str) -> str:
    """Inverse of attribute_field_title() for camel case names."""
    parts = field_title.lower().split("_")
    if len(parts) == 0:
        return field_title
    return parts[0] + "".join(part_.capitalize() for part_ in parts[1:])
