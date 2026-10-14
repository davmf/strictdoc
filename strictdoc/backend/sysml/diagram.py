"""
Builds a Mermaid flowchart that shows the content of a SysML v2 file.

The flowchart follows the SysML v2 graphical notation where Mermaid allows
it. The reader builds it from the parsed model every time a file is read, so
the diagram always matches the file.

- package -> box with the «package» keyword. The top-level package of a
  file is the document itself and has no box, since the page title already
  names it.
- definition (`part def`, `action def`, ...) -> box with square corners
- usage (`part`, `action`, `requirement`, ...) -> box with rounded corners
- an element or package with drawn members -> a box that nests them,
  titled with the keyword and the name only, since Mermaid draws a title
  of more than one line over the members. The rest of the label is a
  compartment box inside it.
- attribute -> a line in the box of its owner, except for requirements
- `decide` and `merge` -> diamond, `fork` and `join` -> bar,
  `start` -> filled circle, `done` -> framed circle
- `first A then B`, `then`, `if ... then`, `else` -> solid arrow
- `satisfy`, `verify`, `allocate`, `perform`, `dependency` -> dashed arrow
  labelled with the keyword
- typing (`:`) or specialization of a definition (`:>`) by a definition in
  the same file -> dashed arrow labelled «defined by» or «specializes»

A reference that does not resolve in the file, such as a requirement in
another file, is drawn as a box with a dashed border.
"""

import html
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, Union

from strictdoc.backend.sysml.model import (
    SysMLAllocate,
    SysMLAttribute,
    SysMLBehaviourControl,
    SysMLDependency,
    SysMLElement,
    SysMLElseThen,
    SysMLIfThen,
    SysMLMember,
    SysMLModel,
    SysMLPackage,
    SysMLPerform,
    SysMLSatisfy,
    SysMLSuccession,
    SysMLThen,
    SysMLVerify,
)

# Elements that are not drawn. Their members are drawn as members of the
# owner, so `objective { verify R; }` is a verify arrow from the owner.
TRANSPARENT_KINDS = {"objective"}

MAX_LINE_LENGTH = 60

# Mermaid wraps labels at 200 pixels by default, and clips a box title that
# does not fit.
WRAPPING_WIDTH = 400

CONTROL_SHAPES = {
    "decide": "diam",
    "merge": "diam",
    "fork": "fork",
    "join": "fork",
}


def create_mermaid_diagram(model: SysMLModel) -> Optional[str]:
    """
    Return the Mermaid source of the diagram, or None when the file has
    nothing to draw.
    """
    builder = _DiagramBuilder()
    packages = [
        member_
        for member_ in model.members
        if isinstance(member_, SysMLPackage)
    ]
    if len(packages) == 1 and packages[0].name is not None:
        builder.add_members(
            packages[0].members,
            builder.root_boxes,
            scope=[packages[0].name],
            owner_id=None,
        )
    else:
        builder.add_members(
            model.members, builder.root_boxes, scope=[], owner_id=None
        )
    if len(builder.root_boxes) == 0:
        return None
    return builder.render()


def as_rst_raw_html(diagram_source: str) -> str:
    """Wrap Mermaid source into an RST raw HTML block for the page."""
    escaped_lines = html.escape(diagram_source, quote=False).splitlines()
    lines = [
        ".. raw:: html",
        "",
        '    <pre class="mermaid">',
        *[f"    {line_}" for line_ in escaped_lines],
        "    </pre>",
    ]
    return "\n".join(lines)


@dataclass
class _Box:
    box_id: str
    # The title of the box when it nests other boxes.
    title: str
    lines: List[str]
    # "definition", "usage", "control", "start" or "done".
    shape: str
    control_kind: Optional[str] = None
    children: List["_Box"] = field(default_factory=list)


@dataclass
class _Edge:
    source_id: str
    target_id: str
    label: Optional[str]
    is_dashed: bool


@dataclass
class _PendingEdge:
    """
    An edge whose ends are resolved after all boxes exist, since a
    reference can name a box that is declared later in the file.

    Each end is a box, a requirement name, or a path of names.
    """

    label: Optional[str]
    is_dashed: bool
    scope: List[str]
    source_id: Optional[str] = None
    source_requirement: Optional[str] = None
    source_path: List[str] = field(default_factory=list)
    target_id: Optional[str] = None
    target_requirement: Optional[str] = None
    target_path: List[str] = field(default_factory=list)


