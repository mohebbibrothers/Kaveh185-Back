#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
#  کاوه ۱۸۵ — استقرار فرانت ایستا روی هاست cPanel (بی‌هیچ فرآیند Node)
#
#  روی هاست: bash ~/Kaveh185-Back/deploy/front-deploy.sh --bundle ~/frontend-*.tar.gz
#
#  ⚠️ این اسکریپت عمداً به **هیچ** مفسری جز bash نیاز ندارد. روی این میزبان
#  نه `python3` هست نه Node؛ فقط bash، coreutils، curl و tar. اعتبارسنجی
#  JSON هم با `sha256sum -c` انجام می‌شود، نه با خواندن JSON.
#
#  گزینه‌ها:
#    --url PATH        خودش آخرین بسته را از این نشانی بگیرد (ساده‌ترین راه)
#    --bundle PATH     بستهٔ tar.gz ساخته‌شده با `pnpm pack:front`
#    --from-dir PATH   نصب از یک پوشهٔ out/ (تست)
#    --keep N          چند نسخهٔ قبلی نگه داشته شود (پیش‌فرض ۳)
#    --rollback        بازگشت فوری به نسخهٔ قبلی
#    --status          وضعیت نسخهٔ فعلی
#    --dry-run         فقط بگو چه می‌کند
# ══════════════════════════════════════════════════════════════════════════════
set -Eeuo pipefail

SCRIPT_VERSION="1.1.0"
readonly R=$'\033[0m' B=$'\033[1m' D=$'\033[2m'
readonly G=$'\033[32m' Y=$'\033[33m' RD=$'\033[31m' BL=$'\033[34m' CY=$'\033[36m'
readonly TAG="[Kaveh185-Front ${SCRIPT_VERSION}]"

# ── مسیرها ──────────────────────────────────────────────────────────────────
# پیش‌فرض‌ها بر اساس چیدمان واقعی هاست (کاربر kavehir، HOME=/home/kavehir)
APP_DIR="${KAVEH185_APP_DIR:-$HOME/Kaveh185-Back}"
FRONT_ROOT="${KAVEH185_FRONT_ROOT:-$HOME/kaveh185-front}"
CURRENT="$FRONT_ROOT/current"
RELEASES="$FRONT_ROOT/releases"
LOG_DIR="${KAVEH185_LOG_DIR:-$HOME/kaveh185-deploy-logs}"
SITE_URL="${KAVEH185_SITE_URL:-https://kaveh185.ir}"
HEALTH_URL="${KAVEH185_HEALTH_URL:-https://kaveh185.ir/api/v1/health/ready/}"
DEFAULT_URL="${KAVEH185_BUNDLE_URL:-}"

KEEP_RELEASES=3
BUNDLE=""; FROM_DIR=""; ACTION="deploy"; DRY_RUN=0; URL=""

step(){ printf '\n%s▸ %s%s\n' "$B$BL" "$*" "$R"; }
ok(){   printf '%s✔%s %s\n' "$G" "$R" "$*"; }
warn(){ printf '%s▲%s %s\n' "$Y" "$R" "$*"; }
err(){  printf '%s✖%s %s\n' "$RD" "$R" "$*" >&2; }
dim(){  printf '%s  %s%s\n' "$D" "$*" "$R"; }
die(){  err "$*"; exit 1; }
run(){  if (( DRY_RUN )); then dim "[dry-run] $*"; else "$@"; fi; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --url)      URL="${2:-}"; shift ;;
    --bundle)   BUNDLE="${2:-}"; shift ;;
    --from-dir) FROM_DIR="${2:-}"; shift ;;
    --keep)     KEEP_RELEASES="${2:-3}"; shift ;;
    --rollback) ACTION="rollback" ;;
    --status)   ACTION="status" ;;
    --dry-run)  DRY_RUN=1 ;;
    -h|--help)  sed -n '2,22p' "$0"; exit 0 ;;
    *) die "آرگومان ناشناخته: $1" ;;
  esac
  shift
done

mkdir -p "$LOG_DIR" "$RELEASES"
LOG_FILE="$LOG_DIR/front-deploy-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee -a "$LOG_FILE") 2>&1
trap 'err "خطا در خط $LINENO (کد $?) — گزارش: $LOG_FILE"' ERR

