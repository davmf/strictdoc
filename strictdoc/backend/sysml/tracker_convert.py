"""
Converts a SysML model of one file per document to the tracker layout, one
file per item (see tracker.py).

Each document file (a file with one top-level package) becomes a tracker:

- the top-level package -> tracker `TRK-<PREFIX>`, titled by the package
  name, so the document keeps its title;
- a nested package -> folder `<PREFIX>-F-<TITLE>`, titled by the package
  name;
- an element of a package -> item, named by its short name, or
  `<PREFIX>-<name>` for a design element without one, or `<PREFIX>-<NNN>`
  for a requirement without one;
- the first doc comment of a package -> the doc of its tracker or folder;
- `dependency from A to B` and `satisfy R by A.b` -> the item of A, when A
  is an element of the same document. Otherwise the consecutive traces stay
  where they are, in a trace item `<PREFIX>-TRACES`;
- line notes and comments -> the item of the next element.

Every item gets the imports of its packages, with the names of converted
packages replaced by their tracker IDs, and an import of its own tracker,
which makes the other items visible as they were in the package. The text
of the elements and traces is copied as written, indented for the item
file. The tracker and folder files are written as SysMLTrackerWriter writes
them, so saving a document does not rewrite them.

The trackers are folders of the model directory, next to the model root
`MODEL.sysml`, as the workspace creates them. Libraries (the files of a
`library` or `_library` folder) are not converted. `_assets` folders move
with the document that uses them.

convert() works on texts and returns texts. main() converts a directory:

    python -m strictdoc.backend.sysml.tracker_convert model --title "Kettle"
"""

import argparse
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple, Union

from strictdoc.backend.sysml.model import (
    SysMLBlockComment,
    SysMLDependency,
    SysMLDocComment,
    SysMLElement,
    SysMLImport,
    SysMLLineNote,
    SysMLModel,
    SysMLPackage,
    SysMLSatisfy,
    SysMLSpan,
)
from strictdoc.backend.sysml.parser import SysMLParser
from strictdoc.backend.sysml.reader import is_requirements_model
from strictdoc.backend.sysml.writer import (
    _INDENT,
    _doc_block,
    _package_lines_text,
    _package_text,
    _quote_name,
)

MODEL_ROOT_ID = "MODEL"
MODEL_ROOT_FILE = f"{MODEL_ROOT_ID}.sysml"
WORKSPACE_LIBRARY_FILE = "StrictDocWorkspace.sysml"
WORKSPACE_LIBRARY_TEXT = """\
library package StrictDocWorkspace {
    private import ScalarValues::*;

    metadata def Model { attribute title : String; }
    metadata def Tracker { attribute title : String; attribute kind : String; attribute prefix : String; }
    metadata def Folder { attribute title : String; }
    metadata def DiagramView { attribute options : String; attribute plantuml : String; }
}
"""
LIBRARY_DIRECTORIES = ("library", "_library")
ASSETS_DIRECTORY = "_assets"

REQUIREMENTS_KIND = "requirements"
DESIGN_KIND = "design"
TEST_CASES_KIND = "test cases"
_KIND_ORDER = {
    REQUIREMENTS_KIND: 0,
    DESIGN_KIND: 1,
    "behaviour": 2,
    TEST_CASES_KIND: 3,
}

_PREFIX_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*$")
# An item ID is also a file name.
_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_NAME_SEGMENT_PATTERN = re.compile(r"'(?:[^'\\]|\\.)*'|[A-Za-z_][A-Za-z0-9_]*")


class ConversionError(Exception):
    pass


@dataclass
class TrackerPlan:
    """How one document file becomes a tracker."""

    source_path: str
    package_name: str
    tracker_id: str
    prefix: str
    kind: str


@dataclass
class ConversionResult:
    # The files of the tracker layout, by path relative to the model
    # directory: trackers, folders, items, the model root and, when the
    # model has none, the StrictDocWorkspace library.
    files: Dict[str, str]
    # The converted document files, relative to the model directory.
    removed: List[str]
    # (from, to) folders of images, relative to the model directory.
    asset_moves: List[Tuple[str, str]]
    plans: List[TrackerPlan]
    # The UID of each top-level design element whose UID changes from its
    # qualified name to its item ID.
    renamed_uids: Dict[str, str]
    # Requirements that had no short name, by their new item ID.
    numbered_requirements: List[str] = field(default_factory=list)


