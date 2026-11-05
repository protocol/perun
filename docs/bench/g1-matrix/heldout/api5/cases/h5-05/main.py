from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from deps import get_db, get_current_user
from models import Report

app = FastAPI()


@app.get("/reports")
def my_reports(user=Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Report).filter(Report.owner_id == user.id).all()


@app.delete("/admin/reports/{report_id}", status_code=204)
def purge_report(report_id: int, user=Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(Report, report_id)
    if row is None:
        raise HTTPException(404)
    db.delete(row)
    db.commit()
