from fastapi import Depends, FastAPI, Security
from sqlalchemy.orm import Session
from deps import get_db, get_user_with_scopes
from models import Report

app = FastAPI()


@app.get("/reports/{report_id}")
def get_report(
    report_id: int,
    user=Security(get_user_with_scopes, scopes=["reports:read"]),
    db: Session = Depends(get_db),
):
    return db.get(Report, report_id)


@app.post("/admin/reports/rebuild")
def rebuild(
    user=Security(get_user_with_scopes, scopes=["admin"]),
    db: Session = Depends(get_db),
):
    db.query(Report).delete()
    db.commit()
    return {"status": "rebuilding"}
