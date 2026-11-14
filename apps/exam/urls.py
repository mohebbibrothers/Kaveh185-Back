"""مسیرهای API موتور آزمون، کارنامه، استعلام رسید و مدیریت بانک سوال."""

from __future__ import annotations

from django.urls import path

from .views import (
    AdminExamConfigurationAPIView,
    AdminQuestionBulkImportAPIView,
    AdminQuestionDetailAPIView,
    AdminQuestionListCreateAPIView,
    AdminQuestionSeedDefaultsAPIView,
    AdminRegradeAllAttemptsAPIView,
    ExamCurrentAttemptAPIView,
    ExamFinishAPIView,
    ExamReportCardAPIView,
    ExamStartAPIView,
    ExamSubmitAnswerAPIView,
    PublicExamStatusAPIView,
    PublicReceiptVerifyAPIView,
)

app_name = "exam"

urlpatterns = [
    # مسیرهای عمومی و شرکت‌کنندگان
    path("status/", PublicExamStatusAPIView.as_view(), name="status"),
    path("start/", ExamStartAPIView.as_view(), name="start"),
    path("current/", ExamCurrentAttemptAPIView.as_view(), name="current"),
    path("answer/", ExamSubmitAnswerAPIView.as_view(), name="answer"),
    path("finish/", ExamFinishAPIView.as_view(), name="finish"),
    path("report-card/", ExamReportCardAPIView.as_view(), name="report-card"),
    path(
        "receipt/<str:tracking_code>/", PublicReceiptVerifyAPIView.as_view(), name="receipt-verify"
    ),
    # مسیرهای مدیریت آزمون و بانک سوال توسط ادمین
    path("admin/config/", AdminExamConfigurationAPIView.as_view(), name="admin-config"),
    path("admin/questions/", AdminQuestionListCreateAPIView.as_view(), name="admin-questions"),
    path(
        "admin/questions/bulk/",
        AdminQuestionBulkImportAPIView.as_view(),
        name="admin-questions-bulk",
    ),
    path(
        "admin/questions/seed-defaults/",
        AdminQuestionSeedDefaultsAPIView.as_view(),
        name="admin-questions-seed",
    ),
    path(
        "admin/questions/<int:question_id>/",
        AdminQuestionDetailAPIView.as_view(),
        name="admin-question-detail",
    ),
    path("admin/regrade/", AdminRegradeAllAttemptsAPIView.as_view(), name="admin-regrade"),
]
