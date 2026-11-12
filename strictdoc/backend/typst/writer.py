"""
Writes an SDoc document as a Typst document in the company report style.

The document imports the company-report template, which draws the letterhead,
page header and footer, and the author and revision tables. The template is
the company's and is not part of StrictDoc: the company typst-doc-builder
image places it next to the exported files when it compiles them.
"""

import re
from typing import Callable, Dict, List, Optional, Set, Tuple, Union

from strictdoc.backend.sdoc.constants import SDocMarkup
from strictdoc.backend.sdoc.models.anchor import Anchor
from strictdoc.backend.sdoc.models.document import SDocDocument
from strictdoc.backend.sdoc.models.document_config import (
    DocumentCustomMetadataKeyValuePair,
)
from strictdoc.backend.sdoc.models.inline_link import InlineLink
from strictdoc.backend.sdoc.models.model import RequirementFieldName
from strictdoc.backend.sdoc.models.node import SDocNode, SDocNodeField
from strictdoc.backend.sysml import node_data
from strictdoc.backend.typst.rst_to_typst import (
    ANCHOR_ROLE,
    LINK_ROLE,
    RstToTypstConverter,
)
from strictdoc.backend.typst.typst_markup import (
    escape_markup,
    label_for,
    string_literal,
)
from strictdoc.core.document_iterator import SDocDocumentIterator
from strictdoc.core.project_config import ProjectConfig
from strictdoc.core.traceability_index import TraceabilityIndex
from strictdoc.helpers.cast import assert_cast
from strictdoc.helpers.git_client import GitClient
from strictdoc.helpers.rst import escape_str_after_inline_markup
from strictdoc.helpers.string import interpolate_at_pattern_lazy

# The node type whose nodes fill the revision history table of the report.
REVISION_NODE_TYPE = "REVISION"

# Fields that the requirement table shows in the UID column, or not at all.
_HIDDEN_FIELDS = frozenset(
    (
        RequirementFieldName.MID,
        RequirementFieldName.UID,
        RequirementFieldName.LEVEL,
        RequirementFieldName.PREFIX,
        RequirementFieldName.TITLE,
    )
)

_ISO_DATE_REGEX = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


