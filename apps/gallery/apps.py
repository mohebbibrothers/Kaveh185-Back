"""پیکربندی اپ گالری محتوایی."""

from __future__ import annotations

from django.apps import AppConfig


class GalleryConfig(AppConfig):
    """اپ گالری: تصاویر رهبر انقلاب و نوار شهدا."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.gallery"
    verbose_name = "گالری محتوایی"
