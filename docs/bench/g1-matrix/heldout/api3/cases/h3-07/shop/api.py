from rest_framework import generics, serializers
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
