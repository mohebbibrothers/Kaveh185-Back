"""یکپارچگیِ شمارنده‌های مسجد — باگی که ادمین گزارش کرد.

«وقتی کاربران را دستی از پنل ادمین پاک می‌کنم، چرا هنوز در جدول مساجد
شمرده می‌شوند؟»

سه علتِ ریشه‌ای داشت و این فایل هر سه را قفل می‌کند:
  ۱) شمارنده فقط بالا می‌رفت؛ هیچ‌کس پایین نمی‌آوردش.
  ۲) جدول `max(شمارنده, شمارشِ زنده)` می‌گرفت، پس عددِ کهنه همیشه برنده بود.
  ۳) حذفِ گروهیِ جنگو سیگنالِ `post_save` نمی‌فرستد و به شمارنده نمی‌رسید.
"""

from __future__ import annotations

from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.authentication.choices import UserRole
from apps.authentication.models import User
from apps.exam.choices import ExamAttemptStatus
from apps.exam.models import ExamAttempt
from apps.mosques.models import Mosque
from apps.mosques.services import (
    live_completed_exam_count,
    live_registered_count,
    recount_mosque_stats,
)
from tests.factories import create_test_mosque, create_test_participant

#: شمارندهٔ سراسری برای ساختنِ کدِ یکتای مسجد در هر تست.
#: `create_test_mosque` کد را از `seq` می‌سازد و `get_or_create` است؛ اگر seq
#: تکرار شود، همان مسجدِ قبلی برمی‌گردد و تست‌ها به هم نشت می‌کنند.
_SEQ = {"mosque": 400}


def _unique_mosque() -> Mosque:
    """مسجدِ تازه با کدِ یکتا (نه `get_or_create`ِ همان کدِ قبلی)."""
    _SEQ["mosque"] += 1
    return create_test_mosque(seq=_SEQ["mosque"])


def _mosque_with_users(count: int, *, seq_start: int = 400) -> tuple[Mosque, list[User]]:
    """یک مسجدِ تازه + `count` شرکت‌کنندهٔ فعال، همه با ثبت‌نامِ واقعی."""
    mosque = _unique_mosque()
    users = [create_test_participant(seq=seq_start + i, mosque=mosque) for i in range(count)]
    return mosque, users


@pytest.mark.django_db
def test_deleting_a_user_lowers_the_counter_immediately() -> None:
    """حذفِ یک کاربر (مثلِ پنل ادمین) فوراً شمارنده را پایین می‌آورد."""
    mosque, users = _mosque_with_users(3)
    mosque.refresh_from_db()
    assert mosque.registered_count == 3

    users[0].delete()

    mosque.refresh_from_db()
    assert mosque.registered_count == 2
    assert live_registered_count(mosque.pk) == 2


@pytest.mark.django_db
def test_bulk_queryset_delete_is_handled() -> None:
    """حذفِ گروهی (`QuerySet.delete()`) هم باید شمارنده را درست کند.

    پنل ادمین با «حذفِ انتخاب‌شده‌ها» دقیقاً همین کار را می‌کند؛ در نسخهٔ
    قبلی هیچ سیگنالی شمارنده را پایین نمی‌آورد.
    """
    mosque, _ = _mosque_with_users(4)
    mosque.refresh_from_db()
    assert mosque.registered_count == 4

    User.objects.filter(mosque=mosque).delete()

    mosque.refresh_from_db()
    assert mosque.registered_count == 0


@pytest.mark.django_db
def test_soft_delete_and_role_change_are_reflected() -> None:
    """غیرفعال‌کردن یا تغییرِ نقش، «ثبت‌نامی» را کم می‌کند — نه اینکه رها شود."""
    mosque, users = _mosque_with_users(2)

    users[0].is_active = False
    users[0].save(update_fields=["is_active"])
    mosque.refresh_from_db()
    assert mosque.registered_count == 1

    users[1].role = UserRole.OPERATOR
    users[1].save(update_fields=["role"])
    mosque.refresh_from_db()
    assert mosque.registered_count == 0


