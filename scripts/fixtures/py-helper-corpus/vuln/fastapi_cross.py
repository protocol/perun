from fastapi import FastAPI, Request
from helpers_b import read_doc, fetch, shout

app = FastAPI()

@app.get("/doc")
def doc(name: str):
    return read_doc(name)

@app.get("/fetch")
def get(url: str):
    return fetch(url)

@app.post("/render")
async def render(request: Request):
    body = await request.body()
    return shout(body.decode())
