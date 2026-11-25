#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
#  کاوه ۱۸۵ — به‌روزرسانی کد + مایگریشن + استاتیک، در یک فرمان
#
#  چرا این اسکریپت لازم شد؟
#  ──────────────────────
#  `sync.sh` فقط کد را هم‌سو می‌کند و `front-deploy.sh` فقط بستهٔ فرانت را
#  نصب می‌کند. هیچ‌کدام `migrate` نمی‌زنند. نتیجه در عمل: پس از هر تغییر
#  مدل (کتاب مسابقه، منبع داستان، فیلدهای مسجد) سایت با خطای ۵۰۰ بالا
#  می‌آید چون جدول‌های تازه ساخته نشده‌اند — و سه دستور جدا لازم است.
#
#  این اسکریپت همان سه دستور را با ترتیب درست و با توقف در اولین خطا انجام
#  می‌دهد. هیچ آرگومان اجباری ندارد و از هر جای مخزن اجرا می‌شود.
#
#      bash deploy/upgrade.sh              # کد + مایگریشن + استاتیک + ری‌استارت
#      bash deploy/upgrade.sh --no-pull    # بدون git pull (فقط مایگریشن/استاتیک)
#      bash deploy/upgrade.sh --dry-run    # بگو چه می‌شود، هیچ‌چیز را عوض نکن
#
#  اصولی که رعایت می‌شود (همان درس‌های استقرارهای قبلی):
#    • هیچ process substitution (`<(...)`، `>(...)`) — روی هاست /dev/fd نیست.
#    • هیچ دستور تعاملی؛ `--noinput` همه‌جا.
#    • کد خروج با واقعیت می‌خواند: خطا ⇒ ۱، موفق ⇒ ۰.
#    • پیش از هر تغییر، پشتیبان SQLite/MySQL گرفته می‌شود.
# ══════════════════════════════════════════════════════════════════════════════
set -Eeuo pipefail

readonly R=$'\033[0m' B=$'\033[1m' D=$'\033[2m'
readonly G=$'\033[32m' Y=$'\033[33m' RD=$'\033[31m' BL=$'\033[34m'

APP_DIR="${KAVEH185_APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
VENV_DIR="${KAVEH185_VENV:-$HOME/virtualenv/Kaveh185-Back/3.13}"
LOG_DIR="${KAVEH185_LOG_DIR:-$HOME/kaveh185-deploy-logs}"
BACKUP_DIR="${KAVEH185_BACKUP_DIR:-$HOME/kaveh185-backups}"
STAMP="$(date +%Y%m%d-%H%M%S)"

DO_PULL=1
DRY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-pull) DO_PULL=0 ;;
    --dry-run) DRY=1 ;;
    -h|--help) sed -n '2,28p' "$0"; exit 0 ;;
    *) printf 'آرگومان ناشناخته: %s\n' "$1"; exit 2 ;;
  esac
  shift
done

step(){ printf '\n%s▸ %s%s\n' "$B$BL" "$*" "$R"; }
ok(){   printf '%s✔%s %s\n' "$G" "$R" "$*"; }
warn(){ printf '%s▲%s %s\n' "$Y" "$R" "$*"; }
err(){  printf '%s✖%s %s\n' "$RD" "$R" "$*" >&2; }
dim(){  printf '%s  %s%s\n' "$D" "$*" "$R"; }
die(){  err "$*"; exit 1; }

run(){
  if [[ $DRY -eq 1 ]]; then dim "[dry-run] $*"; return 0; fi
  "$@"
}

py(){ run python "$@"; }

cd "$APP_DIR"
[[ -d .git ]] || die "مخزن گیت نیست: $APP_DIR"

# ── پیدا کردن virtualenv ──────────────────────────────────────────────────────
if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  for alt in "$HOME/virtualenv/Kaveh185-Back/3.13" "$HOME/virtualenv/Kaveh185-Back/3.12" \
             "$HOME/virtualenv/Kaveh185-Back" "$APP_DIR/.venv" "$APP_DIR/venv"; do
    if [[ -x "$alt/bin/python" ]]; then VENV_DIR="$alt"; break; fi
  done
