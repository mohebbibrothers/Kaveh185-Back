#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
#  کاوه ۱۸۵ — نشاندن اپلیکیشن پایتون روی دامنهٔ اصلی + نصب فرانت
#
#  وضعیت فعلی هاست: اپ Passenger فقط روی `api.kaveh185.ir` سوار است، پس
#  `kaveh185.ir` دایرکتوری خالی سرو می‌کند. این اسکریپت همان اپ موجود را
#  برای دامنهٔ اصلی هم فعال می‌کند — بی‌جابه‌جایی فایل و بی‌دست‌زدن به API.
#
#  اجرا (روی هاست، هیچ مفسری جز bash لازم نیست):
#      bash ~/Kaveh185-Back/deploy/host/serve-main-domain.sh --check
#      bash ~/Kaveh185-Back/deploy/host/serve-main-domain.sh --from-dir ~/frontend-out
#      bash ~/Kaveh185-Back/deploy/host/serve-main-domain.sh --undo
# ══════════════════════════════════════════════════════════════════════════════
set -Eeuo pipefail

readonly R=$'\033[0m' B=$'\033[1m' D=$'\033[2m'
readonly G=$'\033[32m' Y=$'\033[33m' RD=$'\033[31m' BL=$'\033[34m' CY=$'\033[36m'

APP_DIR="${KAVEH185_APP_DIR:-$HOME/Kaveh185-Back}"
MAIN="${KAVEH185_MAIN_DOMAIN:-kaveh185.ir}"
API="api.$MAIN"
DOCROOT="${KAVEH185_DOCROOT:-$HOME/public_html}"
HTACCESS="$DOCROOT/.htaccess"

MODE="install"; FRONT_DIR=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --check)    MODE="check" ;;
    --undo)     MODE="undo" ;;
    --from-dir) FRONT_DIR="${2:-}"; shift ;;
    -h|--help)  sed -n '2,18p' "$0"; exit 0 ;;
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
http_code(){ curl -s -o /dev/null -m 12 -w '%{http_code}' "$1" 2>/dev/null || echo 000; }

printf '%s%s%s\n' "$B$CY" "══════ کاوه ۱۸۵ — دامنهٔ اصلی + فرانت ══════" "$R"
dim "کاربر: $(whoami) · میزبان: $(hostname)"
dim "ریشهٔ سند: $DOCROOT"
dim "اپلیکیشن: $APP_DIR"

[[ -f "$APP_DIR/manage.py" ]] || die "ریشهٔ اپ پیدا نشد: $APP_DIR"

# ══════════════════════════════════════════════════════════════════════════════
#  --undo
# ══════════════════════════════════════════════════════════════════════════════
if [[ "$MODE" == "undo" ]]; then
  step "بازگشت"
  if [[ -f "$HTACCESS" ]]; then
    mv -f "$HTACCESS" "$HTACCESS.removed.$(date +%s)"
    ok ".htaccess کنار گذاشته شد — دامنهٔ اصلی به حالت قبل برگشت"
  else
    dim "فایل .htaccess نبود؛ چیزی برای بازگشت نیست"
  fi
  dim "API روی $API دست‌نخورده است."
  exit 0
fi

