# Путь платежей: stub → external → live

Слой `PaymentProvider` + webhooks + идемпотентность. Букер **не** эскроу-банк. CONTRACT: до U5 — stub или **external**.

## 1. `stub`

- CI / локальная разработка.
- Не показывать инвестору как «оплату».

## 2. `external` (diligence / concierge)

- `BOOKER_PAYMENT_PROVIDER=external`.
- Платёж `Pending`, метод off-platform; подтверждение **только** admin/concierge + audit.
- UI: оплата вне платформы; без «гарант / эскроу / страхование».
- Webhook партнёра не принимается.

## 3. Live (после Wave G)

1. Заполнены `docs/legal/OPERATOR.md` и критичные поля `docs/OWNER_INPUTS.md`.
2. Юрист: `LAWYER_APPROVAL_DATE`, оферта/возвраты/ПДн.
3. Партнёр из `docs/legal/PAYMENTS_SHORTLIST.md` + ключи в systemd.
4. Адаптер за флагом, webhook verify, сверка, 54-ФЗ.
5. Снять баннер draft legal.

**Инвариант:** Deal Room / quote / hold не переписываются при включении live — только провайдер и юргейты.