@dataclass
class _Item:
    item_id: str
    imports: List[str]
    # The comments before the element, and the element.
    element_texts: List[str]
    trace_texts: List[str] = field(default_factory=list)
    element: Optional[SysMLElement] = None
    # For a trace item: the client of each trace, the element it starts
    # from, or None.
    trace_clients: List[Optional[str]] = field(default_factory=list)


@dataclass
class _Folder:
    folder_id: str
    title: str
    doc: Optional[str]
    children: List[Union["_Folder", _Item]] = field(default_factory=list)


@dataclass
class _Document:
    plan: TrackerPlan
    model: SysMLModel
    package: SysMLPackage
    is_requirements: bool
    data: bytes


def is_library_path(path: str) -> bool:
    return any(
        part_ in LIBRARY_DIRECTORIES
        for part_ in path.replace("\\", "/").split("/")
    )


def convert(
    sources: Dict[str, str],
    model_title: str,
    overrides: Optional[Dict[str, Dict[str, str]]] = None,
    tracker_ids: Optional[Dict[str, str]] = None,
) -> ConversionResult:
    """
    Convert the files of a model directory, given as {relative path: text}.

    overrides sets the tracker ID, prefix or kind of a document:
    {"requirements/system.sysml": {"prefix": "SYS", "kind": "requirements"}}.

    tracker_ids gives the tracker ID of packages that are trackers already,
    by package name, so that the imports of the converted files name the
    trackers: {"Stakeholder requirements": "TRK-STK"}.
    """
    overrides = dict(overrides or {})
    documents: List[_Document] = []
    for path_ in sorted(sources):
        if not path_.endswith(".sysml") or is_library_path(path_):
            continue
        model = SysMLParser.parse_string(sources[path_], path_)
        package = _single_package(model, path_)
        documents.append(
            _Document(
                plan=TrackerPlan(
                    source_path=path_,
                    package_name=_package_name(package, path_),
                    tracker_id="",
                    prefix="",
                    kind="",
                ),
                model=model,
                package=package,
                is_requirements=is_requirements_model(model),
                data=sources[path_].encode("utf-8"),
            )
        )
    unknown = set(overrides) - {d_.plan.source_path for d_ in documents}
    if len(unknown) > 0:
        raise ConversionError(
            "Overrides for files that are not documents: "
            + ", ".join(sorted(unknown))
        )
    _plan_trackers(documents, overrides)

    tracker_ids = {
        **(tracker_ids or {}),
        **{
            document_.plan.package_name: document_.plan.tracker_id
            for document_ in documents
        },
    }
    used_ids: Set[str] = {MODEL_ROOT_ID} | set(tracker_ids.values())
    for document_ in documents:
        used_ids.update(_short_names(document_.package))

    result = ConversionResult(
        files={}, removed=[], asset_moves=[], plans=[], renamed_uids={}
    )
    for document_ in documents:
        converter = _DocumentConverter(document_, tracker_ids, used_ids, result)
        converter.convert()
        result.removed.append(document_.plan.source_path)
        result.plans.append(document_.plan)
        if f"{ASSETS_DIRECTORY}/" in sources[document_.plan.source_path]:
            source_directory = os.path.dirname(document_.plan.source_path)
            result.asset_moves.append(
                (
                    _join(source_directory, ASSETS_DIRECTORY),
                    _join(document_.plan.tracker_id, ASSETS_DIRECTORY),
                )
            )

    # The model root lists requirements first, then design, then tests.
    ordered = sorted(
        documents,
        key=lambda document_: (
            _KIND_ORDER.get(document_.plan.kind, len(_KIND_ORDER)),
            document_.plan.source_path,
        ),
    )
    result.files[MODEL_ROOT_FILE] = _model_root_text(
        model_title, [d_.plan.tracker_id for d_ in ordered]
    )
    if not any(
        re.search(r"\bpackage\s+'?StrictDocWorkspace'?\s*\{", text_)
        for path_, text_ in sources.items()
        if is_library_path(path_)
    ):
        result.files[_join("library", WORKSPACE_LIBRARY_FILE)] = (
            WORKSPACE_LIBRARY_TEXT
        )
    return result


