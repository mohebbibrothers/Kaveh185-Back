#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
#  کاوه ۱۸۵ — به‌روزرسانیِ یک‌مرحله‌ایِ دورِ ۱۵  (فرانت + بک‌اند)
#
#  یک فرمان، هفت پرده، بدونِ کارِ دستی:
#     ۱  پیش‌پروازِ شبکه و دسترسی
#     ۲  فرانت: دریافت بستهٔ تازه + تأیید sha256 + انتشار اتمی + ری‌استارت
#     ۳  بک‌اند: git pull + migrate + collectstatic + (گالری) + ری‌استارت
#     ۴  هم‌گام‌سازیِ گالری با بستهٔ فرانتِ نصب‌شده
#     ۵  راستی‌آزماییِ عمیقِ صفحه (نشان/آواتار/یادواره/فوتر/۴۰۴/کتاب)
#     ۶  گزارشِ نسخه‌ها و زمانِ پاسخ
#     ۷  امکانِ بازگشت:  bash kaveh185-update.sh --undo
#
#  اجرا:
#     bash ~/kaveh185-update.sh
#     bash ~/kaveh185-update.sh --check      # فقط بررسی، هیچ تغییری نده
#     bash ~/kaveh185-update.sh --undo       # بازگشت به نسخهٔ فرانتِ قبلی
#     bash ~/kaveh185-update.sh --hard       # استقرارِ کاملِ بک‌اند (بکاپ+وابستگی‌ها)
#
#  ⚠️ این اسکریپت به جز bash/curl/tar/git چیزی لازم ندارد (روی هاست
#     نه Node هست نه python3 آزاد؛ هرچه لازم است در اسکریپت‌های خودِ اپ است).
# ══════════════════════════════════════════════════════════════════════════════
set -Eeuo pipefail

# ── پیکربندی (همه با متغیر محیطی قابل تغییر) ─────────────────────────────────
APP_DIR="${KAVEH185_APP_DIR:-$HOME/Kaveh185-Back}"
SITE_URL="${KAVEH185_SITE_URL:-https://kaveh185.ir}"
API_URL="${KAVEH185_API_URL:-${SITE_URL%/}/api}"
FRONT_DEPLOY="$APP_DIR/deploy/front-deploy.sh"
BACK_DEPLOY="$APP_DIR/deploy/back/back-deploy.sh"
BACK_BRANCH="${KAVEH185_BRANCH:-main}"
EXPECT_FRONT_SHA="${KAVEH185_EXPECT_FRONT_SHA:-6da91e4}"   # دورِ ۱۵
LOG_DIR="${KAVEH185_LOG_DIR:-$HOME/kaveh185-deploy-logs}"
STAMP="$(date +%Y%m%d-%H%M%S)"
LOG="$LOG_DIR/round15-$STAMP.log"
MODE="deploy"

for a in "$@"; do
  case "$a" in
    --check|--dry-run) MODE="check" ;;
    --hard) MODE="hard" ;;
    --undo|--rollback) MODE="undo" ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) printf 'آرگومانِ ناشناخته: %s\n' "$a" >&2; exit 2 ;;
  esac
done

# ── رنگ‌ها و چاپِ خوانا (همه روی stderr تا خروجیِ لوله‌ای تمیز بماند) ────────
R=$'\033[0m'; B=$'\033[1m'; D=$'\033[2m'
G=$'\033[32m'; Y=$'\033[33m'; RD=$'\033[31m'; BL=$'\033[34m'; CY=$'\033[36m'
MK_OK=0; MK_WARN=0; MK_FAIL=0
step(){ printf '\n%s▸ %s%s\n' "$B$BL" "$*" "$R"; }
ok(){   printf '%s✔%s %s\n' "$G" "$R" "$*"; MK_OK=$((MK_OK+1)); }
warn(){ printf '%s▲%s %s\n' "$Y" "$R" "$*"; MK_WARN=$((MK_WARN+1)); }
err(){  printf '%s✖%s %s\n' "$RD" "$R" "$*"; MK_FAIL=$((MK_FAIL+1)); }
dim(){  printf '%s  %s%s\n' "$D" "$*" "$R"; }
die(){  err "$*"; summary; exit 1; }

mkdir -p "$LOG_DIR"