served_build() {
  curl -fsS -m 12 -o /dev/null -D - "$SITE_URL/" 2>/dev/null \
    | tr -d '\r' | awk -F': ' 'tolower($1)=="x-frontend-build"{print $2; exit}'
}
http_code(){ curl -s -o /dev/null -m 12 -w '%{http_code}' "$1" 2>/dev/null || echo "000"; }

restart_app(){
  if [[ -d "$APP_DIR/tmp" ]]; then
    run touch "$APP_DIR/tmp/restart.txt"
    dim "restart.txt لمس شد"
  else
    warn "پوشهٔ $APP_DIR/tmp نبود — بازنشانی Passenger انجام نشد"
  fi
}

activate(){
  local target="$1"
  [[ -n "$target" && -d "$target" ]] || die "هدف فعال‌سازی معتبر نیست: '${target}'"
  if [[ -L "$CURRENT" && "$(readlink -f "$target")" == "$(readlink -f "$CURRENT")" ]]; then
    dim "current از قبل همین نسخه است"
    return 0
  fi
  local tmp="$FRONT_ROOT/.current.tmp.$$"
  ln -sfn "$target" "$tmp"
  run mv -Tf "$tmp" "$CURRENT"
  ok "current → $(basename "$target")"
}

banner(){
  printf '%s%s%s\n' "$B$CY" "══════ کاوه ۱۸۵ — فرانت ایستا ══════" "$R"
  dim "میزبان: $(hostname) · کاربر: $(whoami) · $(date '+%Y-%m-%d %H:%M')"
  dim "ریشهٔ جنگو: $APP_DIR · ریشهٔ فرانت: $FRONT_ROOT"
  dim "گزارش: $LOG_FILE"
}

# ══════════════════════════════════════════════════════════════════════════════
#  status
# ══════════════════════════════════════════════════════════════════════════════
if [[ "$ACTION" == "status" ]]; then
  banner; step "وضعیت"
  if [[ -L "$CURRENT" ]]; then
    dim "current → $(readlink "$CURRENT")"
    [[ -f "$CURRENT/BUILD_ID" ]] && dim "شناسهٔ نصب‌شده: $(cat "$CURRENT/BUILD_ID")"
  elif [[ -e "$CURRENT" ]]; then
    warn "current یک پوشهٔ واقعی است، نه پیوند"
  else
    warn "هیچ نسخه‌ای فعال نیست"
  fi
  dim "نسخه‌های موجود: $(find "$RELEASES" -maxdepth 1 -mindepth 1 -type d 2>/dev/null | wc -l)"
  echo
  printf '  %-22s %s\n' "سایت" "${SITE_URL}/"
  printf '  %-22s %s\n' "کد ریشه" "$(http_code "$SITE_URL/")"
  printf '  %-22s %s\n' "نسخهٔ سروشده" "$(served_build || echo '—')"
  printf '  %-22s %s\n' "سلامت API" "$(http_code "$HEALTH_URL")"
  printf '  %-22s %s\n' "فضای دیسک" "$(du -sh "$FRONT_ROOT" 2>/dev/null | cut -f1)"
  exit 0
fi

