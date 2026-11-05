import json, os, random
D = "/private/tmp/claude-501/heldout-api5-author"
C = []  # (kind, lang, fw, {fname: text}, truth_file, marker)
def add(kind, lang, fw, files, tf=None, marker=None):
    C.append((kind, lang, fw, files, tf, marker))

# ---------------- Express positives ----------------
add("pos","javascript","express",{"routes/users.js":"""const express = require('express');
const { User } = require('../models');
const { requireAuth } = require('../middleware/auth');

const router = express.Router();

router.get('/me', requireAuth, async (req, res) => {
  const me = await User.findByPk(req.user.id);
  res.json({ id: me.id, email: me.email });
});

router.delete('/admin/users/:id', requireAuth, async (req, res) => {
  const count = await User.destroy({ where: { id: req.params.id } });
  if (!count) return res.status(404).json({ error: 'not found' });
  res.status(204).end();
});

module.exports = router;
"""},"routes/users.js","router.delete('/admin/users/:id'")

add("pos","javascript","express",{"app.js":"""const express = require('express');
const jwt = require('jsonwebtoken');
const prisma = require('./db');

const app = express();
app.use(express.json());

function authenticate(req, res, next) {
  const token = (req.headers.authorization || '').replace('Bearer ', '');
  try {
    req.user = jwt.verify(token, process.env.JWT_SECRET);
    next();
  } catch (e) {
    res.status(401).json({ error: 'bad token' });
  }
}

app.put('/users/:id/role', authenticate, async (req, res) => {
  const updated = await prisma.user.update({
    where: { id: Number(req.params.id) },
    data: { role: req.body.role },
  });
  res.json(updated);
});

app.listen(3000);
"""},"app.js","app.put('/users/:id/role'")

add("pos","javascript","express",{"src/admin.js":"""const express = require('express');
const passport = require('passport');
const { Account } = require('./models');

const admin = express.Router();
admin.use(passport.authenticate('jwt', { session: false }));

admin.get('/admin/accounts', async (req, res) => {
  const rows = await Account.findAll({ attributes: ['id', 'email', 'plan'] });
  res.json(rows);
});

admin.post('/admin/accounts/:id/suspend', async (req, res) => {
  const acct = await Account.findByPk(req.params.id);
  if (!acct) return res.sendStatus(404);
  acct.suspended = true;
  await acct.save();
  res.json({ ok: true });
});

module.exports = admin;
"""},"src/admin.js","admin.post('/admin/accounts/:id/suspend'")

add("pos","javascript","express",{"server.js":"""const express = require('express');
const mongoose = require('mongoose');
const auth = require('./auth');
const Invoice = require('./models/invoice');

const app = express();
app.use(express.json());

app.get('/invoices', auth, async (req, res) => {
  res.json(await Invoice.find({ owner: req.user.id }));
});

app.patch('/invoices/:id/status', auth, async (req, res) => {
  const doc = await Invoice.findByIdAndUpdate(
    req.params.id,
    { status: req.body.status },
    { new: true }
  );
  res.json(doc);
});

mongoose.connect(process.env.MONGO_URL).then(() => app.listen(8080));
"""},"server.js","app.patch('/invoices/:id/status'")

add("pos","javascript","express",{"routes/perms.js":"""const router = require('express').Router();
const { sequelize, Permission } = require('../db');
const ensureLoggedIn = (req, res, next) =>
  req.session && req.session.userId ? next() : res.status(401).end();

const grant = async (req, res) => {
  const [perm] = await Permission.findOrCreate({
    where: { userId: req.body.userId, name: req.body.name },
  });
  res.status(201).json(perm);
};

router.get('/permissions', ensureLoggedIn, async (req, res) => {
  res.json(await Permission.findAll({ where: { userId: req.session.userId } }));
});

router.post('/permissions/grant', ensureLoggedIn, grant);

module.exports = { router, sequelize };
"""},"routes/perms.js","router.post('/permissions/grant'")

# ---------------- Flask positives ----------------
add("pos","python","flask",{"app.py":"""from flask import Flask, jsonify
from flask_login import login_required, current_user
from models import db, User

app = Flask(__name__)


@app.route("/profile")
@login_required
def profile():
    return jsonify(name=current_user.name)


@app.route("/admin/users/<int:user_id>", methods=["DELETE"])
@login_required
def remove_user(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        return jsonify(error="missing"), 404
    db.session.delete(user)
    db.session.commit()
    return "", 204
"""},"app.py",'@app.route("/admin/users/<int:user_id>"')

