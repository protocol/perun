import json, os, random
B = "/private/tmp/claude-501/heldout-api3-author/cases"
C = []
def add(kind, lang, fw, files, truth=None):
    C.append(dict(kind=kind, lang=lang, fw=fw, files=files, truth=truth))

# ---------- positives ----------
add("pos","javascript","express-mongoose",{"routes/users.js":"""const express = require('express');
const bcrypt = require('bcrypt');
const User = require('../models/user');

const router = express.Router();

router.post('/register', async (req, res, next) => {
  try {
    if (!req.body.email || !req.body.password) {
      return res.status(400).json({ error: 'email and password required' });
    }
    const existing = await User.findOne({ email: req.body.email });
    if (existing) {
      return res.status(409).json({ error: 'email taken' });
    }
    req.body.password = await bcrypt.hash(req.body.password, 10);
    const user = await User.create(req.body);
    res.status(201).json({ id: user._id, email: user.email });
  } catch (err) {
    next(err);
  }
});

module.exports = router;
"""},("routes/users.js","User.create(req.body)"))

add("pos","javascript","express-mongoose",{"routes/profile.js":"""const express = require('express');
const Profile = require('../models/profile');
const { requireLogin } = require('../middleware/auth');

const router = express.Router();

router.get('/me', requireLogin, async (req, res) => {
  const profile = await Profile.findOne({ owner: req.user.id });
  res.json(profile);
});

router.put('/me', requireLogin, async (req, res, next) => {
  try {
    const updated = await Profile.findOneAndUpdate(
      { owner: req.user.id },
      req.body,
      { new: true, runValidators: true }
    );
    if (!updated) return res.status(404).end();
    res.json(updated);
  } catch (err) {
    next(err);
  }
});

module.exports = router;
""" },("routes/profile.js","      req.body,"))

add("pos","javascript","express-mongoose",{"routes/projects.js":"""const express = require('express');
const Project = require('../models/project');
const { requireLogin } = require('../middleware/auth');

const router = express.Router();

router.patch('/:id', requireLogin, async (req, res, next) => {
  try {
    const project = await Project.findOne({
      _id: req.params.id,
      members: req.user.id,
    });
    if (!project) {
      return res.status(404).json({ error: 'not found' });
    }
    Object.assign(project, req.body);
    project.updatedAt = new Date();
    await project.save();
    res.json(project);
  } catch (err) {
    next(err);
  }
});

module.exports = router;
"""},("routes/projects.js","Object.assign(project, req.body);"))

add("pos","javascript","express-sequelize",{"routes/accounts.js":"""const express = require('express');
const { Account } = require('../models');
const auth = require('../middleware/auth');

const router = express.Router();

router.put('/accounts/:id', auth, async (req, res) => {
  const id = Number(req.params.id);
  if (id !== req.user.accountId) {
    return res.status(403).json({ message: 'not your account' });
  }
  const [count] = await Account.update(req.body, { where: { id } });
  if (count === 0) {
    return res.status(404).json({ message: 'no such account' });
  }
  const account = await Account.findByPk(id);
  return res.json(account);
});

module.exports = router;
"""},("routes/accounts.js","Account.update(req.body, { where: { id } })"))

add("pos","javascript","express-sequelize",{"routes/orders.js":"""const express = require('express');
const { Order } = require('../models');
const auth = require('../middleware/auth');

const router = express.Router();

router.post('/orders', auth, async (req, res, next) => {
  try {
    if (!Array.isArray(req.body.lines) || req.body.lines.length === 0) {
      return res.status(400).json({ message: 'lines required' });
    }
    const order = await Order.create({
      ...req.body,
      customerId: req.user.id,
    });
    res.status(201).json(order);
  } catch (e) {
    next(e);
  }
});

router.get('/orders', auth, async (req, res) => {
  const orders = await Order.findAll({ where: { customerId: req.user.id } });
  res.json(orders);
});

module.exports = router;
"""},("routes/orders.js","      ...req.body,"))

add("pos","javascript","express-prisma",{"routes/members.js":"""const express = require('express');
const { PrismaClient } = require('@prisma/client');
const { requireLogin } = require('../middleware/auth');

const prisma = new PrismaClient();
const router = express.Router();

router.patch('/members/me', requireLogin, async (req, res) => {
  const current = await prisma.member.findUnique({
    where: { id: req.user.id },
  });
  if (!current) {
    return res.status(404).json({ error: 'member missing' });
  }
  const member = await prisma.member.update({
    where: { id: req.user.id },
    data: req.body,
  });
  res.json(member);
});

module.exports = router;
"""},("routes/members.js","    data: req.body,"))

