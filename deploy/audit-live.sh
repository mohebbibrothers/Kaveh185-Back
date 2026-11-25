#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
#  کاوه ۱۸۵ — معاینهٔ سریعِ سایت، روی هاست، بدونِ هیچ نصبِ تازه
#
#      bash ~/Kaveh185-Back/deploy/audit-live.sh
#
#  چه می‌کند: ۶ لایه را می‌سنجد (لایو، آمادگی، صفحه‌ها، دادهٔ آزمون، یکپارچگی،
#  وضعیتِ دیتابیس) و در پایان یک خطِ جمع‌بندی می‌دهد. فقط‌خواندنی است.
# ══════════════════════════════════════════════════════════════════════════════
set -Eeuo pipefail

APP_DIR="${KAVEH185_APP_DIR:-$HOME/Kaveh185-Back}"
PY="${PY:-$HOME/virtualenv/Kaveh185-Back/3.12/bin/python}"

if [[ ! -x "$PY" ]]; then
  for cand in "$HOME"/virtualenv/*/*/bin/python; do
    [[ -x "$cand" ]] && PY="$cand" && break
  done
fi

[[ -x "$PY" ]] || { echo "✖ پایتونِ محیطِ مجازی پیدا نشد. PY=/path/to/python را ست کنید." >&2; exit 1; }
[[ -f "$APP_DIR/manage.py" ]] || { echo "✖ ریشهٔ جنگو پیدا نشد: $APP_DIR" >&2; exit 1; }

cd "$APP_DIR"
# shellcheck disable=SC1091
[[ -f .env ]] && { set -a; . ./.env; set +a; }
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings.production}"

# ── مسیرِ صفحهٔ رتبه‌بندی (منبعِ یک ۴۰۴ِ واقعی) ───────────────────────────
echo
"$PY" manage.py check_ranking_page || echo "  ▲ صفحهٔ رتبه‌بندی مشکل دارد (بالا را ببینید)"

echo
exec "$PY" manage.py shell < scripts/audit_live.py
