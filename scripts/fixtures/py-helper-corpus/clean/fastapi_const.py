import pickle, jinja2
from fastapi import FastAPI

app = FastAPI()

def load(raw):
    return pickle.loads(raw)

def render(s):
    return jinja2.Template(s).render()

@app.get("/seed")
def seed():
    return render("Hi") , load(open("/srv/seed.pkl", "rb").read())
