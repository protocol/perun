from functools import wraps

from flask import Blueprint, abort, g, jsonify

from .models import Report

bp = Blueprint("reports", __name__)


def owns_report(view):
    @wraps(view)
    def wrapper(report_id, *args, **kwargs):
        report = Report.query.get(report_id)
        if report is None or report.team_id not in g.user.team_ids:
            abort(404)
        return view(report, *args, **kwargs)

    return wrapper


@bp.get("/reports/<int:report_id>")
@owns_report
def show_report(report):
    return jsonify(report.to_dict())


@bp.post("/reports/<int:report_id>/archive")
@owns_report
def archive_report(report):
    report.archived = True
    report.save()
    return jsonify(report.to_dict())