add("pos","python","flask",{"views.py":"""from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from extensions import db
from models import Member

bp = Blueprint("members", __name__)


@bp.route("/members/<int:member_id>/promote", methods=["POST"])
@jwt_required()
def promote(member_id):
    member = Member.query.get_or_404(member_id)
    member.role = request.json.get("role", "editor")
    db.session.commit()
    return jsonify(id=member.id, role=member.role)


@bp.route("/members")
@jwt_required()
def listing():
    return jsonify([m.id for m in Member.query.all()])
"""},"views.py",'@bp.route("/members/<int:member_id>/promote"')

add("pos","python","flask",{"admin_bp.py":"""from flask import Blueprint, request, abort, g, jsonify
from store import settings_table

admin_bp = Blueprint("admin_bp", __name__, url_prefix="/admin")


@admin_bp.before_request
def need_login():
    if getattr(g, "user", None) is None:
        abort(401)


@admin_bp.route("/settings", methods=["POST"])
def update_settings():
    for key, value in request.get_json().items():
        settings_table[key] = value
    return jsonify(settings_table)


@admin_bp.route("/settings")
def read_settings():
    return jsonify(settings_table)
"""},"admin_bp.py",'@admin_bp.route("/settings", methods=["POST"])')

add("pos","python","flask",{"api.py":"""from functools import wraps
from flask import Flask, request, jsonify, g
from auth import decode_token
from models import Grant, db

app = Flask(__name__)


def token_required(fn):
    @wraps(fn)
    def inner(*a, **kw):
        g.user = decode_token(request.headers.get("X-Token"))
        if g.user is None:
            return jsonify(error="auth"), 401
        return fn(*a, **kw)
    return inner


@app.put("/users/<int:uid>/permissions")
@token_required
def set_permissions(uid):
    Grant.query.filter_by(user_id=uid).delete()
    for name in request.json["names"]:
        db.session.add(Grant(user_id=uid, name=name))
    db.session.commit()
    return jsonify(ok=True)
"""},"api.py",'@app.put("/users/<int:uid>/permissions")')

add("pos","python","flask",{"accounts.py":"""from flask import Flask, request, jsonify
from flask_login import login_required, current_user
from sqlalchemy import select
from db import Session, Account

app = Flask(__name__)


@app.get("/accounts/me")
@login_required
def me():
    with Session() as s:
        acct = s.scalar(select(Account).where(Account.id == current_user.id))
        return jsonify(email=acct.email)


@app.patch("/accounts/<int:account_id>/email")
@login_required
def change_email(account_id):
    with Session() as s:
        acct = s.get(Account, account_id)
        acct.email = request.json["email"]
        s.commit()
        return jsonify(email=acct.email)
"""},"accounts.py",'@app.patch("/accounts/<int:account_id>/email")')

# ---------------- FastAPI positives ----------------
add("pos","python","fastapi",{"main.py":"""from fastapi import FastAPI, Depends, HTTPException
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
"""},"main.py",'@app.delete("/admin/reports/{report_id}"')

add("pos","python","fastapi",{"routers/admin.py":"""from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from deps import get_db, get_current_user
from models import Tenant

router = APIRouter(prefix="/admin", dependencies=[Depends(get_current_user)])


@router.get("/tenants")
def tenants(db: Session = Depends(get_db)):
    return [t.name for t in db.query(Tenant).all()]


@router.post("/tenants/{tenant_id}/disable")
def disable(tenant_id: int, db: Session = Depends(get_db)):
    t = db.get(Tenant, tenant_id)
    t.enabled = False
    db.commit()
    return {"id": tenant_id, "enabled": False}
"""},"routers/admin.py",'@router.post("/tenants/{tenant_id}/disable")')

add("pos","python","fastapi",{"users_api.py":"""from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from deps import get_db, get_current_user
from models import User

router = APIRouter()


class RoleIn(BaseModel):
    role: str


@router.put("/users/{user_id}/role")
def set_role(user_id: int, body: RoleIn, current_user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    target = db.get(User, user_id)
    target.role = body.role
    db.commit()
    return {"id": target.id, "role": target.role}
"""},"users_api.py",'@router.put("/users/{user_id}/role")')