class _DiagramBuilder:
    def __init__(self) -> None:
        self.root_boxes: List[_Box] = []
        self.external_boxes: Dict[str, _Box] = {}
        self.pending_edges: List[_PendingEdge] = []
        # (box id, definition name, label) for typing and specialization.
        self.pending_definition_edges: List[Tuple[str, str, str]] = []
        # Qualified name segments of every named box, in file order.
        self.box_paths: List[Tuple[List[str], str]] = []
        self.definition_ids: Dict[str, str] = {}
        self.requirement_ids: Dict[str, str] = {}
        self.box_count = 0

    def add_members(
        self,
        members: List[SysMLMember],
        boxes: List[_Box],
        scope: List[str],
        owner_id: Optional[str],
    ) -> None:
        # The source of `then X;`, `if ... then X;` and `else X;`.
        previous_id: Optional[str] = None
        for member_ in members:
            if isinstance(member_, SysMLPackage):
                boxes.append(self._add_package(member_, scope))
            elif isinstance(member_, SysMLElement):
                if member_.kind in TRANSPARENT_KINDS:
                    self.add_members(
                        member_.members, boxes, scope=scope, owner_id=owner_id
                    )
                    continue
                box = self._add_element(member_, scope)
                boxes.append(box)
                previous_id = box.box_id
            elif isinstance(member_, SysMLBehaviourControl):
                box = self._new_box(
                    [member_.name or member_.kind], shape="control"
                )
                box.control_kind = member_.kind
                if member_.name is not None:
                    self.box_paths.append((scope + [member_.name], box.box_id))
                boxes.append(box)
                previous_id = box.box_id
            elif isinstance(member_, SysMLSuccession):
                self.pending_edges.append(
                    _PendingEdge(
                        label=(
                            f"[{member_.guard_text}]"
                            if member_.guard_text is not None
                            else None
                        ),
                        is_dashed=False,
                        scope=scope,
                        source_id=self._pseudo_state_id(
                            member_.first_path, boxes, "start"
                        ),
                        source_path=member_.first_path,
                        target_id=self._pseudo_state_id(
                            member_.then_path, boxes, "done"
                        ),
                        target_path=member_.then_path,
                    )
                )
            elif isinstance(member_, (SysMLThen, SysMLIfThen, SysMLElseThen)):
                if previous_id is None:
                    continue
                self.pending_edges.append(
                    _PendingEdge(
                        label=_transition_label(member_),
                        is_dashed=False,
                        scope=scope,
                        source_id=previous_id,
                        target_id=self._pseudo_state_id(
                            member_.target_path, boxes, "done"
                        ),
                        target_path=member_.target_path,
                    )
                )
            elif isinstance(member_, SysMLSatisfy):
                if member_.by is None and owner_id is None:
                    continue
                self.pending_edges.append(
                    _PendingEdge(
                        label="«satisfy»",
                        is_dashed=True,
                        scope=scope,
                        source_id=owner_id if member_.by is None else None,
                        source_path=member_.by_path,
                        target_requirement=member_.requirement,
                    )
                )
            elif isinstance(member_, (SysMLVerify, SysMLPerform)):
                if owner_id is None:
                    continue
                is_verify = isinstance(member_, SysMLVerify)
                self.pending_edges.append(
                    _PendingEdge(
                        label="«verify»" if is_verify else "«perform»",
                        is_dashed=True,
                        scope=scope,
                        source_id=owner_id,
                        target_requirement=(
                            member_.requirement
                            if isinstance(member_, SysMLVerify)
                            else None
                        ),
                        target_path=(
                            member_.target_path
                            if isinstance(member_, SysMLPerform)
                            else []
                        ),
                    )
                )
            elif isinstance(member_, SysMLAllocate):
                self.pending_edges.append(
                    _PendingEdge(
                        label="«allocate»",
                        is_dashed=True,
                        scope=scope,
                        source_path=member_.source_path,
                        target_path=member_.target_path,
                    )
                )
            elif isinstance(member_, SysMLDependency):
                label = (
                    "«derive»"
                    if "derivation" in member_.annotations
                    else "«dependency»"
                )
                for source_ in member_.sources:
                    for target_ in member_.targets:
                        self.pending_edges.append(
                            _PendingEdge(
                                label=label,
                                is_dashed=True,
                                scope=scope,
                                source_requirement=source_,
                                target_requirement=target_,
                            )
                        )

    def render(self) -> str:
        edges = self._resolve_edges()
        lines = [
            '%%{init: {"flowchart": {"wrappingWidth": '
            + str(WRAPPING_WIDTH)
            + "}}}%%",
            "flowchart LR",
        ]
        for box_ in self.root_boxes:
            lines.extend(_render_box(box_, indent_level=1))
        for box_ in self.external_boxes.values():
            lines.extend(_render_box(box_, indent_level=1))
        seen_edges: Set[Tuple[str, str, Optional[str], bool]] = set()
        for edge_ in edges:
            key = (
                edge_.source_id,
                edge_.target_id,
                edge_.label,
                edge_.is_dashed,
            )
            if key in seen_edges:
                continue
            seen_edges.add(key)
            arrow = "-.->" if edge_.is_dashed else "-->"
            if edge_.label is not None:
                arrow += f'|"{_escape_label(edge_.label)}"|'
            lines.append(f"  {edge_.source_id} {arrow} {edge_.target_id}")
        if len(self.external_boxes) > 0:
            lines.append("  classDef external stroke-dasharray: 5 5")
            external_ids = ",".join(
                box_.box_id for box_ in self.external_boxes.values()
            )
            lines.append(f"  class {external_ids} external")
        return "\n".join(lines)

    def _new_box(self, lines: List[str], shape: str, title: str = "") -> _Box:
        self.box_count += 1
        return _Box(
            box_id=f"n{self.box_count}",
            title=title,
            lines=[line_ for line_ in lines if len(line_) > 0],
            shape=shape,
        )

    def _add_package(self, package: SysMLPackage, scope: List[str]) -> _Box:
        box = self._new_box(
            ["«package»", package.name or ""],
            shape="definition",
            title=f"«package» {package.name or ''}".strip(),
        )
        child_scope = scope
        if package.name is not None:
            child_scope = scope + [package.name]
            self.box_paths.append((child_scope, box.box_id))
        self.add_members(
            package.members,
            box.children,
            scope=child_scope,
            owner_id=box.box_id,
        )
        return box

    def _add_element(self, element: SysMLElement, scope: List[str]) -> _Box:
        keyword = " ".join(
            [
                *element.modifiers,
                f"{element.kind} def"
                if element.is_definition
                else element.kind,
            ]
        )
        lines = [f"«{keyword}»", _feature_text(element)]
        if element.kind != "requirement":
            for member_ in element.members:
                if isinstance(member_, SysMLAttribute):
                    lines.append(_feature_text(member_))
        display_name = element.name
        if display_name is None and len(element.redefines) > 0:
            display_name = _last_segment(element.redefines[0])
        box = self._new_box(
            lines,
            shape="definition" if element.is_definition else "usage",
            title=f"«{keyword}» {display_name or ''}".strip(),
        )
        child_scope = scope
        if display_name is not None:
            child_scope = scope + [display_name]
            self.box_paths.append((child_scope, box.box_id))
        if element.is_definition and element.name is not None:
            self.definition_ids.setdefault(element.name, box.box_id)
        if element.kind == "requirement":
            for name_ in (element.short_name, element.name):
                if name_ is not None:
                    self.requirement_ids.setdefault(name_, box.box_id)

        for specialization_ in element.specializations:
            if specialization_.operator == ":":
                label = "«defined by»"
            elif element.is_definition and specialization_.operator in (
                ":>",
                "subsets",
            ):
                label = "«specializes»"
            else:
                continue
            for target_ in specialization_.targets:
                self.pending_definition_edges.append(
                    (box.box_id, _last_segment(target_), label)
                )

        self.add_members(
            element.members,
            box.children,
            scope=child_scope,
            owner_id=box.box_id,
        )
        return box

    def _pseudo_state_id(
        self, path: List[str], boxes: List[_Box], pseudo_state: str
    ) -> Optional[str]:
        """
        Return the box of `start` or `done` in this body, creating it on
        first use, or None for any other path.
        """
        if path != [pseudo_state]:
            return None
        for box_ in boxes:
            if box_.shape == pseudo_state:
                return box_.box_id
        box = self._new_box([], shape=pseudo_state)
        boxes.append(box)
        return box.box_id

    def _resolve_edges(self) -> List[_Edge]:
        edges: List[_Edge] = []
        for pending_ in self.pending_edges:
            edges.append(
                _Edge(
                    source_id=self._resolve_end(
                        pending_.source_id,
                        pending_.source_requirement,
                        pending_.source_path,
                        pending_.scope,
                    ),
                    target_id=self._resolve_end(
                        pending_.target_id,
                        pending_.target_requirement,
                        pending_.target_path,
                        pending_.scope,
                    ),
                    label=pending_.label,
                    is_dashed=pending_.is_dashed,
                )
            )
        for source_id_, name_, label_ in self.pending_definition_edges:
            target_id = self.definition_ids.get(name_)
            if target_id is not None and target_id != source_id_:
                edges.append(
                    _Edge(
                        source_id=source_id_,
                        target_id=target_id,
                        label=label_,
                        is_dashed=True,
                    )
                )
        return edges

    def _resolve_end(
        self,
        box_id: Optional[str],
        requirement: Optional[str],
        path: List[str],
        scope: List[str],
    ) -> str:
        if box_id is not None:
            return box_id
        if requirement is not None:
            return self._resolve_requirement(requirement)
        return self._resolve_path(path, scope)

    def _resolve_path(self, path: List[str], scope: List[str]) -> str:
        """
        Return the box of a reference, or an external box.

        The names of the enclosing scopes are tried first, from the
        innermost one. Then the longest prefix of the path is matched
        against the end of the qualified names, in the same way as the
        reader resolves satisfy paths.
        """
        for length_ in range(len(scope), -1, -1):
            candidate = scope[:length_] + path
            for segments_, box_id_ in self.box_paths:
                if segments_ == candidate:
                    return box_id_
        for length_ in range(len(path), 0, -1):
            prefix = path[:length_]
            for segments_, box_id_ in self.box_paths:
                if len(segments_) >= length_ and segments_[-length_:] == prefix:
                    return box_id_
        return self._external_box(".".join(path), keyword=None)

    def _resolve_requirement(self, reference: str) -> str:
        name = _last_segment(reference)
        box_id = self.requirement_ids.get(name)
        if box_id is not None:
            return box_id
        return self._external_box(name, keyword="«requirement»")

    def _external_box(self, name: str, keyword: Optional[str]) -> str:
        key = f"{keyword}:{name}"
        box = self.external_boxes.get(key)
        if box is None:
            lines = [name] if keyword is None else [keyword, name]
            box = self._new_box(lines, shape="usage")
            self.external_boxes[key] = box
        return box.box_id


