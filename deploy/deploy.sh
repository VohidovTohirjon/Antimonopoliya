#!/usr/bin/env bash
# Ilova qatlamini (PostgreSQL + FastAPI + Nginx) ishga tushiradi.
#
# vLLM va model yuklab olish BU SKRIPTGA KIRMAYDI: ular GPU'ni to'g'ridan-to'g'ri
# ishlatadi va host'da systemd orqali alohida o'rnatiladi (deploy/README.md).
#
# Hech qanday parol yoki token bu yerda saqlanmaydi.
set -euo pipefail

cd "$(dirname "$0")/.."
COMPOSE="docker compose"

log() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
fail() { printf '\n\033[31mXATO: %s\033[0m\n' "$*" >&2; exit 1; }

# --- 1. .env tekshiruvi -------------------------------------------------------
[ -f .env ] || fail ".env topilmadi. Namuna: cp .env.production.example .env"

missing=()
for key in APP_ENV SECRET_KEY POSTGRES_PASSWORD LLM_PROVIDER LOCAL_LLM_BASE_URL LOCAL_LLM_MODEL; do
    grep -qE "^${key}=.+" .env || missing+=("$key")
done
[ ${#missing[@]} -eq 0 ] || fail ".env da quyidagilar to'ldirilmagan: ${missing[*]}"

grep -qE '^APP_ENV=production$'   .env || fail "Production uchun APP_ENV=production bo'lishi kerak"
grep -qE '^LLM_PROVIDER=local$'   .env || fail "Bu deploy lokal vLLM uchun: LLM_PROVIDER=local"
awk -F= '/^SECRET_KEY=/{ if (length($2) < 32) exit 1 }' .env || fail "SECRET_KEY kamida 32 belgi bo'lishi kerak"

# --- 2. host'dagi vLLM yetib boradimi? ---------------------------------------
VLLM_URL="$(grep -E '^LOCAL_LLM_BASE_URL=' .env | cut -d= -f2-)"
VLLM_MODEL="$(grep -E '^LOCAL_LLM_MODEL=' .env | cut -d= -f2-)"
HOST_PROBE="${VLLM_URL/host.docker.internal/127.0.0.1}"
log "vLLM tekshirilmoqda: ${HOST_PROBE}/models"
if curl -fsS --max-time 10 "${HOST_PROBE}/models" | grep -q "$VLLM_MODEL"; then
    echo "    vLLM javob berdi va '${VLLM_MODEL}' yuklangan."
else
    echo "    OGOHLANTIRISH: vLLM javob bermadi yoki model yuklanmagan."
    echo "    Ilova baribir ishga tushadi (deterministik yo'llar LLMsiz ishlaydi),"
    echo "    lekin generativ javoblar vLLM tayyor bo'lgunicha ishlamaydi."
    echo "    Tekshiring: systemctl status vllm"
fi

# --- 3. build va ishga tushirish ---------------------------------------------
log "Docker образлар quriladi"
$COMPOSE build

log "PostgreSQL ishga tushirilmoqda"
$COMPOSE up -d db
until $COMPOSE exec -T db pg_isready -q; do sleep 2; done
echo "    PostgreSQL tayyor."

log "Migratsiyalar (0001 -> head)"
$COMPOSE run --rm --no-deps backend alembic upgrade head

log "Backend, frontend va Nginx ishga tushirilmoqda"
$COMPOSE up -d

# --- 4. sog'liq tekshiruvi ----------------------------------------------------
log "Backend sog'ligi kutilmoqda (BGE-M3 birinchi yuklanishi bir necha daqiqa)"
for _ in $(seq 1 60); do
    if curl -fsS --max-time 5 http://127.0.0.1/api/health >/dev/null 2>&1; then
        curl -sS http://127.0.0.1/api/health; echo
        log "Tayyor. Keyingi qadamlar:"
        echo "  1) Administrator:  docker compose exec -e ADMIN_PASSWORD='<parol>' backend \\"
        echo "       sh -c 'python -m app.cli --username admin --password \"\$ADMIN_PASSWORD\"'"
        echo "  2) Huquqiy korpus: docker compose exec backend python scripts/import_nhh.py --admin-username admin"
        echo "  3) Tekshirish:     docker compose exec backend python scripts/import_nhh.py --status"
        exit 0
    fi
    sleep 10
done
fail "Backend 10 daqiqada sog'lom bo'lmadi. Loglar: docker compose logs backend"