class TypstWriter:
    def __init__(
        self,
        *,
        traceability_index: TraceabilityIndex,
        project_config: ProjectConfig,
        path_to_output_dir: str,
    ) -> None:
        self.traceability_index: TraceabilityIndex = traceability_index
        self.project_config: ProjectConfig = project_config
        self.path_to_output_dir: str = path_to_output_dir
        self.git_client: GitClient = GitClient()
        self.warnings: List[str] = []

    def write(self, document: SDocDocument, diagram_name_prefix: str) -> str:
        document_labels = self._collect_labels(document)
        converter = RstToTypstConverter(
            path_to_output_dir=self.path_to_output_dir,
            render_link=lambda uid_: self._render_link(uid_, document_labels),
            render_anchor=self._render_anchor,
            diagram_name_prefix=diagram_name_prefix,
        )
        writer = _DocumentWriter(
            document=document,
            traceability_index=self.traceability_index,
            converter=converter,
            document_labels=document_labels,
            render_link=lambda uid_: self._render_link(uid_, document_labels),
        )
        body = writer.write_body()

        output = "// Exported by StrictDoc. Do not edit: export the document again.\n"
        output += '#import "company-report.typ": company-report\n'
        if converter.has_diagrams:
            output += '#import "kroki.typ": kroki\n'
        output += '#import "strictdoc.typ": *\n\n'
        output += self._write_report_header(document, writer.revisions)
        if converter.has_diagrams:
            output += "#show: kroki\n"
        output += "\n#outline(depth: 2)\n#pagebreak()\n\n"
        output += body
        output += "\n"

        self.warnings.extend(
            f"{document.title}: {warning_}" for warning_ in converter.warnings
        )
        return output

    def _write_report_header(
        self, document: SDocDocument, revisions: List[Tuple[str, str, str]]
    ) -> str:
        assert document.meta is not None
        version = self._resolve_git_variables(document.config.version)
        if version is None and len(revisions) > 0:
            version = revisions[-1][0]
        date = self._resolve_git_variables(document.config.date)

        # One argument per line, each a string literal: typst-doc-builder
        # reads doc_no, version and title from these lines to name the PDF.
        arguments: List[str] = [
            f"title: {string_literal(document.title)}",
            f"author: {string_literal(self._metadata(document, 'AUTHOR'))}",
            "author_role: "
            + string_literal(self._metadata(document, "AUTHOR_ROLE")),
            f"doc_no: {string_literal(document.config.uid or 'XXX_XXXX')}",
            f"version: {string_literal(version or '01')}",
            f"project: {string_literal(self.project_config.project_title)}",
            f"filename: {string_literal(document.meta.document_filename)}",
        ]
        if date is not None:
            date_match = _ISO_DATE_REGEX.match(date.strip())
            if date_match is not None:
                year, month, day = (int(part_) for part_ in date_match.groups())
                arguments.append(
                    f"date: datetime(year: {year}, month: {month}, day: {day})"
                )
        if len(revisions) > 0:
            rows = "".join(
                f"    ([{escape_markup(revision_)}], [{date_}], "
                f"[{description_}]),\n"
                for revision_, date_, description_ in revisions
            )
            arguments.append(
                f"revision-history: sd-revision-history(\n{rows}  )"
            )

        output = "#show: company-report.with(\n"
        output += "".join(f"  {argument_},\n" for argument_ in arguments)
        output += ")\n"
        return output

    def _metadata(self, document: SDocDocument, key: str) -> str:
        """The value of a METADATA entry, matching AUTHOR_ROLE to "Author role"."""
        custom_metadata = document.config.custom_metadata
        if custom_metadata is None:
            return ""
        for entry_ in custom_metadata.entries:
            if (
                isinstance(entry_, DocumentCustomMetadataKeyValuePair)
                and entry_.key is not None
                and re.sub(r"[\s-]+", "_", entry_.key.strip()).upper() == key
            ):
                return (
                    self._resolve_git_variables(entry_.get_text_value().strip())
                    or ""
                )
        return ""

    def _resolve_git_variables(self, value: Optional[str]) -> Optional[str]:
        """Replace @GIT_VERSION and the like, as the HTML export does."""
        if value is None:
            return None

        def resolver(variable_name: str) -> str:
            if variable_name == "GIT_VERSION":
                return self.git_client.get_commit_hash()
            if variable_name == "GIT_BRANCH":
                return self.git_client.get_branch()
            if variable_name == "GIT_COMMIT_DATE":
                return self.git_client.get_commit_date()
            if variable_name == "GIT_COMMIT_DATETIME":
                return self.git_client.get_commit_datetime()
            return variable_name

        return interpolate_at_pattern_lazy(value, resolver)

    def _collect_labels(self, document: SDocDocument) -> Set[str]:
        """
        The UIDs that become labels of this Typst document. A link to any
        other UID points out of the PDF.
        """
        labels: Set[str] = set()
        iterator = SDocDocumentIterator(document)
        for node_, _ in iterator.all_content(print_fragments=True):
            if not isinstance(node_, SDocNode):
                continue
            if node_.node_type == REVISION_NODE_TYPE:
                continue
            if node_.reserved_uid is not None:
                labels.add(node_.reserved_uid)
            for field_ in node_.enumerate_fields():
                for part_ in field_.parts:
                    if isinstance(part_, Anchor):
                        labels.add(part_.value)
        return labels

    def _render_link(self, uid: str, document_labels: Set[str]) -> str:
        target = self.traceability_index.get_linkable_node_by_uid_weak(uid)
        if target is None:
            return escape_markup(uid)
        if isinstance(target, SDocDocument):
            return f"#emph[{escape_markup(target.title)}]"
        title = escape_markup(
            target.get_display_title(include_toc_number=False)
        )
        if uid in document_labels:
            return f"#link({label_for(uid)})[{title}]"
        target_document = assert_cast(
            target.get_document()
            if isinstance(target, Anchor)
            else target.get_parent_or_including_document(),
            SDocDocument,
        )
        return (
            f"#sd-external-link([{title}], "
            f"[{escape_markup(target_document.title)}])"
        )

    @staticmethod
    def _render_anchor(uid: str) -> str:
        return f"#metadata({string_literal(uid)})#{label_for(uid)}"


