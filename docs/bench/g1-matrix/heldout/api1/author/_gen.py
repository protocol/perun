import json, os
C = []
def add(id, kind, lang, fw, fname, body):
    C.append((id, kind, lang, fw, fname, body.strip('\n')))

# ---------- Express positives ----------
add('e01','pos','javascript','express','routes/invoices.js', r'''
const express = require('express');
const Invoice = require('../models/invoice');
const { requireAuth } = require('../middleware/auth');

const router = express.Router();
router.use(requireAuth);

router.get('/', async (req, res) => {
  const rows = await Invoice.find({ ownerId: req.user.id }).sort({ createdAt: -1 });
  res.json(rows);
});

router.get('/:id', async (req, res) => {
  const inv = await Invoice.findOne({ _id: req.params.id, ownerId: req.user.id });
  if (!inv) return res.status(404).json({ error: 'not found' });
  res.json(inv);
});

router.delete('/:id', async (req, res) => {
  const inv = await Invoice.findById(req.params.id); @@T
  if (!inv) return res.status(404).json({ error: 'not found' });
  await inv.deleteOne();
  res.status(204).end();
});

module.exports = router;
''')
add('e02','pos','javascript','express','routes/orders.js', r'''
const express = require('express');
const { Order, Shipment } = require('../db');
const auth = require('../auth');

const app = express.Router();

app.get('/orders', auth, async (req, res) => {
  const orders = await Order.findAll({ where: { userId: req.user.id } });
  res.json(orders);
});

app.post('/orders/track', auth, async (req, res) => {
  const order = await Order.findOne({
    where: { id: req.body.orderId, userId: req.user.id },
  });
  if (!order) return res.sendStatus(404);
  res.json(await Shipment.findAll({ where: { orderId: order.id } }));
});

app.post('/orders/cancel', auth, async (req, res) => {
  const order = await Order.findByPk(req.body.orderId); @@T
  if (!order) return res.sendStatus(404);
  await order.update({ status: 'cancelled' });
  res.json({ id: order.id, status: order.status });
});

module.exports = app;
''')
add('e03','pos','javascript','express','src/documents.js', r'''
const express = require('express');
const { PrismaClient } = require('@prisma/client');
const { sessionUser } = require('./session');

const prisma = new PrismaClient();
const router = express.Router();

router.get('/document', sessionUser, async (req, res) => {
  const doc = await prisma.document.findUnique({ where: { id: Number(req.query.docId) } });
  if (!doc) return res.status(404).end();
  if (doc.authorId !== req.user.id) return res.status(403).end();
  res.json(doc);
});

router.get('/document/export', sessionUser, async (req, res) => {
  const doc = await prisma.document.findUnique({ where: { id: Number(req.query.docId) } }); @@T
  if (!doc) return res.status(404).end();
  res.type('text/plain').send(doc.body);
});

module.exports = router;
''')
add('e04','pos','javascript','express','api/projects.js', r'''
const express = require('express');
const knex = require('../knex');
const { authenticate } = require('../authenticate');

const router = express.Router();

function getProject(id) {
  return knex('projects').where({ id }).first(); @@T
}

router.get('/projects/:id', authenticate, async (req, res) => {
  const project = await knex('projects')
    .where({ id: req.params.id, user_id: req.user.id })
    .first();
  if (!project) return res.status(404).json({ error: 'missing' });
  res.json(project);
});

router.put('/projects/:id', authenticate, async (req, res) => {
  const project = await getProject(req.params.id);
  if (!project) return res.status(404).json({ error: 'missing' });
  await knex('projects').where({ id: project.id }).update({ name: req.body.name });
  res.json({ ok: true });
});

module.exports = router;
''')
# ---------- Express negatives ----------
add('e05','neg','javascript','express','routes/invoices.js', r'''
const express = require('express');
const Invoice = require('../models/invoice');
const { requireAuth } = require('../middleware/auth');

const router = express.Router();
router.use(requireAuth);

router.get('/:id', async (req, res) => {
  const inv = await Invoice.findOne({ _id: req.params.id, ownerId: req.user.id });
  if (!inv) return res.status(404).json({ error: 'not found' });
  res.json(inv);
});

router.delete('/:id', async (req, res) => {
  const inv = await Invoice.findOneAndDelete({
    _id: req.params.id,
    ownerId: req.user.id,
  });
  if (!inv) return res.status(404).json({ error: 'not found' });
  res.status(204).end();
});

module.exports = router;
''')
add('e06','neg','javascript','express','routes/tickets.js', r'''
const express = require('express');
const Ticket = require('../models/ticket');
const { requireAuth } = require('../middleware/auth');

const router = express.Router();
router.use(requireAuth);

router.param('ticketId', async (req, res, next, id) => {
  const ticket = await Ticket.findById(id);
  if (!ticket) return res.status(404).json({ error: 'not found' });
  if (String(ticket.reporter) !== String(req.user._id)) {
    return res.status(404).json({ error: 'not found' });
  }
  req.ticket = ticket;
  next();
});

router.get('/:ticketId', (req, res) => res.json(req.ticket));

router.post('/:ticketId/close', async (req, res) => {
  req.ticket.closedAt = new Date();
  await req.ticket.save();
  res.json(req.ticket);
});

router.get('/', async (req, res) => {
  res.json(await Ticket.find({ reporter: req.user._id }));
});

module.exports = router;
''')
add('e07','neg','javascript','express','routes/files.js', r'''
const express = require('express');
const { File, Membership } = require('../db');
const auth = require('../auth');

const router = express.Router();

async function canAccess(userId, file) {
  if (file.userId === userId) return true;
  const m = await Membership.findOne({ where: { teamId: file.teamId, userId } });
  return Boolean(m);
}

router.get('/files/:id', auth, async (req, res) => {
  const file = await File.findByPk(req.params.id);
  if (!file || !(await canAccess(req.user.id, file))) return res.sendStatus(404);
  res.json(file);
});

router.delete('/files/:id', auth, async (req, res) => {
  const file = await File.findByPk(req.params.id);
  if (!file || !(await canAccess(req.user.id, file))) return res.sendStatus(404);
  await file.destroy();
  res.sendStatus(204);
});

router.get('/files', auth, async (req, res) => {
  res.json(await File.findAll({ where: { userId: req.user.id } }));
});

module.exports = router;
''')
add('e08','neg','javascript','express','routes/catalog.js', r'''
const express = require('express');
const knex = require('../knex');
const { authenticate } = require('../authenticate');

const router = express.Router();

router.get('/catalog', authenticate, async (req, res) => {
  const rows = await knex('products').where({ published: true }).orderBy('name');
  res.json(rows);
});

router.get('/catalog/:id', authenticate, async (req, res) => {
  const product = await knex('products')
    .where({ id: req.params.id, published: true })
    .first();
  if (!product) return res.status(404).json({ error: 'missing' });
  res.json(product);
});

router.get('/catalog/:id/reviews', authenticate, async (req, res) => {
  const reviews = await knex('reviews').where({ product_id: req.params.id });
  res.json(reviews);
});

module.exports = router;
''')

