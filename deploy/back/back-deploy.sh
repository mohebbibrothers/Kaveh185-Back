#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
#  کاوه ۱۸۵ — اسکریپت استقرار بک‌اند روی هاست اشتراکی cPanel
#  (Phusion Passenger / Setup Python App + MySQL)
#
#  اصل طراحی: idempotent — هر چند بار هم اجرا شود، نتیجه یکسان است.
#  اصل طراحی: fail-safe — اگر هر مرحله شکست خورد، به نسخهٔ قبلی برمی‌گردد.
#
#  اجرا (روی هاست، در ترمینال cPanel یا SSH):
#      bash ~/Kaveh185-Back/deploy/back-deploy.sh
#
#  گزینه‌ها:
#      --dry-run     فقط نشان بده چه کاری می‌کند، انجام نده
#      --no-pull     بدون git pull (برای وقتی خودت کد را گذاشتی)
#      --no-rollback بازگشت خودکار را خاموش کن (برای دیباگ)
#      --seed        دانه‌ریزی اولیهٔ ۱۷ مسجد + تنظیمات + بانک سوال (فقط بار اول)
#      --with-demo   همراه دانه‌ریزی، داده‌های دمو هم بیاید (فقط برای صحنهٔ تمرین!)
#      --grant-admin «شماره|کدملی|رمز»  ساخت/به‌روزرسانی ادمین
#      --force       ادامه بده حتی اگر check --deploy هشدار داد
#
#  پیش‌نیاز (یک‌بار در cPanel انجام شود):
#      ۱. MySQL Database + User ساخته شود (Users → MySQL® Databases)
#      ۲. Setup Python App با Python 3.12/3.13، ریشهٔ اپ: Kaveh185-Back
#         فایل راه‌انداز: passenger_wsgi.py — Entry point: application
#      ۳. فایل ~/Kaveh185-Back/.env از روی .env.example ساخته و پر شود
#      ۴. دامنه api.kaveh185.ir به همین اپلیکیشن Map شود
# ══════════════════════════════════════════════════════════════════════════════
set -Eeuo pipefail

# ── نسخه و رنگ‌ها ────────────────────────────────────────────────────────────
SCRIPT_VERSION="1.0.0"
readonly C_RESET=$'\033[0m' C_BOLD=$'\033[1m' C_DIM=$'\033[2m'
readonly C_GREEN=$'\033[32m' C_YELLOW=$'\033[33m' C_RED=$'\033[31m' C_BLUE=$'\033[34m' C_CYAN=$'\033[36m'
readonly TAG="[Kaveh185-Back ${SCRIPT_VERSION}]"

# ── پیش‌فرض‌ها (با .env.override یا متغیر محیطی قابل تغییر) ──────────────────
APP_DIR="${KAVEH185_APP_DIR:-$HOME/Kaveh185-Back}"
REPO_URL="${KAVEH185_REPO_URL:-https://github.com/mohebbibrothers/Kaveh185-Back.git}"
BRANCH="${KAVEH185_BRANCH:-main}"
VENV_DIR="${KAVEH185_VENV:-$HOME/virtualenv/Kaveh185-Back/3.13}"
LOG_DIR="${KAVEH185_LOG_DIR:-$HOME/kaveh185-deploy-logs}"
HEALTH_URL="${KAVEH185_HEALTH_URL:-https://api.kaveh185.ir/api/v1/health/}"
BACKUP_DIR="${KAVEH185_BACKUP_DIR:-$HOME/kaveh185-backups}"
KEEP_BACKUPS="${KAVEH185_KEEP_BACKUPS:-5}"

DRY_RUN=0; DO_PULL=1; ROLLBACK=1; DO_SEED=0; WITH_DEMO=0; FORCE=0
GRANT_ADMIN=""

# ── پارس آرگومان‌ها ─────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --no-pull) DO_PULL=0 ;;
    --no-rollback) ROLLBACK=0 ;;
    --seed) DO_SEED=1 ;;
    --with-demo) DO_SEED=1; WITH_DEMO=1 ;;
    --grant-admin) GRANT_ADMIN="${2:-}"; shift ;;
    --force) FORCE=1 ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "${TAG} ${C_RED}آرگومان ناشناخته: $1${C_RESET}"; exit 2 ;;
  esac
  shift
done

# ── ابزارها ─────────────────────────────────────────────────────────────────
mkdir -p "$LOG_DIR" "$BACKUP_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="$LOG_DIR/deploy-$STAMP.log"
exec > >(tee -a "$LOG_FILE") 2>&1

