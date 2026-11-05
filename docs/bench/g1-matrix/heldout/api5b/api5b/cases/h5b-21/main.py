from fastapi import Depends, FastAPI
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from deps import get_db, decode_token
from models import Report

app = FastAPI()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


@app.get("/reports/{report_id}")
def get_report(report_id: int, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    decode_token(token)
    return db.get(Report, report_id)


@app.post("/admin/reports/rebuild")
def rebuild(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    decode_token(token)
    db.query(Report).delete()
    db.commit()
    return {"status": "rebuilding"}
