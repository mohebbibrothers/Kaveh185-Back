#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
#  کاوه ۱۸۵ — گزارش وضعیت سایت، در یک فرمان و یک خروجی
#
#  این اسکریپت فقط **می‌خواند**؛ هیچ فایلی را تغییر نمی‌دهد. برای وقتی است
#  که می‌خواهیم بفهمیم نصب تازه واقعاً درست نشسته یا نه، بدون رفت‌وبرگشت.
#
#      bash ~/Kaveh185-Back/deploy/inspect-host.sh
#      bash inspect-host.sh --json        # خروجی ماشین‌خوان
#
#  هیچ مفسری جز bash و curl لازم نیست.
# ══════════════════════════════════════════════════════════════════════════════
set -uo pipefail

APP_DIR="${KAVEH185_APP_DIR:-$HOME/Kaveh185-Back}"
SITE="${KAVEH185_SITE_URL:-https://kaveh185.ir}"
API="${KAVEH185_API_URL:-https://api.kaveh185.ir}"
JSON=0
[[ "${1:-}" == "--json" ]] && JSON=1

readonly R=$'\033[0m' B=$'\033[1m' D=$'\033[2m' G=$'\033[32m' Y=$'\033[33m' RD=$'\033[31m'
hdr(){ (( JSON )) || printf '\n%s▸ %s%s\n' "$B$D" "$*" "$R"; }
ok(){  (( JSON )) || printf '%s✔%s %s\n' "$G" "$R" "$*"; }
bad(){ (( JSON )) || printf '%s✖%s %s\n' "$RD" "$R" "$*"; }
dim(){ (( JSON )) || printf '%s  %s%s\n' "$D" "$*" "$R"; }

code(){ local c; c="$(curl -s -o /dev/null -m 15 -w '%{http_code}' "$1" 2>/dev/null)"; printf '%s' "${c:-000}"; }
hdrval(){ curl -s -o /dev/null -m 15 -D - "$1" 2>/dev/null | tr -d '\r' \
  | awk -F': ' -v k="$2" 'tolower($1)==tolower(k){print $2; exit}'; }

(( JSON )) && printf '{\n' || printf '%sکاوه ۱۸۵ — وضعیت %s%s\n' "$B" "$(date '+%Y-%m-%d %H:%M')" "$R"

# ── ۱) آنچه از بیرون دیده می‌شود ─────────────────────────────────────────
hdr "۱) سرو از بیرون"
root_code="$(code "$SITE/")"
root_type="$(hdrval "$SITE/" content-type)"
build="$(hdrval "$SITE/" x-frontend-build)"
csp="$(hdrval "$SITE/" content-security-policy)"
api_code="$(code "$API/api/v1/health/ready/")"

if [[ "$root_code" == "200" && "$root_type" == text/html* ]]; then
  ok "/ → 200 · $root_type"
else
  bad "/ → $root_code · ${root_type:-?}  (باید 200 و text/html باشد)"
fi
if [[ -n "$build" ]]; then ok "نسخهٔ سروشده: $build"; else bad "هدر X-Frontend-Build نیست"; fi
if [[ -n "$csp" ]]; then ok "CSP دارد (${#csp} کاراکتر)"; else bad "CSP نیست"; fi
[[ "$api_code" == "200" ]] && ok "API سالم → 200" || bad "API → $api_code"

hdr "۲) صفحهٔ واقعی چه می‌گوید"
home="$(curl -fsS -m 20 "$SITE/?probe=$(date +%s)" 2>/dev/null || true)"
if [[ -z "$home" ]]; then
  bad "صفحه خوانده نشد"
else
  # ⚠️ مهم: پوستهٔ خالی خودش در HTML سریالایز می‌شود (props کامپوننت
  # کلاینت برای hydration). آن بی‌خطر است. چیزی که «دادهٔ پخته» را لو
  # می‌دهد، **مقدار غیرخالی** است: تاریخ واقعی، فهرست مساجد، یا عددِ
  # مشارکت بزرگ‌تر از صفر. همان شکلی که باگ منتشرشده داشت.
  home_flat="$(printf '%s' "$home" | tr -d '\\')"

  if printf '%s' "$home_flat" | grep -qE '"starts_at"[[:space:]]*:[[:space:]]*"[0-9]'; then
    bad "HTML تاریخ واقعی آزمون را پخته دارد"
  else
    ok "هیچ تاریخ واقعی در HTML پخته نشده"
  fi
  if printf '%s' "$home_flat" | grep -qE '"total_completed_participants"[[:space:]]*:[[:space:]]*[1-9]'; then
    bad "HTML عدد مشارکت را پخته دارد"
  else
    ok "هیچ عدد مشارکتی در HTML پخته نشده"
  fi
  if printf '%s' "$home_flat" | grep -qE 'MSQ-[0-9]{2}'; then
    bad "فهرست مساجد در HTML پخته شده"
  else
    ok "فهرست مساجد در HTML نیست (زنده می‌آید)"
  fi
  if printf '%s' "$home_flat" | grep -qE '"total_mosques"[[:space:]]*:[[:space:]]*[1-9]'; then
    bad "تعداد مساجد در HTML پخته شده"
  else
    ok "تعداد مساجد پخته نشده"
  fi

  printf '%s' "$home" | grep -q 'آزمون فعال است' \
    && bad "برچسب «آزمون فعال است» در HTML است (باید زنده باشد)" \
    || ok "برچسب وضعیت زنده می‌آید"
  printf '%s' "$home" | grep -q 'در حال دریافت' \
    && ok "پوستهٔ خالی درست نشان داده می‌شود" || dim "متن «در حال دریافت» نبود — یا داده زنده پخته شده یا متن عوض شده"