add("pos","javascript","koa-mongoose",{"routes/posts.js":"""const Router = require('@koa/router');
const Post = require('../models/post');

const router = new Router({ prefix: '/posts' });

router.get('/', async (ctx) => {
  ctx.body = await Post.find({ published: true }).limit(50);
});

router.post('/', async (ctx) => {
  if (!ctx.state.user) {
    ctx.throw(401, 'login required');
  }
  const post = new Post(ctx.request.body);
  post.author = ctx.state.user.id;
  await post.save();
  ctx.status = 201;
  ctx.body = post;
});

module.exports = router;
"""},("routes/posts.js","new Post(ctx.request.body)"))

add("pos","javascript","koa-prisma",{"routes/settings.js":"""const Router = require('@koa/router');
const { PrismaClient } = require('@prisma/client');

const prisma = new PrismaClient();
const router = new Router({ prefix: '/settings' });

router.put('/', async (ctx) => {
  const user = ctx.state.user;
  if (!user) {
    ctx.throw(401);
  }
  const payload = ctx.request.body;
  const settings = await prisma.settings.update({
    where: { userId: user.id },
    data: payload,
  });
  ctx.body = settings;
});

router.get('/', async (ctx) => {
  ctx.body = await prisma.settings.findUnique({
    where: { userId: ctx.state.user.id },
  });
});

module.exports = router;
"""},("routes/settings.js","    data: payload,"))

add("pos","javascript","express-mongoose",{"routes/members.js":"""const express = require('express');
const members = require('../services/members');
const { requireLogin } = require('../middleware/auth');

const router = express.Router();

router.patch('/members/:id', requireLogin, async (req, res, next) => {
  try {
    if (req.params.id !== req.user.id) {
      return res.status(403).json({ error: 'forbidden' });
    }
    const member = await members.updateMember(req.params.id, req.body);
    res.json(member);
  } catch (err) {
    next(err);
  }
});

module.exports = router;
""","services/members.js":"""const Member = require('../models/member');

async function getMember(id) {
  const member = await Member.findById(id).lean();
  if (!member) {
    const err = new Error('member not found');
    err.status = 404;
    throw err;
  }
  return member;
}

async function updateMember(id, patch) {
  await getMember(id);
  return Member.findOneAndUpdate(
    { _id: id },
    { $set: patch },
    { new: true }
  );
}

module.exports = { getMember, updateMember };
"""},("services/members.js","    { $set: patch },"))

add("pos","python","django",{"billing/views.py":"""import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import Invoice


@csrf_exempt
@require_POST
def create_invoice(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "login required"}, status=401)
    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"error": "bad json"}, status=400)
    if "customer_id" not in data:
        return JsonResponse({"error": "customer_id required"}, status=400)
    invoice = Invoice.objects.create(**data)
    return JsonResponse({"id": invoice.pk, "status": invoice.status}, status=201)
"""},("billing/views.py","Invoice.objects.create(**data)"))

add("pos","python","django",{"crm/views.py":"""import json

from django.http import Http404, JsonResponse
from django.views.decorators.http import require_http_methods

from .models import Customer


@require_http_methods(["PATCH"])
def update_customer(request, pk):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "login required"}, status=401)
    data = json.loads(request.body or "{}")
    rows = Customer.objects.filter(pk=pk, owner=request.user).update(**data)
    if rows == 0:
        raise Http404("customer not found")
    customer = Customer.objects.get(pk=pk)
    return JsonResponse({"id": customer.pk, "name": customer.name})
"""},("crm/views.py",".update(**data)"))

add("pos","python","django-rest-framework",{"staff/serializers.py":"""from rest_framework import serializers, viewsets
from rest_framework.permissions import IsAuthenticated

from .models import Employee


class EmployeeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Employee
        fields = "__all__"


class EmployeeViewSet(viewsets.ModelViewSet):
    serializer_class = EmployeeSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Employee.objects.filter(user=self.request.user)
"""},("staff/serializers.py",'fields = "__all__"'))

