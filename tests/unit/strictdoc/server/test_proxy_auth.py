from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from strictdoc.core.project_config import ProjectConfig
from strictdoc.server.helpers.proxy_auth import (
    SDocRole,
    SDocUser,
    _parse_groups,
    require_editor,
    required_role_for_path,
    resolve_role,
)


def test_01_required_role_for_path():
    assert required_role_for_path("/") == SDocRole.VIEWER
    assert required_role_for_path("/docs/index.html") == SDocRole.VIEWER
    assert required_role_for_path("/search") == SDocRole.VIEWER
    assert required_role_for_path("/actions/show_full_node") == SDocRole.VIEWER
    assert (
        required_role_for_path("/actions/document/update_requirement")
        == SDocRole.EDITOR
    )
    assert (
        required_role_for_path("/actions/table/get_node_comments_inline")
        == SDocRole.EDITOR
    )
    assert required_role_for_path("/reset_uid") == SDocRole.EDITOR
    assert (
        required_role_for_path("/actions/document/save_grammar")
        == SDocRole.ADMIN
    )
    assert (
        required_role_for_path("/actions/document/edit_grammar_element")
        == SDocRole.ADMIN
    )


def test_02_resolve_role_takes_highest_group():
    project_config = ProjectConfig(
        auth_proxy_user_header="X-Forwarded-Email",
        auth_proxy_groups_header="X-Forwarded-Groups",
        auth_editor_groups=["editors"],
        auth_admin_groups=["admins"],
    )
    assert resolve_role(frozenset(), project_config) == SDocRole.VIEWER
    assert resolve_role(frozenset({"staff"}), project_config) == SDocRole.VIEWER
    assert (
        resolve_role(frozenset({"staff", "editors"}), project_config)
        == SDocRole.EDITOR
    )
    assert (
        resolve_role(frozenset({"editors", "admins"}), project_config)
        == SDocRole.ADMIN
    )


def test_03_parse_groups():
    assert _parse_groups(None) == frozenset()
    assert _parse_groups("") == frozenset()
    assert _parse_groups(" a, b ,,c ") == frozenset({"a", "b", "c"})


def test_04_require_editor():
    def connection(user):
        return SimpleNamespace(state=SimpleNamespace(user=user))

    # No user: proxy auth is off, nothing to check.
    require_editor(connection(None))
    require_editor(connection(SDocUser(login="e", role=SDocRole.EDITOR)))
    require_editor(connection(SDocUser(login="a", role=SDocRole.ADMIN)))
    with pytest.raises(HTTPException) as exc_info:
        require_editor(connection(SDocUser(login="v", role=SDocRole.VIEWER)))
    assert exc_info.value.status_code == 403
