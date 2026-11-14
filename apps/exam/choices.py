"""مقادیر ثابت و ماشین حالت آزمون در سامانهٔ کاوه ۱۸۵."""

from __future__ import annotations

from django.db import models


class ExamWindowState(models.TextChoices):
    """وضعیت پنجرهٔ زمانی شرکت در آزمون."""

    UPCOMING = "upcoming", "شرکت در آزمون به زودی"
    OPEN = "open", "آزمون فعال است"
    ENDED = "ended", "مهلت آزمون به پایان رسید"


class QuestionDifficulty(models.TextChoices):
    """سطح دشواری سوال در بانک سوال."""

    EASY = "easy", "ساده"
    MEDIUM = "medium", "متوسط"
    HARD = "hard", "دشوار"


class ExamAttemptStatus(models.TextChoices):
    """وضعیت چرخهٔ حیات آزمون هر شرکت‌کننده."""

    IN_PROGRESS = "in_progress", "در حال پاسخگویی"
    COMPLETED = "completed", "پایان‌یافته توسط شرکت‌کننده"
    TIMED_OUT = "timed_out", "پایان‌یافته به علت اتمام زمان"


class AnswerResultStatus(models.TextChoices):
    """وضعیت پاسخ هر سوال (صرفاً برای گزارش‌های داخلی ادمین و قرعه‌کشی — هرگز به کاربر نمایش داده نمی‌شود)."""

    UNANSWERED = "unanswered", "بی‌پاسخ"
    CORRECT = "correct", "پاسخ درست"
    WRONG = "wrong", "پاسخ غلط"


DEFAULT_COMMUNICATION_CHANNELS: tuple[dict[str, str], ...] = (
    {
        "platform": "eitaa",
        "title": "کانال رسمی حوزه مقاومت بسیج ۱۸۵ شهید کاوه در ایتا",
        "url": "https://eitaa.com/kaveh185_ir",
    },
    {
        "platform": "bale",
        "title": "کانال اطلاع‌رسانی قرعه‌کشی و رویدادهای فرهنگی در بله",
        "url": "https://ble.ir/kaveh185_ir",
    },
    {
        "platform": "rubika",
        "title": "صفحه فرهنگی هفته بسیج حوزه ۱۸۵ شهید کاوه در روبیکا",
        "url": "https://rubika.ir/kaveh185_ir",
    },
)