add("pos","python","django-rest-framework",{"shop/api.py":"""from rest_framework import generics, serializers
from rest_framework.permissions import IsAuthenticated

from .models import Customer


class CustomerSerializer(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        exclude = ("created_at",)

    def get_display_name(self, obj):
        return f"{obj.first_name} {obj.last_name}".strip()


class CustomerDetail(generics.RetrieveUpdateAPIView):
    serializer_class = CustomerSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return Customer.objects.get(user=self.request.user)
"""},("shop/api.py",'exclude = ("created_at",)'))

add("pos","python","flask-sqlalchemy",{"app/routes.py":"""from flask import Blueprint, jsonify, request

from .extensions import db
from .models import User

bp = Blueprint("users", __name__)


@bp.route("/users", methods=["POST"])
def create_user():
    payload = request.get_json(silent=True)
    if not payload or "email" not in payload:
        return jsonify({"error": "email required"}), 400
    if User.query.filter_by(email=payload["email"]).first():
        return jsonify({"error": "exists"}), 409
    user = User(**request.get_json())
    db.session.add(user)
    db.session.commit()
    return jsonify({"id": user.id, "email": user.email}), 201
"""},("app/routes.py","user = User(**request.get_json())"))

add("pos","python","flask-sqlalchemy",{"app/profile.py":"""from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from .extensions import db

bp = Blueprint("profile", __name__)


@bp.route("/profile", methods=["PUT"])
@login_required
def update_profile():
    user = current_user
    body = request.get_json() or {}
    for key, value in body.items():
        setattr(user, key, value)
    db.session.commit()
    return jsonify({"id": user.id, "name": user.name, "email": user.email})


@bp.route("/profile", methods=["GET"])
@login_required
def read_profile():
    return jsonify({"id": current_user.id, "name": current_user.name})
"""},("app/profile.py","        setattr(user, key, value)"))

# ---------- negatives ----------
add("neg","javascript","express-mongoose",{"routes/users.js":"""const express = require('express');
const bcrypt = require('bcrypt');
const User = require('../models/user');

const router = express.Router();

router.post('/register', async (req, res, next) => {
  try {
    const { name, email, password } = req.body;
    if (!email || !password) {
      return res.status(400).json({ error: 'email and password required' });
    }
    const existing = await User.findOne({ email });
    if (existing) {
      return res.status(409).json({ error: 'email taken' });
    }
    const hash = await bcrypt.hash(password, 10);
    const user = await User.create({ name, email, password: hash });
    res.status(201).json({ id: user._id, email: user.email });
  } catch (err) {
    next(err);
  }
});

module.exports = router;
"""})

add("neg","javascript","express-mongoose",{"routes/profile.js":"""const express = require('express');
const pick = require('lodash/pick');
const Profile = require('../models/profile');
const { requireLogin } = require('../middleware/auth');

const router = express.Router();

router.put('/me', requireLogin, async (req, res, next) => {
  try {
    const changes = pick(req.body, ['displayName', 'bio', 'timezone']);
    const updated = await Profile.findOneAndUpdate(
      { owner: req.user.id },
      changes,
      { new: true, runValidators: true }
    );
    if (!updated) return res.status(404).end();
    res.json(updated);
  } catch (err) {
    next(err);
  }
});

module.exports = router;
"""})

add("neg","javascript","express-mongoose",{"routes/members.js":"""const express = require('express');
const Member = require('../models/member');
const { EDITABLE } = require('../config/fields');
const { requireLogin } = require('../middleware/auth');

const router = express.Router();

router.patch('/members/me', requireLogin, async (req, res, next) => {
  try {
    const member = await Member.findById(req.user.id);
    if (!member) return res.status(404).end();
    const entries = Object.entries(req.body).filter(([key]) =>
      EDITABLE.member.includes(key)
    );
    Object.assign(member, Object.fromEntries(entries));
    await member.save();
    res.json(member);
  } catch (err) {
    next(err);
  }
});

module.exports = router;
""","config/fields.js":"""// Fields a member may change on their own record.
const EDITABLE = {
  member: ['displayName', 'avatarUrl', 'locale', 'newsletter'],
  team: ['title', 'description'],
  project: ['name', 'summary', 'archived'],
  comment: ['text'],
  invite: ['message'],
  badge: ['label'],
};

module.exports = { EDITABLE };

// Keep this list in step with the member schema when columns are added,
// and review additions together with the access rules for the new column.
// Each entry is a plain property name, with no nested paths.
"""})

