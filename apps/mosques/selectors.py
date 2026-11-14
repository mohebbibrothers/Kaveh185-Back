"""سلکتورهای خواندن فهرست مساجد و محاسبهٔ رنکینگ لحظه‌ای مشارکت."""

from __future__ import annotations

from typing import Any

from django.db.models import Avg, Count, Q, QuerySet

from apps.core.cache import cache_get_or_set_swr
from apps.core.exceptions import NotFoundDomainError

from .choices import MosqueTier
from .models import Mosque


def get_active_mosques_dropdown() -> list[dict[str, Any]]:
    """دریافت لیست کشویی مساجد فعال برای فرم ثبت‌نام شرکت‌کنندگان (همراه با کش SWR)."""

    def _produce() -> list[dict[str, Any]]:
        rows = Mosque.objects.filter(is_active=True).order_by("display_order", "name")
        return [
            {
                "id": m.id,
                "code": m.code,
                "name": m.name,
                "neighborhood": m.neighborhood,
                "display_order": m.display_order,
                "completed_participants_count": m.completed_exam_count,
            }
            for m in rows
        ]

    return cache_get_or_set_swr(
        domain="mosques",
        key_suffix="dropdown",
        producer=_produce,
    )


def get_mosque_leaderboard_snapshot() -> dict[str, Any]:
    """محاسبهٔ رنکینگ لحظه‌ای مساجد بر اساس تعداد مشارکت‌کنندگان در آزمون."""

    def _produce() -> dict[str, Any]:
        from apps.exam.choices import ExamAttemptStatus

        finished_statuses = [ExamAttemptStatus.COMPLETED, ExamAttemptStatus.TIMED_OUT]
        mosques = list(
            Mosque.objects.filter(is_active=True).annotate(
                live_registered=Count(
                    "participants",
                    filter=Q(participants__is_active=True, participants__role="participant"),
                    distinct=True,
                ),
                live_completed=Count(
                    "participants__exam_attempt",
                    filter=Q(
                        participants__is_active=True,
                        participants__exam_attempt__status__in=finished_statuses,
                    ),
                    distinct=True,
                ),
                avg_score=Avg(
                    "participants__exam_attempt__total_score",
                    filter=Q(
                        participants__is_active=True,
                        participants__exam_attempt__status__in=finished_statuses,
                    ),
                ),
                avg_correct=Avg(
                    "participants__exam_attempt__correct_count",
                    filter=Q(
                        participants__is_active=True,
                        participants__exam_attempt__status__in=finished_statuses,
                    ),
                ),
                avg_duration=Avg(
                    "participants__exam_attempt__duration_seconds",
                    filter=Q(
                        participants__is_active=True,
                        participants__exam_attempt__status__in=finished_statuses,
                    ),
                ),
            )
        )

        # انتخاب بیشینهٔ شمارندهٔ denormalized و شمارش زنده برای تضمین دقت کامل
        enriched: list[dict[str, Any]] = []
        for m in mosques:
            completed_cnt = max(
                int(m.completed_exam_count), int(getattr(m, "live_completed", 0) or 0)
            )
            registered_cnt = max(
                int(m.registered_count), int(getattr(m, "live_registered", 0) or 0)
            )
            avg_score_val = round(float(getattr(m, "avg_score", 0.0) or 0.0), 2)
            avg_correct_val = round(float(getattr(m, "avg_correct", 0.0) or 0.0), 2)
            avg_duration_val = round(float(getattr(m, "avg_duration", 0.0) or 0.0), 1)
            enriched.append(
                {
                    "mosque_id": m.id,
                    "code": m.code,
                    "name": m.name,
                    "neighborhood": m.neighborhood,
                    "imam_name": m.imam_name,
                    "commander_name": m.commander_name,
                    "completed_participants_count": completed_cnt,
                    "registered_users_count": registered_cnt,
                    "target_participants": m.target_participants,
                    "average_score": avg_score_val,
                    "average_correct_answers": avg_correct_val,
                    "average_duration_seconds": avg_duration_val,
                    "display_order": m.display_order,
                }
            )

        # مرتب‌سازی اصلی دقیقاً بر اساس تعداد مشارکت در آزمون (completed_participants_count نزولی)
        enriched.sort(
            key=lambda item: (
                -item["completed_participants_count"],
                -item["registered_users_count"],
                -item["average_score"],
                item["display_order"],
                item["mosque_id"],
            )
        )

        total_completed = sum(x["completed_participants_count"] for x in enriched)
        total_registered = sum(x["registered_users_count"] for x in enriched)

        leaderboard: list[dict[str, Any]] = []
        for idx, item in enumerate(enriched, start=1):
            completed_cnt = item["completed_participants_count"]
            target = max(1, int(item["target_participants"] or 500))
            share_pct = (
                round((completed_cnt / total_completed) * 100.0, 2) if total_completed > 0 else 0.0
            )
            target_pct = round(min(100.0, (completed_cnt / target) * 100.0), 2)
            if idx == 1 and completed_cnt > 0:
                tier = MosqueTier.GOLD
            elif idx in {2, 3} and completed_cnt > 0:
                tier = MosqueTier.SILVER
            elif idx <= 6 and completed_cnt > 0:
                tier = MosqueTier.BRONZE
            else:
                tier = MosqueTier.RISING

            leaderboard.append(
                {
                    "rank": idx,
                    "tier": tier,
                    "tier_label": MosqueTier(tier).label,
                    "mosque_id": item["mosque_id"],
                    "code": item["code"],
                    "name": item["name"],
                    "neighborhood": item["neighborhood"],
                    "imam_name": item["imam_name"],
                    "commander_name": item["commander_name"],
                    "completed_participants_count": completed_cnt,
                    "registered_users_count": item["registered_users_count"],
                    "target_participants": item["target_participants"],
                    "target_progress_percent": target_pct,
                    "participation_share_percent": share_pct,
                    "average_score": item["average_score"],
                    "average_correct_answers": item["average_correct_answers"],
                    "average_duration_seconds": item["average_duration_seconds"],
                }
            )

        return {
            "organizer": "حوزه مقاومت بسیج ۱۸۵ شهید کاوه",
            "total_mosques": len(leaderboard),
            "total_completed_participants": total_completed,
            "total_registered_users": total_registered,
            "leaderboard": leaderboard,
        }

    return cache_get_or_set_swr(
        domain="mosques",
        key_suffix="leaderboard",
        producer=_produce,
    )


