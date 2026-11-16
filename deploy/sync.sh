#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
#  کاوه ۱۸۵ — هم‌سو کردن اپ با مخزن، بی‌آنکه کار گم شود
#
#  چرا این اسکریپت لازم شد؟
#  ──────────────────────
#  نصب اولیهٔ بسته، فایل‌های تحت نظر گیت را مستقیم روی دیسک کپی کرد. نتیجه:
#  `git pull` با «local changes would be overwritten» شکست می‌خورد، چون گیت
#  می‌دید فایل‌ها عوض شده‌اند — در حالی که همان تغییرها در کامیت‌های تازه
#  هم بودند.
#
#  این اسکریپت سه کار می‌کند، به ترتیبی که هیچ‌چیز از دست نرود:
#    ۱) هر تغییر محلی (و فایل‌های ردیابی‌نشده) را در یک stash نام‌دار
#       کنار می‌گذارد — نه پاک. اگر روزی لازم شد: `git stash list`
#    ۲) `git pull --ff-only` می‌زند
#    ۳) اگر پول موفق بود، می‌گوید stash را می‌شود دور ریخت؛ اگر نبود،
#       stash را برمی‌گرداند
#
#      bash deploy/sync.sh              # هم‌سو کن
#      bash deploy/sync.sh --dry-run    # فقط بگو چه می‌شود
#      bash deploy/sync.sh --restore    # آخرین stash را برگردان
# ══════════════════════════════════════════════════════════════════════════════
set -Eeuo pipefail

readonly R=$'\033[0m' B=$'\033[1m' D=$'\033[2m'
readonly G=$'\033[32m' Y=$'\033[33m' RD=$'\033[31m' BL=$'\033[34m'

APP_DIR="${KAVEH185_APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
DRY=0
MODE="sync"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY=1 ;;
    --restore) MODE="restore" ;;
    -h|--help) sed -n '2,26p' "$0"; exit 0 ;;
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

cd "$APP_DIR"
[[ -d .git ]] || die "مخزن گیت نیست: $APP_DIR"

if [[ "$MODE" == "restore" ]]; then
  step "برگرداندن آخرین stash"
  git stash list | head -3 | sed 's/^/  /'
  git stash pop
  ok "برگشت داده شد"
  exit 0
fi

step "۱/۳ بررسی وضعیت"
printf '  HEAD محلی: %s\n' "$(git rev-parse --short HEAD)"
git fetch origin --quiet
printf '  origin/main: %s\n' "$(git rev-parse --short origin/main)"

dirty="$(git status --porcelain | wc -l | tr -d ' ')"
dim "فایل‌های تغییرکرده/ردیابی‌نشده: $dirty"

if [[ "$dirty" == "0" ]]; then
  ok "درخت پاک است — کاری لازم نیست"
else
  step "۲/۳ کنار گذاشتن تغییرات محلی (قابل برگشت)"
  git status --porcelain | head -12 | sed 's/^/  /'
  (( dirty > 12 )) && dim "… و $((dirty - 12)) فایل دیگر"

  LABEL="pre-sync-$(date +%Y%m%d-%H%M%S)"
  if (( DRY )); then
    dim "[dry-run] git stash push -u -m $LABEL"
    dim "[dry-run] git pull --ff-only origin main"
    exit 0
  fi
  git stash push -u -m "$LABEL" >/dev/null
  ok "کنار گذاشته شد: stash@{0} ($LABEL)"
fi

step "۳/۳ هم‌سو با مخزن"
if (( DRY )); then dim "[dry-run] git pull --ff-only origin main"; exit 0; fi

if git pull --ff-only origin main; then
  ok "هم‌سو شد · HEAD → $(git rev-parse --short HEAD)"
  if [[ "$dirty" != "0" ]]; then
    printf '\n'
    dim "تغییرات محلی در stash@{0} مانده‌اند (پاک نشده‌اند)."
    dim "اگر مطمئنی لازم نیستند:  git stash drop"
    dim "اگر لازم شدند:            bash $0 --restore"
  fi
else
  err "پول شکست خورد — تغییرات محلی برگردانده می‌شوند"
  git stash pop >/dev/null 2>&1 || warn "برگرداندن خودکار نشد: git stash pop"
  exit 1
fi