# ── لاگ، بدونِ process substitution ─────────────────────────────────────────
# ⚠️ درسِ گران: روی این هاست (`/dev/fd` ندارد) خطِ
#     exec > >(tee -a "$LOG") 2>&1
# با «/dev/fd/20: No such file or directory» اسکریپت را **پیش از هر کاری**
# می‌کشت. راهِ بی‌دردسر: خودِ اسکریپت را دوباره با `tee` اجرا می‌کنیم؛ هیچ
# وابستگی به /dev/fd یا named pipe نمی‌ماند.
if [[ -z "${K185_UPDATE_LOGGED:-}" ]]; then
  if [[ -r "$0" ]]; then
    export K185_UPDATE_LOGGED=1
    set +e
    bash "$0" "$@" 2>&1 | tee -a "$LOG"
    rc="${PIPESTATUS[0]}"
    set -e
    exit "$rc"
  fi
  warn "اسکریپت از مسیرِ فایل اجرا نشد — لاگ در $LOG ساخته نمی‌شود"
fi

banner(){
  printf '\n%s╔══════════════════════════════════════════════════════════════╗%s\n' "$B$CY" "$R"
  printf '%s║  کاوه ۱۸۵ · به‌روزرسانیِ دورِ ۱۵ — نشانِ شفاف، طاقِ هیرو،     ║%s\n' "$B$CY" "$R"
  printf '%s║  تایمرِ تک‌قاب، یادوارهٔ شهدا، فوترِ تم‌پذیر، ۴۰۴ و کتاب      ║%s\n' "$B$CY" "$R"
  printf '%s╚══════════════════════════════════════════════════════════════╝%s\n' "$B$CY" "$R"
  dim "سایت: $SITE_URL · اپ: $APP_DIR · حالت: $MODE · لاگ: $LOG"
}

summary(){
  printf '\n%s──── جمع‌بندی ────%s\n' "$B" "$R"
  printf '  %s✔ موفق: %d%s   %s▲ هشدار: %d%s   %s✖ خطا: %d%s\n' \
    "$G" "$MK_OK" "$R" "$Y" "$MK_WARN" "$R" "$RD" "$MK_FAIL" "$R"
  if (( MK_FAIL == 0 )); then
    printf '\n  %s✔ آپدیت کامل شد.%s  صفحه را با %sCtrl+Shift+R%s (کشِ سخت) باز کن:\n' "$B$G" "$R" "$B" "$R"
    printf '     %s%s/%s\n\n' "$B" "$SITE_URL" "$R"
  else
    printf '\n  %s✖ آپدیت با خطا تمام شد — لاگ: %s%s\n\n' "$B$RD" "$LOG" "$R"
  fi
}

# ── ابزارهای کوچک ────────────────────────────────────────────────────────────
code(){
  # ⚠️ `curl -w` خودش «000» را چاپ می‌کند و کدِ خروجِ ناموفق برمی‌گرداند؛
  # الگوی `|| echo 000` آن را به «000000» تبدیل می‌کرد و مقایسه‌ها می‌شکست.
  local c
  c="$(curl -s -o /dev/null -m 15 -w '%{http_code}' "$1" 2>/dev/null || true)"
  printf '%s' "${c:-000}"
}
probe(){ # probe URL «توضیح»
  local c; c="$(code "$1")"
  if [[ "$c" == "200" ]]; then ok "$2  ($c)"; else err "$2  ($c)"; fi
}
has(){ # has URL «الگو» «توضیح» — محتوا را می‌گردد
  local body; body="$(curl -fsS -m 20 "$1" 2>/dev/null || true)"
  if printf '%s' "$body" | grep -q -- "$2"; then ok "$3"; else err "$3"; fi
}
sum(){ command -v sha256sum >/dev/null && sha256sum "$1" | cut -d' ' -f1 || echo "—"; }

banner

# ══════════════════════════════════════════════════════════════════════════════
# ۰) بازگشت
# ══════════════════════════════════════════════════════════════════════════════
if [[ "$MODE" == "undo" ]]; then
  step "بازگشت به نسخهٔ فرانتِ قبلی"
  [[ -x "$FRONT_DEPLOY" ]] || [[ -f "$FRONT_DEPLOY" ]] || die "اسکریپت فرانت پیدا نشد: $FRONT_DEPLOY"
  bash "$FRONT_DEPLOY" --rollback || die "بازگشتِ فرانت شکست خورد"
  ok "فرانت به نسخهٔ قبلی برگشت — بک‌اند دست نخورد"
  dim "برای بازگشتِ کدِ بک‌اند:  cd $APP_DIR && git reset --hard HEAD~1 && touch tmp/restart.txt"
  summary; exit 0
