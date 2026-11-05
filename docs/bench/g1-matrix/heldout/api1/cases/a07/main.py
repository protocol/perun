from fastapi import Depends, FastAPI, HTTPException

from auth import current_user

app = FastAPI()

WALLETS = {}


def wallet_for(wid: str, user) -> dict:
    wallet = WALLETS.get(wid)
    if wallet is None or user["id"] not in wallet["members"]:
        raise HTTPException(404, "not found")
    return wallet


@app.get("/wallets/{wid}")
def read_wallet(wid: str, user=Depends(current_user)):
    return wallet_for(wid, user)


@app.post("/wallets/{wid}/deposit")
def deposit(wid: str, amount: int, user=Depends(current_user)):
    wallet = wallet_for(wid, user)
    wallet["balance"] += amount
    return wallet


@app.get("/wallets")
def my_wallets(user=Depends(current_user)):
    return [w for w in WALLETS.values() if user["id"] in w["members"]]
