#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
#  کاوه ۱۸۵ — «یک دستور، همهٔ بررسی‌ها» روی هاست
#
#      bash ~/Kaveh185-Back/deploy/check.sh
#
#  چرا این اسکریپت؟ چون روی این هاست **`python` روی PATH نیست** (فقط مفسرِ
#  داخلِ virtualenv هست) و مسیرِ آن هم همیشه یکی نیست. نتیجه‌اش این بود که
#  دستورِ عیب‌یابی خودش با «command not found» شکست می‌خورد — یعنی ابزارِ
#  حلِ مشکل، خودش مشکل شد. این اسکریپت مفسر را پیدا می‌کند، .env را می‌خواند،
#  و کارِ درست را انجام می‌دهد:
#
#   ۱) کدِ تازه روی سرور هست؟  (`check_ranking_page`)
#   ۲) سلامتِ سایت و داده       (`scripts/audit_live.py`)
#
#  فقط‌خواندنی است: هیچ نوشتنی روی داده یا فایل ندارد.
# ══════════════════════════════════════════════════════════════════════════════
set -Eeuo pipefail

APP_DIR="${KAVEH185_APP_DIR:-$HOME/Kaveh185-Back}"
ENV_FILE="$APP_DIR/.env"

readonly R=$'\033[0m' G=$'\033[32m' Y=$'\033[33m' RD=$'\033[31m' B=$'\033[1m' BL=$'\033[34m'
step(){ printf '\n%s▸ %s%s\n' "$B$BL" "$*" "$R"; }
ok(){   printf '%s✔%s %s\n' "$G" "$R" "$*"; }
warn(){ printf '%s▲%s %s\n' "$Y" "$R" "$*"; }
die(){  printf '%s✖%s %s\n' "$RD" "$R" "$*" >&2; exit 1; }

[[ -d "$APP_DIR" ]] || die "ریشهٔ برنامه پیدا نشد: $APP_DIR (با KAVEH185_APP_DIR عوض کنید)"

# ── ۱) پیدا کردنِ مفسرِ پایتون ───────────────────────────────────────────────
# ترتیب: متغیرِ صریح ← interpreter داخلِ virtualenv اپ ← هر venv دیگر ← python3.
pick_python() {
  if [[ -n "${KAVEH185_VENV:-}" && -x "$KAVEH185_VENV/bin/python" ]]; then
    printf '%s' "$KAVEH185_VENV/bin/python"; return 0
  fi
  local d
  for d in "$HOME"/virtualenv/Kaveh185-Back/*/; do
    [[ -x "${d}bin/python" ]] && { printf '%s' "${d}bin/python"; return 0; }
  done
  for d in "$HOME"/virtualenv/*/*/; do
    [[ -x "${d}bin/python" ]] && { printf '%s' "${d}bin/python"; return 0; }
  done
  if command -v python3 >/dev/null 2>&1; then command -v python3; return 0; fi
  if command -v python  >/dev/null 2>&1; then command -v python;  return 0; fi
  return 1
}

PY="$(pick_python)" || die "مفسرِ پایتون پیدا نشد. با KAVEH185_VENV=/path/to/venv اجرا کنید."
ok "مفسر: $PY  ($("$PY" --version 2>&1))"

cd "$APP_DIR"
[[ -f manage.py ]] || die "manage.py در $APP_DIR نیست"

# ── ۲) خواندنِ .env (بی‌آنکه مقدارها چاپ شوند) ───────────────────────────────
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
  ok ".env خوانده شد"
else
  warn ".env نیست — تنظیمات از پیش‌فرض‌ها می‌آید (روی تولید معمولاً درست نیست)"
fi

# ── ۳) کدام تنظیمات؟ ─────────────────────────────────────────────────────────
# روی هاست، `config.settings.production` درست است. اگر .env خودش ست کرده باشد،
# همان اولویت دارد. ⚠️ این را چاپ می‌کنیم: نصفِ عیب‌یابی‌ها همین‌جاست (اپ با
# یک settings بالا آمده و ما با یکی دیگر تست می‌کنیم).
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings.production}"
ok "تنظیمات: $DJANGO_SETTINGS_MODULE"

# ── ۴) کدِ تازه روی سرور هست؟ ────────────────────────────────────────────────
step "۱/۲ · وضعیتِ صفحهٔ رتبه‌بندی و مسیرها"
set +e
"$PY" manage.py check_ranking_page
RANKING_EXIT=$?
set -e

# ── ۵) سلامتِ سایت و داده ────────────────────────────────────────────────────
step "۲/۲ · سلامتِ سایت، داده و دیتابیس"
set +e
"$PY" manage.py shell < scripts/audit_live.py
AUDIT_EXIT=$?
set -e

# ── جمع‌بندی ─────────────────────────────────────────────────────────────────
printf '\n'
if (( RANKING_EXIT == 0 && AUDIT_EXIT == 0 )); then
  ok "همه‌چیز سالم است."
  exit 0
fi
if (( RANKING_EXIT != 0 )); then
  warn "صفحهٔ رتبه‌بندی مشکل دارد — پیامِ بالا را بفرستید."
fi
if (( AUDIT_EXIT != 0 )); then
  warn "بررسیِ سلامت موردِ نیازمندِ اقدام پیدا کرد — جزئیات در بخشِ ۲/۲."
fi
printf '  (اگر مرورگر این‌جا به API دسترسی ندارد، خطاهای HTTPِ بخشِ اول طبیعی‌اند؛\n'
printf '   ولی بخش‌های «داده» و «دیتابیس» همیشه معتبرند.)\n'
exit 1
