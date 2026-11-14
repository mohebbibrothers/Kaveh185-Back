"""مقادیر ثابت عملیات‌های حسابرسی در سامانهٔ کاوه ۱۸۵."""

from __future__ import annotations

from django.db import models


class AuditAction(models.TextChoices):
    """انواع رخدادهای ثبت‌شده در زنجیرهٔ هش حسابرسی."""

    USER_REGISTERED = "user.registered", "ثبت‌نام شرکت‌کننده"
    USER_LOGGED_IN = "user.logged_in", "ورود کاربر"
    USER_UPDATED = "user.updated", "ویرایش اطلاعات کاربر"
    USER_ROLE_CHANGED = "user.role_changed", "تغییر نقش کاربر"
    SESSION_REVOKED = "session.revoked", "ابطال نشست کاربری"
    MFA_ENROLLED = "mfa.enrolled", "فعال‌سازی تأیید دومرحله‌ای"
    MFA_VERIFIED = "mfa.verified", "تأیید دومرحله‌ای موفق"
    RISK_REVIEWED = "risk.reviewed", "بررسی سیگنال ریسک امنیتی"

    MOSQUE_CREATED = "mosque.created", "ایجاد مسجد"
    MOSQUE_UPDATED = "mosque.updated", "ویرایش مسجد"
    MOSQUE_DELETED = "mosque.deleted", "غیرفعال‌سازی مسجد"
    MOSQUE_SEEDED = "mosque.seeded", "بارگذاری اولیه مساجد حوزه ۱۸۵"

    EXAM_CONFIG_UPDATED = "exam.config_updated", "تغییر تنظیمات آزمون"
    QUESTION_CREATED = "question.created", "ایجاد سوال در بانک سوال"
    QUESTION_UPDATED = "question.updated", "ویرایش سوال یا کلید"
    QUESTION_DELETED = "question.deleted", "غیرفعال‌سازی سوال"
    EXAM_REGRADED = "exam.regraded", "بازتصحیح کارنامه‌های آزمون"
    EXAM_STARTED = "exam.started", "شروع آزمون توسط شرکت‌کننده"
    EXAM_COMPLETED = "exam.completed", "پایان آزمون توسط شرکت‌کننده"
    EXAM_TIMED_OUT = "exam.timed_out", "اتمام مهلت زمانی آزمون"

    REPORT_EXPORTED = "report.exported", "خروجی اکسل گزارش شرکت‌کنندگان"
    AUDIT_EXPORTED = "audit.exported", "خروجی بسته فارنزیک حسابرسی"
