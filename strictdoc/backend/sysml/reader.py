"""
Builds SDocDocument objects from SysML v2 files.

A file is a requirements package when its top-level package contains only
nested packages, doc comments, imports, requirement usages, and dependencies
between requirements. Comments and line notes are accepted and dropped. Any
other content makes the file a design package. See the Halcyon conventions
document for the full rule.

Requirements package (editable):

- top-level package -> document, title from the package name
- nested package -> SECTION
- doc comment -> TEXT (the first doc is the section or document free text)
- requirement usage -> REQUIREMENT, with UID (short name), TITLE (name),
  one field per attribute (upper snake case), STATEMENT (first doc), and
  CONSTRAINT (require constraint text)
- dependency from A to B -> Parent relation on A to B

Design package (read only, autogen):

- part, action, calc def, verification and analysis elements -> nodes, with
  fields UID, TITLE, ELEMENT_KIND, STATEMENT and SOURCE
- satisfy X by E -> Parent relation with role "Satisfies" on E to X
- verify X inside an element -> Parent relation with role "Verifies" on the
  element to X

Node MIDs are derived from the file's relative path and the UID or qualified
name, so they stay stable across reloads.
"""

import hashlib
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, Union

from strictdoc.backend.sdoc.constants import SDocMarkup
from strictdoc.backend.sdoc.document_reference import DocumentReference
from strictdoc.backend.sdoc.models.document import SDocDocument
from strictdoc.backend.sdoc.models.document_grammar import DocumentGrammar
from strictdoc.backend.sdoc.models.grammar_element import (
    GrammarElement,
    GrammarElementFieldString,
    GrammarElementFieldType,
    GrammarElementRelationChild,
    GrammarElementRelationParent,
)
from strictdoc.backend.sdoc.models.node import (
    SDocCompositeNode,
    SDocNode,
    SDocNodeField,
)
from strictdoc.backend.sdoc.models.reference import ParentReqReference
from strictdoc.backend.sdoc.pickle_cache import PickleCache
from strictdoc.backend.sysml import node_data
from strictdoc.backend.sysml.model import (
    SysMLAttribute,
    SysMLBlockComment,
    SysMLDependency,
    SysMLDocComment,
    SysMLElement,
    SysMLImport,
    SysMLLineNote,
    SysMLMember,
    SysMLModel,
    SysMLPackage,
    SysMLRequireConstraint,
    SysMLSatisfy,
    SysMLSpan,
    SysMLVerify,
)
from strictdoc.backend.sysml.parser import SysMLParser
from strictdoc.core.project_config import ProjectConfig
from strictdoc.helpers.cast import assert_cast
from strictdoc.helpers.exception import StrictDocException
from strictdoc.helpers.file_system import file_open_read_utf8
from strictdoc.helpers.mid import MID

REQUIREMENT_TAG = "REQUIREMENT"
SECTION_TAG = "SECTION"
TEXT_TAG = "TEXT"
UID_FIELD = "UID"
TITLE_FIELD = "TITLE"
STATEMENT_FIELD = "STATEMENT"
CONSTRAINT_FIELD = "CONSTRAINT"
RESERVED_REQUIREMENT_FIELDS = {
    UID_FIELD,
    TITLE_FIELD,
    STATEMENT_FIELD,
    CONSTRAINT_FIELD,
    "MID",
}
SATISFIES_ROLE = "Satisfies"
SATISFIED_BY_ROLE = "Satisfied by"
VERIFIES_ROLE = "Verifies"
VERIFIED_BY_ROLE = "Verified by"

# (keyword, is_definition) -> node tag for design packages.
DESIGN_TAGS: Dict[Tuple[str, bool], str] = {
    ("part", False): "PART",
    ("part", True): "PART_DEF",
    ("action", False): "ACTION",
    ("action", True): "ACTION_DEF",
    ("calc", True): "CALC_DEF",
    ("verification", False): "VERIFICATION",
    ("verification", True): "VERIFICATION_DEF",
    ("analysis", False): "ANALYSIS",
    ("analysis", True): "ANALYSIS_DEF",
}


