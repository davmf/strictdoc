"""
Regression checks on the Halcyon dPCR-24 model fixture.

The fixture is a copy of the model repository, which the OMG SysML v2 Pilot
Implementation validates. The StrictDoc parser must read every file without
falling back to opaque members.
"""

from pathlib import Path

from strictdoc.backend.sysml.model import SysMLElement, SysMLOpaque
from strictdoc.backend.sysml.parser import SysMLParser
from strictdoc.backend.sysml.reader import SysMLReader

FIXTURE_DIR = (
    Path(__file__).resolve().parents[5]
    / "tests"
    / "integration"
    / "features"
    / "sysml"
    / "05_halcyon_model_regression"
)

# Opaque members that are allowed in the fixture, with the reason. The list is
# empty: every construct of the model is in the subset.
ALLOWED_OPAQUE_TEXTS: set = set()


def _fixture_files():
    return sorted(FIXTURE_DIR.glob("*/*.sysml"))


def _collect_opaque(members, found):
    for member_ in members:
        if isinstance(member_, SysMLOpaque):
            found.append(member_)
        for child_ in getattr(member_, "members", []) or []:
            _collect_opaque([child_], found)


def test_01_fixture_has_nine_sysml_files():
    assert len(_fixture_files()) == 9


def test_02_no_opaque_members_in_the_halcyon_model():
    unexpected = []
    for path_ in _fixture_files():
        model = SysMLParser.parse_file(str(path_))
        found: list = []
        _collect_opaque(model.members, found)
        for opaque_ in found:
            if opaque_.text not in ALLOWED_OPAQUE_TEXTS:
                unexpected.append(
                    f"{path_.name}:{opaque_.span.line_start}: {opaque_.text}"
                )
    assert unexpected == []


def test_03_design_files_export_with_unique_uids():
    for path_ in sorted(FIXTURE_DIR.glob("design/*.sysml")):
        text = path_.read_text(encoding="utf8")
        document = SysMLReader.read_from_string(
            text, file_path=str(path_), relative_path=path_.name
        )
        uids = []
        stack = list(document.section_contents)
        while stack:
            node_ = stack.pop(0)
            if getattr(node_, "reserved_uid", None) is not None:
                uids.append(node_.reserved_uid)
            stack.extend(getattr(node_, "section_contents", []) or [])
        assert len(uids) == len(set(uids)), path_.name


def test_04_model_declares_the_expected_number_of_sys_requirements():
    text = (
        FIXTURE_DIR / "requirements" / "system_requirements.sysml"
    ).read_text(encoding="utf8")
    model = SysMLParser.parse_string(text)
    sys_members = [
        member_
        for member_ in _walk_elements(model.members)
        if isinstance(member_, SysMLElement)
        and member_.kind == "requirement"
        and (member_.short_name or "").startswith("SYS-")
    ]
    assert len(sys_members) == 12


def _walk_elements(members):
    for member_ in members:
        yield member_
        for child_ in getattr(member_, "members", []) or []:
            yield from _walk_elements([child_])
