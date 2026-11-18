"""Fictional Acme seed: CWE-200 mutant, renamed, exception text and process environment echoed back."""
import os
from flask import Flask, Response

shop = Flask(__name__)
ROWS = {7: {"label": "Acme order", "card_last4": "4242", "secret_note": "internal"}}


@shop.route("/orders/<int:oid>")
def show_order(oid):
    try:
        return Response(str(ROWS[oid]))
    except KeyError as exc:
        return Response("lookup failed: %r env=%s" % (exc, dict(os.environ)), status=500)