# ---------- Flask positives ----------
add('f01','pos','python','flask','notes.py', r'''
from flask import Blueprint, abort, jsonify, request
from flask_login import current_user, login_required

from .models import Note, db

bp = Blueprint("notes", __name__)


@bp.get("/notes")
@login_required
def list_notes():
    notes = Note.query.filter_by(user_id=current_user.id).all()
    return jsonify([n.to_dict() for n in notes])


@bp.get("/notes/<int:note_id>")
@login_required
def show_note(note_id):
    note = Note.query.filter_by(id=note_id, user_id=current_user.id).first_or_404()
    return jsonify(note.to_dict())


@bp.delete("/notes/<int:note_id>")
@login_required
def delete_note(note_id):
    note = Note.query.get(note_id) @@T
    if note is None:
        abort(404)
    db.session.delete(note)
    db.session.commit()
    return "", 204
''')
add('f02','pos','python','flask','accounts.py', r'''
import sqlite3

from flask import Flask, abort, g, jsonify, request

app = Flask(__name__)


def db():
    return sqlite3.connect("acme.db")


@app.get("/statements/<int:sid>")
def get_statement(sid):
    row = db().execute(
        "SELECT * FROM statements WHERE id = ? AND user_id = ?", (sid, g.user["id"])
    ).fetchone()
    if row is None:
        abort(404)
    return jsonify(dict(row))


@app.get("/statements/<int:sid>/download")
def download_statement(sid):
    row = db().execute("SELECT * FROM statements WHERE id = ?", (sid,)).fetchone() @@T
    if row is None:
        abort(404)
    return jsonify({"pdf": row["pdf_path"]})
''')
add('f03','pos','python','flask','tasks.py', r'''
from flask import Blueprint, g, jsonify, request
from peewee import DoesNotExist

from .models import Task

tasks = Blueprint("tasks", __name__, url_prefix="/tasks")


@tasks.route("/<int:task_id>", methods=["GET"])
def read_task(task_id):
    try:
        task = Task.get((Task.id == task_id) & (Task.assignee == g.user.id))
    except DoesNotExist:
        return jsonify(error="missing"), 404
    return jsonify(task.serialize())


@tasks.route("/complete", methods=["POST"])
def complete_task():
    payload = request.get_json()
    try:
        task = Task.get_by_id(payload["task_id"]) @@T
    except DoesNotExist:
        return jsonify(error="missing"), 404
    task.done = True
    task.save()
    return jsonify(task.serialize())
''')
add('f04','pos','python','flask','bookings.py', r'''
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
    booking = db.session.get(Booking, booking_id) @@T
    if booking is None:
        abort(404)
    booking.starts_at = request.json["starts_at"]
    db.session.commit()
    return jsonify(booking.as_dict())
''')
# ---------- Flask negatives ----------
add('f05','neg','python','flask','notes.py', r'''
from flask import Blueprint, abort, jsonify
from flask_login import current_user, login_required

from .models import Note, db

bp = Blueprint("notes", __name__)


@bp.get("/notes/<int:note_id>")
@login_required
def show_note(note_id):
    note = Note.query.filter_by(id=note_id, user_id=current_user.id).first_or_404()
    return jsonify(note.to_dict())


@bp.delete("/notes/<int:note_id>")
@login_required
def delete_note(note_id):
    note = Note.query.get_or_404(note_id)
    if note.user_id != current_user.id:
        abort(403)
    db.session.delete(note)
    db.session.commit()
    return "", 204
''')
add('f06','neg','python','flask','reports.py', r'''
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
''')
add('f07','neg','python','flask','receipts.py', r'''
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
''')
add('f08','neg','python','flask','public_pages.py', r'''
from flask import Blueprint, abort, jsonify

from .models import Article

bp = Blueprint("articles", __name__)


@bp.get("/articles")
def list_articles():
    rows = Article.query.filter_by(status="published").order_by(Article.id.desc())
    return jsonify([a.summary() for a in rows])


@bp.get("/articles/<int:article_id>")
def read_article(article_id):
    article = Article.query.get(article_id)
    if article is None or article.status != "published":
        abort(404)
    return jsonify(article.to_dict())


@bp.get("/articles/<int:article_id>/related")
def related(article_id):
    article = Article.query.get_or_404(article_id)
    rows = Article.query.filter_by(topic=article.topic, status="published").limit(5)
    return jsonify([a.summary() for a in rows])
''')

