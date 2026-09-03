"use client";

import Link from "next/link";
import { CabinetPageShell } from "../CabinetPageShell";
import { useCustomerCabinetData } from "./useCustomerCabinetData";
import { DraftsWidget } from "./widgets/DraftsWidget";
import { ExpiringHoldsWidget } from "./widgets/ExpiringHoldsWidget";
import { NewOffersWidget } from "./widgets/NewOffersWidget";
import { UpcomingEventsWidget } from "./widgets/UpcomingEventsWidget";

export function CustomerCabinetDashboard() {
  const {
    ready,
    error,
    email,
    orgName,
    upcomingEvents,
    drafts,
    newOffers,
    expiringHolds,
    empty,
  } = useCustomerCabinetData();

  return (
    <CabinetPageShell
      mode="customer"
      ready={ready}
      error={error}
      email={email}
      orgName={orgName}
      empty={empty}
      subtitle="Соберите состав на дату, примите предложения и доведите сделки до подтверждения."
      metrics={[
        { label: "Ближайшие", value: upcomingEvents.length, tone: upcomingEvents.length ? "ok" : "default" },
        { label: "Черновики", value: drafts.length, tone: drafts.length ? "wait" : "default" },
        { label: "Ждут ответа", value: newOffers.length, tone: newOffers.length ? "wait" : "default", hint: "предложения" },
        { label: "Удержания", value: expiringHolds.length, tone: expiringHolds.length ? "live" : "default" },
      ]}
      actions={[
        { href: "/events/new", label: "Новое событие", primary: true },
        { href: "/search", label: "Каталог" },
      ]}
      emptyState={
        <article className="cabinet-empty-card">
          <p className="cabinet-eyebrow">Старт</p>
          <h2>Соберите первое событие</h2>
          <p>
            Укажите дату и роли — каталог покажет, у кого есть свободный слот. Цена появится только в серверном
            предложении Deal Room.
          </p>
          <div className="cabinet-hero-actions">
            <Link className="btn" href="/events/new">
              Создать событие
            </Link>
            <Link className="btn secondary" href="/search">
              Открыть каталог
            </Link>
          </div>
        </article>
      }
    >
      <section className="cabinet-zone" aria-label="События">
        <h2 className="cabinet-zone-title">События</h2>
        <div className="cabinet-zone-grid">
          <UpcomingEventsWidget events={upcomingEvents} />
          <DraftsWidget drafts={drafts} />
        </div>
      </section>

      <section className="cabinet-zone" aria-label="Сделки">
        <h2 className="cabinet-zone-title">Сделки</h2>
        <div className="cabinet-zone-grid">
          <NewOffersWidget offers={newOffers} />
          <ExpiringHoldsWidget holds={expiringHolds} />
        </div>
      </section>
    </CabinetPageShell>
  );
}
