#!/usr/bin/env bash
set -euo pipefail
# Выпускает сертификат, когда A-запись уже видна миру.
if ! getent hosts bukergo.ru | grep -q 5.45.112.180; then
  echo "bukergo.ru ещё не резолвится в 5.45.112.180 — позже"
  getent hosts bukergo.ru || true
  exit 2
fi
certbot --nginx -d bukergo.ru --non-interactive --agree-tos \
  -m "${BOOKER_LETSENCRYPT_EMAIL:-webmaster@bukergo.ru}" --redirect
echo "HTTPS готов"