class _DocumentConverter:
    def __init__(
        self,
        document: _Document,
        tracker_ids: Dict[str, str],
        used_ids: Set[str],
        result: ConversionResult,
    ) -> None:
        self.document: _Document = document
        self.plan: TrackerPlan = document.plan
        self.tracker_ids: Dict[str, str] = tracker_ids
        self.used_ids: Set[str] = used_ids
        self.result: ConversionResult = result
        self.self_import: str = (
            f"private import {_quote_name(self.plan.tracker_id)}::*;"
        )
        # The item of each element of the document, by name and short name,
        # for the traces.
        self.items_by_name: Dict[str, _Item] = {}

    def convert(self) -> None:
        package = self.document.package
        self._check_gaps(package)
        root = _Folder(
            folder_id=self.plan.tracker_id,
            title=self.plan.package_name,
            doc=self._doc(package),
        )
        self._convert_package(package, root, inherited_imports=[])
        self._place_traces(root)
        directory = self.plan.tracker_id
        files = self.result.files

        def write(child: Union[_Folder, _Item]) -> None:
            if isinstance(child, _Folder):
                files[_join(directory, f"{child.folder_id}.sysml")] = (
                    _container_text(
                        child.folder_id,
                        f"@StrictDocWorkspace::Folder {{ title = "
                        f"{_sysml_string(child.title)}; }}",
                        child,
                    )
                )
                for grandchild_ in child.children:
                    write(grandchild_)
            else:
                files[_join(directory, f"{child.item_id}.sysml")] = _item_text(
                    child
                )

        files[_join(directory, f"{self.plan.tracker_id}.sysml")] = (
            _container_text(
                self.plan.tracker_id,
                "@StrictDocWorkspace::Tracker { title = "
                f"{_sysml_string(self.plan.package_name)}; kind = "
                f"{_sysml_string(self.plan.kind)}; prefix = "
                f"{_sysml_string(self.plan.prefix)}; }}",
                root,
            )
        )
        for child_ in root.children:
            write(child_)

    def _convert_package(
        self,
        package: SysMLPackage,
        folder: _Folder,
        inherited_imports: List[str],
    ) -> None:
        imports = list(inherited_imports)
        for member_ in package.members:
            if isinstance(member_, SysMLImport):
                imports.append(self._import_text(member_))
        imports = list(dict.fromkeys(imports))
        item_imports = list(dict.fromkeys([*imports, self.self_import]))

        pending_comments: List[str] = []
        first_doc_seen = False
        # Traces not yet placed: (trace member, its text, the item that holds
        # it for now).
        for member_ in package.members:
            if isinstance(member_, SysMLImport):
                continue
            if isinstance(member_, SysMLDocComment):
                if first_doc_seen or member_.name is not None:
                    raise self._error(
                        member_.span,
                        "only the first doc comment of a package can be "
                        "converted; it becomes the doc of the tracker or "
                        "folder",
                    )
                first_doc_seen = True
                continue
            if isinstance(member_, (SysMLLineNote, SysMLBlockComment)):
                pending_comments.append(self._text(member_.span))
                continue
            if isinstance(member_, SysMLPackage):
                if member_.short_name is not None:
                    raise self._error(
                        member_.span,
                        "a package with a short name cannot become a folder",
                    )
                self._check_gaps(member_)
                if len(pending_comments) > 0:
                    raise self._error(
                        member_.span,
                        "a comment before a package cannot be converted",
                    )
                title = _package_name(member_, self.plan.source_path)
                child = _Folder(
                    folder_id=self._new_id(
                        f"{self.plan.prefix}-F-{_slug(title) or 'FOLDER'}"
                    ),
                    title=title,
                    doc=self._doc(member_),
                )
                folder.children.append(child)
                self._convert_package(member_, child, imports)
                continue
            if isinstance(member_, SysMLElement):
                item = _Item(
                    item_id=self._item_id(member_),
                    imports=item_imports,
                    element_texts=[
                        *pending_comments,
                        self._text(member_.member_span or member_.span),
                    ],
                    element=member_,
                )
                pending_comments = []
                folder.children.append(item)
                for name_ in (member_.name, member_.short_name):
                    if name_ is not None:
                        self.items_by_name.setdefault(name_, item)
                continue
            if isinstance(member_, (SysMLDependency, SysMLSatisfy)):
                text = "\n".join([*pending_comments, self._text(member_.span)])
                pending_comments = []
                previous = folder.children[-1] if folder.children else None
                if not (
                    isinstance(previous, _Item) and previous.element is None
                ):
                    previous = _Item(
                        item_id="", imports=item_imports, element_texts=[]
                    )
                    folder.children.append(previous)
                previous.trace_texts.append(text)
                previous.trace_clients.append(_trace_client(member_))
                continue
            raise self._error(
                getattr(member_, "span", package.span),
                f"a {type(member_).__name__.replace('SysML', '').lower()} "
                "in a package cannot be converted",
            )
        if len(pending_comments) > 0:
            last_item = next(
                (
                    child_
                    for child_ in reversed(folder.children)
                    if isinstance(child_, _Item)
                ),
                None,
            )
            if last_item is None:
                raise self._error(
                    package.span,
                    "a comment in a package without elements cannot be "
                    "converted",
                )
            if last_item.element is not None:
                last_item.element_texts.extend(pending_comments)
            else:
                last_item.trace_texts.extend(pending_comments)

    def _place_traces(self, folder: _Folder) -> None:
        """
        Move each trace of a trace item into the item of its client, when
        the client is an element of the document. Trace items that keep
        traces get an ID.
        """
        kept: List[Union[_Folder, _Item]] = []
        for child_ in folder.children:
            if isinstance(child_, _Folder):
                self._place_traces(child_)
                kept.append(child_)
                continue
            if child_.element is not None:
                kept.append(child_)
                continue
            remaining: List[str] = []
            for text_, client in zip(child_.trace_texts, child_.trace_clients):
                target_item = (
                    self.items_by_name.get(client)
                    if client is not None
                    else None
                )
                if target_item is not None:
                    target_item.trace_texts.append(text_)
                else:
                    remaining.append(text_)
            if len(remaining) > 0 and self.document.is_requirements:
                # The writer writes a dependency with its client
                # requirement, and would drop a trace item.
                raise ConversionError(
                    f"{self.plan.source_path}: a trace starts from an "
                    "element that is not in this document: "
                    + remaining[0].strip()
                )
            if len(remaining) > 0:
                child_.trace_texts = remaining
                child_.item_id = self._new_id(f"{self.plan.prefix}-TRACES")
                kept.append(child_)
        folder.children = kept

    def _item_id(self, element: SysMLElement) -> str:
        if element.short_name is not None:
            if _ID_PATTERN.match(element.short_name) is None:
                raise self._error(
                    element.span,
                    f"the short name '{element.short_name}' cannot be a "
                    "file name",
                )
            return element.short_name
        if element.kind == "requirement" and not element.is_definition:
            item_id = self._numbered_id()
            self.result.numbered_requirements.append(item_id)
            return item_id
        if element.name is None:
            return self._numbered_id()
        item_id = self._new_id(
            f"{self.plan.prefix}-{_slug(element.name, upper=False)}"
        )
        self.result.renamed_uids[
            f"{self.plan.package_name}::{element.name}"
        ] = item_id
        return item_id

    def _numbered_id(self) -> str:
        pattern = re.compile(re.escape(self.plan.prefix) + r"-(\d+)$")
        highest = max(
            (
                int(match_.group(1))
                for match_ in (pattern.match(id_) for id_ in self.used_ids)
                if match_ is not None
            ),
            default=0,
        )
        return self._new_id(f"{self.plan.prefix}-{highest + 1:03d}")

    def _new_id(self, base_id: str) -> str:
        """
        base_id, or base_id-N. IDs are file names, so two IDs must differ in
        more than case: Windows and macOS would see one file.
        """
        used = {id_.lower() for id_ in self.used_ids}
        new_id = base_id
        counter = 2
        while new_id.lower() in used:
            new_id = f"{base_id}-{counter}"
            counter += 1
        self.used_ids.add(new_id)
        return new_id

    def _import_text(self, member: SysMLImport) -> str:
        target = member.target.strip()
        match = _NAME_SEGMENT_PATTERN.match(target)
        if match is not None:
            first = _unquote(match.group(0))
            if first in self.tracker_ids:
                rest = target[match.end() :].strip()
                if re.match(r"^(::\s*\*\*?)?$", rest) is None:
                    raise self._error(
                        member.span,
                        f"the import '{target}' names a member of a package "
                        "that becomes a tracker",
                    )
                target = _quote_name(self.tracker_ids[first]) + rest.replace(
                    " ", ""
                )
        visibility = f"{member.visibility} " if member.visibility else ""
        return f"{visibility}import {target};"

    def _doc(self, package: SysMLPackage) -> Optional[str]:
        for member_ in package.members:
            if isinstance(member_, SysMLDocComment):
                return member_.text
        return None

    def _text(self, span: SysMLSpan) -> str:
        """The text of a span, indented for an item file."""
        text = self.document.data[span.byte_start : span.byte_end].decode(
            "utf-8"
        )
        base = span.col_start - 1
        lines = text.split("\n")
        result = [_INDENT + lines[0].rstrip()]
        for index_, line_ in enumerate(lines[1:], start=span.line_start + 1):
            if line_.strip() == "":
                result.append("")
            elif line_[:base].strip() == "":
                result.append(_INDENT + line_[base:].rstrip())
            else:
                raise ConversionError(
                    f"{self.plan.source_path}, line {index_}: the line is "
                    "indented less than the start of its element, so it "
                    "cannot be moved to an item file as it is."
                )
        return "\n".join(result)

    def _check_gaps(self, package: SysMLPackage) -> None:
        """
        Only white space between the members of the package: otherwise a
        span does not cover its member, and text would be lost.
        """
        data = self.document.data
        open_brace = data.index(b"{", package.span.byte_start)
        position = open_brace + 1
        for member_ in package.members:
            span = getattr(member_, "member_span", None) or member_.span
            gap = data[position : span.byte_start]
            if gap.strip() != b"":
                raise self._error(
                    span,
                    "text between members was not read: "
                    f"{gap.decode('utf-8').strip()[:60]!r}",
                )
            position = span.byte_end
        gap = data[position : package.span.byte_end].strip()
        if gap != b"}":
            raise self._error(
                package.span,
                f"text at the end of the package was not read: {gap[:60]!r}",
            )

    def _error(self, span: SysMLSpan, message: str) -> ConversionError:
        return ConversionError(
            f"{self.plan.source_path}, line {span.line_start}: {message}."
        )


