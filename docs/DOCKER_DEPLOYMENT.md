# راهنمای استقرار کانتینری با Docker Compose (`docs/DOCKER_DEPLOYMENT.md`)

پشتهٔ کامل پروداکشن کاوه ۱۸۵ شامل ۴ سرویس کانتینری (**Django + Gunicorn**، **PostgreSQL 16**، **Redis 7** و **Celery Worker**) در فایل [`docker-compose.yml`](../docker-compose.yml) پیکربندی شده است.

---

## ۱. راه‌اندازی سریع با Docker Compose

```bash
# ۱. ساخت ایمیج‌ها و بالا آوردن سرویس‌ها در پس‌زمینه
docker compose up -d --build

# ۲. بررسی سلامت زندهٔ سرویس
curl -i http://localhost:8000/api/v1/health/live/
curl -i http://localhost:8000/api/v1/health/ready/

# ۳. ساخت حساب مدیر کل
docker compose exec web python manage.py grant_admin \
  --phone 09120000000 \
  --national-id 0013542419 \
  --password StrongAdminPass!185
```

---

## ۲. ویژگی‌های امنیتی ایمیج Docker (`Dockerfile`)

- اجرای سرویس با کاربر غیرریشه (`USER kaveh` با شناسه `1001`).
- مجهز به `HEALTHCHECK` خودکار متصل به پروب `/api/v1/health/live/`.
- اجرای خودکار مایگریشن‌ها و بارگذاری اولیهٔ ۱۷ مسجد و بانک سوال (`seed_kaveh185`) در زمان بالا آمدن سرویس `web`.
