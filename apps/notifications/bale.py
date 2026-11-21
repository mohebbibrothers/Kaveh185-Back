"""ارسالِ پیام از طریق **رباتِ بله** (`tapi.bale.ai`) — کانالِ جایگزینِ پنل پیامکی.

چرا بله؟ برای یک حوزهٔ بسیجی، پنل پیامکی نیاز به احرازِ کسب‌وکار و اینماد دارد
و تا وقتی آن مجوز صادر نشود، هیچ پیامکی بیرون نمی‌رود. بله (پیام‌رسانِ داخلی)
همین کار را بی‌هزینه انجام می‌دهد: یک ربات می‌سازیم، کاربر یک‌بار «شروع» را
می‌زند، و از آن لحظه می‌توانیم برایش پیام بفرستیم.

── چرا این‌جا و نه در `providers.py`؟ ──────────────────────────────────────
`providers.py` آداپتورِ HTTPِ پیامک است (یک URL، یک کلید). بله اما **دو** تماس
لازم دارد (دریافتِ پیام‌های ربات / ارسال) و `chat_id`ِ کاربر را باید از قبل
یاد گرفته باشیم. پس منطقش جدا و مستقل است تا خطای هر کدام، مسیرِ دیگری را
نخوابانَد: اگر پیامک وصل شد، بله فقط یک «کمکِ اضافه» می‌ماند و برعکس.

── نکتهٔ امنیتی ────────────────────────────────────────────────────────────
توکنِ ربات مثلِ رمز است. هیچ‌جا در لاگِ خروجی چاپ نمی‌شود و در پاسخِ API هم
برنمی‌گردد. خطاها فقط به شکلِ «کدِ وضعیتِ HTTP + توضیحِ کوتاه» بالا می‌آیند.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from urllib import request as urllib_request

from django.conf import settings

logger = logging.getLogger(__name__)

#: پیش‌فرضِ رسمیِ بله؛ با `BALE_API_BASE` در `.env` قابل تغییر است.
DEFAULT_BASE = "https://tapi.bale.ai"


@dataclass(frozen=True, slots=True)
class BaleResult:
    """نتیجهٔ یک تماس با API بله."""

    ok: bool
    detail: str = ""
    chat_id: int | None = None
    message_id: int | None = None


def bale_is_configured() -> bool:
    """آیا توکنِ ربات تنظیم شده است؟ (بدونِ افشای خودِ توکن)"""
    return bool(str(getattr(settings, "BALE_BOT_TOKEN", "") or "").strip())


def _api(method: str, payload: dict[str, object] | None = None, *, timeout: float = 6.0) -> dict:
    """تماسِ خام با API بله و برگرداندنِ JSONِ پاسخ (یا خطای خوانا)."""
    token = str(getattr(settings, "BALE_BOT_TOKEN", "") or "").strip()
    if not token:
        raise BaleNotConfigured("توکنِ ربات بله تنظیم نشده است.")

    base = str(getattr(settings, "BALE_API_BASE", DEFAULT_BASE) or DEFAULT_BASE).rstrip("/")
    url = f"{base}/bot{token}/{method}"
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"

    req = urllib_request.Request(  # noqa: S310 - آدرسِ ثابتِ داخلی، از .env
        url,
        data=data,
        headers=headers,
        method="POST" if payload is not None else "GET",
    )
    try:
        with urllib_request.urlopen(req, timeout=timeout) as resp:  # noqa: S310  # nosec B310
            body = resp.read().decode("utf-8", errors="replace")
            status = resp.status
    except Exception as exc:  # pragma: no cover - شبکهٔ بیرونی
        # ⚠️ خودِ توکن در پیامِ خطای urllib نیست، ولی آدرسِ آن هست؛ پس فقط
        # نوعِ خطا را بالا می‌بریم تا هیچ ردی از توکن در لاگ نماند.
        raise BaleError(f"ارتباط با بله برقرار نشد ({type(exc).__name__}).") from exc

    if status >= 400:
        raise BaleError(f"بله پاسخِ {status} داد.")
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise BaleError("پاسخِ بله قابل خواندن نبود.") from exc


class BaleError(Exception):
    """خطای ارتباط با بله (بدونِ افشای توکن)."""


class BaleNotConfigured(BaleError):
    """توکنِ ربات تنظیم نشده است."""


def send_bale_message(chat_id: int, text: str) -> BaleResult:
    """ارسالِ یک پیامِ متنی به یک گفتگو."""
    try:
        res = _api(
            "sendMessage", {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
        )
    except BaleNotConfigured:
        raise
    except BaleError as exc:
        return BaleResult(ok=False, detail=str(exc), chat_id=chat_id)
    message = res.get("result") or {}
    return BaleResult(
        ok=bool(res.get("ok")),
        detail="" if res.get("ok") else str(res.get("description", ""))[:160],
        chat_id=chat_id,
        message_id=int(message.get("message_id") or 0) or None,
    )


def get_me() -> dict:
    """اطلاعاتِ ربات — برای تستِ اتصال (`/bale/test` در پنل ادمین)."""
    res = _api("getMe")
    result = res.get("result") or {}
    return {
        "ok": bool(res.get("ok")),
        "username": str(result.get("username") or ""),
        "name": str(result.get("first_name") or ""),
    }
