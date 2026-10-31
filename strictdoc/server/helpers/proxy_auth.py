"""
Identify the signed-in user from headers set by an authenticating proxy.

StrictDoc does not sign users in itself. A reverse proxy in front of it (e.g.
oauth2-proxy) does, and passes the user to StrictDoc in request headers. The
header names come from the project config (auth_proxy_*_header).

The headers are only trustworthy if nothing but the proxy can reach the
server, and the proxy overwrites any copies a browser sends. The deployment
in deploy/server ensures both.

The user's role comes from their groups. The middleware checks the role that
a path needs (required_role_for_path) before the request reaches a route.
"""

import enum
import html
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

from fastapi import HTTPException
from starlette.requests import HTTPConnection
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from strictdoc.core.project_config import ProjectConfig

# Requests to these paths do not need a user: the container health check
# calls the server directly, not through the proxy.
PATHS_WITHOUT_USER = ("/healthz",)

MAX_HEADER_VALUE_LENGTH = 256
MAX_GROUPS_HEADER_VALUE_LENGTH = 8192


class SDocRole(enum.IntEnum):
    VIEWER = 1
    EDITOR = 2
    ADMIN = 3

    def label(self) -> str:
        return self.name.lower()


# Grammar changes affect every node of a document, so they need an admin.
ADMIN_PATHS = frozenset(
    (
        "/actions/document/edit_grammar",
        "/actions/document/save_grammar",
        "/actions/document/add_grammar_element",
        "/actions/document/edit_grammar_element",
        "/actions/document/save_grammar_element",
        "/actions/document/add_grammar_field",
        "/actions/document/add_grammar_relation",
    )
)

# Routes under /actions/ open edit forms or change content. These are the
# exceptions that only show content.
VIEWER_ACTION_PATHS = frozenset(("/actions/show_full_node",))


def required_role_for_path(path: str) -> SDocRole:
    if path in ADMIN_PATHS:
        return SDocRole.ADMIN
    if path in VIEWER_ACTION_PATHS:
        return SDocRole.VIEWER
    if path.startswith("/actions/") or path == "/reset_uid":
        return SDocRole.EDITOR
    return SDocRole.VIEWER


@dataclass(frozen=True)
class SDocUser:
    # Stable identifier from the proxy, e.g. an email address or login.
    login: str
    email: Optional[str] = None
    name: Optional[str] = None
    groups: FrozenSet[str] = field(default_factory=frozenset)
    role: SDocRole = SDocRole.VIEWER

    def display_name(self) -> str:
        return self.name if self.name is not None else self.login

    def initials(self) -> str:
        parts = self.display_name().split("@")[0].replace(".", " ").split()
        letters = "".join(part[0] for part in parts[:2] if len(part) > 0)
        return letters.upper() if len(letters) > 0 else "?"


def get_current_user(connection: HTTPConnection) -> Optional[SDocUser]:
    """
    Return the signed-in user, or None when proxy auth is not configured.
    """

    user: Optional[SDocUser] = getattr(connection.state, "user", None)
    return user


def require_editor(connection: HTTPConnection) -> None:
    """
    FastAPI dependency for routes that change content.

    The middleware already checks paths. This catches write routes added
    outside /actions/ that the path rules do not know about.
    """

    user = get_current_user(connection)
    if user is not None and user.role < SDocRole.EDITOR:
        raise HTTPException(status_code=403, detail=_forbidden_message(user))


def resolve_role(
    groups: FrozenSet[str], project_config: ProjectConfig
) -> SDocRole:
    if not groups.isdisjoint(project_config.auth_admin_groups):
        return SDocRole.ADMIN
    if not groups.isdisjoint(project_config.auth_editor_groups):
        return SDocRole.EDITOR
    return SDocRole.VIEWER


