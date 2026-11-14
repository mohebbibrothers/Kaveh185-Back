"""رجیستری سیاست‌های کش (Cache Policy Registry) برای دامنه‌های مختلف کاوه ۱۸۵.

این ماژول برای هر دامنهٔ عمومی (مساجد، رنکینگ، وضعیت آزمون، داشبورد مدیریتی):
- نام‌فضای کش بک‌اند (Namespace)
- تگ‌ها و مسیرهای بازاعتبارسنجی فرانت‌اند (Frontend Revalidation Tags & Paths)
- زمان تازگی نرم (`soft_ttl`) و زمان انقضای سخت (`hard_ttl`) برای الگوی SWR
- زمان قفل جلوگیری از هجوم هم‌زمان (`lock_ttl` / Dogpile Protection)
را تعریف می‌کند.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DomainCachePolicy:
    """پیکربندی سیاست کش برای یک دامنهٔ مشخص."""

    domain: str
    namespace: str
    soft_ttl: int
    hard_ttl: int
    lock_ttl: int
    frontend_tags: tuple[str, ...]
    frontend_paths: tuple[str, ...]


CACHE_POLICY_REGISTRY: dict[str, DomainCachePolicy] = {
    "mosques": DomainCachePolicy(
        domain="mosques",
        namespace="kaveh185:mosques",
        soft_ttl=30,
        hard_ttl=300,
        lock_ttl=5,
        frontend_tags=("mosques", "mosque-leaderboard"),
        frontend_paths=("/", "/leaderboard", "/register"),
    ),
    "exam_status": DomainCachePolicy(
        domain="exam_status",
        namespace="kaveh185:exam_status",
        soft_ttl=15,
        hard_ttl=120,
        lock_ttl=5,
        frontend_tags=("exam-status", "exam-config"),
        frontend_paths=("/", "/exam"),
    ),
    "reporting": DomainCachePolicy(
        domain="reporting",
        namespace="kaveh185:reporting",
        soft_ttl=20,
        hard_ttl=180,
        lock_ttl=5,
        frontend_tags=("admin-dashboard", "mosque-leaderboard"),
        frontend_paths=("/admin/dashboard", "/leaderboard"),
    ),
}


def get_cache_policy(domain: str) -> DomainCachePolicy:
    """دریافت سیاست کش برای یک دامنهٔ ثبت‌شده (یا پرتاب KeyError در صورت عدم ثبت)."""
    if domain not in CACHE_POLICY_REGISTRY:
        raise KeyError(f"سیاست کش برای دامنهٔ '{domain}' ثبت نشده است.")
    return CACHE_POLICY_REGISTRY[domain]