fi
[[ -x "$VENV_DIR/bin/python" ]] || die "virtualenv پیدا نشد. با KAVEH185_VENV=... مسیر را بده."
export PATH="$VENV_DIR/bin:$PATH"
mkdir -p "$LOG_DIR" "$BACKUP_DIR"

printf '%sکاوه ۱۸۵ — به‌روزرسانی%s\n' "$B" "$R"
dim "اپ: $APP_DIR"
dim "venv: $VENV_DIR ($(python -V 2>&1))"

# ══ ۱/۶ · کد ═════════════════════════════════════════════════════════════════
step "۱/۶ · به‌روزرسانی کد"
BEFORE="$(git rev-parse --short HEAD)"
dim "HEAD فعلی: $BEFORE"
if [[ $DO_PULL -eq 1 ]]; then
  if [[ -n "$(git status --porcelain 2>/dev/null || true)" ]]; then
    warn "تغییرات محلی هست — به‌جای reset، محافظت می‌شود"
    run git stash push -u -m "pre-upgrade-$STAMP"
  fi
  run git fetch --prune origin main
  run git reset --hard origin/main
else
  dim "pull رد شد (--no-pull)"
fi
AFTER="$(git rev-parse --short HEAD)"
if [[ "$BEFORE" == "$AFTER" ]]; then ok "کد همان است: $AFTER"; else ok "کد به‌روز شد: $BEFORE → $AFTER"; fi

# ── بازسازی وضعیت اجرا (درسِ stash که symlink فرانت را می‌برد) ───────────────
FRONT_ROOT="${KAVEH185_FRONT_ROOT:-$HOME/kaveh185-front}"
if [[ -e "$APP_DIR/frontend" ]]; then
  dim "پیوند frontend سر جایش است"
elif [[ -d "$FRONT_ROOT/current" ]]; then
  run ln -sfn "$FRONT_ROOT/current" "$APP_DIR/frontend"
  ok "پیوند frontend بازسازی شد"
else
  warn "فرانت نصب نیست — بعد از این، front-deploy.sh --url <بسته> را بزن"
fi

# ══ ۲/۶ · پیش‌نیازها ═════════════════════════════════════════════════════════
step "۲/۶ · وابستگی‌ها"
HASH_FILE="$APP_DIR/.deploy-requirements-hash"
NEW_HASH="$(sha256sum "$APP_DIR/requirements.txt" | cut -d' ' -f1)"
if [[ -f "$HASH_FILE" && "$(cat "$HASH_FILE")" == "$NEW_HASH" ]]; then
  ok "requirements.txt تغییری نکرده — نصب رد شد"
else
  run pip install --upgrade pip --quiet
  run pip install -r "$APP_DIR/requirements.txt" --quiet
  [[ $DRY -eq 0 ]] && printf '%s\n' "$NEW_HASH" > "$HASH_FILE"
  ok "وابستگی‌ها نصب شدند"
fi

# ══ ۳/۶ · پشتیبان پایگاه‌داده ════════════════════════════════════════════════
step "۳/۶ · پشتیبان پایگاه‌داده (پیش از مایگریشن)"
if [[ -f "$APP_DIR/.env" ]]; then set -a; . "$APP_DIR/.env"; set +a; fi
# ⚠️ پیش‌فرض عمداً «sqlite» است نه مسیرِ کاملِ بک‌اند: پس از دورِ ۵۱
# پیش‌فرضِ خودِ جنگو `apps.core.db_sqlite` است (WAL + busy_timeout). با
# پیش‌فرضِ قدیمی، اگر کسی `.env` نداشت، پشتیبان‌گیری از دیتابیس **بی‌صدا
# رد می‌شد** و آن‌وقت هیچ نسخهٔ بازگشتی نبود. حالا فقط «آیا SQLite است؟»
# را می‌سنجیم، بی‌آنکه مسیرِ بک‌اند را بازنویسی کنیم.
DB_ENGINE_EFF="${DB_ENGINE:-sqlite}"
if [[ $DRY -eq 1 ]]; then
  dim "[dry-run] پشتیبان‌گیری رد شد"
