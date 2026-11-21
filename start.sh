#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi
if [ ! -x .venv/bin/python ]; then
  if command -v python3.12 >/dev/null 2>&1; then python3.12 -m venv .venv; else python3 -m venv .venv; fi
fi
if [ ! -f .venv/.tail-deps ] || [ requirements.txt -nt .venv/.tail-deps ] || [ requirements-providers.txt -nt .venv/.tail-deps ]; then
  .venv/bin/python -m pip install -r requirements.txt
  touch .venv/.tail-deps
fi
if [ ! -d web/node_modules ] || [ web/package-lock.json -nt web/node_modules/.package-lock.json ]; then
  (cd web && npm ci)
fi
if [ ! -f web/dist/index.html ] || [ -n "$(find web/src web/public web/scripts web/index.html web/package.json web/package-lock.json web/vite.config.ts -type f -newer web/dist/index.html -print 2>/dev/null | head -1)" ]; then
  (cd web && npm run build)
fi
if [ "${PET_PAYMENT_MODE:-demo}" = demo ] && [ "${PET_MODEL_MODE:-demo}" = demo ] && [ "${PET_IMAGE_MODE:-demo}" = demo ] && [ -z "${DATABASE_URL:-}" ]; then
  .venv/bin/python -m scripts.local_admin
fi
exec .venv/bin/python -m uvicorn server.app:app --host 127.0.0.1 --port "${PORT:-8000}"
