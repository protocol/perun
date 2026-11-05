#!/usr/bin/env python3
"""ownership_sibling_check.py (OWASP API1 object-level authorization by sibling comparison): seeded positives and near-miss negatives
over Express, Flask, FastAPI and Django, the output-line contract, exit code and the skipped path segments. Fixtures are fictional
(Acme, example.com) tempdir files; each positive pins the exact reported line; each negative must stay silent."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / ".claude/skills/deep-code-review/scripts/ownership_sibling_check.py"

EXPRESS_BASE = """const express = require('express');
const router = express.Router();
"""
FLASK_BASE = """from flask import Flask, request, jsonify
app = Flask(__name__)
"""
FASTAPI_BASE = """from fastapi import FastAPI, Depends, HTTPException
app = FastAPI()
"""
DJANGO_BASE = """from django.http import JsonResponse
from django.shortcuts import get_object_or_404
"""

# name -> (source, "lookup-line substring|handler|model|sibling", or None for a near miss that must stay silent)
CASES = {
    "pos_express_mongoose.js": (EXPRESS_BASE + """router.get('/notes/:id', async (req, res) => {
  const note = await Note.findById(req.params.id);
  res.json(note);
});
router.delete('/notes/:id', async (req, res) => {
  const { id } = req.params;
  const note = await Note.findOne({ _id: id, owner: req.user.id });
  res.sendStatus(note ? 204 : 404);
});
""", "Note.findById|GET /notes/:id|note|DELETE /notes/:id"),
    "pos_express_prisma.ts": (EXPRESS_BASE + """async function readInvoice(req, res) {
  if (!req.user) return res.sendStatus(401);
  const invoice = await prisma.invoice.findUnique({ where: { id: Number(req.params.id) } });
  res.json(invoice);
}
async function payInvoice(req, res) {
  const invoice = await prisma.invoice.findFirst({ where: { id: Number(req.params.id), userId: req.user.id } });
  res.json(invoice);
}
router.get('/invoices/:id', readInvoice);
router.post('/invoices/:id/pay', payInvoice);
""", "prisma.invoice.findUnique|readInvoice|invoice|payInvoice"),
    "pos_express_store.js": (EXPRESS_BASE + """const orders = new Map();
router.get('/orders/:id', (req, res) => {
  const order = orders.get(req.params.id);
  res.json(order);
});
router.put('/orders/:id', (req, res) => {
  const order = orders.get(req.params.id);
  if (order.ownerId !== req.user.id) return res.sendStatus(404);
  res.json(order);
});
""", "orders.get(req.params.id);|GET /orders/:id|order|PUT /orders/:id"),
    "pos_flask_query_get.py": (FLASK_BASE + """@app.route('/items/<int:item_id>')
def get_item(item_id):
    item = Item.query.get(item_id)
    return jsonify(item.to_dict())

@app.route('/items/<int:item_id>', methods=['DELETE'])
def delete_item(item_id):
    item = Item.query.filter_by(id=item_id, user_id=current_user.id).first_or_404()
    return '', 204
""", "Item.query.get(item_id)|get_item|item|delete_item"),
    "pos_flask_compare.py": (FLASK_BASE + """@app.route('/reports/<rid>', methods=['PUT'])
@login_required
def update_report(rid):
    report = Report.query.filter_by(id=rid).first()
    report.title = request.json['title']
    return jsonify(ok=True)

@app.route('/reports/<rid>')
@login_required
def show_report(rid):
    report = Report.query.get_or_404(rid)
    if report.owner_id != current_user.id:
        abort(404)
    return jsonify(report.to_dict())
""", "filter_by(id=rid).first()|update_report|report|show_report"),
    "pos_fastapi_query.py": (FASTAPI_BASE + """@app.get('/docs/{doc_id}')
