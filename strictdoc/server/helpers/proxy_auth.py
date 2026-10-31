"""
Identify the signed-in user from headers set by an authenticating proxy.

StrictDoc does not sign users in itself. A reverse proxy in front of it (e.g.
oauth2-proxy) does, and passes the user to StrictDoc in request headers. The
header names come from the project config (auth_proxy_*_header).

The headers are only trustworthy if nothing but the proxy can reach the
server, and the proxy overwrites any copies a browser sends. The deployment
in deploy/server ensures both.
"""

import html
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from starlette.requests import HTTPConnection
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from strictdoc.core.project_config import ProjectConfig

# Requests to these paths do not need a user: the container health check
# calls the server directly, not through the proxy.
PATHS_WITHOUT_USER = ("/healthz",)

MAX_HEADER_VALUE_LENGTH = 256


@dataclass(frozen=True)
class SDocUser:
    # Stable identifier from the proxy, e.g. an email address or login.
    login: str
    email: Optional[str] = None
    name: Optional[str] = None

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


class ProxyAuthMiddleware:
    """
    Read the user from proxy headers into scope["state"]["user"].

    A pure ASGI middleware, so that it covers WebSocket connections as well
    as HTTP requests.
    """

    def __init__(self, app: ASGIApp, *, project_config: ProjectConfig) -> None:
        assert project_config.auth_proxy_user_header is not None
        self.app = app
        self.user_header: bytes = _header_key(
            project_config.auth_proxy_user_header
        )
        self.email_header: Optional[bytes] = (
            _header_key(project_config.auth_proxy_email_header)
            if project_config.auth_proxy_email_header is not None
            else None
        )
        self.name_header: Optional[bytes] = (
            _header_key(project_config.auth_proxy_name_header)
            if project_config.auth_proxy_name_header is not None
            else None
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

        headers = _headers_dict(scope["headers"])
        login = headers.get(self.user_header)
        if login is None:
            if scope["type"] == "websocket":
                # Policy violation. Closing before accepting makes the server
                # answer the handshake with HTTP 403.
                await send({"type": "websocket.close", "code": 1008})
                return
            response = PlainTextResponse(
                "Sign-in required: the request did not come through the "
                "authenticating proxy.",
                status_code=401,
            )
            await response(scope, receive, send)
            return

        user = SDocUser(
            login=login,
            email=headers.get(self.email_header)
            if self.email_header is not None
            else None,
            name=headers.get(self.name_header)
            if self.name_header is not None
            else None,
        )
        scope.setdefault("state", {})["user"] = user
        await self.app(scope, receive, send)


def render_current_user_badge(user: Optional[SDocUser]) -> str:
    """
    Render the nav bar's user badge. Server pages are cached as static HTML,
    so the nav bar fetches the badge separately on every page load.
    """

    if user is None:
        return ""

    title = f"Signed in as {user.display_name()}"
    if user.email is not None and user.email != user.display_name():
        title += f" ({user.email})"
    return (
        f'<span class="nav_user" title="{html.escape(title)}" '
        'data-testid="nav-current-user">'
        f"{html.escape(user.initials())}"
        "</span>"
    )


def _header_key(header_name: str) -> bytes:
    return header_name.strip().lower().encode("latin-1")


def _headers_dict(raw_headers: List[Tuple[bytes, bytes]]) -> Dict[bytes, str]:
    """
    Decode header values as UTF-8 and drop empty or oversized ones.

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
        if 0 < len(value) <= MAX_HEADER_VALUE_LENGTH:
            result[key_] = value
    return result
