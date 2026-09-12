"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { formatWhen, money } from "@/lib/format";
import { commerceError, type BillingOrder, type CommerceCatalog } from "@/lib/commerce";

type Campaign = {
  id: string; target_id: string; target_type: string; product_code: string; status: string;
  starts_at: string; ends_at: string; impressions: number; clicks: number; ctr: number | null;
  requests: number; bookings: number; order: BillingOrder | null;
};
type Campaigns = {
  items: Campaign[]; credits: { included: number; used: number; remaining: number; period: string };
  targets: { id: string; name: string; type: "artist" | "venue" }[];
};
const STATUS: Record<string, string> = {
  draft: "Черновик", pending_payment: "Ожидает оплаты", scheduled: "Запланировано",
  active: "Идёт продвижение", expired: "Завершено", cancelled: "Отменено", rejected: "Требуется проверка",
};

export function PromotionPanel({ orgId, canManage, catalog, onChanged }: { orgId: string; canManage: boolean; catalog: CommerceCatalog; onChanged: () => Promise<void> }) {
  const [data, setData] = useState<Campaigns | null>(null);
  const [target, setTarget] = useState("");
  const [product, setProduct] = useState("BOOST_24H");
  const [credit, setCredit] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const [message, setMessage] = useState("");
  const key = useRef<{ selection: string; value: string } | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setError("");
    void api<Campaigns>(`/commerce/organizations/${orgId}/promotions`, { signal: controller.signal }).then((result) => {
      setData(result); setTarget((previous) => result.targets.some((t) => t.id === previous) ? previous : result.targets[0]?.id || "");
    }).catch((e) => { if (!controller.signal.aborted) setError(commerceError(e)); });
    return () => controller.abort();
  }, [orgId, revision]);

  const chosenTarget = data?.targets.find((t) => t.id === target);
  const products = catalog.promotions.filter((p) => p.audience === chosenTarget?.type);
  const productNames = Object.fromEntries(products.map((p) => [p.code, p.title]));

  async function action(path: string, body?: unknown, created = false) {
    if (busy) return;
    setError(""); setMessage(""); setBusy(true);
    try {
      await api(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
      if (created) key.current = null;
      setMessage(created ? "Кампания создана. Её состояние показано ниже." : "Изменения сохранены.");
      setRevision((r) => r + 1);
      await onChanged();
    } catch (e) { setError(commerceError(e)); }
    finally { setBusy(false); }
  }

  function create() {
    if (!chosenTarget) return;
    const selection = `${orgId}:${target}:${product}:${credit}`;
    if (key.current?.selection !== selection) key.current = { selection, value: crypto.randomUUID() };
    void action(`/commerce/organizations/${orgId}/promotions`, { target_id: target, target_type: chosenTarget.type,
      product_code: product, use_credit: credit, idempotency_key: key.current.value }, true);
  }

  return <section className="commerce-checkout" aria-label="Продвижение">
    <h2>Продвижение свободных дат</h2>
    <p>Карточка получит метку «Продвижение». Она появится только там, где подходит запросу и доступна на выбранную дату.</p>
    {error && <div role="alert"><p>{error}</p><button className="btn secondary" type="button" onClick={() => setRevision((r) => r + 1)}>Повторить загрузку кампаний</button></div>}
    {message && <p role="status">{message}</p>}
    {!data && !error && <p role="status">Загружаем кампании…</p>}
    {data && <>
      <p>Включённых Boost осталось: <strong>{data.credits.remaining}</strong> из {data.credits.included} в этом месяце.</p>
      {canManage && data.targets.length > 0 && <div className="card">
        <h3>Создать продвижение</h3>
        <label className="commerce-org">Профиль<select value={target} onChange={(e) => setTarget(e.target.value)}>{data.targets.map((t) => <option value={t.id} key={t.id}>{t.name}</option>)}</select></label>
        <label className="commerce-org">Вариант продвижения<select value={product} onChange={(e) => { setProduct(e.target.value); if (e.target.value !== "BOOST_24H") setCredit(false); }}>{products.map((p) => <option value={p.code} key={p.code}>{p.title} · {money(p.price_rub)}</option>)}</select></label>
        {data.credits.remaining > 0 && product === "BOOST_24H" && <label className="commerce-actions"><input type="checkbox" checked={credit} onChange={(e) => setCredit(e.target.checked)} />Использовать включённый Boost</label>}
        <p className="timeline">Включённый Boost расходуется при запуске. Отмена кампании не возвращает использованный Boost.</p>
        <button type="button" className="btn" disabled={busy || !target} onClick={create}>{busy ? "Сохраняем…" : "Создать продвижение"}</button>
      </div>}
      {data.targets.length === 0 && <p className="empty">Сначала создайте профиль, который будете продвигать.</p>}
      {data.items.length === 0 ? <p className="empty">Кампаний пока нет. Органическая выдача доступна без продвижения.</p> : <ul className="commerce-orders">{data.items.map((campaign) => <li className="commerce-order" key={campaign.id}>
        <h3>{productNames[campaign.product_code] || "Продвижение профиля"}</h3>
        <p>{data.targets.find((t) => t.id === campaign.target_id)?.name || "Профиль"} · <strong>{STATUS[campaign.status] || "Состояние уточняется"}</strong></p>
        {["active", "expired"].includes(campaign.status) && <p>До {formatWhen(campaign.ends_at)}</p>}
        <p>Показы: {campaign.impressions} · Переходы: {campaign.clicks} · Заявки: {campaign.requests} · Бронирования: {campaign.bookings}</p>
        <p>Доля переходов: {campaign.ctr === null ? "пока нет показов" : new Intl.NumberFormat("ru-RU", { style: "percent", maximumFractionDigits: 1 }).format(campaign.ctr)}</p>
        {campaign.order?.message && <p>{campaign.order.message}</p>}
        <div className="commerce-actions">{canManage && campaign.order?.test_mode && campaign.order.status === "pending_payment" && <button className="btn" type="button" disabled={busy} onClick={() => void action(`/commerce/orders/${campaign.order!.id}/test-complete`, { status: "paid" })}>Завершить тестовую оплату продвижения</button>}
          {campaign.order?.checkout_url && campaign.order.status === "pending_payment" && <a className="btn" href={campaign.order.checkout_url}>Оплатить продвижение</a>}
          {canManage && ["pending_payment", "active", "scheduled"].includes(campaign.status) && <button className="btn secondary" type="button" disabled={busy} onClick={() => void action(`/commerce/promotions/${campaign.id}/cancel`)}>Остановить кампанию</button>}
        </div>
      </li>)}</ul>}
    </>}
  </section>;
}
