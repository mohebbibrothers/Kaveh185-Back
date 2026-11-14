# استقرار بک‌اند کاوه ۱۸۵ روی cPanel — راهنمای گام‌به‌گام

> نسخهٔ ۱.۰ · ۲۳ آبان ۱۴۰۵
> این سند **دقیقاً** بر اساس هاست شما (cPanel، پلن اول، Python App، MySQL) نوشته شده.
> اسکریپت `back-deploy.sh` کنار همین فایل است و همهٔ مراحل ۵ تا ۹ را خودکار می‌کند.

---

## آنچه تا الان آماده است

| مورد | وضعیت |
|---|---|
| بک‌اند در محیط توسعه اجرا شد | ✅ ۲۲۷ مهاجرت · ۱۷ مسجد · ۸ سوال · مسیر کامل کاربر تست شد |
| قرارداد API با دادهٔ زنده تأیید شد | ✅ bootstrap، register، start، answer، finish، receipt، خطاها |
| `check --deploy` بدون هشدار | ✅ با کلیدهای واقعی و `SECURE_SSL_REDIRECT=True` |
| Passenger WSGI | ✅ `python -c "from config.wsgi import application"` → `WSGIHandler` |
| اسکریپت استقرار | ✅ روی شبیه‌سازی هاست اجرا شد: نصب، migrate، seed، collectstatic، health، **rollback** |
| Schema OpenAPI برای فرانت | ✅ `docs/openapi.yaml` (۱۳۱KB، ۷۰ مسیر) |

**تنها چیزی که از شما لازم است:** یک‌بار `Setup Python App` را بسازید و `.env` را پر کنید. بعد از آن، هر بار فقط **یک دستور** می‌زنید.

---

## گام ۰ — پیش‌نیازها در cPanel (یک‌بار، حدود ۱۰ دقیقه)

### ۰.۱ ساخت دیتابیس (۵ دقیقه)

`cPanel → Databases → MySQL® Databases`

| فیلد | پیشنهاد |
|---|---|
| New Database | `kaveh185` |
| New User | `kaveh185` |
| Password | یک رمز قوی (۲۰+ کاراکتر) — **همین‌جا کپی کن** |
| Add User To Database | تیک **ALL PRIVILEGES** |

cPanel نام‌ها را با پیشوند حساب می‌سازد، مثلاً: `cpuser_kaveh185`
این دو مقدار را بردار: **DB_NAME** و **DB_USER**.

### ۰.۲ ساخت اپلیکیشن پایتون (۵ دقیقه)

`cPanel → Software → Setup Python App → Create application`

| فیلد | مقدار دقیق |
|---|---|
| Python version | **3.12** یا **3.13** (اگر هست) |
| Application root | `Kaveh185-Back` |
| Application URL | `api.kaveh185.ir` (اگر در لیست است) — وگرنه `kaveh185.ir/api` |
| Application startup file | `passenger_wsgi.py` |
| Application Entry point | `application` |

بعد از ساخت، cPanel یک **دستور فعال‌سازی** نشان می‌دهد شبیه این — یادداشتش کن:
```bash
source /home/CPUSER/virtualenv/Kaveh185-Back/3.13/bin/activate && cd /home/CPUSER/Kaveh185-Back
```
و مسیر virtualenv واقعی را بردار (اسکریپت خودش پیدا می‌کند، ولی بهتر است بدانی):
`/home/CPUSER/virtualenv/Kaveh185-Back/3.13`

### ۰.۳ گرفتن کد از گیت‌هاب

`cPanel → Files → Terminal` (یا SSH):

```bash
cd ~
git clone https://github.com/mohebbibrothers/Kaveh185-Back.git
```

> اگر مخزن خصوصی شد، به‌جای `https` از **Deploy Key** استفاده کن (Settings → Deploy keys) نه از توکن شخصی.

### ۰.۴ ساخت فایل `.env` (مهم‌ترین گام)

```bash
cd ~/Kaveh185-Back
cp .env.example .env
nano .env          # یا از File Manager → Edit
```

محتوا را با این مقادیر پر کن:

```ini
# ── پایه ────────────────────────────────────────────
DJANGO_SETTINGS_MODULE=config.settings.production
DJANGO_DEBUG=False

# سه کلید زیر را با دستور پایین تولید کن و بگذار:
#   python -c "import secrets;print(secrets.token_urlsafe(48))"
DJANGO_SECRET_KEY=<۶۴+ کاراکتر تصادفی>
PII_ENCRYPTION_KEY=<۳۲ بایت base64 تصادفی — این کلید با داده‌ها گره می‌خورد، هرگز عوضش نکن>
PII_BLIND_INDEX_KEY=<همچنین>

# ── دامنه و هاست ────────────────────────────────────
DJANGO_ALLOWED_HOSTS=kaveh185.ir,api.kaveh185.ir,www.kaveh185.ir
DJANGO_ADMIN_URL=secure-kaveh185-admin/

# ── دیتابیس (از گام ۰.۱) ─────────────────────────────
DB_ENGINE=django.db.backends.mysql
DB_NAME=cpuser_kaveh185
DB_USER=cpuser_kaveh185
DB_PASSWORD=<رمز دیتابیس>
DB_HOST=localhost
DB_PORT=3306

# ── پیامک ───────────────────────────────────────────
SMS_PROVIDER=console
SMS_API_URL=
SMS_API_KEY=
SMS_SENDER_LINE=3000185

# ── امنیت و مستندات ──────────────────────────────────
SECURE_SSL_REDIRECT=True
CORS_ALLOWED_ORIGINS=https://kaveh185.ir,https://www.kaveh185.ir
API_DOCS_PUBLIC=True
METRICS_PUBLIC_ENABLED=False

# ── کش (این پلن Redis ندارد، خالی بگذار) ──────────────
REDIS_URL=
CELERY_BROKER_URL=
CELERY_RESULT_BACKEND=
```