get_mosque_leaderboard = get_mosque_leaderboard_snapshot


def get_active_mosque_by_id(mosque_id: int) -> Mosque:
    """واکشی مسجد فعال با شناسه یا پرتاب خطای ۴۰۴."""
    mosque = Mosque.objects.filter(pk=mosque_id, is_active=True).first()
    if mosque is None:
        raise NotFoundDomainError(
            "مسجد انتخاب‌شده یافت نشد یا غیرفعال است.", code="mosque_not_found"
        )
    return mosque


def get_admin_mosques_queryset(*, search: str = "", is_active: str = "") -> QuerySet[Mosque]:
    """کوئری‌ست مدیریت مساجد برای پنل ادمین (شامل فعال و غیرفعال)."""
    qs = Mosque.all_objects.all().order_by("display_order", "id")
    if is_active.lower() in {"true", "1"}:
        qs = qs.filter(is_active=True)
    elif is_active.lower() in {"false", "0"}:
        qs = qs.filter(is_active=False)
    if search.strip():
        q = search.strip()
        qs = qs.filter(
            Q(name__icontains=q)
            | Q(code__icontains=q)
            | Q(neighborhood__icontains=q)
            | Q(imam_name__icontains=q)
            | Q(commander_name__icontains=q)
        )
    return qs


def get_admin_mosque_by_id(mosque_id: int) -> Mosque:
    """واکشی مسجد در پنل ادمین (حتی اگر غیرفعال باشد)."""
    mosque = Mosque.all_objects.filter(pk=mosque_id).first()
    if mosque is None:
        raise NotFoundDomainError("مسجد مورد نظر یافت نشد.", code="mosque_not_found")
    return mosque