class SysMLReader:
    """Reads SysML files into SDocDocument objects, with a pickle cache."""

    @staticmethod
    def read_from_file(
        file_path: str,
        project_config: ProjectConfig,
        relative_path: Optional[str] = None,
    ) -> SDocDocument:
        cached_content = PickleCache.read_from_cache(
            file_path, project_config, "sysml"
        )
        if cached_content is not None:
            return assert_cast(cached_content, SDocDocument)

        with file_open_read_utf8(file_path) as file_:
            content = file_.read()
        document = SysMLReader.read_from_string(
            content,
            file_path=file_path,
            relative_path=(
                relative_path
                if relative_path is not None
                else os.path.basename(file_path)
            ),
        )
        document.build_search_index()
        PickleCache.save_to_cache(document, file_path, project_config, "sysml")
        return document

    @staticmethod
    def read_from_string(
        content: str,
        file_path: Optional[str],
        relative_path: str,
    ) -> SDocDocument:
        model = SysMLParser.parse_string(content, file_path=file_path)
        if is_requirements_model(model):
            return _build_requirements_document(
                model, file_path=file_path, relative_path=relative_path
            )
        return _build_design_document(
            model, file_path=file_path, relative_path=relative_path
        )


def is_requirements_model(model: SysMLModel) -> bool:
    """Return True when the model is a requirements package."""
    packages = [m_ for m_ in model.members if isinstance(m_, SysMLPackage)]
    if len(packages) != 1:
        return False
    for member_ in model.members:
        if not isinstance(
            member_,
            (SysMLPackage, SysMLImport, SysMLLineNote, SysMLBlockComment),
        ):
            return False
    if not _is_representable_package(packages[0]):
        return False
    # Each upper snake case field title must come from one attribute name.
    title_to_name: Dict[str, str] = {}
    for attribute_ in _collect_requirement_attributes(model.members):
        assert attribute_.name is not None
        field_title = node_data.attribute_field_title(attribute_.name)
        known_name = title_to_name.setdefault(field_title, attribute_.name)
        if known_name != attribute_.name:
            return False
    return True


def _stable_mid(*parts: str) -> MID:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return MID(digest[:32])


def _fallback_title(file_path: Optional[str]) -> str:
    if file_path is None:
        return "SysML document"
    return os.path.splitext(os.path.basename(file_path))[0]


def _location_message(file_path: Optional[str], span: SysMLSpan) -> str:
    location = file_path if file_path is not None else "<string>"
    return f"{location}, line {span.line_start}"


def _single_line_field(field_name: str, value: str) -> SDocNodeField:
    return SDocNodeField.create_from_string(
        parent=None,
        field_name=field_name,
        field_value=value,
        multiline=False,
    )


def _content_field(field_name: str, value: str) -> SDocNodeField:
    return SDocNodeField(
        parent=None,
        field_name=field_name,
        parts=[value],
        multiline__="multiline" if "\n" in value else None,
    )


def _collapse_value(raw_value: str) -> str:
    collapsed = " ".join(
        line_.strip() for line_ in raw_value.split("\n") if line_.strip()
    )
    return collapsed


def _wire_field_parents(node: SDocNode) -> None:
    for fields_ in node.ordered_fields_lookup.values():
        for field_ in fields_:
            field_.parent = node


def _mark_has_requirements(container: Union[SDocDocument, SDocNode]) -> None:
    current: Union[SDocDocument, SDocNode, None] = container
    while current is not None:
        current.ng_has_requirements = True
        if isinstance(current, SDocNode):
            parent_ = current.parent
            current = (
                parent_
                if isinstance(parent_, (SDocNode, SDocDocument))
                else None
            )
        else:
            current = None


def _is_representable_attribute(attribute: SysMLAttribute) -> bool:
    if attribute.name is None or attribute.short_name is not None:
        return False
    if len(attribute.modifiers) > 0 or len(attribute.annotations) > 0:
        return False
    if attribute.multiplicity is not None:
        return False
    if len(attribute.specializations) > 1:
        return False
    for specialization_ in attribute.specializations:
        if specialization_.operator != ":":
            return False
    return True


