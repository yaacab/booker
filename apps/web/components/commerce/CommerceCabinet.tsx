"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, getActiveOrg, getToken } from "@/lib/api";
import { money, formatWhen } from "@/lib/format";
import { loginHref } from "@/lib/next";
import { BusinessReporting } from "@/components/business/BusinessReporting";
import { BusinessWorkspace } from "@/components/business/BusinessWorkspace";
import { GrowthPanel } from "./GrowthPanel";
import { PromotionPanel } from "./PromotionPanel";
import { SupplyCabinetNav } from "@/components/cabinet/SupplyCabinetNav";
import { commerceError, commerceHref, feePercent, ORDER_STATUS, type Audience,
  type CommerceCatalog, type CommerceMe, type CommerceOrg, type CommerceState } from "@/lib/commerce";

export function CommerceCabinet({ audience }: { audience: Audience }) {
  const [org, setOrg] = useState<CommerceOrg | null>(null);
  const [data, setData] = useState<CommerceState | null>(null);
  const [catalog, setCatalog] = useState<CommerceCatalog | null>(null);
  const [ready, setReady] = useState(false);
  const [authed, setAuthed] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const [nextPlan, setNextPlan] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    setReady(false); setData(null); setOrg(null); setError("");
    setAuthed(Boolean(getToken()));
    if (!getToken()) { setReady(true); return; }
    async function load() {
      try {
        const [me, plans] = await Promise.all([
          api<CommerceMe>("/me", { signal: controller.signal }),
          api<CommerceCatalog>("/commerce/catalog", { signal: controller.signal }),
        ]);
        if (controller.signal.aborted) return;
        setCatalog(plans);
        const active = getActiveOrg() || me.active_organization_id;
        const workspace = me.organizations.find((o) => o.id === active && o.kind === audience)
          || me.organizations.find((o) => o.kind === audience);
        if (!workspace) return;
        setOrg(workspace);
        const state = await api<CommerceState>(`/commerce/organizations/${workspace.id}`, { signal: controller.signal });
        if (!controller.signal.aborted) setData(state);
      } catch (e) { if (!controller.signal.aborted) setError(commerceError(e)); }
      finally { if (!controller.signal.aborted) setReady(true); }
    }
    void load();
    return () => controller.abort();
  }, [audience, revision]);

  async function mutate(path: string, body?: unknown) {
    if (busy) return;
    setBusy(true); setError(""); setMessage("");
    try {
      await api(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
      setMessage("Изменения сохранены."); setRevision((r) => r + 1);
    } catch (e) { setError(commerceError(e)); }
    finally { setBusy(false); }
  }

  const active = data?.subscription && ["active", "trial"].includes(data.subscription.status);
  const lowerPlans = catalog?.plans.filter((p) => p.audience === audience && p.sort_order < (data?.plan.sort_order ?? 0)) || [];
  const names = Object.fromEntries(catalog?.plans.map((p) => [p.code, p.title]) || []);
  return <main className="commerce-page">
    <p className="kicker">{org?.name || "Моё рабочее пространство"}</p>
    <h1>{audience === "customer" ? "Business для организатора" : "Рост и продвижение"}</h1><p><Link href={org ? `/team?organization=${org.id}` : "/team"}>Управление командой</Link></p>
    {audience !== "customer" && <SupplyCabinetNav mode={audience === "artist" ? "performer" : "venue"} />}
    {!ready && <p role="status">Загружаем тариф и историю заказов…</p>}
    {error && <div role="alert" className="card"><p>{error}</p><button type="button" className="btn secondary" onClick={() => setRevision((r) => r + 1)}>Повторить</button></div>}
    {message && <p role="status">{message}</p>}
    {ready && !authed && <div className="empty"><p>Войдите, чтобы увидеть свой тариф.</p><Link className="btn" href={loginHref(commerceHref(audience))}>Войти</Link></div>}
    {ready && authed && !org && !error && <div className="empty"><p>Создайте рабочее пространство для этой роли.</p><Link className="btn" href="/profile">Создать пространство</Link></div>}
    {data && <>
      <section className="card commerce-checkout" aria-label="Текущий тариф">
        <p className="kicker">Ваш тариф</p><h2>{data.plan.title}</h2>
        <p>{audience === "customer" ? "Сервисный сбор" : "Комиссия с гонорара"}: <strong>{feePercent(audience === "customer" ? data.plan.customer_fee_bps : data.plan.supplier_fee_bps)}</strong></p>
        {active && <p>Текущий период до {formatWhen(data.subscription!.current_period_end)}.</p>}
        {data.subscription?.cancel_at_period_end && active && <p>После окончания периода: {names[data.subscription.next_plan_code || ""] || "бесплатный тариф"}. Для следующего платного периода потребуется оплата.</p>}
        <p className="timeline">Новые комиссии применяются к новым предложениям. Уже опубликованные условия сохраняются.</p>
        <div className="commerce-actions"><Link href="/pricing" className="btn">Сравнить тарифы</Link>
          {active && data.can_manage && !data.subscription?.cancel_at_period_end && <button type="button" className="btn secondary" disabled={busy} onClick={() => void mutate(`/commerce/organizations/${org!.id}/subscription/cancel`)}>Отменить продление</button>}
        </div>
        {active && data.can_manage && lowerPlans.length > 0 && <div className="commerce-checkout">
          <label className="commerce-org">Тариф после текущего периода<select value={nextPlan} onChange={(e) => setNextPlan(e.target.value)}><option value="">Выберите тариф</option>{lowerPlans.map((p) => <option key={p.code} value={p.code}>{p.title}</option>)}</select></label>
          <button type="button" className="btn secondary" disabled={!nextPlan || busy} onClick={() => void mutate(`/commerce/organizations/${org!.id}/subscription/change`, { plan_code: nextPlan })}>Запланировать изменение</button>
        </div>}
      </section>
      {audience === "customer" && org && <BusinessReporting key={`report:${org.id}`} orgId={org.id} />}
      {audience === "customer" && org && <BusinessWorkspace key={org.id} orgId={org.id} />}
      {audience !== "customer" && org && catalog?.flags.ARTIST_GROWTH && <GrowthPanel key={`growth:${org.id}`} orgId={org.id} />}
      {audience !== "customer" && org && catalog?.flags.PAID_PROMOTION && <PromotionPanel key={org.id} orgId={org.id} canManage={data.can_manage} catalog={catalog} onChanged={async () => { const next = await api<CommerceState>(`/commerce/organizations/${org.id}`); setData(next); }} />}
      <section className="commerce-checkout" aria-label="Возможности тарифа"><h2>Включено в ваш тариф</h2><ul className="commerce-feature-list">{Object.entries(data.features).filter(([, v]) => v !== false && v !== 0).map(([code, value]) => <li key={code}>{data.plan.feature_labels[code]}{typeof value === "number" ? `: ${value}` : ""}</li>)}</ul></section>
      <section className="commerce-checkout" aria-label="Заказы и оплата"><h2>Заказы и оплата</h2>
        {data.orders.length === 0 ? <p className="empty">Платных заказов пока нет. Бесплатный тариф уже доступен.</p> : <ul className="commerce-orders">{data.orders.map((order) => <li key={order.id} className="commerce-order">
          <h3>{names[order.product_code] || "Заказ продвижения"} · {money(order.amount_rub)}</h3>
          <p>{order.test_mode ? "Тестовый заказ · " : ""}{ORDER_STATUS[order.status] || "Статус уточняется"}</p>
          <p className="timeline">{formatWhen(order.created_at)}</p>{order.message && <p>{order.message}</p>}
          <div className="commerce-actions">{data.can_manage && order.test_mode && order.status === "pending_payment" && <button type="button" className="btn" disabled={busy} onClick={() => void mutate(`/commerce/orders/${order.id}/test-complete`, { status: "paid" })}>Завершить тестовую оплату</button>}
            {order.checkout_url && order.status === "pending_payment" && <a className="btn" href={order.checkout_url}>Перейти к оплате</a>}
            {data.can_manage && ["created", "pending_payment", "failed"].includes(order.status) && <button type="button" className="btn secondary" disabled={busy} onClick={() => void mutate(`/commerce/orders/${order.id}/cancel`)}>Отменить заказ</button>}
          </div>
        </li>)}</ul>}
      </section>
    </>}
  </main>;
}