add("neg","javascript","express-sequelize",{"routes/accounts.js":"""const express = require('express');
const { Account } = require('../models');
const auth = require('../middleware/auth');

const router = express.Router();

router.put('/accounts/:id', auth, async (req, res) => {
  const id = Number(req.params.id);
  if (id !== req.user.accountId) {
    return res.status(403).json({ message: 'not your account' });
  }
  const [count] = await Account.update(req.body, {
    where: { id },
    fields: ['nickname', 'locale'],
  });
  if (count === 0) {
    return res.status(404).json({ message: 'no such account' });
  }
  const account = await Account.findByPk(id);
  return res.json(account);
});

module.exports = router;
"""})

add("neg","javascript","express-sequelize",{"routes/orders.js":"""const express = require('express');
const { z } = require('zod');
const { Order } = require('../models');
const auth = require('../middleware/auth');

const router = express.Router();

const OrderInput = z
  .object({
    note: z.string().max(500).optional(),
    shippingMethod: z.enum(['standard', 'express']),
    lines: z.array(z.object({ sku: z.string(), qty: z.number().int().min(1) })).min(1),
  })
  .strict();

router.post('/orders', auth, async (req, res, next) => {
  try {
    const input = OrderInput.parse(req.body);
    const order = await Order.create({ ...input, customerId: req.user.id });
    res.status(201).json(order);
  } catch (e) {
    next(e);
  }
});

module.exports = router;
"""})

add("neg","javascript","express-prisma",{"routes/members.js":"""const express = require('express');
const { PrismaClient } = require('@prisma/client');
const { requireLogin } = require('../middleware/auth');

const prisma = new PrismaClient();
const router = express.Router();

const selfFields = ['bio', 'city'];

function pickFields(source, names) {
  return Object.fromEntries(names.filter((n) => n in source).map((n) => [n, source[n]]));
}

router.patch('/members/:id', requireLogin, async (req, res) => {
  const isAdmin = req.user.role === 'admin';
  if (!isAdmin && req.params.id !== req.user.id) {
    return res.status(403).json({ error: 'forbidden' });
  }
  const data = isAdmin ? req.body : pickFields(req.body, selfFields);
  const member = await prisma.member.update({
    where: { id: req.params.id },
    data,
  });
  res.json(member);
});

module.exports = router;
"""})

add("neg","javascript","koa-mongoose",{"routes/posts.js":"""const Router = require('@koa/router');
const Post = require('../models/post');

const router = new Router({ prefix: '/posts' });

router.post('/', async (ctx) => {
  if (!ctx.state.user) {
    ctx.throw(401, 'login required');
  }
  const input = ctx.request.body;
  const post = new Post({
    title: input.title,
    body: input.body,
    tags: Array.isArray(input.tags) ? input.tags.slice(0, 5) : [],
    author: ctx.state.user.id,
  });
  await post.save();
  ctx.status = 201;
  ctx.body = post;
});

router.get('/', async (ctx) => {
  ctx.body = await Post.find({ published: true }).limit(50);
});

module.exports = router;
"""})

add("neg","javascript","koa-prisma",{"routes/settings.js":"""const Router = require('@koa/router');
const Joi = require('joi');
const { PrismaClient } = require('@prisma/client');

const prisma = new PrismaClient();
const router = new Router({ prefix: '/settings' });

const schema = Joi.object({
  theme: Joi.string().valid('light', 'dark'),
  emailDigest: Joi.boolean(),
  pageSize: Joi.number().integer().min(10).max(100),
});

router.put('/', async (ctx) => {
  const user = ctx.state.user;
  if (!user) {
    ctx.throw(401);
  }
  const { value, error } = schema.validate(ctx.request.body, {
    stripUnknown: true,
  });
  if (error) {
    ctx.throw(400, error.message);
  }
  ctx.body = await prisma.settings.update({
    where: { userId: user.id },
    data: value,
  });
});

module.exports = router;
"""})

add("neg","python","django",{"directory/views.py":"""from django import forms
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from .models import Contact


class ContactForm(forms.ModelForm):
    class Meta:
        model = Contact
        fields = ["name", "email", "phone"]


@require_POST
def add_contact(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "login required"}, status=401)
    form = ContactForm(request.POST)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors}, status=400)
    contact = form.save(commit=False)
    contact.owner = request.user
    contact.save()
    return JsonResponse({"id": contact.pk}, status=201)
"""})

