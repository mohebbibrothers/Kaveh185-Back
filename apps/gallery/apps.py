"""پیکربندی اپ گالری."""

from __future__ import annotations

from django.apps import AppConfig


class GalleryConfig(AppConfig):
    """پیکربندی اپ گالری محتوایی."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.gallery"
    verbose_name = "گالری محتوایی"
