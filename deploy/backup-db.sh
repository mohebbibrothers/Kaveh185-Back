#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
#  کاوه ۱۸۵ — پشتیبانِ دیتابیس، درست و قابلِ اجرا وسطِ آزمون
#
#      bash ~/Kaveh185-Back/deploy/backup-db.sh
#
#  چرا اسکریپت و نه دستورِ دستی؟ سه دلیل، هر سه از یک تجربهٔ واقعی:
#
#  ۱) **نامِ ابزار**: روی MariaDB 11، `mysqldump` یک «برنامهٔ منسوخ» است و پیام
#     می‌دهد «از mariadb-dump استفاده کنید». کار می‌کند، ولی در لاگِ روزِ آزمون
#     یک هشدارِ قرمز می‌سازد که آدم را نگران می‌کند. این‌جا ابزار درست انتخاب
#     می‌شود.
#  ۲) **بدونِ قفل**: `--single-transaction` یعنی پشتیبان‌گیری جدول‌ها را قفل
#     نمی‌کند ⇒ می‌شود وسطِ آزمون اجرا کرد؛ سایت نمی‌خوابد.
#  ۳) **راستی‌آزمایی**: پشتیبانی که باز نمی‌شود، پشتیبان نیست. این اسکریپت
#     بعد از ساخت، حجم و وجودِ سرآیندِ gzip و تعدادِ `CREATE TABLE` را می‌سنجد.
#
#  خروجی: ~/k185-backups/db-YYYYmmdd-HHMM.sql.gz  با مجوز ۶۰۰
# ══════════════════════════════════════════════════════════════════════════════
set -Eeuo pipefail

APP_DIR="${KAVEH185_APP_DIR:-$HOME/Kaveh185-Back}"
BACKUP_DIR="${K185_BACKUP_DIR:-$HOME/k185-backups}"
KEEP="${K185_BACKUP_KEEP:-14}"

readonly R=$'\033[0m' G=$'\033[32m' Y=$'\033[33m' RD=$'\033[31m' B=$'\033[1m' BL=$'\033[34m'
step(){ printf '\n%s▸ %s%s\n' "$B$BL" "$*" "$R"; }
ok(){   printf '%s✔%s %s\n' "$G" "$R" "$*"; }
warn(){ printf '%s▲%s %s\n' "$Y" "$R" "$*"; }
die(){  printf '%s✖%s %s\n' "$RD" "$R" "$*" >&2; exit 1; }

[[ -f "$APP_DIR/.env" ]] || die ".env پیدا نشد: $APP_DIR/.env"
set -a
# shellcheck disable=SC1091
. "$APP_DIR/.env"
set +a

ENGINE="${DB_ENGINE:-django.db.backends.mysql}"
NAME="${DB_NAME:-}"; USER_="${DB_USER:-}"; PASS="${DB_PASSWORD:-}"
HOST_="${DB_HOST:-localhost}"; PORT_="${DB_PORT:-}"

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
STAMP="$(date +%Y%m%d-%H%M)"

