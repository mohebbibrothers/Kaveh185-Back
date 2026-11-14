"""منیجر سفارشی مدل کاربر (`UserManager`) برای احراز هویت مبتنی بر شماره تماس و کدملی."""

from __future__ import annotations

from typing import Any

from django.contrib.auth.base_user import BaseUserManager

from apps.core.crypto import blind_index, encrypt_pii

from .choices import UserRole
from .validators import normalize_and_validate_national_id, normalize_and_validate_phone


class UserManager(BaseUserManager):
    """مدیریت ایجاد کاربران عادی (شرکت‌کنندگان) و مدیران ارشد سامانه."""

    use_in_migrations = True

    def create_user(
        self,
        phone_number: str,
        national_id: str,
        password: str | None = None,
        **extra_fields: Any,
    ) -> Any:
        """ایجاد و ذخیرهٔ یک کاربر با شماره موبایل و کدملی اعتبارسنجی‌شده."""
        norm_phone = normalize_and_validate_phone(phone_number)
        norm_nid = normalize_and_validate_national_id(national_id)

        extra_fields.setdefault("role", UserRole.PARTICIPANT)
        user = self.model(
            phone_number=norm_phone,
            national_id=norm_nid,
            national_id_encrypted=encrypt_pii(norm_nid),
            national_id_hash=blind_index(norm_nid, purpose="national_id"),
            **extra_fields,
        )
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(
        self,
        phone_number: str,
        national_id: str = "0013542419",
        password: str | None = None,
        **extra_fields: Any,
    ) -> Any:
        """ایجاد مدیر کل سامانه (`role=admin`, `is_staff=True`, `is_superuser=True`)."""
        extra_fields.setdefault("role", UserRole.ADMIN)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_phone_verified", True)
        extra_fields.setdefault("first_name", "مدیر")
        extra_fields.setdefault("last_name", "سامانه کاوه ۱۸۵")
        return self.create_user(
            phone_number=phone_number,
            national_id=national_id,
            password=password,
            **extra_fields,
        )