fi

hdr "۳) API زنده چه می‌گوید"
bs="$(curl -fsS -m 20 "$SITE/api/v1/core/bootstrap/" 2>/dev/null || true)"
if [[ -z "$bs" ]]; then
  bad "bootstrap خوانده نشد"
else
  printf '%s' "$bs" | grep -o '"window_state":"[a-z]*"' | head -1 | sed 's/^/  /'
  printf '%s' "$bs" | grep -o '"starts_at_jalali":"[^"]*"' | head -1 | sed 's/^/  /'
  printf '%s' "$bs" | grep -o '"total_completed_participants":[0-9]*' | head -1 | sed 's/^/  /'
fi

hdr "۴) نصب روی دیسک"
fe="$APP_DIR/frontend"
fe_real="$(readlink -f "$fe" 2>/dev/null || printf '%s' "$fe")"
if [[ -f "$fe_real/index.html" ]]; then
  ok "فرانت نصب است · شناسه $(cat "$fe/BUILD_ID" 2>/dev/null || echo '?')"
  if [[ -f "$fe/FILES.sha256" ]]; then
    if ( cd "$fe" && sha256sum -c FILES.sha256 --quiet >/dev/null 2>&1 ); then
      ok "هش $(wc -l < "$fe/FILES.sha256" | tr -d ' ') فایل سالم"
    else
      bad "هش فایل‌ها نمی‌خواند — نصب ناقص"
    fi
  fi
  [[ -L "$APP_DIR/frontend" ]] && dim "پیوند → $(readlink "$APP_DIR/frontend")"
else
  bad "فرانت نصب نیست ($fe)"
fi

hdr "۵) کد سرو و .env"
if grep -q '_with_www' "$APP_DIR/config/settings/base.py" 2>/dev/null; then
  ok "کد از www پشتیبانی می‌کند"
else
  bad "کد قدیمی است"
fi
if grep -q '_FRONTEND_FALLBACKS' "$APP_DIR/apps/core/frontend.py" 2>/dev/null; then
  ok "جانشین مسیر فرانت هست"
else
  bad "frontend.py قدیمی است"
fi
if [[ -f "$APP_DIR/.env" ]]; then
  # اگر کلیدی دو بار آمده باشد، آخرین مقدار برنده است (رفتار decouple).
  # نمایش هر دو خط، خواننده را گمراه می‌کند؛ پس فقط خط مؤثر را نشان می‌دهیم.
  for key in FRONTEND_DIST DJANGO_ALLOWED_HOSTS; do
    line="$(grep -E "^${key}=" "$APP_DIR/.env" | tail -1 || true)"
    [[ -n "$line" ]] && printf '%s  %s%s\n' "$D" "$line" "$R"
  done
  # تکرار یک کلید فقط وقتی مشکوک است که مقدارها متفاوت باشند؛ دو خط
  # یکسان بی‌خطر است و هشدار دادن برایش نویز است.
  for key in FRONTEND_DIST DJANGO_ALLOWED_HOSTS; do
    n="$(grep -E "^${key}=" "$APP_DIR/.env" | sort -u | wc -l | tr -d ' ')"
    if (( n > 1 )); then
      bad "$key در .env چند مقدار متفاوت دارد — فقط آخرین اعمال می‌شود"
    fi
  done
fi

hdr "۶) مسیرهای سایت"
for p in / /rules/ /register/ /receipt/ /mosques/ /login/ /nope-xyz/; do
  c="$(code "$SITE$p")"
  t="$(hdrval "$SITE$p" content-type)"
  printf '  %-14s %s  %s\n' "$p" "$c" "${t%%;*}"
done

(( JSON )) && printf '}\n' || printf '\n%sپایان گزارش%s\n' "$B" "$R"