DEFAULT_SAMPLE_QUESTIONS: tuple[dict[str, object], ...] = (
    {
        "text": "فرمان تاریخی تشکیل بسیج مستضعفین در چه تاریخی و توسط چه کسی صادر شد؟",
        "chapter": "فصل اول — تاریخچه و فلسفه بسیج",
        "difficulty": QuestionDifficulty.EASY,
        "explanation": "فرمان تشکیل بسیج مستضعفین در ۵ آذر ۱۳۵۸ توسط حضرت امام خمینی (ره) صادر شد.",
        "options": [
            {"option_number": 1, "text": "۵ آذر ۱۳۵۸ — حضرت امام خمینی (ره)", "is_correct": True},
            {"option_number": 2, "text": "۲۲ بهمن ۱۳۵۷ — شورای انقلاب", "is_correct": False},
            {
                "option_number": 3,
                "text": "۳ خرداد ۱۳۶۱ — ستاد کل نیروهای مسلح",
                "is_correct": False,
            },
            {"option_number": 4, "text": "۳۱ شهریور ۱۳۵۹ — مجلس شورای اسلامی", "is_correct": False},
        ],
    },
    {
        "text": "شهید محمود کاوه، فرمانده جوان و نامدار لشکر ویژه شهدا، در کدام عملیات به فیض شهادت نائل آمد؟",
        "chapter": "فصل دوم — سیره شهدای شاخص و شهید کاوه",
        "difficulty": QuestionDifficulty.MEDIUM,
        "explanation": "شهید محمود کاوه در ۱۱ شهریور ۱۳۶۵ در عملیات کربلای ۲ در منطقه حاج عمران به شهادت رسید.",
        "options": [
            {"option_number": 1, "text": "عملیات کربلای ۲ (منطقه حاج عمران)", "is_correct": True},
            {"option_number": 2, "text": "عملیات بیت‌المقدس (آزادسازی خرمشهر)", "is_correct": False},
            {
                "option_number": 3,
                "text": "عملیات فتح‌المبین (منطقه شوش و دزفول)",
                "is_correct": False,
            },
            {"option_number": 4, "text": "عملیات مرصاد (تنگه چهارزبر)", "is_correct": False},
        ],
    },
    {
        "text": "بر اساس اندیشه اسلامی و بیانات رهبر معظم انقلاب، مهم‌ترین کارکرد فرهنگی مسجد در محلات چیست؟",
        "chapter": "فصل سوم — مسجد تراز اسلامی و پایگاه مردمی",
        "difficulty": QuestionDifficulty.EASY,
        "explanation": "مسجد کانون عبادت، بصیرت‌افزایی، همدلی اجتماعی و حل مسائل محله با مشارکت مردم است.",
        "options": [
            {
                "option_number": 1,
                "text": "کانون عبادت، بصیرت‌افزایی، همبستگی اجتماعی و خدمت‌رسانی مردمی",
                "is_correct": True,
            },
            {
                "option_number": 2,
                "text": "صرفاً برگزاری مراسم‌های مناسبتی سالانه",
                "is_correct": False,
            },
            {
                "option_number": 3,
                "text": "فعالیت اداری محدود در ساعات غیرکاری",
                "is_correct": False,
            },
            {
                "option_number": 4,
                "text": "تفکیک امور معنوی از نیازهای فرهنگی جوانان محله",
                "is_correct": False,
            },
        ],
    },
    {
        "text": "کدام ویژگی در سیره مدیریتی و فرماندهی شهید محمود کاوه بیشترین نقش را در موفقیت رزمندگان داشت؟",
        "chapter": "فصل دوم — سیره شهدای شاخص و شهید کاوه",
        "difficulty": QuestionDifficulty.MEDIUM,
        "explanation": "حضور در خط مقدم، شجاعت، اخلاص، اعتماد به جوانان و روحیه مردم‌داری شاخص‌ترین ویژگی شهید کاوه بود.",
        "options": [
            {
                "option_number": 1,
                "text": "حضور میدانی در خط مقدم، اعتماد به جوانان و اخلاص در عمل",
                "is_correct": True,
            },
            {"option_number": 2, "text": "اتکای صرف به تجهیزات سنگین نظامی", "is_correct": False},
            {
                "option_number": 3,
                "text": "فرماندهی از راه دور بدون حضور در میدان",
                "is_correct": False,
            },
            {
                "option_number": 4,
                "text": "پرهیز از واگذاری مسئولیت به نیروهای داوطلب مردمی",
                "is_correct": False,
            },
        ],
    },
    {
        "text": "مفهوم «بسیج، شجره طیبه» در کلام بنیان‌گذار کبیر انقلاب اسلامی ناظر بر کدام حقیقت است؟",
        "chapter": "فصل اول — تاریخچه و فلسفه بسیج",
        "difficulty": QuestionDifficulty.EASY,
        "explanation": "شجره طیبه نماد درخت پاک و پرباری است که ریشه در ایمان مردم دارد و ثمره آن امنیت، علم و خدمت است.",
        "options": [
            {
                "option_number": 1,
                "text": "ریشه‌دار بودن در ایمان مردم و ثمردهی مستمر در عرصه‌های علم، فرهنگ و خدمت",
                "is_correct": True,
            },
            {
                "option_number": 2,
                "text": "محدود بودن فعالیت بسیج به دوران دفاع مقدس",
                "is_correct": False,
            },
            {
                "option_number": 3,
                "text": "تمرکز انحصاری بر فعالیت‌های سازمانی و اداری",
                "is_correct": False,
            },
            {
                "option_number": 4,
                "text": "عدم ارتباط با مساجد و پایگاه‌های محلی",
                "is_correct": False,
            },
        ],
    },
    {
        "text": "در فرهنگ بسیجی، مهم‌ترین رکن «جهاد تبیین» و کار فرهنگی اثرگذار چیست؟",
        "chapter": "فصل چهارم — جهاد تبیین و مسؤلیت اجتماعی",
        "difficulty": QuestionDifficulty.MEDIUM,
        "explanation": "جهاد تبیین بر پایه مطالعه دقیق، استدلال منطقی، اخلاق حسنه و روشنگری هنرمندانه استوار است.",
        "options": [
            {
                "option_number": 1,
                "text": "مطالعه و آگاهی دقیق، استدلال منطقی و بیان محترمانه و هنرمندانه",
                "is_correct": True,
            },
            {
                "option_number": 2,
                "text": "واکنش شتاب‌زده بدون بررسی منابع معتبر",
                "is_correct": False,
            },
            {
                "option_number": 3,
                "text": "نادیده گرفتن پرسش‌ها و شبهات نسل جوان",
                "is_correct": False,
            },
            {
                "option_number": 4,
                "text": "بسنده کردن به شعارهای کلی بدون محتوای علمی",
                "is_correct": False,
            },
        ],
    },
    {
        "text": "کدام گزینه از برکات پیوند عمیق جوانان محله با مسجد و پایگاه بسیج محسوب می‌شود؟",
        "chapter": "فصل سوم — مسجد تراز اسلامی و پایگاه مردمی",
        "difficulty": QuestionDifficulty.EASY,
        "explanation": "تقویت هویت دینی و ملی، نشاط سالم اجتماعی، دستگیری از نیازمندان و رشد علمی و فرهنگی جوانان.",
        "options": [
            {
                "option_number": 1,
                "text": "تقویت هویت دینی و ملی، نشاط معنوی، همیاری اجتماعی و رشد علمی جوانان",
                "is_correct": True,
            },
            {
                "option_number": 2,
                "text": "کاهش مشارکت مردم در امور خیریه و فرهنگی محله",
                "is_correct": False,
            },
            {
                "option_number": 3,
                "text": "فاصله گرفتن نسل نوجوان از کتاب و مطالعه",
                "is_correct": False,
            },
            {
                "option_number": 4,
                "text": "انزوای اجتماعی خانواده‌ها در سطح محلات",
                "is_correct": False,
            },
        ],
    },
    {
        "text": "شهید محمود کاوه در چه سنی فرماندهی لشکر ویژه ۱۵۵ شهدا را بر عهده گرفت و لقب «سردار جوان» را یافت؟",
        "chapter": "فصل دوم — سیره شهدای شاخص و شهید کاوه",
        "difficulty": QuestionDifficulty.HARD,
        "explanation": "شهید محمود کاوه متولد ۱۳۴۰ بود و در سنین حدود ۲۲ تا ۲۵ سالگی فرماندهی تیپ و لشکر ویژه شهدا را بر عهده داشت.",
        "options": [
            {
                "option_number": 1,
                "text": "در اوایل دهه سوم زندگی (حدود ۲۲ تا ۲۵ سالگی)",
                "is_correct": True,
            },
            {"option_number": 2, "text": "در سن ۴۵ سالگی پس از بازنشستگی", "is_correct": False},
            {"option_number": 3, "text": "در سن ۳۸ سالگی در سال پایانی جنگ", "is_correct": False},
            {"option_number": 4, "text": "در سن ۵۰ سالگی", "is_correct": False},
        ],
    },
)