سخت‌گیری‌های امنیتی که خودکار اعمال می‌شوند: HSTS یک‌ساله با preload، کوکی‌های HttpOnly/Secure/SameSite=Lax، `X-Frame-Options: DENY`، `nosniff`، Referrer-Policy.

> ⚠️ **نکتهٔ حیاتی کپی/پیست:** این سه کلید (`DJANGO_SECRET_KEY`، `PII_ENCRYPTION_KEY`، `PII_BLIND_INDEX_KEY`) **هرگز** نباید عوض شوند. اگر `PII_ENCRYPTION_KEY` عوض شود، کدملی‌های ثبت‌شده قابل خواندن نیستند.

---

## گام ۱ — دامنه و SSL

### ۱.۱ رکوردهای DNS

در همان‌جایی که دامنه را خریدی (یا `cPanel → Zone Editor`):

| نوع | نام | مقدار | TTL |
|---|---|---|---|
| A | `api` | IP سرور هاست | 3600 |
| A | `@` | `76.76.21.21` (Vercel) — **بعداً، در گام فرانت** | 3600 |
| A | `www` | `76.76.21.21` (Vercel) | 3600 |

> اول `api` را بساز و DNS را چک کن: `dig +short api.kaveh185.ir` باید IP هاست را برگرداند. (الان هیچ رکوردی ندارد.)

### ۱.۲ SSL

`cPanel → Security → SSL/TLS Status → Run AutoSSL` — باید `api.kaveh185.ir` سبز شود.
اگر نشد، `Let's Encrypt` را دستی نصب کن. **بدون SSL، `SECURE_SSL_REDIRECT=True` باعث حلقه می‌شود.**

---

## گام ۲ — استقرار (همین یک دستور)

```bash
cd ~/Kaveh185-Back
bash deploy/back/back-deploy.sh --seed --grant-admin "09XXXXXXXXX|کدملی|رمز-ادمین"
```

`--seed` فقط **بار اول**: ۱۷ مسجد + تنظیمات آزمون + بانک سوال نمونه.
`--grant-admin` هم فقط بار اول (یا هر وقت می‌خواهی رمز ادمین را عوض کنی).

خروجی موفق چنین است:

```
▸ ۸/۸ · بررسی سلامت (health-check)
✔ سرویس سالم است: {"success":true,...,"data":{"status":"healthy",...}}
═══════════════════════════════════════════════
  ✔ استقرار بک‌اند کاوه ۱۸۵ با موفقیت انجام شد
═══════════════════════════════════════════════
```

### از این به بعد، برای هر آپدیت فقط:

```bash
bash ~/Kaveh185-Back/deploy/back-deploy.sh
```

### چک نهایی

| مسیر | انتظار |
|---|---|
| `https://api.kaveh185.ir/api/v1/health/` | `{"success":true,"data":{"status":"healthy"}}` |
| `https://api.kaveh185.ir/api/v1/` | کاتالوگ کشف اندپوینت‌ها |
| `https://api.kaveh185.ir/api/v1/docs/` | Swagger UI |
| `https://api.kaveh185.ir/api/v1/core/bootstrap/` | دادهٔ صفحهٔ اول (۱۷ مسجد + وضعیت + لیدربورد) |
| `https://api.kaveh185.ir/secure-kaveh185-admin/` | پنل جنگو |

---

## گام ۳ — تنظیمات پس از استقرار (در پنل ادمین)

1. **زمان آزمون را درست کن** — پیش‌فرض «الان تا ۷ روز بعد» است. باید بشود **۲۹ آبان تا ۵ آذر**.
   `PATCH /api/v1/exam/admin/config/` با `{"starts_at": "...", "ends_at": "..."}` یا از پنل ادمین.
