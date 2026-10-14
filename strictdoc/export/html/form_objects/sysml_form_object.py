"""
Form objects for editing SysML design packages in the web UI.

SysMLElementFormObject holds the editor of one design element: the DETAILS
row, the MEMBERS rows and the element source. SysMLSourceFormObject holds
the editor of the whole file. See strictdoc/backend/sysml/editor.py for how
the edits are applied.
"""

from typing import Dict, List, Tuple

from starlette.datastructures import FormData

from strictdoc.backend.sysml import editor, node_data
from strictdoc.backend.sysml.editor import SysMLTableRow
from strictdoc.backend.sysml.model import SysMLElement
from strictdoc.helpers.auto_described import auto_described
from strictdoc.server.error_object import ErrorObject

GENERAL_ERRORS_KEY = "_GENERAL_"


def column_input_key(column: str) -> str:
    """The form input key of a table column, e.g. `Short name` -> short_name."""
    return column.lower().replace(" ", "_")


@auto_described
class SysMLElementFormObject(ErrorObject):
    def __init__(
        self,
        *,
        node_mid: str,
        context_document_mid: str,
        source_hash: str,
        element_kind: str,
        details: Dict[str, str],
        rows: List[SysMLTableRow],
        source: str,
    ) -> None:
        super().__init__()
        self.node_mid: str = node_mid
        self.context_document_mid: str = context_document_mid
        self.source_hash: str = source_hash
        self.element_kind: str = element_kind
        self.details: Dict[str, str] = details
        self.rows: List[SysMLTableRow] = rows
        self.source: str = source
        self.details_columns: Tuple[str, ...] = editor.DETAILS_COLUMNS
        self.members_columns: Tuple[str, ...] = editor.MEMBERS_COLUMNS
        self.new_row_id: str = editor.NEW_ROW_ID

    @staticmethod
    def create_from_element(
        *,
        node_mid: str,
        context_document_mid: str,
        file_text: str,
        element: SysMLElement,
    ) -> "SysMLElementFormObject":
        return SysMLElementFormObject(
            node_mid=node_mid,
            context_document_mid=context_document_mid,
            source_hash=node_data.source_hash(file_text),
            element_kind=editor.declaration_kind(element),
            details=editor.details_values(element),
            rows=[
                SysMLTableRow(
                    row_id=str(index_), values=editor.member_values(member_)
                )
                for index_, member_ in enumerate(
                    editor.editable_members(element)
                )
            ],
            source=editor.element_source(file_text, element),
        )

    @staticmethod
    def create_from_request(
        request_form_data: FormData,
    ) -> "SysMLElementFormObject":
        def value_of(key: str) -> str:
            value = request_form_data.get(key, "")
            return value if isinstance(value, str) else ""

        details = {
            column_: value_of(f"details_{column_input_key(column_)}").strip()
            for column_ in editor.DETAILS_COLUMNS
        }

        row_ids = [
            str(value_) for value_ in request_form_data.getlist("member_row_id")
        ]
        deleted_flags = [
            str(value_)
            for value_ in request_form_data.getlist("member_deleted")
        ]
        column_values: Dict[str, List[str]] = {
            column_: [
                str(value_)
                for value_ in request_form_data.getlist(
                    f"member_{column_input_key(column_)}"
                )
            ]
            for column_ in editor.MEMBERS_COLUMNS
        }
        for column_, values_ in column_values.items():
            if len(values_) != len(row_ids) or len(deleted_flags) != len(
                row_ids
            ):
                raise AssertionError(
                    f"The MEMBERS form has inconsistent rows: {column_}."
                )
        rows = [
            SysMLTableRow(
                row_id=row_id_,
                values={
                    column_: values_[index_].strip()
                    for column_, values_ in column_values.items()
                },
                is_deleted=deleted_flags[index_] == "true",
            )
            for index_, row_id_ in enumerate(row_ids)
        ]

        return SysMLElementFormObject(
            node_mid=value_of("node_mid"),
            context_document_mid=value_of("context_document_mid"),
            source_hash=value_of("source_hash"),
            element_kind=value_of("element_kind"),
            details=details,
            rows=rows,
            source=editor.normalize_source(value_of("sysml_source")),
        )

    def column_input_key(self, column: str) -> str:
        return column_input_key(column)


@auto_described
class SysMLSourceFormObject(ErrorObject):
    def __init__(
        self,
        *,
        document_mid: str,
        source_hash: str,
        source: str,
    ) -> None:
        super().__init__()
        self.document_mid: str = document_mid
        self.source_hash: str = source_hash
        self.source: str = source

    @staticmethod
    def create_from_file_text(
        *, document_mid: str, file_text: str
    ) -> "SysMLSourceFormObject":
        return SysMLSourceFormObject(
            document_mid=document_mid,
            source_hash=node_data.source_hash(file_text),
            source=file_text,
        )

    @staticmethod
    def create_from_request(
        request_form_data: FormData,
    ) -> "SysMLSourceFormObject":
        def value_of(key: str) -> str:
            value = request_form_data.get(key, "")
            return value if isinstance(value, str) else ""

        return SysMLSourceFormObject(
            document_mid=value_of("document_mid"),
            source_hash=value_of("source_hash"),
            source=editor.normalize_source(value_of("sysml_source")) + "\n",
        )
