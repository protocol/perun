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


@router.get("/api/parcel")  # @@R GET /api/parcel 1 ; T decoy missing_authn include_router attaches the current_user dependency and the list is filtered by the session owner
def parcel_list(user=Depends(current_user)):
    return [r for r in ROWS.values() if r["owner"] == user["uid"]]


@router.delete("/api/quarry/{item_id}")  # @@R DELETE /api/quarry/{item_id} 1 ; T decoy missing_authz the handler depends on require_admin which answers 403 for other roles
def quarry_remove(item_id: int, admin=Depends(require_admin)):
    if ROWS.pop(item_id, None) is None:
        raise HTTPException(404)
    return Response(status_code=204)


@router.get("/api/anchor/{item_id}")  # @@R GET /api/anchor/{item_id} 1 ; T decoy missing_object_check owned_or_404 compares the owner with the session user and answers 404
def anchor_get(item_id: int, user=Depends(current_user)):
    return owned_or_404(item_id, user)