def read_doc(doc_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    return doc

@app.delete('/docs/{doc_id}')
def delete_doc(doc_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    doc = db.query(Document).filter(Document.id == doc_id, Document.owner_id == user.id).first()
    db.delete(doc)
""", "Document.id == doc_id).first()|read_doc|document|delete_doc"),
    "pos_fastapi_session_get.py": (FASTAPI_BASE + """@router.get('/tasks/{task_id}')
async def get_task(task_id: int, session: Session = Depends(get_session)):
    task = session.get(Task, task_id)
    return task

@router.patch('/tasks/{task_id}')
async def patch_task(task_id: int, session: Session = Depends(get_session), me: User = Depends(current_user)):
    task = session.get(Task, task_id)
    if task.owner_id != current_user.id:
        raise HTTPException(status_code=404)
    return task
""", "session.get(Task, task_id)|get_task|task|patch_task"),
    "pos_django_objects.py": (DJANGO_BASE + """def view_invoice(request, pk):
    invoice = Invoice.objects.get(pk=pk)
    return JsonResponse({'total': invoice.total})

def edit_invoice(request, pk):
    invoice = Invoice.objects.get(pk=pk, owner=request.user)
    return JsonResponse({'total': invoice.total})
""", "Invoice.objects.get(pk=pk)|view_invoice|invoice|edit_invoice"),
    "pos_django_404_query.py": (DJANGO_BASE + """def photo_detail(request):
    photo = get_object_or_404(Photo, id=request.GET['id'])
    return JsonResponse({'url': photo.url})

def photo_delete(request, photo_id):
    photo = get_object_or_404(Photo, id=photo_id, user=request.user)
    photo.delete()
""", "get_object_or_404(Photo, id=request.GET|photo_detail|photo|photo_delete"),
    "pos_drf_class.py": (DJANGO_BASE + """from rest_framework.views import APIView

class NoteDetail(APIView):
    def get(self, request, pk):
        note = Note.objects.get(pk=pk)
        return JsonResponse({'body': note.body})

    def delete(self, request, pk):
        note = Note.objects.filter(pk=pk).first()
        if note.owner != request.user:
            return JsonResponse({}, status=404)
        note.delete()
""", "Note.objects.get(pk=pk)|get|note|delete"),
    # ---- near misses: must stay silent ----
    "neg_other_model.py": (FLASK_BASE + """@app.route('/items/<int:item_id>')
def get_item(item_id):
    item = Item.query.get(item_id)
    return jsonify(item.to_dict())

@app.route('/notes/<int:note_id>')
def get_note(note_id):
    note = Note.query.filter_by(id=note_id, user_id=current_user.id).first()
    return jsonify(note.to_dict())
""", None),
    "neg_handler_compares.js": (EXPRESS_BASE + """router.get('/notes/:id', async (req, res) => {
  const note = await Note.findById(req.params.id);
  if (note.owner.toString() !== req.user.id) return res.sendStatus(404);
  res.json(note);
});
router.delete('/notes/:id', async (req, res) => {
  const note = await Note.findOne({ _id: req.params.id, owner: req.user.id });
  res.sendStatus(204);
});
""", None),
    "neg_helper_call.py": (FASTAPI_BASE + """@app.get('/docs/{doc_id}')
def read_doc(doc_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    check_ownership(doc, user)
    return doc

@app.delete('/docs/{doc_id}')
def delete_doc(doc_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    doc = db.query(Document).filter(Document.id == doc_id, Document.owner_id == user.id).first()
    db.delete(doc)
""", None),
    "neg_decorator.py": (FLASK_BASE + """@app.route('/reports/<rid>')
@owner_required
def show_report(rid):
    report = Report.query.get(rid)
    return jsonify(report.to_dict())

@app.route('/reports/<rid>', methods=['DELETE'])
def drop_report(rid):
    report = Report.query.filter_by(id=rid, owner_id=current_user.id).first()
    return ''
""", None),
    "neg_id_not_client.py": (DJANGO_BASE + """def my_profile(request):
    profile = Profile.objects.get(pk=request.user.profile_id)
    return JsonResponse({'bio': profile.bio})

def edit_profile(request, pk):
    profile = Profile.objects.get(pk=pk, user=request.user)
    return JsonResponse({'bio': profile.bio})
""", None),
    "neg_no_checking_sibling.js": (EXPRESS_BASE + """router.get('/notes/:id', async (req, res) => {
  const note = await Note.findById(req.params.id);
  res.json(note);
});
router.delete('/notes/:id', async (req, res) => {
  await Note.findByIdAndDelete(req.params.id);
  res.sendStatus(204);
});
""", None),
    "neg_scoped_itself.py": (DJANGO_BASE + """def view_invoice(request, pk):
    invoice = Invoice.objects.filter(owner=request.user).get(pk=pk)
    return JsonResponse({'total': invoice.total})

def edit_invoice(request, pk):
    invoice = Invoice.objects.get(pk=pk, owner=request.user)
    return JsonResponse({'total': invoice.total})
""", None),
    "neg_raises_403.py": (FASTAPI_BASE + """@app.get('/tasks/{task_id}')
def get_task(task_id: int, session: Session = Depends(get_session)):
    task = session.get(Task, task_id)
    if not can_view(task):
        raise HTTPException(status_code=403)
    return task

@app.patch('/tasks/{task_id}')
def patch_task(task_id: int, session: Session = Depends(get_session)):
    task = session.get(Task, task_id)
    if task.owner_id != current_user.id:
        raise HTTPException(status_code=404)
    return task
""", None),
    "neg_depends_guard.py": (FASTAPI_BASE + """@app.get('/tasks/{task_id}')
def get_task(task_id: int, task=Depends(get_owned_task), session: Session = Depends(get_session)):
    task = session.get(Task, task_id)
    return task

@app.patch('/tasks/{task_id}')
def patch_task(task_id: int, session: Session = Depends(get_session)):
    task = session.get(Task, task_id)
    if task.owner_id != current_user.id:
        raise HTTPException(status_code=404)
    return task
""", None),
    "neg_class_get_queryset.py": (DJANGO_BASE + """from rest_framework.views import APIView

class NoteDetail(APIView):
    def get_queryset(self):
        return Note.objects.filter(owner=self.request.user)

    def get(self, request, pk):
        note = Note.objects.get(pk=pk)
        return JsonResponse({'body': note.body})

    def delete(self, request, pk):
        note = Note.objects.filter(pk=pk).first()
        if note.owner != request.user:
            return JsonResponse({}, status=404)
        note.delete()
""", None),
    "neg_route_middleware.js": (EXPRESS_BASE + """router.get('/notes/:id', requireNoteOwner, async (req, res) => {
  const note = await Note.findById(req.params.id);
  res.json(note);
});
router.delete('/notes/:id', async (req, res) => {
  const note = await Note.findOne({ _id: req.params.id, owner: req.user.id });
  res.sendStatus(204);
});
""", None),
    "neg_sibling_scoped_by_client.py": (FLASK_BASE + """@app.route('/items/<int:item_id>')
def get_item(item_id):
    item = Item.query.get(item_id)
    return jsonify(item.to_dict())

@app.route('/users/<int:user_id>/items/<int:item_id>')
def user_item(user_id, item_id):
    item = Item.query.filter_by(id=item_id, user_id=user_id).first()
    return jsonify(item.to_dict())
""", None),
    "neg_role_compare_is_not_ownership.js": (EXPRESS_BASE + """router.get('/notes/:id', async (req, res) => {
  const note = await Note.findById(req.params.id);
  res.json(note);
});
router.delete('/notes/:id', async (req, res) => {
  const note = await Note.findById(req.params.id);
  if (req.user.role === 'admin') await note.deleteOne();
  res.sendStatus(204);
});
""", None),
}


def run(*args):
    return subprocess.run([sys.executable, "-I", str(SCRIPT), *map(str, args)], capture_output=True, text=True, timeout=60, check=False)


class OwnershipSiblingCheck(unittest.TestCase):
    def test_cases(self):
        for name, (src, want) in CASES.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as d:
                f = Path(d) / name
                f.write_text(src)
                r = run(f)
                self.assertEqual(r.returncode, 0, r.stderr)
                lines = r.stdout.splitlines()
                if want is None:
                    self.assertEqual(lines, [], name)
                    continue
                needle, handler, model, sib = want.split("|")
                line = next(i for i, l in enumerate(src.splitlines(), 1) if needle in l)
                self.assertEqual(len(lines), 1, (name, lines))
                self.assertTrue(lines[0].startswith(str(f) + f":{line}: OWNERSHIP: "), lines[0])
                self.assertTrue(lines[0].endswith(f"OWNERSHIP: {handler} loads {model} by client id; sibling {sib} checks ownership"), lines[0])

    def test_skips_test_segments_and_dirs(self):
        with tempfile.TemporaryDirectory() as d:
            for seg in ("tests", "fixtures", "e2e", "app"):
                (Path(d) / seg).mkdir()
                (Path(d) / seg / "views.py").write_text(CASES["pos_flask_query_get.py"][0])
            r = run(d)
            self.assertEqual(r.returncode, 0)
            hits = [l.split(":")[0] for l in r.stdout.splitlines()]
            self.assertEqual(len(hits), 1, hits)
            self.assertTrue(hits[0].endswith("app/views.py"), hits)

    def test_usage_and_missing_path(self):
        self.assertEqual(run().returncode, 2)
        self.assertEqual(run("/nonexistent-acme-path").returncode, 2)

    def test_one_line_handler_at_eof_no_crash(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "v.py").write_text(FLASK_BASE + "@app.route('/x')\ndef f(): return 1")
            r = run(d)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertNotIn("Traceback", r.stderr)

    def test_one_line_handler_matches_multiline(self):
        sib = "@app.route('/o/<oid>', methods=['DELETE'])\ndef delete(oid):\n    o = Order.query.filter_by(id=oid, user_id=current_user.id).first_or_404()\n    return '', 204\n"
        outs = []
        for name, head in (("one", "@app.route('/o/<oid>')\ndef get(oid): return Order.query.get(oid)\n\n"),
                           ("multi", "@app.route('/o/<oid>')\ndef get(oid):\n    return Order.query.get(oid)\n\n")):
            with tempfile.TemporaryDirectory() as d:
                (Path(d) / "v.py").write_text(FLASK_BASE + head + sib)
                r = run(d)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(len(r.stdout.splitlines()), 1, r.stdout)
                self.assertIn("get loads order by client id", r.stdout)
                outs.append(r.stdout.split(": ", 1)[1])
        self.assertEqual(outs[0], outs[1])

    def test_failing_file_skipped_others_report(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "a_bad.py").write_text(FLASK_BASE)
            (Path(d) / "b_good.py").write_text(CASES["pos_flask_query_get.py"][0])
            wrap = ("import sys,runpy\nsys.argv=['x',%r]\nimport importlib.util as u\n"
                    "sp=u.spec_from_file_location('osc',%r);m=u.module_from_spec(sp);sp.loader.exec_module(m)\n"
                    "o=m.scan_file\n"
                    "def sf(f,rel):\n    if 'a_bad' in f: raise ValueError('boom')\n    return o(f,rel)\n"
                    "m.scan_file=sf\nsys.exit(m.main(sys.argv))\n") % (d, str(SCRIPT))
            r = subprocess.run([sys.executable, "-I", "-c", wrap], capture_output=True, text=True, timeout=60, check=False)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("ownership_sibling_check: skipped", r.stderr)
            self.assertIn("boom", r.stderr)
            self.assertEqual(len(r.stdout.splitlines()), 1, r.stdout)

    def test_coverage_floor(self):
        self.assertGreaterEqual(sum(w is not None for _, w in CASES.values()), 8)
        self.assertGreaterEqual(sum(w is None for _, w in CASES.values()), 8)


if __name__ == "__main__":
    unittest.main()