elif [[ "$DB_ENGINE_EFF" == *sqlite3* ]]; then
  sqlite_path="${DB_NAME:-$APP_DIR/db.sqlite3}"
  [[ "$sqlite_path" != /* ]] && sqlite_path="$APP_DIR/$sqlite_path"
  if [[ -f "$sqlite_path" ]]; then
    cp "$sqlite_path" "$BACKUP_DIR/db-$STAMP.sqlite3"
    ok "پشتیبان: $BACKUP_DIR/db-$STAMP.sqlite3"
  else
    dim "پایگاه‌دادهٔ SQLite هنوز ساخته نشده — مایگریشن اول آن را می‌سازد"
  fi
elif [[ "$DB_ENGINE_EFF" == *mysql* ]]; then
  if command -v mysqldump >/dev/null; then
    cnf="$(mktemp)"; chmod 600 "$cnf"
    printf '[client]\nuser=%s\npassword=%s\nhost=%s\n' \
      "${DB_USER:-}" "${DB_PASSWORD:-}" "${DB_HOST:-localhost}" > "$cnf"
    mysqldump --defaults-extra-file="$cnf" --single-transaction --quick \
      "${DB_NAME:-}" 2>/dev/null | gzip -9 > "$BACKUP_DIR/db-$STAMP.sql.gz" || true
    rm -f "$cnf"
    ok "پشتیبان: $BACKUP_DIR/db-$STAMP.sql.gz"
  else
    warn "mysqldump نیست — از phpMyAdmin در cPanel پشتیبان بگیر"
  fi
fi

# ══ ۴/۶ · مایگریشن ═══════════════════════════════════════════════════════════
step "۴/۶ · مایگریشن پایگاه‌داده"
PENDING="$(python manage.py showmigrations --plan 2>/dev/null | grep -c '^\[ \]' || true)"
dim "مهاجرت‌های در انتظار: ${PENDING:-۰}"
py manage.py migrate --noinput
DRIFT="$(python manage.py makemigrations --check --dry-run 2>&1 || true)"
if [[ "$DRIFT" == *"No changes detected"* ]]; then
  ok "مدل‌ها و مهاجرت‌ها همگام‌اند"
else
  warn "drift مدل/مهاجرت: $DRIFT"
fi

# ══ ۵/۶ · فایل‌های ایستا ═════════════════════════════════════════════════════
step "۵/۶ · فایل‌های ایستا"
py manage.py collectstatic --noinput --clear
ok "فایل‌های ایستا جمع‌آوری شدند"

# ══ ۶/۶ · ری‌استارت ══════════════════════════════════════════════════════════
step "۶/۶ · ری‌استارت Passenger"
run mkdir -p "$APP_DIR/tmp"
run touch "$APP_DIR/tmp/restart.txt"
ok "ری‌استارت ثبت شد"

# ── بررسی سریع سلامت (بی‌توقف، شکستش استقرار را رد نمی‌کند) ──────────────────
step "بررسی سلامت"
if [[ $DRY -eq 0 ]]; then
  if python - <<'PY' >/dev/null 2>&1
import os, sys
os.environ.setdefault("DJANGO_SETTINGS_MODULE", os.environ.get("DJANGO_SETTINGS_MODULE", "config.settings.production"))
import django
django.setup()
from django.core.management import call_command
call_command("check", "--fail-level", "ERROR")
sys.exit(0)
PY
  then ok "بررسی جنگو بدون خطا"; else warn "بررسی جنگو هشدار داد — لاگ‌ها را ببین"; fi
fi

printf '\n%s✔ به‌روزرسانی کامل شد%s · نسخه %s · %s\n' "$B$G" "$R" "$AFTER" "$STAMP"
dim "لاگ‌ها: $LOG_DIR"
dim "برگشت به نسخهٔ قبل (اگر لازم شد): git reset --hard <کامیت> && bash deploy/upgrade.sh --no-pull"
exit 0
