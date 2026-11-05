from rest_framework import serializers, viewsets
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
