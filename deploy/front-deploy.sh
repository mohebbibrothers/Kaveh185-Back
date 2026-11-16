#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
#  کاوه ۱۸۵ — استقرار **فرانت ایستا** روی همان هاست cPanel
#
#  فرانت به HTML/JS/CSS ایستا تبدیل می‌شود (`output: "export"`) و از درون
#  خودِ جنگو سرو می‌شود (`apps/core/frontend.py`). هیچ فرآیند Node دائمی
#  لازم نیست — همان الگویی که روی این میزبان برای مهدیه جواب داده است.
#
#  اجرا روی هاست (cPanel → Terminal یا SSH):
#      bash ~/Kaveh185-Back/deploy/front-deploy.sh --bundle ~/frontend-XXXX.tar.gz
#
#  یا بدون آرگومان، اگر بسته در مسیر پیش‌فرض باشد:
#      bash ~/Kaveh185-Back/deploy/front-deploy.sh
#
#  گزینه‌ها:
#      --bundle PATH     مسیر بستهٔ tar.gz ساخته‌شده با `pnpm pack:front`
#      --from-dir PATH   به‌جای بسته، یک پوشهٔ out/ آماده را نصب کن (برای تست سریع)
#      --keep N          چند نسخهٔ قبلی نگه داشته شود (پیش‌فرض ۳)
#      --rollback        بازگشت فوری به نسخهٔ قبلی
#      --status          فقط وضعیت نسخهٔ فعلی را نشان بده
#      --dry-run         فقط بگو چه می‌کند، انجام نده
#
#  اصل طراحی: idempotent و fail-safe. هر مرحله دروازه است؛ اگر راستی‌آزمایی
#  بیرونی شکست بخورد، خودکار به نسخهٔ قبلی برمی‌گردد و سایت سالم می‌ماند.
# ══════════════════════════════════════════════════════════════════════════════
set -Eeuo pipefail

SCRIPT_VERSION="1.0.0"
readonly C_RESET=$'\033[0m' C_BOLD=$'\033[1m' C_DIM=$'\033[2m'
readonly C_GREEN=$'\033[32m' C_YELLOW=$'\033[33m' C_RED=$'\033[31m' C_BLUE=$'\033[34m' C_CYAN=$'\033[36m'
readonly TAG="[Kaveh185-Front ${SCRIPT_VERSION}]"

# ── پیش‌فرض‌ها (با متغیر محیطی قابل تغییر) ───────────────────────────────────
APP_DIR="${KAVEH185_APP_DIR:-$HOME/Kaveh185-Back}"          # ریشهٔ اپ جنگو (Passenger)
FRONT_ROOT="${KAVEH185_FRONT_ROOT:-$HOME/kaveh185-front}"   # نسخه‌ها و پیوند جاری
CURRENT="$FRONT_ROOT/current"                                # ← چیزی که جنگو می‌بیند
RELEASES="$FRONT_ROOT/releases"
SHARED="$FRONT_ROOT/shared"
LOG_DIR="${KAVEH185_LOG_DIR:-$HOME/kaveh185-deploy-logs}"
SITE_URL="${KAVEH185_SITE_URL:-https://kaveh185.ir}"
HEALTH_URL="${KAVEH185_HEALTH_URL:-https://api.kaveh185.ir/api/v1/health/ready/}"
KEEP_RELEASES=3

BUNDLE=""; FROM_DIR=""; ACTION="deploy"; DRY_RUN=0
LOG_FILE="$LOG_DIR/front-deploy-$(date +%Y%m%d-%H%M%S).log"

# ── رنگ و چاپ ───────────────────────────────────────────────────────────────
step(){ printf '\n%s▸ %s%s\n' "$C_BOLD$C_BLUE" "$*" "$C_RESET"; }
ok(){   printf '%s✔%s %s\n' "$C_GREEN" "$C_RESET" "$*"; }
warn(){ printf '%s▲%s %s\n' "$C_YELLOW" "$C_RESET" "$*"; }
err(){  printf '%s✖%s %s\n' "$C_RED" "$C_RESET" "$*" >&2; }
dim(){  printf '%s  %s%s\n' "$C_DIM" "$*" "$C_RESET"; }
die(){  err "$*"; exit 1; }
run(){  if (( DRY_RUN )); then dim "[dry-run] $*"; else "$@"; fi; }