def _is_representable_requirement(element: SysMLElement) -> bool:
    if element.kind != "requirement" or element.is_definition:
        return False
    if (
        len(element.modifiers) > 0
        or len(element.specializations) > 0
        or len(element.annotations) > 0
        or element.multiplicity is not None
        or element.value_text is not None
        or element.result_text is not None
    ):
        return False
    doc_count = 0
    constraint_count = 0
    attribute_names: Set[str] = set()
    for member_ in element.members:
        if isinstance(member_, SysMLDocComment):
            doc_count += 1
        elif isinstance(member_, SysMLRequireConstraint):
            constraint_count += 1
        elif isinstance(member_, (SysMLLineNote, SysMLBlockComment)):
            continue
        elif isinstance(member_, SysMLAttribute):
            if not _is_representable_attribute(member_):
                return False
            assert member_.name is not None
            if member_.name in attribute_names:
                return False
            attribute_names.add(member_.name)
            if node_data.attribute_field_title(member_.name) in (
                RESERVED_REQUIREMENT_FIELDS
            ):
                return False
        else:
            return False
    return doc_count <= 1 and constraint_count <= 1


def _is_representable_dependency(dependency: SysMLDependency) -> bool:
    if len(dependency.sources) == 0 or len(dependency.targets) == 0:
        return False
    return all(
        annotation_ == "derivation" for annotation_ in dependency.annotations
    )


def _is_representable_package(package: SysMLPackage) -> bool:
    if package.short_name is not None:
        return False
    for member_ in package.members:
        if isinstance(member_, SysMLPackage):
            if not _is_representable_package(member_):
                return False
        elif isinstance(
            member_,
            (SysMLDocComment, SysMLImport, SysMLLineNote, SysMLBlockComment),
        ):
            continue
        elif isinstance(member_, SysMLDependency):
            if not _is_representable_dependency(member_):
                return False
        elif isinstance(member_, SysMLElement):
            if not _is_representable_requirement(member_):
                return False
        else:
            return False
    return True


def _collect_requirement_attributes(
    members: List[SysMLMember],
) -> List[SysMLAttribute]:
    attributes: List[SysMLAttribute] = []
    for member_ in members:
        if isinstance(member_, SysMLPackage):
            attributes.extend(_collect_requirement_attributes(member_.members))
        elif isinstance(member_, SysMLElement):
            for child_ in member_.members:
                if isinstance(child_, SysMLAttribute):
                    attributes.append(child_)
    return attributes


@dataclass
class _RequirementsBuildState:
    document: SDocDocument
    document_reference: DocumentReference
    including_reference: DocumentReference
    relative_path: str
    file_path: Optional[str]
    attribute_field_titles: List[str]
    nodes_by_uid: Dict[str, SDocNode] = field(default_factory=dict)
    pending_dependencies: List[SysMLDependency] = field(default_factory=list)
    has_derivation_prefix: bool = False


def _build_requirements_document(
    model: SysMLModel,
    file_path: Optional[str],
    relative_path: str,
) -> SDocDocument:
    top_package = [m_ for m_ in model.members if isinstance(m_, SysMLPackage)][
        0
    ]
    title = (
        top_package.name
        if top_package.name is not None
        else _fallback_title(file_path)
    )
    attribute_field_titles: List[str] = []
    for attribute_ in _collect_requirement_attributes(model.members):
        assert attribute_.name is not None
        field_title = node_data.attribute_field_title(attribute_.name)
        if field_title not in attribute_field_titles:
            attribute_field_titles.append(field_title)

    document = SDocDocument(
        mid=str(_stable_mid(relative_path)),
        title=title,
        config=None,
        view=None,
        grammar=None,
        section_contents=[],
    )
    document.grammar = _create_requirements_grammar(
        document, attribute_field_titles
    )
    document.ng_including_document_reference = DocumentReference()
    document_reference = DocumentReference()
    document_reference.set_document(document)

    state = _RequirementsBuildState(
        document=document,
        document_reference=document_reference,
        including_reference=DocumentReference(),
        relative_path=relative_path,
        file_path=file_path,
        attribute_field_titles=attribute_field_titles,
    )
    _add_requirements_members(
        document, top_package.members, state, path_prefix=""
    )
    _resolve_dependencies(state)
    node_data.set_derivation_prefix(document, state.has_derivation_prefix)
    return document


