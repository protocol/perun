from django import forms
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
