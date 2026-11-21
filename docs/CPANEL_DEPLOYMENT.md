# راهنمای گام‌به‌گام استقرار روی هاست لینوکس و cPanel / Passenger (`docs/CPANEL_DEPLOYMENT.md`)

معماری بک‌اند سامانهٔ کاوه ۱۸۵ به‌گونه‌ای طراحی شده است که علاوه بر استقرار کانتینری (Docker)، به‌طور کامل با هاست‌های اشتراکی لینوکس مجهز به **cPanel (`Setup Python App` / `Phusion Passenger`)** و دیتابیس‌های **MySQL / MariaDB / PostgreSQL** سازگار باشد (بدون نیاز اجباری به Redis یا Celery).

---

## ۰. انتخاب پایگاه داده — چرا MariaDB

Django 6.1 برای هر موتور، حداقل نسخه‌ای دارد که **خودش** بررسی می‌کند و اگر پایین‌تر باشد با `NotSupportedError` متوقف می‌شود:

| موتور | حداقل نسخه برای Django 6.1 | نسخهٔ این هاست | نتیجه |
|---|---|---|---|
| PostgreSQL | **۱۵** | 13.23 | ❌ رد می‌شود |
| MariaDB | **۱۰.۱۱** | 11.4.13 | ✅ پذیرفته می‌شود |
| MySQL | **۸.۴** | (همان MariaDB) | — |

شاهد از سورس نصب‌شده (`django/db/backends/mysql/features.py`):

```python
@cached_property
def minimum_database_version(self):
    if self.connection.mysql_is_mariadb:
        return (10, 11)
    else:
        return (8, 4)
```

**پس MariaDB 11.4.13 تنها گزینه‌ای است که رسماً پشتیبانی می‌شود.** PostgreSQL هاست (13.23) هم EOL شده است (نوامبر ۲۰۲۵) و هیچ نسخهٔ فعالی از Django آن را نمی‌پذیرد.

### تفاوت با PostgreSQL که عملاً اهمیت دارد

* **`utf8mb4`**: دادهٔ چهاربایتی (ایموجی) و فارسی با نیم‌فاصله عیناً ذخیره و بازخوانی می‌شود — با تست تأیید شده.
* **بدون کامپایل**: درایور `PyMySQL` خالص پایتون است؛ روی هاست اشتراکی که هدرهای MySQL و کامپایلر ندارد کار می‌کند (`config/__init__.py`).
* **بدون گیت نسخه**: نیازی به وصله یا بک‌اند سفارشی نیست — بک‌اند رسمی Django استفاده می‌شود.

### مهاجرت به PostgreSQL ۱۵+ (اگر روزی هاست ارتقا یافت)

`make-env.sh` پارامتر `--db-engine` دارد. کافی است:

```bash
bash deploy/host/make-env.sh --force --db-engine django.db.backends.postgresql \
  --db-port 5432 --db-name ... --db-user ... --db-password ...
```

ولی داده‌ها منتقل نمی‌شوند؛ `migrate` روی دیتابیس خالی اجرا می‌شود. برای انتقال داده از `dumpdata`/`loaddata` استفاده کنید.

---

## ۰.۱ ساخت دیتابیس با MySQL Database Wizard

در cPanel، بخش **MySQL Databases** و **MySQL Database Wizard** به یک چیز اشاره دارند: Wizard فقط رابط گام‌به‌گام همان عملیات است (ساخت دیتابیس → ساخت کاربر → افزودن کاربر به دیتابیس → تعیین مجوز). روی این هاست هر دو مسیر نتیجهٔ یکسانی می‌دهند.

مسیر خط فرمان (که همین پروژه استفاده می‌کند و قابل بازتولید است):

```bash
uapi --output=json Mysql create_database name=kaveh185
uapi --output=json Mysql create_user name=k185app password='<strong-pass>'
uapi --output=json Mysql set_privileges_on_database \
  user=k185app database=kaveh185 privileges=ALL
```

سپس تأیید کنید که charset درست است:

```bash
mysql -u kavehir_k185app -p -e "SELECT @@character_set_database, @@collation_database;"
# انتظار: utf8mb4 | utf8mb4_unicode_ci
```

