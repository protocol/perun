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