fi

# ══════════════════════════════════════════════════════════════════════════════
# ۱) پیش‌پرواز
# ══════════════════════════════════════════════════════════════════════════════
step "۱/۷ · پیش‌پرواز"
for c in curl tar git; do command -v "$c" >/dev/null && ok "$c موجود است" || die "$c نصب نیست"; done
[[ -d "$APP_DIR" ]] || die "پوشهٔ اپ پیدا نشد: $APP_DIR"
[[ -f "$FRONT_DEPLOY" ]] || die "اسکریپت استقرارِ فرانت نیست: $FRONT_DEPLOY"
[[ -f "$BACK_DEPLOY"  ]] || die "اسکریپت استقرارِ بک‌اند نیست: $BACK_DEPLOY"
probe "${SITE_URL%/}/api/v1/health/live/" "سلامتِ لایهٔ وب"
curl -fsS -m 20 -o /dev/null "https://github.com/mohebbibrothers/Kaveh185-Front/releases/latest/download/frontend.tar.gz.sha256" \
  && ok "انتشارِ فرانت در دسترس است" || die "نشانیِ بستهٔ فرانت پاسخ نداد"

if [[ "$MODE" == "check" ]]; then
  step "حالتِ بررسی — هیچ تغییری اعمال نشد"
  probe "${SITE_URL%/}/" "صفحهٔ اول"
  hdr="$(curl -fsSI -m 15 "${SITE_URL%/}/" 2>/dev/null | tr -d '\r' | awk -F': ' 'tolower($1)=="x-frontend-build"{print $2; exit}')"
  dim "نسخهٔ فرانتِ سرو‌شده: ${hdr:-نامعلوم}  (انتظار: شاملِ $EXPECT_FRONT_SHA)"
  summary; exit 0
fi

# ══════════════════════════════════════════════════════════════════════════════
# ۲) فرانت — دریافت، تأیید، انتشارِ اتمی
# ══════════════════════════════════════════════════════════════════════════════
step "۲/۷ · فرانت — بستهٔ تازه"
bash "$FRONT_DEPLOY" || die "استقرارِ فرانت شکست خورد (لاگِ خودش: $HOME/kaveh185-deploy-logs)"
ok "فرانت منتشر شد"

# ══════════════════════════════════════════════════════════════════════════════
# ۳) بک‌اند — کدِ تازه (بدون دانه‌ریزیِ اولیه، با هم‌گام‌سازیِ گالری)
# ══════════════════════════════════════════════════════════════════════════════
step "۳/۷ · بک‌اند — کدِ تازه + مهاجرت + استاتیک + گالری"
if [[ "$MODE" == "hard" ]]; then
  # استقرارِ کامل: بکاپ، نصب وابستگی‌ها، همهٔ بررسی‌ها، بازگشتِ خودکار
  bash "$BACK_DEPLOY" --gallery || die "استقرارِ کاملِ بک‌اند شکست خورد"
else
  # مسیرِ پیش‌فرضِ آپدیت: همان چیزی که برای کد لازم است، سریع و کم‌ریسک
  bash "$BACK_DEPLOY" --prep --gallery || die "به‌روزرسانیِ بک‌اند شکست خورد"
fi
ok "بک‌اند به‌روز شد"
dim "گالری با تصاویرِ بستهٔ فرانتِ همین لحظه هم‌گام شد (seed_gallery --force)"

# ══════════════════════════════════════════════════════════════════════════════
# ۴) راستی‌آزماییِ عمیق
# ══════════════════════════════════════════════════════════════════════════════
# ── دروازهٔ «هیچ چیزی خراب نشود» ─────────────────────────────────────────────
# اگر بیلد یا مهاجرت چیزی را شکسته باشد، این‌جا پیش از ادامه می‌ایستیم و
# از کاربر می‌خواهیم بازگشت بزند — نه این‌که تا آخر برویم و گزارشِ سبز بدهیم.
if [[ "$(code "${SITE_URL%/}/")" != "200" ]]; then
  die "صفحهٔ اول ۲۰۰ نداد — ادامه بی‌معنی است. بازگشت: bash $0 --undo"
fi
if [[ "$(code "${SITE_URL%/}/api/v1/health/ready/")" != "200" ]]; then
  die "API آماده نیست — بازگشت: bash $0 --undo"
