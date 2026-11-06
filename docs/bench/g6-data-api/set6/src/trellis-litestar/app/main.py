"""Application assembly: authentication middleware, controllers and server start."""
import os

import uvicorn
from litestar import Litestar
from litestar.logging import LoggingConfig
from litestar.middleware import DefineMiddleware

from app.auth import SessionAuth
from app.routes import courier, depots, intake, parcels, profile, search, sessions, tariffs

app = Litestar(
    route_handlers=[c for m in (parcels, tariffs, depots, courier, profile, sessions, search, intake) for c in m.CONTROLLERS],
    middleware=[DefineMiddleware(SessionAuth)],
    logging_config=LoggingConfig(root={"level": "INFO", "handlers": ["queue_listener"]}),
)

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=int(os.environ.get("PORT", "8000")),
        ssl_certfile=os.environ.get("TRELLIS_TLS_CERT"),
        ssl_keyfile=os.environ.get("TRELLIS_TLS_KEY"),
    )
