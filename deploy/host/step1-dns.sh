#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
#  کاوه ۱۸۵ — گام ۱: ساخت رکورد DNS برای api.kaveh185.ir  (کاملاً از ترمینال)
#
#  اجرا روی هاست (cPanel → Terminal  یا  SSH):
#      bash ~/Kaveh185-Back/deploy/host/step1-dns.sh
#
#  گزینه‌ها:
#      --zone kaveh185.ir   (پیش‌فرض)
#      --name api           (پیش‌فرض) — زیردامنه‌ای که ساخته می‌شود
#      --ip 1.2.3.4         (پیش‌فرض: تشخیص خودکار IP عمومی هاست)
#      --dry-run            فقط نشان بده، چیزی نساز
# ══════════════════════════════════════════════════════════════════════════════
set -uo pipefail

ZONE="kaveh185.ir"; NAME="api"; IP=""; DRY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --zone) ZONE="$2"; shift ;;
    --name) NAME="$2"; shift ;;
    --ip)   IP="$2"; shift ;;
    --dry-run) DRY=1 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "آرگومان ناشناخته: $1"; exit 2 ;;
  esac; shift
done

R=$'\033[0m'; B=$'\033[1m'; DG=$'\033[2m'; G=$'\033[32m'; Y=$'\033[33m'; RD=$'\033[31m'; BL=$'\033[34m'
ok(){ printf '%s✔%s %s\n' "$G" "$R" "$*"; }
wr(){ printf '%s▲%s %s\n' "$Y" "$R" "$*"; }
er(){ printf '%s✖%s %s\n' "$RD" "$R" "$*"; }
if_(){ printf '%s•%s %s\n' "$BL" "$R" "$*"; }
hd(){ printf '\n%s%s▸ %s%s\n' "$B" "$R" "$*" ""; }

FQDN="$NAME.$ZONE"

# ── ۰) ابزارها ──────────────────────────────────────────────────────────────
hd "۰/۴ · بررسی ابزارهای موجود"
HAVE_UAPI=0; command -v uapi >/dev/null 2>&1 && HAVE_UAPI=1
HAVE_WHM=0;  command -v whmapi1 >/dev/null 2>&1 && HAVE_WHM=1
HAVE_CURL=0; command -v curl >/dev/null 2>&1 && HAVE_CURL=1
if_ "uapi: $([[ $HAVE_UAPI -eq 1 ]] && echo 'بله' || echo 'خیر')  ·  whmapi1: $([[ $HAVE_WHM -eq 1 ]] && echo 'بله' || echo 'خیر')  ·  curl: $([[ $HAVE_CURL -eq 1 ]] && echo 'بله' || echo 'خیر')"
if [[ $HAVE_UAPI -eq 0 && $HAVE_WHM -eq 0 ]]; then
  er "هیچ‌کدام از uapi/whmapi1 در دسترس نیست — این هاست اجازهٔ تغییر DNS از ترمینال را نمی‌دهد."
  wr "اسکریپت ادامه می‌دهد تا حداقل IP و مقادیر لازم را چاپ کند."
fi

# ── ۱) تشخیص IP عمومی هاست ───────────────────────────────────────────────────
hd "۱/۴ · IP عمومی هاست"
if [[ -z "$IP" ]]; then
  if [[ $HAVE_CURL -eq 1 ]]; then
    for u in https://api.ipify.org https://ifconfig.me/ip https://icanhazip.com; do
      cand="$(curl -4 -fsS -m 8 "$u" 2>/dev/null | tr -d '[:space:]' || true)"
      if [[ "$cand" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]]; then IP="$cand"; break; fi
    done
  fi
fi
if [[ -z "$IP" ]]; then
  # تلاش با ابزارهای محلی
  IP="$( (hostname -I 2>/dev/null | awk '{print $1}') || true)"
fi
if [[ -z "$IP" ]]; then
  er "IP را نتوانستم تشخیص دهم. دستی بده:  bash $0 --ip <IP هاست>"
  exit 3
fi
ok "IP عمومی: $IP"

# ── ۲) بررسی اینکه zone روی همین cPanel است یا نه ───────────────────────────
hd "۲/۴ · بررسی مالکیت zone"
ZONE_HERE=0
if [[ $HAVE_UAPI -eq 1 ]]; then
  out="$(uapi --output=json DNS parse_zone zone="$ZONE" 2>/dev/null || true)"
  # uapi یک پاکت JSON برمی‌گرداند: result.status=1 یعنی موفق. برای zone موجود،
  # فیلد data آرایه‌ای از رکوردهاست. هر دو حالت را تشخیص می‌دهیم.
  if [[ "$out" == *'"status":1'* || "$out" == *'"status": 1'* ]]; then ZONE_HERE=1; fi
  if [[ "$out" == *'"errors":[]'* && "$out" == *'"data"'* ]]; then ZONE_HERE=1; fi
  if [[ $ZONE_HERE -eq 1 ]]; then
    ok "zone «$ZONE» روی همین cPanel مدیریت می‌شود"
    # آیا رکورد از قبل هست؟
    if [[ "$out" == *"$NAME"* ]]; then
      wr "به‌نظر می‌رسد رکورد «$NAME» از قبل وجود دارد — بررسی می‌کنیم."
    fi
  else
    wr "این cPanel مالک zone نیست (یا uapi اجازه ندارد) — احتمالاً DNS دامنه دست ثبت‌کننده است."
  fi