add("pos","python","fastapi",{"routes.py":"""from typing import Annotated
from fastapi import APIRouter, Depends
from sqlmodel import Session
from deps import get_session, get_current_user
from models import User, PermissionGrant

CurrentUser = Annotated[User, Depends(get_current_user)]
SessionDep = Annotated[Session, Depends(get_session)]
router = APIRouter(tags=["access"])


@router.get("/permissions")
def mine(user: CurrentUser, session: SessionDep):
    return session.query(PermissionGrant).filter_by(user_id=user.id).all()


@router.post("/permissions/grant")
def grant(user_id: int, name: str, user: CurrentUser, session: SessionDep):
    session.add(PermissionGrant(user_id=user_id, name=name))
    session.commit()
    return {"granted": name}
"""},"routes.py",'@router.post("/permissions/grant")')

add("pos","python","fastapi",{"app/profiles.py":"""from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.deps import get_db, get_current_user
from app.models import Profile
from app.schemas import ProfilePatch

router = APIRouter()


@router.get("/profiles/{profile_id}")
def read(profile_id: int, user=Depends(get_current_user), db: Session = Depends(get_db)):
    return db.get(Profile, profile_id)


@router.patch("/profiles/{profile_id}")
def edit(profile_id: int, patch: ProfilePatch, user=Depends(get_current_user),
         db: Session = Depends(get_db)):
    p = db.get(Profile, profile_id)
    if p is None:
        raise HTTPException(404)
    p.display_name = patch.display_name
    db.commit()
    return p
"""},"app/profiles.py",'@router.patch("/profiles/{profile_id}")')

# ---------------- negatives ----------------
add("neg","javascript","express",{"routes/users.js":"""const express = require('express');
const { User } = require('../models');
const { requireAuth, requireRole } = require('../middleware/auth');

const router = express.Router();

router.get('/me', requireAuth, async (req, res) => {
  const me = await User.findByPk(req.user.id);
  res.json({ id: me.id, email: me.email });
});

router.delete('/admin/users/:id', requireAuth, requireRole('admin'), async (req, res) => {
  const count = await User.destroy({ where: { id: req.params.id } });
  if (!count) return res.status(404).json({ error: 'not found' });
  res.status(204).end();
});

module.exports = router;
"""})

add("neg","javascript","express",{"app.js":"""const express = require('express');
const jwt = require('jsonwebtoken');
const prisma = require('./db');

const app = express();
app.use(express.json());

function authenticate(req, res, next) {
  const token = (req.headers.authorization || '').replace('Bearer ', '');
  try {
    req.user = jwt.verify(token, process.env.JWT_SECRET);
    next();
  } catch (e) {
    res.status(401).json({ error: 'bad token' });
  }
}

app.put('/users/:id/role', authenticate, async (req, res) => {
  if (!Array.isArray(req.user.roles) || !req.user.roles.includes('admin')) {
    return res.status(403).json({ error: 'forbidden' });
  }
  const updated = await prisma.user.update({
    where: { id: Number(req.params.id) },
    data: { role: req.body.role },
  });
  res.json(updated);
});

app.listen(3000);
"""})

add("neg","javascript","express",{"src/admin.js":"""const express = require('express');
const passport = require('passport');
const { Account } = require('./models');

const guard = (req, res, next) =>
  req.user && req.user.tier === 'staff' ? next() : res.sendStatus(403);

const admin = express.Router();
admin.use(passport.authenticate('jwt', { session: false }), guard);

admin.get('/admin/accounts', async (req, res) => {
  const rows = await Account.findAll({ attributes: ['id', 'email', 'plan'] });
  res.json(rows);
});

admin.post('/admin/accounts/:id/suspend', async (req, res) => {
  const acct = await Account.findByPk(req.params.id);
  if (!acct) return res.sendStatus(404);
  acct.suspended = true;
  await acct.save();
  res.json({ ok: true });
});

module.exports = admin;
"""})

add("neg","javascript","express",{"server.js":"""const express = require('express');
const mongoose = require('mongoose');
const auth = require('./auth');
const { can } = require('./policy');
const Invoice = require('./models/invoice');

const app = express();
app.use(express.json());

app.get('/invoices', auth, async (req, res) => {
  res.json(await Invoice.find({ owner: req.user.id }));
});

app.patch('/invoices/:id/status', auth, async (req, res) => {
  if (!can(req.user, 'invoice:set-status')) return res.sendStatus(403);
  const doc = await Invoice.findByIdAndUpdate(
    req.params.id,
    { status: req.body.status },
    { new: true }
  );
  res.json(doc);
});

mongoose.connect(process.env.MONGO_URL).then(() => app.listen(8080));
""","policy.js":"""const table = {
  support: ['invoice:set-status'],
  owner: ['invoice:set-status', 'invoice:refund'],
};

function can(user, action) {
  const allowed = table[user.group] || [];
  return allowed.includes(action);
}

module.exports = { can };
"""})

