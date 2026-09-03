"use client";

import { CabinetPageShell } from "../CabinetPageShell";
import { SupplyCabinetSection } from "../SupplyCabinetSection";
import { usePerformerCabinetData } from "./usePerformerCabinetData";
import { AwaitingResponseWidget } from "./widgets/AwaitingResponseWidget";
import { CalendarConflictsWidget } from "./widgets/CalendarConflictsWidget";
import { ExpiringOffersWidget } from "./widgets/ExpiringOffersWidget";
import { HoldsWidget } from "./widgets/HoldsWidget";
import { NewRequestsWidget } from "./widgets/NewRequestsWidget";
import { OpenSlotsWidget } from "./widgets/OpenSlotsWidget";
import { ProfileCompletenessWidget } from "./widgets/ProfileCompletenessWidget";
import { UpcomingPerformancesWidget } from "./widgets/UpcomingPerformancesWidget";

export function PerformerCabinetDashboard() {
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
    upcomingPerformances,
    calendarConflicts,
    profileIncomplete,
    offerBusy,
    sendOffer,
  } = usePerformerCabinetData();

  const noDeals =
    ready &&
    !error &&
    newRequests.length === 0 &&
    awaitingResponse.length === 0 &&
    expiringOffers.length === 0 &&
    activeHolds.length === 0 &&
    upcomingPerformances.length === 0;

  return (
    <CabinetPageShell
      mode="performer"
      kindKey="artist"
      ready={ready}
      error={error}
      email={email}
      orgName={orgName}
      empty={false}
      emptyState={null}
      footer={orgId ? <SupplyCabinetSection orgId={orgId} role={role} /> : null}
    >
      {orgId ? <OpenSlotsWidget orgId={orgId} role={role} orgName={orgName} /> : null}
      {noDeals ? (
        <article className="card empty">
          <h2>Заявок пока нет — это нормально</h2>
          <p>
            Вы не собираете события. Откройте свободные вечера выше: заказчик найдёт вас в каталоге и пришлёт запрос на
            ваш слот.
          </p>
          <p className="timeline">Цена и условия появятся в Deal Room после вашего предложения с сервера.</p>
        </article>
      ) : null}
      <NewRequestsWidget
        requests={newRequests}
        role={role}
        offerBusy={offerBusy}
        onSendOffer={(item) => void sendOffer(item)}
      />
      <AwaitingResponseWidget deals={awaitingResponse} />
      <ExpiringOffersWidget deals={expiringOffers} />
      <HoldsWidget holds={activeHolds} />
      <UpcomingPerformancesWidget bookings={upcomingPerformances} />
      <CalendarConflictsWidget conflicts={calendarConflicts} />
      {profileIncomplete ? <ProfileCompletenessWidget completeness={profileIncomplete} /> : null}
    </CabinetPageShell>
  );
}