# ══════════════════════════════════════════════════════════════════════════════
#  rollback
# ══════════════════════════════════════════════════════════════════════════════
if [[ "$ACTION" == "rollback" ]]; then
  banner; step "بازگشت به نسخهٔ قبلی"
  cur=""; [[ -L "$CURRENT" ]] && cur="$(readlink -f "$CURRENT" 2>/dev/null || true)"
  prev=""
  while IFS= read -r d; do
    d="${d%/}"
    [[ "$d" == "$cur" ]] && continue
    prev="$d"; break
  done < <(ls -1dt "$RELEASES"/*/ 2>/dev/null)
  [[ -n "$prev" && -d "$prev" ]] || die "نسخهٔ دیگری برای بازگشت نیست"
  dim "هدف: $(basename "$prev")"
  activate "$prev"; restart_app; sleep 2
  served="$(served_build || true)"
  [[ -n "$served" ]] && ok "نسخهٔ سروشده: $served" || warn "سرآیند نسخه خوانده نشد"
  exit 0
fi

# ══════════════════════════════════════════════════════════════════════════════
#  deploy
# ══════════════════════════════════════════════════════════════════════════════
banner

step "۱/۸ پیش‌نیازها"
[[ -f "$APP_DIR/manage.py" ]] || die "ریشهٔ جنگو پیدا نشد: $APP_DIR"
for c in tar curl sha256sum find sort; do
  command -v "$c" >/dev/null || die "ابزار لازم نصب نیست: $c"
done
[[ -f "$APP_DIR/apps/core/frontend.py" ]] || die "میان‌افزار فرانت در بک‌اند نیست — اول بک‌اند را به‌روز کنید"
ok "جنگو سر جایش · ابزارها کامل · میان‌افزار فرانت موجود"

# ── آیا این دامنه واقعاً به همین اپلیکیشن می‌رسد؟ ──────────────────────────
# بزرگ‌ترین مانع واقعی: دامنهٔ اصلی حساب `kaveh185.ir` است، ولی اپلیکیشن
# پایتون فقط روی زیردامنهٔ `api.kaveh185.ir` سوار شده. در این حالت سایت
# روی ریشه بالا نمی‌آید، هرچند همه‌چیز درست نصب شده — و پیام خطایش گمراه‌کننده
# است («Index of /» یا صفحهٔ پیش‌فرض). پس همین‌جا و پیش از هر تغییری می‌سنجیم.
probe="$(curl -s -o /dev/null -m 12 -w '%{http_code}' "$SITE_URL/api/v1/health/live/" 2>/dev/null || echo 000)"
if [[ "$probe" == "200" ]]; then
  ok "دامنهٔ سایت به اپلیکیشن می‌رسد (health/live → 200)"
else
  warn "────────────────────────────────────────────────────────────"
  warn "دامنهٔ $SITE_URL به اپلیکیشن پایتون نمی‌رسد (کد $probe)."
  warn "علت معمول: اپلیکیشن فقط روی زیردامنه سوار است."
  warn ""
  warn "در cPanel → Setup Python App → ویرایش همان اپ:"
  warn "   Application root : Kaveh185-Back"
  warn "   Application URL  : kaveh185.ir        ← دامنهٔ اصلی، نه api."
  warn "   سپس Save و Restart."
  warn ""
  warn "برای دیدن فهرست اپ‌های موجود (بدون نیاز به مفسر):"
  warn "   cat ~/.cpanel/nodevenv/*  2>/dev/null"
  warn "   ls ~/Kaveh185-Back/.htaccess && grep -i passenger ~/Kaveh185-Back/.htaccess"
  warn ""
  warn "استقرار ادامه می‌یابد (فایل‌ها نصب می‌شوند)، ولی تا اصلاح آن،"
  warn "سایت از بیرون دیده نمی‌شود."
  warn "────────────────────────────────────────────────────────────"
fi

step "۲/۸ تهیهٔ بسته"
STAGE="$(mktemp -d "$FRONT_ROOT/.stage.XXXXXX")"
cleanup(){ [[ -d "$STAGE" ]] && rm -rf "$STAGE" || true; }
trap 'cleanup; err "خطا در خط $LINENO — گزارش: $LOG_FILE"' ERR

if [[ -z "$BUNDLE" && -z "$FROM_DIR" && -n "$URL" ]]; then
  BUNDLE="$(mktemp -t k185front.XXXXXX.tar.gz)"
  dim "دریافت: $URL"
  run curl -fsSL --retry 3 --connect-timeout 15 -o "$BUNDLE" "$URL" || die "دریافت بسته شکست خورد"
  # اگر کنار بسته .sha256 باشد، همان‌جا هم می‌گیریم
  if run curl -fsSL --connect-timeout 15 -o "$BUNDLE.sha256" "$URL.sha256" 2>/dev/null; then
    dim "فایل sha256 هم دریافت شد"
  else
    warn "فایل .sha256 کنار بسته نبود — یکتایی محتوا با FILES.sha256 داخل بسته سنجیده می‌شود"
  fi
fi

if [[ -n "$FROM_DIR" ]]; then
  [[ -f "$FROM_DIR/index.html" ]] || die "پوشهٔ داده‌شده index.html ندارد: $FROM_DIR"
  cp -a "$FROM_DIR/." "$STAGE/"
  ok "از پوشه: $FROM_DIR"
elif [[ -n "$BUNDLE" ]]; then
  [[ -f "$BUNDLE" ]] || die "بسته پیدا نشد: $BUNDLE"
  if [[ -f "$BUNDLE.sha256" ]]; then
    expected="$(awk '{print $1}' "$BUNDLE.sha256")"
    actual="$(sha256sum "$BUNDLE" | awk '{print $1}')"
    [[ "$expected" == "$actual" ]] \
      || die "هش بسته نمی‌خواند (انتظار ${expected:0:12} / دریافت ${actual:0:12})"
    ok "sha256 بسته تأیید شد (${actual:0:12})"
  else
    warn "فایل .sha256 کنار بسته نبود — بسته بدون تأیید بایت‌به‌بایت باز می‌شود"
  fi
  # بازکردن امن: هیچ مسیر مطلق و هیچ ..
  if tar -tzf "$BUNDLE" | grep -qE '^/|(^|/)\.\.(/|$)'; then
    die "بسته مسیر ناامن دارد (مطلق یا شامل ..) — رد شد"
  fi
  run tar -xzf "$BUNDLE" -C "$STAGE" --no-same-owner
  ok "بسته باز شد"
else
  die "منبعی مشخص نشده: --url URL یا --bundle PATH یا --from-dir PATH"
fi

step "۳/۸ دروازهٔ محتوا (بی‌هیچ مفسر زبان)"
[[ -f "$STAGE/index.html" ]] || die "محتوای استخراج‌شده index.html ندارد"
for f in index.html 404.html robots.txt manifest.webmanifest BUILD_ID; do
  [[ -f "$STAGE/$f" ]] || die "فایل حیاتی غایب است: $f — بسته با `pnpm pack:front` ساخته نشده"
done
# بارِ RSC: نبودش یعنی هر کلیک داخلی، بارگذاری کامل صفحه است
find "$STAGE" -name 'index.txt' -type f | grep -q . \
  || die "بارِ RSC (index.txt) در بسته نیست — ناوبری داخلی می‌شکند"

# بررسی صحت تک‌تک فایل‌ها با sha256sum — جایگزین خواندن JSON
if [[ -f "$STAGE/FILES.sha256" ]]; then
  if ( cd "$STAGE" && sha256sum -c --quiet FILES.sha256 >/dev/null 2>&1 ); then
    ok "هش $(wc -l < "$STAGE/FILES.sha256" | tr -d ' ') فایل تأیید شد"
  else
    err "بررسی هش ناموفق — فایل‌های خراب:"
    ( cd "$STAGE" && sha256sum -c --quiet FILES.sha256 2>&1 | head -10 ) || true
    die "بستهٔ ناسالم — استقرار متوقف شد"
  fi
else
  warn "FILES.sha256 در بسته نیست — صحت فایل‌ها بررسی نشد"
fi

BUILD_ID="$(cat "$STAGE/BUILD_ID" | tr -d '[:space:]')"
[[ -n "$BUILD_ID" ]] || die "BUILD_ID خالی است"
ROUTE_COUNT="$(wc -l < "$STAGE/ROUTES.txt" 2>/dev/null | tr -d ' ' || echo '?')"
ok "نسخه $BUILD_ID · $ROUTE_COUNT مسیر · $(find "$STAGE" -type f | wc -l | tr -d ' ') فایل"

step "۴/۸ ساخت نسخهٔ تازه"
ID="$(date +%Y%m%d-%H%M%S)"
RELEASE="$RELEASES/$ID"
run mkdir -p "$RELEASE"
run cp -a "$STAGE/." "$RELEASE/"
run find "$RELEASE" -type d -exec chmod 755 {} +
run find "$RELEASE" -type f -exec chmod 644 {} +
run chmod 711 "$FRONT_ROOT" "$RELEASES" 2>/dev/null || true
cleanup
trap 'err "خطا در خط $LINENO — گزارش: $LOG_FILE"' ERR
ok "نسخهٔ $ID آماده شد"

step "۵/۸ اتصال به جنگو"
LINK="$APP_DIR/frontend"
if [[ -d "$LINK" && ! -L "$LINK" ]]; then
  warn "$LINK پوشهٔ واقعی است — پشتیبان گرفته و با پیوند جایگزین می‌شود"
  run mv "$LINK" "$LINK.bak.$(date +%s)"
fi
run ln -sfn "$CURRENT" "$LINK"
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

step "۶/۸ فعال‌سازی اتمی"
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

step "۷/۸ راستی‌آزمایی بیرونی"
dim "انتظار: $BUILD_ID در سرآیند X-Frontend-Build"
fail=0; sleep 3
served="$(served_build || true)"
# ── تطبیق نسخه ───────────────────────────────────────────────────────────
# ⚠️ دو حالت واقعی وجود دارد و اشتباه‌گرفتن‌شان زحمت بی‌جا می‌سازد:
#
#  • پس از `front-deploy.sh` تنها، کد پایتونی که روی هاست است همان
#    `frontend.py` قدیمی است و نسخه را از `BUILD_INFO.json` می‌خواند —
#    که در همین بسته هست. پس تطبیق باید درست باشد.
#  • اگر کد هاست تازه‌تر باشد و `BUILD_ID` را بخواند، همان هم درست است.
#
# چیزی که نباید بشود: سرآیند «unknown» بدهد و ما آن را شکست حساب کنیم.
# «unknown» یعنی فرانت سرو می‌شود ولی کد نسخه را نمی‌شناسد — نه این‌که
# استقرار خراب است. در آن حالت به نشانهٔ دیگری تکیه می‌کنیم: صفحه باید
# HTML باشد و دارایی‌های نسخهٔ تازه با هش خودشان پاسخ ۲۰۰ بدهند.
asset="$(cd "$RELEASE" && ls _next/static/chunks/*.js 2>/dev/null | head -1 || true)"

if [[ "$served" == *"$BUILD_ID"* ]]; then
  ok "ریشهٔ سایت نسخهٔ درست را سرو می‌کند ($served)"
elif [[ -n "$served" && "$served" != "unknown" ]]; then
  warn "سرآیند نسخه '${served:-—}' با بستهٔ تازه ($BUILD_ID) نمی‌خواند"; fail=1
elif [[ -n "$asset" ]]; then
  code="$(http_code "$SITE_URL/$asset")"
  if [[ "$code" == "200" ]]; then
    ok "کد هاست نسخه را گزارش نمی‌کند، ولی دارایی تازه سرو می‌شود (${asset##*/} → 200)"
    dim "برای گزارش نسخه، کد تازهٔ بک‌اند را هم روی هاست نصب کن (install.sh)"
  else
    warn "دارایی تازه ۲۰۰ نداد: $asset → $code"; fail=1
  fi