def _create_requirements_grammar(
    document: SDocDocument, attribute_field_titles: List[str]
) -> DocumentGrammar:
    section_element = DocumentGrammar.create_default_section_element(
        parent=None, enable_mid=False
    )
    text_element = DocumentGrammar.create_default_text_element(
        parent=None, enable_mid=False
    )
    fields: List[GrammarElementFieldType] = [
        GrammarElementFieldString(
            parent=None,
            title=UID_FIELD,
            human_title=None,
            required="False",
        ),
        GrammarElementFieldString(
            parent=None,
            title=TITLE_FIELD,
            human_title=None,
            required="False",
        ),
    ]
    for attribute_title_ in attribute_field_titles:
        fields.append(
            GrammarElementFieldString(
                parent=None,
                title=attribute_title_,
                human_title=None,
                required="False",
            )
        )
    fields.extend(
        [
            GrammarElementFieldString(
                parent=None,
                title=STATEMENT_FIELD,
                human_title=None,
                required="False",
            ),
            GrammarElementFieldString(
                parent=None,
                title=CONSTRAINT_FIELD,
                human_title=None,
                required="False",
            ),
        ]
    )
    requirement_element = GrammarElement(
        parent=None,
        tag=REQUIREMENT_TAG,
        property_is_composite="",
        property_prefix="",
        property_view_style="",
        fields=fields,
        relations=[],
    )
    requirement_element.relations = [
        GrammarElementRelationParent(
            parent=requirement_element,
            relation_type="Parent",
            relation_role=None,
            reverse_relation_role=None,
        ),
        GrammarElementRelationChild(
            parent=requirement_element,
            relation_type="Child",
            relation_role=None,
            reverse_relation_role=None,
        ),
    ]
    elements: List[GrammarElement] = [
        section_element,
        text_element,
        requirement_element,
    ]
    grammar = DocumentGrammar(
        parent=document, elements=elements, import_from_file=None
    )
    for element_ in elements:
        element_.parent = grammar
    return grammar


def _add_requirements_members(
    container: Union[SDocDocument, SDocNode],
    members: List[SysMLMember],
    state: _RequirementsBuildState,
    path_prefix: str,
) -> None:
    imports: List[str] = []
    section_index = 0
    for member_ in members:
        if isinstance(member_, SysMLDocComment):
            text_node = _create_text_node(
                container, member_.text, state, member_.span
            )
            container.section_contents.append(text_node)
        elif isinstance(member_, SysMLImport):
            if member_.visibility is not None:
                imports.append(f"{member_.visibility} import {member_.target};")
            else:
                imports.append(f"import {member_.target};")
        elif isinstance(member_, SysMLPackage):
            section_index += 1
            section_name = member_.name if member_.name is not None else ""
            section = SDocNode.create_section(
                container, state.document, section_name
            )
            section.ng_line_start = member_.span.line_start
            section.ng_col_start = member_.span.col_start
            section.ng_including_document_reference = DocumentReference()
            section.ng_document_reference = DocumentReference()
            section.ng_document_reference.set_document(state.document)
            section.reserved_mid = _stable_mid(
                state.relative_path, "section", path_prefix, str(section_index)
            )
            container.section_contents.append(section)
            _add_requirements_members(
                section,
                member_.members,
                state,
                path_prefix=f"{path_prefix}/{section_index}",
            )
        elif isinstance(member_, SysMLElement):
            _create_requirement_node(container, member_, state)
        elif isinstance(member_, SysMLDependency):
            state.pending_dependencies.append(member_)
        # Line notes, block comments and nothing else are dropped.

    if len(imports) > 0:
        node_data.set_imports(container, imports)


def _create_text_node(
    container: Union[SDocDocument, SDocNode],
    text: str,
    state: _RequirementsBuildState,
    span: SysMLSpan,
) -> SDocNode:
    fields: List[SDocNodeField] = []
    if len(text) > 0:
        fields.append(_content_field(STATEMENT_FIELD, text))
    node = SDocNode(
        parent=container, node_type=TEXT_TAG, fields=fields, relations=[]
    )
    _wire_field_parents(node)
    node.ng_document_reference = state.document_reference
    node.ng_including_document_reference = state.including_reference
    node.ng_line_start = span.line_start
    node.ng_col_start = span.col_start
    return node


