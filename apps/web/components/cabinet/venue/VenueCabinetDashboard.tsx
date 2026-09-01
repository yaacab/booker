"use client";

import Link from "next/link";
import { CabinetPageShell } from "../CabinetPageShell";
import { SupplyCabinetSection } from "../SupplyCabinetSection";
import { AwaitingResponseWidget } from "../performer/widgets/AwaitingResponseWidget";
import { CalendarConflictsWidget } from "../performer/widgets/CalendarConflictsWidget";
import { ExpiringOffersWidget } from "../performer/widgets/ExpiringOffersWidget";
import { HoldsWidget } from "../performer/widgets/HoldsWidget";
import { NewRequestsWidget } from "../performer/widgets/NewRequestsWidget";
import { ProfileCompletenessWidget } from "../performer/widgets/ProfileCompletenessWidget";
import { UpcomingPerformancesWidget } from "../performer/widgets/UpcomingPerformancesWidget";
import { useVenueCabinetData } from "./useVenueCabinetData";
import { VenueHallsWidget } from "./widgets/VenueHallsWidget";

export function VenueCabinetDashboard() {
  const {
    ready,
    error,
    email,
    orgName,
    orgId,
    role,
    newRequests,
    awaitingResponse,
    expiringOffers,
    activeHolds,
    upcomingEvents,
    calendarConflicts,
    profileIncomplete,
    halls,
    empty,
    offerBusy,
    sendOffer,
  } = useVenueCabinetData();

  return (
    <CabinetPageShell
      mode="venue"
      ready={ready}
      error={error}
      email={email}
      orgName={orgName}
      empty={empty}
      emptyState={
        <article className="card empty">
          <h2>Пока нет входящих заявок</h2>
          <p>Когда заказчик отправит запрос на ваш зал, он появится здесь.</p>
          <p className="timeline">Условия и итоговая сумма появятся в Deal Room после серверного предложения.</p>
          <p style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <Link className="btn secondary" href="/search">
              Открыть каталог
            </Link>
          </p>
        </article>
      }
      footer={orgId ? <SupplyCabinetSection orgId={orgId} role={role} /> : null}
    >
      <NewRequestsWidget
        requests={newRequests}
        role={role}
        offerBusy={offerBusy}
        onSendOffer={(item) => void sendOffer(item)}
      />
      <AwaitingResponseWidget deals={awaitingResponse} />
      <ExpiringOffersWidget deals={expiringOffers} />
      <HoldsWidget holds={activeHolds} />
      <UpcomingPerformancesWidget bookings={upcomingEvents} />
      <CalendarConflictsWidget conflicts={calendarConflicts} />
      <VenueHallsWidget halls={halls} />
      {profileIncomplete ? <ProfileCompletenessWidget completeness={profileIncomplete} /> : null}
    </CabinetPageShell>
  );
}