say()  { printf '%s %s\n' "${TAG}" "$*"; }
info() { say "${C_BLUE}•${C_RESET} $*"; }
ok()   { say "${C_GREEN}✔${C_RESET} $*"; }
warn() { say "${C_YELLOW}▲${C_RESET} $*"; }
die()  { say "${C_RED}✖ $*${C_RESET}"; exit 1; }
step() { printf '\n%s %s\n' "${C_BOLD}${C_CYAN}▸ $*${C_RESET}" "${C_DIM}────────────────────────${C_RESET}"; }

run() {
  if [[ $DRY_RUN -eq 1 ]]; then
    say "${C_DIM}[dry-run]${C_RESET} $*"
  else
    "$@"
  fi
}

# اجرای دستور در venv با PYTHONPATH درست
py() {
  if [[ $DRY_RUN -eq 1 ]]; then say "${C_DIM}[dry-run]${C_RESET} python $*"; return 0; fi
  ( cd "$APP_DIR" && PATH="$VENV_DIR/bin:$PATH" python "$@" )
}

call_passenger_restart() {
  if [[ $DRY_RUN -eq 1 ]]; then say "${C_DIM}[dry-run]${C_RESET} touch tmp/restart.txt"; return 0; fi
  mkdir -p "$APP_DIR/tmp"; date > "$APP_DIR/tmp/restart.txt"
}

# ── تله‌ها ───────────────────────────────────────────────────────────────────
PREV_COMMIT=""; STAGE="init"; LAST_GOOD_FILE=""
rollback_to_last_good() {
  [[ $ROLLBACK -eq 1 ]] || { warn "rollback خاموش است (--no-rollback)"; return 0; }
  [[ $DRY_RUN -eq 1 ]] && { info "[dry-run] rollback رد شد"; return 0; }
  local target=""
  if [[ -n "$LAST_GOOD_FILE" && -f "$LAST_GOOD_FILE" ]]; then
    target="$(cat "$LAST_GOOD_FILE" 2>/dev/null || true)"
  fi
  # اگر «آخرین نسخهٔ سالم» نداریم، به کامیت قبل از pull برگرد
  [[ -z "$target" && -n "$PREV_COMMIT" ]] && target="$PREV_COMMIT"
  [[ -z "$target" ]] && { warn "نقطهٔ بازگشتی وجود ندارد"; return 0; }
  if [[ "$(git -C "$APP_DIR" rev-parse HEAD)" == "$target" ]]; then
    warn "همین حالا روی همان کامیت هستیم — چیزی برای بازگشت نیست"
    return 0
  fi
  warn "بازگشت به آخرین نسخهٔ سالم: ${target:0:8}"
  if git -C "$APP_DIR" reset --hard "$target" >/dev/null 2>&1; then
    call_passenger_restart || true
    ok "بازگشت انجام شد — سایت روی نسخهٔ سالم است"
  else
    warn "بازگشت شکست خورد — دستی بررسی کن"
  fi
}
on_error() {
  local line=$1
  warn "شکست در خط $line (مرحله: $STAGE)"
  rollback_to_last_good
  die "استقرار ناموفق. لاگ: $LOG_FILE"
}
trap 'on_error $LINENO' ERR

# ══════════════════════════════════════════════════════════════════════════════
step "۰/۸ · بررسی پیش‌نیازها"
# ══════════════════════════════════════════════════════════════════════════════
[[ -d "$APP_DIR" ]] || die "پوشهٔ اپ پیدا نشد: $APP_DIR"
[[ -f "$APP_DIR/manage.py" ]] || die "$APP_DIR پروژهٔ Django نیست"
[[ -f "$APP_DIR/.env" ]] || die "فایل .env نیست — از .env.example بساز و پر کن: $APP_DIR/.env"
command -v git >/dev/null || die "git نصب نیست"
if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  # تلاش برای پیدا کردن نسخهٔ دیگری از virtualenv ساخته‌شده توسط cPanel
  alt="$(ls -d "$HOME"/virtualenv/Kaveh185-Back/* 2>/dev/null | head -1 || true)"
  [[ -n "${alt:-}" && -x "$alt/bin/python" ]] && VENV_DIR="$alt" || die "virtualenv پیدا نشد: $VENV_DIR (با KAVEH185_VENV=... مشخص کن)"
