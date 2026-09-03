"use client";

import { CabinetPageShell } from "../CabinetPageShell";
import { SupplyCabinetSection } from "../SupplyCabinetSection";
import { AwaitingResponseWidget } from "../performer/widgets/AwaitingResponseWidget";
import { CalendarConflictsWidget } from "../performer/widgets/CalendarConflictsWidget";
import { ExpiringOffersWidget } from "../performer/widgets/ExpiringOffersWidget";
import { HoldsWidget } from "../performer/widgets/HoldsWidget";
import { NewRequestsWidget } from "../performer/widgets/NewRequestsWidget";
import { OpenSlotsWidget } from "../performer/widgets/OpenSlotsWidget";
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
    offerBusy,
    sendOffer,
  } = useVenueCabinetData();

  const noDeals =
    ready &&
    !error &&
    newRequests.length === 0 &&
    awaitingResponse.length === 0 &&
    expiringOffers.length === 0 &&
    activeHolds.length === 0 &&
    upcomingEvents.length === 0;

  return (
    <CabinetPageShell
      mode="venue"
      ready={ready}
      error={error}
      email={email}
      orgName={orgName}
      empty={false}
      emptyState={null}
      footer={orgId ? <SupplyCabinetSection orgId={orgId} role={role} /> : null}
    >
      {orgId ? <OpenSlotsWidget orgId={orgId} role={role} orgName={orgName} supplyKind="venue" /> : null}
      {noDeals ? (
        <article className="card empty">
          <h2>Заявок пока нет — это нормально</h2>
          <p>
            Площадка не ищет события в каталоге. Откройте свободные слоты залов выше — заказчик найдёт вас по дате и
            пришлёт запрос.
          </p>
          <p className="timeline">Условия и сумма появятся в Deal Room после серверного предложения.</p>
        </article>
      ) : null}
      <VenueHallsWidget halls={halls} />
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
      {profileIncomplete ? <ProfileCompletenessWidget completeness={profileIncomplete} /> : null}
    </CabinetPageShell>
  );
}
