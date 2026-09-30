"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api, getActiveOrg, getToken, trackClientEvent } from "@/lib/api";
import { money } from "@/lib/format";
import { loginHref } from "@/lib/next";
import { AUDIENCES, commerceError, commerceHref, feePercent, ORDER_STATUS,
  type Audience, type BillingOrder, type CommerceCatalog, type CommerceMe, type CommerceState } from "@/lib/commerce";

const INTROS: Record<Audience, string> = {
  artist: "Профиль, календарь и сделки — с первого дня. Добавляйте инструменты, когда готовы расти.",
  venue: "Работайте с запросами на ваши залы. Расширяйте аналитику и возможности команды вместе с площадкой.",
  customer: "Организуйте личные события бесплатно. Business объединяет инструменты профессиональной команды.",
};

export function PricingClient() {
  const [catalog, setCatalog] = useState<CommerceCatalog | null>(null);
  const [me, setMe] = useState<CommerceMe | null>(null);
  const [audience, setAudience] = useState<Audience>("artist");
  const [annual, setAnnual] = useState(false);
  const [orgId, setOrgId] = useState("");
  const [current, setCurrent] = useState<CommerceState | null>(null);
  const [order, setOrder] = useState<BillingOrder | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const [authed, setAuthed] = useState(false);
  const requestKeys = useRef<Record<string, string>>({});

  useEffect(() => {
    const controller = new AbortController();
    setError("");
    void api<CommerceCatalog>("/commerce/catalog", { signal: controller.signal })
      .then(setCatalog).catch((e) => { if (!controller.signal.aborted) setError(commerceError(e)); });
    const authenticated = Boolean(getToken());
    setAuthed(authenticated);
    if (authenticated) void api<CommerceMe>("/me", { signal: controller.signal }).then((data) => {
      setMe(data);
      const org = data.organizations.find((o) => o.id === (getActiveOrg() || data.active_organization_id)) || data.organizations[0];
      if (org) { setAudience(org.kind); setOrgId(org.id); }
    }).catch((e) => { if (!controller.signal.aborted) setError(commerceError(e)); });
    trackClientEvent("pricing.viewed");
    return () => controller.abort();
  }, [revision]);

  useEffect(() => {
    setCurrent(null);
    if (!orgId) return;
    const controller = new AbortController();
    void api<CommerceState>(`/commerce/organizations/${orgId}`, { signal: controller.signal })
      .then(setCurrent).catch((e) => { if (!controller.signal.aborted) setError(commerceError(e)); });
    return () => controller.abort();
  }, [orgId, revision]);

  function changeAudience(value: Audience) {
    setAudience(value); setOrder(null); setError("");
    setOrgId(me?.organizations.find((org) => org.kind === value)?.id || "");
  }

  async function choose(code: string) {
    if (!orgId || busy) return;
    setBusy(true); setError("");
    const key = `${orgId}:${code}:${annual}`;
    requestKeys.current[key] ||= crypto.randomUUID();
    try {
      const result = await api<BillingOrder>(`/commerce/organizations/${orgId}/orders`, {
        method: "POST", body: JSON.stringify({ plan_code: code, billing_period: annual ? "annual" : "monthly", idempotency_key: requestKeys.current[key] }),
      });
      setOrder(result);
    } catch (e) { setError(commerceError(e)); }
    finally { setBusy(false); }
  }

  async function completeTest() {
    if (!order || busy) return;
    setBusy(true); setError("");
    try {
      await api(`/commerce/orders/${order.id}/test-complete`, { method: "POST", body: JSON.stringify({ status: "paid" }) });
      setOrder(await api<BillingOrder>(`/commerce/orders/${order.id}`));
      setCurrent(await api<CommerceState>(`/commerce/organizations/${orgId}`));
    } catch (e) { setError(commerceError(e)); }
    finally { setBusy(false); }
  }

  const plans = catalog?.plans.filter((p) => p.audience === audience) || [];
  const orgs = me?.organizations.filter((org) => org.kind === audience) || [];
  return <main className="commerce-page">
    <header className="commerce-intro">
      <p className="kicker">Букер · Тарифы</p>
      <h1>Больше возможностей<br />для ваших событий</h1>
      <p className="timeline">{INTROS[audience]}</p>
    </header>
    <div className="commerce-controls">
      <div className="tabs" role="group" aria-label="Для кого тариф">
        {AUDIENCES.map((item) => <button type="button" key={item.code} className={`tab ${item.code === audience ? "on" : ""}`} aria-pressed={item.code === audience} onClick={() => changeAudience(item.code)}>{item.label}</button>)}
      </div>
      <div className="tabs" role="group" aria-label="Период оплаты">
        <button type="button" className={`tab ${!annual ? "on" : ""}`} aria-pressed={!annual} onClick={() => setAnnual(false)}>За месяц</button>
        <button type="button" className={`tab ${annual ? "on" : ""}`} aria-pressed={annual} onClick={() => setAnnual(true)}>За год</button>
      </div>
    </div>
    {orgs.length > 0 && <label className="commerce-org">Для организации<select value={orgId} onChange={(event) => { setOrgId(event.target.value); setOrder(null); }}>
      {orgs.map((org) => <option key={org.id} value={org.id}>{org.name}</option>)}
    </select></label>}
    {error && <div role="alert" className="card"><p>{error}</p><button className="btn secondary" type="button" onClick={() => setRevision((r) => r + 1)}>Повторить загрузку</button></div>}
    {!catalog && !error && <p role="status">Загружаем тарифы…</p>}
    {catalog && plans.length === 0 && <p className="empty">Тарифы для этой роли пока недоступны.</p>}
    <div className="commerce-plans">
      {plans.map((plan) => {
        const isFree = plan.monthly_price_rub === 0;
        const isCurrent = current?.plan.code === plan.code;
        const price = annual ? plan.annual_price_rub : plan.monthly_price_rub;
        return <article key={plan.code} className={`card commerce-plan ${plan.sort_order === 1 ? "tint" : ""}`} aria-label={`Тариф ${plan.title}`}>
          <div className="commerce-plan-top"><h2>{plan.title}</h2>{isCurrent && <span className="chip">Ваш тариф</span>}</div>
          <p className="commerce-price">{money(price)}<span>{isFree ? "без подписки" : annual ? "за год" : "в месяц"}</span></p>
          {annual && plan.annual_savings_rub > 0 && <p className="commerce-saving">Экономия {money(plan.annual_savings_rub)} за год</p>}
          <p>{audience === "customer" ? "Сервисный сбор" : "Комиссия с гонорара"} <strong>{feePercent(audience === "customer" ? plan.customer_fee_bps : plan.supplier_fee_bps)}</strong></p>
          {audience !== "customer" && <p className="timeline">Заказчик отдельно оплачивает сервисный сбор {feePercent(plan.customer_fee_bps)}.</p>}
          <ul className="commerce-feature-list">{Object.entries(plan.features).filter(([, value]) => value !== false && value !== 0).map(([code, value]) => <li key={code}>{plan.feature_labels[code]}{typeof value === "number" ? `: ${value}` : ""}</li>)}</ul>
          <div className="commerce-plan-action">
            {isFree ? <Link className="btn secondary" href={authed ? commerceHref(audience) : loginHref("/pricing")}>Начать бесплатно</Link> : !authed ? <Link className="btn" href={loginHref("/pricing")}>Выбрать тариф</Link> : !orgId ? <Link className="btn secondary" href="/profile">Создать рабочее пространство</Link> : <button className="btn" type="button" disabled={busy || !current?.can_manage || isCurrent} onClick={() => void choose(plan.code)}>{isCurrent ? "Тариф действует" : busy ? "Сохраняем…" : "Выбрать тариф"}</button>}
          </div>
        </article>;
      })}
    </div>
    {order && <section className="card commerce-checkout" aria-labelledby="checkout-heading" aria-live="polite">
      <h2 id="checkout-heading">{order.test_mode && order.status === "paid" ? "Тестовая подписка активирована" : ORDER_STATUS[order.status] || "Заказ тарифа"}</h2>
      <p>{money(order.amount_rub)} · {order.billing_period === "annual" ? "за год" : "за месяц"}</p>
      {order.message && <p>{order.message}</p>}
      {order.test_mode && order.status === "pending_payment" && <button type="button" className="btn" disabled={busy} onClick={() => void completeTest()}>Завершить тестовую оплату</button>}
      {order.checkout_url && order.status === "pending_payment" && <a className="btn" href={order.checkout_url}>Перейти к оплате</a>}
      <p><Link href={commerceHref(audience)}>Перейти к своему тарифу</Link></p>
    </section>}
    <section className="commerce-faq" aria-label="Вопросы о тарифах">
      <h2>Условия без мелкого шрифта</h2>
      <div className="accordion">
        <details><summary>Что доступно бесплатно?</summary><p>Профиль, календарь, услуги, заявки, Deal Room, отзывы и базовая аналитика. Подходящие открытые заказы доступны всем исполнителям.</p></details>
        <details><summary>Можно ли купить верификацию или рейтинг?</summary><p>Нет. Верификация, отзывы, число завершённых сделок и время ответа отражают реальные факты. Подписка их не меняет.</p></details>
        <details><summary>Когда меняется комиссия?</summary><p>Новый тариф учитывается при создании следующего предложения. Условия уже опубликованных предложений сохраняются.</p></details>
        <details><summary>Как работает повышение или понижение тарифа?</summary><p>Повышение начинает новый полный период после оплаты. Автоматического перерасчёта остатка нет. Понижение и отмена действуют после окончания текущего периода; следующий платный период требует оплаты.</p></details>
        <details><summary>Когда доступна онлайн-оплата?</summary><p>После подключения платёжного партнёра и юридического утверждения. Если оплата недоступна, выбор тарифа сохраняет заказ, но не включает платную подписку.</p></details>
        <details><summary>Продвижение гарантирует заказ?</summary><p>Нет. Оно показывается только подходящим запросам и обозначается словом «Продвижение». Доступность даты и обязательные требования сохраняют приоритет.</p></details>
      </div>
    </section>
  </main>;
}
