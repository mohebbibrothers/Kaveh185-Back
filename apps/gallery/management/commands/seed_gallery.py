"""پرکردنِ گالری با محتوای رسمیِ خودِ سایت — بدون هیچ آپلودِ دستی.

── چرا این دستور وجود دارد؟ ────────────────────────────────────────────────
اپ گالری با پایگاه‌دادهٔ خالی متولد می‌شود. اگر بلافاصله بعد از استقرار
چیزی در آن نباشد، باکسِ «کتاب و کلام» فقط حالتِ پایه را نشان می‌دهد و
نوارِ شهدا اصلاً دیده نمی‌شود. ادمین می‌تواند همه را دستی اضافه کند، ولی
داشتنِ یک نقطهٔ شروعِ درست، کارِ او را از «ساختنِ فرم» به «جایگزین‌کردنِ
تصویر» تبدیل می‌کند.

── از کجا تصویر می‌گیرد؟ ──────────────────────────────────────────────────
از **بستهٔ فرانت خودِ سایت** (`frontend/img/...`) که روی همان هاست هست.
یعنی:

  • هیچ فایل باینری‌ای در مخزن بک‌اند نیست (مخزن تمیز می‌ماند).
  • هیچ دانلودِ اینترنتی انجام نمی‌شود (هاستِ اشتراکی همیشه اینترنتِ آزاد
    ندارد).
  • تصاویر همان‌هایی هستند که کاربر در هیرو و باکس می‌بیند — هم‌خوان.

── ایمنی ──────────────────────────────────────────────────────────────────
• پیش‌فرض **idempotent** است: رکوردی که موجود باشد دست نمی‌خورد.
• با `--force` رکوردهای قبلیِ ساختهٔ همین دستور بازنویسی می‌شوند (شناسه‌شان
  با `alt`/`title` مشخص می‌شود)، ولی رکوردهایی که ادمین خودش ساخته
  دست‌نخورده می‌مانند — یعنی محتوای واقعیِ ادمین هرگز پاک نمی‌شود.
• اگر فایل تصویر پیدا نشود، آن قلم با پیام روشن رد می‌شود و بقیه ادامه
  می‌دهند؛ استقرار هرگز به‌خاطرِ این دستور شکست نمی‌خورد.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandParser

from apps.gallery.models import LeaderPortrait, Martyr
from apps.gallery.services import invalidate_gallery

# محتوای رسمی — متن‌ها از بیاناتِ منتشرشدهٔ رهبر انقلاب دربارهٔ کتاب است.
LEADER_ITEMS: tuple[dict[str, str], ...] = (
    {
        "source_file": "emam-reading.jpg",
        "target": "gallery/leader/emam-reading.jpg",
        "alt": "حضرت آیت‌الله خامنه‌ای در حال مطالعهٔ کتاب در کتابخانه",
        "caption": (
            "برای یک ملّت، خسارتِ بزرگ است که افراد آن با کتاب سر و کاری نداشته باشند؛\n"
            "و برای یک فرد، توفیقِ عظیمی است که با کتاب مأنوس و همواره در حال بهره‌گیری از آن باشد."
        ),
        "source": "از بیانات رهبر انقلاب اسلامی دربارهٔ کتاب و کتاب‌خوانی",
    },
    {
        "source_file": "emam-reading-sm.jpg",
        "target": "gallery/leader/emam-reading-close.jpg",
        "alt": "قاب نزدیک‌تر از مطالعهٔ رهبر انقلاب",
        "caption": (
            "اوّلین خطابِ خداوندِ متعال به پیامبرِ گرامی اسلام این است که: بخوان!\n"
            "و در اوّلین سوره‌ای که فرود آمده، نامِ «قلم» به تجلیل یاد شده است."
        ),
        "source": "از بیانات رهبر انقلاب اسلامی دربارهٔ کتاب و کتاب‌خوانی",
    },
)

MARTYR_ITEMS: tuple[dict[str, str], ...] = (
    # ⚠️ نامِ فایل‌ها با `probe/build_front_assets.py` هم‌گام است. نسخهٔ PNG/JPGِ
    # قبلی (`kaveh-hero.jpg`, `icon-face.png`, `emblem-portrait-sm.jpg`) در دورِ
    # ۱۵ از بستهٔ فرانت حذف شد؛ اگر seed به آن‌ها تکیه می‌کرد، روی نصبِ تازه
    # نوارِ شهدا خالی می‌ماند. این سه، همان نشانِ شفاف در سه قاب است.
    {
        "source_file": "emblem-avatar.webp",
        "target": "gallery/martyrs/kaveh-portrait.webp",
        "title": "سیدشهدای مقاومت",
        "subtitle": "شهید محمود کاوه — فرماندهٔ لشکر ویژهٔ ۱۵۵ شهدا",
    },
    {
        "source_file": "emblem-mark.webp",
        "target": "gallery/martyrs/kaveh-emblem.webp",
        "title": "به یادِ کاوه",
        "subtitle": "نشانِ حوزهٔ مقاومت بسیج ۱۸۵ شهید کاوه",
    },
    {
        "source_file": "emblem-head.webp",
        "target": "gallery/martyrs/kaveh-head.webp",
        "title": "شهیدِ حوزهٔ ۱۸۵",
        "subtitle": "یادبود شهیدانِ حوزهٔ مقاومت بسیج ۱۸۵",
    },
)


class Command(BaseCommand):
    """پرکردن گالری از تصاویر موجود در بستهٔ فرانت."""

    help = "گالری (تصاویر رهبر + نوار شهدا) را از تصاویر بستهٔ فرانت پر می‌کند."

    def add_arguments(self, parser: CommandParser) -> None:
        """گزینه‌های دستور."""
        parser.add_argument(
            "--force",
            action="store_true",
            help="رکوردهای ساختهٔ همین دستور را بازنویسی کن (محتوای ادمین دست نمی‌خورد).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="فقط گزارش بده، چیزی ذخیره نکن.",
        )

    def handle(self, *args: str, **options: object) -> None:
        """اجرای دستور."""
        force = bool(options.get("force"))
        dry = bool(options.get("dry_run"))

        img_root = self._frontend_img_root()
        if img_root is None:
            self.stderr.write(
                self.style.ERROR(
                    "پوشهٔ تصاویر فرانت پیدا نشد. مسیر مورد انتظار: "
                    f"{Path(settings.BASE_DIR) / 'frontend' / 'img'} — "
                    "یا FRONTEND_DIST را تنظیم کنید، یا تصاویر را از پنل ادمین اضافه کنید."
                )
            )
            return

        media_root = Path(settings.MEDIA_ROOT)
        created = updated = skipped = 0

        for index, item in enumerate(LEADER_ITEMS, start=1):
            exists = LeaderPortrait.all_objects.filter(alt=item["alt"]).first()
            if exists and not force:
                skipped += 1
                continue
            if dry:
                self.stdout.write(f"[dry] تصویر رهبر: {item['alt']}")
                continue
            if not self._copy(img_root, media_root, item["source_file"], item["target"]):
                self.stderr.write(f"  ! فایل {item['source_file']} پیدا نشد — رد شد.")
                continue
            fields = {
                "image": item["target"],
                "caption": item["caption"],
                "source": item["source"],
                "show_in_box": True,
                "is_active": True,
                "display_order": index,
            }
            if exists:
                LeaderPortrait.all_objects.filter(pk=exists.pk).update(**fields)
                updated += 1
            else:
                LeaderPortrait.all_objects.create(alt=item["alt"], **fields)
                created += 1

        for index, item in enumerate(MARTYR_ITEMS, start=1):
            exists = Martyr.all_objects.filter(title=item["title"]).first()
            if exists and not force:
                skipped += 1
                continue
            if dry:
                self.stdout.write(f"[dry] شهید: {item['title']}")
                continue
            if not self._copy(img_root, media_root, item["source_file"], item["target"]):
                self.stderr.write(f"  ! فایل {item['source_file']} پیدا نشد — رد شد.")
                continue
            fields = {
                "image": item["target"],
                "subtitle": item["subtitle"],
                "is_active": True,
                "display_order": index,
            }
            if exists:
                Martyr.all_objects.filter(pk=exists.pk).update(**fields)
                updated += 1
            else:
                Martyr.all_objects.create(title=item["title"], **fields)
                created += 1

        if dry:
            self.stdout.write(self.style.WARNING("حالت آزمایشی — چیزی ذخیره نشد."))
            return

        invalidate_gallery("seed_gallery")

        self.stdout.write(
            self.style.SUCCESS(
                f"گالری آماده است · جدید: {created} · به‌روزشده: {updated} · بدون تغییر: {skipped}"
            )
        )
        leader_count = LeaderPortrait.all_objects.filter(is_active=True).count()
        martyr_count = Martyr.all_objects.filter(is_active=True).count()
        self.stdout.write(f"  تصاویر رهبر: {leader_count} · شهدا: {martyr_count}")
        if martyr_count < 3:
            self.stdout.write(
                self.style.WARNING("  ⚠️ با کمتر از ۳ شهید، نوار به‌صورت ردیفِ ثابت نمایش داده می‌شود.")
            )

    # ── کمکی‌ها ────────────────────────────────────────────────────────────
    @staticmethod
    def _frontend_img_root() -> Path | None:
        """پوشهٔ تصاویر فرانت.

        ── ترتیبِ جست‌وجو (درسِ استقرارِ واقعی روی هاست) ─────────────────
        اول `FRONTEND_DIST`، بعد پیش‌فرض‌ها. روی هاست، `FRONTEND_DIST` یک
        **سیم‌لینک** به `current` است که `front-deploy.sh` با هر استقرار
        اتمی جابه‌جایش می‌کند؛ اگر به آن اتکا نکنیم و فقط
        `<BASE_DIR>/frontend/img` را ببینیم، ممکن است به نسخهٔ قدیمی یا
        مسیرِ ناموجود بخوریم.

        و اگر `img/` سرِ جایش نبود، **در عمقِ خروجی جست‌وجو می‌کنیم**: ساختِ
        بعدی ممکن است تصاویر را زیر `_next/static/…` بگذارد یا نامِ پوشه
        عوض شود. هزینه‌اش چند `os.scandir` است و فایده‌اش این است که
        `seed_gallery` بی‌صدا یکی از تصاویر را جا نمی‌گذارد — همان چیزی که
        یک بار روی هاست اتفاق افتاد:

            ! فایل emblem-portrait-sm.jpg پیدا نشد — رد شد.
        """
        candidates: list[Path] = []
        dist = getattr(settings, "FRONTEND_DIST", "") or ""
        if dist:
            candidates.append(Path(str(dist)) / "img")
        candidates.append(Path(str(settings.BASE_DIR)) / "frontend" / "img")
        candidates.append(Path(str(settings.BASE_DIR)).parent / "front" / "public" / "img")
        for candidate in candidates:
            if candidate.is_dir():
                return candidate

        # آخرین تلاش: پوشه‌ای به نام `img` در دو سطحِ اولِ خروجی.
        dist_root = Path(str(dist)) if dist else Path(str(settings.BASE_DIR)) / "frontend"
        if dist_root.is_dir():
            for depth_one in sorted(dist_root.iterdir()):
                if not depth_one.is_dir():
                    continue
                if depth_one.name == "img":
                    return depth_one
                for depth_two in sorted(depth_one.iterdir()):
                    if depth_two.is_dir() and depth_two.name == "img":
                        return depth_two
        return None

    @staticmethod
    def _copy(img_root: Path, media_root: Path, source: str, target: str) -> bool:
        """کپی یک تصویر از بستهٔ فرانت به `MEDIA_ROOT`."""
        src = img_root / source
        if not src.is_file():
            return False
        dst = media_root / target
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists() and dst.stat().st_size == src.stat().st_size:
            return True
        shutil.copyfile(src, dst)
        return True
