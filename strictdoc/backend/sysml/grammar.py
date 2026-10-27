"""
textX grammar for the SysML v2 subset used by StrictDoc.

The grammar covers the textual notation listed in the Halcyon conventions
document (sysml_conventions.md). It is shared by StrictDoc's parser (see
parser.py) and kept free of StrictDoc-specific logic, so that it stays
readable and easy to compare with the SysML v2 specification.

Design rules:

- Unknown members inside a body are tolerated as `Opaque` members, either a
  balanced `{ ... }` block or text up to `;`. Top-level members are not
  tolerated, so a broken top-level construct is reported as a syntax error.
- Comments are not skipped by textX. `doc /* */`, `comment /* */` and `//`
  line notes are parsed as members so that their text is preserved.
- Expressions are captured as raw text here. parser.py parses them into an
  expression tree (see expression.py).
- `dependency`, `satisfy` and `verify` take an optional body, so that they
  can carry metadata such as `@StrictDocVersioning::TracedVersion { ... }`.
"""

SYSML_GRAMMAR = r"""
Model:
    members*=Member
;

Member:
    annotations*=Annotation
    core=MemberCore
;

Annotation:
    '#' name=Name
;

MemberCore:
    Package
    | Import
    | DocComment
    | BlockComment
    | LineNote
    | Dependency
    | Satisfy
    | Verify
    | Allocate
    | Succession
    | Then
    | BehaviourControl
    | IfThen
    | ElseThen
    | Perform
    | MetadataUsage
    | MemberRequireConstraint
    | Declaration
;

BodyMember:
    Member
    | Opaque
;

Body:
    '{'
        members*=BodyMember
        result=ResultText?
    '}'
;

ResultText:
    text=/[^\s;{}][^;{}]*/
;

Opaque:
    text=/[^\s;{}][^;{}]*/
    (block=RawBlock | ';')
;

RawBlock:
    '{'
        items*=RawItem
    '}'
;

RawItem:
    RawBlock
    | RawText
;

RawText:
    text=/[^{}]+/
;

Package:
    'package' short_name=ShortName? name=Name? body=Body
;

Import:
    (visibility=Visibility)? 'import' target=/[^;]+/ ';'
;

Visibility:
    'private' | 'public'
;

DocComment:
    'doc' name=Name? text=/\/\*[\s\S]*?\*\//
;

BlockComment:
    'comment' name=Name? text=/\/\*[\s\S]*?\*\//
;

LineNote:
    text=/\/\/[^\n]*/
;

Declaration:
    (
        modifiers*=Modifier kind=DeclKind
        | modifiers+=Modifier
        | head_specialization=Specialization
    )
    is_def?='def'
    short_name=ShortName?
    name=Name?
    specializations*=Specialization
    multiplicity=Multiplicity?
    value=ValueAssignment?
    default=DefaultValue?
    (body=Body | ';')
;

Modifier:
    'variation' | 'variant' | 'ref' | 'in' | 'out' | 'inout' | 'return'
    | 'subject' | 'abstract' | 'derived' | 'readonly' | 'end'
    | 'individual' | 'perform'
;

DeclKind:
    'part' | 'item' | 'attribute' | 'action' | 'calc' | 'analysis'
    | 'verification' | 'requirement' | 'constraint' | 'metadata' | 'enum'
    | 'objective'
;

ShortName:
    '<' name=Name '>'
;

Specialization:
    operator=SpecializationOperator targets+=QualifiedName[',']
;

SpecializationOperator:
    ':>>' | ':>' | ':' | 'redefines' | 'subsets'
;

Multiplicity:
    text=/\[[^\]\n]*\]/
;

ValueAssignment:
    '=' text=/[^;{}]+/
;

DefaultValue:
    'default' ('=')? text=/[^;{}]+/
;

Dependency:
    'dependency'
    ('from' sources+=QualifiedName[','])?
    'to' targets+=QualifiedName[',']
    (body=Body | ';')
;

Satisfy:
    'satisfy' ('requirement')? requirement=QualifiedName
    ('by' by=QualifiedName)? (body=Body | ';')
;

Verify:
    'verify' ('requirement')? requirement=QualifiedName (body=Body | ';')
;

Allocate:
    'allocate' source=QualifiedName 'to' target=QualifiedName ';'
;

Succession:
    'first' first=QualifiedName
    (is_guarded?='if' guard=Guard)?
    'then' then=QualifiedName ';'
;

Then:
    'then' target=QualifiedName ';'
;

BehaviourControl:
    kind=ControlKind name=Name? ';'
;

ControlKind:
    'fork' | 'join' | 'decide' | 'merge'
;

IfThen:
    'if' condition=/(?:(?!\bthen\b)[^;{}])+/ 'then' target=QualifiedName ';'
;

ElseThen:
    'else' target=QualifiedName ';'
;

Perform:
    'perform' ('action')? target=QualifiedName ';'
;

MetadataUsage:
    '@' name=QualifiedName (block=RawBlock | ';')
;

MemberRequireConstraint:
    'require' 'constraint' block=RawBlock
;

Name:
    /'(?:[^'\\]|\\.)*'|[A-Za-z_][A-Za-z0-9_]*/
;

QualifiedName:
    /(?:'(?:[^'\\]|\\.)*'|[A-Za-z_][A-Za-z0-9_]*)(?:(?:::|\.)(?:'(?:[^'\\]|\\.)*'|[A-Za-z_][A-Za-z0-9_]*))*/
;

Guard:
    /(?:(?!\bthen\b)[^;{}])+/
;
"""
