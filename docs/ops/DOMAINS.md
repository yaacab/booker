# Домены Букер (Reg.ru)

Куплено до 18.08.2027. Сайт в панели «не подключён» — это нормально, пока нет A-записей на сервер.

## Схема

| Домен | Роль |
|-------|------|
| **bukergo.ru** | Канон. Публичный сайт и кабинет |
| www.bukergo.ru | 301 → https://bukergo.ru |
| **bookergo.ru** (+ www) | 301 → https://bukergo.ru (латинский дубль) |
| **bukergo.online** (+ www) | 301 → https://bukergo.ru |

Не подключать конструктор / «хостинг Reg.ru» — иначе NS уедут на витрину регистратора и наш nginx не получит трафик.

## DNS в Reg.ru

Домены → выбрать домен → **DNS-серверы и зона** (или «Управление зоной»).

Для **каждого** из трёх доменов:

| Тип | Хост | Значение | TTL |
|-----|------|----------|-----|
| A | `@` | `5.45.112.180` | 300 |
| A | `www` | `5.45.112.180` | 300 |

IP — текущий VPS (тот же, что Белый Путь). Букер висит на **другом** `server_name`, пути THE AIV не трогаем.

После сохранения в зоне Reg.ru имя ещё должно появиться в корне `.ru` (RIPN). Это **не TTL 300**: обычно **от нескольких часов до суток**. Пока `dig bukergo.ru` с телефона/другого интернета даёт NXDOMAIN — браузер имя не откроет, HTTPS выпускать рано.

Проверка с ноутбука:

```bash
dig +short bukergo.ru A
dig +short bookergo.ru A
dig +short bukergo.online A
curl -sI http://bukergo.ru | head -5
```

## SSL

Когда A уже указывает на VPS:

```bash
certbot --nginx -d bukergo.ru -d www.bukergo.ru \
  -d bookergo.ru -d www.bookergo.ru \
  -d bukergo.online -d www.bukergo.online
```

Конфиг: `infra/nginx/bukergo.ru.conf`. На VPS: `/opt/booker`, systemd `booker-api` / `booker-web`, nginx `sites-enabled/bukergo.ru.conf`. HTTPS — certbot, когда RIPN опубликует зону `.ru` (пока NXDOMAIN с корня).

## Не делать

- Разные сайты на трёх доменах в MVP (дубли SEO, три сертификата в голове).
- MX/почта, пока нет своей почты — не включать «почту Reg.ru», если не нужна.
- Деплой приложения на эти домены без явной команды (DNS можно прописать заранее).