fi
ok "دروازه: سایت و API هر دو زنده‌اند — ادامه می‌دهیم"

step "۴/۷ · راستی‌آزماییِ صفحه‌ها"
S="${SITE_URL%/}"
probe "$S/" "صفحهٔ اول"
probe "$S/rules/" "قوانین"
probe "$S/mosques/" "رتبه‌بندی مساجد"
probe "$S/book/" "مطالعهٔ کتاب"
probe "$S/register/" "ثبت‌نام"
probe "$S/api/v1/health/ready/" "آمادگیِ API"

step "۵/۷ · راستی‌آزماییِ دارایی‌ها (نشانِ شفاف و آواتارِ تازه)"
for a in img/emblem-mark.webp img/emblem-avatar.webp img/emblem-head.webp img/punch-fist.webp og.png; do
  probe "$S/$a" "دارایی $a"
done

step "۶/۷ · راستی‌آزماییِ محتوا"
has "$S/" "emblem-avatar" "هدر از آواتارِ شفاف استفاده می‌کند"
has "$S/" "یادوارهٔ شهدا" "نوارِ یادواره در صفحه هست"
has "$S/" "رتبه‌بندی مساجد" "دکمهٔ «رتبه‌بندی مساجد» در هیرو هست"
has "$S/api/v1/gallery/" "martyrs" "API گالری، شهدا را برمی‌گرداند"
gallery_imgs="$(curl -fsS -m 20 "$S/api/v1/gallery/" 2>/dev/null | grep -o 'martyrs/[a-z-]*\.webp' | sort -u | tr '\n' ' ' || true)"
if printf '%s' "$gallery_imgs" | grep -q 'kaveh-portrait.webp'; then
  ok "تصاویرِ نوارِ شهدا با فایل‌های تازه‌اند ($gallery_imgs)"
else
  warn "تصاویرِ نوارِ شهدا هنوز قدیمی‌اند: ${gallery_imgs:-—}"
  warn "دستی: cd $APP_DIR && .venv/bin/python manage.py seed_gallery --force   (یا مسیرِ venv خودت)"
fi
book_file="$(curl -fsS -m 20 "$S/api/v1/exam/book/" 2>/dev/null | grep -o '"/api/v1/exam/book/[^"]*file/"' | tr -d '"' | head -1 || true)"
frame_hdr="$(curl -fsSI -m 15 "$S${book_file:-/api/v1/exam/book/}" 2>/dev/null | tr -d '\r' | awk -F': ' 'tolower($1)=="x-frame-options"{print $2; exit}')"
if [[ "${frame_hdr^^}" == "SAMEORIGIN" ]]; then
  ok "خوانندهٔ کتاب مجاز به قاب‌شدن در دامنهٔ خودی است (SAMEORIGIN)"
else
  warn "X-Frame-Options=$frame_hdr — کدِ تازهٔ بک‌اند روی هاست نیست؟"
fi

step "۷/۷ · گزارشِ نسخه و سرعت"
hdr="$(curl -fsSI -m 15 "$S/" 2>/dev/null | tr -d '\r' | awk -F': ' 'tolower($1)=="x-frontend-build"{print $2; exit}')"
if [[ -n "${hdr:-}" && "${hdr:-unknown}" != "unknown" ]]; then
  if [[ "$hdr" == *"$EXPECT_FRONT_SHA"* ]]; then ok "نسخهٔ فرانتِ سرو‌شده همان دورِ ۱۵ است: $hdr"
  else warn "نسخهٔ سرو‌شده $hdr — انتظار داشتیم شاملِ $EXPECT_FRONT_SHA باشد"; fi
else
  dim "سرآیندِ نسخهٔ فرانت موجود نیست (کدِ بک‌اندِ هاست تازه نیست) — محتوا تأیید شد."
fi
dim "نسخهٔ کدِ بک‌اند: $(cd "$APP_DIR" && git log -1 --pretty='%h %s' 2>/dev/null | cut -c1-70)"
t="$(curl -s -o /dev/null -m 30 -w '%{time_total}' "$S/" 2>/dev/null || echo '—')"
dim "زمانِ پاسخِ صفحهٔ اول: ${t}s"
dim "بیلدِ نصب‌شده: $(readlink -f "$HOME/kaveh185-front/current" 2>/dev/null | xargs -r basename)"

summary
(( MK_FAIL == 0 )) || exit 1
