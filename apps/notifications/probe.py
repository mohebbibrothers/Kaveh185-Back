"""سنجه‌های مشترکِ وب‌هوکِ بله — یک منبعِ حقیقت برای `bale_webhook` و `bale_doctor`.

چرا ماژول جدا؟ پیش‌تر همین دو سنجه (دسترس‌پذیری + آزمونِ حلقه‌ای) در دو
دستور تکرار شده بود و هر تغییر باید دو جا اعمال می‌شد؛ دقیقاً همان الگویی که
باعث می‌شود یک مسیر ترمیم شود و مسیر دیگر بی‌خبر بماند.

هر تابع یک تاپل `(ok, message)` می‌دهد و **هرگز استثنا پرتاب نمی‌کند**؛ عیب‌یابی
نباید خودش منبعِ خطا شود.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

EXPECTED_SERVICE = "kaveh185-bale-webhook"
SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"


def http_call(
    url: str,
    *,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 10,
) -> tuple[int, str]:
    """یک تماسِ HTTPِ خام؛ کدِ وضعیت را حتی روی خطا برمی‌گرداند (۰ = شبکه)."""
    request = urllib.request.Request(  # noqa: S310
        url, data=body, headers=headers or {}, method="POST" if body else "GET"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:  # noqa: S310  # nosec B310
            return resp.status, resp.read(4000).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(4000).decode("utf-8", errors="replace")
    except Exception as exc:
        return 0, type(exc).__name__


def _json(raw: str) -> dict:
    """JSON را در صورتِ خرابی به دیکشنریِ خالی تبدیل می‌کند."""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def health(url: str) -> tuple[bool, str]:
    """آیا این نشانی واقعاً همین اپلیکیشن است؟ (۲۰۰ + نامِ سرویس)

    چرا فقط ۲۰۰ کافی نیست؟ روی این هاست `www`, `api` و دامنهٔ اصلی هر سه به
    همان اپ می‌رسند، ولی یک صفحهٔ ۲۰۰ِ HTML یا صفحهٔ «در حال ساخت» هم ۲۰۰
    است. تنها راهِ مطمئن، دیدنِ پاسخِ خودِ سرویس است.
    """
    status, body = http_call(url)
    if status == 0:
        return False, f"از داخلِ سرور پاسخ نیامد ({body})"
    payload = _json(body)
    if status == 200 and payload.get("service") == EXPECTED_SERVICE:
        return True, f"پاسخِ سلامت: {status} · configured={payload.get('configured')}"
    if status == 200:
        return False, f"پاسخ ۲۰۰ آمد ولی این اپلیکیشن نبود: {body[:80]}"
    return False, f"پاسخِ نامنتظر ({status}): {body[:100]}"


def loopback(url: str, secret: str | None = None) -> tuple[bool, str]:
    """همان POSTای که بله می‌فرستد، از خودمان به خودمان — بی‌آنکه کسی پیام بگیرد.

    چرا لازم است؟ GETِ سلامت فقط «مسیر باز است» را می‌گوید. چیزی که واقعاً
    باید کار کند یک POST با هدرِ کلید است که ۲۰۰ و `ok: true` برگرداند. اگر
    کلید جابه‌جا باشد یا middleware درخواست را رد کند، همین‌جا لو می‌رود — نه
    وقتی کاربر واقعی `/start` می‌زند و هیچ پاسخی نمی‌گیرد.

    آپدیتِ ساختگی `_probe` دارد؛ ویو آن را می‌بیند و **هیچ پیامی نمی‌فرستد**.
    """
    body = json.dumps(
        {
            "_probe": True,
            "message": {
                "message_id": 1,
                "chat": {"id": 1, "first_name": "آزمون"},
                "from": {"first_name": "آزمون"},
                "text": "/start",
            },
        }
    ).encode()
    headers = {"Content-Type": "application/json"}
    secret = secret or ""
    if secret:
        headers[SECRET_HEADER] = secret
    status, raw = http_call(url, body=body, headers=headers)
    payload = _json(raw)
    if status == 200 and payload.get("ok") is True:
        return True, f"پاسخِ اپلیکیشن: {status} · handled={payload.get('handled')}"
    if status == 403:
        return False, "۴۰۳ ⇒ کلیدِ ارسالی پذیرفته نشد (کلیدِ `.env` با ثبتِ بله یکی نیست)."
    if status == 0:
        return False, f"دسترسیِ حلقه‌ای برقرار نشد ({raw})"
    return False, f"پاسخِ نامنتظر ({status}): {raw[:140]}"