# ══════════════════════════════════════════════════════════════════════════════
#  --check : تشخیص وضعیت، بی‌هیچ تغییری
# ══════════════════════════════════════════════════════════════════════════════
if [[ "$MODE" == "check" ]]; then
  step "وضعیت فعلی"
  printf '  %-34s %s\n' "API ($API/health/live)" "$(http_code "https://$API/api/v1/health/live/")"
  printf '  %-34s %s\n' "اصلی ($MAIN/)" "$(http_code "https://$MAIN/")"

  step "ریشهٔ سند"
  if [[ -d "$DOCROOT" ]]; then
    dim "محتوا: $(ls -A "$DOCROOT" 2>/dev/null | tr '\n' ' ' | cut -c1-120)"
  else
    warn "$DOCROOT وجود ندارد"
  fi

  step "تنظیم Passenger همین اپ (آنچه cPanel نوشته)"
  for f in "$APP_DIR/.htaccess" "$HOME/$API/.htaccess" "$DOCROOT/.htaccess"; do
    if [[ -f "$f" ]]; then
      ok "$f"
      grep -iE 'Passenger(AppRoot|BaseURI|AppStartFile|AppEnv|Enabled|Python|FriendlyError)' "$f" 2>/dev/null \
        | sed 's/^/     /' || true
    fi
  done

  step "پوشه‌های واقعی دامنه‌ها"
  for d in "$HOME/$API" "$HOME/$MAIN" "$DOCROOT/$API"; do
    [[ -e "$d" ]] && dim "$d → $(readlink -f "$d" 2>/dev/null || echo '?')"
  done

  step "فرانت نصب‌شده؟"
  if [[ -f "$APP_DIR/frontend/index.html" ]]; then
    ok "نصب است · شناسه: $(cat "$APP_DIR/frontend/BUILD_ID" 2>/dev/null || echo '?')"
  else
    warn "نصب نیست — گام ۲ همین اسکریپت با --from-dir آن را نصب می‌کند"
  fi
  exit 0
fi

# ══════════════════════════════════════════════════════════════════════════════
#  نصب
# ══════════════════════════════════════════════════════════════════════════════
step "۱/۴ بازرسی پیش از تغییر"
[[ -d "$DOCROOT" ]] || die "ریشهٔ سند نیست: $DOCROOT"

# از تنظیم واقعی خودِ اپ یاد بگیریم، نه از حدس
APP_START="passenger_wsgi.py"; APP_ENTRY="application"; PYVER=""
if [[ -f "$APP_DIR/.htaccess" ]]; then
  APP_START="$(grep -i 'PassengerAppStartFile' "$APP_DIR/.htaccess" 2>/dev/null | awk -F': *' '{print $2}' | tr -d ' ' | head -1 || true)"
  APP_ENTRY="$(grep -i 'PassengerAppStartupFile\|PassengerAppEntry' "$APP_DIR/.htaccess" 2>/dev/null | awk -F': *' '{print $2}' | tr -d ' ' | head -1 || true)"
  PYVER="$(grep -i 'PassengerPython\|PassengerBaseURI' "$APP_DIR/.htaccess" 2>/dev/null | head -2 | tr '\n' ' ' || true)"
fi
[[ -n "$APP_START" ]] || APP_START="passenger_wsgi.py"
[[ -n "$APP_ENTRY" ]] || APP_ENTRY="application"

VENV_PY="$(ls -1 "$HOME"/virtualenv/*/*/bin/python 2>/dev/null | head -1 || true)"
dim "نقطهٔ شروع: $APP_START · entry: $APP_ENTRY"
[[ -n "$VENV_PY" ]] && dim "مفسر: $VENV_PY"

if [[ -f "$HTACCESS" ]]; then
  if grep -qi 'kaveh185' "$HTACCESS"; then
    ok "‎.htaccess از قبل برای این اپ تنظیم شده — بازنویسی نمی‌شود"
    SKIP_HT=1
  else
    cp -a "$HTACCESS" "$HTACCESS.bak.$(date +%s)"
    warn "‎.htaccess موجود بود (پشتیبان گرفته شد و جایگزین می‌شود)"
    SKIP_HT=0
  fi
else
  SKIP_HT=0
fi

step "۲/۴ نصب فرانت"
if [[ -n "$FRONT_DIR" ]]; then
  [[ -f "$FRONT_DIR/index.html" ]] || die "پوشهٔ داده‌شده index.html ندارد: $FRONT_DIR"
  [[ -f "$FRONT_DIR/BUILD_ID" ]] || die "BUILD_ID ندارد — با `pnpm pack:front` ساخته نشده"
  TARGET="$APP_DIR/frontend"
  if [[ -L "$TARGET" || -d "$TARGET" ]]; then mv -f "$TARGET" "$TARGET.bak.$(date +%s)"; fi
  cp -a "$FRONT_DIR" "$TARGET"
  find "$TARGET" -type f -exec chmod 644 {} +
  find "$TARGET" -type d -exec chmod 755 {} +
  ok "فرانت نصب شد · شناسه: $(cat "$TARGET/BUILD_ID")"