class ProxyAuthMiddleware:
    """
    Read the user from proxy headers into scope["state"]["user"] and check
    the role that the requested path needs.

    A pure ASGI middleware, so that it covers WebSocket connections as well
    as HTTP requests.
    """

    def __init__(self, app: ASGIApp, *, project_config: ProjectConfig) -> None:
        assert project_config.auth_proxy_user_header is not None
        self.app = app
        self.project_config = project_config
        self.user_header: bytes = _header_key(
            project_config.auth_proxy_user_header
        )
        self.email_header: Optional[bytes] = _optional_header_key(
            project_config.auth_proxy_email_header
        )
        self.name_header: Optional[bytes] = _optional_header_key(
            project_config.auth_proxy_name_header
        )
        self.groups_header: Optional[bytes] = _optional_header_key(
            project_config.auth_proxy_groups_header
        )

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        if scope["path"] in PATHS_WITHOUT_USER:
            await self.app(scope, receive, send)
            return

        headers = _headers_dict(
            scope["headers"],
            long_header=self.groups_header,
        )
        login = headers.get(self.user_header)
        if login is None:
            await self._reject(
                scope,
                receive,
                send,
                status_code=401,
                message=(
                    "Sign-in required: the request did not come through the "
                    "authenticating proxy."
                ),
            )
            return

        groups: FrozenSet[str] = frozenset()
        if self.groups_header is not None:
            groups = _parse_groups(headers.get(self.groups_header))

        user = SDocUser(
            login=login,
            email=headers.get(self.email_header)
            if self.email_header is not None
            else None,
            name=headers.get(self.name_header)
            if self.name_header is not None
            else None,
            groups=groups,
            role=resolve_role(groups, self.project_config),
        )

        if user.role < required_role_for_path(scope["path"]):
            await self._reject(
                scope,
                receive,
                send,
                status_code=403,
                message=_forbidden_message(user),
            )
            return

        scope.setdefault("state", {})["user"] = user
        await self.app(scope, receive, send)

    @staticmethod
    async def _reject(
        scope: Scope,
        receive: Receive,
        send: Send,
        *,
        status_code: int,
        message: str,
    ) -> None:
        if scope["type"] == "websocket":
            # Policy violation. Closing before accepting makes the server
            # answer the handshake with HTTP 403.
            await send({"type": "websocket.close", "code": 1008})
            return
        response = PlainTextResponse(message, status_code=status_code)
        await response(scope, receive, send)


def render_current_user_badge(user: Optional[SDocUser]) -> str:
    """
    Render the nav bar's user badge. Server pages are cached as static HTML,
    so each page fetches the badge separately. The page script copies the
    badge's data-user-role to <body>, where CSS uses it to hide controls the
    user cannot use.
    """

    if user is None:
        return ""

    title = f"Signed in as {user.display_name()}"
    if user.email is not None and user.email != user.display_name():
        title += f" ({user.email})"
    title += f", {user.role.label()}"
    return (
        f'<span class="nav_user" title="{html.escape(title)}" '
        f'data-user-role="{user.role.label()}" '
        'data-testid="nav-current-user">'
        f"{html.escape(user.initials())}"
        "</span>"
    )


def _forbidden_message(user: SDocUser) -> str:
    return (
        f"Not allowed: {user.display_name()} has the {user.role.label()} role."
    )


def _parse_groups(value: Optional[str]) -> FrozenSet[str]:
    """
    Parse a comma-separated groups header, as sent by oauth2-proxy.
    """

    if value is None:
        return frozenset()
    return frozenset(
        group_.strip() for group_ in value.split(",") if len(group_.strip()) > 0
    )


def _header_key(header_name: str) -> bytes:
    return header_name.strip().lower().encode("latin-1")


def _optional_header_key(header_name: Optional[str]) -> Optional[bytes]:
    return _header_key(header_name) if header_name is not None else None


def _headers_dict(
    raw_headers: List[Tuple[bytes, bytes]],
    *,
    long_header: Optional[bytes] = None,
) -> Dict[bytes, str]:
    """
    Decode header values as UTF-8 and drop empty or oversized ones.

    long_header may be longer than the other headers (users can be in many
    groups).

    A header that appears more than once is dropped: the proxy sets exactly
    one value, so a second one means something upstream is misconfigured.
    """

    result: Dict[bytes, str] = {}
    seen: Set[bytes] = set()
    for key_, value_ in raw_headers:
        if key_ in seen:
            result.pop(key_, None)
            continue
        seen.add(key_)
        value = value_.decode("utf-8", errors="replace").strip()
        max_length = (
            MAX_GROUPS_HEADER_VALUE_LENGTH
            if key_ == long_header
            else MAX_HEADER_VALUE_LENGTH
        )
        if 0 < len(value) <= max_length:
            result[key_] = value
    return result