add("neg","javascript","express",{"routes/profile.js":"""const router = require('express').Router();
const { Profile } = require('../db');
const requireAuth = require('../middleware/requireAuth');

router.get('/profiles/:id', requireAuth, async (req, res) => {
  const p = await Profile.findByPk(req.params.id);
  res.json(p);
});

// The path id is only used for the URL shape; the write is pinned to the caller.
router.put('/profiles/:id', requireAuth, async (req, res) => {
  const [n] = await Profile.update(
    { displayName: req.body.displayName },
    { where: { id: req.user.profileId } }
  );
  res.json({ updated: n });
});

module.exports = router;
"""})

add("neg","python","flask",{"app.py":"""from flask import Flask, jsonify
from flask_login import login_required, current_user
from flask_principal import Permission, RoleNeed
from models import db, User

app = Flask(__name__)
admin_permission = Permission(RoleNeed("admin"))


@app.route("/profile")
@login_required
def profile():
    return jsonify(name=current_user.name)


@app.route("/admin/users/<int:user_id>", methods=["DELETE"])
@login_required
@admin_permission.require(http_exception=403)
def remove_user(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        return jsonify(error="missing"), 404
    db.session.delete(user)
    db.session.commit()
    return "", 204
"""})

add("neg","python","flask",{"views.py":"""from flask import Blueprint, request, jsonify, abort
from flask_jwt_extended import jwt_required, get_jwt
from extensions import db
from models import Member

bp = Blueprint("members", __name__)


@bp.route("/members/<int:member_id>/promote", methods=["POST"])
@jwt_required()
def promote(member_id):
    if "admin" not in get_jwt().get("roles", []):
        abort(403)
    member = Member.query.get_or_404(member_id)
    member.role = request.json.get("role", "editor")
    db.session.commit()
    return jsonify(id=member.id, role=member.role)


@bp.route("/members")
@jwt_required()
def listing():
    return jsonify([m.id for m in Member.query.all()])
"""})

add("neg","python","flask",{"admin_bp.py":"""from flask import Blueprint, request, abort, g, jsonify
from store import settings_table

ALLOWED_GROUPS = {"ops", "root"}
admin_bp = Blueprint("admin_bp", __name__, url_prefix="/admin")


@admin_bp.before_request
def gate():
    user = getattr(g, "user", None)
    if user is None:
        abort(401)
    if user.group not in ALLOWED_GROUPS:
        abort(403)


@admin_bp.route("/settings", methods=["POST"])
def update_settings():
    for key, value in request.get_json().items():
        settings_table[key] = value
    return jsonify(settings_table)


@admin_bp.route("/settings")
def read_settings():
    return jsonify(settings_table)
"""})

add("neg","python","flask",{"api.py":"""from flask import Flask, request, jsonify
from guards import token_required, permission_required
from models import Grant, db

app = Flask(__name__)


@app.put("/users/<int:uid>/permissions")
@token_required
@permission_required("grants.write")
def set_permissions(uid):
    Grant.query.filter_by(user_id=uid).delete()
    for name in request.json["names"]:
        db.session.add(Grant(user_id=uid, name=name))
    db.session.commit()
    return jsonify(ok=True)
""","guards.py":"""from functools import wraps
from flask import request, jsonify, g
from auth import decode_token, scopes_for


def token_required(fn):
    @wraps(fn)
    def inner(*a, **kw):
        g.user = decode_token(request.headers.get("X-Token"))
        if g.user is None:
            return jsonify(error="auth"), 401
        return fn(*a, **kw)
    return inner


def permission_required(name):
    def deco(fn):
        @wraps(fn)
        def inner(*a, **kw):
            if name not in scopes_for(g.user):
                return jsonify(error="denied"), 403
            return fn(*a, **kw)
        return inner
    return deco
"""})