> ⚠️ اگر charset روی `latin1` یا `utf8` (سه‌بایتی) باشد، متن فارسی خراب ذخیره می‌شود. `make-env.sh` این را کنترل نمی‌کند؛ دیتابیس باید از ابتدا `utf8mb4` ساخته شود.

---

## ۱. مراحل استقرار در cPanel

1. **ایجاد اپلیکیشن پایتون (`Setup Python App`)**:
   - نسخهٔ پایتون: `Python 3.12` (همان نسخه‌ای که در `Setup Python App` انتخاب می‌کنید)
   - مسیر اپلیکیشن (`Application root`): `Kaveh185-Back`
   - فایل راه‌انداز (`Application startup file`): `passenger_wsgi.py`
   - نقطهٔ ورود (`Application Entry point`): `application`

2. **تنظیم متغیرهای محیطی (`.env`)**:
   ```ini
   DJANGO_SETTINGS_MODULE=config.settings.production
   DJANGO_DEBUG=False
   DJANGO_SECRET_KEY=<64-char-secret>
   PII_ENCRYPTION_KEY=<32-byte-secret>
   PII_BLIND_INDEX_KEY=<32-byte-secret>
   DJANGO_ALLOWED_HOSTS=kaveh185.ir,api.kaveh185.ir
   DB_ENGINE=django.db.backends.mysql
   DB_NAME=cpaneluser_kaveh185
   DB_USER=cpaneluser_dbuser
   DB_PASSWORD=<db-password>
   DB_HOST=localhost
   DB_PORT=3306
   ```

3. **نصب پکیج‌ها، مایگریشن و بارگذاری اولیه**:
   ```bash
   source ~/virtualenv/Kaveh185-Back/3.12/bin/activate   # مسیرِ واقعیِ خود را بگذارید:
   # ls ~/virtualenv/Kaveh185-Back/*/bin/activate
   cd ~/Kaveh185-Back
   pip install -r requirements.txt
   python manage.py migrate
   python manage.py collectstatic --noinput
   python manage.py seed_kaveh185
   python manage.py grant_admin --phone 09120000000 --national-id 0013542419 --password <StrongPassword>
   ```

4. **تنظیم Cron Jobها در cPanel**:
   - دستورات پیشنهادی در فایل [`deploy/cpanel/cron_jobs.txt`](../deploy/cpanel/cron_jobs.txt) قرار داده شده‌اند.

## ۵. کانالِ ارسالِ کدِ تأیید بدونِ پنل پیامکی (رباتِ بله)

برای فعال شدنِ آزمون، سامانه باید بتواند کدِ تأیید را به شرکت‌کننده برساند.
ارسالِ پیامک در ایران به پنلِ رسمی و اینماد نیاز دارد؛ تا آن زمان **رباتِ بله**
همین کار را بی‌هزینه انجام می‌دهد. راه‌اندازی سه قدم است و یک‌بار انجام می‌شود.

**۰) راه‌اندازیِ یک‌مرحله‌ای (سریع‌ترین راه)**

اگر توکنِ ربات را دارید، همین یک دستور همهٔ کارها را می‌کند: نوشتن در `.env`
(با پشتیبان)، تستِ واقعیِ تماس با بله، و ثبتِ وب‌هوک با کلیدِ امن.

```bash
cd ~/Kaveh185-Back
PY=~/virtualenv/Kaveh185-Back/3.12/bin/python   # مسیرِ واقعیِ خودتان

# توکن را در فایلِ موقت بگذارید تا در تاریخچهٔ شل نماند
read -rsp "توکن: " T && echo && printf '%s' "$T" > ~/.bale_token && unset T
$PY manage.py bale_setup --from-stdin < ~/.bale_token
rm -f ~/.bale_token
```

⚠️ **مهم‌ترین نکته:** بعد از نوشتنِ `.env` باید پروسهٔ سایت **restart** شود
(در cPanel: `Setup Python App` → `Restart`؛ یا `touch ~/Kaveh185-Back/tmp/restart.txt`).
تا وقتی restart نشود، اپلیکیشن همان مقدارِ قدیمی را در حافظه دارد و خطای
«BALE_BOT_TOKEN تنظیم نشده است» **با اینکه توکن در فایل هست** تکرار می‌شود.
برای دیدنِ همین تفکیک:

```bash
$PY manage.py bale_setup --status
```

اگر نوشت «در فایل: هست · در پروسهٔ فعلی: نیست» ⇒ فقط restart لازم است.

**۱) ساختِ ربات و گرفتنِ توکن**

1. در بله به [`@BotFather`](https://ble.ir/botfather) پیام بدهید و `/newbot` را بزنید.
2. یک نام و یک نام کاربریِ لاتین (مثلاً `kaveh185_bot`) انتخاب کنید.
3. توکنی که می‌دهد را در `.env` بگذارید:

   ```ini
   BALE_BOT_TOKEN=<توکن>
   BALE_BOT_USERNAME=kaveh185_bot
   BALE_API_BASE=https://tapi.bale.ai
   # اختیاری ولی توصیه‌شده: اگر وب‌هوک را تنظیم کردید، همین رشته را بگذارید
   BALE_WEBHOOK_SECRET=<یک-رشته-تصادفی>
   ```

   ⚠️ توکن مثلِ رمز است: در `.env` می‌ماند، در گیت نمی‌رود و هیچ‌جا لاگ نمی‌شود.

**۲) خواندنِ پیام‌های ربات (یکی از دو راه)**

- **راهِ ساده — cron:** خطِ `bale_inbox` در
  [`deploy/cpanel/cron_jobs.txt`](../deploy/cpanel/cron_jobs.txt) هر دقیقه صندوقِ
  ربات را می‌خواند. دستورِ `deliver_outbox` هم هر ۲ دقیقه صفِ پیام‌ها را خالی
  می‌کند و اگر پیامک در دسترس نباشد، کد را از بله می‌فرستد.
- **راهِ فوری — وب‌هوک:** روی سرورِ همیشه‌روشن، یک‌بار به بله بگویید آپدیت‌ها را
  به این نشانی بفرستد (پاسخ آنی، بدونِ تأخیرِ یک‌دقیقه‌ای):

  ```bash
  curl -X POST "https://tapi.bale.ai/bot<TOKEN>/setWebhook" \
       -H "Content-Type: application/json" \
       -d '{"url": "https://api.kaveh185.ir/api/v1/notifications/bale/webhook/", "secret_token": "<BALE_WEBHOOK_SECRET>"}'
  ```

  وب‌هوک در `apps/notifications/views.py::BaleWebhookAPIView` است و اگر
  `BALE_WEBHOOK_SECRET` تنظیم شده باشد، درخواست‌های بدونِ هدرِ درست را رد می‌کند.

**۳) آزمونِ سریع — یک دستور، چهار سنجه**

```bash
python manage.py bale_check                        # توکن، پاسخِ بله، وب‌هوک/کران، کاربرانِ وصل‌شده
python manage.py bale_check --send-to 09121234567  # + یک پیامِ آزمایشی به شمارهٔ وصل‌شده
```

اگر چیزی کم باشد، همین دستور صریح می‌گوید چه کاری لازم است؛ لازم نیست
جایی لاگ را بخوانید.

```bash
python manage.py bale_inbox --dry-run --verbose   # چه پیام‌هایی در صف است؟
python manage.py shell -c "from apps.notifications.bale import get_me; print(get_me())"   # صحتِ توکن
```

**چطور برای کاربر کار می‌کند؟** بعد از ثبت‌نام، اگر شماره به ربات وصل نباشد
سامانه یک **کدِ اتصالِ ۶ کاراکتری** (مثلِ `A7K2QF`) در همان صفحه نشان می‌دهد؛
کاربر آن را در بله برای ربات می‌فرستد و ربات پاسخ می‌دهد «اتصال برقرار شد».
از آن لحظه هر کدِ تأییدی که برای آن شماره صادر شود، در همان گفتگوی بله می‌آید.
اگر شماره قبلاً وصل باشد، کدِ تأیید بی‌درنگ در بله می‌رود و هیچ کدِ اتصالی
ساخته نمی‌شود. جدول‌های درگیر: `notifications_balesubscriber` (نگاشتِ شماره ⇄
گفتگو) و `notifications_balelinkcode` (کدهای اتصال، فقط هش‌شده و کوتاه‌عمر).