def _create_requirement_node(
    container: Union[SDocDocument, SDocNode],
    element: SysMLElement,
    state: _RequirementsBuildState,
) -> None:
    attributes: List[SysMLAttribute] = [
        member_
        for member_ in element.members
        if isinstance(member_, SysMLAttribute)
    ]
    value_by_field_title: Dict[str, str] = {}
    for attribute_ in attributes:
        assert attribute_.name is not None
        if attribute_.value_text is not None:
            value_by_field_title[
                node_data.attribute_field_title(attribute_.name)
            ] = _collapse_value(attribute_.value_text)

    fields: List[SDocNodeField] = []
    if element.short_name is not None:
        fields.append(_single_line_field(UID_FIELD, element.short_name))
    if element.name is not None and len(element.name) > 0:
        fields.append(_single_line_field(TITLE_FIELD, element.name))
    for field_title_ in state.attribute_field_titles:
        if field_title_ in value_by_field_title:
            fields.append(
                _single_line_field(
                    field_title_, value_by_field_title[field_title_]
                )
            )
    if element.doc is not None and len(element.doc) > 0:
        fields.append(_content_field(STATEMENT_FIELD, element.doc))
    constraint_text = element.require_constraint_text
    if constraint_text is not None and len(constraint_text) > 0:
        fields.append(_content_field(CONSTRAINT_FIELD, constraint_text))

    node = SDocNode(
        parent=container,
        node_type=REQUIREMENT_TAG,
        fields=fields,
        relations=[],
    )
    _wire_field_parents(node)
    node.ng_document_reference = state.document_reference
    node.ng_including_document_reference = state.including_reference
    node.ng_line_start = element.span.line_start
    node.ng_col_start = element.span.col_start
    node.reserved_mid = _stable_mid(
        state.relative_path,
        "requirement",
        element.short_name
        if element.short_name is not None
        else f"line-{element.span.line_start}",
    )
    node_data.set_attribute_types(
        node,
        {
            assert_cast(attribute_.name, str): attribute_.type_text
            for attribute_ in attributes
        },
    )

    if element.short_name is not None:
        if element.short_name in state.nodes_by_uid:
            raise StrictDocException(
                "Could not read SysML file: "
                f"{_location_message(state.file_path, element.span)}: "
                f"duplicate requirement UID '{element.short_name}'."
            )
        state.nodes_by_uid[element.short_name] = node

    container.section_contents.append(node)
    _mark_has_requirements(container)


def _resolve_dependencies(state: _RequirementsBuildState) -> None:
    for dependency_ in state.pending_dependencies:
        if "derivation" in dependency_.annotations:
            state.has_derivation_prefix = True
        for source_ in dependency_.sources:
            child_node = state.nodes_by_uid.get(source_)
            if child_node is None:
                raise StrictDocException(
                    "Could not read SysML file: "
                    f"{_location_message(state.file_path, dependency_.span)}: "
                    f"dependency source '{source_}' is not a requirement "
                    "in this file."
                )
            for target_ in dependency_.targets:
                child_node.relations.append(
                    ParentReqReference(
                        parent=child_node, ref_uid=target_, role=None
                    )
                )


@dataclass
class _DesignBuildState:
    document: SDocDocument
    document_reference: DocumentReference
    including_reference: DocumentReference
    relative_path: str
    file_path: Optional[str]
    nodes_by_qualified_name: Dict[str, SDocNode] = field(default_factory=dict)
    used_mid_keys: Set[str] = field(default_factory=set)
    pending_relations: List[
        Tuple[str, str, Optional[str], Optional[SDocNode], SysMLSpan]
    ] = field(default_factory=list)


def _build_design_document(
    model: SysMLModel,
    file_path: Optional[str],
    relative_path: str,
) -> SDocDocument:
    packages = [m_ for m_ in model.members if isinstance(m_, SysMLPackage)]
    root_name: Optional[str] = None
    members: List[SysMLMember] = list(model.members)
    title = _fallback_title(file_path)
    if len(packages) == 1:
        members = list(packages[0].members)
        root_name = packages[0].name
        if root_name is not None:
            title = root_name

    document = SDocDocument(
        mid=str(_stable_mid(relative_path)),
        title=title,
        config=None,
        view=None,
        grammar=None,
        section_contents=[],
        autogen=True,
    )
    # Design elements carry source text, which is not valid RST. Plain text
    # markup shows it verbatim.
    document.config.markup = SDocMarkup.TEXT
    document.grammar = _create_design_grammar(document)
    document.ng_including_document_reference = DocumentReference()
    document_reference = DocumentReference()
    document_reference.set_document(document)

    state = _DesignBuildState(
        document=document,
        document_reference=document_reference,
        including_reference=DocumentReference(),
        relative_path=relative_path,
        file_path=file_path,
    )
    prefix: List[str] = [root_name] if root_name is not None else []
    _add_design_members(
        document,
        members,
        state,
        qualified_prefix=prefix,
        enclosing_node=None,
    )
    _resolve_design_relations(state)
    return document


