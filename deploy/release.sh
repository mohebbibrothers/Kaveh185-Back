#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
#  کاوه ۱۸۵ — انتشار کامل در یک فرمان (بک + فرانت)
#
#  چرا این اسکریپت؟
#  ──────────────
#  تا امروز یک تغییر مثل «صفحهٔ آزمون» سه قدم جدا داشت و هر بار یکی‌شان
#  فراموش می‌شد: ۱) بیلد فرانت و گذاشتن بسته جایی که هاست بخواند،
#  ۲) نصب بسته، ۳) migrate/collectstatic. نتیجهٔ فراموشی، صفحهٔ ۵۰۰ روی
#  سایت زنده بود.
#
#  این اسکریپت همان سه کار را پشت سر هم و با توقف در اولین خطا انجام می‌دهد.
#  هیچ آرگومان اجباری ندارد. اگر بستهٔ فرانت را ندادید، از آخرین انتشار
#  گیت‌هاب استفاده می‌کند.
#
#      bash ~/Kaveh185-Back/deploy/release.sh                    # همه‌چیز
#      bash ~/Kaveh185-Back/deploy/release.sh --back-only        # فقط بک
#      bash ~/Kaveh185-Back/deploy/release.sh --front-only       # فقط فرانت
#      bash ~/Kaveh185-Back/deploy/release.sh --bundle ~/frontend-*.tar.gz
#      bash ~/Kaveh185-Back/deploy/release.sh --url https://.../frontend-x.tar.gz
#      bash ~/Kaveh185-Back/deploy/release.sh --dry-run
#
#  اصول (همان درس‌های استقرار قبلی، بدون استثنا):
#    • هیچ process substitution — روی این هاست /dev/fd نیست.
#    • هیچ دستور تعاملی؛ `--noinput` همه‌جا.
#    • کد خروج با واقعیت می‌خواند.
#    • فرانت با نصب اتمیک و بازگشت‌پذیر (release/current) نصب می‌شود.
# ══════════════════════════════════════════════════════════════════════════════
set -Eeuo pipefail

readonly R=$'\033[0m' B=$'\033[1m' D=$'\033[2m'
readonly G=$'\033[32m' Y=$'\033[33m' RD=$'\033[31m' BL=$'\033[34m' CY=$'\033[36m'
readonly TAG="[Kaveh185-Release]"

APP_DIR="${KAVEH185_APP_DIR:-$HOME/Kaveh185-Back}"
DEPLOY_DIR="$APP_DIR/deploy"
DO_BACK=1
DO_FRONT=1
DRY=0
BUNDLE=""
URL=""

step(){ printf '\n%s▸ %s%s\n' "$B$BL" "$*" "$R"; }
ok(){   printf '%s✔%s %s\n' "$G" "$R" "$*"; }
warn(){ printf '%s▲%s %s\n' "$Y" "$R" "$*"; }
err(){  printf '%s✖%s %s\n' "$RD" "$R" "$*" >&2; }
dim(){  printf '%s  %s%s\n' "$D" "$*" "$R"; }
die(){  err "$*"; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --back-only)  DO_FRONT=0 ;;
    --front-only) DO_BACK=0 ;;
    --bundle)     BUNDLE="${2:-}"; shift ;;
    --url)        URL="${2:-}"; shift ;;
    --dry-run)    DRY=1 ;;
    -h|--help)    sed -n '2,27p' "$0"; exit 0 ;;
    *) die "آرگومان ناشناخته: $1" ;;
  esac
  shift
done

printf '%s%s══════ کاوه ۱۸۵ — انتشار ══════%s\n' "$B$CY" "" "$R"
dim "$(date '+%Y-%m-%d %H:%M') · $(hostname)"
dim "ریشهٔ اپ: $APP_DIR"

[[ -d "$APP_DIR" ]] || die "پوشهٔ اپ پیدا نشد: $APP_DIR"
[[ -f "$DEPLOY_DIR/upgrade.sh" ]] || warn "deploy/upgrade.sh نیست — شاید مخزن قدیمی است"

FAILED=0

# ══ ۱) بک‌اند: کد + migrate + collectstatic + ری‌استارت ══════════════════════
if (( DO_BACK )); then
  step "۱/۲ · بک‌اند (کد، وابستگی، پشتیبان، مهاجرت، استاتیک، ری‌استارت)"
  args=(--no-pull)
  (( DRY )) && args+=(--dry-run)
  if bash "$DEPLOY_DIR/upgrade.sh" "${args[@]}"; then
    ok "بک‌اند به‌روز شد"
  else
    err "بک‌اند شکست خورد — بخش فرانت اجرا نمی‌شود"
    exit 1
  fi
else
  dim "بک‌اند رد شد (--front-only)"
fi

# ══ ۲) فرانت: نصب بستهٔ ایستا ════════════════════════════════════════════════
if (( DO_FRONT )); then
  step "۲/۲ · فرانت ایستا"
  fargs=()
  if [[ -n "$BUNDLE" ]]; then
    [[ -f "$BUNDLE" ]] || die "بسته پیدا نشد: $BUNDLE"
    fargs+=(--bundle "$BUNDLE")
    dim "بسته: $BUNDLE ($(du -h "$BUNDLE" | cut -f1))"
  elif [[ -n "$URL" ]]; then
    fargs+=(--url "$URL")
    dim "بسته از نشانی: $URL"
  else
    dim "بدون --bundle/--url: آخرین انتشار از گیت‌هاب گرفته می‌شود"
  fi
  (( DRY )) && fargs+=(--dry-run)
  if bash "$DEPLOY_DIR/front-deploy.sh" "${fargs[@]}"; then
    ok "فرانت نصب شد"
  else
    err "نصب فرانت شکست خورد — سایت با نسخهٔ قبلی بالا می‌ماند"
    err "وضعیت: bash $DEPLOY_DIR/front-deploy.sh --status"
    exit 1
  fi
else
  dim "فرانت رد شد (--back-only)"
fi

# ══ گزارش پایانی ═════════════════════════════════════════════════════════════
step "بررسی پایانی"
if (( DRY )); then
  dim "[dry-run] بررسی سلامت انجام نشد"
  exit 0
fi

for __u in "https://kaveh185.ir/" "https://kaveh185.ir/api/v1/health/ready/" "https://api.kaveh185.ir/api/v1/health/ready/"; do
  __c="$(curl -s -o /dev/null -m 15 -w '%{http_code}' "$__u" 2>/dev/null || echo 000)"
  if [[ "$__c" == "200" ]]; then ok "$__u → $__c"; else
    warn "$__u → $__c"
    FAILED=1
  fi
done

if (( FAILED )); then
  warn "بعضی بررسی‌ها سبز نبودند. لاگ‌ها: $HOME/kaveh185-deploy-logs"
  exit 1
fi

printf '\n%s✔ انتشار کامل شد%s\n' "$B$G" "$R"
dim "بازگشت فرانت: bash $DEPLOY_DIR/front-deploy.sh --rollback"
exit 0
