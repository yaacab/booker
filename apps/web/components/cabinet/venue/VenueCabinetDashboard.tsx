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
    reload,
  } = useVenueCabinetData();

  const hallCount = halls.filter((h) => h.resource_type === "hall").length;
  const completenessScore = profileIncomplete?.score;
  const hallsActive = hallCount > 0;
  const slotsActive =
    newRequests.length > 0 || activeHolds.length > 0 || upcomingEvents.length > 0;

  return (
    <CabinetPageShell
      mode="venue"
      ready={ready}
      error={error}
      email={email}
      orgName={orgName}
      empty={false}
      emptyState={null}
      subtitle="Залы, календарь и ответы на бронирования — рабочий стол площадки."
      metrics={[
        {
          label: "Залы",
          value: hallCount,
          tone: hallCount ? "live" : "wait",
          hint: "ресурсы календаря",
          glow: hallsActive,
        },
        {
          label: "Новые заявки",
          value: newRequests.length,
          tone: newRequests.length ? "wait" : "default",
          glow: slotsActive && newRequests.length > 0,
        },
        {
          label: "Удержания",
          value: activeHolds.length,
          tone: activeHolds.length ? "wait" : "default",
          glow: slotsActive && activeHolds.length > 0,
        },
        {
          label: "Профиль",
          value: completenessScore != null ? `${completenessScore}%` : "—",
          tone: completenessScore != null && completenessScore >= 80 ? "ok" : "wait",
          hint: "готовность к выдаче",
          glow: hallsActive || slotsActive,
        },
      ]}
      actions={[{ href: "#cabinet-widgets", label: "К календарю", primary: true }]}
      lead={
        orgId ? (
          <OpenSlotsWidget orgId={orgId} role={role} orgName={orgName} supplyKind="venue" />
        ) : null
      }
      footer={orgId ? <SupplyCabinetSection orgId={orgId} role={role} /> : null}
    >
      <section className="cabinet-zone" aria-label="Пространство">
        <h2 className="cabinet-zone-title">Пространство</h2>
        <div className="cabinet-zone-grid">
          <VenueHallsWidget halls={halls} role={role} onChanged={() => void reload()} />
          {profileIncomplete ? <ProfileCompletenessWidget completeness={profileIncomplete} /> : null}
        </div>
      </section>

      <section className="cabinet-zone" aria-label="Заявки и сделки">
        <h2 className="cabinet-zone-title">Заявки и сделки</h2>
        <div className="cabinet-zone-grid">
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
        </div>
      </section>
    </CabinetPageShell>
  );
}
