"use client";

import Link from "next/link";
import { formatWhen } from "@/lib/format";
import { STATUS_LABEL } from "@/lib/status";
import { CabinetPageShell } from "../CabinetPageShell";
import { CabinetIcon } from "../CabinetIcon";
import { useCustomerCabinetData } from "./useCustomerCabinetData";
import { DraftsWidget } from "./widgets/DraftsWidget";
import { CustomerOnboardingWidget } from "./widgets/CustomerOnboardingWidget";
import { ExpiringHoldsWidget } from "./widgets/ExpiringHoldsWidget";
import { NewOffersWidget } from "./widgets/NewOffersWidget";
import { UpcomingEventsWidget } from "./widgets/UpcomingEventsWidget";

export function CustomerCabinetDashboard() {
  const { ready, error, email, fullName, orgName, upcomingEvents, drafts, newOffers, expiringHolds, hasEventWithCity, showStartCard } = useCustomerCabinetData();
  const nextEvent = upcomingEvents[0];
  const name = fullName?.trim().split(/\s+/)[0];

  return <CabinetPageShell mode="customer" title={name ? `Привет, ${name}!` : "Мой кабинет"} ready={ready} error={error} email={email} orgName={orgName} empty={false} emptyState={null}
    subtitle={nextEvent ? "Ваше следующее событие скоро. Всё под контролем." : "Ваши события, предложения и договорённости — в одном месте."}
    actions={[{ href: "/events/new", label: "Новое событие", primary: true }]}
    leadBeforeMetrics
    lead={nextEvent ? <article className="customer-next-event">
      <div className="customer-event-art" aria-hidden="true"><span /><span /><span /></div>
      <div className="customer-next-event-copy"><p>{formatWhen(nextEvent.event_date)}</p><h2>{nextEvent.title}</h2>{nextEvent.city ? <p><CabinetIcon name="pin" />{nextEvent.city}</p> : null}<span className="customer-event-status">{STATUS_LABEL[nextEvent.status] || nextEvent.status}</span></div>
      <Link className="btn secondary" href={`/events/${nextEvent.id}`}>Перейти к событию <CabinetIcon name="arrow" /></Link>
    </article> : <article className="customer-start-panel" data-testid="customer-start-card"><div><p className="cabinet-account-context">Ваше первое событие</p><h2>Хорошие события<br />начинаются с людей.</h2><p>Укажите дату, город и нужных специалистов. Найдите тех, кто сделает ваш день особенным.</p><Link className="btn" href="/events/new">Создать событие <CabinetIcon name="arrow" /></Link></div><div className="customer-start-mark" aria-hidden="true">＋</div></article>}
    metrics={[
      { label: "Ближайшие события", value: upcomingEvents.length },
      { label: "Новые предложения", value: newOffers.length, hint: "ждут вашего ответа" },
      { label: "Черновики", value: drafts.length },
      { label: "Удержания", value: expiringHolds.length },
    ]}
  >
    <section className="cabinet-zone-grid workspace-customer-grid" aria-label="Подготовка событий"><NewOffersWidget offers={newOffers} /><DraftsWidget drafts={drafts} />{expiringHolds.length > 0 ? <ExpiringHoldsWidget holds={expiringHolds} /> : null}</section>
    {upcomingEvents.length > 1 ? <UpcomingEventsWidget events={upcomingEvents.slice(1)} /> : null}
    <details className="workspace-disclosure" open={showStartCard || undefined}><summary>Подготовка к первому событию <span aria-hidden="true">＋</span></summary><CustomerOnboardingWidget hasName={Boolean(fullName)} hasContact={Boolean(email)} hasEventWithCity={hasEventWithCity} hasOffers={newOffers.length > 0} /><div className="workspace-quick-links"><Link href="/search">Найти артистов и площадки →</Link><Link href="/cabinet/customer/favorites">Избранное →</Link></div></details>
  </CabinetPageShell>;
}
