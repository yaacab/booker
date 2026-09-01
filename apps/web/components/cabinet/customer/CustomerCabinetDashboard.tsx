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
      emptyState={
        <article className="card empty">
          <h2>У вас пока нет заявок</h2>
          <p>Создайте первую заявку или найдите свободный слот в каталоге. Черновик можно заполнить за несколько минут.</p>
          <p className="timeline">Условия и итоговая сумма появятся в Deal Room после серверного предложения.</p>
          <p style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <Link className="btn" href="/events/new">
              Создать заявку
            </Link>
            <Link className="btn secondary" href="/search">
              Открыть каталог
            </Link>
          </p>
        </article>
      }
    >
      <UpcomingEventsWidget events={upcomingEvents} />
      <DraftsWidget drafts={drafts} />
      <NewOffersWidget offers={newOffers} />
      <ExpiringHoldsWidget holds={expiringHolds} />
    </CabinetPageShell>
  );
}
