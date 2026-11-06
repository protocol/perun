"""Session authentication middleware, role guard and ownership helper."""
from litestar.connection import ASGIConnection
from litestar.exceptions import NotAuthorizedException, PermissionDeniedException
from litestar.handlers.base import BaseRouteHandler
from litestar.middleware import AbstractAuthenticationMiddleware, AuthenticationResult

from app.store import ROWS, SESSIONS


class Member:
    def __init__(self, sess):
        self.sess = sess


class SessionAuth(AbstractAuthenticationMiddleware):
    async def authenticate_request(self, connection: ASGIConnection) -> AuthenticationResult:
        if connection.url.path.startswith("/web/"):
            token = connection.cookies.get("sid", "")
        else:
            token = connection.headers.get("authorization", "").removeprefix("Bearer ")
        sess = SESSIONS.get(token)
        if sess is None:
            raise NotAuthorizedException()
        return AuthenticationResult(user=Member(sess), auth=token)


def admin_only(connection: ASGIConnection, _: BaseRouteHandler) -> None:
    if connection.user.sess["role"] != "admin":
        raise PermissionDeniedException()


def owned_or_404(request, rid):
    row = ROWS.get(rid)
    return row if row and row["owner"] == request.user.sess["uid"] else None
