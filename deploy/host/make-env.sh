#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
#  ساخت فایل .env برای استقرار روی cPanel — کاوه ۱۸۵
#
#  چرا اسکریپت و نه دستور دستی؟
#    کلیدهای رمزنگاری باید تصادفی و یکتا باشند و نباید در تاریخچهٔ شل یا چت
#    بمانند. این اسکریپت کلیدها را با openssl می‌سازد، فایل را با مجوز ۶۰۰
#    می‌نویسد و اگر .env از قبل باشد، هرگز بازنویسی نمی‌کند (مگر --force).
#
#  استفاده:
#    bash deploy/host/make-env.sh --db-name kavehir_kaveh185 \
#         --db-user kavehir_kaveh185 --db-password 'XXXX'
# ══════════════════════════════════════════════════════════════════════════════
set -Eeuo pipefail

APP_DIR="${KAVEH185_APP_DIR:-$HOME/Kaveh185-Back}"
ENV_FILE="$APP_DIR/.env"
FORCE=0
DB_ENGINE="django.db.backends.mysql"
DB_NAME=""; DB_USER=""; DB_PASSWORD=""; DB_HOST="localhost"; DB_PORT="3306"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --db-engine)    DB_ENGINE="${2:-}"; shift 2 ;;
    --db-name)      DB_NAME="${2:-}"; shift 2 ;;
    --db-user)      DB_USER="${2:-}"; shift 2 ;;
    --db-password)  DB_PASSWORD="${2:-}"; shift 2 ;;
    --db-host)      DB_HOST="${2:-}"; shift 2 ;;
    --db-port)      DB_PORT="${2:-}"; shift 2 ;;
    --force)        FORCE=1; shift ;;
    -h|--help)      sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "گزینهٔ ناشناخته: $1" >&2; exit 2 ;;
  esac
done

[[ -n "$DB_NAME" && -n "$DB_USER" && -n "$DB_PASSWORD" ]] || {
  echo "خطا: --db-name و --db-user و --db-password الزامی‌اند" >&2; exit 2; }

[[ -d "$APP_DIR" ]] || { echo "خطا: $APP_DIR نیست" >&2; exit 2; }
if [[ -f "$ENV_FILE" && $FORCE -eq 0 ]]; then
  echo "✖ .env از قبل هست — برای بازنویسی --force بده (کلیدهای فعلی از بین می‌روند)" >&2
  exit 3
fi

gen() { openssl rand -hex "${1:-32}"; }

SECRET_KEY="$(gen 40)"
PII_KEY="$(gen 32)"
PII_INDEX_KEY="$(gen 32)"

umask 077
cat > "$ENV_FILE" <<EOF
# ⚠️ فایل محرمانه — این فایل هرگز نباید در گیت باشد.
# ساخته‌شده در: $(date -u '+%Y-%m-%dT%H:%M:%SZ')
# بازسازی: bash deploy/host/make-env.sh --force --db-name ... --db-user ... --db-password ...

DJANGO_SETTINGS_MODULE=config.settings.production
DJANGO_DEBUG=False
DJANGO_SECRET_KEY=$SECRET_KEY
PII_ENCRYPTION_KEY=$PII_KEY
PII_BLIND_INDEX_KEY=$PII_INDEX_KEY
DJANGO_ALLOWED_HOSTS=kaveh185.ir,www.kaveh185.ir,api.kaveh185.ir,localhost,127.0.0.1
DJANGO_ADMIN_URL=secure-kaveh185-admin/

# پایگاه داده — MariaDB 11.4 روی همین هاست (cPanel)
# چرا MariaDB؟ Django 6.1 حداقل MariaDB 10.11 می‌خواهد و هاست 11.4.13 دارد
# (تأیید: mysql --version → 11.4.13-MariaDB). PostgreSQL هاست فقط 13.23 است
# و Django 6.1 حداقل ۱۵ می‌خواهد، پس MariaDB تنها مسیر با پشتیبانی رسمی است.
# درایور: PyMySQL (خالص پایتون، بدون نیاز به کامپایل) — نگاه کنید به config/__init__.py
DB_ENGINE=$DB_ENGINE
DB_NAME=$DB_NAME
DB_USER=$DB_USER
DB_PASSWORD=$DB_PASSWORD
DB_HOST=$DB_HOST
DB_PORT=$DB_PORT
DB_CONN_MAX_AGE=60

# کش و Celery — روی هاست اشتراکی خالی می‌مانند و به LocMem/Database برمی‌گردند
REDIS_URL=
CELERY_BROKER_URL=
CELERY_RESULT_BACKEND=

# پیامک — فعلاً console؛ بعداً اعتبارنامهٔ پنل پیامک
SMS_PROVIDER=console
SMS_API_URL=
SMS_API_KEY=
SMS_SENDER_LINE=3000185
OTP_EXPOSE_DEBUG_CODE=False

# امنیت و پایش
CORS_ALLOWED_ORIGINS=https://kaveh185.ir,https://www.kaveh185.ir
API_DOCS_PUBLIC=True
METRICS_PUBLIC_ENABLED=False
SECURE_SSL_REDIRECT=True
EOF
chmod 600 "$ENV_FILE"

echo "✔ ساخته شد: $ENV_FILE (مجوز $(stat -c '%a' "$ENV_FILE"))"
echo "  DJANGO_SETTINGS_MODULE : config.settings.production"
echo "  DB_ENGINE              : $DB_ENGINE"
echo "  DB_NAME                : $DB_NAME"
echo "  DB_USER                : $DB_USER"
echo "  کلیدها                 : SECRET_KEY، PII_ENCRYPTION_KEY، PII_BLIND_INDEX_KEY (هر سه تصادفی)"
echo
echo "⚠️ از این لحظه اگر PII_ENCRYPTION_KEY عوض شود، دادهٔ هویتیِ موجود قابل خواندن نیست."
echo "   از فایل پشتیبان بگیرید: cp $ENV_FILE ~/kaveh185-env-backup-\$(date +%F).env"