def _plan_trackers(
    documents: List[_Document], overrides: Dict[str, Dict[str, str]]
) -> None:
    used_prefixes: Set[str] = set()
    # Overrides first, so that an automatic prefix does not take theirs.
    for document_ in documents:
        prefix = overrides.get(document_.plan.source_path, {}).get("prefix")
        if prefix is not None:
            if prefix in used_prefixes:
                raise ConversionError(f"The prefix {prefix} is used twice.")
            used_prefixes.add(prefix)
    for document_ in documents:
        override = overrides.get(document_.plan.source_path, {})
        plan = document_.plan
        plan.prefix = override.get("prefix") or _automatic_prefix(
            document_, used_prefixes
        )
        if _PREFIX_PATTERN.match(plan.prefix) is None:
            raise ConversionError(
                f"{plan.source_path}: the prefix '{plan.prefix}' is not "
                "upper-case letters and digits, starting with a letter."
            )
        used_prefixes.add(plan.prefix)
        plan.tracker_id = override.get("tracker_id") or f"TRK-{plan.prefix}"
        plan.kind = override.get("kind") or _automatic_kind(document_)


def _automatic_prefix(document: _Document, used: Set[str]) -> str:
    """
    The leading letter segments that the short names of the document share
    (SYS for SYS-THR-001 and SYS-TAT-001), else the initials of the title.
    """
    segment_lists = [
        _leading_letter_segments(short_name_)
        for short_name_ in _short_names(document.package)
    ]
    segment_lists = [list_ for list_ in segment_lists if len(list_) > 0]
    candidates: List[str] = []
    if len(segment_lists) > 0:
        common = segment_lists[0]
        for list_ in segment_lists[1:]:
            length = 0
            while (
                length < min(len(common), len(list_))
                and common[length] == list_[length]
            ):
                length += 1
            common = common[:length]
        if len(common) > 0:
            candidates.append(common[0])
            if len(common) > 1:
                candidates.append("".join(common[:2]))
    words = re.findall(
        r"[A-Za-z][a-z]*|[A-Z]+(?![a-z])", document.plan.package_name
    )
    initials = "".join(word_[0] for word_ in words).upper()
    if len(initials) > 0:
        candidates.append(initials)
    candidates.append("TRK")
    for candidate_ in candidates:
        if candidate_ not in used:
            return candidate_
    counter = 2
    while f"{candidates[0]}{counter}" in used:
        counter += 1
    return f"{candidates[0]}{counter}"