# ---------- FastAPI positives ----------
add('a01','pos','python','fastapi','routers/items.py', r'''
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..deps import get_current_user, get_db
from ..models import Item

router = APIRouter(prefix="/items")


@router.get("/{item_id}")
def read_item(item_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    item = db.query(Item).filter(Item.id == item_id, Item.owner_id == user.id).first()
    if item is None:
        raise HTTPException(status_code=404)
    return item


@router.delete("/{item_id}")
def delete_item(item_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    item = db.query(Item).filter(Item.id == item_id).first() @@T
    if item is None:
        raise HTTPException(status_code=404)
    db.delete(item)
    db.commit()
    return {"deleted": item_id}
''')
add('a02','pos','python','fastapi','main.py', r'''
from fastapi import Depends, FastAPI, HTTPException

from auth import current_user

app = FastAPI()

PROFILES = {}


@app.get("/profiles/{pid}")
def read_profile(pid: str, user=Depends(current_user)):
    profile = PROFILES.get(pid)
    if profile is None or profile["user_id"] != user["id"]:
        raise HTTPException(404, "not found")
    return profile


@app.put("/profiles/{pid}")
def update_profile(pid: str, patch: dict, user=Depends(current_user)):
    profile = PROFILES.get(pid) @@T
    if profile is None:
        raise HTTPException(404, "not found")
    profile.update(patch)
    return profile
''')
add('a03','pos','python','fastapi','app/orders.py', r'''
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from .db import engine
from .models import Order
from .security import get_user

router = APIRouter()


def session():
    with Session(engine) as s:
        yield s


@router.get("/orders")
def my_orders(s: Session = Depends(session), user=Depends(get_user)):
    return s.exec(select(Order).where(Order.user_id == user.id)).all()


@router.post("/orders/refund")
def refund(body: dict, s: Session = Depends(session), user=Depends(get_user)):
    order = s.get(Order, body["order_id"]) @@T
    if order is None:
        raise HTTPException(status_code=404)
    order.status = "refunded"
    s.add(order)
    s.commit()
    return order
''')
add('a04','pos','python','fastapi','api/messages.py', r'''
from databases import Database
from fastapi import APIRouter, Depends, HTTPException

from .security import current_user

database = Database("postgresql://localhost/acme")
router = APIRouter()


@router.get("/messages/{message_id}")
async def get_message(message_id: int, user=Depends(current_user)):
    row = await database.fetch_one(
        "SELECT * FROM messages WHERE id = :id AND recipient_id = :uid",
        {"id": message_id, "uid": user.id},
    )
    if row is None:
        raise HTTPException(status_code=404)
    return dict(row)


@router.get("/messages/{message_id}/attachments")
async def attachments(message_id: int, user=Depends(current_user)):
    msg = await database.fetch_one("SELECT * FROM messages WHERE id = :id", {"id": message_id}) @@T
    if msg is None:
        raise HTTPException(status_code=404)
    return await database.fetch_all(
        "SELECT * FROM attachments WHERE message_id = :id", {"id": msg["id"]}
    )
''')
# ---------- FastAPI negatives ----------
add('a05','neg','python','fastapi','routers/items.py', r'''
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..deps import get_current_user, get_db
from ..models import Item

router = APIRouter(prefix="/items")


@router.get("/{item_id}")
def read_item(item_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    item = db.query(Item).filter(Item.id == item_id, Item.owner_id == user.id).first()
    if item is None:
        raise HTTPException(status_code=404)
    return item


@router.delete("/{item_id}")
def delete_item(item_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    item = db.get(Item, item_id)
    if item is None or item.owner_id != user.id:
        raise HTTPException(status_code=404)
    db.delete(item)
    db.commit()
    return {"deleted": item_id}
''')
add('a06','neg','python','fastapi','routers/albums.py', r'''
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..deps import get_current_user, get_db
from ..models import Album

router = APIRouter(prefix="/albums")


def owned_album(album_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    album = db.get(Album, album_id)
    if album is None or album.user_id != user.id:
        raise HTTPException(status_code=404)
    return album


@router.get("/{album_id}")
def read_album(album=Depends(owned_album)):
    return album


@router.patch("/{album_id}")
def rename_album(title: str, album=Depends(owned_album), db: Session = Depends(get_db)):
    album.title = title
    db.commit()
    return album


@router.get("")
def list_albums(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return db.query(Album).filter(Album.user_id == user.id).all()
''')
add('a07','neg','python','fastapi','main.py', r'''
from fastapi import Depends, FastAPI, HTTPException

from auth import current_user

app = FastAPI()

WALLETS = {}


def wallet_for(wid: str, user) -> dict:
    wallet = WALLETS.get(wid)
    if wallet is None or user["id"] not in wallet["members"]:
        raise HTTPException(404, "not found")
    return wallet


@app.get("/wallets/{wid}")
def read_wallet(wid: str, user=Depends(current_user)):
    return wallet_for(wid, user)


@app.post("/wallets/{wid}/deposit")
def deposit(wid: str, amount: int, user=Depends(current_user)):
    wallet = wallet_for(wid, user)
    wallet["balance"] += amount
    return wallet


@app.get("/wallets")
def my_wallets(user=Depends(current_user)):
    return [w for w in WALLETS.values() if user["id"] in w["members"]]
''')

