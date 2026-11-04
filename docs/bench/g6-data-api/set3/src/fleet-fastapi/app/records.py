import json
import logging
import os
import secrets

import requests
from fastapi import APIRouter, Depends, Form, Header, HTTPException, Request, Response
from pydantic import BaseModel

from app.deps import cookie_user, current_user, member, require_admin
from app.store import ROWS, open_session
from app.util import Window, ask_model, ask_tool, owned_or_404

router = APIRouter()
log = logging.getLogger("fleet")
VENDOR = "https://dispatch.vendor.example.com"
VENDOR_KEY = os.environ.get("DISPATCH_KEY", "")
PIN = os.environ.get("FLEET_PIN", "")


class Label(BaseModel):
    label: str


@router.post("/api/depot/{item_id}/purge")  # @@R POST /api/depot/{item_id}/purge 0 ; T positive missing_authz purge is an admin action but the router only requires a session
def depot_purge(item_id: int):
    if ROWS.pop(item_id, None) is None:
        raise HTTPException(404)
    return Response(status_code=204)


@router.post("/api/harbor/{item_id}/purge")  # @@R POST /api/harbor/{item_id}/purge 0 ; T positive missing_authz purge is an admin action but the router only requires a session
def harbor_purge(item_id: int):
    if ROWS.pop(item_id, None) is None:
        raise HTTPException(404)
    return Response(status_code=204)


@router.get("/api/lantern/{item_id}")  # @@R GET /api/lantern/{item_id} 0 ; T positive missing_object_check row returned by id without comparing its owner with the session user
def lantern_get(item_id: int):
    row = ROWS.get(item_id)
    if row is None:
        raise HTTPException(404)
    return row


@router.get("/api/compass/{item_id}")  # @@R GET /api/compass/{item_id} 0 ; T positive missing_object_check row returned by id without comparing its owner with the session user
def compass_get(item_id: int):
    row = ROWS.get(item_id)
    if row is None:
        raise HTTPException(404)
    return row
