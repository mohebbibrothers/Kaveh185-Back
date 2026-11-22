"""سیگنال‌های هم‌گام‌سازیِ شمارندهٔ مساجد با دادهٔ واقعی.

چرا این‌جا و نه در `services.py`؟ چون رخدادها از همه‌جا می‌آیند و ما نمی‌توانیم
به «همه‌جا» تکیه کنیم:

* **پنل جنگو.** ادمین کاربر را حذف/غیرفعال می‌کند و کدِ دامنه در جریان نیست.
* **حذفِ گروهی.** `QuerySet.delete()` سیگنالِ `pre_delete`/`post_delete` را
  برای هر نمونه می‌فرستد (برخلافِ `DELETE` خام)، ولی `post_save` نمی‌آید.
* **مهاجرت/اسکریپت.** هر کدی که مستقیم `save()` می‌زند.

پس به سطحِ مدل می‌چسبیم: هر `post_save`/`post_delete` روی `User` و
`ExamAttempt`، شمارندهٔ مسجدِ مربوطه را از **شمارشِ زنده** بازسازی می‌کند.

⚠️ نکتهٔ کارایی: `post_save` با `update_fields=["last_login"]` هم می‌آید
(در هر ورود). برای همین اگر هیچ فیلدِ مؤثر عوض نشده باشد، کار را رها می‌کنیم.
"""

from __future__ import annotations

import logging
from contextlib import suppress
from typing import Any

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

#: فیلدهایی که «تعدادِ ثبت‌نام‌کنندگانِ مسجد» را تحتِ‌تأثیر می‌گذارند.
USER_COUNTED_FIELDS = frozenset({"mosque", "mosque_id", "is_active", "role"})


def _touches(update_fields: Any, relevant: frozenset[str]) -> bool:
    """آیا این `save()` فیلدی را عوض کرده که شمارش را تغییر می‌دهد؟

    `update_fields=None` یعنی «همهٔ فیلدها» ⇒ بالقوه مؤثر، پس `True`.
    """
    if update_fields is None:
        return True
    return bool(relevant & set(update_fields))


logger = logging.getLogger(__name__)


def _refresh(mosque_id: int | None) -> None:
    """فراخوانیِ امنِ بازشمارش؛ هرگز اجازه نمی‌دهیم سیگنال، ذخیره را بشکند.

    اگر این‌جا خطا بالا برود، خودِ `save()` کاربر یا آزمون شکست می‌خورد —
    یعنی یک شمارندهٔ آماری می‌تواند ثبت‌نام را از کار بیندازد. پس خطا را
    می‌بلعیم ولی **لاگ** می‌کنیم؛ تورِ ایمنیِ `keepalive`/`recount` جبرانش می‌کند.
    """
    from .services import refresh_mosque_stats

    with suppress(Exception):
        refresh_mosque_stats(mosque_id)
        return
    logger.warning("mosque_stats_refresh_failed mosque_id=%s", mosque_id)


@receiver(pre_save, dispatch_uid="k185_mosque_stats_user_presave")
def remember_previous_mosque(sender: Any, instance: Any, **_: Any) -> None:
    """یادآوریِ مسجدِ **قبلی** پیش از ذخیره.

    بدونِ این، انتقالِ کاربر از مسجدِ الف به ب، فقط مسجدِ ب را تازه می‌کرد و
    مسجدِ الف همچنان او را می‌شمرد — یک شمارندهٔ بادکردهٔ تازه، دقیقاً همان
    باگی که می‌خواهیم ریشه‌کن شود.
    """
    del sender
    from apps.authentication.models import User

    if not isinstance(instance, User) or instance.pk is None:
        return
    instance._previous_mosque_id = (
        User.objects.filter(pk=instance.pk).values_list("mosque_id", flat=True).first()
    )


@receiver(post_save, dispatch_uid="k185_mosque_stats_user_save")
def on_user_saved(
    sender: Any, instance: Any, created: bool, update_fields: Any = None, **_: Any
) -> None:
    """هر کاربرِ ذخیره‌شده: شمارندهٔ مسجدش هم‌گام شود."""
    del sender, created
    from apps.authentication.models import User

    if not isinstance(instance, User):
        return
    if update_fields is not None and not _touches(update_fields, USER_COUNTED_FIELDS):
        return
    # هم مسجدِ تازه و هم مسجدِ قبلی (در صورتِ انتقال) باید بازشمارش شوند.
    previous = getattr(instance, "_previous_mosque_id", None)
    _refresh(instance.mosque_id)
    if previous and previous != instance.mosque_id:
        _refresh(previous)


@receiver(post_delete, dispatch_uid="k185_mosque_stats_user_delete")
def on_user_deleted(sender: Any, instance: Any, **_: Any) -> None:
    """هر کاربرِ حذف‌شده (تکی یا گروهی): شمارندهٔ مسجدش کم شود."""
    del sender
    from apps.authentication.models import User

    if not isinstance(instance, User):
        return
    _refresh(instance.mosque_id)


@receiver(post_save, dispatch_uid="k185_mosque_stats_attempt_save")
def on_attempt_saved(
    sender: Any, instance: Any, created: bool, update_fields: Any = None, **_: Any
) -> None:
    """تکمیل/پایانِ آزمون شمارندهٔ «تکمیل‌کنندگان» را عوض می‌کند."""
    del sender, created
    from apps.exam.models import ExamAttempt

    if not isinstance(instance, ExamAttempt):
        return
    if update_fields is not None and not _touches(
        update_fields, frozenset({"status", "mosque", "mosque_id"})
    ):
        return
    _refresh(instance.mosque_id)


@receiver(post_delete, dispatch_uid="k185_mosque_stats_attempt_delete")
def on_attempt_deleted(sender: Any, instance: Any, **_: Any) -> None:
    """حذفِ آزمون (مثلاً پاک‌سازیِ دادهٔ آزمایشی) شمارنده را پس می‌برد."""
    del sender
    from apps.exam.models import ExamAttempt

    if not isinstance(instance, ExamAttempt):
        return
    _refresh(instance.mosque_id)