# ── SQLite ───────────────────────────────────────────────────────────────────
if [[ "$ENGINE" == *sqlite* ]]; then
  DB_PATH="${NAME:-$APP_DIR/db.sqlite3}"
  [[ "$DB_PATH" != /* ]] && DB_PATH="$APP_DIR/$DB_PATH"
  [[ -f "$DB_PATH" ]] || die "فایلِ SQLite پیدا نشد: $DB_PATH"

  OUT="$BACKUP_DIR/db-$STAMP.sqlite3"
  step "پشتیبانِ SQLite"
  if command -v sqlite3 >/dev/null 2>&1; then
    # `.backup` فایلِ WAL را هم به‌درستی ادغام می‌کند — `cp` نمی‌کند.
    sqlite3 "$DB_PATH" ".backup '$OUT'"
    ok "با sqlite3 .backup (WAL ادغام شد)"
  else
    warn "sqlite3 نصب نیست — کپیِ خام. اگر آزمون در جریان است، این کار ممکن"
    warn "است نسخهٔ نیمه‌نوشته بدهد. بین دو بازه اجرا کنید."
    cp "$DB_PATH" "$OUT"
    [[ -f "$DB_PATH-wal" ]] && cp "$DB_PATH-wal" "$OUT-wal"
  fi
  chmod 600 "$OUT"
  ok "$OUT ($(du -h "$OUT" | cut -f1))"
  exit 0
fi

# ── MySQL / MariaDB ──────────────────────────────────────────────────────────
[[ -n "$NAME" && -n "$USER_" ]] || die "DB_NAME و DB_USER در .env نیستند"

# انتخابِ ابزارِ درست: روی MariaDB، `mariadb-dump` نسخهٔ رسمی است.
DUMP=""
if command -v mariadb-dump >/dev/null 2>&1; then
  DUMP="mariadb-dump"
elif command -v mysqldump >/dev/null 2>&1; then
  DUMP="mysqldump"
  warn "mariadb-dump نیست؛ با mysqldump (روی MariaDB منسوخ اعلام می‌شود،"
  warn "ولی کار می‌کند). برای حذفِ هشدار: sudo dnf install mariadb-client"
else
  die "هیچ ابزارِ dump پیدا نشد (mariadb-dump یا mysqldump)"
fi

OUT="$BACKUP_DIR/db-$STAMP.sql.gz"
step "پشتیبانِ $DUMP از دیتابیس «$NAME»"

# رمز از فایلِ موقت با مجوز ۶۰۰ عبور می‌کند تا در `ps` دیده نشود.
CNF="$(mktemp)"; chmod 600 "$CNF"
trap 'rm -f "$CNF"' EXIT
printf '[client]\nuser=%s\npassword=%s\nhost=%s\n' "$USER_" "$PASS" "$HOST_" > "$CNF"
[[ -n "$PORT_" ]] && printf 'port=%s\n' "$PORT_" >> "$CNF"

ARGS=(--defaults-extra-file="$CNF" --single-transaction --quick
      --default-character-set=utf8mb4 --routines --triggers)
[[ "$DUMP" == "mysqldump" ]] && ARGS+=(--no-tablespaces)

START=$SECONDS
"$DUMP" "${ARGS[@]}" "$NAME" | gzip -9 > "$OUT"
ELAPSED=$((SECONDS - START))
chmod 600 "$OUT"

# ── راستی‌آزمایی: پشتیبانی که باز نمی‌شود، پشتیبان نیست ─────────────────────
step "راستی‌آزمایی"
SIZE=$(stat -c %s "$OUT" 2>/dev/null || echo 0)
(( SIZE > 1024 )) || die "فایل خیلی کوچک است ($SIZE بایت) — پشتیبان معتبر نیست"

gzip -t "$OUT" || die "فایلِ gzip خراب است"
TABLES=$(gzip -dc "$OUT" | grep -c '^CREATE TABLE' || true)
(( TABLES > 0 )) || die "هیچ CREATE TABLE در فایل نیست — پشتیبان خالی است"

ok "حجم: $(du -h "$OUT" | cut -f1) · جدول‌ها: $TABLES · زمان: ${ELAPSED}s"
ok "مسیر: $OUT"
printf '  دستورِ بازگردانی (روی دیتابیسِ خالی، نه روی همین):\n'
printf '    gzip -dc %s | mysql -u USER -p EMPTY_DB\n' "$(basename "$OUT")"

# ── هرسِ نسخه‌های قدیمی ─────────────────────────────────────────────────────
mapfile -t OLD < <(ls -1t "$BACKUP_DIR"/db-*.sql.gz 2>/dev/null | tail -n +$((KEEP + 1)) || true)
if (( ${#OLD[@]} )); then
  step "هرس (نگه‌داشتنِ $KEEP نسخهٔ آخر)"
  for f in "${OLD[@]}"; do rm -f "$f"; ok "حذف: $(basename "$f")"; done
fi

warn "این فایل کد ملی و شمارهٔ همهٔ شرکت‌کننده‌ها را دارد:"
warn "  مجوز ۶۰۰ است و باید بیرونِ public_html بماند."
