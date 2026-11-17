#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
#  کاوه ۱۸۵ — اجرای `manage.py` با همان مفسری که اپ با آن اجرا می‌شود
#
#  چرا؟ روی این هاست نسخهٔ پایتونِ virtualenv می‌تواند 3.12 یا 3.13 باشد و
#  مسیرش هم همیشه یکی نیست. به‌جای اینکه هر بار دستی مسیر را حدس بزنیم:
#
#      ./deploy/run-manage.sh seed_gallery --force
#      ./deploy/run-manage.sh migrate
#      ./deploy/run-manage.sh showmigrations --plan
#
#  ترتیبِ جست‌وجو: KAVEH185_VENV → هر venv موجود در ~/virtualenv/Kaveh185-Back/*.
# ══════════════════════════════════════════════════════════════════════════════
set -Eeuo pipefail
APP_DIR="${KAVEH185_APP_DIR:-$HOME/Kaveh185-Back}"

pick_python() {
  if [[ -n "${KAVEH185_VENV:-}" && -x "$KAVEH185_VENV/bin/python" ]]; then
    printf '%s' "$KAVEH185_VENV/bin/python"; return 0
  fi
  local d
  for d in "$HOME"/virtualenv/Kaveh185-Back/*/; do
    [[ -x "${d}bin/python" ]] && { printf '%s' "${d}bin/python"; return 0; }
  done
  command -v python3 || command -v python
}

PY="$(pick_python)"
[[ -n "${PY:-}" ]] || { echo "✖ مفسرِ پایتون پیدا نشد" >&2; exit 1; }
cd "$APP_DIR"
exec "$PY" manage.py "$@"
