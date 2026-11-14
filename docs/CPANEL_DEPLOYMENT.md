# راهنمای گام‌به‌گام استقرار روی هاست لینوکس و cPanel / Passenger (`docs/CPANEL_DEPLOYMENT.md`)

معماری بک‌اند سامانهٔ کاوه ۱۸۵ به‌گونه‌ای طراحی شده است که علاوه بر استقرار کانتینری (Docker)، به‌طور کامل با هاست‌های اشتراکی لینوکس مجهز به **cPanel (`Setup Python App` / `Phusion Passenger`)** و دیتابیس‌های **MySQL / MariaDB / PostgreSQL** سازگار باشد (بدون نیاز اجباری به Redis یا Celery).

---

## ۱. مراحل استقرار در cPanel

1. **ایجاد اپلیکیشن پایتون (`Setup Python App`)**:
   - نسخهٔ پایتون: `Python 3.12` یا `3.13`
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
   source ~/virtualenv/Kaveh185-Back/3.13/bin/activate
   cd ~/Kaveh185-Back
   pip install -r requirements.txt
   python manage.py migrate
   python manage.py collectstatic --noinput
   python manage.py seed_kaveh185
   python manage.py grant_admin --phone 09120000000 --national-id 0013542419 --password <StrongPassword>
   ```

4. **تنظیم Cron Jobها در cPanel**:
   - دستورات پیشنهادی در فایل [`deploy/cpanel/cron_jobs.txt`](../deploy/cpanel/cron_jobs.txt) قرار داده شده‌اند.
