from flask import Flask, abort, g, jsonify

from models import Receipt, Session

app = Flask(__name__)


def owned_or_404(model, pk):
    obj = Session().get(model, pk)
    if obj is None or obj.user_id != g.user.id:
        abort(404)
    return obj


@app.get("/receipts")
def list_receipts():
    rows = Session().query(Receipt).filter(Receipt.user_id == g.user.id)
    return jsonify([r.to_dict() for r in rows])


@app.get("/receipts/<int:rid>")
def get_receipt(rid):
    return jsonify(owned_or_404(Receipt, rid).to_dict())


@app.delete("/receipts/<int:rid>")
def delete_receipt(rid):
    receipt = owned_or_404(Receipt, rid)
    Session().delete(receipt)
    return "", 204