add("neg","python","django",{"billing/views.py":"""import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import Invoice

ACCEPTED = ("customer_id", "amount", "currency", "due_date")


@csrf_exempt
@require_POST
def create_invoice(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "login required"}, status=401)
    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"error": "bad json"}, status=400)
    values = {key: data[key] for key in ACCEPTED if key in data}
    invoice = Invoice.objects.create(**values)
    return JsonResponse({"id": invoice.pk, "status": invoice.status}, status=201)
"""})

add("neg","python","django-rest-framework",{"staff/serializers.py":"""from rest_framework import serializers, viewsets
from rest_framework.permissions import IsAuthenticated

from .models import Employee


class EmployeeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Employee
        fields = ("id", "name", "title", "is_staff", "salary")
        read_only_fields = ("id", "is_staff", "salary")


class EmployeeViewSet(viewsets.ModelViewSet):
    serializer_class = EmployeeSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Employee.objects.filter(user=self.request.user)
"""})

add("neg","python","django-rest-framework",{"shop/api.py":"""from rest_framework import generics, serializers
from rest_framework.permissions import IsAuthenticated

from .models import Customer


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = "__all__"
        extra_kwargs = {
            "id": {"read_only": True},
            "user": {"read_only": True},
            "loyalty_tier": {"read_only": True},
            "credit_limit": {"read_only": True},
            "created_at": {"read_only": True},
        }


class CustomerDetail(generics.RetrieveUpdateAPIView):
    serializer_class = CustomerSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return Customer.objects.get(user=self.request.user)
"""})

add("neg","python","flask-sqlalchemy",{"app/routes.py":"""from flask import Blueprint, jsonify, request
from marshmallow import EXCLUDE, Schema, fields

from .extensions import db
from .models import User

bp = Blueprint("users", __name__)


class SignupSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    email = fields.Email(required=True)
    name = fields.Str(required=True)
    is_admin = fields.Bool(dump_only=True)


@bp.route("/users", methods=["POST"])
def create_user():
    data = SignupSchema().load(request.get_json(silent=True) or {})
    user = User(**data)
    db.session.add(user)
    db.session.commit()
    return jsonify({"id": user.id, "email": user.email}), 201
"""})

add("neg","python","flask-sqlalchemy",{"app/profile.py":"""from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from .extensions import db

bp = Blueprint("profile", __name__)

EDITABLE = {"name", "bio", "timezone"}


@bp.route("/profile", methods=["PUT"])
@login_required
def update_profile():
    user = current_user
    body = request.get_json() or {}
    for key, value in body.items():
        if key in EDITABLE:
            setattr(user, key, value)
    db.session.commit()
    return jsonify({"id": user.id, "name": user.name, "email": user.email})


@bp.route("/profile", methods=["GET"])
@login_required
def read_profile():
    return jsonify({"id": current_user.id, "name": current_user.name})
"""})

add("neg","python","flask-sqlalchemy",{"app/admin.py":"""from functools import wraps

from flask import Blueprint, abort, jsonify, request
from flask_login import current_user, login_required

from .extensions import db
from .models import User

bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return fn(*args, **kwargs)

    return wrapper


@bp.route("/users", methods=["POST"])
@login_required
@admin_required
def create_user():
    user = User(**request.get_json())
    db.session.add(user)
    db.session.commit()
    return jsonify({"id": user.id, "email": user.email}), 201
"""})

random.seed(31415)
random.shuffle(C)
out = []
for i, c in enumerate(C, 1):
    cid = "h3-%02d" % i
    d = os.path.join(B, cid)
    os.makedirs(d, exist_ok=True)
    for name, txt in c["files"].items():
        p = os.path.join(d, name)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w").write(txt)
    tf = tl = None
    if c["truth"]:
        tf, marker = c["truth"]
        lines = c["files"][tf].split("\n")
        hits = [n for n, l in enumerate(lines, 1) if marker in l]
        assert len(hits) == 1, (cid, marker, hits)
        tl = hits[0]
    out.append(dict(id=cid, kind=c["kind"], language=c["lang"], framework=c["fw"], truth_file=tf, truth_line=tl))
json.dump(out, open("/private/tmp/claude-501/heldout-api3-author/cases.json", "w"), indent=1)