class _DocumentWriter:
    """Writes the body of one document: its sections, text and nodes."""

    def __init__(
        self,
        *,
        document: SDocDocument,
        traceability_index: TraceabilityIndex,
        converter: RstToTypstConverter,
        document_labels: Set[str],
        render_link: Callable[[str], str],
    ) -> None:
        self.document: SDocDocument = document
        self.traceability_index: TraceabilityIndex = traceability_index
        self.converter: RstToTypstConverter = converter
        self.document_labels: Set[str] = document_labels
        self.render_link: Callable[[str], str] = render_link
        # (revision as plain text, date as Typst, description as Typst)
        self.revisions: List[Tuple[str, str, str]] = []
        self._blocks: List[str] = []
        self._pending_requirements: List[str] = []

    def write_body(self) -> str:
        iterator = SDocDocumentIterator(self.document)
        for node_, context_ in iterator.all_content(print_fragments=True):
            level = max(context_.get_level(), 1)
            if isinstance(node_, SDocDocument):
                # The root of an included document.
                self._flush_requirements()
                self._blocks.append(
                    self._heading(node_.title, level, node_.config.uid, True)
                )
                continue
            if not isinstance(node_, SDocNode):
                continue
            # The diagram that the SysML reader puts at the top of each
            # SysML document is for the web pages only.
            if node_data.is_diagram(node_):
                continue
            if node_.node_type == REVISION_NODE_TYPE:
                self.revisions.append(self._revision(node_))
            elif node_.node_type == "SECTION" or (
                node_.is_text_node() and node_.reserved_title is not None
            ):
                self._flush_requirements()
                assert node_.reserved_title is not None
                self._blocks.append(
                    self._heading(
                        node_.reserved_title,
                        level,
                        node_.reserved_uid,
                        node_.ng_resolved_custom_level != "None",
                    )
                )
                if node_.is_text_node():
                    self._write_text_node(node_)
            elif node_.is_text_node():
                self._flush_requirements()
                self._write_text_node(node_)
            else:
                self._pending_requirements.append(self._requirement(node_))
        self._flush_requirements()
        return "\n\n".join(block_ for block_ in self._blocks if len(block_) > 0)

    def _flush_requirements(self) -> None:
        if len(self._pending_requirements) == 0:
            return
        self._blocks.append(
            "#sd-requirements(\n"
            + "".join(
                f"  {requirement_},\n"
                for requirement_ in self._pending_requirements
            )
            + ")"
        )
        self._pending_requirements = []

    @staticmethod
    def _heading(
        title: str, level: int, uid: Optional[str], numbered: bool
    ) -> str:
        arguments = f"level: {level}"
        if not numbered:
            arguments += ", numbering: none"
        output = f"#heading({arguments})[{escape_markup(title)}]"
        if uid is not None:
            output += f"#{label_for(uid)}"
        return output

    def _write_text_node(self, node: SDocNode) -> None:
        if not node.has_reserved_statement():
            return
        self._blocks.append(self._field_block(node.get_content_field()))

    def _requirement(self, node: SDocNode) -> str:
        entries: Dict[str, str] = {}
        if node.reserved_uid is not None:
            entries["uid"] = string_literal(node.reserved_uid)
        if node.reserved_title is not None:
            entries["title"] = f"[{escape_markup(node.reserved_title)}]"

        content_field_name: Optional[str] = None
        if node.has_reserved_statement():
            content_field = node.get_content_field()
            content_field_name = content_field.field_name
            entries["statement"] = f"[{self._field_block(content_field)}]"

        short_fields: List[str] = []
        long_fields: List[str] = []
        for field_ in node.enumerate_fields():
            if (
                field_.field_name in _HIDDEN_FIELDS
                or field_.field_name == content_field_name
            ):
                continue
            name = escape_markup(self._field_title(node, field_.field_name))
            if field_.is_multiline():
                value = self._field_block(field_)
                long_fields.append(f"([{name}], [{value}])")
            else:
                value = self._field_inline(field_)
                short_fields.append(f"([{name}], [{value}])")
        if len(short_fields) > 0:
            entries["short-fields"] = _array(short_fields)
        if len(long_fields) > 0:
            entries["fields"] = _array(long_fields)

        parents = [
            self._relation(parent_)
            for parent_ in self.traceability_index.get_parent_requirements(node)
        ]
        if len(parents) > 0:
            entries["parents"] = _array(parents)
        children = [
            self._relation(child_)
            for child_ in self.traceability_index.get_children_requirements(
                node
            )
        ]
        if len(children) > 0:
            entries["children"] = _array(children)

        return (
            "("
            + ", ".join(f"{key_}: {value_}" for key_, value_ in entries.items())
            + ")"
        )

    @staticmethod
    def _field_title(node: SDocNode, field_name: str) -> str:
        """
        The human title of a field. A field without one, such as
        VERIFICATION, is shown as "Verification".
        """
        human_title = node.get_field_human_title(field_name)
        if human_title == field_name:
            return field_name.replace("_", " ").capitalize()
        return human_title

    def _relation(self, node: SDocNode) -> str:
        """A parent or child, shown by its UID."""
        uid = node.reserved_uid
        assert uid is not None
        if uid in self.document_labels:
            return f"[#link({label_for(uid)})[{escape_markup(uid)}]]"
        document = assert_cast(
            node.get_parent_or_including_document(), SDocDocument
        )
        return (
            f"[#sd-external-link([{escape_markup(uid)}], "
            f"[{escape_markup(document.title)}])]"
        )

    def _revision(self, node: SDocNode) -> Tuple[str, str, str]:
        def field_or_none(*names: str) -> Optional[SDocNodeField]:
            for name_ in names:
                fields = node.ordered_fields_lookup.get(name_)
                if fields is not None and len(fields) > 0:
                    return fields[0]
            return None

        revision = field_or_none("REVISION", "VERSION")
        date = field_or_none("DATE")
        description = field_or_none(
            "DESCRIPTION", "STATEMENT", "CONTENT", "COMMENT"
        )
        # The revision stays plain text: it is also the version string of
        # the report header.
        return (
            revision.get_text_value().strip() if revision is not None else "",
            escape_markup(date.get_text_value().strip())
            if date is not None
            else "",
            self._field_block(description) if description is not None else "",
        )

    def _field_block(self, field: SDocNodeField) -> str:
        if self._markup(field) == SDocMarkup.RST:
            return self.converter.convert(self._field_rst(field))
        return self._field_text(field)

    def _field_inline(self, field: SDocNodeField) -> str:
        if self._markup(field) == SDocMarkup.RST:
            return self.converter.convert_inline(self._field_rst(field))
        return self._field_text(field)

    @staticmethod
    def _markup(field: SDocNodeField) -> str:
        node = field.get_owning_node()
        assert node is not None
        document = node.get_document()
        assert isinstance(document, SDocDocument)
        return document.config.get_markup()

    @staticmethod
    def _field_rst(field: SDocNodeField) -> str:
        """
        The RST text of a field. Links and anchors become RST roles that the
        converter writes as Typst links and labels.
        """
        output = ""
        previous_part: Union[str, InlineLink, Anchor, None] = None
        for part_ in field.parts:
            if isinstance(part_, str):
                if isinstance(previous_part, InlineLink):
                    output += escape_str_after_inline_markup(part_)
                else:
                    output += part_
            elif isinstance(part_, InlineLink):
                output += f":{LINK_ROLE}:`{part_.link}`"
            elif isinstance(part_, Anchor):
                output += f"\n\n:{ANCHOR_ROLE}:`{part_.value}`\n\n"
            else:
                raise NotImplementedError(part_)
            previous_part = part_
        return output

    def _field_text(self, field: SDocNodeField) -> str:
        """
        Text, HTML and Markdown fields are written as plain text, one
        paragraph per blank-line separated block.
        """
        output = ""
        for part_ in field.parts:
            if isinstance(part_, str):
                output += escape_markup(part_)
            elif isinstance(part_, InlineLink):
                output += self.render_link(part_.link)
            elif isinstance(part_, Anchor):
                output += TypstWriter._render_anchor(part_.value)
        return output.strip()


def _array(items: List[str]) -> str:
    # The trailing comma keeps a one-item array from being read as
    # parentheses around a value.
    return "(" + ", ".join(items) + ",)"