else
  warn "نه سرآیند نسخه، نه دارایی قابل‌سنجش — راستی‌آزمایی ممکن نشد"; fail=1
fi
for path in / /register/ /rules/ /receipt/; do
  code="$(http_code "$SITE_URL$path")"
  if [[ "$code" == "200" ]]; then ok "$path → 200"; else warn "$path → $code"; fail=1; fi
done
code="$(http_code "$SITE_URL/not-a-real-page/")"
if [[ "$code" == "404" ]]; then ok "مسیر ناشناخته → 404 (نه 200)"; else warn "→ $code"; fail=1; fi
code="$(http_code "$HEALTH_URL")"
if [[ "$code" == "200" ]]; then ok "سلامت API → 200"; else warn "سلامت API → $code"; fail=1; fi

if (( fail )); then
  err "راستی‌آزمایی شکست خورد — بازگشت خودکار"
  if [[ -n "$PREV" && -d "$PREV" ]]; then
    activate "$PREV"; restart_app
    err "به $(basename "$PREV") برگشت داده شد"
  else
    err "نسخهٔ قبلی نبود — current روی نسخهٔ تازه ماند؛ دستی بررسی کنید"
  fi
  exit 1
fi

step "۸/۸ هرس"
CUR="$(readlink -f "$CURRENT")"
n=0
while IFS= read -r d; do
  d="${d%/}"
  [[ "$(realpath "$d")" == "$(realpath "$CUR")" ]] && continue
  n=$((n+1))
  if (( n > KEEP_RELEASES )); then run rm -rf "$d"; dim "حذف: $(basename "$d")"; fi
done < <(ls -1dt "$RELEASES"/*/ 2>/dev/null)
ok "نسخه‌های نگه‌داشته‌شده: $(find "$RELEASES" -maxdepth 1 -mindepth 1 -type d | wc -l | tr -d ' ')"

printf '\n%s%s%s\n' "$B$G" "✔ استقرار کامل شد" "$R"
dim "نسخه: $ID · شناسه: $BUILD_ID"
dim "بازگشت: bash $0 --rollback"
exit 0