def _render_box(box: _Box, indent_level: int) -> List[str]:
    pad = "  " * indent_level
    label = "<br/>".join(_escape_label(line_) for line_ in box.lines)
    if len(box.children) > 0:
        # Non-breaking spaces keep the title on one line.
        title = _escape_label(box.title).replace(" ", "#160;")
        lines = [f'{pad}subgraph {box.box_id}["{title}"]']
        # The declaration and the attributes, when they say more than the
        # title.
        compartment = box.lines[1:]
        if " ".join(compartment) not in box.title:
            compartment_label = "<br/>".join(
                _escape_label(line_) for line_ in compartment
            )
            lines.append(f'{pad}  {box.box_id}c["{compartment_label}"]')
        for child_ in box.children:
            lines.extend(_render_box(child_, indent_level + 1))
        lines.append(f"{pad}end")
        return lines
    if box.shape == "definition":
        return [f'{pad}{box.box_id}["{label}"]']
    if box.shape == "usage":
        return [f'{pad}{box.box_id}("{label}")']
    if box.shape == "start":
        return [f"{pad}{box.box_id}@{{ shape: sm-circ }}"]
    if box.shape == "done":
        return [f"{pad}{box.box_id}@{{ shape: fr-circ }}"]
    assert box.control_kind is not None
    if CONTROL_SHAPES.get(box.control_kind) == "fork":
        return [f"{pad}{box.box_id}@{{ shape: fork }}"]
    return [f'{pad}{box.box_id}@{{ shape: diam, label: "{label}" }}']


