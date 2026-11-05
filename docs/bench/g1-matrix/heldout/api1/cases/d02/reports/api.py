from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Report
from .serializers import ReportSerializer


class ReportList(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Report.objects.filter(author=request.user)
        return Response(ReportSerializer(qs, many=True).data)


class ReportDetail(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        report = get_object_or_404(Report, pk=pk)
        return Response(ReportSerializer(report).data)

    def delete(self, request, pk):
        report = get_object_or_404(Report, pk=pk, author=request.user)
        report.delete()
        return Response(status=204)
