#!/usr/bin/env bash
set -euo pipefail
# Выпускает сертификат, когда A-запись уже видна миру.
if ! getent hosts bukergo.ru | grep -q 5.45.112.180; then
  echo "bukergo.ru ещё не резолвится в 5.45.112.180 — позже"
  getent hosts bukergo.ru || true
  exit 2
fi
certbot --nginx --non-interactive --agree-tos \
  -d bukergo.ru -d www.bukergo.ru \
  -d bookergo.ru -d www.bookergo.ru \
  -d bukergo.online -d www.bukergo.online \
  -m "${BOOKER_LETSENCRYPT_EMAIL:-webmaster@bukergo.ru}" --redirect
echo "HTTPS готов"
