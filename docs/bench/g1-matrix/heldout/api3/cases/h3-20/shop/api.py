from rest_framework import generics, serializers
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