else
  wr "uapi نیست — نمی‌توانم مالکیت zone را بررسی کنم."
fi

# ── ۳) ساخت رکورد ───────────────────────────────────────────────────────────
hd "۳/۴ · ساخت رکورد A"
MADE=0
if [[ $DRY -eq 1 ]]; then
  wr "[dry-run] رکورد ساخته نشد. دستوری که اجرا می‌شد:"
  printf '    uapi DNS add_zone_record zone=%s type=A name=%s address=%s ttl=1440\n' "$ZONE" "$NAME" "$IP"
elif [[ $HAVE_UAPI -eq 1 && $ZONE_HERE -eq 1 ]]; then
  if_ "اجرای uapi DNS add_zone_record ..."
  if uapi --output=json DNS add_zone_record zone="$ZONE" type=A name="$NAME" address="$IP" ttl=1440 >/tmp/.k185_dns_out 2>&1; then
    MADE=1; ok "رکورد A ساخته شد"
  else
    wr "uapi قبول نکرد. خروجی:"
    sed 's/^/    /' /tmp/.k185_dns_out | head -12
    wr "ممکن است رکورد از قبل وجود داشته باشد. اگر وجود دارد، فقط مقدارش را چک کن:"
    printf '    uapi --output=json DNS parse_zone zone=%s | grep -A4 %s\n' "$ZONE" "$NAME"
  fi
else
  wr "ساخت خودکار ممکن نیست؛ مقادیر زیر را در Zone Editor ثبت کن:"
  printf '    %sType%s : A\n    %sName%s : %s\n    %sRecord%s : %s\n    %sTTL%s : 1440\n' \
    "$B" "$R" "$B" "$R" "$NAME" "$B" "$R" "$IP" "$B" "$R"
fi

# ── ۴) تأیید ────────────────────────────────────────────────────────────────
hd "۴/۴ · تأیید"
resolved=""
if [[ $DRY -eq 1 ]]; then
  wr "[dry-run] مرحلهٔ تأیید رد شد (چیزی ثبت نشده)"
  resolved=""
elif [[ -z "${resolved_pre:-}" ]]; then
  resolved=""
fi
resolved_pre="skip"
for t in 1 2 3 4 5 6 7 8; do
  [[ $DRY -eq 1 ]] && break
  if command -v dig >/dev/null 2>&1; then
    resolved="$(dig +short A "$FQDN" @1.1.1.1 2>/dev/null | tail -1)"
  elif command -v host >/dev/null 2>&1; then
    resolved="$(host -t A "$FQDN" 2>/dev/null | awk '/has address/{print $4; exit}')"
  else
    resolved="$(python3 - <<PY 2>/dev/null
import socket
try: print(socket.gethostbyname("$FQDN"))
except Exception: pass
PY
)"
  fi
  [[ -n "$resolved" ]] && break
  printf '%s  مقاومت %s/8 — هنوز propagate نشده...\n' "$DG" "$t"
  sleep 10
done

if [[ "$resolved" == "$IP" ]]; then
  ok "$FQDN → $resolved  (درست است)"
elif [[ $DRY -eq 1 ]]; then
  :
elif [[ -n "$resolved" ]]; then
  wr "$FQDN → $resolved  (با IP موردانتظار $IP فرق دارد)"
else
  wr "$FQDN هنوز resolve نمی‌شود — تا ۳۰ دقیقه پس از ثبت رکورد طبیعی است"
fi

printf '\n%s%s════════ خروجی برای ارسال به تیم فرانت ════════%s\n' "$B" "" "$R"
printf 'FQDN=%s\n' "$FQDN"
printf 'IP=%s\n' "$IP"
printf 'ZONE_ON_CPANEL=%s\n' "$([[ $ZONE_HERE -eq 1 ]] && echo yes || echo no)"
printf 'RECORD_MADE_BY_SCRIPT=%s\n' "$([[ $MADE -eq 1 ]] && echo yes || echo no)"
printf 'RESOLVED=%s\n' "${resolved:-none}"
printf '%s════════════════════════════════════════════════════════════════%s\n' "$B" "$R"