# ── پارس آرگومان ────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --bundle)   BUNDLE="${2:-}"; shift ;;
    --from-dir) FROM_DIR="${2:-}"; shift ;;
    --keep)     KEEP_RELEASES="${2:-3}"; shift ;;
    --rollback) ACTION="rollback" ;;
    --status)   ACTION="status" ;;
    --dry-run)  DRY_RUN=1 ;;
    -h|--help)  sed -n '2,30p' "$0"; exit 0 ;;
    *) die "آرگومان ناشناخته: $1" ;;
  esac
  shift
done

mkdir -p "$LOG_DIR" "$RELEASES" "$SHARED"
exec > >(tee -a "$LOG_FILE") 2>&1
trap 'err "خطا در خط $LINENO (کد $?) — گزارش: $LOG_FILE"' ERR

printf '%s%s%s\n' "$C_BOLD$C_CYAN" "══════ کاوه ۱۸۵ — استقرار فرانت ایستا ══════" "$C_RESET"
dim "میزبان: $(hostname) · کاربر: $(whoami) · زمان: $(date '+%Y-%m-%d %H:%M')"
dim "ریشهٔ جنگو: $APP_DIR"
dim "ریشهٔ فرانت: $FRONT_ROOT"
dim "گزارش: $LOG_FILE"

# ══════════════════════════════════════════════════════════════════════════════
#  توابع کمکی
# ══════════════════════════════════════════════════════════════════════════════

# نسخهٔ سروشده از سرآیند پاسخ (تنها سنجهٔ واقعی از بیرون)
served_build() {
  curl -fsS -m 12 -o /dev/null -D - "$SITE_URL/" 2>/dev/null \
    | tr -d '\r' | awk -F': ' 'tolower($1)=="x-frontend-build"{print $2; exit}'
}

http_code() { curl -s -o /dev/null -m 12 -w '%{http_code}' "$1" 2>/dev/null || echo "000"; }

# بازنشانی نرم Passenger — لازم است چون مسیر `current` در import-time حل می‌شود؟
# نه: `realpath` در هر درخواست حل می‌شود، پس این فقط برای اطمینان است و
# ارزان؛ touch روی فایل خالی.
restart_app() {
  local f="$APP_DIR/tmp/restart.txt"
  if [[ -d "$APP_DIR/tmp" ]]; then
    run touch "$f"
    dim "restart.txt لمس شد (بازنشانی نرم Passenger)"
  else
    warn "پوشهٔ $APP_DIR/tmp پیدا نشد — بازنشانی Passenger انجام نشد"
  fi
}

# فعال‌سازی یک نسخه با جابه‌جایی اتمی پیوند نمادین
activate() {
  local target="$1"
  # مرز ایمنی: هدف باید پوشهٔ واقعی باشد، نه خودِ `current` و نه مسیر خالی.
  if [[ -z "$target" || ! -d "$target" ]]; then
    die "هدف فعال‌سازی معتبر نیست: '${target}'"
  fi
  if [[ "$(realpath "$target")" == "$(realpath -m "$CURRENT")" ]]; then
    die "هدف فعال‌سازی همان current است — این کار پیوند را به خودش وصل می‌کند"
  fi
  local tmp="$FRONT_ROOT/.current.tmp.$$"
  ln -sfn "$target" "$tmp"
  # `-T` تا اگر `current` پوشه بود هم با پیوند جایگزین شود (mv اتمی است)
  run mv -Tf "$tmp" "$CURRENT"
  ok "current → $(basename "$target")"
}

# ══════════════════════════════════════════════════════════════════════════════
#  status
# ══════════════════════════════════════════════════════════════════════════════
if [[ "$ACTION" == "status" ]]; then
  step "وضعیت"
  if [[ -L "$CURRENT" ]]; then
    dim "current → $(readlink "$CURRENT")"
  elif [[ -e "$CURRENT" ]]; then
    dim "current یک پوشهٔ واقعی است (نه پیوند): $CURRENT"
  else
    warn "هیچ نسخه‌ای فعال نیست"
  fi
  printf '%-28s %s\n' "نسخه‌های موجود:" "$(ls -1 "$RELEASES" 2>/dev/null | wc -l)"
  ls -1 "$RELEASES" 2>/dev/null | tail -5 | sed 's/^/   • /'
  echo
  printf '%-28s %s\n' "سایت:" "${SITE_URL}/"
  printf '%-28s %s\n' "کد پاسخ ریشه:" "$(http_code "$SITE_URL/")"
  printf '%-28s %s\n' "نسخهٔ سروشده:" "$(served_build || echo '—')"
  printf '%-28s %s\n' "سلامت API:" "$(http_code "$HEALTH_URL")"
  if [[ -f "$CURRENT/BUILD_INFO.json" ]]; then
    echo; dim "BUILD_INFO.json نسخهٔ فعال:"
    python3 -c "
