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
