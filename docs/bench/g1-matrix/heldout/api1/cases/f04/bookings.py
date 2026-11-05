from flask import Blueprint, abort, jsonify, request, session

from .extensions import db
from .models import Booking

bp = Blueprint("bookings", __name__)


def current_uid():
    return session["uid"]


@bp.route("/bookings/<int:booking_id>")
def view_booking(booking_id):
    booking = db.session.get(Booking, booking_id)
    if booking is None or booking.customer_id != current_uid():
        abort(404)
    return jsonify(booking.as_dict())


@bp.route("/bookings/<int:booking_id>/reschedule", methods=["POST"])
def reschedule(booking_id):
    booking = db.session.get(Booking, booking_id)
    if booking is None:
        abort(404)
    booking.starts_at = request.json["starts_at"]
    db.session.commit()
    return jsonify(booking.as_dict())