def _transition_label(
    transition: Union[SysMLThen, SysMLIfThen, SysMLElseThen],
) -> Optional[str]:
    if isinstance(transition, SysMLIfThen):
        return f"[{transition.condition_text}]"
    if isinstance(transition, SysMLElseThen):
        return "[else]"
    return None


def _feature_text(feature: Union[SysMLElement, SysMLAttribute]) -> str:
    """
    Return the declaration of a feature without its keyword, for example
    `<'HW-STN'> station : Station [4] = 2 [s]`.
    """
    parts: List[str] = []
    if isinstance(feature, SysMLAttribute) and len(feature.modifiers) > 0:
        parts.append(" ".join(feature.modifiers))
    if feature.short_name is not None:
        parts.append(f"<'{feature.short_name}'>")
    if feature.name is not None:
        parts.append(feature.name)
    for specialization_ in feature.specializations:
        parts.append(
            f"{specialization_.operator} {specialization_.targets_text}"
        )
    if feature.multiplicity is not None:
        parts.append(feature.multiplicity)
    if feature.value_text is not None:
        parts.append(f"= {' '.join(feature.value_text.split())}")
    elif feature.default_text is not None:
        parts.append(f"default {' '.join(feature.default_text.split())}")
    text = " ".join(parts)
    if len(text) > MAX_LINE_LENGTH:
        text = text[: MAX_LINE_LENGTH - 1] + "…"
    return text


def _last_segment(reference: str) -> str:
    return reference.replace("::", ".").split(".")[-1].strip("'")


def _escape_label(text: str) -> str:
    """
    Replace the characters that Mermaid reads as syntax or as HTML with
    Mermaid entity codes.
    """
    return (
        text.replace("#", "#35;")
        .replace('"', "#quot;")
        .replace("<", "#lt;")
        .replace(">", "#gt;")
    )