# ---------- Django positives ----------
add('d01','pos','python','django','docs/views.py', r'''
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse

from .models import Document


@login_required
def my_documents(request):
    rows = Document.objects.filter(owner=request.user).values("id", "title")
    return JsonResponse({"documents": list(rows)})


@login_required
def document_detail(request, pk):
    try:
        doc = Document.objects.get(pk=pk, owner=request.user)
    except Document.DoesNotExist:
        raise Http404
    return JsonResponse({"id": doc.pk, "title": doc.title, "body": doc.body})


@login_required
def document_share_link(request, pk):
    doc = Document.objects.get(pk=pk) @@T
    return JsonResponse({"url": f"https://example.com/s/{doc.share_token}"})
''')
add('d02','pos','python','django','reports/api.py', r'''
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Report
from .serializers import ReportSerializer


class ReportList(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Report.objects.filter(author=request.user)
        return Response(ReportSerializer(qs, many=True).data)


class ReportDetail(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        report = get_object_or_404(Report, pk=pk) @@T
        return Response(ReportSerializer(report).data)

    def delete(self, request, pk):
        report = get_object_or_404(Report, pk=pk, author=request.user)
        report.delete()
        return Response(status=204)
''')
add('d03','pos','python','django','billing/views.py', r'''
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, JsonResponse
from django.views.decorators.http import require_POST

from .models import Invoice


@login_required
@require_POST
def pay_invoice(request):
    invoice = Invoice.objects.filter(pk=request.POST["invoice_id"]).first()
    if invoice is None or invoice.customer_id != request.user.id:
        return HttpResponseForbidden()
    invoice.paid = True
    invoice.save()
    return JsonResponse({"paid": True})


@login_required
@require_POST
def void_invoice(request):
    invoice = Invoice.objects.filter(pk=request.POST["invoice_id"]).first() @@T
    if invoice is None:
        return JsonResponse({"error": "missing"}, status=404)
    invoice.voided = True
    invoice.save()
    return JsonResponse({"voided": True})
''')
# ---------- Django negatives ----------
add('d04','neg','python','django','docs/views.py', r'''
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse

from .models import Document


@login_required
def document_detail(request, pk):
    try:
        doc = Document.objects.get(pk=pk, owner=request.user)
    except Document.DoesNotExist:
        raise Http404
    return JsonResponse({"id": doc.pk, "title": doc.title, "body": doc.body})


@login_required
def document_share_link(request, pk):
    doc = Document.objects.filter(owner=request.user).get(pk=pk)
    return JsonResponse({"url": f"https://example.com/s/{doc.share_token}"})
''')
add('d05','neg','python','django','tasks/views.py', r'''
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from .models import Task


@login_required
def task_list(request):
    return JsonResponse({"tasks": list(Task.objects.for_user(request.user).values("id", "name"))})


@login_required
def task_detail(request, pk):
    task = get_object_or_404(Task.objects.for_user(request.user), pk=pk)
    return JsonResponse({"id": task.pk, "name": task.name})


@login_required
def task_finish(request, pk):
    task = get_object_or_404(Task.objects.for_user(request.user), pk=pk)
    task.done = True
    task.save(update_fields=["done"])
    return JsonResponse({"done": True})
''')
add('d06','neg','python','django','notes/viewsets.py', r'''
from rest_framework import permissions, viewsets

from .models import Note
from .serializers import NoteSerializer


class NoteViewSet(viewsets.ModelViewSet):
    serializer_class = NoteSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Note.objects.filter(author=self.request.user)

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)


class PinnedNoteViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NoteSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Note.objects.filter(author=self.request.user, pinned=True)
''')
add('d07','neg','python','django','shop/views.py', r'''
from django.http import Http404, JsonResponse

from .models import Product


def product_list(request):
    rows = Product.objects.filter(active=True).values("id", "name", "price")
    return JsonResponse({"products": list(rows)})


def product_detail(request, pk):
    product = Product.objects.filter(pk=pk, active=True).first()
    if product is None:
        raise Http404
    return JsonResponse({"id": product.pk, "name": product.name, "price": str(product.price)})


def product_stock(request):
    product = Product.objects.filter(pk=request.GET.get("id"), active=True).first()
    if product is None:
        raise Http404
    return JsonResponse({"stock": product.stock})
''')

# ---- extra to reach 15/15 and framework spread ----
# so far pos: e4 f4 a4 d3 =15 ; neg: e4 f4 a3 d4 =15
os.makedirs('cases', exist_ok=True)
meta = []
for id, kind, lang, fw, fname, body in C:
    lines = body.split('\n')
    tl = None
    out = []
    for i, l in enumerate(lines, 1):
        if l.rstrip().endswith('@@T'):
            tl = i
            l = l.rstrip()[:-3].rstrip()
        out.append(l)
    p = os.path.join('cases', id, fname)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w').write('\n'.join(out) + '\n')
    m = dict(id=id, kind=kind, language=lang, framework=fw)
    if kind == 'pos':
        m.update(truth_file=f'{id}/{fname}', truth_line=tl)
    meta.append(m)
json.dump(meta, open('cases.json', 'w'), indent=1)
