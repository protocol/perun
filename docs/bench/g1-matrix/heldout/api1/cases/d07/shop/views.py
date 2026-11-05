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