@pytest.mark.django_db
def test_moving_user_to_another_mosque_updates_both() -> None:
    """انتقالِ کاربر بین دو مسجد: یکی کم، دیگری زیاد — بدونِ شمارشِ دوباره."""
    first, users = _mosque_with_users(2)
    second = _unique_mosque()

    users[0].mosque = second
    users[0].save(update_fields=["mosque"])

    first.refresh_from_db()
    second.refresh_from_db()
    assert first.registered_count == 1
    assert second.registered_count == 1


@pytest.mark.django_db
def test_leaderboard_reads_live_counts_not_stale_columns(api_client) -> None:
    """جدول باید شمارشِ زنده را نشان دهد، نه عددِ بادکردهٔ ستون را.

    این همان مسیرِ `max(شمارنده, زنده)` است که باگ را می‌پوشاند.
    """
    mosque, users = _mosque_with_users(3)
    _unique_mosque()

    # خرابکاریِ عمدی: ستون را باد می‌کنیم، مثلِ چیزی که باگِ قبلی می‌ساخت.
    Mosque.objects.filter(pk=mosque.pk).update(registered_count=99, completed_exam_count=99)

    data = api_client.get("/api/v1/mosques/leaderboard/").json()["data"]
    row = next(r for r in data["leaderboard"] if r["mosque_id"] == mosque.pk)
    assert row["registered_users_count"] == 3
    assert row["completed_participants_count"] == 0
    assert users  # کاربران واقعی‌اند؛ عدد از آن‌ها می‌آید


@pytest.mark.django_db
def test_recount_command_reports_then_fixes() -> None:
    """`recount_mosque_stats` پیش‌فرض فقط گزارش می‌دهد؛ با `--fix` اصلاح می‌کند."""
    mosque, _ = _mosque_with_users(2)
    Mosque.objects.filter(pk=mosque.pk).update(registered_count=50)

    out = StringIO()
    call_command("recount_mosque_stats", stdout=out)
    assert "50" in out.getvalue() and "2" in out.getvalue()
    mosque.refresh_from_db()
    assert mosque.registered_count == 50  # بدونِ --fix چیزی نوشته نشد

    call_command("recount_mosque_stats", "--fix", stdout=StringIO())
    mosque.refresh_from_db()
    assert mosque.registered_count == 2


@pytest.mark.django_db
def test_recount_service_heals_all_mosques() -> None:
    """بازشمارشِ سرویسی همهٔ مساجد را می‌بیند و تعدادِ اصلاح‌شده را برمی‌گرداند."""
    mosque, _ = _mosque_with_users(2)
    other = _unique_mosque()
    Mosque.objects.filter(pk=mosque.pk).update(registered_count=7)
    Mosque.objects.filter(pk=other.pk).update(completed_exam_count=5)

    result = recount_mosque_stats()

    assert result["fixed"] == 2
    mosque.refresh_from_db()
    other.refresh_from_db()
    assert mosque.registered_count == 2
    assert other.completed_exam_count == 0


@pytest.mark.django_db
def test_completed_counter_follows_finished_attempts_only() -> None:
    """فقط کارنامهٔ تمام‌شده شمرده می‌شود؛ آزمونِ نیمه‌کاره نه."""
    mosque, users = _mosque_with_users(2)
    for i, status in enumerate([ExamAttemptStatus.IN_PROGRESS, ExamAttemptStatus.COMPLETED]):
        ExamAttempt.objects.create(
            user=users[i],
            mosque=mosque,
            tracking_code=f"TRK-CNT-{i}",
            status=status,
            expires_at=timezone.now() + timedelta(minutes=5),
            completed_at=timezone.now() if status == ExamAttemptStatus.COMPLETED else None,
        )

    mosque.refresh_from_db()
    assert mosque.completed_exam_count == 1
    assert live_completed_exam_count(mosque.pk) == 1

    # وقتی آزمونِ نیمه‌کاره تمام می‌شود، شمارنده بالا می‌رود.
    attempt = ExamAttempt.objects.get(tracking_code="TRK-CNT-0")
    attempt.status = ExamAttemptStatus.COMPLETED
    attempt.save(update_fields=["status"])
    mosque.refresh_from_db()
    assert mosque.completed_exam_count == 2


