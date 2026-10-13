"""
Typed, picklable model of a SysML v2 file, produced by SysMLParser.

The model is a plain tree of dataclasses. It holds no textX objects, so it
can be pickled, cached and sent between processes. Every element carries a
SysMLSpan with 1-based line and column numbers and 0-based byte offsets.

Walking a model:

    model = SysMLParser.parse_file("model/requirements/system.sysml")
    for member_ in model.members:
        if isinstance(member_, SysMLPackage):
            ...

Member types (SysMLMember) are: SysMLPackage, SysMLImport, SysMLDocComment,
SysMLBlockComment, SysMLLineNote, SysMLAttribute, SysMLElement,
SysMLRequireConstraint, SysMLDependency, SysMLSatisfy, SysMLVerify,
SysMLAllocate, SysMLSuccession, SysMLThen, SysMLBehaviourControl,
SysMLIfThen, SysMLElseThen, SysMLPerform, SysMLMetadataUsage and
SysMLOpaque. The Opaque type stands for unknown members inside a body.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Union

from strictdoc.backend.sysml.expression import Expression


@dataclass
class SysMLSpan:
    """
    Source location of an element.

    line_start, col_start, line_end, col_end are 1-based.
    byte_start and byte_end are 0-based offsets into the UTF-8 encoded text.
    """

    line_start: int
    col_start: int
    line_end: int
    col_end: int
    byte_start: int
    byte_end: int


@dataclass
class SysMLSpecialization:
    """A `:`, `:>`, `:>>`, `redefines` or `subsets` clause."""

    operator: str
    targets: List[str]
    targets_text: str


@dataclass
class SysMLPackage:
    name: Optional[str]
    short_name: Optional[str]
    members: List["SysMLMember"]
    span: SysMLSpan


@dataclass
class SysMLImport:
    visibility: Optional[str]
    target: str
    span: SysMLSpan


@dataclass
class SysMLDocComment:
    """A `doc /* ... */` comment. text has the ` * ` decoration removed."""

    name: Optional[str]
    text: str
    span: SysMLSpan


@dataclass
class SysMLBlockComment:
    name: Optional[str]
    text: str
    span: SysMLSpan


@dataclass
class SysMLLineNote:
    """A `// ...` line note. text includes the leading slashes."""

    text: str
    span: SysMLSpan


@dataclass
class SysMLAttribute:
    """
    An attribute usage, e.g. `attribute x : Real = 96 [s];`.

    Also used for feature declarations without a keyword, e.g. `in a : Real;`.
    Direction keywords such as `in` are kept in modifiers.

    type_names holds the names after `:`, and type_text is their raw text.
    value_text is the raw text after `=`, including any unit, e.g. `96 [s]`.
    value is the parsed expression tree, or None when the text is outside the
    supported expression syntax. units is the text of a trailing `[...]`.
    """

    name: Optional[str]
    short_name: Optional[str]
    modifiers: List[str]
    specializations: List[SysMLSpecialization]
    type_names: List[str]
    type_text: Optional[str]
    multiplicity: Optional[str]
    value_text: Optional[str]
    value: Optional[Expression]
    units: Optional[str]
    annotations: List[str]
    span: SysMLSpan
    source_text: str
    is_abstract: bool = False
    redefines: List[str] = field(default_factory=list)
    default_text: Optional[str] = None
    default_value: Optional[Expression] = None


@dataclass
class SysMLElement:
    """
    A definition or usage with a keyword, e.g. `part def Pump { ... }`,
    `requirement <'R-1'> 'Title' { ... }`, `calc def Flow { ... }`.

    kind is the keyword, e.g. "part", "requirement" or "calc". is_definition
    is True for `... def`. For a calc, result_text and result_expression hold
    the trailing expression of the body, e.g. `a * b`.

    doc is the text of the first doc comment, or None. docs holds all of
    them. members is empty when the element has no body.
    """

    kind: str
    is_definition: bool
    modifiers: List[str]
    short_name: Optional[str]
    name: Optional[str]
    specializations: List[SysMLSpecialization]
    multiplicity: Optional[str]
    value_text: Optional[str]
    value: Optional[Expression]
    annotations: List[str]
    has_body: bool
    members: List["SysMLMember"]
    doc: Optional[str]
    docs: List[str]
    result_text: Optional[str]
    result_expression: Optional[Expression]
    span: SysMLSpan
    source_text: str
    qualified_name: Optional[str] = field(default=None)

    @property
    def require_constraint_text(self) -> Optional[str]:
        """Text of the first `require constraint` in the body, or None."""
        for member_ in self.members:
            if isinstance(member_, SysMLRequireConstraint):
                return member_.text
        return None

    @property
    def uid(self) -> Optional[str]:
        """The short name if present, otherwise None."""
        return self.short_name

    is_abstract: bool = False
    redefines: List[str] = field(default_factory=list)
    default_text: Optional[str] = None
    default_value: Optional[Expression] = None


@dataclass
class SysMLRequireConstraint:
    """A `require constraint { ... }` member. text is verbatim."""

    text: str
    span: SysMLSpan


@dataclass
class SysMLDependency:
    """`dependency from <sources> to <targets>;`. Names are unquoted."""

    sources: List[str]
    targets: List[str]
    annotations: List[str]
    span: SysMLSpan


@dataclass
class SysMLSatisfy:
    requirement: str
    by: Optional[str]
    annotations: List[str]
    span: SysMLSpan
    by_path: List[str] = field(default_factory=list)
    source_text: str = ""


@dataclass
class SysMLVerify:
    requirement: str
    annotations: List[str]
    span: SysMLSpan
    source_text: str = ""


@dataclass
class SysMLAllocate:
    source: str
    target: str
    annotations: List[str]
    span: SysMLSpan
    source_path: List[str] = field(default_factory=list)
    target_path: List[str] = field(default_factory=list)


@dataclass
class SysMLSuccession:
    first: str
    then: str
    annotations: List[str]
    span: SysMLSpan
    first_path: List[str] = field(default_factory=list)
    then_path: List[str] = field(default_factory=list)
    guard_text: Optional[str] = None
    guard: Optional[Expression] = None


@dataclass
class SysMLThen:
    target: str
    annotations: List[str]
    span: SysMLSpan
    target_path: List[str] = field(default_factory=list)


@dataclass
class SysMLBehaviourControl:
    """`fork`, `join`, `decide` or `merge`, with an optional name."""

    kind: str
    name: Optional[str]
    annotations: List[str]
    span: SysMLSpan


@dataclass
class SysMLIfThen:
    condition_text: str
    condition: Optional[Expression]
    target: str
    annotations: List[str]
    span: SysMLSpan
    target_path: List[str] = field(default_factory=list)


@dataclass
class SysMLElseThen:
    target: str
    annotations: List[str]
    span: SysMLSpan
    target_path: List[str] = field(default_factory=list)


@dataclass
class SysMLPerform:
    target: str
    annotations: List[str]
    span: SysMLSpan
    target_path: List[str] = field(default_factory=list)


@dataclass
class SysMLMetadataUsage:
    """`@Name { ... }` or `@Name;`. body_text is None without a block."""

    name: str
    body_text: Optional[str]
    annotations: List[str]
    span: SysMLSpan


@dataclass
class SysMLOpaque:
    """
    An unknown member inside a body, kept as raw text.

    text is the first part, up to the `{` or `;`. The block, if any, is
    included in source_text.
    """

    text: str
    source_text: str
    span: SysMLSpan


SysMLMember = Union[
    SysMLPackage,
    SysMLImport,
    SysMLDocComment,
    SysMLBlockComment,
    SysMLLineNote,
    SysMLAttribute,
    SysMLElement,
    SysMLRequireConstraint,
    SysMLDependency,
    SysMLSatisfy,
    SysMLVerify,
    SysMLAllocate,
    SysMLSuccession,
    SysMLThen,
    SysMLBehaviourControl,
    SysMLIfThen,
    SysMLElseThen,
    SysMLPerform,
    SysMLMetadataUsage,
    SysMLOpaque,
]


@dataclass
class SysMLModel:
    """The root of a parsed SysML file."""

    file_path: Optional[str]
    members: List[SysMLMember]
    source_text: str
