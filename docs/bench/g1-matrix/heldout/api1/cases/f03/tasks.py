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
        task = Task.get_by_id(payload["task_id"])
    except DoesNotExist:
        return jsonify(error="missing"), 404
    task.done = True
    task.save()
    return jsonify(task.serialize())
