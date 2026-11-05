import os

from fastapi import Depends, FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app import account, catalog, gateway, integrations, partners, profile, public, records
from app.deps import cookie_user, current_user, member

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=os.environ["FLEET_SECRET"], same_site="strict", https_only=True)


@app.get("/healthz")  # @@R GET /healthz 0 public
def healthz():
    return {"ok": True}


@app.get("/api/me")  # @@R GET /api/me 1
def me(user=Depends(current_user)):
    return {"uid": user["uid"], "role": user["role"]}


app.include_router(public.router)
app.include_router(gateway.router)
app.include_router(records.router, dependencies=[Depends(current_user)])
app.include_router(catalog.router, dependencies=[Depends(current_user)])
app.include_router(partners.router, dependencies=[Depends(current_user)])
app.include_router(integrations.router, dependencies=[Depends(current_user)])
app.include_router(account.router, dependencies=[Depends(cookie_user)])
app.include_router(profile.router, dependencies=[Depends(member)])
