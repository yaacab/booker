#!/usr/bin/env bash
set -euo pipefail
# Ждёт, пока публичный DNS отдаст A 5.45.112.180 для bukergo.ru.
HOST="${1:-bukergo.ru}"
EXPECT="${2:-5.45.112.180}"
for i in $(seq 1 20); do
  ip="$(getent ahostsv4 "$HOST" 2>/dev/null | awk '{print $1; exit}')"
  echo "попытка ${i}: ${HOST} → ${ip:-нет}"
  if [[ "${ip}" == "${EXPECT}" ]]; then
    echo "DNS готов"
    exit 0
  fi
  sleep 30
done
echo "ещё NXDOMAIN или чужой IP — обычно часы, редко сутки после делегирования .ru"
exit 2