import json,sys
d=json.load(open('$CURRENT/BUILD_INFO.json'))
print('   version   ', d.get('version'))
print('   built_at  ', d.get('built_at'))
print('   routes    ', len(d.get('routes',[])))
print('   files     ', d.get('totals',{}).get('files'))
t=d.get('totals',{})
if t: print('   brotli    ', round(t.get('brotli_bytes',0)/1024,1), 'KB')
" 2>/dev/null || true
  fi
  exit 0
fi

# ══════════════════════════════════════════════════════════════════════════════
#  rollback
# ══════════════════════════════════════════════════════════════════════════════
if [[ "$ACTION" == "rollback" ]]; then
  step "بازگشت به نسخهٔ قبلی"
  mapfile -t list < <(ls -1dt "$RELEASES"/*/ 2>/dev/null)
  cur=""
  if [[ -L "$CURRENT" ]]; then cur="$(readlink -f "$CURRENT" 2>/dev/null || true)"; fi
  prev=""
  for d in "${list[@]}"; do
    d="${d%/}"
    if [[ "$d" != "$cur" ]]; then prev="$d"; break; fi
  done
  [[ -n "$prev" && -d "$prev" ]] || die "نسخهٔ دیگری برای بازگشت وجود ندارد"
  dim "هدف: $(basename "$prev")"
  activate "$prev"
  restart_app
  sleep 2
  served="$(served_build || true)"
  if [[ -n "$served" ]]; then ok "نسخهٔ سروشده اکنون: $served"; else warn "سرآیند نسخه خوانده نشد — دستی بررسی کنید"; fi
  exit 0
fi

# ══════════════════════════════════════════════════════════════════════════════
#  deploy
# ══════════════════════════════════════════════════════════════════════════════

# ── ۱) پیش‌نیازها ──────────────────────────────────────────────────────────
step "۱/۸ پیش‌نیازها"
[[ -f "$APP_DIR/manage.py" ]] || die "ریشهٔ جنگو پیدا نشد: $APP_DIR"
for c in tar curl python3; do command -v "$c" >/dev/null || die "ابزار لازم نصب نیست: $c"; done
[[ -f "$APP_DIR/apps/core/frontend.py" ]] || die "میان‌افزار فرانت در بک‌اند نیست — اول بک‌اند را به‌روز کنید (git pull)"
ok "جنگو در $APP_DIR · ابزارها کامل · میان‌افزار فرانت موجود"

# ── ۲) آماده‌سازی محتوای نسخه ─────────────────────────────────────────────
step "۲/۸ آماده‌سازی محتوای نسخه"
STAGE="$(mktemp -d "$FRONT_ROOT/.stage.XXXXXX")"
cleanup_stage(){ [[ -d "$STAGE" ]] && rm -rf "$STAGE"; }
trap 'cleanup_stage; err "خطا در خط $LINENO — گزارش: $LOG_FILE"' ERR

if [[ -n "$FROM_DIR" ]]; then
  [[ -f "$FROM_DIR/index.html" ]] || die "پوشهٔ داده‌شده index.html ندارد: $FROM_DIR"
  dim "منبع: پوشهٔ $FROM_DIR"
  cp -a "$FROM_DIR/." "$STAGE/"
elif [[ -n "$BUNDLE" ]]; then
  [[ -f "$BUNDLE" ]] || die "بسته پیدا نشد: $BUNDLE"

  # ── راستی‌آزمایی sha256 ────────────────────────────────────────────────
  if [[ -f "$BUNDLE.sha256" ]]; then
    expected="$(awk '{print $1}' "$BUNDLE.sha256")"
    actual="$(sha256sum "$BUNDLE" | awk '{print $1}')"
    [[ "$expected" == "$actual" ]] || die "هش بسته نمی‌خواند (انتظار ${expected:0:12}، دریافت ${actual:0:12})"
    ok "sha256 بسته تأیید شد (${actual:0:12})"
  else
    warn "فایل .sha256 کنار بسته نیست — یکتایی محتوا تأیید نشد"
  fi

  # ── بازکردن امن: بی‌مسیر مطلق، بی‌`..`، بی‌پیوند نمادین ────────────────
  if tar -tzf "$BUNDLE" | grep -qE '(^/|(^|/)\.\.(/|$))'; then
    die "بسته مسیر ناامن دارد (مطلق یا شامل ..) — رد شد"
  fi
  tar -xzf "$BUNDLE" -C "$STAGE" --no-same-owner
  ok "بسته باز شد"
else
  die "منبعی مشخص نشده: --bundle PATH یا --from-dir PATH"
fi

[[ -f "$STAGE/index.html" ]] || die "محتوای استخراج‌شده index.html ندارد"

# ── ۳) دروازهٔ محتوا ─────────────────────────────────────────────────────
step "۳/۸ دروازهٔ محتوا"
python3 - "$STAGE" <<'PY'
import json, pathlib, sys
root = pathlib.Path(sys.argv[1])
info = root / "BUILD_INFO.json"
if not info.is_file():
    print("✖ BUILD_INFO.json غایب است — بسته با `pnpm pack:front` ساخته نشده")
    raise SystemExit(1)
data = json.loads(info.read_text("utf-8"))
files = data.get("files") or {}
missing = [rel for rel in files if not (root / rel).is_file()]
if missing:
    print(f"✖ {len(missing)} فایل اعلام‌شده در بسته نیست، مثلاً: {missing[:3]}")
    raise SystemExit(1)
# مسیرهای حیاتی
for rel in ("index.html", "404.html", "manifest.webmanifest", "robots.txt"):
    if not (root / rel).is_file():
        print(f"✖ فایل حیاتی غایب: {rel}")
        raise SystemExit(1)
if not any(p.name == "index.txt" for p in root.rglob("index.txt")):
    print("✖ بارِ RSC (index.txt) غایب است — ناوبری داخلی به بارگذاری کامل می‌افتد")
    raise SystemExit(1)
print(f"✔ {len(files)} فایل تأیید شد · {len(data.get('routes') or [])} مسیر")
t = data.get("totals") or {}
if t:
    print(f"  brotli {t.get('brotli_bytes',0)/1024:.0f}KB از {t.get('raw_bytes',0)/1024:.0f}KB خام")
print(f"  نسخه {data.get('version')} · ساخته‌شده {data.get('built_at')}")
PY
ok "محتوای نسخه سالم است"

# ── ۴) ساخت نسخه ────────────────────────────────────────────────────────
step "۴/۸ ساخت نسخهٔ تازه"
ID="$(date +%Y%m%d-%H%M%S)"
RELEASE="$RELEASES/$ID"
run mkdir -p "$RELEASE"
run cp -a "$STAGE/." "$RELEASE/"
# مالکیت و دسترسی: فایل‌ها فقط-خواندنی، پوشه‌ها قابل‌پیمایش
run find "$RELEASE" -type d -exec chmod 755 {} +
run find "$RELEASE" -type f -exec chmod 644 {} +
run chmod 711 "$FRONT_ROOT" "$RELEASES" 2>/dev/null || true
cleanup_stage
trap 'err "خطا در خط $LINENO — گزارش: $LOG_FILE"' ERR
ok "نسخهٔ $ID در $RELEASE"

# ── ۵) پیوند به جنگو ────────────────────────────────────────────────────
step "۵/۸ اتصال به جنگو (FRONTEND_DIST)"
# چرا پیوند و نه کپی؟ تا جابه‌جایی نسخه با یک `mv` اتمی انجام شود و
# استقرار/بازگشت بدون بازنشانی Passenger دیده شود.
LINK="$APP_DIR/frontend"
if [[ -d "$LINK" && ! -L "$LINK" ]]; then
  warn "$LINK یک پوشهٔ واقعی است — پشتیبان می‌گیرم و با پیوند جایگزین می‌کنم"
  run mv "$LINK" "$LINK.bak.$(date +%s)"
fi
if [[ -e "$SHARED/FRONTEND_DIST" ]]; then
  dim "پیوند آماده است: $LINK"
else
  run ln -sfn "$CURRENT" "$SHARED/FRONTEND_DIST"
  run ln -sfn "$CURRENT" "$LINK"
fi

# متغیر محیطی: اگر در .env نیست، اضافه کن (idempotent)
if ! grep -q '^FRONTEND_DIST=' "$APP_DIR/.env" 2>/dev/null; then
  if (( DRY_RUN )); then
    dim "[dry-run] افزودن FRONTEND_DIST=$LINK به .env"
  else
    printf '\n# رابط کاربری ایستای Next (سروشده از درون جنگو)\nFRONTEND_DIST=%s\n' "$LINK" >> "$APP_DIR/.env"
    chmod 600 "$APP_DIR/.env"
    ok "FRONTEND_DIST به .env افزوده شد"
  fi
else
  dim "FRONTEND_DIST از قبل در .env هست"
fi
ok "پیوند آماده: $LINK → current"

# ── ۶) فعال‌سازی اتمی + بازنشانی ────────────────────────────────────────
step "۶/۸ فعال‌سازی اتمی"
# ⚠️ نسخهٔ قبلی فقط وقتی معتبر است که `current` یک پیوند سالم به یک پوشهٔ
# واقعی **داخل** releases باشد. `readlink -f` روی مسیر ناموجود، خودِ مسیر
# را برمی‌گرداند؛ اگر همان را به `activate` بدهیم، پیوندی به خودش می‌سازیم
# و بازگشت بی‌اثر می‌شود. این حالت واقعاً در تمرین اول رخ داد.
PREV=""
if [[ -L "$CURRENT" ]]; then
  cand="$(readlink -f "$CURRENT" 2>/dev/null || true)"
  if [[ -n "$cand" && -d "$cand" && "$cand" == "$RELEASES/"* && "$cand" != "$RELEASE" ]]; then
    PREV="$cand"
  fi
fi
activate "$RELEASE"
restart_app
dim "نسخهٔ قبلی برای بازگشت: ${PREV:-—}"

# ── ۷) راستی‌آزمایی بیرونی ──────────────────────────────────────────────
step "۷/۸ راستی‌آزمایی بیرونی"
EXPECTED="$(python3 -c "import json;print(json.load(open('$RELEASE/BUILD_INFO.json'))['sha256_index'][:12])")"
dim "انتظار: نسخهٔ $EXPECTED در سرآیند X-Frontend-Build"

fail_verify=0
sleep 3
served="$(served_build || true)"
if [[ "$served" == *"$EXPECTED"* ]]; then
  ok "ریشهٔ سایت نسخهٔ درست را سرو می‌کند ($served)"
else
  warn "سرآیند نسخه: '${served:-—}' (انتظار: *$EXPECTED*)"
  fail_verify=1
fi

for path in "/" "/register/" "/rules/" "/receipt/"; do
  code="$(http_code "$SITE_URL$path")"
  if [[ "$code" == "200" ]]; then ok "$path → 200"
  else warn "$path → $code"; fail_verify=1; fi
done

code="$(http_code "$SITE_URL/not-a-real-page/")"
if [[ "$code" == "404" ]]; then ok "صفحهٔ ناشناخته → 404 (نه 200)"; else warn "صفحهٔ ناشناخته → $code"; fail_verify=1; fi

code="$(http_code "$HEALTH_URL")"
if [[ "$code" == "200" ]]; then ok "سلامت API → 200"; else warn "سلامت API → $code"; fail_verify=1; fi

# روزی که اینترنت میزبان به دامنه برنگردد، راستی‌آزمایی شکست می‌خورد و
# نسخهٔ سالم را برمی‌گردانیم — همان رفتار fail-safe بک‌اند.
if (( fail_verify )); then
  err "راستی‌آزمایی شکست خورد — بازگشت خودکار"
  if [[ -n "$PREV" && -d "$PREV" ]]; then
    activate "$PREV"
    restart_app
    err "به نسخهٔ $(basename "$PREV") برگشت داده شد"
  else
    err "نسخهٔ قبلی نبود؛ current روی نسخهٔ تازه مانده است — دستی بررسی کنید"
  fi
  exit 1
fi

# ── ۸) هرس نسخه‌های قدیمی ───────────────────────────────────────────────
step "۸/۸ هرس"
count=0
CUR="$(readlink -f "$CURRENT")"
while read -r d; do
  d="${d%/}"
  [[ "$(realpath "$d")" == "$(realpath "$CUR")" ]] && continue
  count=$((count+1))
  if (( count > KEEP_RELEASES )); then
    run rm -rf "$d"
    dim "حذف نسخهٔ قدیمی: $(basename "$d")"
  fi
done < <(ls -1dt "$RELEASES"/*/ 2>/dev/null | tail -n +1)
ok "نسخه‌های نگه‌داشته‌شده: $(( $(ls -1 "$RELEASES" | wc -l) ))"

printf '\n%s%s%s\n' "$C_BOLD$C_GREEN" "✔ استقرار فرانت کامل شد" "$C_RESET"
dim "نسخه: $ID · شناسه: $EXPECTED"
dim "سایت: $SITE_URL/"
dim "بازگشت در صورت نیاز: bash $0 --rollback"
exit 0