fi
ok "پیش‌نیازها برقرارند"
info "اپ: $APP_DIR"
info "venv: $VENV_DIR ($("$VENV_DIR/bin/python" -V 2>&1))"
grep -qE '^DJANGO_SETTINGS_MODULE=config\.settings\.production' "$APP_DIR/.env" \
  || warn "DJANGO_SETTINGS_MODULE در .env برابر production نیست — بررسی کن"

# ══════════════════════════════════════════════════════════════════════════════
step "۱/۸ · گرفتن آخرین نسخه از گیت‌هاب"
# ══════════════════════════════════════════════════════════════════════════════
cd "$APP_DIR"
PREV_COMMIT="$(git rev-parse HEAD 2>/dev/null || echo '')"
info "کامیت فعلی: ${PREV_COMMIT:0:8}"

# ── ثبت «آخرین نسخهٔ سالمِ تأییدشده» ────────────────────────────────────────
# فقط کامیتی که یک استقرارِ موفق پشت سرش بوده ثبت می‌شود.
LAST_GOOD_FILE="$APP_DIR/.deploy-last-good"
cd "$APP_DIR"
_prev_good="$(cat "$LAST_GOOD_FILE" 2>/dev/null || echo '')"
_prev_good_ok=0
if [[ -n "$_prev_good" ]]; then
  if git cat-file -e "${_prev_good}^{commit}" 2>/dev/null; then _prev_good_ok=1; fi
fi
[[ $_prev_good_ok -eq 1 ]] && info "آخرین نسخهٔ سالمِ ثبت‌شده: ${_prev_good:0:8}"

if [[ $DO_PULL -eq 1 ]]; then
  if [[ -z "$(git status --porcelain 2>/dev/null || true)" ]]; then
    run git fetch --prune origin "$BRANCH"
    run git reset --hard "origin/$BRANCH"
  else
    warn "تغییرات محلی وجود دارد — به‌جای reset، stash + pull انجام می‌شود"
    run git stash push -u -m "auto-stash-$STAMP" || true
    run git fetch --prune origin "$BRANCH"
    run git reset --hard "origin/$BRANCH"
  fi
fi
NEW_COMMIT="$(git rev-parse HEAD)"
[[ "$PREV_COMMIT" == "$NEW_COMMIT" ]] && info "کد تغییری نکرده (همان کامیت)" || ok "به ${NEW_COMMIT:0:8} به‌روز شد"
info "پیام آخرین کامیت: $(git log -1 --pretty=%s | cut -c1-80)"

