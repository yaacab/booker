# REL-STAGING-HOST — intake после OWN-STAGING-GO · 2026-11-05

`OWN-STAGING-GO` записан. Для `REL-STAGING-HOST` DONE нужны **значения**, не ещё один GO.

## Запрещено

- IP production FastVPS `5.45.112.180`
- Cloud.ru `87.242.86.210` (wl-relay / AIV, не Buker staging)
- Деплой на prod «временно как staging»

## Нужно от владельца (заполнить)

```text
STAGING_VPS_IP=
STAGING_SSH_USER=
STAGING_SSH_PORT=22
STAGING_SSH_KEY_PATH=   # или способ передачи ключа агенту без коммита в git
DNS: staging.bukergo.ru → STAGING_VPS_IP (A/AAAA)
OS/образ: 
Регион РФ (152-ФЗ): yes/no
```

## После заполнения агент делает

1. SSH probe + fail-closed preflight.  
2. DNS check `staging.bukergo.ru`.  
3. Поднять staging package (без production secrets).  
4. Evidence → `REL-STAGING-HOST` DONE; затем T09/P06/O05 по факту.

## Пока пусто

Задача остаётся TODO. Локальный V07/API не заменяют staging host.