def _automatic_kind(document: _Document) -> str:
    if document.is_requirements:
        return REQUIREMENTS_KIND
    elements = _elements(document.package)
    verifications = [e_ for e_ in elements if e_.kind == "verification"]
    if len(elements) > 0 and len(verifications) * 2 > len(elements):
        return TEST_CASES_KIND
    return DESIGN_KIND


def _elements(package: SysMLPackage) -> List[SysMLElement]:
    result: List[SysMLElement] = []
    for member_ in package.members:
        if isinstance(member_, SysMLPackage):
            result.extend(_elements(member_))
        elif isinstance(member_, SysMLElement):
            result.append(member_)
    return result


def _short_names(package: SysMLPackage) -> List[str]:
    return [
        element_.short_name
        for element_ in _elements(package)
        if element_.short_name is not None
    ]


def _leading_letter_segments(short_name: str) -> List[str]:
    segments: List[str] = []
    for segment_ in short_name.split("-"):
        if (
            re.match(r"^[A-Z][A-Z0-9]*$", segment_) is None
            or segment_.isdigit()
        ):
            break
        if re.search(r"\d", segment_) is not None:
            break
        segments.append(segment_)
    return segments


def _trace_client(
    member: Union[SysMLDependency, SysMLSatisfy],
) -> Optional[str]:
    """
    The element a trace starts from: A of `dependency from A to B` and of
    `satisfy R by A.b`.
    """
    # The parser gives the names unquoted: `'SYS-1'` is SYS-1.
    if isinstance(member, SysMLDependency):
        if len(member.sources) == 0:
            return None
        # A qualified name names its last segment.
        return member.sources[0].split("::")[-1].strip()
    if len(member.by_path) > 0:
        # A feature chain starts from an element.
        return member.by_path[0].strip()
    return None


