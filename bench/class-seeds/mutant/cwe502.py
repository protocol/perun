import yaml
from fastapi import FastAPI

app = FastAPI()


@app.post("/import")
async def import_config(payload: str):
    cfg = yaml.load(payload, Loader=yaml.Loader)
    return {"name": cfg.get("name")}
