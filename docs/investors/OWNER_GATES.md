# Owner gates — Wave G (чеклист владельца)

Вне кода. Без этого **уровень 3 (live-деньги)** не «включается конфигом честно».

## 1. OPERATOR

- [ ] Заполнить все поля [docs/legal/OPERATOR.md](../legal/OPERATOR.md)
- [ ] Убрать плейсхолдеры `[…]` перед публичным переносом в оферту
- [ ] Email ПДн, телефон, ДПО, статус РКН

## 2. OWNER_INPUTS

- [ ] Юрблок: наименование, ИНН, ОГРН, адреса (`docs/OWNER_INPUTS.md`)
- [ ] `SUPPORT_EMAIL` / `PRIVACY_EMAIL` / `SECURITY_EMAIL`
- [ ] Платёжные секреты — только systemd / vault, не git
- [ ] `LAWYER_APPROVAL_DATE`, `PAYMENT_FLOW_APPROVAL` после юриста

## 3. Юрист

- [ ] Назначить по [LAWYER_BRIEF.md](../legal/LAWYER_BRIEF.md)
- [ ] Пакет: оферта, ПДн, возвраты/споры, cancellation
- [ ] Дата утверждения зафиксирована

## 4. Платёжный партнёр

- [ ] Выбрать 1 из [PAYMENTS_SHORTLIST.md](../legal/PAYMENTS_SHORTLIST.md)
- [ ] Черновик term sheet / оферта партнёра
- [ ] Ключи + webhook secret в prod
- [ ] Путь: сейчас `external` → live по [PAYMENTS_PATH.md](PAYMENTS_PATH.md)

## 5. Traction

- [ ] 5–10 design-partner сделок (хотя бы external-paid)
- [ ] Обновить [METRICS_SNAPSHOT.md](METRICS_SNAPSHOT.md) фактическими цифрами (не только seed)

## После G

Включить live-адаптер выбранного партнёра, сверку, снять баннер draft — **без** смены UX Deal Room.
