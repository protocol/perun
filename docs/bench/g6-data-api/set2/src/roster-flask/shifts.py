from flask import Blueprint, abort, g, jsonify, request

from auth import bearer_session, need_role
from store import EMPLOYEES, SHIFTS

board = Blueprint("board", __name__)
bp = Blueprint("shifts", __name__, url_prefix="/api")
mgr = Blueprint("mgr", __name__, url_prefix="/api/manage")


@bp.before_request
def require_session():
    sess = bearer_session()
    if sess is None:
        abort(401)
    g.user = sess


@mgr.before_request
def require_manager():
    sess = bearer_session()
    if sess is None:
        abort(401)
    if sess["role"] != "manager":
        abort(403)
    g.user = sess


def owned_shift_or_404(shift_id):
    shift = SHIFTS.get(shift_id)
    if shift is None or shift["employee_id"] != g.user["user_id"]:
        abort(404)
    return shift


@board.get("/api/board/today")  # @@R GET /api/board/today 0 ; T positive missing_authn board blueprint has no before_request gate and lists employee ids with shift slots
def board_today():
    return jsonify([{"employee": s["employee_id"], "slot": s["slot"]} for s in SHIFTS.values()])


@bp.post("/shifts/<int:shift_id>/approve")  # @@R POST /api/shifts/<int:shift_id>/approve 0 ; T positive missing_authz approval is a manager action but only a session is required
def approve(shift_id):
    shift = SHIFTS.get(shift_id) or abort(404)
    shift["published"] = True
    return jsonify(shift)


@bp.get("/employees/<int:emp_id>/shifts")  # @@R GET /api/employees/<int:emp_id>/shifts 0 ; T positive missing_object_check path employee id used as the filter and never compared with the session user
def shifts_of(emp_id):
    return jsonify([s for s in SHIFTS.values() if s["employee_id"] == emp_id])


@bp.put("/shifts/<int:shift_id>/note")  # @@R PUT /api/shifts/<int:shift_id>/note 0 ; T positive missing_object_check note replaced without checking the shift belongs to the caller
def set_note(shift_id):
    shift = SHIFTS.get(shift_id) or abort(404)
    shift["note"] = str(request.json.get("note", ""))[:500]
    return jsonify(shift)


@bp.get("/me/shifts")  # @@R GET /api/me/shifts 1 ; T decoy missing_authn blueprint before_request gate and the list is filtered by the session employee id
def my_shifts():
    return jsonify([s for s in SHIFTS.values() if s["employee_id"] == g.user["user_id"]])


@bp.get("/employees")  # @@R GET /api/employees 1
def employees():
    return jsonify([{"id": e["id"], "name": e["name"]} for e in EMPLOYEES.values()])


@bp.get("/shifts/<int:shift_id>")  # @@R GET /api/shifts/<int:shift_id> 1 ; T decoy missing_object_check owned_shift_or_404 compares the employee id with the session and answers 404
def get_shift(shift_id):
    return jsonify(owned_shift_or_404(shift_id))


@bp.post("/shifts/<int:shift_id>/publish")  # @@R POST /api/shifts/<int:shift_id>/publish 1 ; T decoy missing_authz need_role("manager") decorator rejects other roles
@need_role("manager")
def publish(shift_id):
    shift = SHIFTS.get(shift_id) or abort(404)
    shift["published"] = True
    return jsonify(shift)


@bp.post("/shifts/<int:shift_id>/swap")  # @@R POST /api/shifts/<int:shift_id>/swap 1 ; T decoy missing_object_check swap allowed for the owning employee or a manager and others get 404
def swap(shift_id):
    shift = SHIFTS.get(shift_id)
    if shift is None or (shift["employee_id"] != g.user["user_id"] and g.user["role"] != "manager"):
        abort(404)
    shift["slot"] = "late" if shift["slot"] == "early" else "early"
    return jsonify(shift)


@mgr.delete("/shifts/<int:shift_id>")  # @@R DELETE /api/manage/shifts/<int:shift_id> 1 ; T decoy missing_authz mgr blueprint before_request rejects every non-manager
def remove(shift_id):
    if SHIFTS.pop(shift_id, None) is None:
        abort(404)
    return "", 204
