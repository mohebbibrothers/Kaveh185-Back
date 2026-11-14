"""نقطهٔ ورود Phusion Passenger برای استقرار روی هاست‌های اشتراکی لینوکس و cPanel."""

from __future__ import annotations

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

from config.wsgi import application  # noqa: E402

__all__ = ("application",)