def _container_text(package_id: str, metadata: str, folder: _Folder) -> str:
    head_lines = [_INDENT + metadata]
    if folder.doc is not None:
        head_lines.extend(_doc_block(folder.doc, _INDENT))
    return _package_text(
        package_id,
        head_lines,
        [
            child_.folder_id if isinstance(child_, _Folder) else child_.item_id
            for child_ in folder.children
        ],
    )


def _item_text(item: _Item) -> str:
    blocks = []
    if len(item.imports) > 0:
        blocks.append("\n".join(_INDENT + import_ for import_ in item.imports))
    if len(item.element_texts) > 0:
        blocks.append("\n".join(item.element_texts))
    if len(item.trace_texts) > 0:
        blocks.append("\n".join(item.trace_texts))
    return _package_lines_text(item.item_id, blocks)


def _model_root_text(title: str, tracker_ids: Sequence[str]) -> str:
    lines = [
        f"package {_quote_name(MODEL_ROOT_ID)} {{",
        f"{_INDENT}@StrictDocWorkspace::Model {{ title = {_sysml_string(title)}; }}",
        "",
    ]
    lines.extend(
        f"{_INDENT}public import {_quote_name(id_)};" for id_ in tracker_ids
    )
    lines.append("}")
    return "\n".join(lines) + "\n"