## ۶. عیب‌یابیِ سریع روی سرور (بدونِ نصبِ چیزی)

**«`python: command not found`»** یعنی یا virtualenv فعال نشده، یا نسخهٔ مسیر عوض شده است:

```bash
ls ~/virtualenv/Kaveh185-Back/*/bin/python        # مسیرِ واقعی (مثلاً …/3.12/bin/python)
~/virtualenv/Kaveh185-Back/3.12/bin/python -V     # باید نسخهٔ پایتون را چاپ کند
```

از این پس همه‌جا از **همان مسیرِ کامل** استفاده کنید (کران هم همین را می‌خواهد):

```bash
cd ~/Kaveh185-Back
~/virtualenv/Kaveh185-Back/3.12/bin/python manage.py migrate
~/virtualenv/Kaveh185-Back/3.12/bin/python manage.py bale_check
```

**«`python3: command not found`» در حالی که سایت کار می‌کند.** طبیعی است: پایتون روی
این هاست فقط داخلِ virtualenv نصب است و از پوستهٔ عادی دیده نمی‌شود. برای اسکریپتِ
کوتاه، از همان مفسرِ virtualenv استفاده کنید. این نسخه هر کاری را با یک دستور انجام
می‌دهد — خواندنِ `.env`، ثبتِ وب‌هوک، و تستِ رسیدنِ پیام:

```bash
cd ~/Kaveh185-Back && ~/virtualenv/Kaveh185-Back/3.12/bin/python manage.py bale_webhook
```

پاسخِ سالم چنین است: `{"ok": true, ... "description": "Webhook was set"}`.

- `manage.py bale_webhook --show` وضعیتِ فعلیِ وب‌هوک را نشان می‌دهد.
- `manage.py bale_webhook --delete` وب‌هوک را برمی‌دارد (برای برگشتن به کران).

**اگر نوشت `Webhook was set` ولی ربات جواب نمی‌دهد**، یعنی بله به نشانیِ ما نمی‌رسد؛
وب‌هوک را بردارید و از کران استفاده کنید:

```bash
~/virtualenv/Kaveh185-Back/3.12/bin/python manage.py bale_webhook --delete
~/virtualenv/Kaveh185-Back/3.12/bin/python manage.py bale_inbox --verbose   # تستِ دستیِ صندوق
```

سپس خطِ `bale_inbox` را در کران هر دقیقه اجرا کنید (فایل
[`deploy/cpanel/cron_jobs.txt`](../deploy/cpanel/cron_jobs.txt)).


## ۷. چرا `www` برای وب‌هوک اشتباه است؟

`bale_webhook` نشانی را از `ALLOWED_HOSTS` می‌سازد. اگر ترتیبِ دامنه‌ها
`kaveh185.ir, www.kaveh185.ir` باشد و `api.` وجود نداشته باشد، دستور
**اولین دامنه** را برمی‌دارد و نتیجه می‌شود:

```
✗ https://www.kaveh185.ir/api/v1/…      ← اشتباه
✓ https://api.kaveh185.ir/api/v1/…      ← درست
```

نشانه‌اش این است: `setWebhook` می‌گوید `Webhook was set` و آپدیت‌ها هم صفر
می‌مانند، ولی ربات هیچ پاسخی نمی‌دهد. راهِ قطعی، صریح گفتنِ نشانی است:

```bash
# در .env (بهتر است یک‌بار برای همیشه):
BALE_WEBHOOK_URL=https://api.kaveh185.ir/api/v1/notifications/bale/webhook/

# یا دستی:
python manage.py bale_webhook --url https://api.kaveh185.ir/api/v1/notifications/bale/webhook/
```

برای اطمینان، این نشانی باید در مرورگر همین پاسخ را بدهد (نه ۴۰۴):

```json
{"ok": true, "service": "kaveh185-bale-webhook", "configured": true, "secret_required": true}
```

اگر پاسخِ بالا نیامد، وب‌هوک را بردارید و از کران استفاده کنید:
`bale_webhook --delete` و سپس خطِ `bale_inbox` هر دقیقه.