2. **تایمر** — پیش‌فرض ۳۰۰ ثانیه. اگر «پنج دقیقه برای پنج سوال» مناسب است، همین بماند.
3. **بانک سوال** — ۸ سوال نمونه هست؛ بانک واقعی ۳۰ سوالی را از `POST /api/v1/exam/admin/questions/bulk/` بار کن.
4. **کانال‌ها** — لینک‌های ایتا/بله/روبیکا در تنظیمات ثبت شدند (`kaveh185_ir`). اگر واقعی نیستند، عوضشان کن.
5. **پیامک** — `SMS_PROVIDER=console` یعنی پیامک فقط لاگ می‌شود. برای ارسال واقعی، کلید کاوه‌نگار/ایران‌پیامک را در `.env` بگذار و `SMS_PROVIDER=kavenegar` کن، بعد `back-deploy.sh` بزن.
6. **OTP** — پیش‌فرض `require_otp_before_exam=false` است (ورود سریع). توصیهٔ من: **روشن نگذار**. برای رویداد یک‌هفته‌ای، هر پیامکِ اضافه ریزش می‌آورد.

---

## گام ۴ — Cron (اختیاری ولی توصیه‌شده)

`cPanel → Advanced → Cron Jobs` — دو مورد زیر را اضافه کن:

```cron
# هر ساعت: بررسی یکپارچگی زنجیرهٔ حسابرسی
0 * * * * cd /home/CPUSER/Kaveh185-Back && /home/CPUSER/virtualenv/Kaveh185-Back/3.13/bin/python manage.py verify_audit_chain >> /home/CPUSER/kaveh185_audit.log 2>&1

# هر شب ۳:۳۰: پاک‌سازی جلسات منقضی
30 3 * * * cd /home/CPUSER/Kaveh185-Back && /home/CPUSER/virtualenv/Kaveh185-Back/3.13/bin/python manage.py clearsessions >> /home/CPUSER/kaveh185_maintenance.log 2>&1
```

> `clearsessions` دستور خود Django است — همیشه هست. `verify_audit_chain` دستور اختصاصی همین بک‌اند است.

---

## گام ۵ — پشتیبان‌گیری

اسکریپت، **قبل از هر `migrate`** خودکار از دیتابیس پشتیبان می‌گیرد و ۵ مورد آخر را نگه می‌دارد:
`~/kaveh185-backups/db-YYYYmmdd-HHMMSS.sql.gz`

بازگردانی (در صورت نیاز):
```bash
zcat ~/kaveh185-backups/db-20261114-123000.sql.gz | mysql -u cpuser_kaveh185 -p cpuser_kaveh185
```
> ⚠️ پیش از بازگردانی، اسکریپت را با `--no-rollback` اجرا نکن و اول `mysqldump` از وضعیت فعلی بگیر.

---

## عیب‌یابی — خطاهای رایج و راه‌حل دقیق

| نشانه | علت | راه‌حل |
|---|---|---|
| صفحهٔ 504 یا «Application failed to start» | خطا در import یا `.env` ناقص | `Setup Python App → stderr.log` را ببین؛ اغلب کلید/دیتابیس است |
| `ModuleNotFoundError: celery` | وابستگی نصب نشده | `bash deploy/back/back-deploy.sh` (نصب را خودش می‌کند) |
| `Access denied for user` | رمز/نام دیتابیس غلط | `DB_NAME`/`DB_USER` با پیشوند `cpuser_` چک کن |
| حلقهٔ ریدایرکت | `SECURE_SSL_REDIRECT=True` بدون SSL | اول AutoSSL را اجرا کن (گام ۱.۲) |
| `DisallowedHost` | دامنه در `DJANGO_ALLOWED_HOSTS` نیست | اضافه کن و اسکریپت را دوباره بزن |
| فایل‌های ایستا ۴۰۴ | `collectstatic` اجرا نشده | در اسکریپت خودکار است؛ اگر دستی: `python manage.py collectstatic` |
| health-check جواب نمی‌دهد ولی سایت بالا است | Passenger کند بالا می‌آید | ۳۰ ثانیه صبر و: `curl -s https://api.kaveh185.ir/api/v1/health/` |
| `--force` برای رد هشدار `check --deploy` | `SECURE_SSL_REDIRECT` خاموش است | فقط برای تست؛ در پروداکشن درستش کن |

---

## نقشهٔ فایل‌ها

```
deploy/
├── back-deploy.sh          ← همین اسکریپت (روی هاست اجرا می‌شود)
└── CPANEL-GUIDE.md         ← همین سند
```

**تست‌هایی که روی این اسکریپت انجام شده** (در محیط شبیه‌سازی cPanel):

| سناریو | نتیجه |
|---|---|
| استقرار اول با `--seed` و `--grant-admin` | ✅ ۲۲۷ مهاجرت، ۱۷ مسجد، ادمین ساخته شد |
| استقرار بدون تغییر کد (idempotent) | ✅ نصب وابستگی رد شد، بقیه سالم |
| کامیت سالم → ثبت «آخرین نسخهٔ سالم» | ✅ `.deploy-last-good` ثبت شد |
| کامیت خراب + health خراب | ✅ **بازگشت خودکار به نسخهٔ سالم** |
| health با ریدایرکت HTTPS | ✅ تشخیص می‌دهد و پشت پراکسی بررسی می‌کند |
| `check --deploy` با هشدار | ✅ متوقف می‌شود مگر `--force` |