def _single_package(model: SysMLModel, path: str) -> SysMLPackage:
    packages = [m_ for m_ in model.members if isinstance(m_, SysMLPackage)]
    others = [
        m_
        for m_ in model.members
        if not isinstance(m_, (SysMLPackage, SysMLLineNote, SysMLBlockComment))
    ]
    if len(packages) != 1 or len(others) > 0:
        raise ConversionError(
            f"{path}: a document file must hold one top-level package and "
            "nothing else."
        )
    if len(model.members) != 1:
        raise ConversionError(
            f"{path}: comments outside the top-level package cannot be "
            "converted."
        )
    return packages[0]


def _package_name(package: SysMLPackage, path: str) -> str:
    if package.name is None:
        raise ConversionError(
            f"{path}, line {package.span.line_start}: a package has no name."
        )
    return package.name


def _slug(title: str, upper: bool = True) -> str:
    """As the writer makes the IDs of new folders."""
    slug = re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-")
    return slug.upper() if upper else slug


def _sysml_string(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _unquote(name: str) -> str:
    if len(name) >= 2 and name[0] == "'" and name[-1] == "'":
        return name[1:-1].replace("\\'", "'")
    return name


def _join(*parts: str) -> str:
    return "/".join(part_ for part_ in parts if len(part_) > 0)


def read_sources(model_directory: str) -> Dict[str, str]:
    sources: Dict[str, str] = {}
    for directory_, directories_, files_ in os.walk(model_directory):
        directories_[:] = sorted(
            d_ for d_ in directories_ if not d_.startswith(".")
        )
        for file_ in sorted(files_):
            if file_.endswith(".sysml"):
                path = os.path.join(directory_, file_)
                with open(path, encoding="utf-8") as stream_:
                    sources[
                        os.path.relpath(path, model_directory).replace(
                            os.sep, "/"
                        )
                    ] = stream_.read()
    return sources


def write_result(model_directory: str, result: ConversionResult) -> None:
    """Write the files, move the images and delete the converted files."""
    for path_, text_ in result.files.items():
        full_path = os.path.join(model_directory, path_)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8", newline="") as stream_:
            stream_.write(text_)
    moved_from: Set[str] = set()
    for from_, to_ in result.asset_moves:
        source = os.path.join(model_directory, from_)
        if not os.path.isdir(source):
            continue
        shutil.copytree(
            source, os.path.join(model_directory, to_), dirs_exist_ok=True
        )
        moved_from.add(source)
    for path_ in result.removed:
        os.remove(os.path.join(model_directory, path_))
    for source_ in moved_from:
        shutil.rmtree(source_)
    for directory_, _, _ in sorted(
        os.walk(model_directory), key=lambda entry_: -len(entry_[0])
    ):
        if directory_ != model_directory and len(os.listdir(directory_)) == 0:
            os.rmdir(directory_)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert a SysML model to the tracker layout."
    )
    parser.add_argument("model_directory")
    parser.add_argument("--title", required=True, help="The model title.")
    parser.add_argument(
        "--overrides",
        help="A JSON file: {document path: {prefix, tracker_id, kind}}.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the plan and write nothing.",
    )
    arguments = parser.parse_args(argv)
    overrides = None
    if arguments.overrides is not None:
        with open(arguments.overrides, encoding="utf-8") as stream_:
            overrides = json.load(stream_)
    try:
        result = convert(
            read_sources(arguments.model_directory),
            model_title=arguments.title,
            overrides=overrides,
        )
    except ConversionError as error_:
        print(f"error: {error_}", file=sys.stderr)  # noqa: T201
        return 1
    for plan_ in result.plans:
        print(  # noqa: T201
            f"{plan_.source_path} -> {plan_.tracker_id} "
            f"(prefix {plan_.prefix}, {plan_.kind}): {plan_.package_name}"
        )
    print(  # noqa: T201
        f"{len(result.files)} files, {len(result.renamed_uids)} design "
        f"UIDs renamed, {len(result.numbered_requirements)} requirements "
        "numbered."
    )
    if not arguments.dry_run:
        write_result(arguments.model_directory, result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