else
  if [[ -f "$APP_DIR/frontend/index.html" ]]; then
    ok "فرانت از قبل نصب است · شناسه: $(cat "$APP_DIR/frontend/BUILD_ID" 2>/dev/null || echo '?')"
  else
    warn "فرانت نصب نیست (--from-dir بده یا front-deploy.sh را اجرا کن)"
  fi
fi

step "۳/۴ اتصال دامنهٔ اصلی"
if (( SKIP_HT )); then
  dim "رد شد — .htaccess از قبل درست است"
else
  cat > "$HTACCESS" <<HT
# ── کاوه ۱۸۵ — سرو سایت از اپلیکیشن پایتون روی دامنهٔ اصلی ──────────────
# ساخته‌شده توسط deploy/host/serve-main-domain.sh در $(date '+%Y-%m-%d %H:%M')
# بازگشت: bash ~/Kaveh185-Back/deploy/host/serve-main-domain.sh --undo
#
# ⚠️ هیچ فایلی جابه‌جا نشده؛ این فایل فقط به Apache می‌گوید درخواست‌های
#    همین دامنه را به همان اپلیکیشنی بدهد که روی $API سرو می‌شود.

PassengerAppRoot "$APP_DIR"
PassengerBaseURI "/"
PassengerAppType wsgi
PassengerStartupFile $APP_START
PassengerAppEnv production
PassengerEnabled on
HT
  [[ -n "$VENV_PY" ]] && printf 'PassengerPython %s\n' "$VENV_PY" >> "$HTACCESS"
  chmod 644 "$HTACCESS"
  ok ".htaccess نوشته شد"
fi

# restart.txt تا Passenger نسخهٔ تازه را بارگذاری کند
mkdir -p "$APP_DIR/tmp"
touch "$APP_DIR/tmp/restart.txt"
dim "restart.txt لمس شد"

step "۴/۴ راستی‌آزمایی"
sleep 4
fail=0
for pair in "$API/api/v1/health/ready/|API" "$MAIN/|صفحهٔ اول" "$MAIN/api/v1/health/live/|API از دامنهٔ اصلی"; do
  url="${pair%|*}"; label="${pair#*|}"
  code="$(http_code "https://$url")"
  if [[ "$code" == "200" ]]; then ok "$label → 200"
  else warn "$label → $code"; fail=1; fi
done

served="$(curl -fsS -m 12 -o /dev/null -D - "https://$MAIN/" 2>/dev/null | tr -d '\r' \
  | awk -F': ' 'tolower($1)=="x-frontend-build"{print $2; exit}' || true)"
[[ -n "$served" ]] && ok "نسخهٔ سروشده: $served"

if (( fail )); then
  printf '\n'
  warn "اگر دامنهٔ اصلی هنوز ۲۰۰ نمی‌دهد:"
  warn "  • cPanel → Domains: مطمئن شو $MAIN به همین حساب و $DOCROOT اشاره می‌کند"
  warn "  • cPanel → Setup Python App: همان اپ را Edit کن و Application URL را"
  warn "    $MAIN بگذار (اپ روی چند دامنه هم‌زمان سرو می‌شود)، Save + Restart"
  warn "  • گزارش خطا: ~/logs/passenger.log  (یا فایل Passenger log file در همان صفحه)"
  warn "بازگشت کامل: bash $0 --undo"
  exit 1
fi

printf '\n%s%s%s\n' "$B$G" "✔ دامنهٔ اصلی وصل شد" "$R"
dim "سایت: https://$MAIN/"
dim "API : https://$API/"
dim "بازگشت: bash $0 --undo"