def _create_design_grammar(document: SDocDocument) -> DocumentGrammar:
    section_element = DocumentGrammar.create_default_section_element(
        parent=None, enable_mid=False
    )
    text_element = DocumentGrammar.create_default_text_element(
        parent=None, enable_mid=False
    )
    elements: List[GrammarElement] = [section_element, text_element]
    for tag_ in sorted(set(DESIGN_TAGS.values())):
        fields: List[GrammarElementFieldType] = [
            GrammarElementFieldString(
                parent=None,
                title=field_title_,
                human_title=None,
                required="False",
            )
            for field_title_ in (
                UID_FIELD,
                TITLE_FIELD,
                "ELEMENT_KIND",
                STATEMENT_FIELD,
                "SOURCE",
            )
        ]
        element = GrammarElement(
            parent=None,
            tag=tag_,
            property_is_composite="True",
            property_prefix="",
            property_view_style="",
            fields=fields,
            relations=[],
        )
        element.relations = [
            GrammarElementRelationParent(
                parent=element,
                relation_type="Parent",
                relation_role=SATISFIES_ROLE,
                reverse_relation_role=SATISFIED_BY_ROLE,
            ),
            GrammarElementRelationParent(
                parent=element,
                relation_type="Parent",
                relation_role=VERIFIES_ROLE,
                reverse_relation_role=VERIFIED_BY_ROLE,
            ),
        ]
        elements.append(element)
    grammar = DocumentGrammar(
        parent=document, elements=elements, import_from_file=None
    )
    for element_ in elements:
        element_.parent = grammar
    return grammar


def _sanitize_uid(raw_uid: str) -> str:
    """Replace characters that StrictDoc UIDs do not allow with `_`."""
    sanitized = re.sub(r"[^\w()\-/.: ]", "_", raw_uid)
    if re.match(r"\w", sanitized) is None:
        sanitized = "_" + sanitized
    return sanitized


def _add_design_members(
    container: Union[SDocDocument, SDocNode],
    members: List[SysMLMember],
    state: _DesignBuildState,
    qualified_prefix: List[str],
    enclosing_node: Optional[SDocNode],
) -> None:
    section_index = 0
    for member_ in members:
        if isinstance(member_, SysMLDocComment):
            text_node = _create_design_text_node(container, member_.text, state)
            text_node.ng_line_start = member_.span.line_start
            text_node.ng_col_start = member_.span.col_start
            container.section_contents.append(text_node)
        elif isinstance(member_, SysMLPackage):
            section_index += 1
            section_name = member_.name if member_.name is not None else ""
            section = SDocNode.create_section(
                container, state.document, section_name
            )
            section.autogen = True
            section.ng_line_start = member_.span.line_start
            section.ng_col_start = member_.span.col_start
            section.ng_including_document_reference = DocumentReference()
            section.ng_document_reference = DocumentReference()
            section.ng_document_reference.set_document(state.document)
            container.section_contents.append(section)
            child_prefix = (
                qualified_prefix + [member_.name]
                if member_.name is not None
                else qualified_prefix
            )
            _add_design_members(
                section,
                member_.members,
                state,
                qualified_prefix=child_prefix,
                enclosing_node=enclosing_node,
            )
        elif isinstance(member_, SysMLElement):
            element_tag = DESIGN_TAGS.get((member_.kind, member_.is_definition))
            child_prefix = (
                qualified_prefix + [member_.name]
                if member_.name is not None
                else qualified_prefix
            )
            if element_tag is None:
                _add_design_members(
                    container,
                    member_.members,
                    state,
                    qualified_prefix=child_prefix,
                    enclosing_node=enclosing_node,
                )
                continue
            node = _create_design_node(
                container, member_, element_tag, child_prefix, state
            )
            container.section_contents.append(node)
            _add_design_members(
                node,
                member_.members,
                state,
                qualified_prefix=child_prefix,
                enclosing_node=node,
            )
        elif isinstance(member_, SysMLSatisfy):
            state.pending_relations.append(
                (
                    SATISFIES_ROLE,
                    member_.requirement,
                    member_.by,
                    enclosing_node,
                    member_.span,
                )
            )
        elif isinstance(member_, SysMLVerify):
            state.pending_relations.append(
                (
                    VERIFIES_ROLE,
                    member_.requirement,
                    None,
                    enclosing_node,
                    member_.span,
                )
            )


