"""Session authentication backend and ownership helpers."""
from starlette.authentication import AuthCredentials, AuthenticationBackend, SimpleUser

from app.store import ROWS, SESSIONS


class Member(SimpleUser):
    def __init__(self, sess):
        super().__init__(str(sess["uid"]))
        self.sess = sess


class SessionBackend(AuthenticationBackend):
    async def authenticate(self, conn):
        if conn.url.path.startswith("/web/"):
            token = conn.cookies.get("sid", "")
        else:
            token = conn.headers.get("authorization", "").removeprefix("Bearer ")
        sess = SESSIONS.get(token)
        if sess is None:
            return None
        return AuthCredentials(["authenticated", sess["role"]]), Member(sess)


def owned_or_404(request, rid):
    row = ROWS.get(rid)
    return row if row and row["owner"] == request.user.sess["uid"] else None