add("neg","python","flask",{"accounts.py":"""from flask import Flask, request, jsonify, abort
from flask_login import login_required, current_user
from db import Session, Account

app = Flask(__name__)


@app.get("/accounts/me")
@login_required
def me():
    with Session() as s:
        return jsonify(email=s.get(Account, current_user.id).email)


@app.patch("/accounts/<int:account_id>/email")
@login_required
def change_email(account_id):
    if account_id != current_user.id and not current_user.is_staff:
        abort(403)
    with Session() as s:
        acct = s.get(Account, account_id)
        acct.email = request.json["email"]
        s.commit()
        return jsonify(email=acct.email)
"""})

add("neg","python","fastapi",{"main.py":"""from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from deps import get_db, get_current_user, require_admin
from models import Report

app = FastAPI()


@app.get("/reports")
def my_reports(user=Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Report).filter(Report.owner_id == user.id).all()


@app.delete("/admin/reports/{report_id}", status_code=204)
def purge_report(report_id: int, admin=Depends(require_admin), db: Session = Depends(get_db)):
    row = db.get(Report, report_id)
    if row is None:
        raise HTTPException(404)
    db.delete(row)
    db.commit()
""","deps.py":"""from fastapi import Depends, HTTPException


def get_current_user():
    raise NotImplementedError


def require_admin(user=Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="admin required")
    return user
"""})

add("neg","python","fastapi",{"routers/admin.py":"""from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from deps import get_db, require_role
from models import Tenant

router = APIRouter(prefix="/admin", dependencies=[Depends(require_role("admin"))])


@router.get("/tenants")
def tenants(db: Session = Depends(get_db)):
    return [t.name for t in db.query(Tenant).all()]


@router.post("/tenants/{tenant_id}/disable")
def disable(tenant_id: int, db: Session = Depends(get_db)):
    t = db.get(Tenant, tenant_id)
    t.enabled = False
    db.commit()
    return {"id": tenant_id, "enabled": False}
"""})

add("neg","python","fastapi",{"users_api.py":"""from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from deps import get_db, get_current_user
from models import User

router = APIRouter()


class RoleIn(BaseModel):
    role: str


@router.put("/users/{user_id}/role")
def set_role(user_id: int, body: RoleIn, current_user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    if "roles:write" not in current_user.scopes:
        raise HTTPException(status_code=403)
    target = db.get(User, user_id)
    target.role = body.role
    db.commit()
    return {"id": target.id, "role": target.role}
"""})

add("neg","python","fastapi",{"routes.py":"""from fastapi import APIRouter, Depends, Security
from sqlmodel import Session
from deps import get_session, get_current_user
from models import PermissionGrant

router = APIRouter(tags=["access"])


@router.get("/permissions")
def mine(user=Security(get_current_user, scopes=["me"]), session: Session = Depends(get_session)):
    return session.query(PermissionGrant).filter_by(user_id=user.id).all()


@router.post("/permissions/grant")
def grant(user_id: int, name: str, user=Security(get_current_user, scopes=["admin"]),
          session: Session = Depends(get_session)):
    session.add(PermissionGrant(user_id=user_id, name=name))
    session.commit()
    return {"granted": name}
"""})

add("neg","python","fastapi",{"app/profiles.py":"""from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.deps import get_db, get_current_user
from app.models import Profile
from app.schemas import ProfilePatch

router = APIRouter()


@router.get("/profiles/{profile_id}")
def read(profile_id: int, user=Depends(get_current_user), db: Session = Depends(get_db)):
    return db.get(Profile, profile_id)


@router.patch("/profiles/{profile_id}")
def edit(profile_id: int, patch: ProfilePatch, user=Depends(get_current_user),
         db: Session = Depends(get_db)):
    p = db.query(Profile).filter(Profile.id == profile_id, Profile.user_id == user.id).first()
    if p is None:
        raise HTTPException(404)
    p.display_name = patch.display_name
    db.commit()
    return p
"""})

random.seed(5)
random.shuffle(C)
out = []
for i, (kind, lang, fw, files, tf, marker) in enumerate(C, 1):
    cid = "h5-%02d" % i
    for fn, txt in files.items():
        p = os.path.join(D, "cases", cid, fn)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w").write(txt)
    tl = None
    if kind == "pos":
        lines = files[tf].split("\n")
        tl = [n for n, l in enumerate(lines, 1) if marker in l][0]
    out.append({"id": cid, "kind": kind, "language": lang, "framework": fw,
                "truth_file": tf, "truth_line": tl})
json.dump(out, open(os.path.join(D, "cases.json"), "w"), indent=1)
