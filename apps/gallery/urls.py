"""مسیرهای API عمومیِ گالری.

| مسیر | کاربرد |
|---|---|
| `GET /api/v1/gallery/` | هر دو مجموعه در یک پاسخ |
| `GET /api/v1/gallery/leader/` | تصاویر رهبر انقلاب + کلام هر تصویر |
| `GET /api/v1/gallery/martyrs/` | نوار شهدا: تصویر + عنوان کوتاه |

هر سه `AllowAny` و بدون احراز هویت‌اند: محتوای صفحهٔ اول است و باید
بی‌درخواستِ توکن خوانده شود. صفحهٔ اول از `core/bootstrap` می‌خواند و
این مسیرها برای بازدید مستقیم/دیباگ و صفحه‌های بعدی‌اند.
"""

from __future__ import annotations

from django.urls import path

from .views import PublicGalleryAPIView, PublicLeaderGalleryAPIView, PublicMartyrsAPIView

app_name = "gallery"

urlpatterns = [
    path("", PublicGalleryAPIView.as_view(), name="public-gallery"),
    path("leader/", PublicLeaderGalleryAPIView.as_view(), name="public-gallery-leader"),
    path("martyrs/", PublicMartyrsAPIView.as_view(), name="public-gallery-martyrs"),
]