def _create_design_text_node(
    container: Union[SDocDocument, SDocNode],
    text: str,
    state: _DesignBuildState,
) -> SDocNode:
    fields: List[SDocNodeField] = []
    if len(text) > 0:
        fields.append(_content_field(STATEMENT_FIELD, text))
    node = SDocNode(
        parent=container,
        node_type=TEXT_TAG,
        fields=fields,
        relations=[],
        autogen=True,
    )
    _wire_field_parents(node)
    node.ng_document_reference = state.document_reference
    node.ng_including_document_reference = state.including_reference
    return node


def _create_design_node(
    container: Union[SDocDocument, SDocNode],
    element: SysMLElement,
    element_tag: str,
    qualified_prefix: List[str],
    state: _DesignBuildState,
) -> SDocCompositeNode:
    qualified_name = (
        "::".join(qualified_prefix) if len(qualified_prefix) > 0 else None
    )
    raw_uid: Optional[str] = (
        element.short_name if element.short_name is not None else qualified_name
    )
    fields: List[SDocNodeField] = []
    if raw_uid is not None:
        fields.append(_single_line_field(UID_FIELD, _sanitize_uid(raw_uid)))
    if element.name is not None:
        fields.append(_single_line_field(TITLE_FIELD, element.name))
    element_kind = (
        f"{element.kind} def" if element.is_definition else element.kind
    )
    fields.append(_single_line_field("ELEMENT_KIND", element_kind))
    if element.doc is not None and len(element.doc) > 0:
        fields.append(_content_field(STATEMENT_FIELD, element.doc))
    fields.append(_content_field("SOURCE", element.source_text))

    node = SDocCompositeNode(
        parent=container,
        node_type=element_tag,
        fields=fields,
        relations=[],
        section_contents=[],
        node_type_close=element_tag,
    )
    node.autogen = True
    _wire_field_parents(node)
    node.ng_document_reference = state.document_reference
    node.ng_including_document_reference = state.including_reference
    node.ng_line_start = element.span.line_start
    node.ng_col_start = element.span.col_start

    key = (
        qualified_name
        if qualified_name is not None
        else (f"{element_tag}-line-{element.span.line_start}")
    )
    unique_key = key
    suffix = 1
    while unique_key in state.used_mid_keys:
        suffix += 1
        unique_key = f"{key}#{suffix}"
    state.used_mid_keys.add(unique_key)
    node.reserved_mid = _stable_mid(state.relative_path, "design", unique_key)

    if (
        qualified_name is not None
        and qualified_name not in state.nodes_by_qualified_name
    ):
        state.nodes_by_qualified_name[qualified_name] = node
    return node


def _find_design_node(
    name: str, state: _DesignBuildState
) -> Optional[SDocNode]:
    if name in state.nodes_by_qualified_name:
        return state.nodes_by_qualified_name[name]
    for qualified_name_, node_ in state.nodes_by_qualified_name.items():
        if qualified_name_.endswith(f"::{name}"):
            return node_
    return None


def _resolve_design_relations(state: _DesignBuildState) -> None:
    for (
        role_,
        requirement_uid_,
        by_name_,
        enclosing_,
        span_,
    ) in state.pending_relations:
        target_node: Optional[SDocNode]
        if by_name_ is not None:
            target_node = _find_design_node(by_name_, state)
            if target_node is None:
                raise StrictDocException(
                    "Could not read SysML file: "
                    f"{_location_message(state.file_path, span_)}: "
                    f"'{by_name_}' is not an element of this file."
                )
        else:
            target_node = enclosing_
        if target_node is None:
            raise StrictDocException(
                "Could not read SysML file: "
                f"{_location_message(state.file_path, span_)}: "
                f"'{role_.lower()}' statement must be inside an element "
                "or name the element with 'by'."
            )
        target_node.relations.append(
            ParentReqReference(
                parent=target_node, ref_uid=requirement_uid_, role=role_
            )
        )
