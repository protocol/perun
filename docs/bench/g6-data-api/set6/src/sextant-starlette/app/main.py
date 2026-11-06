"""Application assembly: middleware, mounts and server start."""
import logging
import os

import uvicorn
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.routing import Mount

from app.auth import SessionBackend
from app.routes import accounts, billing, inventory, notes, orders, reports, support, uploads
from app.util import Throttle

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

MODULES = [orders, billing, inventory, reports, accounts, notes, uploads, support]

app = Starlette(
    routes=[
        *[Mount(m.sub.prefix, routes=m.sub.routes, middleware=[Middleware(Throttle, cap=30, span=60)]) for m in MODULES if hasattr(m, "sub")],
        *[r for m in MODULES for r in m.rt.routes],
    ],
    middleware=[Middleware(AuthenticationMiddleware, backend=SessionBackend())],
)

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=int(os.environ.get("PORT", "8000")),
        ssl_certfile=os.environ.get("SEXTANT_TLS_CERT"),
        ssl_keyfile=os.environ.get("SEXTANT_TLS_KEY"),
    )