# ══════════════════════════════════════════════════════════════════════════════
step "۲/۸ · نسخهٔ پشتیبان پایگاه‌داده (قبل از migrate)"
# ══════════════════════════════════════════════════════════════════════════════
# اعتبارسنجی: فقط SELECT/مقادیر عددی؟ نه — اینجا از پارامترهای .env استفاده می‌کنیم
# تا هرگز اسم جدول/کاربر از ورودی کاربر نیاید (جلوگیری از تزریق).
set -a; . "$APP_DIR/.env"; set +a
DB_ENGINE_EFF="${DB_ENGINE:-django.db.backends.sqlite3}"
BACKUP_FILE=""
if [[ $DRY_RUN -eq 0 ]]; then
  if [[ "$DB_ENGINE_EFF" == *sqlite3* ]]; then
    sqlite_path="${DB_NAME:-$APP_DIR/db.sqlite3}"
    [[ "$sqlite_path" != /* ]] && sqlite_path="$APP_DIR/$sqlite_path"
    if [[ -f "$sqlite_path" ]]; then
      BACKUP_FILE="$BACKUP_DIR/db-$STAMP.sqlite3"
      cp "$sqlite_path" "$BACKUP_FILE" && ok "پشتیبان SQLite: $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"
    fi
  elif [[ "$DB_ENGINE_EFF" == *mysql* ]]; then
    BACKUP_FILE="$BACKUP_DIR/db-$STAMP.sql.gz"
    if command -v mysqldump >/dev/null; then
      # رمز عبور از فایل موقت با مجوز ۶۰۰ عبور داده می‌شود تا در ps دیده نشود
      cnf="$(mktemp)"; chmod 600 "$cnf"
      printf '[client]\nuser=%s\npassword=%s\nhost=%s\n' "${DB_USER:-}" "${DB_PASSWORD:-}" "${DB_HOST:-localhost}" > "$cnf"
      mysqldump --defaults-extra-file="$cnf" --single-transaction --quick \
        "${DB_NAME:-}" 2>/dev/null | gzip -9 > "$BACKUP_FILE"
      rm -f "$cnf"
      ok "پشتیبان MySQL: $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"
    else
      warn "mysqldump روی این هاست نیست — پشتیبان با ابزار cPanel (phpMyAdmin → Export) بگیر"
      BACKUP_FILE=""
    fi
  fi
else
  info "[dry-run] پشتیبان‌گیری رد شد"
fi

# ══════════════════════════════════════════════════════════════════════════════
step "۳/۸ · نصب وابستگی‌ها"
# ══════════════════════════════════════════════════════════════════════════════
REQ_HASH_FILE="$APP_DIR/.deploy-requirements-hash"
NEW_HASH="$(sha256sum "$APP_DIR/requirements.txt" | cut -d' ' -f1)"
if [[ -f "$REQ_HASH_FILE" ]] && [[ "$(cat "$REQ_HASH_FILE")" == "$NEW_HASH" ]]; then
  info "requirements.txt تغییری نکرده — نصب رد شد (سریع)"
else
  info "نصب وابستگی‌ها از requirements.txt ..."
  run "$VENV_DIR/bin/pip" install --upgrade pip --quiet
  run "$VENV_DIR/bin/pip" install -r "$APP_DIR/requirements.txt" --quiet
  [[ $DRY_RUN -eq 0 ]] && echo "$NEW_HASH" > "$REQ_HASH_FILE"
  ok "وابستگی‌ها نصب شدند"
fi

# ══════════════════════════════════════════════════════════════════════════════
step "۴/۸ · بررسی پیکربندی پروداکشن (depolite)"
# ══════════════════════════════════════════════════════════════════════════════
set -a; . "$APP_DIR/.env"; set +a
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings.production}"

check_out="$( py manage.py check --deploy --fail-level WARNING 2>&1 || true )"
if [[ "$check_out" == *"issues"* || "$check_out" == *"WARNINGS"* ]]; then
  if [[ $FORCE -eq 1 ]]; then
    warn "check --deploy هشدار داد ولی --force داده شده؛ ادامه می‌دهیم"
    printf '%s\n' "$check_out" | sed 's/^/    /'
  else
    printf '%s\n' "$check_out" | sed 's/^/    /'
    die "پیکربندی پروداکشن هشدار دارد. رفع کن یا --force بده."
  fi
else
  ok "پیکربندی پروداکشن سالم است"
fi

# ══════════════════════════════════════════════════════════════════════════════
step "۵/۸ · مهاجرت پایگاه‌داده"
# ══════════════════════════════════════════════════════════════════════════════
info "مهاجرت‌های در انتظار:"
py manage.py showmigrations --plan 2>/dev/null | grep -c '^\[ \]' | sed 's/^/    تعداد: /' || true
STAGE="migrate"
py manage.py migrate --noinput
ok "مهاجرت انجام شد"

# بررسی drift: مدل بدون مهاجرت نباید وجود داشته باشد
drift="$( py manage.py makemigrations --check --dry-run 2>&1 || true )"
if [[ "$drift" == *"No changes detected"* ]]; then ok "مدل‌ها و مهاجرت‌ها همگام‌اند"
else warn "drift مدل/مهاجرت: $drift"; fi

# ══════════════════════════════════════════════════════════════════════════════
step "۶/۸ · فایل‌های ایستا و دانه‌ریزی"
# ══════════════════════════════════════════════════════════════════════════════
STAGE="collectstatic"
py manage.py collectstatic --noinput --clear
ok "فایل‌های ایستا جمع‌آوری شدند"

if [[ $DO_SEED -eq 1 ]]; then
  STAGE="seed"
  # `seed_kaveh185` افزایشی (additive) است و کلیدهای موجود را دست نمی‌زند،
  # پس اجرای مکرر آن بی‌خطر است؛ ولی برای شفافیت، پیش از اجرا هشدارِ
  # «الگو را بازنویسی نکن» به .env بی‌خطر است.
  if [[ $WITH_DEMO -eq 1 ]]; then
    warn "دادهٔ دمو در حال بارگذاری — این برای پروداکشنِ واقعی نیست!"
    py manage.py seed_kaveh185 --with-demo-data
  else
    py manage.py seed_kaveh185
  fi
  ok "دانه‌ریزی انجام شد (۱۷ مسجد + تنظیمات + بانک سوال)"
else
  info "دانه‌ریزی رد شد (برای بار اول: --seed)"
fi

if [[ -n "$GRANT_ADMIN" ]]; then
  STAGE="grant-admin"
  IFS='|' read -r A_PHONE A_NID A_PASS <<< "$GRANT_ADMIN"
  [[ -n "${A_PHONE:-}" && -n "${A_NID:-}" && -n "${A_PASS:-}" ]] || die "--grant-admin باید به شکل «09xxxxxxxxx|کدملی|رمز» باشد"
  py manage.py grant_admin --phone "$A_PHONE" --national-id "$A_NID" --password "$A_PASS"
  ok "ادمین ساخته/به‌روزرسانی شد: $A_PHONE"
fi

# ══════════════════════════════════════════════════════════════════════════════
step "۷/۸ · راه‌اندازی مجدد Passenger"
# ══════════════════════════════════════════════════════════════════════════════
STAGE="restart"
call_passenger_restart
ok "درخواست ری‌استارت ثبت شد (touch tmp/restart.txt)"

# ══════════════════════════════════════════════════════════════════════════════
step "۸/۸ · بررسی سلامت (health-check)"
# ══════════════════════════════════════════════════════════════════════════════
if [[ $DRY_RUN -eq 1 ]]; then
  info "[dry-run] health-check رد شد"; HEALTHY=1
else
  HEALTHY=0
  for attempt in 1 2 3 4 5 6; do
    info "تلاش $attempt از ۶ برای $HEALTH_URL ..."
    sleep $(( attempt * 2 ))
    # ۱) تلاش مستقیم
    body="$(curl -fsS -m 10 "$HEALTH_URL" 2>/dev/null || true)"
    if [[ "$body" == *'"healthy"'* ]]; then HEALTHY=1; break; fi
    # ۲) اگر SECURE_SSL_REDIRECT فعال است، درخواست پشت پراکسی با هدر X-Forwarded-Proto
    code="$(curl -s -o /dev/null -m 10 -w '%{http_code}' "$HEALTH_URL" 2>/dev/null || true)"
    if [[ "$code" == "301" || "$code" == "302" || "$code" == "308" ]]; then
      info "  ریدایرکت HTTPS (HTTP $code) — بررسی پشت پراکسی ..."
      body="$(curl -fsS -m 10 -H 'X-Forwarded-Proto: https' "$HEALTH_URL" 2>/dev/null || true)"
      if [[ "$body" == *'"healthy"'* ]]; then HEALTHY=1; break; fi
    fi
  done
  if [[ $HEALTHY -eq 1 ]]; then
    ok "سرویس سالم است: $body"
  else
    warn "health-check جواب نداد: $HEALTH_URL"
    warn "بررسی‌های دستی: لاگ خطای cPanel → Setup Python App → stderr.log"
    warn "اگر Passenger هنوز بالا نیامده، ۳۰ ثانیه صبر کن و دوباره: curl -s $HEALTH_URL"
    rollback_to_last_good
    die "استقرار ناتمام (سرویس سالم نشد). لاگ: $LOG_FILE"
  fi
fi

# ══════════════════════════════════════════════════════════════════════════════
step "پاک‌سازی پشتیبان‌های قدیمی (نگه‌داری: $KEEP_BACKUPS مورد آخر)"
# ══════════════════════════════════════════════════════════════════════════════
if [[ $DRY_RUN -eq 0 ]]; then
  ls -1t "$BACKUP_DIR"/db-* 2>/dev/null | tail -n +$(( KEEP_BACKUPS + 1 )) | while read -r old; do
    rm -f "$old" && info "حذف شد: $(basename "$old")"
  done || true
fi

# ثبت این کامیت به‌عنوان «آخرین نسخهٔ سالم»
if [[ $DRY_RUN -eq 0 ]]; then
  echo "$NEW_COMMIT" > "$LAST_GOOD_FILE"
  info "ثبت شد: ${NEW_COMMIT:0:8} = آخرین نسخهٔ سالم"
fi

printf '\n%s\n' "${C_BOLD}${C_GREEN}═══════════════════════════════════════════════════════${C_RESET}"
printf '%s\n'   "${C_BOLD}${C_GREEN}  ✔ استقرار بک‌اند کاوه ۱۸۵ با موفقیت انجام شد${C_RESET}"
printf '%s\n\n' "${C_BOLD}${C_GREEN}═══════════════════════════════════════════════════════${C_RESET}"
info "کامیت: ${NEW_COMMIT:0:8} · لاگ: $LOG_FILE"
info "Swagger:  https://api.kaveh185.ir/api/v1/docs/"
info "ReDoc:    https://api.kaveh185.ir/api/v1/redoc/"
info "Health:   $HEALTH_URL"
