from fastapi import Depends, FastAPI, HTTPException

from auth import current_user

app = FastAPI()

PROFILES = {}


@app.get("/profiles/{pid}")
def read_profile(pid: str, user=Depends(current_user)):
    profile = PROFILES.get(pid)
    if profile is None or profile["user_id"] != user["id"]:
        raise HTTPException(404, "not found")
    return profile


@app.put("/profiles/{pid}")
def update_profile(pid: str, patch: dict, user=Depends(current_user)):
    profile = PROFILES.get(pid)
    if profile is None:
        raise HTTPException(404, "not found")
    profile.update(patch)
    return profile
