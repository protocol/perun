import os
from fastapi import FastAPI

app = FastAPI()

def do_ping(host: str):
    return os.system(f"ping -c1 {host}")  # SINK command-injection

@app.get("/ping")
def ping(host: str):
    return do_ping(host)