@pytest.mark.django_db
def test_keepalive_heals_counters_silently(monkeypatch) -> None:
    """نگهبانِ دوره‌ای باید شمارنده‌ها را بدونِ اینکه کسی بداند ترمیم کند."""
    from apps.notifications.management.commands import keepalive as keepalive_mod

    # ⚠️ در محیطِ تست، نشانِ تپشِ سرویس کهنه است و `keepalive` می‌خواهد یک
    # پروسهٔ واقعی بالا بیاورد (و آن پروسه بعد از تست زنده می‌ماند و هشدارِ
    # ResourceWarning می‌دهد). ترمیمِ شمارنده قبل از آن اجرا می‌شود، پس فقط
    # «بالا آوردن» را بی‌اثر می‌کنیم.
    monkeypatch.setattr(keepalive_mod.Command, "_start", lambda self, options: None)

    mosque, _ = _mosque_with_users(2)
    Mosque.objects.filter(pk=mosque.pk).update(registered_count=40)

    call_command("keepalive", stdout=StringIO())

    mosque.refresh_from_db()
    assert mosque.registered_count == 2


@pytest.mark.django_db
def test_login_only_save_does_not_recompute(monkeypatch) -> None:
    """`update_fields=['last_login']` نباید بازشمارش را بی‌دلیل اجرا کند (کارایی)."""
    from apps.mosques import signals

    calls: list[int | None] = []
    monkeypatch.setattr(signals, "_refresh", lambda mosque_id: calls.append(mosque_id))

    _, users = _mosque_with_users(1)
    calls.clear()

    users[0].last_login = timezone.now()
    users[0].save(update_fields=["last_login"])

    assert calls == []


@pytest.mark.django_db
def test_relevant_save_triggers_refresh(monkeypatch) -> None:
    """ولی `update_fields=['mosque']` باید بازشمارش را صدا بزند."""
    from apps.mosques import signals

    calls: list[int | None] = []
    monkeypatch.setattr(signals, "_refresh", lambda mosque_id: calls.append(mosque_id))

    previous, users = _mosque_with_users(1)
    other = _unique_mosque()
    calls.clear()

    users[0].mosque = other
    users[0].save(update_fields=["mosque"])

    # هر دو مسجد بازشمارش می‌شوند: مسجدِ تازه و مسجدِ قبلی (که دیگر او را
    # نمی‌شمارد). اگر فقط مسجدِ تازه تازه شود، مسجدِ قبلی بادکرده می‌ماند.
    assert calls[0] == other.pk
    assert set(calls) == {other.pk, previous.pk}


@pytest.mark.django_db
def test_heal_site_reports_drift_then_fixes_it() -> None:
    """`heal_site` باید وضعیتِ واقعی را گزارش کند و با `--fix` ترمیم کند."""
    mosque, _ = _mosque_with_users(2)
    Mosque.objects.filter(pk=mosque.pk).update(registered_count=33)

    out = StringIO()
    call_command("heal_site", stdout=out)
    assert "انحراف" in out.getvalue() or "33" in out.getvalue()
    mosque.refresh_from_db()
    assert mosque.registered_count == 33  # بدونِ --fix تغییری نکرد

    call_command("heal_site", "--fix", "--quiet", stdout=StringIO())
    mosque.refresh_from_db()
    assert mosque.registered_count == 2


@pytest.mark.django_db
def test_heal_site_purges_simulated_data_only() -> None:
    """`--purge-simulated` فقط دادهٔ ساختگی را می‌برد، نه کاربرِ واقعی را."""
    from apps.exam.services import create_simulated_finished_attempt

    mosque, users = _mosque_with_users(1)
    create_simulated_finished_attempt(mosque=mosque)
    assert User.objects.filter(phone_number__startswith="0990").exists()

    call_command("heal_site", "--purge-simulated", "--fix", "--quiet", stdout=StringIO())

    assert not User.objects.filter(phone_number__startswith="0990").exists()
    assert User.objects.filter(pk=users[0].pk).exists()
    mosque.refresh_from_db()
    assert mosque.registered_count == 1
