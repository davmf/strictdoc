"""
Item versions and traced versions on StrictDoc objects read from SysML.

The reader stores the item version, the computed content hash and the
traced versions on the nodes and relations (see node_data.py). This module
uses them:

- update_requirement_versions() runs before StrictDoc writes a
  requirements package. It gives each requirement a version, bumps the
  version of each changed requirement and pins each new relation to the
  current version of its target.
- report_issues() runs after the traceability index is built. It reports
  items that changed without a version bump and suspect traces.
- suspect_traces() lists the traces of a node whose target has moved on.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Iterator, List, Optional, Union

from strictdoc.backend.sdoc.models.document import SDocDocument
from strictdoc.backend.sdoc.models.node import SDocNode, SDocNodeField
from strictdoc.backend.sdoc.models.reference import ParentReqReference
from strictdoc.backend.sysml import node_data
from strictdoc.backend.sysml.versioning import (
    ITEM_VERSION_FIELD,
    LIBRARY_PACKAGE,
    ItemVersion,
)
from strictdoc.backend.sysml.writer import SysMLWriter
from strictdoc.helpers.exception import StrictDocException

if TYPE_CHECKING:
    from strictdoc.core.traceability_index import TraceabilityIndex

TargetVersionLookup = Callable[[str], Optional[int]]


@dataclass
class SuspectTrace:
    reference: ParentReqReference
    traced_version: int
    current_version: Optional[int]


def iterate_nodes(
    container: Union[SDocDocument, SDocNode],
) -> Iterator[SDocNode]:
    for node_ in container.section_contents:
        if isinstance(node_, SDocNode):
            yield node_
            yield from iterate_nodes(node_)


def is_sysml_document(document: SDocDocument) -> bool:
    return document.meta is not None and (
        document.meta.input_doc_full_path.endswith(".sysml")
    )


def item_version_of(node: SDocNode) -> Optional[int]:
    item_version = node_data.get_item_version(node)
    return item_version.version if item_version is not None else None


def index_target_version_lookup(
    traceability_index: Optional["TraceabilityIndex"],
    document: Optional[SDocDocument] = None,
) -> TargetVersionLookup:
    """
    Return a function that gives the current version of the node with a
    UID. Nodes of document are found without the index, so that versions
    bumped in the same save are seen.
    """

    def lookup(uid: str) -> Optional[int]:
        if document is not None:
            for node_ in iterate_nodes(document):
                if node_.reserved_uid == uid:
                    return item_version_of(node_)
        if traceability_index is None or len(uid) == 0:
            return None
        node = traceability_index.get_node_by_uid_weak2(uid)
        if not isinstance(node, SDocNode):
            return None
        return item_version_of(node)

    return lookup


def update_requirement_versions(
    document: SDocDocument, target_version: TargetVersionLookup
) -> None:
    """
    Version every requirement of a requirements package before it is
    written.

    - A requirement without a version gets version 1.
    - A requirement whose content hash changed gets the next version, unless
      the user changed the ITEM_VERSION field, which then wins.
    - A Parent relation without a traced version is pinned to the current
      version of its target, if the target has one.
    """
    requirements = [
        node_
        for node_ in iterate_nodes(document)
        if node_.node_type == "REQUIREMENT"
    ]
    for requirement_ in requirements:
        _update_requirement_version(requirement_)
    for requirement_ in requirements:
        for relation_ in requirement_.relations:
            if not isinstance(relation_, ParentReqReference):
                continue
            if node_data.get_traced_version(relation_) is not None:
                continue
            node_data.set_traced_version(
                relation_, target_version(relation_.ref_uid)
            )


def review_traces(
    node: SDocNode, target_version: TargetVersionLookup
) -> List[ParentReqReference]:
    """
    Pin each suspect trace of a node to the current version of its target.

    Returns the relations that changed. The caller writes the document.
    """
    changed: List[ParentReqReference] = []
    for suspect_ in suspect_traces(node, target_version):
        if suspect_.current_version is None:
            continue
        node_data.set_traced_version(
            suspect_.reference, suspect_.current_version
        )
        changed.append(suspect_.reference)
    return changed


def suspect_traces(
    node: SDocNode, target_version: TargetVersionLookup
) -> List[SuspectTrace]:
    """The traces of a node whose traced version is not current."""
    suspects: List[SuspectTrace] = []
    for relation_ in node.relations:
        if not isinstance(relation_, ParentReqReference):
            continue
        traced_version = node_data.get_traced_version(relation_)
        if traced_version is None:
            continue
        current_version = target_version(relation_.ref_uid)
        if current_version != traced_version:
            suspects.append(
                SuspectTrace(
                    reference=relation_,
                    traced_version=traced_version,
                    current_version=current_version,
                )
            )
    return suspects


def report_issues(traceability_index: "TraceabilityIndex") -> None:
    """
    Report versioning issues of all SysML documents as validation issues.

    StrictDoc prints each issue as a warning and shows it on the node.
    """
    target_version = index_target_version_lookup(traceability_index)
    for document_ in traceability_index.document_tree.document_list:
        if not is_sysml_document(document_):
            continue
        for node_ in iterate_nodes(document_):
            for issue_ in _node_issues(node_, target_version):
                traceability_index.validation_index.add_issue(
                    node_,
                    issue_,
                    subject=_issue_subject(document_, node_),
                )


def has_library(traceability_index: Optional["TraceabilityIndex"]) -> bool:
    """True when the project has a SysML package named StrictDocVersioning."""
    if traceability_index is None:
        return False
    return any(
        is_sysml_document(document_)
        and document_.reserved_title == LIBRARY_PACKAGE
        for document_ in traceability_index.document_tree.document_list
    )


def _update_requirement_version(requirement: SDocNode) -> None:
    current_hash = SysMLWriter.requirement_hash(requirement)
    item_version = node_data.get_item_version(requirement)
    field_version = _field_version(requirement)
    if item_version is None:
        version = field_version if field_version is not None else 1
    elif field_version is not None and field_version != item_version.version:
        version = field_version
    elif item_version.content_hash is None:
        version = item_version.version
    elif item_version.content_hash != current_hash:
        version = item_version.version + 1
    else:
        version = item_version.version
    node_data.set_item_version(
        requirement, ItemVersion(version=version, content_hash=current_hash)
    )
    node_data.set_computed_hash(requirement, current_hash)
    _set_version_field(requirement, version)


def _field_version(requirement: SDocNode) -> Optional[int]:
    fields = requirement.ordered_fields_lookup.get(ITEM_VERSION_FIELD)
    if fields is None or len(fields) == 0:
        return None
    text = fields[0].get_text_value().strip()
    if len(text) == 0:
        return None
    if not text.isdigit():
        raise StrictDocException(
            f"{ITEM_VERSION_FIELD} must be a whole number, "
            f"for example 1: '{text}'."
        )
    return int(text)


def _set_version_field(requirement: SDocNode, version: int) -> None:
    document = requirement.get_document()
    assert isinstance(document, SDocDocument) and document.grammar is not None
    element = document.grammar.elements_by_type[requirement.node_type]
    if ITEM_VERSION_FIELD not in element.field_titles:
        return
    field = SDocNodeField.create_from_string(
        parent=requirement,
        field_name=ITEM_VERSION_FIELD,
        field_value=str(version),
        multiline=False,
    )
    requirement.set_field_value(
        field_name=ITEM_VERSION_FIELD,
        form_field_index=0,
        value=field,
    )


def _node_issues(
    node: SDocNode, target_version: TargetVersionLookup
) -> List[str]:
    issues: List[str] = []
    item_version = node_data.get_item_version(node)
    computed_hash = node_data.get_computed_hash(node)
    if (
        item_version is not None
        and item_version.content_hash is not None
        and computed_hash is not None
        and item_version.content_hash != computed_hash
    ):
        issues.append(
            f"The content changed after version {item_version.version}, "
            "but the version was not bumped."
        )
    for suspect_ in suspect_traces(node, target_version):
        target_uid = suspect_.reference.ref_uid
        if suspect_.current_version is None:
            issues.append(
                f"Suspect trace to {target_uid}: traced version "
                f"{suspect_.traced_version}, but {target_uid} has no "
                "item version."
            )
        else:
            issues.append(
                f"Suspect trace to {target_uid}: traced version "
                f"{suspect_.traced_version}, current version "
                f"{suspect_.current_version}."
            )
    return issues


def _issue_subject(document: SDocDocument, node: SDocNode) -> str:
    assert document.meta is not None
    uid = node.reserved_uid if node.reserved_uid is not None else "<no UID>"
    path = document.meta.input_doc_rel_path.relative_path_posix
    return f"({uid}, {path}:{node.ng_line_start})"
